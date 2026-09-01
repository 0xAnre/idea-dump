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


class CanonicalIdeaFormatTests(unittest.TestCase):
    def test_text_idea_title_and_clean_body_without_raw_telegram(self) -> None:
        raw = "illa her sey icin agent kullanmaya gerek yok"
        title = "No Need for Agents in Everything"
        clean = "You don't need to use an agent for everything."
        body = main.idea_markdown(title, clean)
        self.assertEqual(
            body,
            "# No Need for Agents in Everything\n\n"
            "You don't need to use an agent for everything.\n",
        )
        self.assertNotIn("## Original Message", body)
        self.assertNotIn(raw, body)
        self.assertNotIn("![](", body)
        self.assertNotIn("[Video](", body)

    def test_image_idea_uses_existing_assets_path(self) -> None:
        body = main.idea_markdown(
            "This Is How Börek Should Be",
            "This is what börek should be like.",
            image_ref="assets/003-image.jpg",
        )
        self.assertIn("![](assets/003-image.jpg)", body)
        self.assertNotIn("## Original Message", body)
        self.assertNotIn("../assets/", body)

    def test_video_idea_uses_existing_assets_path(self) -> None:
        body = main.idea_markdown(
            "Lifeguard in Da Nang",
            "There is a lifeguard in Da Nang.",
            video_ref="assets/004-video.mp4",
        )
        self.assertIn("[Video](assets/004-video.mp4)", body)
        self.assertNotIn("## Original Message", body)

    def test_filename_and_id_unchanged(self) -> None:
        self.assertEqual(
            main.title_slug("No Need for Agents in Everything"),
            "no-need-for-agents-in-everything",
        )
        td = Path(tempfile.mkdtemp())
        (td / "001-first-idea.md").write_text("x")
        (td / "002-second-idea.md").write_text("x")
        original_ideas = main.IDEAS_DIR
        main.IDEAS_DIR = td
        try:
            self.assertEqual(main.next_idea_id(), "003")
            path = main.write_idea_file(
                "003",
                "No Need for Agents in Everything",
                "You don't need to use an agent for everything.",
            )
            self.assertEqual(path.name, "003-no-need-for-agents-in-everything.md")
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("## Original Message", text)
        finally:
            main.IDEAS_DIR = original_ideas


if __name__ == "__main__":
    unittest.main()
