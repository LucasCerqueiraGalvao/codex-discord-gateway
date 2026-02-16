from __future__ import annotations

import json
import logging
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal


CommandMode = Literal["json", "output_file"]


@dataclass(frozen=True)
class CodexCommandSpec:
    args: tuple[str, ...]
    mode: CommandMode


@dataclass(frozen=True)
class CodexResult:
    text: str
    stdout: str
    stderr: str
    return_code: int
    command: str


DEFAULT_COMMAND_SPECS: tuple[CodexCommandSpec, ...] = (
    CodexCommandSpec(args=("codex", "exec", "--skip-git-repo-check", "--json"), mode="json"),
    CodexCommandSpec(args=("codex", "exec", "--json"), mode="json"),
    CodexCommandSpec(args=("codex", "exec", "--skip-git-repo-check"), mode="output_file"),
    CodexCommandSpec(args=("codex", "exec"), mode="output_file"),
)


def _split_command(command: str) -> tuple[str, ...]:
    return tuple(shlex.split(command, posix=False))


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


def _parse_mode_from_args(args: tuple[str, ...]) -> CommandMode:
    return "json" if "--json" in args else "output_file"


def _has_output_file_arg(args: list[str]) -> bool:
    return "-o" in args or "--output-last-message" in args


def _build_candidate_specs(command_override: str | None) -> list[CodexCommandSpec]:
    candidates: list[CodexCommandSpec] = []
    seen: set[tuple[str, ...]] = set()

    if command_override:
        override_args = _split_command(command_override)
        if not override_args:
            raise RuntimeError("CODEX_CMD is empty after parsing.")
        override_spec = CodexCommandSpec(
            args=override_args,
            mode=_parse_mode_from_args(override_args),
        )
        candidates.append(override_spec)
        seen.add(override_spec.args)

    for spec in DEFAULT_COMMAND_SPECS:
        if spec.args in seen:
            continue
        candidates.append(spec)
        seen.add(spec.args)

    return candidates


def _run_with_spec(
    spec: CodexCommandSpec,
    prompt: str,
    timeout_seconds: int,
    workdir: str | None = None,
) -> CodexResult:
    cmd = list(spec.args)
    output_file_path: Path | None = None
    command_str = " ".join(spec.args)

    if spec.mode == "output_file" and not _has_output_file_arg(cmd):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as handle:
            output_file_path = Path(handle.name)
        cmd.extend(["-o", str(output_file_path)])

    cmd.append(prompt)

    try:
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
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"[{command_str}] Timed out after {timeout_seconds}s") from exc

    try:
        stdout = process.stdout.strip()
        stderr = process.stderr.strip()

        if process.returncode != 0:
            error_text = stderr or stdout or f"Command failed with return code {process.returncode}"
            raise RuntimeError(f"[{command_str}] {error_text}")

        if spec.mode == "json":
            text = _extract_text_from_json_lines(stdout.splitlines()).strip()
        else:
            text = ""
            if output_file_path and output_file_path.exists():
                text = output_file_path.read_text(encoding="utf-8", errors="replace").strip()

        if not text:
            text = stdout.strip()

        return CodexResult(
            text=text,
            stdout=stdout,
            stderr=stderr,
            return_code=process.returncode,
            command=command_str,
        )
    finally:
        if output_file_path and output_file_path.exists():
            output_file_path.unlink(missing_ok=True)


class CodexBridge:
    def __init__(
        self,
        command_override: str | None,
        timeout_seconds: int,
        workdir: str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._workdir = workdir
        self._logger = logger or logging.getLogger(__name__)
        self._candidates = _build_candidate_specs(command_override)
        self._active_spec: CodexCommandSpec | None = None

    def run(self, prompt: str) -> CodexResult:
        errors: list[str] = []
        candidates: list[CodexCommandSpec] = []

        if self._active_spec is not None:
            candidates.append(self._active_spec)

        for spec in self._candidates:
            if spec not in candidates:
                candidates.append(spec)

        for spec in candidates:
            try:
                result = _run_with_spec(
                    spec=spec,
                    prompt=prompt,
                    timeout_seconds=self._timeout_seconds,
                    workdir=self._workdir,
                )
            except Exception as exc:
                errors.append(str(exc))
                continue

            self._active_spec = spec
            self._logger.info("Codex command selected: %s", result.command)
            return result

        error_details = " | ".join(errors) if errors else "Unknown error."
        raise RuntimeError(f"No Codex command worked. Details: {error_details}")
