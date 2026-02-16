from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CodexResult:
    text: str
    stdout: str
    stderr: str
    return_code: int


def _split_command(command: str) -> list[str]:
    return shlex.split(command, posix=False)


def _extract_text_from_json_lines(lines: Iterable[str]) -> str:
    last_message = ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "item.completed":
            continue
        item = payload.get("item", {})
        if item.get("type") == "agent_message":
            last_message = str(item.get("text", "")).strip()
    return last_message


def run_codex(
    prompt: str,
    command: str,
    timeout_seconds: int,
    workdir: str | None = None,
) -> CodexResult:
    cmd = _split_command(command) + [prompt]
    process = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        cwd=workdir,
        shell=False,
        encoding="utf-8",
        errors="replace",
    )

    stdout = process.stdout.strip()
    stderr = process.stderr.strip()

    if process.returncode != 0:
        error_text = stderr or stdout or f"Command failed with return code {process.returncode}"
        raise RuntimeError(error_text)

    parsed = _extract_text_from_json_lines(stdout.splitlines())
    text = parsed or stdout
    return CodexResult(text=text.strip(), stdout=stdout, stderr=stderr, return_code=process.returncode)
