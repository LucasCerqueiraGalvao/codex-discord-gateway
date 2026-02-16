from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    discord_token: str
    allowed_user_id: int
    allowed_channel_id: int | None


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

    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required.")
    if not allowed_user_id_raw:
        raise RuntimeError("DISCORD_ALLOWED_USER_ID is required.")

    allowed_user_id = _parse_int("DISCORD_ALLOWED_USER_ID", allowed_user_id_raw)
    allowed_channel_id = (
        _parse_int("DISCORD_ALLOWED_CHANNEL_ID", allowed_channel_id_raw)
        if allowed_channel_id_raw
        else None
    )

    return Settings(
        discord_token=token,
        allowed_user_id=allowed_user_id,
        allowed_channel_id=allowed_channel_id,
    )
