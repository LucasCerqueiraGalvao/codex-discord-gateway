from __future__ import annotations

import json
import logging
import shlex
import shutil
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
    usage: "CodexUsage | None" = None
    session_id: str | None = None


@dataclass(frozen=True)
class CodexUsage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int

    @property
    def billable_input_tokens(self) -> int:
        return max(self.input_tokens - self.cached_input_tokens, 0)

    @property
    def estimated_billable_tokens(self) -> int:
        return self.billable_input_tokens + self.output_tokens


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


def _extract_session_id_from_json_lines(lines: Iterable[str]) -> str | None:
    for raw_line in lines:
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "thread.started":
            continue
        thread_id = payload.get("thread_id")
        if isinstance(thread_id, str) and thread_id.strip():
            return thread_id.strip()
    return None


def _coerce_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _extract_usage_from_json_lines(lines: Iterable[str]) -> CodexUsage | None:
    last_usage: CodexUsage | None = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "turn.completed":
            continue
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            continue

        last_usage = CodexUsage(
            input_tokens=_coerce_int(usage.get("input_tokens")),
            cached_input_tokens=_coerce_int(usage.get("cached_input_tokens")),
            output_tokens=_coerce_int(usage.get("output_tokens")),
        )

    return last_usage


def _parse_mode_from_args(args: tuple[str, ...]) -> CommandMode:
    return "json" if "--json" in args else "output_file"


def _has_output_file_arg(args: list[str]) -> bool:
    return "-o" in args or "--output-last-message" in args


RESUME_UNSUPPORTED_OPTIONS: dict[str, int] = {
    "-a": 1,
    "-C": 1,
    "-p": 1,
    "-s": 1,
    "--add-dir": 1,
    "--ask-for-approval": 1,
    "--cd": 1,
    "--no-alt-screen": 0,
    "--profile": 1,
    "--remote": 1,
    "--remote-auth-token-env": 1,
    "--sandbox": 1,
    "--search": 0,
}


def _resolve_updated_vscode_codex(executable: str) -> str | None:
    path = Path(executable)
    normalized = str(path).replace("/", "\\").lower()
    marker = "\\.vscode\\extensions\\openai.chatgpt-"
    suffix = "\\bin\\windows-x86_64\\codex.exe"
    if marker not in normalized or not normalized.endswith(suffix):
        return None

    home = Path.home()
    extensions_dir = home / ".vscode" / "extensions"
    if not extensions_dir.exists():
        return None

    matches = sorted(
        extensions_dir.glob("openai.chatgpt-*/bin/windows-x86_64/codex.exe"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for match in matches:
        if match.exists():
            return str(match)
    return None


def _build_candidate_specs(command_override: str | None) -> list[CodexCommandSpec]:
    if command_override:
        override_args = _split_command(command_override)
        if not override_args:
            raise RuntimeError("CODEX_CMD is empty after parsing.")

        candidates: list[CodexCommandSpec] = []
        seen_args: set[tuple[str, ...]] = set()

        def _append(args: tuple[str, ...]) -> None:
            if not args or args in seen_args:
                return
            seen_args.add(args)
            candidates.append(
                CodexCommandSpec(
                    args=args,
                    mode=_parse_mode_from_args(args),
                )
            )

        _append(override_args)

        executable = override_args[0]
        looks_like_path = "\\" in executable or "/" in executable or ":" in executable
        if looks_like_path and not Path(executable).exists():
            updated_vscode_executable = _resolve_updated_vscode_codex(executable)
            if updated_vscode_executable:
                _append((updated_vscode_executable, *override_args[1:]))

            fallback_names: list[str] = []
            executable_path = Path(executable)
            if executable_path.name:
                fallback_names.append(executable_path.name)
            if executable_path.stem and executable_path.stem not in fallback_names:
                fallback_names.append(executable_path.stem)
            if "codex" not in fallback_names:
                fallback_names.append("codex")

            for fallback_name in fallback_names:
                resolved = shutil.which(fallback_name)
                if resolved:
                    _append((resolved, *override_args[1:]))

        for default_spec in DEFAULT_COMMAND_SPECS:
            _append(default_spec.args)

        return candidates

    return list(DEFAULT_COMMAND_SPECS)


def _strip_unsupported_resume_args(args: tuple[str, ...]) -> tuple[str, ...]:
    filtered: list[str] = []
    idx = 0
    while idx < len(args):
        arg = args[idx]
        skip_count = RESUME_UNSUPPORTED_OPTIONS.get(arg)
        if skip_count is None:
            filtered.append(arg)
            idx += 1
            continue
        idx += 1 + skip_count
    return tuple(filtered)


def _build_resume_spec(spec: CodexCommandSpec) -> CodexCommandSpec | None:
    args = list(spec.args)
    try:
        exec_index = args.index("exec")
    except ValueError:
        return None

    resume_args = tuple([*args[: exec_index + 1], "resume", *args[exec_index + 1 :]])
    return CodexCommandSpec(
        args=_strip_unsupported_resume_args(resume_args),
        mode=spec.mode,
    )


def _run_with_spec(
    spec: CodexCommandSpec,
    prompt: str,
    timeout_seconds: int,
    workdir: str | None = None,
    image_paths: list[str] | None = None,
    session_id: str | None = None,
) -> CodexResult:
    cmd = list(spec.args)
    output_file_path: Path | None = None
    command_str = " ".join(spec.args)

    if spec.mode == "output_file" and not _has_output_file_arg(cmd):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as handle:
            output_file_path = Path(handle.name)
        cmd.extend(["-o", str(output_file_path)])

    if image_paths:
        for image_path in image_paths:
            cmd.extend(["--image", image_path])

    if session_id:
        cmd.append(session_id)

    cmd.extend(["--", prompt])

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

        usage: CodexUsage | None = None
        if spec.mode == "json":
            lines = stdout.splitlines()
            text = _extract_text_from_json_lines(lines).strip()
            usage = _extract_usage_from_json_lines(lines)
            parsed_session_id = _extract_session_id_from_json_lines(lines)
        else:
            text = ""
            parsed_session_id = None
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
            usage=usage,
            session_id=parsed_session_id,
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

    def run(
        self,
        prompt: str,
        image_paths: list[str] | None = None,
        workdir: str | None = None,
    ) -> CodexResult:
        errors: list[str] = []
        candidates: list[CodexCommandSpec] = []
        effective_workdir = workdir if workdir is not None else self._workdir

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
                    workdir=effective_workdir,
                    image_paths=image_paths,
                )
            except Exception as exc:
                errors.append(str(exc))
                continue

            self._active_spec = spec
            self._logger.info("Codex command selected: %s", result.command)
            return result

        error_details = " | ".join(errors) if errors else "Unknown error."
        raise RuntimeError(f"No Codex command worked. Details: {error_details}")

    def resume(
        self,
        session_id: str,
        prompt: str,
        image_paths: list[str] | None = None,
        workdir: str | None = None,
    ) -> CodexResult:
        errors: list[str] = []
        effective_workdir = workdir if workdir is not None else self._workdir

        base_candidates: list[CodexCommandSpec] = []
        if self._active_spec is not None:
            base_candidates.append(self._active_spec)
        for spec in self._candidates:
            if spec not in base_candidates:
                base_candidates.append(spec)

        for base_spec in base_candidates:
            resume_spec = _build_resume_spec(base_spec)
            if resume_spec is None:
                continue
            try:
                result = _run_with_spec(
                    spec=resume_spec,
                    prompt=prompt,
                    timeout_seconds=self._timeout_seconds,
                    workdir=effective_workdir,
                    image_paths=image_paths,
                    session_id=session_id,
                )
            except Exception as exc:
                errors.append(str(exc))
                continue

            self._active_spec = base_spec
            self._logger.info("Codex resume command selected: %s", result.command)
            return result

        error_details = " | ".join(errors) if errors else "Unknown error."
        raise RuntimeError(f"No Codex resume command worked. Details: {error_details}")
