from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    discord_token: str
    allowed_user_id: int
    allowed_channel_id: int | None
    codex_cmd: str
    codex_timeout_seconds: int
    codex_workdir: str | None


def _parse_int(name: str, value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc


def load_settings() -> Settings:
    load_dotenv()

    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    allowed_user_id_raw = os.getenv("DISCORD_ALLOWED_USER_ID", "").strip()
    allowed_channel_id_raw = os.getenv("DISCORD_ALLOWED_CHANNEL_ID", "").strip()
    codex_cmd = os.getenv("CODEX_CMD", "codex exec --skip-git-repo-check --json").strip()
    codex_timeout_raw = os.getenv("CODEX_TIMEOUT_SECONDS", "120").strip()
    codex_workdir = os.getenv("CODEX_WORKDIR", "").strip() or None

    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required.")
    if not allowed_user_id_raw:
        raise RuntimeError("DISCORD_ALLOWED_USER_ID is required.")
    if not codex_cmd:
        raise RuntimeError("CODEX_CMD cannot be empty.")

    allowed_user_id = _parse_int("DISCORD_ALLOWED_USER_ID", allowed_user_id_raw)
    codex_timeout_seconds = _parse_int("CODEX_TIMEOUT_SECONDS", codex_timeout_raw)
    if codex_timeout_seconds <= 0:
        raise RuntimeError("CODEX_TIMEOUT_SECONDS must be greater than zero.")
    allowed_channel_id = (
        _parse_int("DISCORD_ALLOWED_CHANNEL_ID", allowed_channel_id_raw)
        if allowed_channel_id_raw
        else None
    )

    return Settings(
        discord_token=token,
        allowed_user_id=allowed_user_id,
        allowed_channel_id=allowed_channel_id,
        codex_cmd=codex_cmd,
        codex_timeout_seconds=codex_timeout_seconds,
        codex_workdir=codex_workdir,
    )
