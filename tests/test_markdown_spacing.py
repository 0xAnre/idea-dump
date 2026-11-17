import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("OPENROUTER_MODEL", "test-model")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main

IDEA = '''---
id: "083"
title: Ideas vs. Execution
type: idea
created: 2026-11-17
source: telegram
tags:
  - execution
---
# Ideas vs. Execution

Ideas are cheap. Execution changes everything.

## Source

> Ideas are cheap. Execution changes everything.
'''

TOPIC_ITEM = "- [Product Development](../topics/product-development.md)"
TOPIC_TARGET = "../topics/product-development.md"
RELATED_ITEM = "- [Ship Fast, Learn Fast](080-ship-fast-learn-fast.md)"
RELATED_TARGET = "080-ship-fast-learn-fast.md"


class AppendedSectionSpacingTests(unittest.TestCase):
    def _with_sections(self) -> str:
        text = main._append_list_item(IDEA, "## Topics", TOPIC_ITEM, TOPIC_TARGET)
        return main._append_list_item(
            text, "## Related Ideas", RELATED_ITEM, RELATED_TARGET
        )

    def test_sections_are_separated_by_one_blank_line(self) -> None:
        text = self._with_sections()

        self.assertNotIn("\n\n\n", text)
        self.assertTrue(text[: text.index("## Topics")].endswith("\n\n"))
        self.assertTrue(text[: text.index("## Related Ideas")].endswith("\n\n"))
        self.assertTrue(text[: text.index("## Source")].endswith("\n\n"))

    def test_section_order_is_topics_then_related_then_source(self) -> None:
        text = self._with_sections()

        self.assertLess(text.index("## Topics"), text.index("## Related Ideas"))
        self.assertLess(text.index("## Related Ideas"), text.index("## Source"))

    def test_existing_blank_lines_before_source_are_collapsed(self) -> None:
        text = IDEA.replace("everything.\n\n## Source", "everything.\n\n\n\n## Source")
        text = main._append_list_item(text, "## Topics", TOPIC_ITEM, TOPIC_TARGET)

        self.assertNotIn("\n\n\n", text)
        self.assertTrue(text[: text.index("## Topics")].endswith("\n\n"))

    def test_source_block_is_untouched(self) -> None:
        text = self._with_sections()

        self.assertEqual(
            main.recover_source_from_idea(text),
            "Ideas are cheap. Execution changes everything.",
        )

    def test_adding_the_same_item_twice_keeps_one_entry(self) -> None:
        text = main._append_list_item(IDEA, "## Topics", TOPIC_ITEM, TOPIC_TARGET)
        twice = main._append_list_item(text, "## Topics", TOPIC_ITEM, TOPIC_TARGET)

        self.assertEqual(twice.count("## Topics"), 1)
        self.assertEqual(twice.count(TOPIC_ITEM), 1)


if __name__ == "__main__":
    unittest.main()
