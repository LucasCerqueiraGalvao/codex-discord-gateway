from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    discord_token: str
    allowed_user_id: int
    allowed_channel_id: int | None
    codex_cmd: str | None
    codex_timeout_seconds: int
    codex_workdir: str | None
    discord_chunk_size: int
    log_level: str
    log_dir: str
    attachments_temp_dir: str
    attachments_max_mb: int
    attachments_keep_files: bool
    audio_transcription_enabled: bool
    audio_stt_model: str
    audio_stt_language: str | None
    audio_stt_device: str
    audio_stt_compute_type: str
    audio_max_duration_seconds: int
    audio_rate_limit_per_minute: int
    audio_max_files_per_message: int
    token_budget_total: int | None
    message_budget_total: int | None
    context_window_tokens: int | None


def _parse_int(name: str, value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc


def _parse_bool(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean (true/false).")


def _parse_optional_positive_int(name: str, value: str) -> int | None:
    raw = value.strip()
    if not raw:
        return None
    parsed = _parse_int(name, raw)
    if parsed <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")
    return parsed


def load_settings() -> Settings:
    load_dotenv()

    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    allowed_user_id_raw = os.getenv("DISCORD_ALLOWED_USER_ID", "").strip()
    allowed_channel_id_raw = os.getenv("DISCORD_ALLOWED_CHANNEL_ID", "").strip()
    codex_cmd = os.getenv("CODEX_CMD", "").strip() or None
    codex_timeout_raw = os.getenv("CODEX_TIMEOUT_SECONDS", "120").strip()
    codex_workdir = os.getenv("CODEX_WORKDIR", "").strip() or None
    discord_chunk_size_raw = os.getenv("DISCORD_CHUNK_SIZE", "1900").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    log_dir = os.getenv("LOG_DIR", "logs").strip() or "logs"
    attachments_temp_dir = os.getenv("ATTACHMENTS_TEMP_DIR", "runtime/attachments").strip() or "runtime/attachments"
    attachments_max_mb_raw = os.getenv("ATTACHMENTS_MAX_MB", "20").strip()
    attachments_keep_files_raw = os.getenv("ATTACHMENTS_KEEP_FILES", "false").strip()
    audio_transcription_enabled_raw = os.getenv("AUDIO_TRANSCRIPTION_ENABLED", "true").strip()
    audio_stt_model = os.getenv("AUDIO_STT_MODEL", "small").strip() or "small"
    audio_stt_language_raw = os.getenv("AUDIO_STT_LANGUAGE", "pt").strip()
    audio_stt_device = os.getenv("AUDIO_STT_DEVICE", "cpu").strip() or "cpu"
    audio_stt_compute_type = os.getenv("AUDIO_STT_COMPUTE_TYPE", "int8").strip() or "int8"
    audio_max_duration_raw = os.getenv("AUDIO_MAX_DURATION_SECONDS", "60").strip()
    audio_rate_limit_raw = os.getenv("AUDIO_RATE_LIMIT_PER_MINUTE", "4").strip()
    audio_max_files_raw = os.getenv("AUDIO_MAX_FILES_PER_MESSAGE", "3").strip()
    token_budget_total_raw = os.getenv("TOKEN_BUDGET_TOTAL", "").strip()
    message_budget_total_raw = os.getenv("MESSAGE_BUDGET_TOTAL", "").strip()
    context_window_tokens_raw = os.getenv("CONTEXT_WINDOW_TOKENS", "").strip()

    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required.")
    if not allowed_user_id_raw:
        raise RuntimeError("DISCORD_ALLOWED_USER_ID is required.")

    allowed_user_id = _parse_int("DISCORD_ALLOWED_USER_ID", allowed_user_id_raw)
    codex_timeout_seconds = _parse_int("CODEX_TIMEOUT_SECONDS", codex_timeout_raw)
    discord_chunk_size = _parse_int("DISCORD_CHUNK_SIZE", discord_chunk_size_raw)
    attachments_max_mb = _parse_int("ATTACHMENTS_MAX_MB", attachments_max_mb_raw)
    attachments_keep_files = _parse_bool("ATTACHMENTS_KEEP_FILES", attachments_keep_files_raw)
    audio_transcription_enabled = _parse_bool("AUDIO_TRANSCRIPTION_ENABLED", audio_transcription_enabled_raw)
    audio_max_duration_seconds = _parse_int("AUDIO_MAX_DURATION_SECONDS", audio_max_duration_raw)
    audio_rate_limit_per_minute = _parse_int("AUDIO_RATE_LIMIT_PER_MINUTE", audio_rate_limit_raw)
    audio_max_files_per_message = _parse_int("AUDIO_MAX_FILES_PER_MESSAGE", audio_max_files_raw)
    token_budget_total = _parse_optional_positive_int("TOKEN_BUDGET_TOTAL", token_budget_total_raw)
    message_budget_total = _parse_optional_positive_int("MESSAGE_BUDGET_TOTAL", message_budget_total_raw)
    context_window_tokens = _parse_optional_positive_int("CONTEXT_WINDOW_TOKENS", context_window_tokens_raw)

    if codex_timeout_seconds <= 0:
        raise RuntimeError("CODEX_TIMEOUT_SECONDS must be greater than zero.")
    if not 100 <= discord_chunk_size <= 2000:
        raise RuntimeError("DISCORD_CHUNK_SIZE must be between 100 and 2000.")
    if not 1 <= attachments_max_mb <= 200:
        raise RuntimeError("ATTACHMENTS_MAX_MB must be between 1 and 200.")
    if not 5 <= audio_max_duration_seconds <= 3_600:
        raise RuntimeError("AUDIO_MAX_DURATION_SECONDS must be between 5 and 3600.")
    if not 1 <= audio_rate_limit_per_minute <= 120:
        raise RuntimeError("AUDIO_RATE_LIMIT_PER_MINUTE must be between 1 and 120.")
    if not 1 <= audio_max_files_per_message <= 10:
        raise RuntimeError("AUDIO_MAX_FILES_PER_MESSAGE must be between 1 and 10.")

    allowed_channel_id = (
        _parse_int("DISCORD_ALLOWED_CHANNEL_ID", allowed_channel_id_raw)
        if allowed_channel_id_raw
        else None
    )
    audio_stt_language = audio_stt_language_raw or None

    return Settings(
        discord_token=token,
        allowed_user_id=allowed_user_id,
        allowed_channel_id=allowed_channel_id,
        codex_cmd=codex_cmd,
        codex_timeout_seconds=codex_timeout_seconds,
        codex_workdir=codex_workdir,
        discord_chunk_size=discord_chunk_size,
        log_level=log_level,
        log_dir=log_dir,
        attachments_temp_dir=attachments_temp_dir,
        attachments_max_mb=attachments_max_mb,
        attachments_keep_files=attachments_keep_files,
        audio_transcription_enabled=audio_transcription_enabled,
        audio_stt_model=audio_stt_model,
        audio_stt_language=audio_stt_language,
        audio_stt_device=audio_stt_device,
        audio_stt_compute_type=audio_stt_compute_type,
        audio_max_duration_seconds=audio_max_duration_seconds,
        audio_rate_limit_per_minute=audio_rate_limit_per_minute,
        audio_max_files_per_message=audio_max_files_per_message,
        token_budget_total=token_budget_total,
        message_budget_total=message_budget_total,
        context_window_tokens=context_window_tokens,
    )
