import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import migrate_legacy_assets as migrate


def _kb() -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "ideas" / "assets").mkdir(parents=True)
    (root / "assets").mkdir()
    (root / "ideas" / "assets" / ".gitkeep").write_text("")
    (root / "assets" / ".gitkeep").write_text("")
    return root


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_idea(root: Path, name: str, body: str) -> Path:
    path = root / "ideas" / name
    path.write_text(body, encoding="utf-8")
    return path


class InventoryClassificationTests(unittest.TestCase):
    def test_valid_image_pair(self) -> None:
        root = _kb()
        (root / "ideas" / "assets" / "003-image.jpg").write_bytes(b"jpeg-bytes")
        _write_idea(
            root,
            "003-borek.md",
            "# Borek\n\nbody\n\n![](assets/003-image.jpg)\n",
        )
        inv = migrate.build_inventory(root)
        self.assertEqual(inv.pairs, ["003-image.jpg"])
        self.assertEqual(inv.pair_ideas["003-image.jpg"], ["003-borek.md"])
        report = migrate.format_inventory(inv)
        self.assertIn("pairs: 1", report)
        self.assertIn("003-image.jpg", report)

    def test_valid_video_pair(self) -> None:
        root = _kb()
        (root / "ideas" / "assets" / "004-video.mp4").write_bytes(b"mp4-bytes")
        _write_idea(
            root,
            "004-lifeguard.md",
            "# Lifeguard\n\nbody\n\n[Video](assets/004-video.mp4)\n",
        )
        inv = migrate.build_inventory(root)
        self.assertEqual(inv.pairs, ["004-video.mp4"])

    def test_orphan(self) -> None:
        root = _kb()
        (root / "ideas" / "assets" / "orphan.bin").write_bytes(b"orphan")
        _write_idea(root, "001-text.md", "# Text\n\nno media\n")
        inv = migrate.build_inventory(root)
        self.assertEqual(inv.orphans, ["orphan.bin"])
        self.assertEqual(inv.pairs, [])

    def test_broken_reference(self) -> None:
        root = _kb()
        _write_idea(
            root,
            "005-missing.md",
            "# Missing\n\n![](assets/005-image.jpg)\n",
        )
        inv = migrate.build_inventory(root)
        self.assertEqual(inv.broken, [("005-missing.md", 3, "005-image.jpg")])
        self.assertEqual(inv.pairs, [])

    def test_already_new_reference(self) -> None:
        root = _kb()
        (root / "assets" / "006-image.jpg").write_bytes(b"new")
        _write_idea(
            root,
            "006-new.md",
            "# New\n\n![](../assets/006-image.jpg)\n",
        )
        inv = migrate.build_inventory(root)
        self.assertEqual(inv.already_new[0][2], "006-image.jpg")
        self.assertEqual(inv.pairs, [])
        self.assertEqual(inv.orphans, [])

    def test_collision_same(self) -> None:
        root = _kb()
        payload = b"same-bytes"
        (root / "ideas" / "assets" / "003-image.jpg").write_bytes(payload)
        (root / "assets" / "003-image.jpg").write_bytes(payload)
        _write_idea(
            root,
            "003-borek.md",
            "# Borek\n\n![](assets/003-image.jpg)\n",
        )
        inv = migrate.build_inventory(root)
        self.assertEqual(inv.collision_same, ["003-image.jpg"])
        self.assertEqual(inv.collision_diff, [])
        self.assertEqual(inv.pairs, ["003-image.jpg"])

    def test_collision_diff(self) -> None:
        root = _kb()
        (root / "ideas" / "assets" / "003-image.jpg").write_bytes(b"legacy")
        (root / "assets" / "003-image.jpg").write_bytes(b"other")
        _write_idea(
            root,
            "003-borek.md",
            "# Borek\n\n![](assets/003-image.jpg)\n",
        )
        inv = migrate.build_inventory(root)
        self.assertEqual(inv.collision_diff, ["003-image.jpg"])
        self.assertEqual(inv.collision_same, [])


class ApplyMigrationTests(unittest.TestCase):
    def test_collision_diff_causes_zero_mutations(self) -> None:
        root = _kb()
        (root / "ideas" / "assets" / "003-image.jpg").write_bytes(b"legacy")
        (root / "assets" / "003-image.jpg").write_bytes(b"other")
        idea = _write_idea(
            root,
            "003-borek.md",
            "# Borek\n\nkeep body\n\n![](assets/003-image.jpg)\n",
        )
        before_idea = idea.read_bytes()
        before_legacy = (root / "ideas" / "assets" / "003-image.jpg").read_bytes()
        before_dest = (root / "assets" / "003-image.jpg").read_bytes()
        code = migrate.apply_migration(root)
        self.assertEqual(code, 2)
        self.assertEqual(idea.read_bytes(), before_idea)
        self.assertEqual(
            (root / "ideas" / "assets" / "003-image.jpg").read_bytes(),
            before_legacy,
        )
        self.assertEqual((root / "assets" / "003-image.jpg").read_bytes(), before_dest)

    def test_copy_occurs_before_markdown_rewrite(self) -> None:
        root = _kb()
        (root / "ideas" / "assets" / "003-image.jpg").write_bytes(b"jpeg-bytes")
        idea = _write_idea(
            root,
            "003-borek.md",
            "# Borek\n\n![](assets/003-image.jpg)\n",
        )
        seen: list[str] = []

        def copy_file(src: Path, dst: Path) -> None:
            text = idea.read_text(encoding="utf-8")
            self.assertIn("](assets/003-image.jpg)", text)
            self.assertNotIn("](../assets/003-image.jpg)", text)
            seen.append("copy")
            shutil.copy2(src, dst)

        code = migrate.apply_migration(root, copy_file=copy_file)
        self.assertEqual(code, 0)
        self.assertEqual(seen, ["copy"])
        self.assertIn("](../assets/003-image.jpg)", idea.read_text(encoding="utf-8"))

    def test_sha_mismatch_prevents_markdown_rewrite(self) -> None:
        root = _kb()
        (root / "ideas" / "assets" / "003-image.jpg").write_bytes(b"jpeg-bytes")
        idea = _write_idea(
            root,
            "003-borek.md",
            "# Borek\n\n![](assets/003-image.jpg)\n",
        )
        original = idea.read_text(encoding="utf-8")

        def bad_copy(src: Path, dst: Path) -> None:
            dst.write_bytes(b"corrupted")

        code = migrate.apply_migration(root, copy_file=bad_copy)
        self.assertEqual(code, 1)
        self.assertEqual(idea.read_text(encoding="utf-8"), original)
        self.assertIn("](assets/003-image.jpg)", original)

    def test_idea_content_changes_only_on_the_media_path(self) -> None:
        root = _kb()
        (root / "ideas" / "assets" / "003-image.jpg").write_bytes(b"jpeg-bytes")
        body = (
            "# This Is How Börek Should Be\n\n"
            "This is what börek should be like.\n\n"
            "## Original Message\n\n"
            "> börek böyle olmalı\n\n"
            "![](assets/003-image.jpg)\n\n"
            "## Topics\n\n"
            "- [Cooking](../topics/cooking.md)\n"
        )
        idea = _write_idea(root, "003-borek.md", body)
        self.assertEqual(migrate.apply_migration(root), 0)
        updated = idea.read_text(encoding="utf-8")
        self.assertEqual(
            updated,
            body.replace("](assets/003-image.jpg)", "](../assets/003-image.jpg)"),
        )
        self.assertIn("# This Is How Börek Should Be", updated)
        self.assertIn("This is what börek should be like.", updated)
        self.assertIn("## Original Message", updated)
        self.assertIn("> börek böyle olmalı", updated)
        self.assertIn("## Topics", updated)

    def test_legacy_source_remains_after_apply(self) -> None:
        root = _kb()
        source = root / "ideas" / "assets" / "004-video.mp4"
        source.write_bytes(b"mp4-bytes")
        _write_idea(
            root,
            "004-lifeguard.md",
            "# Lifeguard\n\n[Video](assets/004-video.mp4)\n",
        )
        self.assertEqual(migrate.apply_migration(root), 0)
        self.assertTrue(source.exists())
        self.assertEqual(source.read_bytes(), b"mp4-bytes")
        dest = root / "assets" / "004-video.mp4"
        self.assertTrue(dest.exists())
        self.assertEqual(_sha(source), _sha(dest))

    def test_second_apply_is_safe_idempotent(self) -> None:
        root = _kb()
        (root / "ideas" / "assets" / "003-image.jpg").write_bytes(b"jpeg-bytes")
        idea = _write_idea(
            root,
            "003-borek.md",
            "# Borek\n\n![](assets/003-image.jpg)\n",
        )
        self.assertEqual(migrate.apply_migration(root), 0)
        after_first_idea = idea.read_bytes()
        after_first_dest = (root / "assets" / "003-image.jpg").read_bytes()
        after_first_src = (root / "ideas" / "assets" / "003-image.jpg").read_bytes()
        self.assertEqual(migrate.apply_migration(root), 0)
        self.assertEqual(idea.read_bytes(), after_first_idea)
        self.assertEqual(
            (root / "assets" / "003-image.jpg").read_bytes(),
            after_first_dest,
        )
        self.assertEqual(
            (root / "ideas" / "assets" / "003-image.jpg").read_bytes(),
            after_first_src,
        )
        self.assertEqual(idea.read_text(encoding="utf-8").count("../assets/"), 1)

    def test_verify_succeeds_after_valid_migration(self) -> None:
        root = _kb()
        (root / "ideas" / "assets" / "003-image.jpg").write_bytes(b"jpeg-bytes")
        (root / "ideas" / "assets" / "004-video.mp4").write_bytes(b"mp4-bytes")
        _write_idea(
            root,
            "003-borek.md",
            "# Borek\n\n![](assets/003-image.jpg)\n",
        )
        _write_idea(
            root,
            "004-lifeguard.md",
            "# Lifeguard\n\n[Video](assets/004-video.mp4)\n",
        )
        self.assertEqual(migrate.apply_migration(root), 0)
        self.assertEqual(migrate.verify_migration(root), 0)
        self.assertIn(
            "![](../assets/003-image.jpg)",
            (root / "ideas" / "003-borek.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "[Video](../assets/004-video.mp4)",
            (root / "ideas" / "004-lifeguard.md").read_text(encoding="utf-8"),
        )

    def test_collision_same_rewrites_markdown_without_changing_dest_bytes(self) -> None:
        root = _kb()
        payload = b"same-bytes"
        (root / "ideas" / "assets" / "003-image.jpg").write_bytes(payload)
        dest = root / "assets" / "003-image.jpg"
        dest.write_bytes(payload)
        idea = _write_idea(
            root,
            "003-borek.md",
            "# Borek\n\n![](assets/003-image.jpg)\n",
        )
        self.assertEqual(migrate.apply_migration(root), 0)
        self.assertEqual(dest.read_bytes(), payload)
        self.assertIn("](../assets/003-image.jpg)", idea.read_text(encoding="utf-8"))

    def test_inventory_writes_nothing(self) -> None:
        root = _kb()
        (root / "ideas" / "assets" / "003-image.jpg").write_bytes(b"jpeg-bytes")
        idea = _write_idea(
            root,
            "003-borek.md",
            "# Borek\n\n![](assets/003-image.jpg)\n",
        )
        before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
        migrate.build_inventory(root)
        after = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(idea.exists())


if __name__ == "__main__":
    unittest.main()
