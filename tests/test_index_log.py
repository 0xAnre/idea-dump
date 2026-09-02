import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("OPENROUTER_MODEL", "test-model")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main

STAMP = datetime(2026, 9, 1, 4, 30)


def _empty_wiki() -> tuple[Path, Path, Path, Path]:
    root = Path(tempfile.mkdtemp())
    ideas = root / "ideas"
    topics = root / "topics"
    ideas.mkdir()
    topics.mkdir()
    index_path = root / "index.md"
    log_path = root / "log.md"
    log_path.write_text("# Log\n", encoding="utf-8")
    return ideas, topics, index_path, log_path


class IndexRebuildTests(unittest.TestCase):
    def test_empty_index(self) -> None:
        ideas, topics, index_path, _log = _empty_wiki()
        text = main.rebuild_index(
            ideas_dir=ideas,
            topics_dir=topics,
            index_path=index_path,
        )
        self.assertEqual(text, "# Idea Dump\n")
        self.assertEqual(index_path.read_text(encoding="utf-8"), "# Idea Dump\n")
        self.assertNotIn("## Topics", text)
        self.assertNotIn("## Ideas", text)

    def test_ideas_only_index(self) -> None:
        ideas, topics, index_path, _log = _empty_wiki()
        (ideas / "001-start-command.md").write_text(
            "# Start Command\n\n/start\n",
            encoding="utf-8",
        )
        text = main.rebuild_index(
            ideas_dir=ideas,
            topics_dir=topics,
            index_path=index_path,
        )
        self.assertEqual(
            text,
            "# Idea Dump\n\n"
            "## Ideas\n\n"
            "- 001 — [Start Command](ideas/001-start-command.md)\n",
        )
        self.assertNotIn("## Topics", text)

    def test_topics_only_index(self) -> None:
        ideas, topics, index_path, _log = _empty_wiki()
        (topics / "cooking.md").write_text("# Cooking\n\n## Ideas\n", encoding="utf-8")
        text = main.rebuild_index(
            ideas_dir=ideas,
            topics_dir=topics,
            index_path=index_path,
        )
        self.assertEqual(
            text,
            "# Idea Dump\n\n"
            "## Topics\n\n"
            "- [Cooking](topics/cooking.md)\n",
        )
        self.assertNotIn("## Ideas", text)

    def test_topics_and_ideas_index(self) -> None:
        ideas, topics, index_path, _log = _empty_wiki()
        (topics / "cooking.md").write_text("# Cooking\n", encoding="utf-8")
        (ideas / "001-start-command.md").write_text(
            "# Start Command\n\n/start\n",
            encoding="utf-8",
        )
        text = main.rebuild_index(
            ideas_dir=ideas,
            topics_dir=topics,
            index_path=index_path,
        )
        self.assertEqual(
            text,
            "# Idea Dump\n\n"
            "## Topics\n\n"
            "- [Cooking](topics/cooking.md)\n\n"
            "## Ideas\n\n"
            "- 001 — [Start Command](ideas/001-start-command.md)\n",
        )

    def test_topic_ordering(self) -> None:
        ideas, topics, index_path, _log = _empty_wiki()
        (topics / "zebra.md").write_text("# Zebra\n", encoding="utf-8")
        (topics / "apple.md").write_text("# apple\n", encoding="utf-8")
        (topics / "beta.md").write_text("# Apple\n", encoding="utf-8")
        text = main.rebuild_index(
            ideas_dir=ideas,
            topics_dir=topics,
            index_path=index_path,
        )
        titles = [
            line[line.index("[") + 1 : line.index("]")]
            for line in text.splitlines()
            if line.startswith("- [")
        ]
        self.assertEqual(titles, ["apple", "Apple", "Zebra"])
        self.assertLess(text.index("topics/apple.md"), text.index("topics/beta.md"))

    def test_idea_numeric_ordering(self) -> None:
        ideas, topics, index_path, _log = _empty_wiki()
        (ideas / "010-later.md").write_text("# Later\n\nx\n", encoding="utf-8")
        (ideas / "002-second.md").write_text("# Second\n\nx\n", encoding="utf-8")
        (ideas / "001-first.md").write_text("# First\n\nx\n", encoding="utf-8")
        text = main.rebuild_index(
            ideas_dir=ideas,
            topics_dir=topics,
            index_path=index_path,
        )
        self.assertLess(text.index("- 001 —"), text.index("- 002 —"))
        self.assertLess(text.index("- 002 —"), text.index("- 010 —"))

    def test_index_full_rebuild_removes_stale_entries(self) -> None:
        ideas, topics, index_path, _log = _empty_wiki()
        index_path.write_text(
            "# Idea Dump\n\n"
            "## Ideas\n\n"
            "- 999 — [Gone](ideas/999-gone.md)\n",
            encoding="utf-8",
        )
        (ideas / "001-start-command.md").write_text(
            "# Start Command\n\n/start\n",
            encoding="utf-8",
        )
        text = main.rebuild_index(
            ideas_dir=ideas,
            topics_dir=topics,
            index_path=index_path,
        )
        self.assertNotIn("999", text)
        self.assertNotIn("Gone", text)
        self.assertIn("001 — [Start Command](ideas/001-start-command.md)", text)


    def test_v2_frontmatter_ideas_index_by_h1_title(self) -> None:
        ideas, topics, index_path, _log = _empty_wiki()
        (ideas / "015-vietnam-enters-winter-season.md").write_text(
            main.idea_markdown(
                "Vietnam Enters Winter Season",
                "We are gradually entering the winter season in Vietnam.",
                idea_id="015",
                original_text="vietnamda yavas yavas kis sezonuna giriyoruz",
                created=datetime(2026, 9, 1),
            ),
            encoding="utf-8",
        )
        text = main.rebuild_index(
            ideas_dir=ideas,
            topics_dir=topics,
            index_path=index_path,
        )
        self.assertIn(
            "- 015 — [Vietnam Enters Winter Season]"
            "(ideas/015-vietnam-enters-winter-season.md)",
            text,
        )
        self.assertNotIn("vietnamda", text)


class WikiLogTests(unittest.TestCase):
    def test_one_log_line_per_idea(self) -> None:
        _ideas, _topics, _index, log_path = _empty_wiki()
        main.append_wiki_log(
            "001",
            "Start Command",
            log_path=log_path,
            now=STAMP,
        )
        main.append_wiki_log(
            "002",
            "Second Idea",
            log_path=log_path,
            now=datetime(2026, 9, 1, 4, 31),
        )
        text = log_path.read_text(encoding="utf-8")
        self.assertEqual(
            text,
            "# Log\n"
            "- 2026-09-01 04:30 — Added 001 — Start Command\n"
            "- 2026-09-01 04:31 — Added 002 — Second Idea\n",
        )
        self.assertEqual(text.count("— Added "), 2)

    def test_created_topic_names_appear_on_the_same_log_line(self) -> None:
        ideas, topics, index_path, log_path = _empty_wiki()
        (ideas / "005-agents.md").write_text("# Agents\n\nbody\n", encoding="utf-8")
        main.after_capture_index_and_log(
            "005",
            "No Need for Agents in Everything",
            {
                "use_topic_slugs": [],
                "create_topics": [
                    {"title": "Agents", "slug": "agents"},
                    {"title": "Da Nang", "slug": "da-nang"},
                ],
                "related_idea_ids": [],
            },
            ideas_dir=ideas,
            topics_dir=topics,
            index_path=index_path,
            log_path=log_path,
            now=STAMP,
        )
        text = log_path.read_text(encoding="utf-8")
        self.assertEqual(text.count("\n- "), 1)
        self.assertIn(
            "- 2026-09-01 04:30 — Added 005 — No Need for Agents in Everything"
            "; created topic Agents, Da Nang\n",
            text,
        )

    def test_existing_topic_attachment_does_not_add_extra_log_detail(self) -> None:
        ideas, topics, index_path, log_path = _empty_wiki()
        (topics / "cooking.md").write_text("# Cooking\n", encoding="utf-8")
        (ideas / "003-borek.md").write_text("# Borek\n\nbody\n", encoding="utf-8")
        main.after_capture_index_and_log(
            "003",
            "This Is How Börek Should Be",
            {
                "use_topic_slugs": ["cooking"],
                "create_topics": [],
                "related_idea_ids": [],
            },
            ideas_dir=ideas,
            topics_dir=topics,
            index_path=index_path,
            log_path=log_path,
            now=STAMP,
        )
        text = log_path.read_text(encoding="utf-8")
        self.assertEqual(
            text,
            "# Log\n"
            "- 2026-09-01 04:30 — Added 003 — This Is How Börek Should Be\n",
        )
        self.assertNotIn("created topic", text)
        self.assertNotIn("cooking", text)


class CaptureFinalizeSafetyTests(unittest.TestCase):
    def test_maintainer_failure_still_indexes_and_logs_captured_idea(self) -> None:
        ideas, topics, index_path, log_path = _empty_wiki()
        (ideas / "003-no-need-for-agents-in-everything.md").write_text(
            "# No Need for Agents in Everything\n\n"
            "You don't need to use an agent for everything.\n",
            encoding="utf-8",
        )
        main.after_capture_index_and_log(
            "003",
            "No Need for Agents in Everything",
            None,
            ideas_dir=ideas,
            topics_dir=topics,
            index_path=index_path,
            log_path=log_path,
            now=STAMP,
        )
        index = index_path.read_text(encoding="utf-8")
        log = log_path.read_text(encoding="utf-8")
        self.assertIn(
            "- 003 — [No Need for Agents in Everything]"
            "(ideas/003-no-need-for-agents-in-everything.md)",
            index,
        )
        self.assertNotIn("## Topics", index)
        self.assertEqual(
            log,
            "# Log\n"
            "- 2026-09-01 04:30 — Added 003 — No Need for Agents in Everything\n",
        )
        self.assertNotIn("created topic", log)

    def test_index_log_failure_does_not_destroy_canonical_idea_or_relationships(
        self,
    ) -> None:
        ideas, topics, index_path, log_path = _empty_wiki()
        new_path = ideas / "003-no-need-for-agents-in-everything.md"
        idea_body = (
            "# No Need for Agents in Everything\n\n"
            "You don't need to use an agent for everything.\n"
        )
        new_path.write_text(idea_body, encoding="utf-8")
        (ideas / "001-start-command.md").write_text(
            "# Start Command\n\n/start\n",
            encoding="utf-8",
        )
        main.apply_maintainer_decision(
            {
                "use_topic_slugs": [],
                "create_topics": [{"title": "Agents", "slug": "agents"}],
                "related_idea_ids": ["001"],
            },
            "003",
            "No Need for Agents in Everything",
            "003-no-need-for-agents-in-everything.md",
            ideas_dir=ideas,
            topics_dir=topics,
        )
        topic_before = (topics / "agents.md").read_text(encoding="utf-8")
        idea_before = new_path.read_text(encoding="utf-8")
        related_before = (ideas / "001-start-command.md").read_text(encoding="utf-8")
        with patch.object(main, "rebuild_index", side_effect=OSError("disk full")):
            main.try_after_capture_index_and_log(
                "003",
                "No Need for Agents in Everything",
                {
                    "use_topic_slugs": [],
                    "create_topics": [{"title": "Agents", "slug": "agents"}],
                    "related_idea_ids": ["001"],
                },
                ideas_dir=ideas,
                topics_dir=topics,
                index_path=index_path,
                log_path=log_path,
                now=STAMP,
            )
        self.assertEqual(new_path.read_text(encoding="utf-8"), idea_before)
        self.assertEqual((topics / "agents.md").read_text(encoding="utf-8"), topic_before)
        self.assertEqual(
            (ideas / "001-start-command.md").read_text(encoding="utf-8"),
            related_before,
        )
        self.assertIn("## Related Ideas", idea_before)
        self.assertIn("## Ideas", topic_before)


if __name__ == "__main__":
    unittest.main()
