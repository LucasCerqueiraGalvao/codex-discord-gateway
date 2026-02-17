from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

import discord
from discord.ext import commands

from .attachments import cleanup_attachments, download_attachments
from .codex_bridge import CodexBridge
from .config import Settings, load_settings
from .history_log import HistoryLogger
from .text_utils import split_for_discord


logger = logging.getLogger("discord_codex_gateway")
REASONING_PATTERN = re.compile(r'model_reasoning_effort\s*=\s*(?:"[^"]*"|\'[^\']*\'|\S+)')

REASONING_BY_COMMAND: dict[str, str] = {
    "baixo": "low",
    "medio": "medium",
    "alto": "high",
    "altissimo": "xhigh",
}


def _configure_logging(settings: Settings) -> None:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, settings.log_level, logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


def _is_allowed_message(settings: Settings, message: discord.Message) -> bool:
    if message.author.bot:
        return False

    if message.author.id != settings.allowed_user_id:
        if message.content.startswith("!"):
            logger.warning(
                "Ignored command from unauthorized user_id=%s on channel_id=%s",
                message.author.id,
                message.channel.id,
            )
        return False

    if settings.allowed_channel_id is not None and message.channel.id != settings.allowed_channel_id:
        logger.warning(
            "Ignored message outside allowed channel_id=%s (got channel_id=%s, user_id=%s)",
            settings.allowed_channel_id,
            message.channel.id,
            message.author.id,
        )
        return False

    return True


def _with_reasoning_effort(command: str, effort: str) -> str:
    normalized = command.strip()
    if REASONING_PATTERN.search(normalized):
        return REASONING_PATTERN.sub(f'model_reasoning_effort="{effort}"', normalized)
    return f'{normalized} -c model_reasoning_effort="{effort}"'


def _extract_reasoning_effort(command: str | None) -> str:
    if not command:
        return "padrao"
    match = REASONING_PATTERN.search(command)
    if not match:
        return "padrao"
    raw = match.group(0).split("=", 1)[1].strip()
    return raw.strip('"').strip("'")


def _persist_env_key(project_root: Path, key: str, value: str) -> None:
    env_path = project_root / ".env"
    if not env_path.exists():
        return

    lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
    updated: list[str] = []
    found = False
    for line in lines:
        if line.startswith(f"{key}="):
            updated.append(f"{key}={value}")
            found = True
        else:
            updated.append(line)

    if not found:
        updated.append(f"{key}={value}")

    env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def build_bot(settings: Settings) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    runtime_cmd = settings.codex_cmd
    if not runtime_cmd:
        runtime_cmd = 'codex exec --skip-git-repo-check --json --sandbox danger-full-access -c model_reasoning_effort="medium"'

    codex_bridge = CodexBridge(
        command_override=runtime_cmd,
        timeout_seconds=settings.codex_timeout_seconds,
        workdir=settings.codex_workdir,
        logger=logger,
    )
    state = {
        "codex_cmd": runtime_cmd,
        "codex_timeout_seconds": settings.codex_timeout_seconds,
        "codex_bridge": codex_bridge,
    }
    project_root = Path(__file__).resolve().parent.parent
    attachments_root = (project_root / settings.attachments_temp_dir).resolve()
    history = HistoryLogger(Path(settings.log_dir) / "history.jsonl")

    def _rebuild_bridge() -> None:
        state["codex_bridge"] = CodexBridge(
            command_override=state["codex_cmd"],
            timeout_seconds=state["codex_timeout_seconds"],
            workdir=settings.codex_workdir,
            logger=logger,
        )

    async def _handle_codex_prompt(
        message: discord.Message,
        prompt: str,
        source: str,
    ) -> None:
        normalized_prompt = (prompt or "").strip()
        attachments_in_message = list(message.attachments)

        if not normalized_prompt and attachments_in_message:
            normalized_prompt = "Analise os anexos desta mensagem e responda de forma objetiva."

        if not normalized_prompt and not attachments_in_message:
            await message.reply(
                "Uso: `!codex <texto>` ou envie mensagem normal no canal.",
                mention_author=False,
            )
            return

        request_id = uuid4().hex[:8]
        attachment_names = [attachment.filename for attachment in attachments_in_message]
        history.write(
            {
                "event": "codex_request",
                "request_id": request_id,
                "source": source,
                "user_id": message.author.id,
                "channel_id": message.channel.id,
                "prompt": normalized_prompt,
                "attachment_count": len(attachments_in_message),
                "attachment_names": attachment_names,
            }
        )

        logger.info(
            "request_id=%s source=%s received codex prompt with %s chars and %s attachments",
            request_id,
            source,
            len(normalized_prompt),
            len(attachments_in_message),
        )

        collection = None
        downloaded_count = 0
        skipped_attachments: list[str] = []
        codex_prompt = normalized_prompt
        image_paths: list[str] = []

        try:
            if attachments_in_message:
                max_bytes = settings.attachments_max_mb * 1024 * 1024
                collection = await download_attachments(
                    attachments=attachments_in_message,
                    temp_root=attachments_root,
                    request_id=request_id,
                    max_bytes=max_bytes,
                )
                downloaded_count = len(collection.downloaded)
                skipped_attachments = list(collection.skipped)
                image_paths = [str(item.saved_path) for item in collection.downloaded if item.is_image]

                if collection.downloaded or collection.skipped:
                    attachment_lines = ["Arquivos anexados salvos localmente:"]
                    for item in collection.downloaded:
                        kind = "imagem" if item.is_image else "arquivo"
                        attachment_lines.append(
                            f"- {item.original_name} -> {item.saved_path} ({kind}, {item.size_bytes} bytes)"
                        )
                    for skipped in collection.skipped:
                        attachment_lines.append(f"- {skipped}")
                    attachment_lines.append("Use os caminhos acima para abrir/analisar os arquivos locais.")
                    if image_paths:
                        attachment_lines.append("As imagens tambem foram enviadas como input visual.")
                    codex_prompt = normalized_prompt + "\n\n" + "\n".join(attachment_lines)

            async with message.channel.typing():
                active_bridge: CodexBridge = state["codex_bridge"]
                result = await asyncio.to_thread(active_bridge.run, codex_prompt, image_paths)
        except Exception as exc:
            logger.exception("request_id=%s failed to execute codex command", request_id)
            history.write(
                {
                    "event": "codex_error",
                    "request_id": request_id,
                    "source": source,
                    "error": str(exc),
                    "downloaded_attachments": downloaded_count,
                    "skipped_attachments": skipped_attachments,
                }
            )
            await message.reply(f"Erro ao executar Codex: {exc}", mention_author=False)
            return
        finally:
            if collection is not None and not settings.attachments_keep_files:
                await asyncio.to_thread(cleanup_attachments, collection.request_dir)

        chunks = split_for_discord(result.text, settings.discord_chunk_size)
        logger.info(
            "request_id=%s response chars=%s split_chunks=%s command=%s downloaded_attachments=%s skipped_attachments=%s",
            request_id,
            len(result.text),
            len(chunks),
            result.command,
            downloaded_count,
            len(skipped_attachments),
        )
        history.write(
            {
                "event": "codex_response",
                "request_id": request_id,
                "source": source,
                "command": result.command,
                "response": result.text,
                "chunk_count": len(chunks),
                "downloaded_attachments": downloaded_count,
                "skipped_attachments": skipped_attachments,
            }
        )

        await message.reply(chunks[0], mention_author=False)
        for extra_chunk in chunks[1:]:
            await message.channel.send(extra_chunk)

    async def _set_reasoning(
        ctx: commands.Context[commands.Bot],
        command_name: str,
        effort: str,
    ) -> None:
        current_cmd: str = state["codex_cmd"]
        new_cmd = _with_reasoning_effort(current_cmd, effort)
        state["codex_cmd"] = new_cmd
        state["codex_bridge"] = CodexBridge(
            command_override=new_cmd,
            timeout_seconds=state["codex_timeout_seconds"],
            workdir=settings.codex_workdir,
            logger=logger,
        )
        _persist_env_key(project_root, "CODEX_CMD", new_cmd)

        history.write(
            {
                "event": "reasoning_changed",
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "command_name": command_name,
                "reasoning_effort": effort,
                "codex_cmd": new_cmd,
            }
        )
        await ctx.reply(
            f'OK. Inteligencia ajustada para `{command_name}` ({effort}).',
            mention_author=False,
        )

    def _status_text() -> str:
        current_effort = _extract_reasoning_effort(state["codex_cmd"])
        timeout_seconds = state["codex_timeout_seconds"]
        channel_id = settings.allowed_channel_id if settings.allowed_channel_id is not None else "qualquer"
        workdir = settings.codex_workdir or "(padrao do processo)"
        attachment_max_mb = settings.attachments_max_mb
        attachment_keep = settings.attachments_keep_files
        attachment_temp = settings.attachments_temp_dir
        return (
            "Status atual:\n"
            f"- reasoning: `{current_effort}`\n"
            f"- timeout: `{timeout_seconds}s`\n"
            f"- canal permitido: `{channel_id}`\n"
            f"- workdir codex: `{workdir}`\n"
            f"- pasta anexos: `{attachment_temp}`\n"
            f"- anexos max: `{attachment_max_mb} MB`\n"
            f"- anexos persistentes: `{attachment_keep}`\n"
            "- entrada: mensagem normal ou `!codex <texto>`"
        )

    @bot.event
    async def on_ready() -> None:
        logger.info("Bot online as %s (id=%s)", bot.user, bot.user.id if bot.user else "unknown")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if not _is_allowed_message(settings, message):
            return

        content = message.content.strip()
        has_attachments = bool(message.attachments)
        if not content and not has_attachments:
            return

        if content.startswith("!ping"):
            await bot.process_commands(message)
            return

        if content.startswith("!codex"):
            prompt = content[len("!codex") :].strip()
            await _handle_codex_prompt(message, prompt, source="bang_command")
            return

        if content.startswith("!"):
            await bot.process_commands(message)
            return

        await _handle_codex_prompt(message, content, source="plain_message")

    @bot.command(name="ping")
    async def ping(ctx: commands.Context[commands.Bot]) -> None:
        history.write(
            {
                "event": "ping",
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
            }
        )
        await ctx.reply("pong", mention_author=False)

    @bot.command(name="help")
    async def help_cmd(ctx: commands.Context[commands.Bot]) -> None:
        current_effort = _extract_reasoning_effort(state["codex_cmd"])
        text = (
            "Comandos disponiveis:\n"
            "- `!ping` -> teste rapido\n"
            "- `!baixo` -> reasoning low\n"
            "- `!medio` -> reasoning medium\n"
            "- `!alto` -> reasoning high\n"
            "- `!altissimo` -> reasoning xhigh\n"
            "- `!status` -> mostra configuracao atual\n"
            "- `!timeout <segundos>` -> altera timeout da execucao\n"
            "- `!reiniciar` -> reinicia processo do bot\n"
            "- `!comandos` -> exemplos prontos\n"
            "- `!help` -> mostra esta mensagem\n\n"
            "Voce tambem pode mandar mensagem normal sem `!codex`.\n"
            "Anexos (txt, py, pdf, imagens etc.) sao baixados e enviados para analise.\n"
            f"Nivel atual: `{current_effort}`"
        )
        await ctx.reply(text, mention_author=False)

    @bot.command(name="baixo")
    async def baixo(ctx: commands.Context[commands.Bot]) -> None:
        await _set_reasoning(ctx, "baixo", REASONING_BY_COMMAND["baixo"])

    @bot.command(name="medio")
    async def medio(ctx: commands.Context[commands.Bot]) -> None:
        await _set_reasoning(ctx, "medio", REASONING_BY_COMMAND["medio"])

    @bot.command(name="alto")
    async def alto(ctx: commands.Context[commands.Bot]) -> None:
        await _set_reasoning(ctx, "alto", REASONING_BY_COMMAND["alto"])

    @bot.command(name="altissimo")
    async def altissimo(ctx: commands.Context[commands.Bot]) -> None:
        await _set_reasoning(ctx, "altissimo", REASONING_BY_COMMAND["altissimo"])

    @bot.command(name="status")
    async def status(ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(_status_text(), mention_author=False)

    @bot.command(name="timeout")
    async def timeout_cmd(ctx: commands.Context[commands.Bot], seconds: str | None = None) -> None:
        if not seconds:
            await ctx.reply(
                f"Timeout atual: `{state['codex_timeout_seconds']}s`. Uso: `!timeout 300`",
                mention_author=False,
            )
            return

        try:
            timeout_value = int(seconds)
        except ValueError:
            await ctx.reply("Valor invalido. Uso: `!timeout 300`", mention_author=False)
            return

        if timeout_value < 30 or timeout_value > 3600:
            await ctx.reply("Use um valor entre 30 e 3600 segundos.", mention_author=False)
            return

        state["codex_timeout_seconds"] = timeout_value
        _rebuild_bridge()
        _persist_env_key(project_root, "CODEX_TIMEOUT_SECONDS", str(timeout_value))

        history.write(
            {
                "event": "timeout_changed",
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "timeout_seconds": timeout_value,
            }
        )
        await ctx.reply(f"Timeout atualizado para `{timeout_value}s`.", mention_author=False)

    @bot.command(name="reiniciar")
    async def reiniciar(ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply("Reiniciando processo do bot...", mention_author=False)
        history.write(
            {
                "event": "bot_restart_requested",
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
            }
        )

        async def _restart() -> None:
            await asyncio.sleep(1.0)
            os.execv(sys.executable, [sys.executable, "-m", "src.bot"])

        asyncio.create_task(_restart())

    @bot.command(name="comandos")
    async def comandos(ctx: commands.Context[commands.Bot]) -> None:
        text = (
            "Exemplos prontos:\n"
            "- `liste os atalhos da minha area de trabalho`\n"
            "- `procure na pasta Downloads arquivos .pdf e me diga os 10 mais recentes`\n"
            "- `crie um script python que renomeia arquivos .txt com data e salve em C:/Users/lucas/Desktop`\n"
            "- `faça um resumo do arquivo C:/Users/lucas/Desktop/anotacoes.txt`\n"
            "- `gere um plano de tarefas para hoje com base no arquivo C:/Users/lucas/Desktop/todo.txt`"
        )
        await ctx.reply(text, mention_author=False)

    @bot.event
    async def on_command_error(ctx: commands.Context[commands.Bot], error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        logger.exception("Unhandled command error: %s", error)
        await ctx.reply("Erro interno no bot. Veja logs locais para detalhes.", mention_author=False)

    return bot


def main() -> None:
    settings = load_settings()
    _configure_logging(settings)
    bot = build_bot(settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
