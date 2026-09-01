#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

SKIP_NAMES = {".gitkeep"}
LEGACY_REF = re.compile(r"\]\(assets/([^)]+)\)")
NEW_REF = re.compile(r"\]\(\.\./assets/([^)]+)\)")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def media_names(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    return {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name not in SKIP_NAMES
    }


def ideas_dir(root: Path) -> Path:
    return root / "ideas"


def legacy_assets_dir(root: Path) -> Path:
    return root / "ideas" / "assets"


def dest_assets_dir(root: Path) -> Path:
    return root / "assets"


@dataclass
class Inventory:
    root: Path
    pairs: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    broken: list[tuple[str, int, str]] = field(default_factory=list)
    already_new: list[tuple[str, int, str]] = field(default_factory=list)
    collision_same: list[str] = field(default_factory=list)
    collision_diff: list[str] = field(default_factory=list)
    pair_ideas: dict[str, list[str]] = field(default_factory=dict)
    legacy_sha256: dict[str, str] = field(default_factory=dict)
    dest_sha256: dict[str, str] = field(default_factory=dict)


def scan_idea_refs(root: Path) -> tuple[dict[str, list[tuple[str, int]]], list[tuple[str, int, str]]]:
    legacy: dict[str, list[tuple[str, int]]] = {}
    already_new: list[tuple[str, int, str]] = []
    ideas = ideas_dir(root)
    if not ideas.is_dir():
        return legacy, already_new
    for path in sorted(ideas.glob("*.md")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in LEGACY_REF.finditer(line):
                name = match.group(1)
                legacy.setdefault(name, []).append((path.name, line_no))
            for match in NEW_REF.finditer(line):
                already_new.append((path.name, line_no, match.group(1)))
    return legacy, already_new


def build_inventory(root: Path) -> Inventory:
    root = root.resolve()
    inv = Inventory(root=root)
    legacy_files = media_names(legacy_assets_dir(root))
    dest_files = media_names(dest_assets_dir(root))
    legacy_refs, already_new = scan_idea_refs(root)
    inv.already_new = already_new
    referenced = set(legacy_refs)

    for name in sorted(legacy_files):
        source = legacy_assets_dir(root) / name
        inv.legacy_sha256[name] = sha256_file(source)
        if name in referenced:
            inv.pairs.append(name)
            inv.pair_ideas[name] = sorted({item[0] for item in legacy_refs[name]})
        else:
            inv.orphans.append(name)
        if name in dest_files:
            dest_hash = sha256_file(dest_assets_dir(root) / name)
            inv.dest_sha256[name] = dest_hash
            if dest_hash == inv.legacy_sha256[name]:
                inv.collision_same.append(name)
            else:
                inv.collision_diff.append(name)

    for name in sorted(referenced):
        if name not in legacy_files:
            for idea_name, line_no in legacy_refs[name]:
                inv.broken.append((idea_name, line_no, name))

    for name in dest_files:
        if name not in inv.dest_sha256:
            inv.dest_sha256[name] = sha256_file(dest_assets_dir(root) / name)
    return inv


def format_inventory(inv: Inventory) -> str:
    lines = [
        "# Asset migration inventory",
        f"root: {inv.root}",
        f"pairs: {len(inv.pairs)}",
        f"orphans: {len(inv.orphans)}",
        f"broken: {len(inv.broken)}",
        f"already_new: {len(inv.already_new)}",
        f"collision_same: {len(inv.collision_same)}",
        f"collision_diff: {len(inv.collision_diff)}",
        "",
        "## pairs",
    ]
    if inv.pairs:
        for name in inv.pairs:
            ideas = ", ".join(inv.pair_ideas.get(name, []))
            lines.append(
                f"- {name}  ideas: {ideas}  sha256: {inv.legacy_sha256[name]}"
            )
    else:
        lines.append("- (none)")
    lines.extend(["", "## orphans"])
    if inv.orphans:
        for name in inv.orphans:
            path = legacy_assets_dir(inv.root) / name
            lines.append(
                f"- {name}  size: {path.stat().st_size}  sha256: {inv.legacy_sha256[name]}"
            )
    else:
        lines.append("- (none)")
    lines.extend(["", "## broken"])
    if inv.broken:
        for idea_name, line_no, name in inv.broken:
            lines.append(f"- {idea_name}:{line_no}  ref: assets/{name}")
    else:
        lines.append("- (none)")
    lines.extend(["", "## already_new"])
    if inv.already_new:
        for idea_name, line_no, name in inv.already_new:
            lines.append(f"- {idea_name}:{line_no}  ref: ../assets/{name}")
    else:
        lines.append("- (none)")
    lines.extend(["", "## collision_same"])
    if inv.collision_same:
        for name in inv.collision_same:
            lines.append(f"- {name}  (skip copy; still rewrite Markdown if still legacy)")
    else:
        lines.append("- (none)")
    lines.extend(["", "## collision_diff"])
    if inv.collision_diff:
        for name in inv.collision_diff:
            lines.append(
                f"- {name}  legacy_sha256: {inv.legacy_sha256[name]}  "
                f"dest_sha256: {inv.dest_sha256[name]}"
            )
    else:
        lines.append("- (none)")
    return "\n".join(lines) + "\n"


def rewrite_legacy_media_paths(text: str, names: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in names:
            return f"](../assets/{name})"
        return match.group(0)

    return LEGACY_REF.sub(replace, text)


def apply_migration(
    root: Path,
    *,
    copy_file=shutil.copy2,
) -> int:
    root = root.resolve()
    inv = build_inventory(root)
    print(format_inventory(inv), end="")
    if inv.collision_diff:
        print(
            "Apply aborted: collision_diff present. No files were changed.",
            flush=True,
        )
        return 2

    dest_dir = dest_assets_dir(root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in inv.pairs:
        source = legacy_assets_dir(root) / name
        dest = dest_dir / name
        if name in inv.collision_same and dest.exists():
            continue
        copy_file(source, dest)

    for name in inv.pairs:
        source = legacy_assets_dir(root) / name
        dest = dest_dir / name
        if not dest.is_file():
            print(f"Apply aborted: missing dest after copy: {name}", flush=True)
            return 1
        if sha256_file(dest) != sha256_file(source):
            print(
                f"Apply aborted: SHA-256 mismatch after copy: {name}. "
                "Markdown was not rewritten.",
                flush=True,
            )
            return 1

    names = set(inv.pairs)
    if names:
        for path in sorted(ideas_dir(root).glob("*.md")):
            original = path.read_text(encoding="utf-8")
            updated = rewrite_legacy_media_paths(original, names)
            if updated != original:
                path.write_text(updated, encoding="utf-8")
    print("Apply completed.", flush=True)
    return 0


def verify_migration(root: Path) -> int:
    root = root.resolve()
    failures: list[str] = []
    dest_dir = dest_assets_dir(root)
    legacy_dir = legacy_assets_dir(root)
    ideas = ideas_dir(root)
    if ideas.is_dir():
        for path in sorted(ideas.glob("*.md")):
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                for match in NEW_REF.finditer(line):
                    name = match.group(1)
                    dest = dest_dir / name
                    if not dest.is_file():
                        failures.append(
                            f"broken migrated ref {path.name}:{line_no} ../assets/{name}"
                        )
    if legacy_dir.is_dir():
        for name in sorted(media_names(legacy_dir)):
            source = legacy_dir / name
            if not source.is_file():
                failures.append(f"missing legacy source: {name}")
                continue
            dest = dest_dir / name
            if dest.is_file() and sha256_file(dest) != sha256_file(source):
                failures.append(f"byte mismatch for {name}")
    if failures:
        print("Verify failed:", flush=True)
        for item in failures:
            print(f"- {item}", flush=True)
        return 1
    print("Verify succeeded.", flush=True)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy Idea Dump assets.")
    parser.add_argument(
        "command",
        choices=("inventory", "apply", "verify"),
        help="inventory is read-only; apply copies then rewrites; verify checks result",
    )
    parser.add_argument(
        "knowledge_base",
        type=Path,
        help="Path to the knowledge-base directory",
    )
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
        return apply_migration(root)
    return verify_migration(root)


if __name__ == "__main__":
    sys.exit(main())
