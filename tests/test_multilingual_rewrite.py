import asyncio
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("OPENROUTER_MODEL", "test-model")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main

CREATED = datetime(2026, 9, 1, 12, 0)

TURKISH = "yeni zevkim yemek yapmak"
ENGLISH = "try cooking lunch at home this week"
SPANISH = "quiero aprender a cocinar este fin de semana"


class RewritePromptContractTests(unittest.TestCase):
    def test_prompt_accepts_any_language_not_turkish_only(self) -> None:
        prompt = main.REWRITE_SYSTEM_PROMPT
        self.assertIn("any language", prompt)
        self.assertIn("English", prompt)
        self.assertIn("already English", prompt)
        self.assertNotIn("informal Turkish", prompt)
        self.assertNotIn("Turkish", prompt)

    def test_maintainer_prompt_still_uses_canonical_english_only(self) -> None:
        self.assertIn("canonical English", main.MAINTAINER_SYSTEM_PROMPT)
        self.assertNotIn("Turkish", main.MAINTAINER_SYSTEM_PROMPT)


class RewritePassesOriginalTextTests(unittest.TestCase):
    def test_openrouter_user_content_is_unmodified_source(self) -> None:
        async def fake_chat(system_prompt: str, user_content: str) -> str:
            self.assertEqual(system_prompt, main.REWRITE_SYSTEM_PROMPT)
            self.assertEqual(user_content, TURKISH)
            return '{"title":"New Hobby: Cooking","clean_text":"My new hobby is cooking."}'

        with patch.object(main, "_openrouter_chat", fake_chat):
            title, clean_text = asyncio.run(main.rewrite_with_openrouter(TURKISH))
        self.assertEqual(title, "New Hobby: Cooking")
        self.assertEqual(clean_text, "My new hobby is cooking.")


class SourceFidelityAndEnglishCanonicalTests(unittest.TestCase):
    def _round_trip(self, raw: str, title: str, english_body: str) -> dict:
        body = main.idea_markdown(
            title,
            english_body,
            idea_id="006",
            original_text=raw,
            created=CREATED,
        )
        parsed = main.parse_idea_markdown("006-idea.md", body)
        self.assertEqual(main.recover_source_from_idea(body), raw)
        self.assertEqual(parsed["clean_text"], english_body)
        self.assertNotIn(raw, parsed["clean_text"])
        self.assertIn("## Source", body)
        return parsed

    def test_turkish_input_english_canonical_source_verbatim(self) -> None:
        parsed = self._round_trip(
            TURKISH,
            "New Hobby: Cooking",
            "My new hobby is cooking.",
        )
        self.assertEqual(parsed["title"], "New Hobby: Cooking")

    def test_english_input_cleaned_english_source_verbatim(self) -> None:
        self._round_trip(
            ENGLISH,
            "Try Cooking Lunch at Home This Week",
            "Try cooking lunch at home this week.",
        )

    def test_spanish_input_english_canonical_source_verbatim(self) -> None:
        parsed = self._round_trip(
            SPANISH,
            "Learn to Cook This Weekend",
            "I want to learn to cook this weekend.",
        )
        self.assertEqual(parsed["clean_text"], "I want to learn to cook this weekend.")

    def test_v2_headings_unchanged(self) -> None:
        body = main.idea_markdown(
            "New Hobby: Cooking",
            "My new hobby is cooking.",
            idea_id="006",
            original_text=TURKISH,
            created=CREATED,
        )
        self.assertIn("## Source", body)
        self.assertNotIn("## Original Message", body)
        self.assertIn("type: idea", body)
        parsed = main.parse_idea_markdown("006-new-hobby-cooking.md", body)
        self.assertEqual(parsed["id"], "006")
        self.assertEqual(parsed["title"], "New Hobby: Cooking")


class HandleMessageUsesOriginalAsSourceTests(unittest.TestCase):
    def test_handle_message_passes_spanish_text_unchanged_to_write(self) -> None:
        update = MagicMock()
        update.message.text = SPANISH
        update.message.caption = None
        update.message.photo = []
        update.message.video = None
        rewrite = AsyncMock(
            return_value=("Learn to Cook This Weekend", "I want to learn to cook this weekend.")
        )
        with patch.object(main, "rewrite_with_openrouter", rewrite), patch.object(
            main,
            "run_wiki_maintainer",
            AsyncMock(
                return_value={
                    "use_topic_slugs": [],
                    "create_topics": [],
                    "related_idea_ids": [],
                    "tags": ["cooking"],
                }
            ),
        ), patch.object(main, "try_after_capture_index_and_log"), patch.object(
            main, "write_idea_file", return_value=Path("006-learn-to-cook-this-weekend.md")
        ) as write_idea_file, patch.object(main, "next_idea_id", return_value="006"):
            asyncio.run(main.handle_message(update, MagicMock()))
        write_idea_file.assert_called_once()
        kwargs = write_idea_file.call_args
        self.assertEqual(kwargs.kwargs["original_text"], SPANISH)
        self.assertEqual(kwargs.args[1], "Learn to Cook This Weekend")
        self.assertEqual(kwargs.args[2], "I want to learn to cook this weekend.")
        rewrite.assert_awaited_once_with(SPANISH)


if __name__ == "__main__":
    unittest.main()
