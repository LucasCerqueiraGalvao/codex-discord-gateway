from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import types
import unittest
from unittest.mock import patch

discord_stub = types.ModuleType("discord")
discord_stub.File = object
discord_stub.Message = object
sys.modules.setdefault("discord", discord_stub)

from src.actions import ActionRegistry
from src.config import Settings
from src.stable_state import StablePromptBundle, StableStateStore


class _FakeChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id


class _FakeMessage:
    def __init__(self, channel_id: int) -> None:
        self.channel = _FakeChannel(channel_id)


def _build_settings() -> Settings:
    return Settings(
        discord_token="token",
        allowed_user_id=1,
        allowed_channel_id=None,
        codex_cmd=None,
        codex_timeout_seconds=120,
        codex_workdir=None,
        agent_scripts_root=None,
        stable_auto_image_script_path=None,
        discord_chunk_size=1900,
        log_level="INFO",
        log_dir="logs",
        attachments_temp_dir="runtime/attachments",
        attachments_max_mb=20,
        attachments_keep_files=False,
        audio_transcription_enabled=False,
        audio_stt_model="small",
        audio_stt_language=None,
        audio_stt_device="cpu",
        audio_stt_compute_type="int8",
        audio_max_duration_seconds=60,
        audio_rate_limit_per_minute=4,
        audio_max_files_per_message=3,
        token_budget_total=None,
        message_budget_total=None,
        context_window_tokens=None,
    )


class ActionRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_invocation_preserves_stable_multiline_body(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            registry = ActionRegistry(
                settings=_build_settings(),
                stable_state_store=StableStateStore(Path(tmp_dir)),
            )

            invocation = registry.parse_invocation("!stable line one\n\nline two\nline three")

            self.assertIsNotNone(invocation)
            assert invocation is not None
            self.assertEqual(invocation.name, "stable")
            self.assertEqual(invocation.raw_body, "line one\n\nline two\nline three")
            self.assertEqual(invocation.params, {})

    async def test_stable_requires_saved_base_for_channel(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            registry = ActionRegistry(
                settings=_build_settings(),
                stable_state_store=StableStateStore(Path(tmp_dir)),
            )
            message = _FakeMessage(channel_id=42)
            invocation = registry.parse_invocation("!stable dramatic sunset")
            assert invocation is not None

            result = await registry.execute(message, invocation)

            self.assertFalse(result.ok)
            self.assertEqual(result.status, "stable_state_missing")

    async def test_stable_updates_only_main_prompt_and_saves_new_bundle(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            store = StableStateStore(Path(tmp_dir))
            store.set(
                42,
                StablePromptBundle(
                    main_prompt="old main",
                    face_prompt="face prompt",
                    negative_prompt="negative prompt",
                    face_negative_prompt="face negative",
                    source="codex_auto_image",
                    last_image_path=r"C:\tmp\before.png",
                ),
            )
            registry = ActionRegistry(
                settings=_build_settings(),
                stable_state_store=store,
            )
            message = _FakeMessage(channel_id=42)
            invocation = registry.parse_invocation("!stable line one\nline two")
            assert invocation is not None

            fake_image = Path(tmp_dir) / "image.png"
            fake_image.write_bytes(b"png")

            class _CompletedProcess:
                def __init__(self) -> None:
                    self.returncode = 0
                    self.stdout = json.dumps(
                        {
                            "prompt_id": "prompt-1",
                            "elapsed_seconds": 12.5,
                            "image_paths": [str(fake_image)],
                            "primary_image_path": str(fake_image),
                        }
                    )
                    self.stderr = ""

            registry._stable_auto_image_script_path = Path(tmp_dir) / "generate_auto_image.py"
            with patch("src.actions.PROJECT_ROOT", Path(tmp_dir)):
                Path(tmp_dir, "generate_auto_image.py").write_text("# stub\n", encoding="utf-8")
                with patch("src.actions.subprocess.run", return_value=_CompletedProcess()) as run_mock:
                    result = await registry.execute(message, invocation)

            self.assertTrue(result.ok)
            self.assertEqual(result.status, "generated")
            run_command = run_mock.call_args.args[0]
            self.assertEqual(run_command[3], "line one\nline two")
            loaded = store.get(42)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.main_prompt, "line one\nline two")
            self.assertEqual(loaded.face_prompt, "face prompt")
            self.assertEqual(loaded.negative_prompt, "negative prompt")
            self.assertEqual(loaded.face_negative_prompt, "face negative")
            self.assertEqual(loaded.source, "stable_action")
            self.assertEqual(loaded.last_image_path, str(fake_image.resolve()))


if __name__ == "__main__":
    unittest.main()
