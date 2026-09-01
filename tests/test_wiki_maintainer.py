import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("OPENROUTER_MODEL", "test-model")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


SCHEMA_TEXT = "# Idea Dump wiki schema\n\nTopics organize Ideas.\n"


def _wiki() -> tuple[Path, Path, Path]:
    root = Path(tempfile.mkdtemp())
    ideas = root / "ideas"
    topics = root / "topics"
    ideas.mkdir()
    topics.mkdir()
    schema = root / "schema.md"
    schema.write_text(SCHEMA_TEXT, encoding="utf-8")
    (ideas / "001-start-command.md").write_text(
        "# Start Command\n\n"
        "/start\n\n"
        "## Original Message\n\n"
        "> /start\n",
        encoding="utf-8",
    )
    (ideas / "002-borek.md").write_text(
        "# This Is How Börek Should Be\n\n"
        "This is what börek should be like.\n\n"
        "## Original Message\n\n"
        "> börek böyle olmalı\n\n"
        "![](assets/002-image.jpg)\n",
        encoding="utf-8",
    )
    (topics / "cooking.md").write_text(
        "# Cooking\n\n"
        "## Ideas\n\n"
        "- [This Is How Börek Should Be](../ideas/002-borek.md)\n",
        encoding="utf-8",
    )
    return ideas, topics, schema


def _new_idea() -> dict:
    return {
        "id": "003",
        "title": "No Need for Agents in Everything",
        "clean_text": "You don't need to use an agent for everything.",
        "filename": "003-no-need-for-agents-in-everything.md",
    }


def _context() -> dict:
    ideas, topics, schema = _wiki()
    new = _new_idea()
    (ideas / new["filename"]).write_text(
        f"# {new['title']}\n\n{new['clean_text']}\n",
        encoding="utf-8",
    )
    return main.build_maintainer_context(
        new["id"],
        new["title"],
        new["clean_text"],
        new["filename"],
        ideas_dir=ideas,
        topics_dir=topics,
        schema_path=schema,
    )


class WikiMaintainerContextTests(unittest.TestCase):
    def test_context_excludes_the_new_idea_from_existing_ideas(self) -> None:
        context = _context()
        ids = [idea["id"] for idea in context["existing_ideas"]]
        self.assertEqual(ids, ["001", "002"])
        self.assertEqual(context["new_idea"]["id"], "003")
        self.assertEqual(
            context["new_idea"]["filename"],
            "003-no-need-for-agents-in-everything.md",
        )

    def test_context_does_not_contain_raw_telegram_input(self) -> None:
        context = _context()
        dumped = str(context)
        self.assertNotIn("börek böyle olmalı", dumped)
        self.assertNotIn("> /start", dumped)
        for idea in context["existing_ideas"]:
            self.assertNotIn("## Original Message", idea["clean_text"])
            self.assertNotIn("![](", idea["clean_text"])
        self.assertNotIn("index.md", dumped)
        self.assertNotIn("log.md", dumped)


class WikiMaintainerDecisionTests(unittest.TestCase):
    def test_valid_empty_decision(self) -> None:
        decision = main.parse_maintainer_decision(
            '{"use_topic_slugs":[],"create_topics":[],"related_idea_ids":[]}',
            _context(),
        )
        self.assertEqual(
            decision,
            {
                "use_topic_slugs": [],
                "create_topics": [],
                "related_idea_ids": [],
            },
        )

    def test_valid_existing_topic_selection(self) -> None:
        decision = main.parse_maintainer_decision(
            '{"use_topic_slugs":["cooking"],"create_topics":[],"related_idea_ids":[]}',
            _context(),
        )
        self.assertEqual(decision["use_topic_slugs"], ["cooking"])

    def test_valid_new_topic_creation(self) -> None:
        decision = main.parse_maintainer_decision(
            '{"use_topic_slugs":[],"create_topics":[{"title":"Agents","slug":"agents"}],"related_idea_ids":[]}',
            _context(),
        )
        self.assertEqual(
            decision["create_topics"],
            [{"title": "Agents", "slug": "agents"}],
        )

    def test_valid_related_idea_selection(self) -> None:
        decision = main.parse_maintainer_decision(
            '{"use_topic_slugs":[],"create_topics":[],"related_idea_ids":["001"]}',
            _context(),
        )
        self.assertEqual(decision["related_idea_ids"], ["001"])

    def test_reject_unknown_topic(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown Topic slug"):
            main.parse_maintainer_decision(
                '{"use_topic_slugs":["travel"],"create_topics":[],"related_idea_ids":[]}',
                _context(),
            )

    def test_reject_topic_collision(self) -> None:
        with self.assertRaisesRegex(ValueError, "Topic slug collision"):
            main.parse_maintainer_decision(
                '{"use_topic_slugs":[],"create_topics":[{"title":"Cooking","slug":"cooking"}],"related_idea_ids":[]}',
                _context(),
            )

    def test_reject_unknown_idea_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown Idea ID"):
            main.parse_maintainer_decision(
                '{"use_topic_slugs":[],"create_topics":[],"related_idea_ids":["999"]}',
                _context(),
            )

    def test_reject_self_link(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not include the new Idea"):
            main.parse_maintainer_decision(
                '{"use_topic_slugs":[],"create_topics":[],"related_idea_ids":["003"]}',
                _context(),
            )

    def test_malformed_empty_llm_response(self) -> None:
        context = _context()
        with self.assertRaisesRegex(ValueError, "empty"):
            main.parse_maintainer_decision("", context)
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            main.parse_maintainer_decision("{", context)


class WikiMaintainerFailureTests(unittest.TestCase):
    def test_maintainer_failure_preserves_canonical_idea(self) -> None:
        ideas, topics, schema = _wiki()
        new = _new_idea()
        path = ideas / new["filename"]
        body = f"# {new['title']}\n\n{new['clean_text']}\n"
        path.write_text(body, encoding="utf-8")
        original_ideas = main.IDEAS_DIR
        original_topics = main.TOPICS_DIR
        original_schema = main.SCHEMA_PATH
        main.IDEAS_DIR = ideas
        main.TOPICS_DIR = topics
        main.SCHEMA_PATH = schema
        try:
            with patch.object(
                main,
                "maintainer_with_openrouter",
                AsyncMock(side_effect=ValueError("OpenRouter response empty")),
            ):
                result = asyncio.run(
                    main.run_wiki_maintainer(
                        new["id"],
                        new["title"],
                        new["clean_text"],
                        new["filename"],
                    )
                )
            self.assertIsNone(result)
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), body)
        finally:
            main.IDEAS_DIR = original_ideas
            main.TOPICS_DIR = original_topics
            main.SCHEMA_PATH = original_schema


class WikiMaintainerApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ideas, self.topics, self.schema = _wiki()
        self.new = _new_idea()
        self.new_path = self.ideas / self.new["filename"]
        self.new_path.write_text(
            f"# {self.new['title']}\n\n{self.new['clean_text']}\n\n"
            "![](assets/003-image.jpg)\n",
            encoding="utf-8",
        )

    def _apply(self, decision: dict) -> None:
        main.apply_maintainer_decision(
            decision,
            self.new["id"],
            self.new["title"],
            self.new["filename"],
            ideas_dir=self.ideas,
            topics_dir=self.topics,
        )

    def test_create_a_new_topic_page(self) -> None:
        self._apply(
            {
                "use_topic_slugs": [],
                "create_topics": [{"title": "Agents", "slug": "agents"}],
                "related_idea_ids": [],
            }
        )
        path = self.topics / "agents.md"
        self.assertTrue(path.exists())
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            "# Agents\n\n"
            "## Ideas\n\n"
            "- [No Need for Agents in Everything]"
            "(../ideas/003-no-need-for-agents-in-everything.md)\n",
        )

    def test_update_an_existing_topic(self) -> None:
        self._apply(
            {
                "use_topic_slugs": ["cooking"],
                "create_topics": [],
                "related_idea_ids": [],
            }
        )
        text = (self.topics / "cooking.md").read_text(encoding="utf-8")
        self.assertIn("- [This Is How Börek Should Be](../ideas/002-borek.md)", text)
        self.assertIn(
            "- [No Need for Agents in Everything]"
            "(../ideas/003-no-need-for-agents-in-everything.md)",
            text,
        )

    def test_new_idea_receives_topic_link(self) -> None:
        self._apply(
            {
                "use_topic_slugs": ["cooking"],
                "create_topics": [{"title": "Agents", "slug": "agents"}],
                "related_idea_ids": [],
            }
        )
        text = self.new_path.read_text(encoding="utf-8")
        self.assertIn("## Topics", text)
        self.assertIn("- [Cooking](../topics/cooking.md)", text)
        self.assertIn("- [Agents](../topics/agents.md)", text)

    def test_new_idea_receives_related_ideas_link(self) -> None:
        self._apply(
            {
                "use_topic_slugs": [],
                "create_topics": [],
                "related_idea_ids": ["001"],
            }
        )
        text = self.new_path.read_text(encoding="utf-8")
        self.assertIn("## Related Ideas", text)
        self.assertIn("- [Start Command](001-start-command.md)", text)

    def test_reciprocal_related_ideas_link_is_added(self) -> None:
        self._apply(
            {
                "use_topic_slugs": [],
                "create_topics": [],
                "related_idea_ids": ["001"],
            }
        )
        text = (self.ideas / "001-start-command.md").read_text(encoding="utf-8")
        self.assertIn("## Related Ideas", text)
        self.assertIn(
            "- [No Need for Agents in Everything]"
            "(003-no-need-for-agents-in-everything.md)",
            text,
        )
        self.assertIn("## Original Message", text)
        self.assertIn("> /start", text)

    def test_duplicate_links_are_not_created(self) -> None:
        decision = {
            "use_topic_slugs": ["cooking"],
            "create_topics": [{"title": "Agents", "slug": "agents"}],
            "related_idea_ids": ["001"],
        }
        self._apply(decision)
        self._apply(decision)
        cooking = (self.topics / "cooking.md").read_text(encoding="utf-8")
        agents = (self.topics / "agents.md").read_text(encoding="utf-8")
        new_text = self.new_path.read_text(encoding="utf-8")
        related = (self.ideas / "001-start-command.md").read_text(encoding="utf-8")
        self.assertEqual(
            cooking.count("../ideas/003-no-need-for-agents-in-everything.md"),
            1,
        )
        self.assertEqual(agents.count("003-no-need-for-agents-in-everything.md"), 1)
        self.assertEqual(new_text.count("../topics/cooking.md"), 1)
        self.assertEqual(new_text.count("../topics/agents.md"), 1)
        self.assertEqual(new_text.count("001-start-command.md"), 1)
        self.assertEqual(
            related.count("003-no-need-for-agents-in-everything.md"),
            1,
        )

    def test_canonical_idea_title_body_remain_unchanged(self) -> None:
        self._apply(
            {
                "use_topic_slugs": ["cooking"],
                "create_topics": [],
                "related_idea_ids": ["002"],
            }
        )
        new_parsed = main.parse_idea_markdown(
            self.new["filename"],
            self.new_path.read_text(encoding="utf-8"),
        )
        self.assertEqual(new_parsed["title"], self.new["title"])
        self.assertEqual(new_parsed["clean_text"], self.new["clean_text"])
        related = main.parse_idea_markdown(
            "002-borek.md",
            (self.ideas / "002-borek.md").read_text(encoding="utf-8"),
        )
        self.assertEqual(related["title"], "This Is How Börek Should Be")
        self.assertEqual(related["clean_text"], "This is what börek should be like.")

    def test_existing_media_remains_unchanged(self) -> None:
        self._apply(
            {
                "use_topic_slugs": ["cooking"],
                "create_topics": [],
                "related_idea_ids": ["002"],
            }
        )
        new_text = self.new_path.read_text(encoding="utf-8")
        related = (self.ideas / "002-borek.md").read_text(encoding="utf-8")
        self.assertIn("![](assets/003-image.jpg)", new_text)
        self.assertIn("![](assets/002-image.jpg)", related)

    def test_empty_decision_causes_no_relationship_changes(self) -> None:
        before_new = self.new_path.read_text(encoding="utf-8")
        before_cooking = (self.topics / "cooking.md").read_text(encoding="utf-8")
        before_001 = (self.ideas / "001-start-command.md").read_text(encoding="utf-8")
        topic_names = {path.name for path in self.topics.glob("*.md")}
        self._apply(
            {
                "use_topic_slugs": [],
                "create_topics": [],
                "related_idea_ids": [],
            }
        )
        self.assertEqual(self.new_path.read_text(encoding="utf-8"), before_new)
        self.assertEqual(
            (self.topics / "cooking.md").read_text(encoding="utf-8"),
            before_cooking,
        )
        self.assertEqual(
            (self.ideas / "001-start-command.md").read_text(encoding="utf-8"),
            before_001,
        )
        self.assertEqual(
            {path.name for path in self.topics.glob("*.md")},
            topic_names,
        )
        self.assertNotIn("## Topics", before_new)
        self.assertNotIn("## Related Ideas", before_new)


if __name__ == "__main__":
    unittest.main()
