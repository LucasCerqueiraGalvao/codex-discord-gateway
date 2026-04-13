from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.codex_bridge import (
    CodexArtifact,
    CodexBridge,
    CodexCommandSpec,
    _build_resume_spec,
    _extract_artifacts_from_json_lines,
    _extract_prompt_bundle_from_json_lines,
    _extract_sandbox_policy_from_json_lines,
)
from src.single_instance import SingleInstanceLock


class CodexBridgeTests(unittest.TestCase):
    def test_resume_spec_preserves_danger_full_access(self) -> None:
        spec = CodexCommandSpec(
            args=("codex", "exec", "--json", "--sandbox", "danger-full-access"),
            mode="json",
        )

        resume_spec = _build_resume_spec(spec)

        self.assertIsNotNone(resume_spec)
        assert resume_spec is not None
        self.assertNotIn("--sandbox", resume_spec.args)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", resume_spec.args)

    def test_resume_spec_preserves_workspace_write(self) -> None:
        spec = CodexCommandSpec(
            args=("codex", "exec", "--json", "--sandbox", "workspace-write"),
            mode="json",
        )

        resume_spec = _build_resume_spec(spec)

        self.assertIsNotNone(resume_spec)
        assert resume_spec is not None
        self.assertNotIn("--sandbox", resume_spec.args)
        self.assertIn("--full-auto", resume_spec.args)

    def test_extract_sandbox_policy_from_json_lines(self) -> None:
        lines = [
            '{"type":"turn_context","payload":{"sandbox_policy":{"type":"danger-full-access"}}}',
            '{"type":"turn_context","payload":{"sandbox_policy":{"type":"read-only"}}}',
        ]

        self.assertEqual(_extract_sandbox_policy_from_json_lines(lines), "read-only")

    def test_bridge_reports_danger_full_access_preference(self) -> None:
        bridge = CodexBridge(
            command_override="codex exec --json --sandbox danger-full-access",
            timeout_seconds=30,
        )

        self.assertTrue(bridge.prefers_danger_full_access())

    def test_extract_artifacts_from_function_call_output_json(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            primary = (tmp_path / "primary.png").resolve()
            secondary = (tmp_path / "secondary.png").resolve()
            primary.write_bytes(b"primary")
            secondary.write_bytes(b"secondary")

            output_payload = (
                "Exit code: 0\nOutput:\n"
                + json.dumps(
                    {
                        "image_paths": [str(primary), str(secondary)],
                        "primary_image_path": str(primary),
                    },
                    indent=2,
                )
            )
            lines = [
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "output": output_payload,
                        },
                    }
                )
            ]

            artifacts = _extract_artifacts_from_json_lines(lines)

            self.assertEqual(
                artifacts,
                (
                    CodexArtifact(
                        path=str(primary),
                        source="function_call_output.primary_image_path",
                        priority=1,
                        label="primary_image_path",
                    ),
                    CodexArtifact(
                        path=str(secondary),
                        source="function_call_output.image_paths",
                        priority=2,
                        label="image_paths",
                    ),
                ),
            )

    def test_extract_artifacts_from_textual_tool_output(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            artifact_path = (tmp_path / "report.txt").resolve()
            artifact_path.write_text("ok", encoding="utf-8")

            lines = [
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "output": f"Arquivo salvo em {artifact_path} com sucesso",
                        },
                    }
                )
            ]

            artifacts = _extract_artifacts_from_json_lines(lines)

            self.assertEqual(len(artifacts), 1)
            self.assertEqual(artifacts[0].path, str(artifact_path))
            self.assertEqual(artifacts[0].source, "function_call_output.text")
            self.assertEqual(artifacts[0].priority, 3)

    def test_extract_artifacts_from_assistant_markdown_link_with_encoded_spaces(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            spaced_dir = tmp_path / "stable diffusion"
            spaced_dir.mkdir()
            artifact_path = (spaced_dir / "image final.png").resolve()
            artifact_path.write_bytes(b"png")

            encoded_path = str(artifact_path).replace("\\", "/").replace(" ", "%20")
            lines = [
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": f"Arquivo: [image]({encoded_path})",
                                }
                            ],
                        },
                    }
                )
            ]

            artifacts = _extract_artifacts_from_json_lines(lines)

            self.assertEqual(len(artifacts), 1)
            self.assertEqual(artifacts[0].path, str(artifact_path))
            self.assertEqual(artifacts[0].source, "assistant_message.text")
            self.assertEqual(artifacts[0].priority, 4)

    def test_extract_prompt_bundle_from_direct_generate_script_command(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            image_path = (Path(tmp_dir) / "image.png").resolve()
            image_path.write_bytes(b"png")
            lines = [
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "shell_command",
                            "arguments": json.dumps(
                                {
                                    "command": (
                                        'python "C:\\Users\\lucas\\Documents\\Projects\\personal\\stable diffusion'
                                        '\\generate_auto_image.py" --main-prompt "hero skyline" '
                                        '--face-prompt "sharp face" --negative-prompt "bad hands" '
                                        '--face-negative-prompt "bad face" --json'
                                    )
                                }
                            ),
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "output": json.dumps(
                                {
                                    "image_paths": [str(image_path)],
                                    "primary_image_path": str(image_path),
                                }
                            ),
                        },
                    }
                ),
            ]

            artifacts = _extract_artifacts_from_json_lines(lines)
            bundle = _extract_prompt_bundle_from_json_lines(lines, artifacts)

            self.assertIsNotNone(bundle)
            assert bundle is not None
            self.assertEqual(bundle.main_prompt, "hero skyline")
            self.assertEqual(bundle.face_prompt, "sharp face")
            self.assertEqual(bundle.negative_prompt, "bad hands")
            self.assertEqual(bundle.face_negative_prompt, "bad face")
            self.assertEqual(bundle.source, "codex_auto_image")

    def test_extract_prompt_bundle_from_inline_python_wrapper(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            image_path = (Path(tmp_dir) / "image.png").resolve()
            image_path.write_bytes(b"png")
            command = (
                "@'\n"
                "import subprocess, textwrap\n"
                "main_prompt = textwrap.dedent('''\nhero skyline\n''').strip()\n"
                "face_prompt = 'sharp face'\n"
                "neg = 'bad hands'\n"
                "face_neg = 'bad face'\n"
                "subprocess.run(['python', r'C:\\Users\\lucas\\Documents\\Projects\\personal\\stable diffusion\\generate_auto_image.py'])\n"
                "'@ | python -"
            )
            lines = [
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "shell_command",
                            "arguments": json.dumps({"command": command}),
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "output": json.dumps({"primary_image_path": str(image_path)}),
                        },
                    }
                ),
            ]

            artifacts = _extract_artifacts_from_json_lines(lines)
            bundle = _extract_prompt_bundle_from_json_lines(lines, artifacts)

            self.assertIsNotNone(bundle)
            assert bundle is not None
            self.assertEqual(bundle.main_prompt, "hero skyline")
            self.assertEqual(bundle.face_prompt, "sharp face")
            self.assertEqual(bundle.negative_prompt, "bad hands")
            self.assertEqual(bundle.face_negative_prompt, "bad face")

    def test_single_instance_lock_blocks_second_acquire(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            lock_path = Path(tmp_dir) / "gateway.lock"
            first = SingleInstanceLock(lock_path)
            second = SingleInstanceLock(lock_path)

            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())

            first.release()
            second.release()


if __name__ == "__main__":
    unittest.main()
