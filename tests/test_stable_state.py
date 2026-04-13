from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.stable_state import StablePromptBundle, StableStateStore


class StableStateStoreTests(unittest.TestCase):
    def test_roundtrip_preserves_prompt_bundle_fields(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            store = StableStateStore(Path(tmp_dir))
            saved = store.set(
                123,
                StablePromptBundle(
                    main_prompt="main",
                    face_prompt="face",
                    negative_prompt="neg",
                    face_negative_prompt="face-neg",
                    source="codex_auto_image",
                    last_image_path=r"C:\tmp\image.png",
                ),
            )

            loaded = store.get(123)

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.main_prompt, "main")
            self.assertEqual(loaded.face_prompt, "face")
            self.assertEqual(loaded.negative_prompt, "neg")
            self.assertEqual(loaded.face_negative_prompt, "face-neg")
            self.assertEqual(loaded.source, "codex_auto_image")
            self.assertEqual(loaded.last_image_path, r"C:\tmp\image.png")
            self.assertEqual(loaded.updated_at, saved.updated_at)


if __name__ == "__main__":
    unittest.main()
