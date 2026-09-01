import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import migrate_legacy_ideas as migrate


def _kb() -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp())
    ideas = root / "ideas"
    ideas.mkdir()
    backup = Path(tempfile.mkdtemp())
    backup.rmdir()
    return root, backup


def _write(root: Path, name: str, text: str) -> Path:
    path = root / "ideas" / name
    path.write_text(text, encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


TEXT_ONLY = (
    "# No Need for Agents in Everything\n\n"
    "You don't need to use an agent for everything.\n\n"
    "## Original Message\n\n"
    "> secret raw telegram\n"
)

IMAGE_UNDER_ORIGINAL = (
    "# This Is How Börek Should Be\n\n"
    "This is what börek should be like.\n\n"
    "## Original Message\n\n"
    "> raw image caption\n\n"
    "![](../assets/003-image.jpg)\n"
)

VIDEO_UNDER_ORIGINAL = (
    "# Lifeguard in Da Nang\n\n"
    "There is a lifeguard in Da Nang.\n\n"
    "## Original Message\n\n"
    "> raw video caption\n\n"
    "[Video](../assets/004-video.mp4)\n"
)


class InventoryTests(unittest.TestCase):
    def test_normal_text_only_legacy_idea(self) -> None:
        root, _backup = _kb()
        _write(root, "002-no-need-for-agents-in-everything.md", TEXT_ONLY)
        item = migrate.parse_idea_file(
            root / "ideas" / "002-no-need-for-agents-in-everything.md"
        )
        self.assertEqual(item.classification, "A")
        self.assertTrue(item.has_original)
        self.assertEqual(item.h1, "No Need for Agents in Everything")
        self.assertEqual(
            item.body,
            "You don't need to use an agent for everything.",
        )
        report = migrate.format_inventory(migrate.build_inventory(root))
        self.assertIn("class: A", report)
        self.assertNotIn("secret raw telegram", report)

    def test_legacy_image_below_original_message(self) -> None:
        root, _backup = _kb()
        _write(root, "003-borek.md", IMAGE_UNDER_ORIGINAL)
        item = migrate.parse_idea_file(root / "ideas" / "003-borek.md")
        self.assertEqual(item.classification, "A")
        self.assertEqual(item.media, ["![](../assets/003-image.jpg)"])
        self.assertEqual(item.body, "This is what börek should be like.")

    def test_legacy_video_below_original_message(self) -> None:
        root, _backup = _kb()
        _write(root, "004-lifeguard.md", VIDEO_UNDER_ORIGINAL)
        item = migrate.parse_idea_file(root / "ideas" / "004-lifeguard.md")
        self.assertEqual(item.classification, "A")
        self.assertEqual(item.media, ["[Video](../assets/004-video.mp4)"])

    def test_ambiguous_structure_classified_b(self) -> None:
        root, _backup = _kb()
        _write(
            root,
            "099-weird.md",
            "# Weird\n\nbody\n\n## Notes\n\nunexpected\n",
        )
        item = migrate.parse_idea_file(root / "ideas" / "099-weird.md")
        self.assertEqual(item.classification, "B")
        self.assertIn("unexpected heading", item.reason)


class ApplyTests(unittest.TestCase):
    def test_existing_topics_preserved(self) -> None:
        root, backup = _kb()
        _write(
            root,
            "002-agents.md",
            "# Agents\n\n"
            "Body text.\n\n"
            "## Original Message\n\n"
            "> raw\n\n"
            "## Topics\n\n"
            "- [Cooking](../topics/cooking.md)\n",
        )
        self.assertEqual(migrate.apply_migration(root, backup), 0)
        text = (root / "ideas" / "002-agents.md").read_text(encoding="utf-8")
        self.assertIn("## Topics\n\n- [Cooking](../topics/cooking.md)\n", text)
        self.assertNotIn("## Original Message", text)
        self.assertNotIn("> raw", text)

    def test_existing_related_ideas_preserved(self) -> None:
        root, backup = _kb()
        _write(
            root,
            "002-agents.md",
            "# Agents\n\n"
            "Body text.\n\n"
            "## Original Message\n\n"
            "> raw\n\n"
            "## Related Ideas\n\n"
            "- [Start Command](001-start-command.md)\n",
        )
        self.assertEqual(migrate.apply_migration(root, backup), 0)
        text = (root / "ideas" / "002-agents.md").read_text(encoding="utf-8")
        self.assertIn(
            "## Related Ideas\n\n- [Start Command](001-start-command.md)\n",
            text,
        )

    def test_media_already_in_canonical_position(self) -> None:
        root, backup = _kb()
        _write(
            root,
            "003-borek.md",
            "# Borek\n\n"
            "This is what börek should be like.\n\n"
            "![](../assets/003-image.jpg)\n\n"
            "## Original Message\n\n"
            "> raw\n",
        )
        self.assertEqual(migrate.apply_migration(root, backup), 0)
        text = (root / "ideas" / "003-borek.md").read_text(encoding="utf-8")
        self.assertEqual(
            text,
            "# Borek\n\n"
            "This is what börek should be like.\n\n"
            "![](../assets/003-image.jpg)\n",
        )
        self.assertEqual(text.count("![](../assets/003-image.jpg)"), 1)

    def test_any_b_causes_zero_mutations(self) -> None:
        root, backup = _kb()
        safe = _write(root, "002-agents.md", TEXT_ONLY)
        _write(
            root,
            "099-weird.md",
            "# Weird\n\nbody\n\n## Notes\n\nx\n",
        )
        before = safe.read_bytes()
        self.assertEqual(migrate.apply_migration(root, backup), 2)
        self.assertEqual(safe.read_bytes(), before)
        self.assertFalse(backup.exists() and any(backup.iterdir()))

    def test_backup_created_before_mutation(self) -> None:
        root, backup = _kb()
        live = _write(root, "002-agents.md", TEXT_ONLY)
        self.assertEqual(migrate.apply_migration(root, backup), 0)
        saved = backup / "002-agents.md"
        self.assertTrue(saved.exists())
        self.assertIn("## Original Message", saved.read_text(encoding="utf-8"))
        self.assertIn("> secret raw telegram", saved.read_text(encoding="utf-8"))
        self.assertNotIn("## Original Message", live.read_text(encoding="utf-8"))

    def test_existing_non_empty_backup_refuses_apply(self) -> None:
        root, backup = _kb()
        live = _write(root, "002-agents.md", TEXT_ONLY)
        backup.mkdir()
        (backup / "already.md").write_text("nope", encoding="utf-8")
        before = live.read_bytes()
        self.assertEqual(migrate.apply_migration(root, backup), 3)
        self.assertEqual(live.read_bytes(), before)

    def test_original_message_removed_h1_body_media_unchanged(self) -> None:
        root, backup = _kb()
        _write(root, "003-borek.md", IMAGE_UNDER_ORIGINAL)
        self.assertEqual(migrate.apply_migration(root, backup), 0)
        item = migrate.parse_idea_file(root / "ideas" / "003-borek.md")
        self.assertFalse(item.has_original)
        self.assertEqual(item.h1, "This Is How Börek Should Be")
        self.assertEqual(item.body, "This is what börek should be like.")
        self.assertEqual(item.media, ["![](../assets/003-image.jpg)"])
        text = (root / "ideas" / "003-borek.md").read_text(encoding="utf-8")
        self.assertNotIn("## Original Message", text)
        self.assertNotIn("raw image caption", text)

    def test_second_apply_is_safe(self) -> None:
        root, backup = _kb()
        live = _write(root, "002-agents.md", TEXT_ONLY)
        self.assertEqual(migrate.apply_migration(root, backup), 0)
        after_first = live.read_bytes()
        backup2 = Path(tempfile.mkdtemp())
        backup2.rmdir()
        self.assertEqual(migrate.apply_migration(root, backup2), 0)
        self.assertEqual(live.read_bytes(), after_first)
        self.assertNotIn("## Original Message", live.read_text(encoding="utf-8"))

    def test_verify_succeeds_against_backup(self) -> None:
        root, backup = _kb()
        _write(root, "002-agents.md", TEXT_ONLY)
        _write(root, "003-borek.md", IMAGE_UNDER_ORIGINAL)
        _write(root, "004-lifeguard.md", VIDEO_UNDER_ORIGINAL)
        self.assertEqual(migrate.apply_migration(root, backup), 0)
        self.assertEqual(migrate.verify_migration(root, backup), 0)

    def test_inventory_writes_nothing(self) -> None:
        root, _backup = _kb()
        path = _write(root, "002-agents.md", TEXT_ONLY)
        before = path.read_bytes()
        migrate.build_inventory(root)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
