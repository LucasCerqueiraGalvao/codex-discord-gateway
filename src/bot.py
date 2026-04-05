from __future__ import annotations

import asyncio
from collections import defaultdict, deque
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

import discord
from discord.ext import commands

from .actions import ActionRegistry, render_action_result
from .attachments import cleanup_attachments, download_attachments
from .audio_transcriber import AudioTooLongError, AudioTranscriptionError, LocalAudioTranscriber
from .codex_bridge import CodexBridge, CodexUsage
from .config import Settings, load_settings
from .codex_official_status import (
    read_latest_token_count_snapshot,
    read_local_total_tokens_last_days,
    read_official_rate_limits,
)
from .codex_session_catalog import CodexSessionCatalog
from .codex_thread_normalizer import CodexThreadNormalizer
from .channel_sessions import ChannelSessionStore
from .channel_workspace import ChannelWorkspaceManager
from .history_log import HistoryLogger
from .text_utils import split_for_discord


logger = logging.getLogger("discord_codex_gateway")
REASONING_PATTERN = re.compile(r'model_reasoning_effort\s*=\s*(?:"[^"]*"|\'[^\']*\'|\S+)')
MAX_CONTEXT_TURNS = 8
MAX_CONTEXT_ENTRY_CHARS = 1600
CHARS_PER_TOKEN_ESTIMATE = 4
AUDIO_RATE_WINDOW_SECONDS = 60

REASONING_BY_COMMAND: dict[str, str] = {
    "baixo": "low",
    "medio": "medium",
    "alto": "high",
    "altissimo": "xhigh",
}


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _empty_usage_stats() -> dict[str, int]:
    return {
        "messages_sent": 0,
        "responses_sent": 0,
        "usage_samples": 0,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "estimated_billable_tokens": 0,
    }


def _usage_tuple_from_payload(payload: object) -> tuple[int, int, int] | None:
    if not isinstance(payload, dict):
        return None
    input_tokens = _safe_int(payload.get("input_tokens"))
    cached_input_tokens = _safe_int(payload.get("cached_input_tokens"))
    output_tokens = _safe_int(payload.get("output_tokens"))
    return input_tokens, cached_input_tokens, output_tokens


def _add_usage_to_stats(stats: dict[str, int], usage: CodexUsage) -> None:
    stats["usage_samples"] += 1
    stats["input_tokens"] += max(usage.input_tokens, 0)
    stats["cached_input_tokens"] += max(usage.cached_input_tokens, 0)
    stats["output_tokens"] += max(usage.output_tokens, 0)
    stats["estimated_billable_tokens"] += max(usage.estimated_billable_tokens, 0)


def _load_usage_stats_from_history(path: Path) -> dict[str, int]:
    stats = _empty_usage_stats()
    if not path.exists():
        return stats

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            event = payload.get("event")
            if event == "codex_request":
                stats["messages_sent"] += 1
                continue
            if event != "codex_response":
                continue

            stats["responses_sent"] += 1
            usage_data = _usage_tuple_from_payload(payload.get("usage_tokens"))
            if usage_data is None:
                continue

            input_tokens, cached_input_tokens, output_tokens = usage_data
            _add_usage_to_stats(
                stats,
                CodexUsage(
                    input_tokens=max(input_tokens, 0),
                    cached_input_tokens=max(cached_input_tokens, 0),
                    output_tokens=max(output_tokens, 0),
                ),
            )

    return stats


def _parse_iso_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_gateway_tokens_last_days(path: Path, days: int = 7) -> int:
    if days <= 0 or not path.exists():
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total = 0
    prompt_chars_by_request: dict[str, int] = {}

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_time = _parse_iso_utc(payload.get("timestamp_utc"))
            if event_time is None or event_time < cutoff:
                continue

            event_name = payload.get("event")
            if event_name == "codex_request":
                request_id = payload.get("request_id")
                prompt_text = payload.get("prompt", "")
                if isinstance(request_id, str):
                    prompt_chars_by_request[request_id] = len(str(prompt_text))
                continue

            if event_name != "codex_response":
                continue

            usage = payload.get("usage_tokens")
            if not isinstance(usage, dict):
                request_id = payload.get("request_id")
                prompt_chars = prompt_chars_by_request.get(request_id, 0) if isinstance(request_id, str) else 0
                response_chars = len(str(payload.get("response", "")))
                estimated_chars = max(prompt_chars + response_chars, 0)
                estimated_tokens = (estimated_chars + CHARS_PER_TOKEN_ESTIMATE - 1) // CHARS_PER_TOKEN_ESTIMATE
                total += max(estimated_tokens, 0)
                continue

            estimated = _safe_int(usage.get("estimated_billable_tokens"))
            if estimated <= 0:
                input_tokens = _safe_int(usage.get("input_tokens"))
                cached_input_tokens = _safe_int(usage.get("cached_input_tokens"))
                output_tokens = _safe_int(usage.get("output_tokens"))
                estimated = max(input_tokens - cached_input_tokens, 0) + max(output_tokens, 0)

            total += max(estimated, 0)

    return total


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


def _compact_text(text: str, max_chars: int = MAX_CONTEXT_ENTRY_CHARS) -> str:
    normalized = (text or "").replace("\r\n", "\n").strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _build_thread_name(
    *,
    prompt: str,
    channel_name: str | None = None,
    attachment_names: list[str] | None = None,
) -> str:
    normalized = re.sub(r"\s+", " ", (prompt or "").strip())
    if not normalized and attachment_names:
        normalized = "Analisar " + ", ".join(name.strip() for name in attachment_names if name.strip())
    if not normalized:
        normalized = f"Discord {channel_name or 'channel'}"
    if len(normalized) <= 72:
        return normalized
    return normalized[:69].rstrip() + "..."


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
    project_root = Path(__file__).resolve().parent.parent
    attachments_root = (project_root / settings.attachments_temp_dir).resolve()
    channel_workspaces_root = (project_root / "runtime" / "channel_workspaces").resolve()
    channel_sessions_path = (project_root / "runtime" / "channel_sessions.json").resolve()
    codex_session_index_path = (Path.home() / ".codex" / "session_index.jsonl").resolve()
    codex_state_db_path = (Path.home() / ".codex" / "state_5.sqlite").resolve()
    history_path = Path(settings.log_dir) / "history.jsonl"
    usage_stats = _load_usage_stats_from_history(history_path)
    history = HistoryLogger(history_path)
    channel_workspaces = ChannelWorkspaceManager(channel_workspaces_root)
    channel_sessions = ChannelSessionStore(channel_sessions_path)
    session_catalog = CodexSessionCatalog(codex_session_index_path)
    thread_normalizer = CodexThreadNormalizer(codex_state_db_path)
    audio_transcriber = (
        LocalAudioTranscriber(
            model_name=settings.audio_stt_model,
            language=settings.audio_stt_language,
            device=settings.audio_stt_device,
            compute_type=settings.audio_stt_compute_type,
            logger=logger,
        )
        if settings.audio_transcription_enabled
        else None
    )
    action_registry = ActionRegistry(settings=settings, logger=logger)
    state = {
        "codex_cmd": runtime_cmd,
        "codex_timeout_seconds": settings.codex_timeout_seconds,
        "codex_bridge": codex_bridge,
        "context_by_channel": {},
        "usage_stats": usage_stats,
        "audio_rate_window": defaultdict(deque),
    }

    def _rebuild_bridge() -> None:
        state["codex_bridge"] = CodexBridge(
            command_override=state["codex_cmd"],
            timeout_seconds=state["codex_timeout_seconds"],
            workdir=settings.codex_workdir,
            logger=logger,
        )

    def _context_key(channel_id: int) -> str:
        return str(channel_id)

    def _reserve_audio_rate_slot(user_id: int, slots: int = 1) -> tuple[bool, float]:
        # Sliding window limiter: X transcriptions per 60s.
        now_ts = datetime.now(timezone.utc).timestamp()
        bucket: deque[float] = state["audio_rate_window"][user_id]
        while bucket and now_ts - bucket[0] > AUDIO_RATE_WINDOW_SECONDS:
            bucket.popleft()
        needed_slots = max(slots, 1)
        if len(bucket) + needed_slots > settings.audio_rate_limit_per_minute:
            retry_after = (
                max(AUDIO_RATE_WINDOW_SECONDS - (now_ts - bucket[0]), 0.0)
                if bucket
                else float(AUDIO_RATE_WINDOW_SECONDS)
            )
            return False, retry_after
        for _ in range(needed_slots):
            bucket.append(now_ts)
        return True, 0.0

    def _context_turns_count(channel_id: int) -> int:
        key = _context_key(channel_id)
        return len(state["context_by_channel"].get(key, []))

    def _reset_context(channel_id: int) -> int:
        key = _context_key(channel_id)
        removed = len(state["context_by_channel"].get(key, []))
        state["context_by_channel"].pop(key, None)
        return removed

    def _append_context(channel_id: int, user_text: str, assistant_text: str) -> None:
        key = _context_key(channel_id)
        context_list = state["context_by_channel"].setdefault(key, [])
        context_list.append(
            {
                "user": _compact_text(user_text),
                "assistant": _compact_text(assistant_text),
            }
        )
        if len(context_list) > MAX_CONTEXT_TURNS:
            del context_list[:-MAX_CONTEXT_TURNS]

    def _build_prompt_with_context(
        channel_id: int,
        latest_prompt: str,
        *,
        include_recent_turns: bool = True,
    ) -> str:
        key = _context_key(channel_id)
        turns = state["context_by_channel"].get(key, []) if include_recent_turns else []

        header = (
            "Contexto: voce esta respondendo em um chat do Discord. "
            "Seja objetivo e util, com formato curto quando possivel."
        )

        if not turns:
            return header + "\n\nMensagem atual do usuario:\n" + latest_prompt

        lines: list[str] = [header, "Historico recente (mais antigo -> mais novo):"]
        for idx, turn in enumerate(turns, start=1):
            lines.append(f"{idx}. Usuario: {turn['user']}")
            lines.append(f"{idx}. Codex: {turn['assistant']}")
        lines.append("Mensagem atual do usuario:")
        lines.append(latest_prompt)
        return "\n".join(lines)

    def _estimate_tokens(text: str) -> int:
        normalized = (text or "").strip()
        if not normalized:
            return 0
        return max((len(normalized) + CHARS_PER_TOKEN_ESTIMATE - 1) // CHARS_PER_TOKEN_ESTIMATE, 1)

    def _context_tokens_estimate(channel_id: int) -> int:
        key = _context_key(channel_id)
        turns = state["context_by_channel"].get(key, [])
        if not turns:
            return 0
        lines: list[str] = []
        for idx, turn in enumerate(turns, start=1):
            lines.append(f"{idx}. Usuario: {turn['user']}")
            lines.append(f"{idx}. Codex: {turn['assistant']}")
        return _estimate_tokens("\n".join(lines))

    def _percent_text(value: int, total: int) -> str:
        if total <= 0:
            return "0.0%"
        return f"{(value / total) * 100:.1f}%"

    def _format_usage_with_optional_total(value: int, total: int | None) -> str:
        if total is None:
            return f"{value}"
        return f"{value} ({_percent_text(value, total)} de {total})"

    def _format_remaining(total: int | None, used: int) -> str:
        if total is None:
            return "nao configurado"
        remaining = total - used
        if remaining >= 0:
            return f"{remaining} ({_percent_text(remaining, total)} de {total})"
        return f"0 (0.0% de {total}, excedido em {-remaining})"

    async def _handle_codex_prompt(
        message: discord.Message,
        prompt: str,
        source: str,
    ) -> None:
        original_prompt = (prompt or "").strip()
        normalized_prompt = original_prompt
        attachments_in_message = list(message.attachments)

        if not normalized_prompt and not attachments_in_message:
            await message.reply(
                "Envie texto, audio ou anexos para eu processar.",
                mention_author=False,
            )
            return

        request_id = uuid4().hex[:8]
        attachment_names = [attachment.filename for attachment in attachments_in_message]
        channel_session = await asyncio.to_thread(channel_sessions.get, message.channel.id)
        history.write(
            {
                "event": "codex_request",
                "request_id": request_id,
                "source": source,
                "user_id": message.author.id,
                "channel_id": message.channel.id,
                "prompt": original_prompt,
                "attachment_count": len(attachments_in_message),
                "attachment_names": attachment_names,
                "session_id": channel_session.session_id if channel_session is not None else None,
            }
        )
        state["usage_stats"]["messages_sent"] += 1
        workspace_info = channel_workspaces.ensure_workspace(
            channel_id=message.channel.id,
            channel_name=getattr(message.channel, "name", None),
        )
        active_workdir = str(channel_workspaces.root)

        logger.info(
            "request_id=%s source=%s received codex prompt with %s chars, %s attachments, session_id=%s",
            request_id,
            source,
            len(normalized_prompt),
            len(attachments_in_message),
            channel_session.session_id if channel_session is not None else "none",
        )

        collection = None
        downloaded_count = 0
        audio_attachment_count = 0
        transcribed_audio_count = 0
        skipped_attachments: list[str] = []
        audio_errors: list[str] = []
        codex_prompt = normalized_prompt
        image_paths: list[str] = []
        user_context_text = normalized_prompt
        execution_mode = "exec"
        session_id_for_request = channel_session.session_id if channel_session is not None else None
        thread_name_for_request = channel_session.thread_name if channel_session is not None else ""

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
                audio_downloaded = [item for item in collection.downloaded if item.is_audio]
                audio_attachment_count = len(audio_downloaded)

                if audio_downloaded:
                    if audio_transcriber is None:
                        audio_errors.append("transcricao de audio desativada neste bot")
                    else:
                        max_audio_files = settings.audio_max_files_per_message
                        allowed_audio_items = audio_downloaded[:max_audio_files]
                        ignored_audio_items = audio_downloaded[max_audio_files:]
                        for item in ignored_audio_items:
                            audio_errors.append(
                                f"{item.original_name} (ignorado: limite de {max_audio_files} audios por mensagem)"
                            )

                        allowed_audio, retry_after = _reserve_audio_rate_slot(
                            message.author.id,
                            slots=len(allowed_audio_items),
                        )
                        if not allowed_audio:
                            retry_after_seconds = max(int(retry_after) + 1, 1)
                            wait_message = (
                                "Muitas transcricoes em sequencia. "
                                f"Tente novamente em cerca de {retry_after_seconds}s."
                            )
                            history.write(
                                {
                                    "event": "audio_rate_limited",
                                    "request_id": request_id,
                                    "source": source,
                                    "user_id": message.author.id,
                                    "channel_id": message.channel.id,
                                    "retry_after_seconds": retry_after_seconds,
                                }
                            )
                            await message.reply(wait_message, mention_author=False)
                            return

                        transcribed_items: list[tuple[str, str, float | None, str | None]] = []
                        for audio_item in allowed_audio_items:
                            try:
                                transcription = await asyncio.to_thread(
                                    audio_transcriber.transcribe,
                                    audio_item.saved_path,
                                    max_duration_seconds=settings.audio_max_duration_seconds,
                                )
                            except AudioTooLongError as exc:
                                audio_errors.append(
                                    f"{audio_item.original_name} (ignorado: {exc.duration_seconds:.1f}s > {exc.max_duration_seconds}s)"
                                )
                                continue
                            except AudioTranscriptionError as exc:
                                audio_errors.append(f"{audio_item.original_name} (erro: {exc})")
                                continue
                            except Exception as exc:
                                audio_errors.append(f"{audio_item.original_name} (erro inesperado: {exc})")
                                continue

                            transcribed_items.append(
                                (
                                    audio_item.original_name,
                                    transcription.text,
                                    transcription.duration_seconds,
                                    transcription.detected_language,
                                )
                            )

                        transcribed_audio_count = len(transcribed_items)
                        if transcribed_items:
                            transcription_lines = ["Transcricao de audio:"]
                            prompt_transcription_lines = ["Transcricao de audio enviada pelo usuario:"]
                            for idx, (name, text, duration, detected_language) in enumerate(transcribed_items, start=1):
                                duration_text = (
                                    f"{duration:.1f}s"
                                    if isinstance(duration, (int, float)) and duration > 0
                                    else "duracao desconhecida"
                                )
                                language_text = detected_language or settings.audio_stt_language or "auto"
                                transcription_lines.append(
                                    f"{idx}) {name} [{duration_text}, idioma={language_text}]"
                                )
                                transcription_lines.append(text)
                                prompt_transcription_lines.append(f"[Audio {idx}: {name}]")
                                prompt_transcription_lines.append(text)

                            transcription_message = "\n".join(transcription_lines)
                            transcription_chunks = split_for_discord(
                                transcription_message,
                                settings.discord_chunk_size,
                            )
                            await message.reply(transcription_chunks[0], mention_author=False)
                            for extra_chunk in transcription_chunks[1:]:
                                await message.channel.send(extra_chunk)

                            prompt_audio_block = "\n".join(prompt_transcription_lines)
                            if normalized_prompt:
                                normalized_prompt = normalized_prompt + "\n\n" + prompt_audio_block
                            else:
                                normalized_prompt = prompt_audio_block

                if collection.downloaded or collection.skipped:
                    attachment_lines = ["Arquivos anexados salvos localmente:"]
                    sent_names: list[str] = []
                    for item in collection.downloaded:
                        if item.is_image:
                            kind = "imagem"
                        elif item.is_audio:
                            kind = "audio"
                        else:
                            kind = "arquivo"
                        sent_names.append(item.original_name)
                        attachment_lines.append(
                            f"- {item.original_name} -> {item.saved_path} ({kind}, {item.size_bytes} bytes)"
                        )
                    for skipped in collection.skipped:
                        attachment_lines.append(f"- {skipped}")
                    if sent_names:
                        user_context_text = (normalized_prompt or "").strip()
                        if user_context_text:
                            user_context_text += "\n"
                        user_context_text += "[Anexos: " + ", ".join(sent_names) + "]"
                    attachment_lines.append("Use os caminhos acima para abrir/analisar os arquivos locais.")
                    if image_paths:
                        attachment_lines.append("As imagens tambem foram enviadas como input visual.")
                    if normalized_prompt:
                        codex_prompt = normalized_prompt + "\n\n" + "\n".join(attachment_lines)
                    else:
                        codex_prompt = "\n".join(attachment_lines)

                if audio_errors:
                    warning_text = "Avisos de audio:\n- " + "\n- ".join(audio_errors)
                    warning_chunks = split_for_discord(warning_text, settings.discord_chunk_size)
                    await message.channel.send(warning_chunks[0])
                    for extra_chunk in warning_chunks[1:]:
                        await message.channel.send(extra_chunk)

                if not normalized_prompt and attachments_in_message:
                    normalized_prompt = "Analise os anexos desta mensagem e responda de forma objetiva."
                    if codex_prompt:
                        codex_prompt = normalized_prompt + "\n\n" + codex_prompt
                    else:
                        codex_prompt = normalized_prompt

                if audio_attachment_count > 0 and transcribed_audio_count == 0 and not original_prompt:
                    only_audio_in_message = all(item.is_audio for item in collection.downloaded) if collection.downloaded else True
                    if only_audio_in_message:
                        await message.reply(
                            "Nao consegui transcrever o audio enviado. Verifique formato/duracao e tente novamente.",
                            mention_author=False,
                        )
                        history.write(
                            {
                                "event": "audio_transcription_failed",
                                "request_id": request_id,
                                "source": source,
                                "audio_attachment_count": audio_attachment_count,
                                "audio_errors": audio_errors,
                            }
                        )
                        return

            async with message.channel.typing():
                active_bridge: CodexBridge = state["codex_bridge"]
                prompt_with_context = _build_prompt_with_context(
                    message.channel.id,
                    codex_prompt,
                    include_recent_turns=channel_session is None,
                )
                if channel_session is not None:
                    try:
                        execution_mode = "resume"
                        result = await asyncio.to_thread(
                            active_bridge.resume,
                            channel_session.session_id,
                            prompt_with_context,
                            image_paths,
                            active_workdir,
                        )
                    except Exception as exc:
                        execution_mode = "exec"
                        logger.warning(
                            "request_id=%s failed to resume session_id=%s; creating a new session instead: %s",
                            request_id,
                            channel_session.session_id,
                            exc,
                        )
                        history.write(
                            {
                                "event": "codex_resume_failed",
                                "request_id": request_id,
                                "source": source,
                                "channel_id": message.channel.id,
                                "session_id": channel_session.session_id,
                                "error": str(exc),
                            }
                        )
                        await asyncio.to_thread(channel_sessions.remove, message.channel.id)
                        channel_session = None
                        session_id_for_request = None
                        thread_name_for_request = ""
                        prompt_with_context = _build_prompt_with_context(
                            message.channel.id,
                            codex_prompt,
                            include_recent_turns=True,
                        )
                        result = await asyncio.to_thread(
                            active_bridge.run,
                            prompt_with_context,
                            image_paths,
                            active_workdir,
                        )
                else:
                    result = await asyncio.to_thread(
                        active_bridge.run,
                        prompt_with_context,
                        image_paths,
                        active_workdir,
                    )
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
                    "audio_attachment_count": audio_attachment_count,
                    "transcribed_audio_count": transcribed_audio_count,
                    "audio_errors": audio_errors,
                    "workdir": active_workdir,
                    "execution_mode": execution_mode,
                    "session_id": session_id_for_request,
                }
            )
            await asyncio.to_thread(
                channel_workspaces.append_error,
                info=workspace_info,
                request_id=request_id,
                source=source,
                prompt=original_prompt or codex_prompt,
                error=str(exc),
                execution_mode=execution_mode,
                execution_workdir=active_workdir,
                session_id=session_id_for_request,
                attachment_names=attachment_names,
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
        if not user_context_text:
            user_context_text = normalized_prompt
        _append_context(message.channel.id, user_context_text, result.text)

        if result.session_id:
            session_id_for_request = result.session_id
        if not thread_name_for_request:
            thread_name_for_request = _build_thread_name(
                prompt=original_prompt or normalized_prompt or codex_prompt,
                channel_name=getattr(message.channel, "name", None),
                attachment_names=attachment_names,
            )
        if session_id_for_request:
            try:
                await asyncio.to_thread(
                    thread_normalizer.normalize,
                    session_id_for_request,
                    cwd=active_workdir,
                    source="vscode",
                )
            except Exception:
                logger.warning(
                    "request_id=%s failed to normalize Codex thread metadata for session_id=%s",
                    request_id,
                    session_id_for_request,
                    exc_info=True,
                )

            updated_session = await asyncio.to_thread(
                channel_sessions.set,
                message.channel.id,
                session_id_for_request,
                thread_name_for_request,
            )
            thread_name_for_request = updated_session.thread_name
            await asyncio.to_thread(
                session_catalog.upsert,
                updated_session.session_id,
                updated_session.thread_name,
                updated_session.updated_at,
            )

        usage_payload: dict[str, int] | None = None
        if result.usage is not None:
            _add_usage_to_stats(state["usage_stats"], result.usage)
            usage_payload = {
                "input_tokens": max(result.usage.input_tokens, 0),
                "cached_input_tokens": max(result.usage.cached_input_tokens, 0),
                "output_tokens": max(result.usage.output_tokens, 0),
                "estimated_billable_tokens": max(result.usage.estimated_billable_tokens, 0),
            }
        state["usage_stats"]["responses_sent"] += 1

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
                "audio_attachment_count": audio_attachment_count,
                "transcribed_audio_count": transcribed_audio_count,
                "audio_errors": audio_errors,
                "context_turns_after": _context_turns_count(message.channel.id),
                "usage_tokens": usage_payload,
                "workdir": active_workdir,
                "execution_mode": execution_mode,
                "session_id": session_id_for_request,
                "thread_name": thread_name_for_request,
            }
        )
        await asyncio.to_thread(
            channel_workspaces.append_exchange,
            info=workspace_info,
            request_id=request_id,
            source=source,
            prompt=original_prompt or codex_prompt,
            response=result.text,
            command=result.command,
            execution_mode=execution_mode,
            execution_workdir=active_workdir,
            session_id=session_id_for_request,
            thread_name=thread_name_for_request,
            attachment_names=attachment_names,
            usage_tokens=usage_payload,
        )

        await message.reply(chunks[0], mention_author=False)
        for extra_chunk in chunks[1:]:
            await message.channel.send(extra_chunk)

    async def _maybe_handle_standard_action(
        message: discord.Message,
        raw_text: str,
        source: str,
    ) -> bool:
        invocation = action_registry.parse_invocation(raw_text)
        if invocation is None:
            return False

        request_id = uuid4().hex[:8]
        history.write(
            {
                "event": "standard_action_request",
                "request_id": request_id,
                "source": source,
                "user_id": message.author.id,
                "channel_id": message.channel.id,
                "raw_text": raw_text,
                "action_name": invocation.name,
                "action_params": invocation.params,
                "explicit_action_call": invocation.explicit,
            }
        )

        logger.info(
            "request_id=%s source=%s action=%s explicit=%s",
            request_id,
            source,
            invocation.name,
            invocation.explicit,
        )

        result = await action_registry.execute(message, invocation)
        result_text = render_action_result(result)
        chunks = split_for_discord(result_text, settings.discord_chunk_size)
        await message.reply(chunks[0], mention_author=False)
        for extra_chunk in chunks[1:]:
            await message.channel.send(extra_chunk)

        history.write(
            {
                "event": "standard_action_response",
                "request_id": request_id,
                "source": source,
                "action_name": result.action,
                "ok": result.ok,
                "status": result.status,
                "message": result.message,
                "data": result.data,
                "chunk_count": len(chunks),
            }
        )
        return True

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

    def _status_text(current_channel_id: int | None = None) -> str:
        current_effort = _extract_reasoning_effort(state["codex_cmd"])
        timeout_seconds = state["codex_timeout_seconds"]
        allowed_channel = settings.allowed_channel_id if settings.allowed_channel_id is not None else "qualquer"
        bridge_workdir = settings.codex_workdir or "(padrao do processo)"
        discord_workspace_root = str(channel_workspaces.root)
        channel_workspace = (
            str(channel_workspaces.ensure_workspace(current_channel_id).workspace_dir)
            if isinstance(current_channel_id, int)
            else "(selecione um canal)"
        )
        active_session = (
            channel_sessions.get(current_channel_id)
            if isinstance(current_channel_id, int)
            else None
        )
        attachment_max_mb = settings.attachments_max_mb
        attachment_keep = settings.attachments_keep_files
        attachment_temp = settings.attachments_temp_dir
        context_turns = _context_turns_count(current_channel_id) if isinstance(current_channel_id, int) else 0

        def _fmt_int(value: int | None) -> str:
            if not isinstance(value, int):
                return "indisponivel"
            return f"{value:,}".replace(",", ".")

        def _fmt_pct(value: float | None) -> str:
            if not isinstance(value, (int, float)):
                return "indisponivel"
            rounded = round(float(value), 1)
            if rounded.is_integer():
                return f"{int(rounded)}%"
            return f"{rounded:.1f}%"

        official_limits = read_official_rate_limits(timeout_seconds=6)
        weekly_used_pct = official_limits.secondary_used_percent if official_limits is not None else None
        short_used_pct = official_limits.primary_used_percent if official_limits is not None else None
        weekly_available_pct = None if weekly_used_pct is None else max(100.0 - weekly_used_pct, 0.0)
        short_available_pct = None if short_used_pct is None else max(100.0 - short_used_pct, 0.0)

        gateway_week_tokens = _load_gateway_tokens_last_days(history_path, days=7)
        local_week_tokens = read_local_total_tokens_last_days(days=7)
        gateway_weekly_pct: float | None = None
        if isinstance(weekly_used_pct, (int, float)) and isinstance(local_week_tokens, int) and local_week_tokens > 0:
            gateway_share = min(max(gateway_week_tokens / local_week_tokens, 0.0), 1.0)
            gateway_weekly_pct = float(weekly_used_pct) * gateway_share

        latest_token_count = read_latest_token_count_snapshot()
        if context_turns <= 0:
            context_tokens_now: int | None = 0
        elif latest_token_count is None:
            context_tokens_now = None
        else:
            context_tokens_now = latest_token_count.last_tokens
            if not isinstance(context_tokens_now, int):
                context_tokens_now = latest_token_count.total_tokens

        tokens_gateway_text = _fmt_int(gateway_week_tokens)
        gateway_weekly_pct_text = _fmt_pct(gateway_weekly_pct)
        context_tokens_text = _fmt_int(context_tokens_now)
        weekly_available_text = _fmt_pct(weekly_available_pct)
        short_available_text = _fmt_pct(short_available_pct)

        return (
            "Status atual:\n"
            "1) Configuracao\n"
            f"- reasoning: {current_effort}\n"
            f"- timeout: {timeout_seconds}s\n"
            f"- canal permitido: {allowed_channel}\n"
            f"- workdir base do bridge: {bridge_workdir}\n"
            f"- raiz de workspaces: {channel_workspaces.root}\n"
            f"- cwd usado nas sessoes Discord: {discord_workspace_root}\n"
            f"- pasta de artefatos deste canal: {channel_workspace}\n"
            f"- sessao ativa deste canal: {active_session.session_id if active_session else 'nenhuma'}\n"
            f"- titulo indexado: {active_session.thread_name if active_session else 'nenhum'}\n"
            f"- pasta anexos: {attachment_temp}\n"
            f"- anexos max: {attachment_max_mb} MB\n"
            f"- anexos persistentes: {str(attachment_keep).lower()}\n"
            "2) Metricas de Tokens\n"
            f"- Janela de contexto: {context_turns} turnos ({context_tokens_text} tokens)\n"
            f"- Tokens gastos pelo gateway: {tokens_gateway_text} tokens ({gateway_weekly_pct_text} da cota semanal, estimado)\n"
            f"- Limite de uso (semanal): {weekly_available_text} disponivel\n"
            f"- Limite de uso (5h): {short_available_text} disponivel"
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

        if content:
            handled_by_action = await _maybe_handle_standard_action(
                message,
                content,
                source="bang_action" if content.startswith("!") else "plain_action",
            )
            if handled_by_action:
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
            "- `!reset` / `!newchat` -> inicia uma nova conversa do Codex neste canal\n"
            "- `!acoes` / `!actions` -> lista acoes padronizadas\n"
            "- `!comandos` -> exemplos prontos\n"
            "- `!help` -> mostra esta mensagem\n\n"
            "Voce tambem pode mandar mensagem normal sem `!codex`.\n"
            "Acoes padronizadas por texto: `find_file`, `upload_file`, `create_script`.\n"
            "Voice message/arquivo de audio tambem vira prompt via transcricao local.\n"
            "Anexos (txt, py, pdf, imagens etc.) sao baixados e enviados para analise.\n"
            f"Nivel atual: `{current_effort}`"
        )
        await ctx.reply(text, mention_author=False)

    @bot.command(name="acoes", aliases=["actions"])
    async def acoes_cmd(ctx: commands.Context[commands.Bot]) -> None:
        text = action_registry.build_actions_help_text()
        chunks = split_for_discord(text, settings.discord_chunk_size)
        await ctx.reply(chunks[0], mention_author=False)
        for extra_chunk in chunks[1:]:
            await ctx.send(extra_chunk)

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
        text = await asyncio.to_thread(_status_text, ctx.channel.id)
        await ctx.reply(text, mention_author=False)

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

    @bot.command(name="reset", aliases=["newchat"])
    async def reset(ctx: commands.Context[commands.Bot]) -> None:
        removed_turns = _reset_context(ctx.channel.id)
        removed_session = await asyncio.to_thread(channel_sessions.remove, ctx.channel.id)
        history.write(
            {
                "event": "context_reset",
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "removed_turns": removed_turns,
                "removed_session_id": removed_session.session_id if removed_session else None,
            }
        )
        if removed_session is None:
            session_text = "Nenhuma sessao persistente ativa estava vinculada a este canal."
        else:
            session_text = f"Sessao anterior desvinculada: `{removed_session.session_id}`."
        await ctx.reply(
            (
                "Nova conversa preparada para este canal.\n"
                f"- turnos locais removidos: `{removed_turns}`\n"
                f"- {session_text}"
            ),
            mention_author=False,
        )

    @bot.command(name="comandos")
    async def comandos(ctx: commands.Context[commands.Bot]) -> None:
        text = (
            "Exemplos prontos:\n"
            "- `find_file name=\"README.md\" root=\"C:/Users/lucas/Documents/Projects\"`\n"
            "- `upload_file path=\"C:/Users/lucas/Desktop/relatorio.pdf\"`\n"
            "- `create_script name=\"merge_excels\" language=\"python\"`\n"
            "- `liste os atalhos da minha area de trabalho`\n"
            "- `procure na pasta Downloads arquivos .pdf e me diga os 10 mais recentes`\n"
            "- `crie um script python que renomeia arquivos .txt com data e salve em C:/Users/lucas/Desktop`\n"
            "- `faca um resumo do arquivo C:/Users/lucas/Desktop/anotacoes.txt`\n"
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

