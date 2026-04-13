from __future__ import annotations

import ast
import json
import logging
import re
import shlex
import shutil
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal
from urllib.parse import unquote

from .stable_state import StablePromptBundle


CommandMode = Literal["json", "output_file"]


@dataclass(frozen=True)
class CodexCommandSpec:
    args: tuple[str, ...]
    mode: CommandMode


@dataclass(frozen=True)
class CodexArtifact:
    path: str
    source: str
    priority: int
    label: str | None = None


@dataclass(frozen=True)
class CodexResult:
    text: str
    stdout: str
    stderr: str
    return_code: int
    command: str
    usage: "CodexUsage | None" = None
    session_id: str | None = None
    sandbox_policy: str | None = None
    artifacts: tuple[CodexArtifact, ...] = ()
    prompt_bundle: StablePromptBundle | None = None


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
ABSOLUTE_PATH_PREFIX_RE = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\|/)")


def _split_command(command: str) -> tuple[str, ...]:
    return tuple(shlex.split(command, posix=False))


def _iter_json_payloads(lines: Iterable[str]) -> Iterable[dict[str, object]]:
    for raw_line in lines:
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            yield payload


def _iter_response_items(lines: Iterable[str]) -> Iterable[dict[str, object]]:
    for payload in _iter_json_payloads(lines):
        payload_type = payload.get("type")
        item: object | None = None
        if payload_type == "item.completed":
            item = payload.get("item")
        elif payload_type == "response_item":
            item = payload.get("payload")
        elif payload_type in {"message", "agent_message", "function_call_output"}:
            item = payload

        if isinstance(item, dict):
            yield item


def _extract_output_text_from_message_item(item: dict[str, object]) -> str:
    item_type = item.get("type")
    if item_type == "agent_message":
        return str(item.get("text", "")).strip()
    if item_type != "message":
        return ""

    content = item.get("content")
    if not isinstance(content, list):
        return ""

    texts: list[str] = []
    for entry in content:
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type")
        if entry_type not in {"output_text", "text"}:
            continue
        text = entry.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    return "\n".join(texts).strip()


def _extract_text_from_json_lines(lines: Iterable[str]) -> str:
    last_message = ""
    for item in _iter_response_items(lines):
        role = item.get("role")
        if isinstance(role, str) and role not in {"assistant", "agent"}:
            continue
        message_text = _extract_output_text_from_message_item(item)
        if message_text:
            last_message = message_text
    return last_message


def _extract_session_id_from_json_lines(lines: Iterable[str]) -> str | None:
    for payload in _iter_json_payloads(lines):
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
    for payload in _iter_json_payloads(lines):
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


def _normalize_sandbox_policy(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, dict):
        policy_type = value.get("type")
        if isinstance(policy_type, str):
            normalized = policy_type.strip()
            return normalized or None
    return None


def _extract_sandbox_policy_from_json_lines(lines: Iterable[str]) -> str | None:
    last_policy: str | None = None
    for payload in _iter_json_payloads(lines):
        if payload.get("type") != "turn_context":
            continue

        turn_payload = payload.get("payload")
        if not isinstance(turn_payload, dict):
            continue

        normalized = _normalize_sandbox_policy(turn_payload.get("sandbox_policy"))
        if normalized:
            last_policy = normalized

    return last_policy


def _looks_like_absolute_path(value: str) -> bool:
    return bool(re.match(r"^(?:[A-Za-z]:[\\/]|\\\\|/)", value))


def _normalize_artifact_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    candidate = unquote(value.strip().strip("\"'`").strip())
    if not candidate or not _looks_like_absolute_path(candidate):
        return None

    try:
        path = Path(candidate)
    except OSError:
        return None

    if not path.is_absolute():
        return None

    try:
        return str(path.resolve(strict=False))
    except OSError:
        return str(path.absolute())


def _artifact_key(path: str) -> str:
    return path.replace("/", "\\").casefold()


def _add_artifact_candidate(
    artifacts: list[CodexArtifact],
    seen: dict[str, int],
    *,
    path: str,
    source: str,
    priority: int,
    label: str | None,
) -> None:
    normalized_path = _normalize_artifact_path(path)
    if normalized_path is None:
        return

    key = _artifact_key(normalized_path)
    artifact = CodexArtifact(
        path=normalized_path,
        source=source,
        priority=priority,
        label=label,
    )
    existing_index = seen.get(key)
    if existing_index is None:
        seen[key] = len(artifacts)
        artifacts.append(artifact)
        return

    existing = artifacts[existing_index]
    if artifact.priority < existing.priority:
        artifacts[existing_index] = artifact


def _extract_existing_path_prefix(segment: str) -> str | None:
    candidate = segment.rstrip()
    while candidate:
        trimmed = candidate.rstrip(" \t\r\n\"'`<>[](){}.,;")
        normalized = _normalize_artifact_path(trimmed)
        if normalized is not None:
            try:
                if Path(normalized).exists():
                    return normalized
            except OSError:
                return None
        candidate = candidate[:-1]
    return None


def _extract_existing_paths_from_text(text: str) -> list[str]:
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        for match in ABSOLUTE_PATH_PREFIX_RE.finditer(raw_line):
            candidate = _extract_existing_path_prefix(raw_line[match.start() :])
            if candidate is None:
                continue
            key = _artifact_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            found.append(candidate)
    return found


def _iter_embedded_json_values(text: str) -> Iterable[object]:
    decoder = json.JSONDecoder()
    idx = 0
    length = len(text)
    while idx < length:
        if text[idx] not in "{[":
            idx += 1
            continue
        try:
            value, offset = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            idx += 1
            continue
        yield value
        idx += offset


def _collect_artifacts_from_json_value(
    value: object,
    artifacts: list[CodexArtifact],
    seen: dict[str, int],
    *,
    source: str,
    label: str | None = None,
) -> None:
    if isinstance(value, dict):
        primary_image_path = value.get("primary_image_path")
        if primary_image_path is not None:
            _add_artifact_candidate(
                artifacts,
                seen,
                path=str(primary_image_path),
                source=f"{source}.primary_image_path",
                priority=1,
                label="primary_image_path",
            )

        image_paths = value.get("image_paths")
        if isinstance(image_paths, list):
            normalized_paths = [path for path in image_paths if isinstance(path, str)]
            last_index = len(normalized_paths) - 1
            for index, path in enumerate(normalized_paths):
                _add_artifact_candidate(
                    artifacts,
                    seen,
                    path=path,
                    source=f"{source}.image_paths",
                    priority=2 if index == last_index else 3,
                    label="image_paths",
                )

        for key, nested in value.items():
            if key in {"primary_image_path", "image_paths"}:
                continue
            _collect_artifacts_from_json_value(
                nested,
                artifacts,
                seen,
                source=source,
                label=key,
            )
        return

    if isinstance(value, list):
        for nested in value:
            _collect_artifacts_from_json_value(
                nested,
                artifacts,
                seen,
                source=source,
                label=label,
            )
        return

    if isinstance(value, str):
        normalized = _normalize_artifact_path(value)
        if normalized is not None:
            _add_artifact_candidate(
                artifacts,
                seen,
                path=normalized,
                source=f"{source}.value",
                priority=3,
                label=label,
            )
            return

        for path in _extract_existing_paths_from_text(value):
            _add_artifact_candidate(
                artifacts,
                seen,
                path=path,
                source=f"{source}.text",
                priority=3,
                label=label,
            )


def _extract_artifacts_from_json_lines(lines: Iterable[str]) -> tuple[CodexArtifact, ...]:
    artifacts: list[CodexArtifact] = []
    seen: dict[str, int] = {}

    for item in _iter_response_items(lines):
        item_type = item.get("type")
        if item_type == "function_call_output":
            output = item.get("output")
            if isinstance(output, str):
                for value in _iter_embedded_json_values(output):
                    _collect_artifacts_from_json_value(
                        value,
                        artifacts,
                        seen,
                        source="function_call_output",
                    )
                for path in _extract_existing_paths_from_text(output):
                    _add_artifact_candidate(
                        artifacts,
                        seen,
                        path=path,
                        source="function_call_output.text",
                        priority=3,
                        label="output",
                    )
            continue

        message_text = _extract_output_text_from_message_item(item)
        if not message_text:
            continue
        for path in _extract_existing_paths_from_text(message_text):
            _add_artifact_candidate(
                artifacts,
                seen,
                path=path,
                source="assistant_message.text",
                priority=4,
                label="assistant_message",
            )

    return tuple(sorted(artifacts, key=lambda artifact: artifact.priority))


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _looks_like_image_artifact(path: str) -> bool:
    return Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _extract_shell_command_from_item(item: dict[str, object]) -> str | None:
    if item.get("type") != "function_call" or item.get("name") != "shell_command":
        return None

    arguments = item.get("arguments")
    if not isinstance(arguments, str) or not arguments.strip():
        return None

    try:
        payload = json.loads(arguments)
    except json.JSONDecodeError:
        return None

    command = payload.get("command")
    if isinstance(command, str) and command.strip():
        return command.strip()
    return None


def _extract_generate_script_prompt_bundle_from_flags(command: str) -> StablePromptBundle | None:
    if "generate_auto_image.py" not in command:
        return None

    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        return None

    def _find_flag_value(flag: str) -> str | None:
        for index, token in enumerate(tokens[:-1]):
            if token == flag:
                candidate = _strip_matching_quotes(tokens[index + 1].strip())
                return candidate
        return None

    main_prompt = _find_flag_value("--main-prompt")
    face_prompt = _find_flag_value("--face-prompt")
    negative_prompt = _find_flag_value("--negative-prompt")
    face_negative_prompt = _find_flag_value("--face-negative-prompt")
    if not all([main_prompt, face_prompt, negative_prompt, face_negative_prompt]):
        return None

    return StablePromptBundle(
        main_prompt=main_prompt,
        face_prompt=face_prompt,
        negative_prompt=negative_prompt,
        face_negative_prompt=face_negative_prompt,
        source="codex_auto_image",
    )


def _extract_inline_python_code(command: str) -> str | None:
    here_string_match = re.search(r"@'\r?\n(?P<code>[\s\S]*?)\r?\n'@\s*\|\s*python\b", command)
    if here_string_match:
        return here_string_match.group("code")
    return None


def _evaluate_prompt_expr(node: ast.AST, values: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return values.get(node.id)
    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "strip"
            and not node.args
            and not node.keywords
        ):
            base_value = _evaluate_prompt_expr(node.func.value, values)
            return base_value.strip() if base_value is not None else None
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "dedent"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "textwrap"
            and len(node.args) == 1
            and not node.keywords
        ):
            base_value = _evaluate_prompt_expr(node.args[0], values)
            return textwrap.dedent(base_value) if base_value is not None else None
    return None


def _extract_generate_script_prompt_bundle_from_inline_python(command: str) -> StablePromptBundle | None:
    if "generate_auto_image.py" not in command:
        return None

    code = _extract_inline_python_code(command)
    if not code:
        return None

    try:
        module = ast.parse(code)
    except SyntaxError:
        return None

    values: dict[str, str] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        evaluated = _evaluate_prompt_expr(node.value, values)
        if evaluated is not None:
            values[target.id] = evaluated

    main_prompt = values.get("main_prompt")
    face_prompt = values.get("face_prompt")
    negative_prompt = values.get("neg")
    face_negative_prompt = values.get("face_neg")
    if not all([main_prompt, face_prompt, negative_prompt, face_negative_prompt]):
        return None

    return StablePromptBundle(
        main_prompt=main_prompt,
        face_prompt=face_prompt,
        negative_prompt=negative_prompt,
        face_negative_prompt=face_negative_prompt,
        source="codex_auto_image",
    )


def _extract_prompt_bundle_from_command(command: str) -> StablePromptBundle | None:
    return (
        _extract_generate_script_prompt_bundle_from_flags(command)
        or _extract_generate_script_prompt_bundle_from_inline_python(command)
    )


def _extract_prompt_bundle_from_json_lines(
    lines: Iterable[str],
    artifacts: tuple[CodexArtifact, ...],
) -> StablePromptBundle | None:
    if not any(_looks_like_image_artifact(artifact.path) for artifact in artifacts):
        return None

    last_bundle: StablePromptBundle | None = None
    for item in _iter_response_items(lines):
        command = _extract_shell_command_from_item(item)
        if not command:
            continue
        bundle = _extract_prompt_bundle_from_command(command)
        if bundle is not None:
            last_bundle = bundle
    return last_bundle


def _parse_mode_from_args(args: tuple[str, ...]) -> CommandMode:
    return "json" if "--json" in args else "output_file"


def _has_output_file_arg(args: list[str]) -> bool:
    return "-o" in args or "--output-last-message" in args


def _spec_requests_danger_full_access(args: tuple[str, ...]) -> bool:
    if "--dangerously-bypass-approvals-and-sandbox" in args:
        return True

    for index, arg in enumerate(args[:-1]):
        if arg == "--sandbox" and args[index + 1] == "danger-full-access":
            return True

    return False


def _spec_requests_workspace_write(args: tuple[str, ...]) -> bool:
    if "--full-auto" in args:
        return True

    for index, arg in enumerate(args[:-1]):
        if arg == "--sandbox" and args[index + 1] == "workspace-write":
            return True

    return False


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
    filtered_args = list(_strip_unsupported_resume_args(resume_args))

    if _spec_requests_danger_full_access(spec.args):
        if "--dangerously-bypass-approvals-and-sandbox" not in filtered_args:
            filtered_args.append("--dangerously-bypass-approvals-and-sandbox")
    elif _spec_requests_workspace_write(spec.args):
        if "--full-auto" not in filtered_args:
            filtered_args.append("--full-auto")

    return CodexCommandSpec(
        args=tuple(filtered_args),
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
        sandbox_policy: str | None = None
        artifacts: tuple[CodexArtifact, ...] = ()
        prompt_bundle: StablePromptBundle | None = None
        if spec.mode == "json":
            lines = stdout.splitlines()
            text = _extract_text_from_json_lines(lines).strip()
            usage = _extract_usage_from_json_lines(lines)
            parsed_session_id = _extract_session_id_from_json_lines(lines)
            sandbox_policy = _extract_sandbox_policy_from_json_lines(lines)
            artifacts = _extract_artifacts_from_json_lines(lines)
            prompt_bundle = _extract_prompt_bundle_from_json_lines(lines, artifacts)
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
            sandbox_policy=sandbox_policy,
            artifacts=artifacts,
            prompt_bundle=prompt_bundle,
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

    def prefers_danger_full_access(self) -> bool:
        reference_spec = self._active_spec or (self._candidates[0] if self._candidates else None)
        if reference_spec is None:
            return False
        return _spec_requests_danger_full_access(reference_spec.args)
