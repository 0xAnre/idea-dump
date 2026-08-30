import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")

if not TELEGRAM_BOT_TOKEN:
    sys.exit("TELEGRAM_BOT_TOKEN is missing")
if not OPENROUTER_API_KEY:
    sys.exit("OPENROUTER_API_KEY is missing")
if not OPENROUTER_MODEL:
    sys.exit("OPENROUTER_MODEL is missing")

IDEAS_DIR = BASE_DIR / "knowledge-base" / "ideas"
ASSETS_DIR = IDEAS_DIR / "assets"
INDEX_PATH = IDEAS_DIR.parent / "index.md"
LOG_PATH = IDEAS_DIR.parent / "log.md"
IDEA_ID_PREFIX = re.compile(r"^(\d+)-")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REWRITE_SYSTEM_PROMPT = """You rewrite Telegram messages into English.
Return JSON only with keys "title" and "clean_text".
"title": a short descriptive English title.
"clean_text": a clear, natural, grammatically correct English rewrite.
Understand the intended meaning. Preserve the original meaning and relevant details.
Do not invent information. Do not add new ideas. Do not unnecessarily expand or reinterpret the message.
The input may be rough, incomplete, informal Turkish."""


def _parse_title_and_clean_text(content: str) -> tuple[str, str]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    data = json.loads(text)
    title = data.get("title")
    clean_text = data.get("clean_text")
    if not title or not clean_text:
        raise ValueError("OpenRouter response missing title or clean_text")
    return str(title), str(clean_text)


async def rewrite_with_openrouter(original_text: str) -> tuple[str, str]:
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": original_text},
        ],
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
    if response.status_code != 200:
        raise RuntimeError(
            f"OpenRouter request failed: {response.status_code} {response.text}"
        )
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    return _parse_title_and_clean_text(content)


def next_idea_id() -> str:
    highest = 0
    for path in IDEAS_DIR.glob("*.md"):
        match = IDEA_ID_PREFIX.match(path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{highest + 1:03d}"


def title_slug(title: str) -> str:
    slug = title.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return slug.strip("-")


def idea_markdown(
    title: str,
    clean_text: str,
    original_text: str,
    image_ref: str | None = None,
    video_ref: str | None = None,
) -> str:
    quoted = "\n".join(f"> {line}" for line in original_text.splitlines())
    body = f"# {title}\n\n{clean_text}\n\n## Original Message\n\n{quoted}\n"
    if image_ref:
        body += f"\n![]({image_ref})\n"
    if video_ref:
        body += f"\n[Video]({video_ref})\n"
    return body


def write_idea_file(
    idea_id: str,
    title: str,
    clean_text: str,
    original_text: str,
    image_ref: str | None = None,
    video_ref: str | None = None,
) -> Path:
    filename = f"{idea_id}-{title_slug(title)}.md"
    path = IDEAS_DIR / filename
    path.write_text(
        idea_markdown(title, clean_text, original_text, image_ref, video_ref),
        encoding="utf-8",
    )
    return path


def _append_line(path: Path, line: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + line + "\n", encoding="utf-8")


def update_index(idea_id: str, title: str, filename: str) -> None:
    _append_line(INDEX_PATH, f"- {idea_id} — [{title}](ideas/{filename})")


def update_log(idea_id: str, title: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    _append_line(LOG_PATH, f"- {stamp} — Added {idea_id} — {title}")


def media_extension(file_path: str | None) -> str:
    if not file_path:
        return ""
    return Path(file_path).suffix


async def download_media(bot, file_id: str, dest: Path) -> str:
    telegram_file = await bot.get_file(file_id)
    dest = dest.with_suffix(media_extension(telegram_file.file_path))
    await telegram_file.download_to_drive(custom_path=dest)
    return dest.name


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    original_text = message.text or message.caption
    if not original_text:
        return

    has_image = bool(message.photo)
    has_video = message.video is not None
    image_file_id = message.photo[-1].file_id if message.photo else None
    video_file_id = message.video.file_id if message.video else None

    title, clean_text = await rewrite_with_openrouter(original_text)
    idea_id = next_idea_id()

    image_ref = None
    video_ref = None
    if image_file_id:
        image_name = await download_media(
            context.bot,
            image_file_id,
            ASSETS_DIR / f"{idea_id}-image",
        )
        image_ref = f"assets/{image_name}"
    if video_file_id:
        video_name = await download_media(
            context.bot,
            video_file_id,
            ASSETS_DIR / f"{idea_id}-video",
        )
        video_ref = f"assets/{video_name}"

    idea_path = write_idea_file(
        idea_id,
        title,
        clean_text,
        original_text,
        image_ref,
        video_ref,
    )
    update_index(idea_id, title, idea_path.name)
    update_log(idea_id, title)

    print(
        {
            "original_text": original_text,
            "title": title,
            "clean_text": clean_text,
            "idea_id": idea_id,
            "idea_path": str(idea_path),
            "has_image": has_image,
            "has_video": has_video,
            "image_file_id": image_file_id,
            "video_file_id": video_file_id,
        },
        flush=True,
    )


def main() -> None:
    asyncio.set_event_loop(asyncio.new_event_loop())
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    application.run_polling()


if __name__ == "__main__":
    main()
