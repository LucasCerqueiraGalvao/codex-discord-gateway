from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

discord_stub = types.ModuleType("discord")
discord_stub.File = object
discord_stub.Message = object

discord_ext_stub = types.ModuleType("discord.ext")
commands_stub = types.ModuleType("discord.ext.commands")
commands_stub.Bot = object
commands_stub.Context = object
discord_ext_stub.commands = commands_stub

sys.modules.setdefault("discord", discord_stub)
sys.modules.setdefault("discord.ext", discord_ext_stub)
sys.modules.setdefault("discord.ext.commands", commands_stub)

from src.bot import _build_response_text, _select_upload_artifact, _send_discord_response
from src.codex_bridge import CodexArtifact, CodexResult
from src.stable_state import StablePromptBundle, StableStateStore
from src.bot import _prepare_codex_stable_bundle, _save_stable_state


class _FakeChannel:
    def __init__(self) -> None:
        self.send = AsyncMock()


class _FakeMessage:
    def __init__(self) -> None:
        self.channel = _FakeChannel()
        self.reply = AsyncMock()


class BotHelpersTests(unittest.TestCase):
    def test_select_upload_artifact_skips_invalid_candidates(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            valid_path = (tmp_path / "valid.txt").resolve()
            valid_path.write_text("ok", encoding="utf-8")

            too_large_path = (tmp_path / "large.bin").resolve()
            too_large_path.write_bytes(b"123456")

            artifacts = (
                CodexArtifact(
                    path=str((tmp_path / "missing.txt").resolve()),
                    source="function_call_output.primary_image_path",
                    priority=1,
                    label="primary_image_path",
                ),
                CodexArtifact(
                    path=str(too_large_path),
                    source="function_call_output.image_paths",
                    priority=2,
                    label="image_paths",
                ),
                CodexArtifact(
                    path=str(valid_path),
                    source="function_call_output.text",
                    priority=3,
                    label="output",
                ),
            )

            selected, diagnostics = _select_upload_artifact(artifacts, max_bytes=4)

            self.assertIsNotNone(selected)
            assert selected is not None
            self.assertEqual(selected.path, str(valid_path))
            self.assertEqual(
                [entry.get("reason") for entry in diagnostics if entry.get("status") == "discarded"],
                ["missing", "too_large"],
            )

    def test_build_response_text_uses_generated_file_caption_when_needed(self) -> None:
        artifact = CodexArtifact(
            path=r"C:\tmp\generated.png",
            source="function_call_output.primary_image_path",
            priority=1,
            label="primary_image_path",
        )

        text = _build_response_text("", artifact)

        self.assertEqual(text, "Arquivo gerado anexado automaticamente: generated.png")

    def test_prepare_codex_stable_bundle_carries_artifact_path(self) -> None:
        artifact = CodexArtifact(
            path=r"C:\tmp\generated.png",
            source="function_call_output.primary_image_path",
            priority=1,
            label="primary_image_path",
        )
        result = CodexResult(
            text="ok",
            stdout="",
            stderr="",
            return_code=0,
            command="codex exec",
            prompt_bundle=StablePromptBundle(
                main_prompt="main",
                face_prompt="face",
                negative_prompt="neg",
                face_negative_prompt="face-neg",
                source="codex_auto_image",
            ),
        )

        bundle = _prepare_codex_stable_bundle(result, artifact)

        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertEqual(bundle.last_image_path, artifact.path)
        self.assertEqual(bundle.source, "codex_auto_image")

    def test_save_stable_state_persists_bundle(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            store = StableStateStore(Path(tmp_dir))
            saved = _save_stable_state(
                store,
                77,
                StablePromptBundle(
                    main_prompt="main",
                    face_prompt="face",
                    negative_prompt="neg",
                    face_negative_prompt="face-neg",
                    source="codex_auto_image",
                    last_image_path=r"C:\tmp\generated.png",
                ),
            )

            loaded = store.get(77)

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.main_prompt, "main")
            self.assertEqual(loaded.last_image_path, r"C:\tmp\generated.png")
            self.assertEqual(loaded.updated_at, saved.updated_at)


class SendDiscordResponseTests(unittest.IsolatedAsyncioTestCase):
    @patch("src.bot.discord.File")
    async def test_send_discord_response_attaches_only_first_chunk(self, file_cls: unittest.mock.Mock) -> None:
        file_obj = object()
        file_cls.return_value = file_obj

        message = _FakeMessage()
        artifact_path = Path(r"C:\tmp\artifact.png")

        sent_chunks = await _send_discord_response(
            message,
            "primeiro chunk segundo chunk terceiro",
            14,
            artifact_path=artifact_path,
        )

        self.assertEqual(sent_chunks, 3)
        message.reply.assert_awaited_once()
        _, reply_kwargs = message.reply.await_args
        self.assertEqual(reply_kwargs["file"], file_obj)
        self.assertFalse(reply_kwargs["mention_author"])
        self.assertEqual(message.channel.send.await_count, 2)
        first_extra_args, first_extra_kwargs = message.channel.send.await_args_list[0]
        self.assertEqual(first_extra_args[0], "segundo chunk")
        self.assertEqual(first_extra_kwargs, {})


if __name__ == "__main__":
    unittest.main()
