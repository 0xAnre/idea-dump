import asyncio
import base64
import os
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("OPENROUTER_MODEL", "test-model")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main

TRANSCRIBED = "Her akşam 3 madde yazmak, günü daha net görmemi sağlıyor."
TITLE = "Journaling Habit"
CLEAN = "Writing three lines every night clarifies the day."
IMAGE_BYTES = b"\xff\xd8\xff\xe0jpeg-bytes"

MAINTAINER_DECISION = {
    "use_topic_slugs": [],
    "create_topics": [],
    "related_idea_ids": [],
    "tags": ["journaling"],
}


def photo_message(*, text=None, caption=None, photos=None, document=None, video=None):
    message = MagicMock()
    message.text = text
    message.caption = caption
    message.photo = photos if photos is not None else []
    message.document = document
    message.video = video
    message.reply_text = AsyncMock()
    return message


def photos(file_id="large-photo"):
    return [MagicMock(file_id="small-photo"), MagicMock(file_id=file_id)]


def document(mime_type, file_id="document-1"):
    doc = MagicMock()
    doc.mime_type = mime_type
    doc.file_id = file_id
    return doc


class ImageCaptureHarness(unittest.TestCase):
    """Runs handle_message with every side effect mocked out."""

    def run_handler(
        self,
        message,
        *,
        transcription=TRANSCRIBED,
        transcription_error=None,
        rewrite_error=None,
    ):
        update = MagicMock()
        update.message = message
        context = MagicMock()
        context.bot = MagicMock()

        transcribe = AsyncMock()
        if transcription_error is not None:
            transcribe.side_effect = transcription_error
        else:
            transcribe.return_value = transcription

        rewrite = AsyncMock()
        if rewrite_error is not None:
            rewrite.side_effect = rewrite_error
        else:
            rewrite.return_value = (TITLE, CLEAN)

        mocks = {
            "download_media_bytes": AsyncMock(return_value=IMAGE_BYTES),
            "transcribe_image": transcribe,
            "rewrite_idea": rewrite,
            "write_idea_file": MagicMock(
                return_value=Path("081-journaling-habit.md")
            ),
            "run_wiki_maintainer": AsyncMock(return_value=MAINTAINER_DECISION),
            "try_after_capture_index_and_log": MagicMock(),
            "next_idea_id": MagicMock(return_value="081"),
            "download_media": AsyncMock(return_value="081-image.jpg"),
        }
        with ExitStack() as stack:
            for name, mock in mocks.items():
                stack.enter_context(patch.object(main, name, mock))
            asyncio.run(main.handle_message(update, context))
        return mocks


class ImageOnlyCaptureTests(ImageCaptureHarness):
    def test_image_only_is_transcribed_and_treated_like_text(self) -> None:
        message = photo_message(photos=photos())
        mocks = self.run_handler(message)

        mocks["transcribe_image"].assert_awaited_once_with(
            IMAGE_BYTES, "image/jpeg"
        )
        mocks["rewrite_idea"].assert_awaited_once_with(TRANSCRIBED)
        call = mocks["write_idea_file"].call_args
        self.assertEqual(call.args[1], TITLE)
        self.assertEqual(call.args[2], CLEAN)
        self.assertEqual(
            call.kwargs["original_text"],
            f"[Read from image]\n\n{TRANSCRIBED}",
        )

    def test_image_only_does_not_store_the_image_file(self) -> None:
        message = photo_message(photos=photos())
        mocks = self.run_handler(message)

        mocks["download_media"].assert_not_called()
        call = mocks["write_idea_file"].call_args
        self.assertIsNone(call.args[3])
        self.assertIsNone(call.args[4])

    def test_image_only_replies_with_the_saved_title(self) -> None:
        message = photo_message(photos=photos())
        self.run_handler(message)

        message.reply_text.assert_awaited_once_with(f"Kaydettim: {TITLE}")

    def test_image_without_text_writes_nothing_and_warns(self) -> None:
        message = photo_message(photos=photos())
        mocks = self.run_handler(message, transcription="   \n ")

        mocks["write_idea_file"].assert_not_called()
        mocks["rewrite_idea"].assert_not_called()
        message.reply_text.assert_awaited_once()
        self.assertIn("okunacak yazı bulamadım", message.reply_text.call_args.args[0])

    def test_transcription_failure_writes_nothing_and_warns(self) -> None:
        message = photo_message(photos=photos())
        mocks = self.run_handler(
            message, transcription_error=RuntimeError("LLM request failed")
        )

        mocks["write_idea_file"].assert_not_called()
        message.reply_text.assert_awaited_once()
        self.assertIn("Görseli okuyamadım", message.reply_text.call_args.args[0])

    def test_rewrite_failure_on_image_only_warns(self) -> None:
        message = photo_message(photos=photos())
        mocks = self.run_handler(
            message, rewrite_error=ValueError("bad json")
        )

        mocks["write_idea_file"].assert_not_called()
        message.reply_text.assert_awaited_once()
        self.assertIn("Fikri oluşturamadım", message.reply_text.call_args.args[0])

    def test_jpeg_sent_as_document_is_transcribed(self) -> None:
        message = photo_message(document=document("image/JPEG"))
        mocks = self.run_handler(message)

        mocks["transcribe_image"].assert_awaited_once_with(
            IMAGE_BYTES, "image/jpeg"
        )
        self.assertEqual(
            mocks["write_idea_file"].call_args.kwargs["original_text"],
            f"[Read from image]\n\n{TRANSCRIBED}",
        )


class TextWithImageStaysUnchangedTests(ImageCaptureHarness):
    def test_caption_is_used_and_image_kept_as_asset(self) -> None:
        message = photo_message(caption="notlar", photos=photos())
        mocks = self.run_handler(message)

        mocks["transcribe_image"].assert_not_called()
        mocks["download_media_bytes"].assert_not_called()
        mocks["rewrite_idea"].assert_awaited_once_with("notlar")
        call = mocks["write_idea_file"].call_args
        self.assertEqual(call.args[3], "../assets/081-image.jpg")
        self.assertEqual(call.kwargs["original_text"], "notlar")
        message.reply_text.assert_not_called()

    def test_text_only_is_untouched(self) -> None:
        message = photo_message(text="yeni zevkim yemek yapmak")
        mocks = self.run_handler(message)

        mocks["transcribe_image"].assert_not_called()
        mocks["download_media"].assert_not_called()
        mocks["rewrite_idea"].assert_awaited_once_with(
            "yeni zevkim yemek yapmak"
        )
        message.reply_text.assert_not_called()


class IgnoredMessagesTests(ImageCaptureHarness):
    def test_pdf_document_is_ignored(self) -> None:
        message = photo_message(document=document("application/pdf"))
        mocks = self.run_handler(message)

        mocks["transcribe_image"].assert_not_called()
        mocks["write_idea_file"].assert_not_called()
        message.reply_text.assert_not_called()

    def test_video_without_caption_is_ignored(self) -> None:
        message = photo_message(video=MagicMock(file_id="video-1"))
        mocks = self.run_handler(message)

        mocks["write_idea_file"].assert_not_called()
        message.reply_text.assert_not_called()


class TranscriptionRequestTests(unittest.TestCase):
    def test_image_is_sent_as_data_url_to_the_vision_backend(self) -> None:
        captured = {}

        async def fake_chat(
            system_prompt, user_content, *, url, api_key, model, headers=None
        ):
            captured["system_prompt"] = system_prompt
            captured["user_content"] = user_content
            captured["url"] = url
            captured["api_key"] = api_key
            captured["model"] = model
            captured["headers"] = headers
            return '{"text":"hello"}'

        backend = main.vision_backends()[0]
        with patch.object(main, "_chat_completion", fake_chat):
            text = asyncio.run(main.transcribe_image(b"abc", "image/jpeg"))

        self.assertEqual(text, "hello")
        self.assertEqual(captured["url"], backend["url"])
        self.assertEqual(captured["api_key"], backend["api_key"])
        self.assertEqual(captured["model"], backend["model"])
        self.assertEqual(captured["headers"], backend["headers"])
        self.assertEqual(
            captured["system_prompt"], main.IMAGE_TRANSCRIBE_SYSTEM_PROMPT
        )
        image_part = captured["user_content"][1]
        self.assertEqual(image_part["type"], "image_url")
        data_url = image_part["image_url"]["url"]
        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        self.assertEqual(
            data_url.split(",", 1)[1],
            base64.b64encode(b"abc").decode("ascii"),
        )

    def test_transcription_prompt_does_not_reinterpret_the_image(self) -> None:
        prompt = main.IMAGE_TRANSCRIBE_SYSTEM_PROMPT
        self.assertIn("exactly as written", prompt)
        self.assertIn("Do not translate", prompt)
        self.assertIn("Do not translate, summarize, correct, or add anything", prompt)
        self.assertIn("Do not describe the image", prompt)
        self.assertIn('"text"', prompt)
        self.assertIn("empty string", prompt)

    def test_vision_model_is_configured(self) -> None:
        backend = main.vision_backends()[0]
        self.assertIsInstance(backend["model"], str)
        self.assertTrue(backend["model"].strip())

    def test_parse_transcription_returns_empty_for_no_text(self) -> None:
        self.assertEqual(main._parse_transcription('{"text":""}'), "")
        self.assertEqual(main._parse_transcription('{"text":"  hi  "}'), "hi")

    def test_parse_transcription_requires_text_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing text"):
            main._parse_transcription('{"other":"value"}')

    def test_mime_types_supported(self) -> None:
        self.assertEqual(
            main.SUPPORTED_IMAGE_MIME_TYPES,
            frozenset({"image/jpeg", "image/png", "image/webp"}),
        )


class BackendChainTests(unittest.TestCase):
    def test_text_backends_put_opencode_first(self) -> None:
        with patch.object(main, "OPENCODE_API_KEY", "oc-key"), patch.object(
            main, "OPENROUTER_API_KEY", "or-key"
        ), patch.object(main, "OPENROUTER_MODEL", "or-model"):
            backends = main.text_backends()

        self.assertEqual([b["name"] for b in backends], ["opencode", "openrouter"])
        self.assertEqual(backends[0]["model"], main.OPENCODE_CHAT_MODEL)
        self.assertEqual(
            backends[0]["headers"]["x-opencode-session"],
            main.OPENCODE_SESSION_ID,
        )
        self.assertEqual(backends[0]["headers"]["User-Agent"], main.OPENCODE_USER_AGENT)
        self.assertEqual(backends[1]["headers"], {})

    def test_vision_backends_use_the_vision_models(self) -> None:
        with patch.object(main, "OPENCODE_API_KEY", "oc-key"), patch.object(
            main, "OPENROUTER_API_KEY", "or-key"
        ), patch.object(main, "OPENROUTER_VISION_MODEL", "or-vision"):
            backends = main.vision_backends()

        self.assertEqual(backends[0]["model"], main.OPENCODE_VISION_MODEL)
        self.assertEqual(backends[0]["model"], "glm-5.3-flash")
        self.assertEqual(backends[1]["model"], "or-vision")

    def test_openrouter_only_when_opencode_key_is_missing(self) -> None:
        with patch.object(main, "OPENCODE_API_KEY", None), patch.object(
            main, "OPENROUTER_API_KEY", "or-key"
        ), patch.object(main, "OPENROUTER_MODEL", "or-model"):
            backends = main.text_backends()

        self.assertEqual([b["name"] for b in backends], ["openrouter"])

    def test_no_backend_configured_fails_loudly(self) -> None:
        with patch.object(main, "OPENCODE_API_KEY", None), patch.object(
            main, "OPENROUTER_API_KEY", None
        ):
            with self.assertRaisesRegex(RuntimeError, "No text LLM backend"):
                main.text_backends()

    def test_falls_back_to_openrouter_when_opencode_fails(self) -> None:
        calls = []

        async def fake_chat(
            system_prompt, user_content, *, url, api_key, model, headers=None
        ):
            calls.append(url)
            if "opencode" in url:
                raise RuntimeError("opencode down")
            return (
                '{"title":"Journaling Habit",'
                '"clean_text":"Writing three lines."}'
            )

        with patch.object(main, "OPENCODE_API_KEY", "oc-key"), patch.object(
            main, "OPENCODE_CHAT_URL", "https://opencode.invalid/chat"
        ), patch.object(main, "OPENROUTER_API_KEY", "or-key"), patch.object(
            main, "OPENROUTER_MODEL", "or-model"
        ), patch.object(main, "_chat_completion", fake_chat):
            title, clean = asyncio.run(main.rewrite_idea("gunde 3 satir yaz"))

        self.assertEqual(title, "Journaling Habit")
        self.assertEqual(clean, "Writing three lines.")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], "https://opencode.invalid/chat")
        self.assertEqual(calls[1], main.OPENROUTER_URL)

    def test_falls_back_when_opencode_returns_broken_json(self) -> None:
        calls = []

        async def fake_chat(system_prompt, user_content, **kwargs):
            calls.append(kwargs["url"])
            if "opencode" in kwargs["url"]:
                return "not json at all"
            return '{"title":"T","clean_text":"C"}'

        with patch.object(main, "OPENCODE_API_KEY", "oc-key"), patch.object(
            main, "OPENCODE_CHAT_URL", "https://opencode.invalid/chat"
        ), patch.object(main, "OPENROUTER_API_KEY", "or-key"), patch.object(
            main, "OPENROUTER_MODEL", "or-model"
        ), patch.object(main, "_chat_completion", fake_chat):
            title, clean = asyncio.run(main.rewrite_idea("fikir"))

        self.assertEqual((title, clean), ("T", "C"))
        self.assertEqual(len(calls), 2)

    def test_does_not_fall_back_when_opencode_succeeds(self) -> None:
        calls = []

        async def fake_chat(system_prompt, user_content, **kwargs):
            calls.append(kwargs["url"])
            return '{"title":"T","clean_text":"C"}'

        with patch.object(main, "OPENCODE_API_KEY", "oc-key"), patch.object(
            main, "OPENCODE_CHAT_URL", "https://opencode.invalid/chat"
        ), patch.object(main, "OPENROUTER_API_KEY", "or-key"), patch.object(
            main, "OPENROUTER_MODEL", "or-model"
        ), patch.object(main, "_chat_completion", fake_chat):
            asyncio.run(main.rewrite_idea("fikir"))

        self.assertEqual(calls, ["https://opencode.invalid/chat"])

    def test_vision_falls_back_to_the_openrouter_vision_model(self) -> None:
        seen = []

        async def fake_chat(system_prompt, user_content, **kwargs):
            seen.append((kwargs["url"], kwargs["model"]))
            if "opencode" in kwargs["url"]:
                raise RuntimeError("opencode down")
            return '{"text":"hello"}'

        with patch.object(main, "OPENCODE_API_KEY", "oc-key"), patch.object(
            main, "OPENCODE_CHAT_URL", "https://opencode.invalid/chat"
        ), patch.object(main, "OPENROUTER_API_KEY", "or-key"), patch.object(
            main, "OPENROUTER_VISION_MODEL", "or-vision"
        ), patch.object(main, "_chat_completion", fake_chat):
            text = asyncio.run(main.transcribe_image(b"abc", "image/jpeg"))

        self.assertEqual(text, "hello")
        self.assertEqual(seen[0][1], main.OPENCODE_VISION_MODEL)
        self.assertEqual(seen[1], (main.OPENROUTER_URL, "or-vision"))

    def test_all_backends_failing_raises(self) -> None:
        async def fake_chat(system_prompt, user_content, **kwargs):
            raise RuntimeError("down")

        with patch.object(main, "OPENCODE_API_KEY", "oc-key"), patch.object(
            main, "OPENROUTER_API_KEY", "or-key"
        ), patch.object(main, "OPENROUTER_MODEL", "or-model"), patch.object(
            main, "_chat_completion", fake_chat
        ):
            with self.assertRaisesRegex(ValueError, "All LLM backends failed"):
                asyncio.run(main.rewrite_idea("fikir"))


if __name__ == "__main__":
    unittest.main()
