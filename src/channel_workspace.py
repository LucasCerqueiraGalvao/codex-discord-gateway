from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Iterable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sanitize_channel_name(value: str | None) -> str:
    raw = (value or "").strip().lower()
    cleaned = []
    for char in raw:
        if char.isalnum():
            cleaned.append(char)
        elif char in {" ", "-", "_"}:
            cleaned.append("_")
    text = "".join(cleaned).strip("_")
    while "__" in text:
        text = text.replace("__", "_")
    return text or "channel"


def _format_list(values: Iterable[str]) -> str:
    items = [value.strip() for value in values if value and value.strip()]
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


@dataclass(frozen=True)
class ChannelWorkspaceInfo:
    channel_id: int
    channel_name: str
    workspace_dir: Path
    conversation_path: Path


class ChannelWorkspaceManager:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @property
    def root(self) -> Path:
        return self._root

    def ensure_workspace(self, channel_id: int, channel_name: str | None = None) -> ChannelWorkspaceInfo:
        slug = _sanitize_channel_name(channel_name)
        workspace_dir = self._root / f"{slug}__{channel_id}"
        conversation_path = workspace_dir / "conversation.md"
        metadata_path = workspace_dir / "README.md"

        with self._lock:
            workspace_dir.mkdir(parents=True, exist_ok=True)
            if not metadata_path.exists():
                metadata_path.write_text(
                    "\n".join(
                        [
                            "# Discord Codex Workspace",
                            "",
                            "This directory is the dedicated working directory for one Discord channel.",
                            "",
                            f"- Channel id: `{channel_id}`",
                            f"- Channel name: `{channel_name or 'unknown'}`",
                            "",
                            "Files in this directory are safe places for Codex to keep local notes,",
                            "conversation history, and temporary project-specific artifacts.",
                            "",
                            "Main files:",
                            "- `conversation.md`: append-only Markdown log of prompts and responses.",
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
            if not conversation_path.exists():
                conversation_path.write_text(
                    "\n".join(
                        [
                            "# Conversation History",
                            "",
                            f"- Channel id: `{channel_id}`",
                            f"- Channel name: `{channel_name or 'unknown'}`",
                            f"- Created at: `{_utc_now_iso()}`",
                            "",
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )

        return ChannelWorkspaceInfo(
            channel_id=channel_id,
            channel_name=channel_name or "unknown",
            workspace_dir=workspace_dir,
            conversation_path=conversation_path,
        )

    def append_exchange(
        self,
        *,
        info: ChannelWorkspaceInfo,
        request_id: str,
        source: str,
        prompt: str,
        response: str,
        command: str,
        execution_mode: str | None = None,
        execution_workdir: str | None = None,
        session_id: str | None = None,
        thread_name: str | None = None,
        attachment_names: list[str] | None = None,
        usage_tokens: dict[str, int] | None = None,
    ) -> None:
        lines = [
            f"## Request {request_id}",
            "",
            f"- Timestamp (UTC): `{_utc_now_iso()}`",
            f"- Source: `{source}`",
            f"- Channel workspace: `{info.workspace_dir}`",
            f"- Codex cwd: `{execution_workdir or info.workspace_dir}`",
            f"- Execution mode: `{execution_mode or 'exec'}`",
            f"- Session id: `{session_id or 'unknown'}`",
            f"- Thread name: `{thread_name or 'unknown'}`",
            f"- Command: `{command}`",
            "",
            "### User Prompt",
            "",
            "```text",
            (prompt or "").strip() or "(empty prompt)",
            "```",
            "",
            "### Attachments",
            "",
            _format_list(attachment_names or []),
            "",
        ]

        if usage_tokens:
            lines.extend(
                [
                    "### Usage",
                    "",
                    f"- input_tokens: `{usage_tokens.get('input_tokens', 0)}`",
                    f"- cached_input_tokens: `{usage_tokens.get('cached_input_tokens', 0)}`",
                    f"- output_tokens: `{usage_tokens.get('output_tokens', 0)}`",
                    f"- estimated_billable_tokens: `{usage_tokens.get('estimated_billable_tokens', 0)}`",
                    "",
                ]
            )

        lines.extend(
            [
                "### Codex Response",
                "",
                "```text",
                (response or "").strip() or "(empty response)",
                "```",
                "",
            ]
        )

        with self._lock:
            with info.conversation_path.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
                handle.write("\n")

    def append_error(
        self,
        *,
        info: ChannelWorkspaceInfo,
        request_id: str,
        source: str,
        prompt: str,
        error: str,
        execution_mode: str | None = None,
        execution_workdir: str | None = None,
        session_id: str | None = None,
        attachment_names: list[str] | None = None,
    ) -> None:
        lines = [
            f"## Request {request_id} (error)",
            "",
            f"- Timestamp (UTC): `{_utc_now_iso()}`",
            f"- Source: `{source}`",
            f"- Channel workspace: `{info.workspace_dir}`",
            f"- Codex cwd: `{execution_workdir or info.workspace_dir}`",
            f"- Execution mode: `{execution_mode or 'exec'}`",
            f"- Session id: `{session_id or 'unknown'}`",
            "",
            "### User Prompt",
            "",
            "```text",
            (prompt or "").strip() or "(empty prompt)",
            "```",
            "",
            "### Attachments",
            "",
            _format_list(attachment_names or []),
            "",
            "### Error",
            "",
            "```text",
            error.strip() or "(unknown error)",
            "```",
            "",
        ]

        with self._lock:
            with info.conversation_path.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
                handle.write("\n")
