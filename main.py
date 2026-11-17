import asyncio
import base64
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
OPENROUTER_VISION_MODEL = os.getenv("OPENROUTER_VISION_MODEL") or OPENROUTER_MODEL
OPENCODE_API_KEY = os.getenv("OPENCODE_API_KEY")
OPENCODE_CHAT_MODEL = os.getenv("OPENCODE_CHAT_MODEL") or "deepseek-v4.1-flash"
OPENCODE_VISION_MODEL = os.getenv("OPENCODE_VISION_MODEL") or "glm-5.3-flash"
OPENCODE_CHAT_URL = (
    os.getenv("OPENCODE_CHAT_URL")
    or "https://opencode.ai/inference/go/openai/v1/chat/completions"
)
OPENCODE_SESSION_ID = os.getenv("OPENCODE_SESSION_ID") or "idea-dump"
OPENCODE_USER_AGENT = os.getenv("OPENCODE_USER_AGENT") or "idea-dump/1.0"

if not TELEGRAM_BOT_TOKEN:
    sys.exit("TELEGRAM_BOT_TOKEN is missing")
if not OPENCODE_API_KEY and not (OPENROUTER_API_KEY and OPENROUTER_MODEL):
    sys.exit(
        "No LLM backend configured: set OPENCODE_API_KEY "
        "or OPENROUTER_API_KEY + OPENROUTER_MODEL"
    )

IDEAS_DIR = BASE_DIR / "knowledge-base" / "ideas"
TOPICS_DIR = BASE_DIR / "knowledge-base" / "topics"
SCHEMA_PATH = BASE_DIR / "knowledge-base" / "schema.md"
ASSETS_DIR = BASE_DIR / "knowledge-base" / "assets"
INDEX_PATH = IDEAS_DIR.parent / "index.md"
LOG_PATH = IDEAS_DIR.parent / "log.md"
IDEA_ID_PREFIX = re.compile(r"^(\d+)-")
IDEA_LINK_ID = re.compile(r"ideas/(\d+)-")
IDEA_BODY_STOP_HEADINGS = (
    "## Original Message",
    "## Topics",
    "## Related Ideas",
    "## Source",
)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REWRITE_SYSTEM_PROMPT = """You rewrite Telegram messages into canonical English Ideas.
The input may be in any language. Understand it in that language.
Return JSON only with keys "title" and "clean_text".
"title": a short descriptive English title.
"clean_text": a clear, natural, grammatically correct English Idea body.
Preserve the original meaning and relevant details.
Do not invent information. Do not add new ideas. Do not unnecessarily expand or reinterpret the message.
If the input is already English, clean grammar and clarity; do not translate or rephrase it without need.
Do not return the original Telegram text. That is stored separately as Source."""
IMAGE_TRANSCRIBE_SYSTEM_PROMPT = """You transcribe the text in an image exactly as written.
Preserve the original language, line breaks, and punctuation.
Do not translate, summarize, correct, or add anything.
Do not describe the image.
Skip only obvious interface chrome such as status bars, timestamps, and button labels.
Return JSON only with key "text".
"text": the transcribed text exactly as written, or an empty string when the image has no readable text."""
MAINTAINER_SYSTEM_PROMPT = """You are the Wiki Maintainer for Idea Dump.
Place a new canonical Idea into the existing Markdown wiki.
Return JSON only with keys "use_topic_slugs", "create_topics", "related_idea_ids", and "tags".
Do not rewrite the Idea title or body. Do not return title or clean_text.
Use only the canonical English title and body. Never use Source or original Telegram text.
Prefer an existing Topic when it already covers the Idea.
Create a Topic only when no existing Topic fits.
Link related Ideas only when the relationship is meaningful, not to fill a graph.
use_topic_slugs: slugs of existing Topics to attach.
create_topics: array of {"title", "slug"} for new Topics. Slugs must not collide with existing Topics.
related_idea_ids: JSON array of existing Idea ID strings, zero-padded, e.g. ["031"]. Never numbers, null, or empty strings. Never the new Idea. Use [] when none.
tags: lowercase kebab-case Obsidian labels. Normally 1–3; maximum 4.
Prefer a suitable tag from existing_tags. If none fits, one new broad reusable kebab-case concept is appropriate.
tags: [] is exceptional: test pings, no reusable subject, or similarly unclassifiable input. Do not invent filler merely to avoid [].
Empty Topics or Related Ideas does not imply empty tags.
Tags classify and filter. Topics are wiki nodes. Tags do not replace Topics.
Avoid synonyms and near-duplicates. No nested tags, no #, no spaces."""
TAG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,23}$")
RESERVED_TAGS = frozenset({"idea", "telegram"})
SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


JSON_PARSE_SNIPPET_LIMIT = 240


def _strip_json_fences(content: str | None) -> str:
    if content is None or not str(content).strip():
        raise ValueError("OpenRouter response empty")
    text = str(content).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    if not text:
        raise ValueError("OpenRouter response empty")
    return text


def _json_content_snippet(content: object) -> str:
    text = "" if content is None else str(content)
    clipped = text[:JSON_PARSE_SNIPPET_LIMIT]
    suffix = "..." if len(text) > JSON_PARSE_SNIPPET_LIMIT else ""
    return repr(clipped) + suffix


def _log_json_parse_failure(content: object) -> None:
    print(
        f"OpenRouter JSON parse failed; content_snippet={_json_content_snippet(content)}",
        flush=True,
    )


def _parse_json_object(content: str | None) -> dict:
    text = _strip_json_fences(content)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    else:
        if isinstance(data, dict):
            return data
        _log_json_parse_failure(content)
        raise ValueError("OpenRouter response is not valid JSON")
    start = text.find("{")
    if start != -1:
        try:
            data, _end = json.JSONDecoder().raw_decode(text, start)
        except json.JSONDecodeError:
            data = None
        else:
            if isinstance(data, dict):
                return data
    _log_json_parse_failure(content)
    raise ValueError("OpenRouter response is not valid JSON")


def _parse_title_and_clean_text(content: str | None) -> tuple[str, str]:
    data = _parse_json_object(content)
    title = data.get("title")
    clean_text = data.get("clean_text")
    if not title:
        raise ValueError("OpenRouter response missing title")
    if not clean_text:
        raise ValueError("OpenRouter response missing clean_text")
    return str(title), str(clean_text)


def _parse_transcription(content: str | None) -> str:
    data = _parse_json_object(content)
    text = data.get("text")
    if text is None:
        raise ValueError("OpenRouter response missing text")
    return str(text).strip()


async def _chat_completion(
    system_prompt: str,
    user_content: str | list,
    *,
    url: str,
    api_key: str,
    model: str,
    headers: dict[str, str] | None = None,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    request_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **(headers or {}),
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=request_headers, json=payload)
    if response.status_code != 200:
        raise RuntimeError(
            f"LLM request failed: {response.status_code} {response.text}"
        )
    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("LLM response empty") from exc
    return content


def opencode_headers() -> dict[str, str]:
    return {
        "User-Agent": OPENCODE_USER_AGENT,
        "x-opencode-session": OPENCODE_SESSION_ID,
    }


def _backend(name, url, api_key, model, headers) -> dict:
    return {
        "name": name,
        "url": url,
        "api_key": api_key,
        "model": model,
        "headers": headers,
    }


def text_backends() -> list[dict]:
    """Text backends in priority order: OpenCode first, OpenRouter fallback."""
    backends = []
    if OPENCODE_API_KEY:
        backends.append(
            _backend(
                "opencode",
                OPENCODE_CHAT_URL,
                OPENCODE_API_KEY,
                OPENCODE_CHAT_MODEL,
                opencode_headers(),
            )
        )
    if OPENROUTER_API_KEY and OPENROUTER_MODEL:
        backends.append(
            _backend(
                "openrouter",
                OPENROUTER_URL,
                OPENROUTER_API_KEY,
                OPENROUTER_MODEL,
                {},
            )
        )
    if not backends:
        raise RuntimeError("No text LLM backend configured")
    return backends


def vision_backends() -> list[dict]:
    """Vision backends in priority order: OpenCode first, OpenRouter fallback."""
    backends = []
    if OPENCODE_API_KEY:
        backends.append(
            _backend(
                "opencode",
                OPENCODE_CHAT_URL,
                OPENCODE_API_KEY,
                OPENCODE_VISION_MODEL,
                opencode_headers(),
            )
        )
    if OPENROUTER_API_KEY and OPENROUTER_VISION_MODEL:
        backends.append(
            _backend(
                "openrouter",
                OPENROUTER_URL,
                OPENROUTER_API_KEY,
                OPENROUTER_VISION_MODEL,
                {},
            )
        )
    if not backends:
        raise RuntimeError("No vision LLM backend configured")
    return backends


async def _llm_json(
    system_prompt: str,
    user_content: str | list,
    parse,
    *,
    vision: bool = False,
):
    """Call the first working backend and parse its JSON, falling back silently."""
    backends = vision_backends() if vision else text_backends()
    errors: list[str] = []
    for backend in backends:
        try:
            content = await _chat_completion(
                system_prompt,
                user_content,
                url=backend["url"],
                api_key=backend["api_key"],
                model=backend["model"],
                headers=backend["headers"],
            )
            return parse(content)
        except Exception as exc:
            errors.append(f"{backend['name']}: {exc}")
            print(
                f"LLM backend failed ({backend['name']}): {exc}",
                flush=True,
            )
    raise ValueError("All LLM backends failed: " + "; ".join(errors))


async def rewrite_idea(original_text: str) -> tuple[str, str]:
    return await _llm_json(
        REWRITE_SYSTEM_PROMPT,
        original_text,
        _parse_title_and_clean_text,
    )


async def transcribe_image(
    image_bytes: bytes,
    mime_type: str,
) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    user_content = [
        {"type": "text", "text": "Transcribe the text in this image."},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
        },
    ]
    return await _llm_json(
        IMAGE_TRANSCRIBE_SYSTEM_PROMPT,
        user_content,
        _parse_transcription,
        vision=True,
    )


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


def media_dest(idea_id: str, kind: str) -> Path:
    return ASSETS_DIR / f"{idea_id}-{kind}"


def media_ref(filename: str) -> str:
    return f"../assets/{filename}"


def _yaml_needs_quotes(value: str) -> bool:
    if not value or value != value.strip():
        return True
    if value.lower() in {"true", "false", "null", "yes", "no", "on", "off"}:
        return True
    if value[0] in "-?:{}[]#&*!|>'\"%@`":
        return True
    if ": " in value or " #" in value or "\n" in value or "\r" in value:
        return True
    return False


def _yaml_scalar(value: str, *, force_quotes: bool = False) -> str:
    if force_quotes or _yaml_needs_quotes(value):
        return json.dumps(value, ensure_ascii=False)
    return value


def idea_yaml_frontmatter(
    idea_id: str,
    title: str,
    created: datetime | None = None,
) -> str:
    created_s = (created if created is not None else datetime.now()).strftime(
        "%Y-%m-%d"
    )
    return (
        "---\n"
        f"id: {_yaml_scalar(str(idea_id), force_quotes=True)}\n"
        f"title: {_yaml_scalar(title)}\n"
        "type: idea\n"
        f"created: {created_s}\n"
        "source: telegram\n"
        "tags: []\n"
        "---\n"
    )


def source_blockquote(original_text: str) -> str:
    parts = original_text.split("\n")
    quoted: list[str] = []
    for part in parts:
        quoted.append(">" if part == "" else f"> {part}")
    return "\n".join(quoted)


def recover_source_from_idea(text: str) -> str:
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == "## Source"),
        None,
    )
    if start is None:
        return ""
    recovered: list[str] = []
    started = False
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if not started and not line.strip():
            continue
        if line.startswith("> "):
            started = True
            recovered.append(line[2:])
            continue
        if line == ">":
            started = True
            recovered.append("")
            continue
        break
    return "\n".join(recovered)


def idea_markdown(
    title: str,
    clean_text: str,
    image_ref: str | None = None,
    video_ref: str | None = None,
    *,
    idea_id: str,
    original_text: str,
    created: datetime | None = None,
) -> str:
    body = idea_yaml_frontmatter(idea_id, title, created)
    body += f"# {title}\n\n{clean_text}\n"
    if image_ref:
        body += f"\n![]({image_ref})\n"
    if video_ref:
        body += f"\n[Video]({video_ref})\n"
    body += f"\n## Source\n\n{source_blockquote(original_text)}\n"
    return body


def write_idea_file(
    idea_id: str,
    title: str,
    clean_text: str,
    image_ref: str | None = None,
    video_ref: str | None = None,
    *,
    original_text: str,
    created: datetime | None = None,
) -> Path:
    filename = f"{idea_id}-{title_slug(title)}.md"
    path = IDEAS_DIR / filename
    path.write_text(
        idea_markdown(
            title,
            clean_text,
            image_ref,
            video_ref,
            idea_id=idea_id,
            original_text=original_text,
            created=created,
        ),
        encoding="utf-8",
    )
    return path


def _append_line(path: Path, line: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + line + "\n", encoding="utf-8")


def rebuild_index(
    *,
    ideas_dir: Path | None = None,
    topics_dir: Path | None = None,
    index_path: Path | None = None,
) -> str:
    ideas_dir = ideas_dir if ideas_dir is not None else IDEAS_DIR
    topics_dir = topics_dir if topics_dir is not None else TOPICS_DIR
    index_path = index_path if index_path is not None else INDEX_PATH
    topics: list[dict] = []
    if topics_dir.is_dir():
        for path in topics_dir.glob("*.md"):
            topics.append(
                parse_topic_markdown(path.name, path.read_text(encoding="utf-8"))
            )
    topics.sort(key=lambda topic: (topic["title"].casefold(), topic["slug"]))
    ideas: list[dict] = []
    if ideas_dir.is_dir():
        for path in ideas_dir.glob("*.md"):
            if _idea_id_from_filename(path.name) is None:
                continue
            ideas.append(
                parse_idea_markdown(path.name, path.read_text(encoding="utf-8"))
            )
    ideas.sort(key=lambda idea: int(idea["id"]))
    parts = ["# Idea Dump\n"]
    if topics:
        parts.append("\n## Topics\n\n")
        for topic in topics:
            parts.append(f"- [{topic['title']}](topics/{topic['slug']}.md)\n")
    if ideas:
        parts.append("\n## Ideas\n\n")
        for idea in ideas:
            parts.append(
                f"- {idea['id']} — [{idea['title']}](ideas/{idea['filename']})\n"
            )
    text = "".join(parts)
    index_path.write_text(text, encoding="utf-8")
    return text


def append_wiki_log(
    idea_id: str,
    title: str,
    created_topic_titles: list[str] | None = None,
    *,
    log_path: Path | None = None,
    now: datetime | None = None,
) -> str:
    log_path = log_path if log_path is not None else LOG_PATH
    stamp = (now if now is not None else datetime.now()).strftime("%Y-%m-%d %H:%M")
    line = f"- {stamp} — Added {idea_id} — {title}"
    if created_topic_titles:
        line += f"; created topic {', '.join(created_topic_titles)}"
    if not log_path.exists():
        log_path.write_text("# Log\n", encoding="utf-8")
    _append_line(log_path, line)
    return line


def after_capture_index_and_log(
    idea_id: str,
    title: str,
    decision: dict | None,
    *,
    ideas_dir: Path | None = None,
    topics_dir: Path | None = None,
    index_path: Path | None = None,
    log_path: Path | None = None,
    now: datetime | None = None,
) -> None:
    rebuild_index(
        ideas_dir=ideas_dir,
        topics_dir=topics_dir,
        index_path=index_path,
    )
    created: list[str] = []
    if decision:
        created = [item["title"] for item in decision.get("create_topics") or []]
    append_wiki_log(
        idea_id,
        title,
        created,
        log_path=log_path,
        now=now,
    )


def try_after_capture_index_and_log(
    idea_id: str,
    title: str,
    decision: dict | None,
    *,
    ideas_dir: Path | None = None,
    topics_dir: Path | None = None,
    index_path: Path | None = None,
    log_path: Path | None = None,
    now: datetime | None = None,
) -> None:
    try:
        after_capture_index_and_log(
            idea_id,
            title,
            decision,
            ideas_dir=ideas_dir,
            topics_dir=topics_dir,
            index_path=index_path,
            log_path=log_path,
            now=now,
        )
    except Exception as exc:
        print(f"Index/log update failed: {exc}", flush=True)


def _idea_id_from_filename(name: str) -> str | None:
    match = IDEA_ID_PREFIX.match(name)
    if not match:
        return None
    return match.group(1)


def _body_after_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1 :])
    return text


def parse_idea_markdown(filename: str, text: str) -> dict:
    idea_id = _idea_id_from_filename(filename)
    if idea_id is None:
        raise ValueError(f"Invalid idea filename: {filename}")
    title = ""
    body_lines: list[str] = []
    started = False
    for line in _body_after_frontmatter(text).splitlines():
        if not started:
            if line.startswith("# "):
                title = line[2:].strip()
                started = True
            continue
        if any(line.startswith(heading) for heading in IDEA_BODY_STOP_HEADINGS):
            break
        stripped = line.strip()
        if stripped.startswith("![](") or stripped.startswith("[Video]("):
            continue
        body_lines.append(line)
    return {
        "id": idea_id,
        "title": title,
        "clean_text": "\n".join(body_lines).strip(),
        "filename": filename,
    }


def _frontmatter_lines(text: str) -> tuple[list[str], int] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], i
    return None


def parse_idea_tags(text: str) -> list[str]:
    bounds = _frontmatter_lines(text)
    if bounds is None:
        return []
    fm, _end = bounds
    tags: list[str] = []
    i = 0
    while i < len(fm):
        line = fm[i]
        if not line.startswith("tags:") and line.strip() != "tags:":
            i += 1
            continue
        rest = line.split(":", 1)[1].strip()
        if rest == "[]":
            return []
        if rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1].strip()
            if not inner:
                return []
            return [
                part.strip().strip("\"'")
                for part in inner.split(",")
                if part.strip()
            ]
        i += 1
        while i < len(fm):
            item = fm[i]
            if not (
                item.startswith("  ")
                or item.startswith("\t")
                or item.strip().startswith("- ")
            ):
                break
            stripped = item.strip()
            if stripped.startswith("- "):
                value = stripped[2:].strip().strip("\"'")
                if value:
                    tags.append(value)
            i += 1
        return tags
    return []


def collect_existing_tags(ideas_dir: Path, *, skip_idea_id: str | None = None) -> list[str]:
    found: set[str] = set()
    for path in ideas_dir.glob("*.md"):
        if skip_idea_id and _idea_id_from_filename(path.name) == skip_idea_id:
            continue
        found.update(parse_idea_tags(path.read_text(encoding="utf-8")))
    return sorted(found)


def _yaml_tags_block(tags: list[str]) -> list[str]:
    if not tags:
        return ["tags: []"]
    return ["tags:"] + [f"  - {tag}" for tag in tags]


def replace_frontmatter_tags(text: str, tags: list[str]) -> str:
    lines = text.splitlines()
    bounds = _frontmatter_lines(text)
    if bounds is None:
        if tags:
            raise ValueError("Cannot apply tags without YAML frontmatter")
        return text if text.endswith("\n") else f"{text}\n"
    fm, end = bounds
    start = None
    stop = None
    for i, line in enumerate(fm):
        if line.startswith("tags:") or line.strip() == "tags:":
            start = i
            stop = i + 1
            while stop < len(fm) and (
                fm[stop].startswith("  ")
                or fm[stop].startswith("\t")
                or fm[stop].strip().startswith("- ")
            ):
                stop += 1
            break
    rendered = _yaml_tags_block(tags)
    if start is None:
        fm.extend(rendered)
    else:
        fm[start:stop] = rendered
    updated = ["---", *fm, "---", *lines[end + 1 :]]
    return "\n".join(updated) + "\n"


def validate_idea_tags(raw: object, new_idea_id: str) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError("tags must be a list")
    if len(raw) > 4:
        raise ValueError("tags must contain at most 4 items")
    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item:
            raise ValueError("tags items must be non-empty strings")
        if item == new_idea_id:
            raise ValueError("tags must not include the Idea ID")
        if item != item.lower() or any(ch.isupper() for ch in item):
            raise ValueError(f"Invalid tag: {item}")
        if " " in item or "/" in item or "#" in item:
            raise ValueError(f"Invalid tag: {item}")
        if item.startswith("-") or item.endswith("-") or "--" in item:
            raise ValueError(f"Invalid tag: {item}")
        if len(item) > 24 or not TAG_PATTERN.fullmatch(item):
            raise ValueError(f"Invalid tag: {item}")
        if item in RESERVED_TAGS:
            raise ValueError(f"Reserved tag: {item}")
        if item in seen:
            raise ValueError(f"Duplicate tag: {item}")
        seen.add(item)
        normalized.append(item)
    return normalized


def parse_topic_markdown(filename: str, text: str) -> dict:
    slug = Path(filename).stem
    title = ""
    linked: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        for match in IDEA_LINK_ID.finditer(line):
            idea_id = match.group(1)
            if idea_id not in seen:
                seen.add(idea_id)
                linked.append(idea_id)
    return {
        "slug": slug,
        "title": title,
        "linked_idea_ids": linked,
    }


def build_maintainer_context(
    new_idea_id: str,
    title: str,
    clean_text: str,
    filename: str,
    *,
    ideas_dir: Path | None = None,
    topics_dir: Path | None = None,
    schema_path: Path | None = None,
) -> dict:
    ideas_dir = ideas_dir if ideas_dir is not None else IDEAS_DIR
    topics_dir = topics_dir if topics_dir is not None else TOPICS_DIR
    schema_path = schema_path if schema_path is not None else SCHEMA_PATH
    existing_ideas = []
    for path in sorted(ideas_dir.glob("*.md")):
        parsed = parse_idea_markdown(path.name, path.read_text(encoding="utf-8"))
        if parsed["id"] == new_idea_id:
            continue
        existing_ideas.append(
            {
                "id": parsed["id"],
                "title": parsed["title"],
                "clean_text": parsed["clean_text"],
            }
        )
    existing_topics = []
    if topics_dir.is_dir():
        for path in sorted(topics_dir.glob("*.md")):
            existing_topics.append(
                parse_topic_markdown(path.name, path.read_text(encoding="utf-8"))
            )
    return {
        "schema": schema_path.read_text(encoding="utf-8"),
        "new_idea": {
            "id": new_idea_id,
            "title": title,
            "clean_text": clean_text,
            "filename": filename,
        },
        "existing_topics": existing_topics,
        "existing_ideas": existing_ideas,
        "existing_tags": collect_existing_tags(
            ideas_dir, skip_idea_id=new_idea_id
        ),
    }


def _canonical_related_idea_id(raw: object) -> str:
    if isinstance(raw, bool) or raw is None:
        raise ValueError("related_idea_ids items must be non-empty strings")
    if isinstance(raw, int):
        if raw < 0:
            raise ValueError("related_idea_ids items must be non-empty strings")
        return f"{raw:03d}"
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            raise ValueError("related_idea_ids items must be non-empty strings")
        if stripped.isdigit() and len(stripped) <= 3:
            return f"{int(stripped):03d}"
        return stripped
    raise ValueError("related_idea_ids items must be non-empty strings")


def validate_maintainer_decision(data: dict, context: dict) -> dict:
    required = ("use_topic_slugs", "create_topics", "related_idea_ids", "tags")
    extra = set(data.keys()) - set(required)
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"Maintainer response missing keys: {', '.join(missing)}")
    if extra:
        raise ValueError(f"Maintainer response has unexpected keys: {', '.join(sorted(extra))}")

    use_topic_slugs = data["use_topic_slugs"]
    create_topics = data["create_topics"]
    related_idea_ids = data["related_idea_ids"]
    tags = data["tags"]
    if not isinstance(use_topic_slugs, list):
        raise ValueError("use_topic_slugs must be a list")
    if not isinstance(create_topics, list):
        raise ValueError("create_topics must be a list")
    if not isinstance(related_idea_ids, list):
        raise ValueError("related_idea_ids must be a list")

    existing_topic_slugs = {
        topic["slug"] for topic in context["existing_topics"]
    }
    existing_idea_ids = {idea["id"] for idea in context["existing_ideas"]}
    new_idea_id = context["new_idea"]["id"]

    seen_use: set[str] = set()
    normalized_use: list[str] = []
    for slug in use_topic_slugs:
        if not isinstance(slug, str) or not slug.strip():
            raise ValueError("use_topic_slugs items must be non-empty strings")
        if slug in seen_use:
            raise ValueError(f"Duplicate Topic slug: {slug}")
        if slug not in existing_topic_slugs:
            raise ValueError(f"Unknown Topic slug: {slug}")
        seen_use.add(slug)
        normalized_use.append(slug)

    seen_create: set[str] = set()
    normalized_create: list[dict] = []
    for item in create_topics:
        if not isinstance(item, dict):
            raise ValueError("create_topics items must be objects")
        if set(item.keys()) != {"title", "slug"}:
            raise ValueError("create_topics items must have only title and slug")
        topic_title = item["title"]
        topic_slug = item["slug"]
        if not isinstance(topic_title, str) or not topic_title.strip():
            raise ValueError("create_topics title must be a non-empty string")
        if not isinstance(topic_slug, str) or not topic_slug.strip():
            raise ValueError("create_topics slug must be a non-empty string")
        if topic_slug in seen_create:
            raise ValueError(f"Duplicate Topic slug: {topic_slug}")
        if topic_slug in existing_topic_slugs or topic_slug in seen_use:
            raise ValueError(f"Topic slug collision: {topic_slug}")
        seen_create.add(topic_slug)
        normalized_create.append({"title": topic_title, "slug": topic_slug})

    seen_related: set[str] = set()
    normalized_related: list[str] = []
    for idea_id in related_idea_ids:
        idea_id = _canonical_related_idea_id(idea_id)
        if idea_id == new_idea_id:
            raise ValueError("related_idea_ids must not include the new Idea")
        if idea_id not in existing_idea_ids:
            raise ValueError(f"Unknown Idea ID: {idea_id}")
        if idea_id in seen_related:
            raise ValueError(f"Duplicate related Idea ID: {idea_id}")
        seen_related.add(idea_id)
        normalized_related.append(idea_id)

    normalized_tags = validate_idea_tags(tags, new_idea_id)

    return {
        "use_topic_slugs": normalized_use,
        "create_topics": normalized_create,
        "related_idea_ids": normalized_related,
        "tags": normalized_tags,
    }


def parse_maintainer_decision(content: str | None, context: dict) -> dict:
    data = _parse_json_object(content)
    return validate_maintainer_decision(data, context)


def topic_markdown(title: str, idea_title: str, idea_filename: str) -> str:
    return (
        f"# {title}\n\n"
        f"## Ideas\n\n"
        f"- [{idea_title}](../ideas/{idea_filename})\n"
    )


def _idea_file_for_id(ideas_dir: Path, idea_id: str) -> Path:
    matches = [
        path
        for path in ideas_dir.glob("*.md")
        if _idea_id_from_filename(path.name) == idea_id
    ]
    if not matches:
        raise ValueError(f"Idea file not found for ID: {idea_id}")
    return matches[0]


def _markdown_has_target(text: str, target: str) -> bool:
    return f"]({target})" in text


def _append_list_item(text: str, heading: str, item_line: str, target: str) -> str:
    if _markdown_has_target(text, target):
        return text if text.endswith("\n") else text + "\n"
    item_line = item_line.rstrip("\n")
    lines = text.splitlines()
    heading_idx = next(
        (i for i, line in enumerate(lines) if line.strip() == heading),
        None,
    )
    if heading_idx is None:
        source_idx = next(
            (i for i, line in enumerate(lines) if line.strip() == "## Source"),
            None,
        )
        if source_idx is not None:
            insert_at = source_idx
            while insert_at > 0 and lines[insert_at - 1].strip() == "":
                insert_at -= 1
            block = [heading, "", item_line, ""]
            if insert_at > 0 and lines[insert_at - 1].strip():
                block.insert(0, "")
            del lines[insert_at:source_idx]
            lines[insert_at:insert_at] = block
            return "\n".join(lines) + "\n"
        body = text.rstrip()
        if body:
            body += "\n\n"
        return f"{body}{heading}\n\n{item_line}\n"
    end_idx = heading_idx + 1
    while end_idx < len(lines) and not lines[end_idx].startswith("## "):
        end_idx += 1
    insert_at = heading_idx + 1
    for i in range(end_idx - 1, heading_idx, -1):
        if lines[i].strip():
            insert_at = i + 1
            break
    if insert_at == heading_idx + 1:
        lines.insert(insert_at, "")
        insert_at += 1
    lines.insert(insert_at, item_line)
    return "\n".join(lines) + "\n"


def _add_idea_to_topic(path: Path, idea_title: str, idea_filename: str) -> None:
    target = f"../ideas/{idea_filename}"
    text = path.read_text(encoding="utf-8")
    idea_id = _idea_id_from_filename(idea_filename)
    if idea_id and f"](../ideas/{idea_id}-" in text:
        return
    updated = _append_list_item(
        text,
        "## Ideas",
        f"- [{idea_title}]({target})",
        target,
    )
    path.write_text(updated, encoding="utf-8")


def apply_maintainer_decision(
    decision: dict,
    new_idea_id: str,
    title: str,
    filename: str,
    *,
    ideas_dir: Path | None = None,
    topics_dir: Path | None = None,
) -> None:
    ideas_dir = ideas_dir if ideas_dir is not None else IDEAS_DIR
    topics_dir = topics_dir if topics_dir is not None else TOPICS_DIR
    use_topic_slugs = decision["use_topic_slugs"]
    create_topics = decision["create_topics"]
    related_idea_ids = decision["related_idea_ids"]
    tags = list(decision.get("tags") or [])
    has_graph = bool(use_topic_slugs or create_topics or related_idea_ids)
    if not has_graph and not tags:
        return

    topic_entries: list[tuple[str, str]] = []
    related_entries: list[tuple[str, str, Path]] = []
    if has_graph:
        topics_dir.mkdir(parents=True, exist_ok=True)
        for slug in use_topic_slugs:
            path = topics_dir / f"{slug}.md"
            parsed = parse_topic_markdown(
                path.name, path.read_text(encoding="utf-8")
            )
            _add_idea_to_topic(path, title, filename)
            topic_entries.append((parsed["title"], slug))
        for item in create_topics:
            path = topics_dir / f"{item['slug']}.md"
            if not path.exists():
                path.write_text(
                    topic_markdown(item["title"], title, filename),
                    encoding="utf-8",
                )
            else:
                _add_idea_to_topic(path, title, filename)
            topic_entries.append((item["title"], item["slug"]))
        for idea_id in related_idea_ids:
            related_path = _idea_file_for_id(ideas_dir, idea_id)
            parsed = parse_idea_markdown(
                related_path.name,
                related_path.read_text(encoding="utf-8"),
            )
            related_entries.append((parsed["title"], related_path.name, related_path))

    new_path = ideas_dir / filename
    new_text = new_path.read_text(encoding="utf-8")
    for topic_title, slug in topic_entries:
        target = f"../topics/{slug}.md"
        new_text = _append_list_item(
            new_text,
            "## Topics",
            f"- [{topic_title}]({target})",
            target,
        )
    for related_title, related_filename, _related_path in related_entries:
        new_text = _append_list_item(
            new_text,
            "## Related Ideas",
            f"- [{related_title}]({related_filename})",
            related_filename,
        )
    new_text = replace_frontmatter_tags(new_text, tags)
    new_path.write_text(new_text, encoding="utf-8")

    new_target = filename
    for _related_title, _related_filename, related_path in related_entries:
        related_text = related_path.read_text(encoding="utf-8")
        related_text = _append_list_item(
            related_text,
            "## Related Ideas",
            f"- [{title}]({new_target})",
            new_target,
        )
        related_path.write_text(related_text, encoding="utf-8")


async def maintainer_decision(context: dict) -> dict:
    user_content = json.dumps(context, ensure_ascii=False, indent=2)
    return await _llm_json(
        MAINTAINER_SYSTEM_PROMPT,
        user_content,
        lambda content: parse_maintainer_decision(content, context),
    )


async def run_wiki_maintainer(
    new_idea_id: str,
    title: str,
    clean_text: str,
    filename: str,
) -> dict | None:
    try:
        context = build_maintainer_context(
            new_idea_id,
            title,
            clean_text,
            filename,
        )
        decision = await maintainer_decision(context)
        apply_maintainer_decision(decision, new_idea_id, title, filename)
    except Exception as exc:
        print(f"Wiki Maintainer failed: {exc}", flush=True)
        return None
    print({"wiki_maintainer_decision": decision}, flush=True)
    return decision


def message_image(message) -> tuple[str, str] | None:
    if message.photo:
        return message.photo[-1].file_id, "image/jpeg"
    document = getattr(message, "document", None)
    mime_type = getattr(document, "mime_type", None)
    if isinstance(mime_type, str) and mime_type.lower() in SUPPORTED_IMAGE_MIME_TYPES:
        return document.file_id, mime_type.lower()
    return None


def media_extension(file_path: str | None) -> str:
    if not file_path:
        return ""
    return Path(file_path).suffix


async def download_media(bot, file_id: str, dest: Path) -> str:
    telegram_file = await bot.get_file(file_id)
    dest = dest.with_suffix(media_extension(telegram_file.file_path))
    await telegram_file.download_to_drive(custom_path=dest)
    return dest.name


async def download_media_bytes(bot, file_id: str) -> bytes:
    telegram_file = await bot.get_file(file_id)
    return bytes(await telegram_file.download_as_bytearray())


async def reply_quietly(message, text: str) -> None:
    try:
        await message.reply_text(text)
    except Exception as exc:
        print(f"Telegram reply failed: {exc}", flush=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    text_input = message.text or message.caption
    image = message_image(message)
    video_file_id = message.video.file_id if message.video else None

    if not text_input and image is None:
        return

    has_image = image is not None
    has_video = video_file_id is not None
    image_only = image is not None and not text_input
    source_text = text_input
    image_file_id = None

    if image_only:
        image_source_id, mime_type = image
        try:
            image_bytes = await download_media_bytes(context.bot, image_source_id)
            transcription = await transcribe_image(
                image_bytes, mime_type
            )
        except Exception as exc:
            print(f"Image transcription failed: {exc}", flush=True)
            await reply_quietly(message, "Görseli okuyamadım, kaydetmedim.")
            return
        transcription = transcription.strip()
        if not transcription:
            print({"image_transcription": "empty"}, flush=True)
            await reply_quietly(
                message, "Görselde okunacak yazı bulamadım, kaydetmedim."
            )
            return
        text_input = transcription
        source_text = f"[Read from image]\n\n{transcription}"
    elif image is not None:
        image_file_id = image[0]

    try:
        title, clean_text = await rewrite_idea(text_input)
    except ValueError as exc:
        print(f"OpenRouter rewrite failed: {exc}", flush=True)
        if image_only:
            await reply_quietly(message, "Fikri oluşturamadım, kaydetmedim.")
        return

    idea_id = next_idea_id()

    image_ref = None
    video_ref = None
    if image_file_id:
        image_name = await download_media(
            context.bot,
            image_file_id,
            media_dest(idea_id, "image"),
        )
        image_ref = media_ref(image_name)
    if video_file_id:
        video_name = await download_media(
            context.bot,
            video_file_id,
            media_dest(idea_id, "video"),
        )
        video_ref = media_ref(video_name)

    idea_path = write_idea_file(
        idea_id,
        title,
        clean_text,
        image_ref,
        video_ref,
        original_text=source_text,
    )
    decision = await run_wiki_maintainer(idea_id, title, clean_text, idea_path.name)
    try_after_capture_index_and_log(idea_id, title, decision)

    if image_only:
        await reply_quietly(message, f"Kaydettim: {title}")

    print(
        {
            "original_text": source_text,
            "title": title,
            "clean_text": clean_text,
            "idea_id": idea_id,
            "idea_path": str(idea_path),
            "has_image": has_image,
            "has_video": has_video,
            "image_only": image_only,
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
