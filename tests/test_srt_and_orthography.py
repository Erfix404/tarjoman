"""Tests for the SRT check and the orthography lint rules (spelling, zwnj, punct)."""
from __future__ import annotations

import os
import tempfile
import unittest

from click.testing import CliRunner

from tarjoman.cli import cli
from tarjoman.linter import lint_text
from tarjoman.parsers.srt import check_srt, parse_srt

SRC = (
    "1\n00:00:01,000 --> 00:00:03,000\nHit snooze.\n\n"
    "2\n00:00:03,500 --> 00:00:06,500\nMelatonin matters.\n\n"
    "3\n00:00:07,000 --> 00:00:09,000\nOK then.\n"
)
GOOD = (
    "1\n00:00:01,000 --> 00:00:03,000\nدکمه‌ی چرت رو بزن.\n\n"
    "2\n00:00:03,500 --> 00:00:06,500\nملاتونین مهمه.\n\n"
    "3\n00:00:07,000 --> 00:00:09,000\nباشه پس.\n"
)


class TestSrt(unittest.TestCase):
    def test_parse(self) -> None:
        cues = parse_srt("﻿" + SRC.replace("\n", "\r\n"))
        self.assertEqual([c.index for c in cues], ["1", "2", "3"])
        self.assertEqual(cues[0].start_ms, 1000)
        self.assertEqual(cues[1].lines, ["Melatonin matters."])

    def test_good_translation_passes(self) -> None:
        self.assertEqual(check_srt(SRC, GOOD), [])

    def test_cue_count_and_timing(self) -> None:
        merged = GOOD.replace("\n\n3\n00:00:07,000 --> 00:00:09,000\nباشه پس.\n", "\n")
        self.assertIn("cues", [f.category for f in check_srt(SRC, merged)])
        shifted = GOOD.replace("00:00:03,500", "00:00:03,600")
        self.assertIn("cues", [f.category for f in check_srt(SRC, shifted)])

    def test_length_lines_speed(self) -> None:
        long = GOOD.replace("ملاتونین مهمه.", "ملاتونین اینجا خیلی خیلی خیلی مهمه، واقعاً واقعاً مهمه.\nخط دوم\nخط سوم")
        cats = {f.category for f in check_srt(SRC, long)}
        self.assertTrue({"length", "lines", "speed"} <= cats)

    def test_residue_and_untranslated(self) -> None:
        bad = GOOD.replace("ملاتونین مهمه.", "ترجمه: ملاتونین مهمه.").replace("باشه پس.", "OK then.")
        cats = {f.category for f in check_srt(SRC, bad)}
        self.assertTrue({"residue", "untranslated"} <= cats)

    def test_zwnj_not_counted_as_char(self) -> None:
        line = "می‌" * 14  # 28 visible letters, 14 ZWNJs
        srt = f"1\n00:00:00,000 --> 00:00:05,000\n{line}\n"
        self.assertEqual(check_srt(None, srt), [])

    def test_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            src, tgt = os.path.join(tmp, "en.srt"), os.path.join(tmp, "fa.srt")
            with open(src, "w", encoding="utf-8") as f:
                f.write(SRC)
            with open(tgt, "w", encoding="utf-8") as f:
                f.write(GOOD)
            ok = runner.invoke(cli, ["srt", "check", tgt, "--source", src])
            self.assertEqual(ok.exit_code, 0, ok.output)
            with open(tgt, "w", encoding="utf-8") as f:
                f.write(GOOD.replace("باشه پس.", "OK then."))
            bad = runner.invoke(cli, ["srt", "check", tgt, "--source", src])
            self.assertEqual(bad.exit_code, 1)
            self.assertIn("[untranslated]", bad.output)


class TestOrthographyLint(unittest.TestCase):
    def _cats(self, text: str) -> list:
        return [i.category for i in lint_text(text)]

    def test_flags(self) -> None:
        cases = {
            "این روش اثرگزاری زیادی دارد.": "spelling",
            "کتاب را روی میز گزاشت.": "spelling",
            "کتاب ها را آوردم.": "zwnj",
            "بزرگ ترین خانه بود.": "zwnj",
            "می​روم": "fake-zwnj",
            "چرا رفتی?": "punct",
            "واقعاً؟؟": "punct",
            "سیب, پرتقال و موز": "punct",
        }
        for text, cat in cases.items():
            self.assertIn(cat, self._cats(text), text)

    def test_no_false_alarms(self) -> None:
        for text in [
            "گزارش را نوشت و سپاسگزار بود.",
            "خدمتگزار و نمازگزار و برگزار",
            "لباس تر شد.",
            "کتاب‌ها و بزرگ‌ترین دفترها",
            "عدد 1,250 است.",
            "مقدار `a, b?` درست است.",
            "گذاشت و رفت.",
        ]:
            cats = self._cats(text)
            for cat in ("spelling", "zwnj", "fake-zwnj", "punct"):
                self.assertNotIn(cat, cats, f"{text}: {cat}")


if __name__ == "__main__":
    unittest.main()
