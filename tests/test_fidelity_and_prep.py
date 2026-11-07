"""Tests for the fidelity check (verify), PDF text prep, and new lint rules."""
from __future__ import annotations

import os
import tempfile
import unittest

from click.testing import CliRunner

from tarjoman.cli import cli
from tarjoman.linter import lint_text
from tarjoman.memory.fidelity import check_fidelity, split_paragraphs
from tarjoman.parsers.text_prep import prepare_text

LONG = "A long paragraph about many things that keeps going for a while, so the length check has text to measure."


class TestFidelity(unittest.TestCase):
    def test_faithful_translation_passes(self) -> None:
        src = "He paid $1,250 on 12 May 2024 [3].\n\nSee https://example.com and run `pip install x`."
        tgt = "او در ۱۲ مه ۲۰۲۴ مبلغ ۱٬۲۵۰ دلار پرداخت کرد [۳].\n\nبه https://example.com سر بزنید و `pip install x` را اجرا کنید."
        self.assertEqual(check_fidelity(src, tgt), [])

    def test_missing_number(self) -> None:
        cats = [f.category for f in check_fidelity("It costs 450 dollars.", "گران است.")]
        self.assertIn("number", cats)

    def test_single_digit_words_ok(self) -> None:
        self.assertEqual(check_fidelity("She had 3 cats.", "سه گربه داشت."), [])

    def test_decimal_with_persian_separator(self) -> None:
        self.assertEqual(check_fidelity("Growth was 2.5 percent.", "رشد ۲٫۵ درصد بود."), [])

    def test_dropped_paragraph(self) -> None:
        cats = [f.category for f in check_fidelity("One.\n\nTwo.", "یک.")]
        self.assertIn("paragraphs", cats)

    def test_summarized_paragraph(self) -> None:
        findings = check_fidelity(LONG * 2, "خلاصه.")
        self.assertEqual([f.category for f in findings], ["length"])

    def test_missing_citation_url_code(self) -> None:
        src = "See [12] and https://a.org, then `make`.\n\n```\nx = 1\n```"
        tgt = "ببینید و بعد make را اجرا کنید.\n\n```\nx = 2\n```"
        cats = {f.category for f in check_fidelity(src, tgt)}
        self.assertTrue({"citation", "url", "code"} <= cats)

    def test_code_block_is_one_paragraph(self) -> None:
        self.assertEqual(len(split_paragraphs("a\n\n```\nx\n\ny\n```\n\nb")), 3)

    def test_verify_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            src, tgt = os.path.join(tmp, "s.md"), os.path.join(tmp, "t.md")
            with open(src, "w", encoding="utf-8") as f:
                f.write("Version 12 shipped.")
            with open(tgt, "w", encoding="utf-8") as f:
                f.write("نسخه‌ی ۱۲ منتشر شد.")
            ok = runner.invoke(cli, ["verify", src, tgt])
            self.assertEqual(ok.exit_code, 0, ok.output)
            with open(tgt, "w", encoding="utf-8") as f:
                f.write("نسخه‌ی جدید منتشر شد.")
            bad = runner.invoke(cli, ["verify", src, tgt])
            self.assertEqual(bad.exit_code, 1)
            self.assertIn("[number]", bad.output)


class TestTextPrep(unittest.TestCase):
    PDF = (
        "THE LONG ROAD\nThe first para-\ngraph goes on\nand on.\n\nSecond one starts\n12\n"
        "\fTHE LONG ROAD\nhere and ends.\n\nThird.\n13\n"
        "\fTHE LONG ROAD\nFourth para.\n14\n\f"
    )

    def test_headers_page_numbers_hyphens_wraps(self) -> None:
        clean, report = prepare_text(self.PDF)
        self.assertEqual(
            clean,
            "The first paragraph goes on and on.\n\nSecond one starts here and ends.\n\nThird.\n\nFourth para.\n",
        )
        self.assertEqual(report.removed_headers, {"THE LONG ROAD": 3})
        self.assertEqual(report.removed_page_numbers, 3)
        self.assertEqual(report.rejoined_hyphens, 1)

    def test_no_page_breaks_keeps_numbers_and_lists(self) -> None:
        text = "# Title\n\n- one\n- two\n\nChapter\n3\n"
        clean, report = prepare_text(text)
        self.assertIn("- one\n- two", clean)
        self.assertIn("3", clean)
        self.assertEqual(report.removed_page_numbers, 0)

    def test_code_block_untouched(self) -> None:
        text = "Intro line\nwrapped.\n\n```\nfoo(a-\nb)\nbar\n```\n"
        clean, _ = prepare_text(text)
        self.assertIn("```\nfoo(a-\nb)\nbar\n```", clean)

    def test_keep_lines(self) -> None:
        clean, report = prepare_text("line one\nline two\n", unwrap=False)
        self.assertEqual(clean, "line one\nline two\n")
        self.assertEqual(report.joined_lines, 0)

    def test_prep_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            src, out = os.path.join(tmp, "book.txt"), os.path.join(tmp, "clean.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write(self.PDF)
            result = runner.invoke(cli, ["prep", src, "-o", out])
            self.assertEqual(result.exit_code, 0, result.output)
            with open(out, encoding="utf-8") as f:
                self.assertNotIn("THE LONG ROAD", f.read())


class TestNewLintRules(unittest.TestCase):
    def _cats(self, text: str) -> list:
        return [i.category for i in lint_text(text)]

    def test_space_before_punctuation(self) -> None:
        self.assertIn("punct-space", self._cats("به راهرو نگاه کرد ، اما چیزی ندید ."))
        self.assertIn("punct-space", self._cats("گفت: « سلام »"))
        self.assertIn("punct-space", self._cats("در ( هاگوارتز ) ماند."))

    def test_correct_punctuation_not_flagged(self) -> None:
        for text in ["به راهرو نگاه کرد، اما چیزی ندید.", "گفت: «سلام!» و رفت.", "بله ...", "مقدار `a , b` است."]:
            self.assertNotIn("punct-space", self._cats(text), text)

    def test_new_ai_tells(self) -> None:
        for text in [
            "حقیقت این است که کسی نیامد.",
            "کارشناسان معتقدند خواب مهم است.",
            "اما سؤال اصلی چیست؟",
            "این تازه آغاز راه است.",
            "فرصت را از دست ندهید!",
            "همان‌طور که مشاهده می‌کنید، نتیجه خوب است.",
            "نکته‌ای که اغلب نادیده گرفته می‌شود، خواب است.",
        ]:
            self.assertIn("ai-tell", self._cats(text), text)

    def test_new_ai_tells_no_false_alarm(self) -> None:
        for text in ["حقیقت را گفت. جوابش ساده نبود.", "نکته‌ای که دیروز گفتی درست بود.", "این آغاز فصل دوم است."]:
            self.assertNotIn("ai-tell", self._cats(text), text)


if __name__ == "__main__":
    unittest.main()
