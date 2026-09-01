#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

IDEA_ID_PREFIX = re.compile(r"^(\d+)-")
KNOWN_HEADINGS = ("## Original Message", "## Topics", "## Related Ideas")
MEDIA_LINE = re.compile(r"^(!\[\]\([^)]+\)|\[Video\]\([^)]+\))$")


def ideas_dir(root: Path) -> Path:
    return root / "ideas"


def idea_id_from_filename(name: str) -> str | None:
    match = IDEA_ID_PREFIX.match(name)
    if not match:
        return None
    return match.group(1)


def is_media_line(line: str) -> bool:
    return MEDIA_LINE.match(line.strip()) is not None


def is_quote_line(line: str) -> bool:
    return line.strip().startswith(">")


@dataclass
class IdeaRecord:
    path: Path
    idea_id: str
    filename: str
    h1: str
    body: str
    media: list[str]
    topics_section: str | None
    related_section: str | None
    has_original: bool
    classification: str
    reason: str
    needs_migration: bool


@dataclass
class Inventory:
    root: Path
    records: list[IdeaRecord] = field(default_factory=list)

    @property
    def class_a(self) -> list[IdeaRecord]:
        return [item for item in self.records if item.classification == "A"]

    @property
    def class_b(self) -> list[IdeaRecord]:
        return [item for item in self.records if item.classification == "B"]


def _section_text(lines: list[str], start: int) -> tuple[str, int]:
    end = start + 1
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    chunk = "\n".join(lines[start:end])
    if not chunk.endswith("\n"):
        chunk += "\n"
    return chunk, end


def parse_idea_file(path: Path) -> IdeaRecord:
    filename = path.name
    idea_id = idea_id_from_filename(filename) or ""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    blank = IdeaRecord(
        path=path,
        idea_id=idea_id,
        filename=filename,
        h1="",
        body="",
        media=[],
        topics_section=None,
        related_section=None,
        has_original=False,
        classification="B",
        reason="",
        needs_migration=False,
    )
    if not idea_id:
        blank.reason = "filename has no numeric Idea ID"
        return blank
    if not lines or not lines[0].startswith("# "):
        blank.reason = "file does not start with an H1 title"
        return blank

    h1 = lines[0][2:].strip()
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

    topics_section = None
    related_section = None
    has_original = False
    original_ok = True
    unexpected: list[str] = []

    while index < len(lines):
        heading = lines[index].strip()
        if heading not in KNOWN_HEADINGS:
            unexpected.append(heading)
            section, index = _section_text(lines, index)
            continue
        section, next_index = _section_text(lines, index)
        content_lines = lines[index + 1 : next_index]
        if heading == "## Original Message":
            has_original = True
            for line in content_lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if is_media_line(line):
                    media.append(line.strip())
                    continue
                if is_quote_line(line):
                    continue
                original_ok = False
            index = next_index
            continue
        if heading == "## Topics":
            topics_section = section
        elif heading == "## Related Ideas":
            related_section = section
        index = next_index

    reason = ""
    classification = "A"
    if not h1:
        classification = "B"
        reason = "empty H1 title"
    elif not body:
        classification = "B"
        reason = "clean English body is empty or cannot be identified"
    elif unexpected:
        classification = "B"
        reason = "unexpected heading: " + ", ".join(unexpected)
    elif has_original and not original_ok:
        classification = "B"
        reason = "Original Message section contains non-quote, non-media content"

    return IdeaRecord(
        path=path,
        idea_id=idea_id,
        filename=filename,
        h1=h1,
        body=body,
        media=media,
        topics_section=topics_section,
        related_section=related_section,
        has_original=has_original,
        classification=classification,
        reason=reason,
        needs_migration=classification == "A" and has_original,
    )


def build_inventory(root: Path) -> Inventory:
    root = root.resolve()
    inv = Inventory(root=root)
    directory = ideas_dir(root)
    if directory.is_dir():
        for path in sorted(directory.glob("*.md")):
            inv.records.append(parse_idea_file(path))
    return inv


def format_inventory(inv: Inventory) -> str:
    lines = [
        "# Idea canonical migration inventory",
        f"root: {inv.root}",
        f"ideas: {len(inv.records)}",
        f"class_A: {len(inv.class_a)}",
        f"class_B: {len(inv.class_b)}",
        "",
    ]
    for item in inv.records:
        media = ", ".join(item.media) if item.media else "(none)"
        lines.extend(
            [
                f"## {item.filename}",
                f"- ID: {item.idea_id}",
                f"- filename: {item.filename}",
                f"- H1: {item.h1}",
                f"- Original Message: {'yes' if item.has_original else 'no'}",
                f"- media: {media}",
                f"- Topics: {'yes' if item.topics_section else 'no'}",
                f"- Related Ideas: {'yes' if item.related_section else 'no'}",
                f"- class: {item.classification}",
            ]
        )
        if item.classification == "B":
            lines.append(f"- reason: {item.reason}")
        lines.append("")
    return "\n".join(lines)


def render_canonical(item: IdeaRecord) -> str:
    parts = [f"# {item.h1}\n\n", item.body, "\n"]
    if item.media:
        parts.append("\n")
        for ref in item.media:
            parts.append(f"{ref}\n")
    if item.topics_section:
        section = item.topics_section
        if not section.endswith("\n"):
            section += "\n"
        parts.append("\n")
        parts.append(section)
    if item.related_section:
        section = item.related_section
        if not section.endswith("\n"):
            section += "\n"
        parts.append("\n")
        parts.append(section)
    text = "".join(parts)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _backup_is_nonempty(backup_dir: Path) -> bool:
    if not backup_dir.exists():
        return False
    return any(backup_dir.iterdir())


def apply_migration(root: Path, backup_dir: Path) -> int:
    root = root.resolve()
    backup_dir = backup_dir.resolve()
    inv = build_inventory(root)
    print(format_inventory(inv), end="")
    if inv.class_b:
        print(
            "Apply aborted: class B Idea(s) present. No files were changed.",
            flush=True,
        )
        return 2
    if _backup_is_nonempty(backup_dir):
        print(
            f"Apply aborted: backup directory is not empty: {backup_dir}",
            flush=True,
        )
        return 3
    affected = [item for item in inv.class_a if item.needs_migration]
    backup_dir.mkdir(parents=True, exist_ok=True)
    for item in affected:
        shutil.copy2(item.path, backup_dir / item.filename)
        item.path.write_text(render_canonical(item), encoding="utf-8")
    print(
        f"Apply completed. migrated={len(affected)} backup={backup_dir}",
        flush=True,
    )
    return 0


def _canonical_fields(item: IdeaRecord) -> dict:
    return {
        "filename": item.filename,
        "id": item.idea_id,
        "h1": item.h1,
        "body": item.body,
        "media": item.media,
        "topics": item.topics_section,
        "related": item.related_section,
    }


def verify_migration(root: Path, backup_dir: Path) -> int:
    root = root.resolve()
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
    for backup_path in backups:
        live_path = live_dir / backup_path.name
        if not live_path.is_file():
            failures.append(f"missing live Idea after migration: {backup_path.name}")
            continue
        before = parse_idea_file(backup_path)
        after = parse_idea_file(live_path)
        if after.has_original:
            failures.append(f"{backup_path.name}: Original Message still present")
        if after.classification == "B":
            failures.append(f"{backup_path.name}: migrated file classified B ({after.reason})")
        before_fields = _canonical_fields(before)
        after_fields = _canonical_fields(after)
        for key, value in before_fields.items():
            if after_fields[key] != value:
                failures.append(
                    f"{backup_path.name}: {key} changed during migration"
                )
        if live_path.name != backup_path.name:
            failures.append(f"{backup_path.name}: filename changed")
    if failures:
        print("Verify failed:", flush=True)
        for item in failures:
            print(f"- {item}", flush=True)
        return 1
    print("Verify succeeded.", flush=True)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate legacy Idea Dump Ideas to canonical Markdown."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory", help="Read-only A/B classification")
    inv.add_argument("knowledge_base", type=Path)
    apply_p = sub.add_parser("apply", help="Backup then rewrite class A Ideas")
    apply_p.add_argument("knowledge_base", type=Path)
    apply_p.add_argument("backup_dir", type=Path)
    ver = sub.add_parser("verify", help="Compare live Ideas to backup snapshot")
    ver.add_argument("knowledge_base", type=Path)
    ver.add_argument("backup_dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.knowledge_base
    if not root.is_dir():
        print(f"knowledge-base path is not a directory: {root}", flush=True)
        return 1
    if args.command == "inventory":
        print(format_inventory(build_inventory(root)), end="")
        return 0
    if args.command == "apply":
        return apply_migration(root, args.backup_dir)
    return verify_migration(root, args.backup_dir)


if __name__ == "__main__":
    sys.exit(main())
