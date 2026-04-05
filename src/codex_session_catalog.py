from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class CodexSessionCatalog:
    def __init__(self, index_path: Path) -> None:
        self._index_path = index_path
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def upsert(self, session_id: str, thread_name: str, updated_at: str | None = None) -> None:
        normalized_session_id = session_id.strip()
        normalized_thread_name = thread_name.strip()
        normalized_updated_at = (updated_at or "").strip() or _utc_now_iso()
        if not normalized_session_id or not normalized_thread_name:
            return

        with self._lock:
            existing: list[dict[str, str]] = []
            if self._index_path.exists():
                for raw_line in self._index_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    entry_id = str(payload.get("id", "")).strip()
                    entry_name = str(payload.get("thread_name", "")).strip()
                    entry_updated_at = str(payload.get("updated_at", "")).strip()
                    if not entry_id or not entry_name:
                        continue
                    existing.append(
                        {
                            "id": entry_id,
                            "thread_name": entry_name,
                            "updated_at": entry_updated_at or _utc_now_iso(),
                        }
                    )

            deduped: list[dict[str, str]] = []
            seen_ids: set[str] = set()
            for entry in existing:
                entry_id = entry["id"]
                if entry_id == normalized_session_id or entry_id in seen_ids:
                    continue
                deduped.append(entry)
                seen_ids.add(entry_id)

            deduped.append(
                {
                    "id": normalized_session_id,
                    "thread_name": normalized_thread_name,
                    "updated_at": normalized_updated_at,
                }
            )

            temp_path = self._index_path.with_suffix(".tmp")
            temp_path.write_text(
                "\n".join(json.dumps(entry, ensure_ascii=False) for entry in deduped) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(self._index_path)
