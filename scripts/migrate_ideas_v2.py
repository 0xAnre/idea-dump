#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "migrate-ideas-v2")
os.environ.setdefault("OPENROUTER_API_KEY", "migrate-ideas-v2")
os.environ.setdefault("OPENROUTER_MODEL", "migrate-ideas-v2")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main

IDEA_ID_PREFIX = re.compile(r"^(\d+)-")
LOG_ADDED = re.compile(
    r"^- (\d{4}-\d{2}-\d{2}) \d{2}:\d{2} — Added (\d+) —"
)
MEDIA_LINE = re.compile(r"^(!\[\]\([^)]+\)|\[Video\]\([^)]+\))$")
KNOWN_HEADINGS = (
    "## Original Message",
    "## Topics",
    "## Related Ideas",
    "## Source",
)


def ideas_dir(root: Path) -> Path:
    return root / "ideas"


def idea_id_from_filename(name: str) -> str | None:
    match = IDEA_ID_PREFIX.match(name)
    if not match:
        return None
    return f"{int(match.group(1)):03d}"


def is_media_line(line: str) -> bool:
    return MEDIA_LINE.match(line.strip()) is not None


def parse_created_dates(log_path: Path) -> dict[str, str]:
    if not log_path.is_file():
        raise ValueError(f"log.md missing: {log_path}")
    dates: dict[str, str] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        match = LOG_ADDED.match(line)
        if not match:
            continue
        created, raw_id = match.group(1), match.group(2)
        idea_id = f"{int(raw_id):03d}"
        if idea_id not in dates:
            dates[idea_id] = created
    return dates


def recover_quotes_after_heading(text: str, heading: str) -> str | None:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return None
    recovered: list[str] = []
    started = False
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if is_media_line(line):
            continue
        if not started and not line.strip():
            continue
        if line.startswith("> "):
            started = True
            recovered.append(line[2:])
            continue
        if line.strip() == ">":
            started = True
            recovered.append("")
            continue
        if line.strip():
            raise ValueError(f"non-quote content under {heading}")
    if not started:
        raise ValueError(f"{heading} has no recoverable quote text")
    return "\n".join(recovered)


def source_from_backup(source_backup: Path | None, idea_id: str) -> str | None:
    if source_backup is None:
        return None
    matches = [
        path
        for path in source_backup.glob("*.md")
        if idea_id_from_filename(path.name) == idea_id
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(f"multiple Source backup files for Idea {idea_id}")
    recovered = recover_quotes_after_heading(
        matches[0].read_text(encoding="utf-8"),
        "## Original Message",
    )
    if recovered is None:
        raise ValueError(f"Source backup for Idea {idea_id} has no Original Message")
    return recovered


def load_tags_file(path: Path, idea_ids: list[str]) -> dict[str, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("tags file must be a JSON object of Idea ID to tag list")
    missing = [idea_id for idea_id in idea_ids if idea_id not in data]
    extra = sorted(str(key) for key in data.keys() if str(key) not in idea_ids)
    if missing:
        raise ValueError(f"tags file missing Idea IDs: {', '.join(missing)}")
    if extra:
        raise ValueError(f"tags file has unknown Idea IDs: {', '.join(extra)}")
    validated: dict[str, list[str]] = {}
    for idea_id in idea_ids:
        validated[idea_id] = main.validate_idea_tags(data[idea_id], idea_id)
    return validated


def parse_v1_idea(path: Path) -> dict:
    filename = path.name
    idea_id = idea_id_from_filename(filename)
    if idea_id is None:
        raise ValueError(f"filename has no numeric Idea ID: {filename}")
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if text.startswith("---"):
        raise ValueError(f"{filename} already has YAML frontmatter")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ValueError(f"{filename} does not start with an H1 title")
    title = lines[0][2:].strip()
    index = 1
    pre: list[str] = []
    while index < len(lines) and not lines[index].startswith("## "):
        pre.append(lines[index])
        index += 1
    media: list[str] = []
    body_lines: list[str] = []
    for line in pre:
        if is_media_line(line):
            media.append(line.strip())
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    topics = None
    related = None
    while index < len(lines):
        heading = lines[index].strip()
        if heading not in KNOWN_HEADINGS:
            raise ValueError(f"{filename} unexpected heading: {heading}")
        end = index + 1
        while end < len(lines) and not lines[end].startswith("## "):
            end += 1
        chunk = "\n".join(lines[index:end])
        if not chunk.endswith("\n"):
            chunk += "\n"
        if heading == "## Topics":
            topics = chunk
        elif heading == "## Related Ideas":
            related = chunk
        index = end
    return {
        "path": path,
        "raw": raw,
        "filename": filename,
        "id": idea_id,
        "title": title,
        "body": body,
        "media": media,
        "topics": topics,
        "related": related,
    }


def render_v2(
    parsed: dict,
    created: str,
    tags: list[str],
    source_text: str | None,
) -> str:
    created_dt = datetime.strptime(created, "%Y-%m-%d")
    parts = [main.idea_yaml_frontmatter(parsed["id"], parsed["title"], created_dt)]
    parts.append(f"# {parsed['title']}\n\n{parsed['body']}\n")
    if parsed["media"]:
        parts.append("\n")
        for ref in parsed["media"]:
            parts.append(f"{ref}\n")
    if parsed["topics"]:
        section = parsed["topics"]
        if not section.endswith("\n"):
            section += "\n"
        parts.append("\n")
        parts.append(section)
    if parsed["related"]:
        section = parsed["related"]
        if not section.endswith("\n"):
            section += "\n"
        parts.append("\n")
        parts.append(section)
    if source_text is not None:
        parts.append(f"\n## Source\n\n{main.source_blockquote(source_text)}\n")
    return main.replace_frontmatter_tags("".join(parts), tags)


def list_idea_paths(root: Path) -> list[Path]:
    return sorted(
        ideas_dir(root).glob("*.md"),
        key=lambda path: int(idea_id_from_filename(path.name) or 0),
    )


def prepare_plan(
    root: Path,
    *,
    tags_file: Path,
    source_backup: Path | None,
) -> list[dict]:
    log_path = root / "log.md"
    created_dates = parse_created_dates(log_path)
    paths = list_idea_paths(root)
    if not paths:
        raise ValueError("no Idea Markdown files found")
    idea_ids = []
    parsed_items = []
    for path in paths:
        parsed = parse_v1_idea(path)
        idea_ids.append(parsed["id"])
        parsed_items.append(parsed)
    tags_by_id = load_tags_file(tags_file, idea_ids)
    plan = []
    for parsed in parsed_items:
        idea_id = parsed["id"]
        if idea_id not in created_dates:
            raise ValueError(f"no deterministic created date in log.md for Idea {idea_id}")
        source_text = source_from_backup(source_backup, idea_id)
        new_text = render_v2(
            parsed,
            created_dates[idea_id],
            tags_by_id[idea_id],
            source_text,
        )
        plan.append(
            {
                "parsed": parsed,
                "created": created_dates[idea_id],
                "tags": tags_by_id[idea_id],
                "source_text": source_text,
                "new_text": new_text,
            }
        )
    return plan


def format_inventory(root: Path, source_backup: Path | None) -> str:
    lines = ["# Idea Dump v2 migration inventory", f"root: {root.resolve()}", ""]
    created_dates = parse_created_dates(root / "log.md") if (root / "log.md").is_file() else {}
    for path in list_idea_paths(root):
        idea_id = idea_id_from_filename(path.name) or "?"
        text = path.read_text(encoding="utf-8")
        has_yaml = text.startswith("---")
        has_source = "## Source" in text
        has_om = "## Original Message" in text
        backup_source = False
        try:
            backup_source = source_from_backup(source_backup, idea_id) is not None
        except ValueError:
            backup_source = False
        lines.append(f"## {path.name}")
        lines.append(f"- ID: {idea_id}")
        lines.append(f"- YAML: {'yes' if has_yaml else 'no'}")
        lines.append(f"- live Source: {'yes' if has_source else 'no'}")
        lines.append(f"- live Original Message: {'yes' if has_om else 'no'}")
        lines.append(f"- Source backup: {'yes' if backup_source else 'no'}")
        lines.append(f"- created: {created_dates.get(idea_id, 'MISSING')}")
        lines.append("")
    return "\n".join(lines)


def _backup_is_nonempty(backup_dir: Path) -> bool:
    if not backup_dir.exists():
        return False
    return any(backup_dir.iterdir())


def apply_migration(
    root: Path,
    backup_dir: Path,
    *,
    tags_file: Path,
    source_backup: Path | None,
) -> int:
    backup_dir = backup_dir.resolve()
    if _backup_is_nonempty(backup_dir):
        print(f"Apply aborted: backup directory is not empty: {backup_dir}", flush=True)
        return 3
    try:
        plan = prepare_plan(root, tags_file=tags_file, source_backup=source_backup)
    except ValueError as exc:
        print(f"Apply aborted: {exc}", flush=True)
        return 2
    backup_dir.mkdir(parents=True, exist_ok=True)
    for item in plan:
        parsed = item["parsed"]
        (backup_dir / parsed["filename"]).write_bytes(parsed["raw"])
    for item in plan:
        parsed = item["parsed"]
        parsed["path"].write_text(item["new_text"], encoding="utf-8")
    print(f"Apply completed. migrated={len(plan)} backup={backup_dir}", flush=True)
    return 0


def dry_run(
    root: Path,
    *,
    tags_file: Path,
    source_backup: Path | None,
) -> int:
    try:
        plan = prepare_plan(root, tags_file=tags_file, source_backup=source_backup)
    except ValueError as exc:
        print(f"Dry-run aborted: {exc}", flush=True)
        return 2
    print(f"Dry-run OK. would_migrate={len(plan)}", flush=True)
    for item in plan:
        parsed = item["parsed"]
        source = "yes" if item["source_text"] is not None else "no"
        tags = ",".join(item["tags"]) if item["tags"] else "(none)"
        print(
            f"- {parsed['filename']} created={item['created']} "
            f"source={source} tags={tags}",
            flush=True,
        )
    return 0


def _section_heading_block(text: str, heading: str) -> str | None:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    chunk = "\n".join(lines[start:end])
    if not chunk.endswith("\n"):
        chunk += "\n"
    return chunk


def _media_from_text(text: str) -> list[str]:
    body = main._body_after_frontmatter(text)
    media: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            break
        if is_media_line(line):
            media.append(line.strip())
    return media


def verify_migration(
    root: Path,
    backup_dir: Path,
    *,
    tags_file: Path,
    source_backup: Path | None,
) -> int:
    backup_dir = backup_dir.resolve()
    failures: list[str] = []
    if not backup_dir.is_dir():
        print(f"Verify failed: backup directory missing: {backup_dir}", flush=True)
        return 1
    backups = sorted(backup_dir.glob("*.md"))
    if not backups:
        print("Verify failed: backup directory has no Idea Markdown files.", flush=True)
        return 1
    live_dir = ideas_dir(root)
    live_files = {path.name for path in live_dir.glob("*.md")}
    backup_files = {path.name for path in backups}
    if live_files != backup_files:
        failures.append(
            f"Idea filename set changed: live={sorted(live_files)} backup={sorted(backup_files)}"
        )
    created_dates = parse_created_dates(root / "log.md")
    idea_ids = [idea_id_from_filename(name) or "" for name in sorted(backup_files)]
    try:
        tags_by_id = load_tags_file(tags_file, [i for i in idea_ids if i])
    except ValueError as exc:
        print(f"Verify failed: {exc}", flush=True)
        return 1
    for backup_path in backups:
        live_path = live_dir / backup_path.name
        if not live_path.is_file():
            failures.append(f"missing live Idea: {backup_path.name}")
            continue
        try:
            before = parse_v1_idea(backup_path)
        except ValueError as exc:
            failures.append(f"{backup_path.name}: backup unreadable ({exc})")
            continue
        after_text = live_path.read_text(encoding="utf-8")
        try:
            parsed = main.parse_idea_markdown(live_path.name, after_text)
        except Exception as exc:
            failures.append(f"{live_path.name}: parser failed ({exc})")
            continue
        if parsed["id"] != before["id"]:
            failures.append(f"{live_path.name}: ID changed")
        if live_path.name != backup_path.name:
            failures.append(f"{backup_path.name}: filename changed")
        if parsed["title"] != before["title"]:
            failures.append(f"{live_path.name}: title changed")
        if parsed["clean_text"] != before["body"]:
            failures.append(f"{live_path.name}: canonical body changed")
        if _media_from_text(after_text) != before["media"]:
            failures.append(f"{live_path.name}: media refs changed")
        if _section_heading_block(after_text, "## Topics") != before["topics"]:
            failures.append(f"{live_path.name}: Topics changed")
        if _section_heading_block(after_text, "## Related Ideas") != before["related"]:
            failures.append(f"{live_path.name}: Related Ideas changed")
        expected_created = created_dates.get(before["id"])
        if expected_created is None:
            failures.append(f"{live_path.name}: created date missing from log.md")
        elif f"created: {expected_created}" not in after_text:
            failures.append(f"{live_path.name}: created date mismatch")
        if 'type: idea' not in after_text or "source: telegram" not in after_text:
            failures.append(f"{live_path.name}: YAML Properties incomplete")
        try:
            live_tags = main.parse_idea_tags(after_text)
            main.validate_idea_tags(live_tags, before["id"])
        except ValueError as exc:
            failures.append(f"{live_path.name}: tags invalid ({exc})")
        else:
            if live_tags != tags_by_id[before["id"]]:
                failures.append(f"{live_path.name}: tags mismatch")
        try:
            expected_source = source_from_backup(source_backup, before["id"])
        except ValueError as exc:
            failures.append(f"{live_path.name}: Source backup unreadable ({exc})")
            continue
        live_source = main.recover_source_from_idea(after_text)
        if expected_source is None:
            if "## Source" in after_text:
                failures.append(f"{live_path.name}: unexpected Source section")
        elif live_source != expected_source:
            failures.append(f"{live_path.name}: Source does not match backup")
    if failures:
        print("Verify failed:", flush=True)
        for item in failures:
            print(f"- {item}", flush=True)
        return 1
    print("Verify succeeded.", flush=True)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate existing Idea Dump Ideas to v2 canonical Markdown."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory", help="Read-only Idea inventory")
    inv.add_argument("knowledge_base", type=Path)
    inv.add_argument("--source-backup", type=Path, default=None)
    dry = sub.add_parser("dry-run", help="Validate and print the plan; write nothing")
    dry.add_argument("knowledge_base", type=Path)
    dry.add_argument("--tags-file", type=Path, required=True)
    dry.add_argument("--source-backup", type=Path, default=None)
    apply_p = sub.add_parser("apply", help="Backup then rewrite Ideas to v2")
    apply_p.add_argument("knowledge_base", type=Path)
    apply_p.add_argument("backup_dir", type=Path)
    apply_p.add_argument("--tags-file", type=Path, required=True)
    apply_p.add_argument("--source-backup", type=Path, default=None)
    ver = sub.add_parser("verify", help="Compare live v2 Ideas to pre-transform backup")
    ver.add_argument("knowledge_base", type=Path)
    ver.add_argument("backup_dir", type=Path)
    ver.add_argument("--tags-file", type=Path, required=True)
    ver.add_argument("--source-backup", type=Path, default=None)
    return parser.parse_args(argv)


def main_cli(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.knowledge_base
    if not root.is_dir():
        print(f"knowledge-base path is not a directory: {root}", flush=True)
        return 1
    source_backup = args.source_backup
    if args.command == "inventory":
        print(format_inventory(root, source_backup), end="")
        return 0
    if args.command == "dry-run":
        return dry_run(root, tags_file=args.tags_file, source_backup=source_backup)
    if args.command == "apply":
        return apply_migration(
            root,
            args.backup_dir,
            tags_file=args.tags_file,
            source_backup=source_backup,
        )
    return verify_migration(
        root,
        args.backup_dir,
        tags_file=args.tags_file,
        source_backup=source_backup,
    )


if __name__ == "__main__":
    sys.exit(main_cli())
