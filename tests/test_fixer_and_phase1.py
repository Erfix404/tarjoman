"""Tests for Phase 1: safe orthography auto-fixer, style/severity linting, and CLI --json."""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Iterator

from click.testing import CliRunner

from tarjoman.cli import cli
from tarjoman.fixer import fix_text
from tarjoman.linter import format_json_report, lint_text
from tests.test_no_false_rewrites import CORRECT_SENTENCES

ROOT = Path(__file__).resolve().parent.parent


@contextlib.contextmanager
def _temp_cwd() -> Iterator[Path]:
    prev = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield Path(tmp)
        finally:
            os.chdir(prev)


class TestSafeFixer(unittest.TestCase):
    def test_arabic_tatweel_and_fake_zwnj(self) -> None:
        raw = "كتاب عربي بـا نام\u200bهای متفاوت"
        res = fix_text(raw)
        self.assertTrue(res.changed)
        self.assertEqual(res.text, "کتاب عربی با نام\u200cهای متفاوت")
        self.assertGreater(res.counts.get("arabic", 0), 0)
        self.assertEqual(res.counts.get("fake-zwnj"), 1)

    def test_zwnj_rules_and_non_verb_preservation(self) -> None:
        raw = "من می دانم و الان میدونم که این کتاب ها بزرگ ترین میز و میوه در خانه ای هست."
        res = fix_text(raw)
        self.assertEqual(
            res.text,
            "من می\u200cدانم و الان می\u200cدونم که این کتاب\u200cها بزرگ\u200cترین میز و میوه در خانه\u200cای هست.",
        )

    def test_tanvin_spelling_and_punctuation(self) -> None:
        raw = "لطفا گاهاً به این اثرگزار توجه کنید , نرخ ۹.۵ درصد شد ? « سلام » ( خوب ) ."
        res = fix_text(raw)
        self.assertEqual(
            res.text,
            "لطفاً گاهی به این اثرگذار توجه کنید، نرخ ۹٫۵ درصد شد؟ «سلام» (خوب).",
        )

    def test_verbatim_spans_preserved_byte_identical(self) -> None:
        raw = (
            "متن `my_var , ي ك` و {count} و {{user}} و %(name)s\n"
            "لینک https://example.com/a?x=1&y=2 ایمیل test.user@example.org\n"
            "<span data-k=\"ي\">متن</span> و فرمول $x + y = 1.5$ و \\cite{key_2026}\n"
            "```python\n"
            "# ك ي می دانم , ? 1.5\n"
            "x = 'لطفا'\n"
            "```\n"
        )
        res = fix_text(raw)
        self.assertFalse(res.changed)
        self.assertEqual(res.text, raw)

    def test_never_rewrites_semantic_rules_or_em_dash_or_hekasre(self) -> None:
        samples = (
            "این کتاب توسط علی نوشته شد.",
            "این موضوع از اهمیت بالایی برخوردار است.",
            "جمله — با خط تیره.",
            'او گفت: "سلام".',
            "کتابه من کجاست؟",
        )
        for sample in samples:
            res = fix_text(sample)
            self.assertFalse(res.changed, sample)
            self.assertEqual(res.text, sample)

    def test_idempotency(self) -> None:
        raw = "لطفا كتاب ها را می خوانم , و بزرگ ترین اثرگزار « خوب » ."
        first = fix_text(raw)
        second = fix_text(first.text)
        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(first.text, second.text)

    def test_zero_false_rewrites_on_clean_and_eval_corpora(self) -> None:
        for sentence in CORRECT_SENTENCES:
            self.assertEqual(fix_text(sentence).text, sentence, sentence)

        with open(ROOT / "docs/research/eval-set/samples.jsonl", encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if row.get("type") == "negative":
                    self.assertEqual(fix_text(row["natural"]).text, row["natural"], row["id"])

        for rel in (
            "docs/research/improvement-eval-samples.jsonl",
            "docs/research/naturalize-eval-samples.jsonl",
        ):
            with open(ROOT / rel, encoding="utf-8") as f:
                for line in f:
                    row = json.loads(line)
                    self.assertEqual(fix_text(row["after"]).text, row["after"], row["id"])


class TestFixCli(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_fix_dry_run_in_place_output_and_json(self) -> None:
        with _temp_cwd():
            src = Path("sample.md")
            src.write_text("لطفا كتاب را می خوانم ,", encoding="utf-8")

            dry = self.runner.invoke(cli, ["fix", str(src), "--dry-run", "--json"])
            self.assertEqual(dry.exit_code, 1)
            dry_data = json.loads(dry.output)
            self.assertTrue(dry_data["changed"])
            self.assertEqual(src.read_text(encoding="utf-8"), "لطفا كتاب را می خوانم ,")

            out_file = Path("fixed.md")
            out_res = self.runner.invoke(cli, ["fix", str(src), "-o", str(out_file)])
            self.assertEqual(out_res.exit_code, 0)
            self.assertEqual(out_file.read_text(encoding="utf-8"), "لطفاً کتاب را می‌خوانم،")

            in_place = self.runner.invoke(cli, ["fix", str(src), "-i", "--json"])
            self.assertEqual(in_place.exit_code, 0)
            self.assertEqual(src.read_text(encoding="utf-8"), "لطفاً کتاب را می‌خوانم،")

            clean_dry = self.runner.invoke(cli, ["fix", str(src), "--dry-run"])
            self.assertEqual(clean_dry.exit_code, 0)

    def test_fix_stdout_and_mutual_exclusion(self) -> None:
        with _temp_cwd():
            src = Path("note.md")
            src.write_text("لطفا سلام", encoding="utf-8")

            stdout_json = self.runner.invoke(cli, ["fix", str(src), "--json"])
            self.assertEqual(stdout_json.exit_code, 0)
            payload = json.loads(stdout_json.output)
            self.assertEqual(payload["text"], "لطفاً سلام")

            bad = self.runner.invoke(cli, ["fix", str(src), "-i", "-o", "out.md"])
            self.assertNotEqual(bad.exit_code, 0)


class TestStyleAndJsonLinter(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_severity_and_errors_only(self) -> None:
        suggestion_only = "این کار توسط تیم انجام شد."
        issues = lint_text(suggestion_only)
        self.assertTrue(all(i.severity == "suggestion" for i in issues))

        with _temp_cwd():
            f = Path("calque.md")
            f.write_text(suggestion_only, encoding="utf-8")
            res_all = self.runner.invoke(cli, ["lint", str(f), "--json"])
            self.assertEqual(res_all.exit_code, 1)
            data = json.loads(res_all.output)
            self.assertEqual(data["errors"], 0)
            self.assertGreaterEqual(data["suggestions"], 1)

            res_err = self.runner.invoke(cli, ["lint", str(f), "--errors-only", "--json"])
            self.assertEqual(res_err.exit_code, 0)
            err_data = json.loads(res_err.output)
            self.assertTrue(err_data["passed"])

            bad = Path("arabic.md")
            bad.write_text("كتاب عربي", encoding="utf-8")
            res_bad = self.runner.invoke(cli, ["lint", str(bad), "--errors-only"])
            self.assertEqual(res_bad.exit_code, 1)

    def test_style_modes(self) -> None:
        with self.assertRaises(ValueError):
            lint_text("سلام", style="unknown")

        col_issues = lint_text("می‌خواهم بروم.", style="colloquial")
        self.assertIn("register", {i.category for i in col_issues})

        formal_issues = lint_text("می‌خوام برم.", style="formal")
        self.assertIn("register", {i.category for i in formal_issues})

        lit_text = "او گفت: «می‌خوام برم.» و از در بیرون رفت تا 12 دقیقه منتظر بماند."
        lit_issues = lint_text(lit_text, style="literary")
        lit_cats = {i.category for i in lit_issues}
        self.assertNotIn("register", lit_cats)
        self.assertIn("digits", lit_cats)

        lit_narration = lint_text("او می‌خوام گفت و رفت.", style="literary")
        self.assertIn("register", {i.category for i in lit_narration})

        tech_issues = lint_text("یک کاربر باید صبر کند.", style="technical")
        self.assertNotIn("generic-article", {i.category for i in tech_issues})

        poetry_issues = lint_text("باد می‌وزد — آرام", style="poetry")
        em_issues = [i for i in poetry_issues if i.category == "em-dash"]
        self.assertTrue(em_issues)
        self.assertTrue(all(i.severity == "suggestion" for i in em_issues))

        # Direct helper check
        formatted = format_json_report("demo.md", poetry_issues)
        self.assertFalse(json.loads(formatted)["passed"])


class TestJsonReportsForCheckCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_verify_srt_check_and_book_check_json(self) -> None:
        with _temp_cwd():
            src = Path("en.md")
            tgt = Path("fa.md")
            src.write_text("Year 2026.", encoding="utf-8")
            tgt.write_text("سال ۲۰۲۶.", encoding="utf-8")
            ok_v = self.runner.invoke(cli, ["verify", str(src), str(tgt), "--json"])
            self.assertEqual(ok_v.exit_code, 0)
            self.assertTrue(json.loads(ok_v.output)["passed"])

            tgt_bad = Path("fa_bad.md")
            tgt_bad.write_text("امسال.", encoding="utf-8")
            bad_v = self.runner.invoke(cli, ["verify", str(src), str(tgt_bad), "--json"])
            self.assertEqual(bad_v.exit_code, 1)
            self.assertFalse(json.loads(bad_v.output)["passed"])

            srt_en = Path("en.srt")
            srt_fa = Path("fa.srt")
            srt_en.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello.\n", encoding="utf-8")
            srt_fa.write_text("1\n00:00:01,000 --> 00:00:03,000\nسلام.\n", encoding="utf-8")
            srt_ok = self.runner.invoke(
                cli, ["srt", "check", str(srt_fa), "--source", str(srt_en), "--json"]
            )
            self.assertEqual(srt_ok.exit_code, 0)
            self.assertTrue(json.loads(srt_ok.output)["passed"])

            proj = Path("bookproj")
            self.runner.invoke(cli, ["book", "init", "Test", "-o", str(proj)])
            self.runner.invoke(cli, ["book", "terms", str(proj), "--add", "Year=سال"])
            book_ok = self.runner.invoke(
                cli, ["book", "check", str(proj), str(src), str(tgt), "--json"]
            )
            self.assertEqual(book_ok.exit_code, 0)
            self.assertTrue(json.loads(book_ok.output)["passed"])

            book_bad = self.runner.invoke(
                cli, ["book", "check", str(proj), str(src), str(tgt_bad), "--json"]
            )
            self.assertEqual(book_bad.exit_code, 1)
            self.assertFalse(json.loads(book_bad.output)["passed"])


if __name__ == "__main__":
    unittest.main()
