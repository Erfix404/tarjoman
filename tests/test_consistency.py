"""Tests for cross-chapter consistency checks (book projects)."""
from __future__ import annotations

import os
import tempfile
import unittest

from click.testing import CliRunner

from tarjoman.cli import cli
from tarjoman.memory.consistency import (
    check_characters,
    check_chapter,
    check_register_mix,
    check_terms,
)


class TestConsistencyChecks(unittest.TestCase):
    def test_missing_term_reported(self) -> None:
        findings = check_terms("He raised his wand.", "چوبش را بالا برد.", {"wand": "چوب‌دستی"})
        self.assertEqual([f.category for f in findings], ["term"])

    def test_present_term_ok(self) -> None:
        self.assertEqual(
            check_terms("He raised his wand.", "چوب‌دستی‌اش را بالا برد.", {"wand": "چوب‌دستی"}), []
        )

    def test_unused_term_ignored(self) -> None:
        self.assertEqual(check_terms("Hello.", "سلام.", {"wand": "چوب‌دستی"}), [])

    def test_missing_character_name(self) -> None:
        findings = check_characters("Siobhan left.", "شیوان رفت.", [("Siobhan", "سیوبان")])
        self.assertEqual(len(findings), 1)

    def test_register_mix_in_dialogue(self) -> None:
        text = "گفت: «می‌خواهم بروم.» بعد گفت: «می‌خوام بمونم.»"
        self.assertEqual(len(check_register_mix(text)), 1)

    def test_consistent_colloquial_ok(self) -> None:
        text = "گفت: «می‌خوام برم.» بعد گفت: «نمی‌دونم.»"
        self.assertEqual(check_register_mix(text), [])

    def test_narration_not_counted(self) -> None:
        # Standard verbs in narration plus colloquial dialogue is the intended style.
        text = "می‌خواهد برود. گفت: «می‌خوام برم.»"
        self.assertEqual(check_register_mix(text), [])

    def test_clean_chapter(self) -> None:
        self.assertEqual(
            check_chapter(
                "Harry raised his wand.",
                "هری چوب‌دستی‌اش را بالا برد.",
                {"wand": "چوب‌دستی"},
                [("Harry", "هری")],
            ),
            [],
        )


class TestBookCli(unittest.TestCase):
    def test_init_creates_style_sheet_and_check_runs(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, "proj")
            self.assertEqual(runner.invoke(cli, ["book", "init", "T", "-o", proj]).exit_code, 0)
            self.assertTrue(os.path.exists(os.path.join(proj, "style.md")))
            runner.invoke(cli, ["book", "terms", proj, "--add", "wand=چوب‌دستی"])
            src = os.path.join(tmp, "src.txt")
            tgt = os.path.join(tmp, "tgt.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("He raised his wand.")
            with open(tgt, "w", encoding="utf-8") as f:
                f.write("چوبش را بالا برد.")
            result = runner.invoke(cli, ["book", "check", proj, src, tgt])
            self.assertEqual(result.exit_code, 1)
            self.assertIn("[term]", result.output)


if __name__ == "__main__":
    unittest.main()


class TestTermUpdateCli(unittest.TestCase):
    def test_re_adding_term_reports_old_value(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, "proj")
            runner.invoke(cli, ["book", "init", "T", "-o", proj])
            runner.invoke(cli, ["book", "terms", proj, "--add", "wand=چوب‌دستی"])
            result = runner.invoke(cli, ["book", "terms", proj, "--add", "wand=چوب جادو"])
            self.assertIn("was: چوب‌دستی", result.output)
