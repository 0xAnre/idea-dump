import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("OPENROUTER_MODEL", "test-model")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main

CREATED = datetime(2026, 9, 1, 12, 0)


class CanonicalIdeaFormatTests(unittest.TestCase):
    def test_text_idea_has_required_properties_and_source(self) -> None:
        raw = "illa her sey icin agent kullanmaya gerek yok"
        title = "No Need for Agents in Everything"
        clean = "You don't need to use an agent for everything."
        body = main.idea_markdown(
            title,
            clean,
            idea_id="002",
            original_text=raw,
            created=CREATED,
        )
        self.assertEqual(
            body,
            "---\n"
            'id: "002"\n'
            "title: No Need for Agents in Everything\n"
            "type: idea\n"
            "created: 2026-09-01\n"
            "source: telegram\n"
            "tags: []\n"
            "---\n"
            "# No Need for Agents in Everything\n\n"
            "You don't need to use an agent for everything.\n"
            "\n"
            "## Source\n\n"
            "> illa her sey icin agent kullanmaya gerek yok\n",
        )
        self.assertNotIn("## Original Message", body)
        self.assertNotIn("![](", body)
        self.assertNotIn("[Video](", body)

    def test_one_write_creates_one_markdown_file(self) -> None:
        td = Path(tempfile.mkdtemp())
        original_ideas = main.IDEAS_DIR
        main.IDEAS_DIR = td
        try:
            path = main.write_idea_file(
                "015",
                "Vietnam Enters Winter Season",
                "We are gradually entering the winter season in Vietnam.",
                original_text="vietnamda yavas yavas kis sezonuna giriyoruz",
                created=CREATED,
            )
            files = list(td.glob("*.md"))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0], path)
            self.assertEqual(path.name, "015-vietnam-enters-winter-season.md")
            self.assertFalse((td / "015-vietnam-enters-winter-season").is_dir())
        finally:
            main.IDEAS_DIR = original_ideas

    def test_zero_padded_id_and_capture_date(self) -> None:
        body = main.idea_markdown(
            "Start Command",
            "/start",
            idea_id="001",
            original_text="/start",
            created=CREATED,
        )
        self.assertIn('id: "001"', body)
        self.assertIn("created: 2026-09-01", body)
        self.assertIn("type: idea", body)
        self.assertIn("source: telegram", body)
        self.assertIn("tags: []", body)

    def test_turkish_source_preserved_verbatim(self) -> None:
        raw = "börek böyle olmalı"
        body = main.idea_markdown(
            "This Is How Börek Should Be",
            "This is what börek should be like.",
            idea_id="003",
            original_text=raw,
            created=CREATED,
        )
        self.assertEqual(main.recover_source_from_idea(body), raw)
        self.assertIn("> börek böyle olmalı", body)
        parsed = main.parse_idea_markdown("003-borek.md", body)
        self.assertEqual(parsed["clean_text"], "This is what börek should be like.")
        self.assertNotIn("börek böyle olmalı", parsed["clean_text"])

    def test_multiline_source_is_recoverable(self) -> None:
        raw = "line one\n\nline two\nline three\n"
        body = main.idea_markdown(
            "Multiline Source",
            "Line one. Line two. Line three.",
            idea_id="016",
            original_text=raw,
            created=CREATED,
        )
        self.assertEqual(main.recover_source_from_idea(body), raw)
        self.assertIn("> line one\n>\n> line two\n> line three\n>", body)

    def test_yaml_safe_title_with_colon(self) -> None:
        title = "Note: Agents Everywhere"
        body = main.idea_markdown(
            title,
            "You do not need an agent for everything.",
            idea_id="008",
            original_text="note: agents",
            created=CREATED,
        )
        self.assertIn('title: "Note: Agents Everywhere"', body)
        self.assertIn(f"# {title}\n", body)

    def test_image_idea_uses_top_level_assets_path(self) -> None:
        body = main.idea_markdown(
            "This Is How Börek Should Be",
            "This is what börek should be like.",
            image_ref="../assets/003-image.jpg",
            idea_id="003",
            original_text="börek böyle olmalı",
            created=CREATED,
        )
        self.assertIn("![](../assets/003-image.jpg)", body)
        self.assertNotIn("## Original Message", body)
        self.assertNotIn("](assets/", body)
        self.assertGreater(
            body.index("![](../assets/003-image.jpg)"),
            body.index("# This Is How Börek Should Be"),
        )
        self.assertGreater(body.index("## Source"), body.index("![]("))

    def test_video_idea_uses_top_level_assets_path(self) -> None:
        body = main.idea_markdown(
            "Lifeguard in Da Nang",
            "There is a lifeguard in Da Nang.",
            video_ref="../assets/004-video.mp4",
            idea_id="004",
            original_text="da nangda cankurtaran var",
            created=CREATED,
        )
        self.assertIn("[Video](../assets/004-video.mp4)", body)
        self.assertNotIn("## Original Message", body)
        self.assertNotIn("](assets/", body)
        self.assertGreater(body.index("## Source"), body.index("[Video]("))

    def test_parser_ignores_frontmatter_and_source(self) -> None:
        body = main.idea_markdown(
            "Vietnam Enters Winter Season",
            "We are gradually entering the winter season in Vietnam.",
            idea_id="015",
            original_text="vietnamda yavas yavas kis sezonuna giriyoruz",
            created=CREATED,
        )
        parsed = main.parse_idea_markdown(
            "015-vietnam-enters-winter-season.md",
            body,
        )
        self.assertEqual(parsed["id"], "015")
        self.assertEqual(parsed["title"], "Vietnam Enters Winter Season")
        self.assertEqual(
            parsed["clean_text"],
            "We are gradually entering the winter season in Vietnam.",
        )
        self.assertNotIn("type: idea", parsed["clean_text"])
        self.assertNotIn("telegram", parsed["clean_text"])
        self.assertNotIn("vietnamda", parsed["clean_text"])

    def test_parser_still_reads_v1_ideas(self) -> None:
        text = (
            "# Start Command\n\n"
            "/start\n\n"
            "## Original Message\n\n"
            "> /start\n"
        )
        parsed = main.parse_idea_markdown("001-start-command.md", text)
        self.assertEqual(parsed["id"], "001")
        self.assertEqual(parsed["title"], "Start Command")
        self.assertEqual(parsed["clean_text"], "/start")

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
                original_text="illa her sey icin agent kullanmaya gerek yok",
                created=CREATED,
            )
            self.assertEqual(path.name, "003-no-need-for-agents-in-everything.md")
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("## Original Message", text)
            self.assertIn("## Source", text)
        finally:
            main.IDEAS_DIR = original_ideas


if __name__ == "__main__":
    unittest.main()
