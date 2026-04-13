from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StablePromptBundle:
    main_prompt: str
    face_prompt: str
    negative_prompt: str
    face_negative_prompt: str
    source: str
    updated_at: str | None = None
    last_image_path: str | None = None

    def with_updates(
        self,
        *,
        main_prompt: str | None = None,
        face_prompt: str | None = None,
        negative_prompt: str | None = None,
        face_negative_prompt: str | None = None,
        source: str | None = None,
        updated_at: str | None = None,
        last_image_path: str | None = None,
    ) -> "StablePromptBundle":
        return replace(
            self,
            main_prompt=self.main_prompt if main_prompt is None else main_prompt,
            face_prompt=self.face_prompt if face_prompt is None else face_prompt,
            negative_prompt=self.negative_prompt if negative_prompt is None else negative_prompt,
            face_negative_prompt=(
                self.face_negative_prompt
                if face_negative_prompt is None
                else face_negative_prompt
            ),
            source=self.source if source is None else source,
            updated_at=self.updated_at if updated_at is None else updated_at,
            last_image_path=self.last_image_path if last_image_path is None else last_image_path,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "main_prompt": self.main_prompt,
            "face_prompt": self.face_prompt,
            "negative_prompt": self.negative_prompt,
            "face_negative_prompt": self.face_negative_prompt,
            "source": self.source,
            "updated_at": self.updated_at,
            "last_image_path": self.last_image_path,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StablePromptBundle":
        required_fields = (
            "main_prompt",
            "face_prompt",
            "negative_prompt",
            "face_negative_prompt",
            "source",
        )
        missing = [field for field in required_fields if not isinstance(payload.get(field), str)]
        if missing:
            missing_fields = ", ".join(sorted(missing))
            raise RuntimeError(f"StablePromptBundle invalido. Campos ausentes: {missing_fields}")

        updated_at = payload.get("updated_at")
        last_image_path = payload.get("last_image_path")
        return cls(
            main_prompt=str(payload["main_prompt"]),
            face_prompt=str(payload["face_prompt"]),
            negative_prompt=str(payload["negative_prompt"]),
            face_negative_prompt=str(payload["face_negative_prompt"]),
            source=str(payload["source"]),
            updated_at=str(updated_at) if isinstance(updated_at, str) and updated_at.strip() else None,
            last_image_path=(
                str(last_image_path)
                if isinstance(last_image_path, str) and last_image_path.strip()
                else None
            ),
        )


class StableStateStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def path_for(self, channel_id: int) -> Path:
        return self._root / f"{int(channel_id)}.json"

    def get(self, channel_id: int) -> StablePromptBundle | None:
        path = self.path_for(channel_id)
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError(f"Estado stable invalido em {path}")
        return StablePromptBundle.from_dict(payload)

    def set(self, channel_id: int, bundle: StablePromptBundle) -> StablePromptBundle:
        path = self.path_for(channel_id)
        updated_bundle = bundle.with_updates(updated_at=datetime.now(timezone.utc).isoformat())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(updated_bundle.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return updated_bundle
