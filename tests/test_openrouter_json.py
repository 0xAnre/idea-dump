import asyncio
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("OPENROUTER_MODEL", "test-model")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


OBJECT = '{"title":"Khabib is a Man","clean_text":"Khabib is a man."}'


class ParseJsonObjectTests(unittest.TestCase):
    def test_clean_json_object(self) -> None:
        data = main._parse_json_object(OBJECT)
        self.assertEqual(data["title"], "Khabib is a Man")
        self.assertEqual(data["clean_text"], "Khabib is a man.")

    def test_surrounding_whitespace(self) -> None:
        data = main._parse_json_object(f"\n  {OBJECT}\n")
        self.assertEqual(data["title"], "Khabib is a Man")

    def test_fenced_json(self) -> None:
        fenced = f"```json\n{OBJECT}\n```"
        data = main._parse_json_object(fenced)
        self.assertEqual(data["clean_text"], "Khabib is a man.")

    def test_prose_before_valid_object(self) -> None:
        data = main._parse_json_object(f"Here is the rewrite:\n{OBJECT}")
        self.assertEqual(data["title"], "Khabib is a Man")

    def test_valid_object_followed_by_prose(self) -> None:
        data = main._parse_json_object(f"{OBJECT}\nDone.")
        self.assertEqual(data["clean_text"], "Khabib is a man.")

    def test_prose_before_and_after_valid_object(self) -> None:
        data = main._parse_json_object(f"JSON below.\n{OBJECT}\nThanks.")
        self.assertEqual(data["title"], "Khabib is a Man")

    def test_truncated_object_still_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            main._parse_json_object('{"title":"Khabib is a Man"')

    def test_array_still_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            main._parse_json_object('[{"title":"x","clean_text":"y"}]')

    def test_scalar_still_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            main._parse_json_object('"just a string"')

    def test_missing_title_still_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing title"):
            main._parse_title_and_clean_text('{"title":"","clean_text":"Khabib is a man."}')

    def test_missing_clean_text_still_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing clean_text"):
            main._parse_title_and_clean_text('{"title":"Khabib is a Man","clean_text":""}')

    def test_parse_failure_log_contains_bounded_snippet(self) -> None:
        payload = "{" + ("x" * 400)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            with self.assertRaisesRegex(ValueError, "not valid JSON"):
                main._parse_json_object(payload)
        logged = buf.getvalue()
        self.assertIn("OpenRouter JSON parse failed; content_snippet=", logged)
        self.assertIn("content_snippet='{", logged)
        self.assertIn("...", logged)
        self.assertLess(len(logged), 400)
        self.assertNotIn("test-key", logged)
        self.assertNotIn("Authorization", logged)


class RewriteFailureDoesNotWriteTests(unittest.TestCase):
    def test_rewrite_failure_does_not_call_write_idea_file(self) -> None:
        update = MagicMock()
        update.message.text = "khabib adamdir."
        update.message.caption = None
        update.message.photo = []
        update.message.video = None
        with patch.object(
            main,
            "rewrite_with_openrouter",
            AsyncMock(side_effect=ValueError("OpenRouter response is not valid JSON")),
        ), patch.object(main, "write_idea_file") as write_idea_file:
            asyncio.run(main.handle_message(update, MagicMock()))
            write_idea_file.assert_not_called()
