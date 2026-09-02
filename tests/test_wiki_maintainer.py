import asyncio
import os
import sys
import tempfile
import unittest
from datetime import datetime
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
        self.assertEqual(context["existing_tags"], [])


class WikiMaintainerDecisionTests(unittest.TestCase):
    def test_valid_empty_decision(self) -> None:
        decision = main.parse_maintainer_decision(
            '{"use_topic_slugs":[],"create_topics":[],"related_idea_ids":[],"tags":[]}',
            _context(),
        )
        self.assertEqual(
            decision,
            {
                "use_topic_slugs": [],
                "create_topics": [],
                "related_idea_ids": [],
                "tags": [],
            },
        )

    def test_valid_existing_topic_selection(self) -> None:
        decision = main.parse_maintainer_decision(
            '{"use_topic_slugs":["cooking"],"create_topics":[],"related_idea_ids":[],"tags":[]}',
            _context(),
        )
        self.assertEqual(decision["use_topic_slugs"], ["cooking"])

    def test_valid_new_topic_creation(self) -> None:
        decision = main.parse_maintainer_decision(
            '{"use_topic_slugs":[],"create_topics":[{"title":"Agents","slug":"agents"}],"related_idea_ids":[],"tags":[]}',
            _context(),
        )
        self.assertEqual(
            decision["create_topics"],
            [{"title": "Agents", "slug": "agents"}],
        )

    def test_valid_related_idea_selection(self) -> None:
        decision = main.parse_maintainer_decision(
            '{"use_topic_slugs":[],"create_topics":[],"related_idea_ids":["001"],"tags":[]}',
            _context(),
        )
        self.assertEqual(decision["related_idea_ids"], ["001"])

    def test_reject_unknown_topic(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown Topic slug"):
            main.parse_maintainer_decision(
                '{"use_topic_slugs":["travel"],"create_topics":[],"related_idea_ids":[],"tags":[]}',
                _context(),
            )

    def test_reject_topic_collision(self) -> None:
        with self.assertRaisesRegex(ValueError, "Topic slug collision"):
            main.parse_maintainer_decision(
                '{"use_topic_slugs":[],"create_topics":[{"title":"Cooking","slug":"cooking"}],"related_idea_ids":[],"tags":[]}',
                _context(),
            )

    def test_reject_unknown_idea_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown Idea ID"):
            main.parse_maintainer_decision(
                '{"use_topic_slugs":[],"create_topics":[],"related_idea_ids":["999"],"tags":[]}',
                _context(),
            )

    def test_reject_self_link(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not include the new Idea"):
            main.parse_maintainer_decision(
                '{"use_topic_slugs":[],"create_topics":[],"related_idea_ids":["003"],"tags":[]}',
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
                "tags": [],
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
                "tags": [],
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
                "tags": [],
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
                "tags": [],
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
                "tags": [],
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
            "tags": [],
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
                "tags": [],
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
                "tags": [],
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
                "tags": [],
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


class WikiMaintainerV2IdeaTests(unittest.TestCase):
    def test_context_excludes_v2_source_from_canonical_body(self) -> None:
        ideas, topics, schema = _wiki()
        (ideas / "004-winter.md").write_text(
            main.idea_markdown(
                "Vietnam Enters Winter Season",
                "We are gradually entering the winter season in Vietnam.",
                idea_id="004",
                original_text="vietnamda yavas yavas kis sezonuna giriyoruz",
                created=datetime(2026, 9, 1),
            ),
            encoding="utf-8",
        )
        context = main.build_maintainer_context(
            "005",
            "New Idea",
            "A new idea.",
            "005-new.md",
            ideas_dir=ideas,
            topics_dir=topics,
            schema_path=schema,
        )
        dumped = str(context)
        self.assertNotIn("vietnamda yavas yavas kis sezonuna giriyoruz", dumped)
        winter = next(idea for idea in context["existing_ideas"] if idea["id"] == "004")
        self.assertEqual(
            winter["clean_text"],
            "We are gradually entering the winter season in Vietnam.",
        )

    def test_topics_and_related_are_inserted_before_source(self) -> None:
        ideas, topics, _schema = _wiki()
        new_path = ideas / "003-no-need-for-agents-in-everything.md"
        new_path.write_text(
            main.idea_markdown(
                "No Need for Agents in Everything",
                "You don't need to use an agent for everything.",
                idea_id="003",
                original_text="illa her sey icin agent kullanmaya gerek yok",
                created=datetime(2026, 9, 1),
            ),
            encoding="utf-8",
        )
        main.apply_maintainer_decision(
            {
                "use_topic_slugs": ["cooking"],
                "create_topics": [],
                "related_idea_ids": ["001"],
                "tags": [],
            },
            "003",
            "No Need for Agents in Everything",
            "003-no-need-for-agents-in-everything.md",
            ideas_dir=ideas,
            topics_dir=topics,
        )
        text = new_path.read_text(encoding="utf-8")
        self.assertLess(text.index("## Topics"), text.index("## Source"))
        self.assertLess(text.index("## Related Ideas"), text.index("## Source"))
        self.assertEqual(
            main.recover_source_from_idea(text),
            "illa her sey icin agent kullanmaya gerek yok",
        )
        parsed = main.parse_idea_markdown(new_path.name, text)
        self.assertEqual(
            parsed["clean_text"],
            "You don't need to use an agent for everything.",
        )


CREATED = datetime(2026, 9, 1)


def _v2_idea(
    idea_id: str,
    title: str,
    body: str,
    original: str,
    tags: list[str] | None = None,
) -> str:
    text = main.idea_markdown(
        title,
        body,
        idea_id=idea_id,
        original_text=original,
        created=CREATED,
    )
    if tags is None:
        return text
    return main.replace_frontmatter_tags(text, tags)


def _tag_context() -> dict:
    ideas, topics, schema = _wiki()
    (ideas / "010-vietnam.md").write_text(
        _v2_idea(
            "010",
            "Getting Used to Da Nang",
            "Getting used to Da Nang takes time.",
            "danang",
            ["vietnam", "cooking"],
        ),
        encoding="utf-8",
    )
    (ideas / "011-empty.md").write_text(
        _v2_idea(
            "011",
            "Empty Tags",
            "This idea has no tags yet.",
            "bos",
            [],
        ),
        encoding="utf-8",
    )
    new = _new_idea()
    (ideas / new["filename"]).write_text(
        _v2_idea(new["id"], new["title"], new["clean_text"], "agent raw"),
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


class WikiMaintainerTagTests(unittest.TestCase):
    def _parse_tags(self, tags_json: str, context: dict | None = None):
        payload = (
            '{"use_topic_slugs":[],"create_topics":[],'
            f'"related_idea_ids":[],"tags":{tags_json}}}'
        )
        return main.parse_maintainer_decision(payload, context or _context())

    def test_existing_tags_are_sorted_unique(self) -> None:
        context = _tag_context()
        self.assertEqual(context["existing_tags"], ["cooking", "vietnam"])

    def test_v1_ideas_contribute_no_tags(self) -> None:
        context = _context()
        self.assertEqual(context["existing_tags"], [])

    def test_source_excluded_from_tag_context(self) -> None:
        context = _tag_context()
        dumped = str(context)
        self.assertNotIn("danang", dumped)
        self.assertNotIn("agent raw", dumped)
        self.assertNotIn("bos", dumped)

    def test_tags_required_in_decision_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing keys"):
            main.parse_maintainer_decision(
                '{"use_topic_slugs":[],"create_topics":[],"related_idea_ids":[]}',
                _context(),
            )

    def test_empty_tags_valid(self) -> None:
        decision = self._parse_tags("[]")
        self.assertEqual(decision["tags"], [])

    def test_one_to_four_tags_valid(self) -> None:
        self.assertEqual(self._parse_tags('["coding"]')["tags"], ["coding"])
        self.assertEqual(
            self._parse_tags('["vietnam","season","cooking","crypto"]')["tags"],
            ["vietnam", "season", "cooking", "crypto"],
        )

    def test_more_than_four_tags_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at most 4"):
            self._parse_tags('["a","b","c","d","e"]')

    def test_duplicate_tags_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate tag"):
            self._parse_tags('["coding","coding"]')

    def test_uppercase_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid tag"):
            self._parse_tags('["Coding"]')

    def test_spaces_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid tag"):
            self._parse_tags('["da nang"]')

    def test_slash_nested_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid tag"):
            self._parse_tags('["crypto/trading"]')

    def test_hash_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid tag"):
            self._parse_tags('["#vietnam"]')

    def test_leading_trailing_hyphen_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid tag"):
            self._parse_tags('["-vietnam"]')
        with self.assertRaisesRegex(ValueError, "Invalid tag"):
            self._parse_tags('["vietnam-"]')

    def test_consecutive_hyphen_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid tag"):
            self._parse_tags('["da--nang"]')

    def test_over_24_chars_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid tag"):
            self._parse_tags('["abcdefghijklmnopqrstuvwxy"]')

    def test_reserved_idea_and_telegram_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Reserved tag"):
            self._parse_tags('["idea"]')
        with self.assertRaisesRegex(ValueError, "Reserved tag"):
            self._parse_tags('["telegram"]')

    def test_idea_id_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Idea ID"):
            self._parse_tags('["003"]')

    def test_valid_tags_written_preserving_order_and_rest(self) -> None:
        ideas, topics, _schema = _wiki()
        other = ideas / "010-getting-used-to-da-nang.md"
        other.write_text(
            _v2_idea(
                "010",
                "Getting Used to Da Nang",
                "Getting used to Da Nang takes time.",
                "danang",
                ["da-nang"],
            ),
            encoding="utf-8",
        )
        new_path = ideas / "003-no-need-for-agents-in-everything.md"
        original = "illa her sey icin agent kullanmaya gerek yok"
        new_path.write_text(
            _v2_idea(
                "003",
                "No Need for Agents in Everything",
                "You don't need to use an agent for everything.",
                original,
            ),
            encoding="utf-8",
        )
        before_other = other.read_text(encoding="utf-8")
        main.apply_maintainer_decision(
            {
                "use_topic_slugs": ["cooking"],
                "create_topics": [],
                "related_idea_ids": ["001"],
                "tags": ["vietnam", "season"],
            },
            "003",
            "No Need for Agents in Everything",
            new_path.name,
            ideas_dir=ideas,
            topics_dir=topics,
        )
        text = new_path.read_text(encoding="utf-8")
        self.assertIn("id: \"003\"", text)
        self.assertIn("title: No Need for Agents in Everything", text)
        self.assertIn("type: idea", text)
        self.assertIn("created: 2026-09-01", text)
        self.assertIn("source: telegram", text)
        self.assertIn("tags:\n  - vietnam\n  - season\n", text)
        self.assertNotIn("tags: []", text)
        self.assertIn("# No Need for Agents in Everything", text)
        self.assertIn("You don't need to use an agent for everything.", text)
        self.assertEqual(main.recover_source_from_idea(text), original)
        self.assertIn("## Topics", text)
        self.assertIn("## Related Ideas", text)
        self.assertLess(text.index("## Topics"), text.index("## Source"))
        parsed = main.parse_idea_markdown(new_path.name, text)
        self.assertEqual(
            parsed["clean_text"],
            "You don't need to use an agent for everything.",
        )
        self.assertEqual(other.read_text(encoding="utf-8"), before_other)
        self.assertEqual(main.parse_idea_tags(before_other), ["da-nang"])

    def test_maintainer_tag_failure_leaves_canonical_idea_intact(self) -> None:
        ideas, topics, schema = _wiki()
        new = _new_idea()
        path = ideas / new["filename"]
        body = _v2_idea(new["id"], new["title"], new["clean_text"], "raw source")
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
                "_openrouter_chat",
                AsyncMock(
                    return_value=(
                        '{"use_topic_slugs":[],"create_topics":[],'
                        '"related_idea_ids":[],"tags":["NOT-VALID"]}'
                    )
                ),
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
            self.assertEqual(path.read_text(encoding="utf-8"), body)
            self.assertIn("tags: []", body)
        finally:
            main.IDEAS_DIR = original_ideas
            main.TOPICS_DIR = original_topics
            main.SCHEMA_PATH = original_schema


if __name__ == "__main__":
    unittest.main()
