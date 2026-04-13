from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock


def _canonicalize_windows_cwd(raw_cwd: str) -> str:
    normalized = raw_cwd.strip()
    if not normalized:
        return normalized
    if normalized.startswith("\\\\?\\"):
        return normalized

    resolved = str(Path(normalized).resolve(strict=False))
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    if len(resolved) >= 2 and resolved[1] == ":":
        return "\\\\?\\" + resolved
    return resolved


class CodexThreadNormalizer:
    def __init__(self, state_db_path: Path) -> None:
        self._state_db_path = state_db_path
        self._lock = Lock()

    def normalize(
        self,
        session_id: str,
        *,
        cwd: str,
        source: str = "vscode",
    ) -> None:
        normalized_session_id = session_id.strip()
        normalized_source = source.strip() or "vscode"
        normalized_cwd = _canonicalize_windows_cwd(cwd)
        if not normalized_session_id or not normalized_cwd:
            return

        with self._lock:
            rollout_path = self._update_state_db(
                session_id=normalized_session_id,
                cwd=normalized_cwd,
                source=normalized_source,
            )
            if rollout_path is not None:
                self._update_rollout_file(
                    rollout_path=rollout_path,
                    session_id=normalized_session_id,
                    cwd=normalized_cwd,
                    source=normalized_source,
                )

    def _update_state_db(
        self,
        *,
        session_id: str,
        cwd: str,
        source: str,
    ) -> Path | None:
        if not self._state_db_path.exists():
            return None

        conn = sqlite3.connect(self._state_db_path)
        try:
            cur = conn.cursor()
            row = cur.execute(
                "SELECT rollout_path FROM threads WHERE id=?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None

            cur.execute(
                "UPDATE threads SET source=?, cwd=? WHERE id=?",
                (source, cwd, session_id),
            )
            conn.commit()
            rollout_path_raw = row[0]
        finally:
            conn.close()

        if not isinstance(rollout_path_raw, str) or not rollout_path_raw.strip():
            return None
        return Path(rollout_path_raw)

    def _update_rollout_file(
        self,
        *,
        rollout_path: Path,
        session_id: str,
        cwd: str,
        source: str,
    ) -> None:
        if not rollout_path.exists():
            return

        temp_path = rollout_path.with_suffix(rollout_path.suffix + ".tmp")
        try:
            updated_lines: list[str] = []
            for raw_line in rollout_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    updated_lines.append(raw_line)
                    continue

                event_type = payload.get("type")
                if event_type == "session_meta":
                    event_payload = payload.get("payload")
                    if isinstance(event_payload, dict) and event_payload.get("id") == session_id:
                        event_payload["cwd"] = cwd
                        event_payload["source"] = source
                elif event_type == "turn_context":
                    event_payload = payload.get("payload")
                    if isinstance(event_payload, dict):
                        event_payload["cwd"] = cwd

                updated_lines.append(json.dumps(payload, ensure_ascii=False))

            temp_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
            temp_path.replace(rollout_path)
        except PermissionError:
            temp_path.unlink(missing_ok=True)
