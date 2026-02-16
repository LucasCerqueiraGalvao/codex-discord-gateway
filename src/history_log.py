from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


class HistoryLogger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def write(self, event: dict[str, Any]) -> None:
        payload = dict(event)
        payload.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
        line = json.dumps(payload, ensure_ascii=False)

        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
