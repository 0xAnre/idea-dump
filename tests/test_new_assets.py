import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("OPENROUTER_MODEL", "test-model")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class NewTopLevelAssetsTests(unittest.TestCase):
    def test_new_image_is_stored_under_top_level_assets(self) -> None:
        self.assertEqual(
            main.ASSETS_DIR,
            main.BASE_DIR / "knowledge-base" / "assets",
        )
        dest = main.media_dest("005", "image")
        self.assertEqual(dest, main.ASSETS_DIR / "005-image")
        self.assertEqual(dest.parent.name, "assets")
        self.assertEqual(dest.parent.parent.name, "knowledge-base")
        self.assertNotEqual(dest.parent, main.IDEAS_DIR / "assets")

    def test_new_video_is_stored_under_top_level_assets(self) -> None:
        dest = main.media_dest("006", "video")
        self.assertEqual(dest, main.ASSETS_DIR / "006-video")
        self.assertNotEqual(dest.parent, main.IDEAS_DIR / "assets")

    def test_new_image_markdown_uses_parent_assets(self) -> None:
        self.assertEqual(main.media_ref("005-image.jpg"), "../assets/005-image.jpg")
        body = main.idea_markdown(
            "Borek",
            "This is what börek should be like.",
            image_ref=main.media_ref("005-image.jpg"),
        )
        self.assertIn("![](../assets/005-image.jpg)", body)
        self.assertNotIn("](assets/", body)

    def test_new_video_markdown_uses_parent_assets(self) -> None:
        self.assertEqual(main.media_ref("006-video.mp4"), "../assets/006-video.mp4")
        body = main.idea_markdown(
            "Lifeguard in Da Nang",
            "There is a lifeguard in Da Nang.",
            video_ref=main.media_ref("006-video.mp4"),
        )
        self.assertIn("[Video](../assets/006-video.mp4)", body)
        self.assertNotIn("](assets/", body)

    def test_old_ideas_assets_files_are_not_touched(self) -> None:
        root = Path(tempfile.mkdtemp())
        ideas = root / "ideas"
        assets = root / "assets"
        legacy = ideas / "assets"
        ideas.mkdir()
        assets.mkdir()
        legacy.mkdir()
        old = legacy / "003-image.jpg"
        old.write_bytes(b"legacy-bytes")
        original_ideas = main.IDEAS_DIR
        original_assets = main.ASSETS_DIR
        main.IDEAS_DIR = ideas
        main.ASSETS_DIR = assets
        try:
            dest = main.media_dest("005", "image").with_suffix(".jpg")
            dest.write_bytes(b"new-bytes")
            path = main.write_idea_file(
                "005",
                "New Image Idea",
                "A new idea with an image.",
                image_ref=main.media_ref(dest.name),
            )
            self.assertEqual(old.read_bytes(), b"legacy-bytes")
            self.assertTrue(old.exists())
            self.assertEqual(dest.read_bytes(), b"new-bytes")
            text = path.read_text(encoding="utf-8")
            self.assertIn("![](../assets/005-image.jpg)", text)
            self.assertNotIn("assets/003-image.jpg", text)
            self.assertEqual(list(legacy.iterdir()), [old])
        finally:
            main.IDEAS_DIR = original_ideas
            main.ASSETS_DIR = original_assets

    def test_canonical_idea_behavior_remains_intact(self) -> None:
        path = Path(tempfile.mkdtemp())
        original_ideas = main.IDEAS_DIR
        main.IDEAS_DIR = path
        try:
            written = main.write_idea_file(
                "007",
                "No Need for Agents in Everything",
                "You don't need to use an agent for everything.",
                image_ref=main.media_ref("007-image.jpg"),
            )
            text = written.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# No Need for Agents in Everything\n"))
            self.assertIn("You don't need to use an agent for everything.", text)
            self.assertNotIn("## Original Message", text)
            self.assertEqual(written.name, "007-no-need-for-agents-in-everything.md")
            parsed = main.parse_idea_markdown(written.name, text)
            self.assertEqual(parsed["id"], "007")
            self.assertEqual(parsed["title"], "No Need for Agents in Everything")
            self.assertEqual(
                parsed["clean_text"],
                "You don't need to use an agent for everything.",
            )
        finally:
            main.IDEAS_DIR = original_ideas


if __name__ == "__main__":
    unittest.main()
