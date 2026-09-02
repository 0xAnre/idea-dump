import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import migrate_ideas_v2 as migrate


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _kb() -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "ideas").mkdir()
    (root / "topics").mkdir()
    (root / "assets").mkdir()
    (root / "index.md").write_text("# Idea Dump\n", encoding="utf-8")
    (root / "log.md").write_text(
        "# Log\n"
        "- 2026-08-30 08:19 — Added 001 — Start Command\n"
        "- 2026-08-30 08:19 — Added 002 — No Need for Agents in Everything\n",
        encoding="utf-8",
    )
    (root / "topics" / "cooking.md").write_text("# Cooking\n", encoding="utf-8")
    (root / "assets" / "003-image.jpg").write_bytes(b"img")
    return root


def _tags(root: Path, mapping: dict) -> Path:
    path = root / "tags.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


def _backup_dir() -> Path:
    path = Path(tempfile.mkdtemp())
    path.rmdir()
    return path


def _write_idea(root: Path, name: str, text: str) -> Path:
    path = root / "ideas" / name
    path.write_text(text, encoding="utf-8")
    return path


class MigrateIdeasV2Tests(unittest.TestCase):
    def test_v1_to_v2_basic_and_created_from_log(self) -> None:
        root = _kb()
        _write_idea(
            root,
            "001-start-command.md",
            "# Start Command\n\n/start\n",
        )
        tags = _tags(root, {"001": []})
        backup = _backup_dir()
        self.assertEqual(
            migrate.apply_migration(root, backup, tags_file=tags, source_backup=None),
            0,
        )
        text = (root / "ideas" / "001-start-command.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn('id: "001"', text)
        self.assertIn("created: 2026-08-30", text)
        self.assertIn("type: idea", text)
        self.assertIn("source: telegram", text)
        self.assertIn("tags: []", text)
        self.assertIn("# Start Command\n", text)
        self.assertIn("/start", text)
        self.assertNotIn("## Source", text)
        parsed = migrate.main.parse_idea_markdown("001-start-command.md", text)
        self.assertEqual(parsed["title"], "Start Command")
        self.assertEqual(parsed["clean_text"], "/start")

    def test_source_recovery_including_multiline(self) -> None:
        root = _kb()
        _write_idea(
            root,
            "001-start-command.md",
            "# Start Command\n\n/start\n",
        )
        source_backup = Path(tempfile.mkdtemp())
        raw = "line one\n\nline two\n"
        (source_backup / "001-start-command.md").write_text(
            "# Start Command\n\n"
            "/start\n\n"
            "## Original Message\n\n"
            "> line one\n"
            ">\n"
            "> line two\n"
            ">\n",
            encoding="utf-8",
        )
        tags = _tags(root, {"001": ["coding"]})
        backup = _backup_dir()
        self.assertEqual(
            migrate.apply_migration(
                root, backup, tags_file=tags, source_backup=source_backup
            ),
            0,
        )
        text = (root / "ideas" / "001-start-command.md").read_text(encoding="utf-8")
        self.assertEqual(migrate.main.recover_source_from_idea(text), raw)

    def test_missing_source_is_omitted(self) -> None:
        root = _kb()
        _write_idea(
            root,
            "002-no-need-for-agents-in-everything.md",
            "# No Need for Agents in Everything\n\n"
            "You don't need to use an agent for everything.\n",
        )
        source_backup = Path(tempfile.mkdtemp())
        tags = _tags(root, {"002": []})
        backup = _backup_dir()
        migrate.apply_migration(
            root, backup, tags_file=tags, source_backup=source_backup
        )
        text = (root / "ideas" / "002-no-need-for-agents-in-everything.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("## Source", text)

    def test_missing_created_date_fails(self) -> None:
        root = _kb()
        _write_idea(root, "099-orphan.md", "# Orphan\n\nbody\n")
        tags = _tags(root, {"099": []})
        backup = _backup_dir()
        before = (root / "ideas" / "099-orphan.md").read_bytes()
        self.assertEqual(
            migrate.apply_migration(root, backup, tags_file=tags, source_backup=None),
            2,
        )
        self.assertEqual((root / "ideas" / "099-orphan.md").read_bytes(), before)

    def test_yaml_safe_title(self) -> None:
        root = _kb()
        (root / "log.md").write_text(
            "# Log\n- 2026-08-30 10:52 — Added 006 — New Hobby: Cooking\n",
            encoding="utf-8",
        )
        _write_idea(
            root,
            "006-new-hobby-cooking.md",
            "# New Hobby: Cooking\n\nMy new hobby is cooking.\n",
        )
        tags = _tags(root, {"006": ["cooking"]})
        backup = _backup_dir()
        migrate.apply_migration(root, backup, tags_file=tags, source_backup=None)
        text = (root / "ideas" / "006-new-hobby-cooking.md").read_text(encoding="utf-8")
        self.assertIn('title: "New Hobby: Cooking"', text)
        self.assertIn("# New Hobby: Cooking\n", text)

    def test_tag_backfill_and_invalid_tags_fail_before_mutation(self) -> None:
        root = _kb()
        idea = _write_idea(
            root,
            "001-start-command.md",
            "# Start Command\n\n/start\n",
        )
        before = idea.read_bytes()
        tags = _tags(root, {"001": ["NOT-VALID"]})
        backup = _backup_dir()
        self.assertEqual(
            migrate.apply_migration(root, backup, tags_file=tags, source_backup=None),
            2,
        )
        self.assertEqual(idea.read_bytes(), before)
        tags = _tags(root, {"001": ["coding"]})
        backup = _backup_dir()
        migrate.apply_migration(root, backup, tags_file=tags, source_backup=None)
        text = idea.read_text(encoding="utf-8")
        self.assertEqual(migrate.main.parse_idea_tags(text), ["coding"])

    def test_media_topics_related_filename_preserved(self) -> None:
        root = _kb()
        _write_idea(
            root,
            "003-this-is-how-brek-should-be.md",
            "# This Is How Börek Should Be\n\n"
            "This is what börek should be like.\n\n"
            "![](../assets/003-image.jpg)\n\n"
            "## Topics\n\n"
            "- [Cooking](../topics/cooking.md)\n\n"
            "## Related Ideas\n\n"
            "- [Start Command](001-start-command.md)\n",
        )
        (root / "log.md").write_text(
            "# Log\n- 2026-08-30 08:22 — Added 003 — This Is How Börek Should Be\n",
            encoding="utf-8",
        )
        tags = _tags(root, {"003": ["cooking"]})
        backup = _backup_dir()
        migrate.apply_migration(root, backup, tags_file=tags, source_backup=None)
        path = root / "ideas" / "003-this-is-how-brek-should-be.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("![](../assets/003-image.jpg)", text)
        self.assertIn("- [Cooking](../topics/cooking.md)", text)
        self.assertIn("- [Start Command](001-start-command.md)", text)
        parsed = migrate.main.parse_idea_markdown(path.name, text)
        self.assertEqual(parsed["id"], "003")
        self.assertEqual(parsed["clean_text"], "This is what börek should be like.")

    def test_dry_run_makes_zero_mutations(self) -> None:
        root = _kb()
        idea = _write_idea(
            root,
            "001-start-command.md",
            "# Start Command\n\n/start\n",
        )
        tags = _tags(root, {"001": []})
        before = {p: _sha(p) for p in root.rglob("*") if p.is_file()}
        self.assertEqual(
            migrate.dry_run(root, tags_file=tags, source_backup=None),
            0,
        )
        after = {p: _sha(p) for p in root.rglob("*") if p.is_file()}
        self.assertEqual(after, before)
        self.assertFalse(idea.read_text(encoding="utf-8").startswith("---"))

    def test_mandatory_backup_and_nonempty_rejected(self) -> None:
        root = _kb()
        _write_idea(root, "001-start-command.md", "# Start Command\n\n/start\n")
        tags = _tags(root, {"001": []})
        occupied = Path(tempfile.mkdtemp())
        (occupied / "stale.txt").write_text("nope", encoding="utf-8")
        self.assertEqual(
            migrate.apply_migration(
                root, occupied, tags_file=tags, source_backup=None
            ),
            3,
        )
        self.assertFalse(
            (root / "ideas" / "001-start-command.md").read_text().startswith("---")
        )

    def test_exact_pre_transform_backup_bytes(self) -> None:
        root = _kb()
        original = "# Start Command\n\n/start\n"
        idea = _write_idea(root, "001-start-command.md", original)
        original_bytes = idea.read_bytes()
        tags = _tags(root, {"001": []})
        backup = _backup_dir()
        migrate.apply_migration(root, backup, tags_file=tags, source_backup=None)
        saved = backup / "001-start-command.md"
        self.assertEqual(saved.read_bytes(), original_bytes)
        self.assertNotEqual(idea.read_bytes(), original_bytes)

    def test_verify_success_and_detects_corruption(self) -> None:
        root = _kb()
        _write_idea(root, "001-start-command.md", "# Start Command\n\n/start\n")
        tags = _tags(root, {"001": ["coding"]})
        backup = _backup_dir()
        migrate.apply_migration(root, backup, tags_file=tags, source_backup=None)
        self.assertEqual(
            migrate.verify_migration(
                root, backup, tags_file=tags, source_backup=None
            ),
            0,
        )
        live = root / "ideas" / "001-start-command.md"
        live.write_text(live.read_text(encoding="utf-8").replace("/start", "CHANGED"), encoding="utf-8")
        self.assertEqual(
            migrate.verify_migration(
                root, backup, tags_file=tags, source_backup=None
            ),
            1,
        )

    def test_does_not_modify_index_log_topics_assets(self) -> None:
        root = _kb()
        _write_idea(root, "001-start-command.md", "# Start Command\n\n/start\n")
        watched = [
            root / "index.md",
            root / "log.md",
            root / "topics" / "cooking.md",
            root / "assets" / "003-image.jpg",
        ]
        before = {path: path.read_bytes() for path in watched}
        tags = _tags(root, {"001": []})
        migrate.apply_migration(root, _backup_dir(), tags_file=tags, source_backup=None)
        for path, payload in before.items():
            self.assertEqual(path.read_bytes(), payload)

    def test_multiple_ideas_migrated_together(self) -> None:
        root = _kb()
        _write_idea(root, "001-start-command.md", "# Start Command\n\n/start\n")
        _write_idea(
            root,
            "002-no-need-for-agents-in-everything.md",
            "# No Need for Agents in Everything\n\n"
            "You don't need to use an agent for everything.\n",
        )
        source_backup = Path(tempfile.mkdtemp())
        (source_backup / "001-start-command.md").write_text(
            "# Start Command\n\n/start\n\n## Original Message\n\n> /start\n",
            encoding="utf-8",
        )
        tags = _tags(root, {"001": ["coding"], "002": []})
        backup = _backup_dir()
        self.assertEqual(
            migrate.apply_migration(
                root, backup, tags_file=tags, source_backup=source_backup
            ),
            0,
        )
        one = (root / "ideas" / "001-start-command.md").read_text(encoding="utf-8")
        two = (root / "ideas" / "002-no-need-for-agents-in-everything.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(migrate.main.recover_source_from_idea(one), "/start")
        self.assertNotIn("## Source", two)
        self.assertEqual(
            migrate.verify_migration(
                root, backup, tags_file=tags, source_backup=source_backup
            ),
            0,
        )
        self.assertEqual(len(list((root / "ideas").glob("*.md"))), 2)


if __name__ == "__main__":
    unittest.main()
