from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

import discord
from discord.ext import commands

from .codex_bridge import CodexBridge
from .config import Settings, load_settings
from .history_log import HistoryLogger
from .text_utils import split_for_discord


logger = logging.getLogger("discord_codex_gateway")


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
        if message.content.startswith("!"):
            logger.warning("Ignored command outside allowed channel_id=%s", settings.allowed_channel_id)
        return False

    return True


def build_bot(settings: Settings) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    codex_bridge = CodexBridge(
        command_override=settings.codex_cmd,
        timeout_seconds=settings.codex_timeout_seconds,
        workdir=settings.codex_workdir,
        logger=logger,
    )
    history = HistoryLogger(Path(settings.log_dir) / "history.jsonl")

    @bot.event
    async def on_ready() -> None:
        logger.info("Bot online as %s (id=%s)", bot.user, bot.user.id if bot.user else "unknown")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if not _is_allowed_message(settings, message):
            return
        await bot.process_commands(message)

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

    @bot.command(name="codex")
    async def codex(ctx: commands.Context[commands.Bot], *, prompt: str | None = None) -> None:
        normalized_prompt = (prompt or "").strip()
        if not normalized_prompt:
            await ctx.reply("Uso: `!codex <texto>`", mention_author=False)
            return

        request_id = uuid4().hex[:8]
        history.write(
            {
                "event": "codex_request",
                "request_id": request_id,
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "prompt": normalized_prompt,
            }
        )

        logger.info("request_id=%s received codex prompt with %s chars", request_id, len(normalized_prompt))
        await ctx.trigger_typing()

        try:
            result = await asyncio.to_thread(codex_bridge.run, normalized_prompt)
        except Exception as exc:
            logger.exception("request_id=%s failed to execute codex command", request_id)
            history.write(
                {
                    "event": "codex_error",
                    "request_id": request_id,
                    "error": str(exc),
                }
            )
            await ctx.reply(f"Erro ao executar Codex: {exc}", mention_author=False)
            return

        chunks = split_for_discord(result.text, settings.discord_chunk_size)
        logger.info(
            "request_id=%s response chars=%s split_chunks=%s command=%s",
            request_id,
            len(result.text),
            len(chunks),
            result.command,
        )
        history.write(
            {
                "event": "codex_response",
                "request_id": request_id,
                "command": result.command,
                "response": result.text,
                "chunk_count": len(chunks),
            }
        )

        first_chunk = chunks[0]
        await ctx.reply(first_chunk, mention_author=False)
        for extra_chunk in chunks[1:]:
            await ctx.send(extra_chunk)

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
