from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ChannelSession:
    channel_id: int
    session_id: str
    thread_name: str
    updated_at: str


class ChannelSessionStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _read_unlocked(self) -> dict[str, dict[str, str]]:
        if not self._path.exists():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        normalized: dict[str, dict[str, str]] = {}
        for key, value in payload.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            session_id = str(value.get("session_id", "")).strip()
            thread_name = str(value.get("thread_name", "")).strip()
            updated_at = str(value.get("updated_at", "")).strip()
            if not session_id:
                continue
            normalized[key] = {
                "session_id": session_id,
                "thread_name": thread_name,
                "updated_at": updated_at or _utc_now_iso(),
            }
        return normalized

    def _write_unlocked(self, payload: dict[str, dict[str, str]]) -> None:
        temp_path = self._path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self._path)

    def get(self, channel_id: int) -> ChannelSession | None:
        key = str(channel_id)
        with self._lock:
            payload = self._read_unlocked()
            record = payload.get(key)
            if record is None:
                return None
            return ChannelSession(
                channel_id=channel_id,
                session_id=record["session_id"],
                thread_name=record.get("thread_name", ""),
                updated_at=record.get("updated_at", "") or _utc_now_iso(),
            )

    def set(
        self,
        channel_id: int,
        session_id: str,
        thread_name: str,
        updated_at: str | None = None,
    ) -> ChannelSession:
        key = str(channel_id)
        normalized_updated_at = (updated_at or "").strip() or _utc_now_iso()
        normalized_thread_name = thread_name.strip()

        with self._lock:
            payload = self._read_unlocked()
            payload[key] = {
                "session_id": session_id.strip(),
                "thread_name": normalized_thread_name,
                "updated_at": normalized_updated_at,
            }
            self._write_unlocked(payload)

        return ChannelSession(
            channel_id=channel_id,
            session_id=session_id.strip(),
            thread_name=normalized_thread_name,
            updated_at=normalized_updated_at,
        )

    def remove(self, channel_id: int) -> ChannelSession | None:
        key = str(channel_id)
        with self._lock:
            payload = self._read_unlocked()
            record = payload.pop(key, None)
            self._write_unlocked(payload)

        if record is None:
            return None
        return ChannelSession(
            channel_id=channel_id,
            session_id=record.get("session_id", "").strip(),
            thread_name=record.get("thread_name", "").strip(),
            updated_at=record.get("updated_at", "").strip() or _utc_now_iso(),
        )
