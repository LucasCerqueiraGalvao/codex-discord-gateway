from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
import re
import shlex
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

import discord

from .config import Settings


AGENT_SCRIPTS_ROOT = Path(r"C:\Users\lucas\Documents\Projects\agent_scripts")
MAX_FIND_RESULTS_DEFAULT = 20
MAX_FIND_RESULTS_LIMIT = 200
SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    description: str
    required_params: tuple[str, ...]
    optional_params: tuple[str, ...]
    example: str


@dataclass(frozen=True)
class ActionInvocation:
    name: str
    params: dict[str, str]
    raw: str
    explicit: bool


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    action: str
    status: str
    data: dict[str, Any]
    message: str


class ActionRegistry:
    def __init__(self, settings: Settings, logger: logging.Logger | None = None) -> None:
        self._settings = settings
        self._logger = logger or logging.getLogger(__name__)
        self._definitions: dict[str, ActionDefinition] = {
            "find_file": ActionDefinition(
                name="find_file",
                description="Procura arquivos por nome/padrao em uma raiz.",
                required_params=("name",),
                optional_params=("root", "max_results"),
                example='find_file name="README.md" root="C:/Users/lucas/Documents/Projects" max_results=10',
            ),
            "upload_file": ActionDefinition(
                name="upload_file",
                description="Envia um arquivo local para o canal do Discord.",
                required_params=("path",),
                optional_params=("caption",),
                example='upload_file path="C:/Users/lucas/Desktop/relatorio.pdf" caption="Relatorio"',
            ),
            "create_script": ActionDefinition(
                name="create_script",
                description=(
                    "Cria script em nova pasta dentro de "
                    "C:/Users/lucas/Documents/Projects/agent_scripts."
                ),
                required_params=("name",),
                optional_params=("language", "content", "filename"),
                example='create_script name="merge_excels" language="python"',
            ),
        }
        self._handlers: dict[str, Callable[[discord.Message, dict[str, str]], Awaitable[ActionResult]]] = {
            "find_file": self._run_find_file,
            "upload_file": self._run_upload_file,
            "create_script": self._run_create_script,
        }

    @property
    def definitions(self) -> list[ActionDefinition]:
        return [self._definitions[name] for name in sorted(self._definitions)]

    def build_actions_help_text(self) -> str:
        lines: list[str] = [
            "Acoes padronizadas registradas:",
        ]
        for definition in self.definitions:
            lines.append(f"- `{definition.name}`: {definition.description}")
            lines.append(
                f"  params obrigatorios: {', '.join(definition.required_params)} | opcionais: {', '.join(definition.optional_params)}"
            )
            lines.append(f"  exemplo: `{definition.example}`")
        lines.append("Tambem aceita `acao <nome> ...` para chamada explicita.")
        return "\n".join(lines)

    def parse_invocation(self, raw_text: str) -> ActionInvocation | None:
        raw = (raw_text or "").strip()
        if not raw:
            return None

        try:
            tokens = shlex.split(raw, posix=True)
        except ValueError:
            return None

        if not tokens:
            return None

        first = tokens[0].strip().lower()
        explicit = False
        action_name = ""
        params_tokens: list[str] = []

        if first in {"acao", "action", "!acao", "!action"}:
            explicit = True
            if len(tokens) >= 2:
                action_name = tokens[1].strip().lower()
                params_tokens = tokens[2:]
        else:
            action_name = first.lstrip("!")
            params_tokens = tokens[1:]

        if action_name not in self._definitions:
            if not explicit:
                return None
            return ActionInvocation(name=action_name, params=self._parse_params(params_tokens), raw=raw, explicit=True)

        return ActionInvocation(name=action_name, params=self._parse_params(params_tokens), raw=raw, explicit=explicit)

    async def execute(self, message: discord.Message, invocation: ActionInvocation) -> ActionResult:
        if not invocation.name:
            return ActionResult(
                ok=False,
                action="",
                status="invalid_action_name",
                data={"available_actions": sorted(self._definitions.keys())},
                message="Nome da acao ausente. Use: `acao <nome> ...`.",
            )

        handler = self._handlers.get(invocation.name)
        if handler is None:
            return ActionResult(
                ok=False,
                action=invocation.name,
                status="action_not_registered",
                data={"available_actions": sorted(self._definitions.keys())},
                message=f"Acao `{invocation.name}` ainda nao registrada.",
            )

        try:
            return await handler(message, dict(invocation.params))
        except Exception as exc:
            self._logger.exception("Standard action failed: %s", invocation.name)
            return ActionResult(
                ok=False,
                action=invocation.name,
                status="action_exception",
                data={"error": str(exc)},
                message=f"Falha na acao `{invocation.name}`: {exc}",
            )

    def _parse_params(self, tokens: list[str]) -> dict[str, str]:
        params: dict[str, str] = {}
        free_tokens: list[str] = []
        for token in tokens:
            if "=" in token:
                key, value = token.split("=", 1)
                key = key.strip().lower()
                if key:
                    params[key] = value.strip()
                    continue
            free_tokens.append(token)

        if free_tokens:
            params["_free"] = " ".join(free_tokens).strip()
        return params

    def _resolve_path(self, raw_path: str | None) -> Path:
        raw = (raw_path or "").strip()
        if not raw:
            if self._settings.codex_workdir:
                return Path(self._settings.codex_workdir).resolve()
            return Path.home().resolve()

        path = Path(raw).expanduser()
        if path.is_absolute():
            return path.resolve()
        if self._settings.codex_workdir:
            return (Path(self._settings.codex_workdir).resolve() / path).resolve()
        return path.resolve()

    def _safe_slug(self, value: str, fallback: str = "script") -> str:
        cleaned = SAFE_NAME_PATTERN.sub("_", value.strip().lower())
        cleaned = cleaned.strip("._-")
        return cleaned or fallback

    def _parse_max_results(self, params: dict[str, str]) -> tuple[int | None, str | None]:
        raw = (params.get("max_results") or "").strip()
        if not raw:
            return MAX_FIND_RESULTS_DEFAULT, None
        try:
            parsed = int(raw)
        except ValueError:
            return None, "max_results deve ser numero inteiro."
        if parsed < 1 or parsed > MAX_FIND_RESULTS_LIMIT:
            return None, f"max_results deve estar entre 1 e {MAX_FIND_RESULTS_LIMIT}."
        return parsed, None

    def _find_files_sync(self, name: str, root: Path, max_results: int) -> tuple[list[str], bool]:
        query = name.strip()
        root = root.resolve()
        if not root.exists():
            raise FileNotFoundError(f"raiz nao encontrada: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"raiz invalida (nao e pasta): {root}")

        query_lower = query.lower()
        use_glob = any(char in query for char in "*?[]")
        matches: list[str] = []
        truncated = False

        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                filename_lower = filename.lower()
                if use_glob:
                    matched = fnmatch.fnmatch(filename_lower, query_lower)
                else:
                    matched = query_lower in filename_lower
                if not matched:
                    continue

                full_path = Path(dirpath) / filename
                matches.append(str(full_path))
                if len(matches) >= max_results:
                    truncated = True
                    return matches, truncated

        return matches, truncated

    async def _run_find_file(self, _message: discord.Message, params: dict[str, str]) -> ActionResult:
        name = (
            params.get("name")
            or params.get("query")
            or params.get("pattern")
            or params.get("_free")
            or ""
        ).strip()
        if not name:
            return ActionResult(
                ok=False,
                action="find_file",
                status="invalid_params",
                data={"required_params": ["name"]},
                message="find_file requer `name` (ou `query`).",
            )

        max_results, max_error = self._parse_max_results(params)
        if max_error is not None or max_results is None:
            return ActionResult(
                ok=False,
                action="find_file",
                status="invalid_params",
                data={},
                message=max_error or "max_results invalido.",
            )

        root = self._resolve_path(params.get("root"))
        try:
            matches, truncated = await asyncio.to_thread(
                self._find_files_sync,
                name,
                root,
                max_results,
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="find_file",
                status="search_error",
                data={"query": name, "root": str(root), "error": str(exc)},
                message=f"Erro em find_file: {exc}",
            )

        status = "ok" if matches else "not_found"
        return ActionResult(
            ok=bool(matches),
            action="find_file",
            status=status,
            data={
                "query": name,
                "root": str(root),
                "count": len(matches),
                "max_results": max_results,
                "truncated": truncated,
                "matches": matches,
            },
            message=f"find_file retornou {len(matches)} resultado(s).",
        )

    async def _run_upload_file(self, message: discord.Message, params: dict[str, str]) -> ActionResult:
        raw_path = (params.get("path") or params.get("file") or params.get("_free") or "").strip()
        if not raw_path:
            return ActionResult(
                ok=False,
                action="upload_file",
                status="invalid_params",
                data={"required_params": ["path"]},
                message="upload_file requer `path`.",
            )

        path = self._resolve_path(raw_path)
        if not path.exists():
            return ActionResult(
                ok=False,
                action="upload_file",
                status="file_not_found",
                data={"path": str(path)},
                message=f"Arquivo nao encontrado: {path}",
            )
        if not path.is_file():
            return ActionResult(
                ok=False,
                action="upload_file",
                status="not_a_file",
                data={"path": str(path)},
                message=f"Caminho nao e arquivo: {path}",
            )

        size_bytes = path.stat().st_size
        max_bytes = self._settings.attachments_max_mb * 1024 * 1024
        if size_bytes > max_bytes:
            return ActionResult(
                ok=False,
                action="upload_file",
                status="file_too_large",
                data={
                    "path": str(path),
                    "size_bytes": size_bytes,
                    "max_bytes": max_bytes,
                },
                message=(
                    f"Arquivo excede limite ({size_bytes} bytes > {max_bytes} bytes). "
                    f"Atual: ATTACHMENTS_MAX_MB={self._settings.attachments_max_mb}"
                ),
            )

        caption = (params.get("caption") or "").strip()
        file_to_send = discord.File(str(path), filename=path.name)
        if caption:
            await message.channel.send(caption, file=file_to_send)
        else:
            await message.channel.send(file=file_to_send)

        return ActionResult(
            ok=True,
            action="upload_file",
            status="uploaded",
            data={
                "path": str(path),
                "file_name": path.name,
                "size_bytes": size_bytes,
                "channel_id": message.channel.id,
            },
            message=f"Arquivo enviado: {path.name}",
        )

    def _build_script_content(self, language: str, default_name: str) -> str:
        if language == "python":
            return (
                "def main() -> None:\n"
                '    print("TODO: implement")\n'
                "\n"
                'if __name__ == "__main__":\n'
                "    main()\n"
            )
        if language == "powershell":
            return 'Write-Host "TODO: implement"\n'
        if language == "batch":
            return "@echo off\r\necho TODO: implement\r\n"
        return f"# TODO: implement {default_name}\n"

    async def _run_create_script(self, _message: discord.Message, params: dict[str, str]) -> ActionResult:
        name = (
            params.get("name")
            or params.get("script_name")
            or params.get("title")
            or params.get("_free")
            or ""
        ).strip()
        if not name:
            return ActionResult(
                ok=False,
                action="create_script",
                status="invalid_params",
                data={"required_params": ["name"]},
                message="create_script requer `name`.",
            )

        language_raw = (params.get("language") or "python").strip().lower()
        language_map = {
            "py": "python",
            "python": "python",
            "ps1": "powershell",
            "powershell": "powershell",
            "bat": "batch",
            "batch": "batch",
        }
        language = language_map.get(language_raw)
        if language is None:
            return ActionResult(
                ok=False,
                action="create_script",
                status="invalid_params",
                data={"language": language_raw, "supported": sorted(language_map.keys())},
                message=f"Linguagem nao suportada: {language_raw}",
            )

        suffix_by_language = {
            "python": ".py",
            "powershell": ".ps1",
            "batch": ".bat",
        }
        suffix = suffix_by_language[language]

        script_slug = self._safe_slug(name, fallback="script")
        folder_base = AGENT_SCRIPTS_ROOT
        folder_base.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{timestamp}_{script_slug}"
        folder_path = folder_base / folder_name
        while folder_path.exists():
            folder_path = folder_base / f"{folder_name}_{uuid4().hex[:4]}"
        folder_path.mkdir(parents=True, exist_ok=False)

        filename_raw = (params.get("filename") or "").strip()
        if filename_raw:
            filename_stem = self._safe_slug(Path(filename_raw).stem, fallback=script_slug)
        else:
            filename_stem = script_slug
        script_path = folder_path / f"{filename_stem}{suffix}"

        content_raw = params.get("content")
        if content_raw:
            content = content_raw.replace("\\n", "\n")
        else:
            content = self._build_script_content(language, filename_stem)
        script_path.write_text(content, encoding="utf-8")

        return ActionResult(
            ok=True,
            action="create_script",
            status="created",
            data={
                "scripts_root": str(folder_base),
                "folder_path": str(folder_path),
                "script_path": str(script_path),
                "language": language,
                "size_bytes": script_path.stat().st_size,
            },
            message=f"Script criado em {script_path}",
        )


def render_action_result(result: ActionResult) -> str:
    payload = {
        "ok": result.ok,
        "action": result.action,
        "status": result.status,
        "data": result.data,
        "message": result.message,
    }
    return "Resultado da acao padronizada:\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
