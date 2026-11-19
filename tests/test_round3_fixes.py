"""Regression tests for bugs and quality gaps uncovered in Round 3 Hydrogen benchmark."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from click.testing import CliRunner

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"
if str(BENCHMARKS_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS_DIR))

from eval_naturalness import STYLE_CATEGORIES, load_samples, style_findings  # noqa: E402
from tarjoman.cli import cli  # noqa: E402
from tarjoman.fixer import fix_text  # noqa: E402
from tarjoman.linter import (  # noqa: E402
    VALID_STYLES,
    find_hekasre,
    lint_json_text,
    lint_text,
)
from tarjoman.memory.fidelity import check_fidelity  # noqa: E402
from tarjoman.parsers.i18n import check_i18n  # noqa: E402
from tarjoman.stages.stage4_polish import StylisticPolishStage  # noqa: E402


@contextmanager
def _temp_cwd() -> Iterator[Path]:
    prev = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        os.chdir(tmp_path)
        try:
            yield tmp_path
        finally:
            os.chdir(prev)


class TestRound3LinterAndFidelityFixes(unittest.TestCase):
    def test_persian_digits_not_flagged_as_ascii_while_ascii_caught(self) -> None:
        clean_persian = "ساعت ۶:۱۵ در پاییز ۱۹۸۷ کنار دروازه‌ی شرقی بودیم."
        for style in ("literary", "mystery", "memoir", "speculative"):
            issues = lint_text(clean_persian, style=style)
            digit_issues = [i for i in issues if i.category == "digits"]
            self.assertEqual(digit_issues, [], f"{style}: {digit_issues}")

        ascii_in_literary = "ساعت 6:15 در پاییز 1987 کنار دروازه‌ی شرقی بودیم."
        flagged = [i for i in lint_text(ascii_in_literary, style="literary") if i.category == "digits"]
        self.assertGreaterEqual(len(flagged), 1)

    def test_percentage_plus_word_not_matched_as_printf_placeholder(self) -> None:
        src = "Margins narrowed to 18.6% due to capex, yet grants +12% frost resistance and kept %(user)s %02d %.1f."
        tgt_ok = "حاشیه سود به ۱۸٫۶ درصد رسید و ۱۲٪+ مقاومت در برابر یخبندان می‌دهد برای %(user)s با %02d و %.1f."
        findings = [f for f in check_fidelity(src, tgt_ok) if f.category == "placeholder"]
        self.assertEqual(findings, [])

        tgt_missing = "حاشیه سود به ۱۸٫۶ درصد رسید و ۱۲٪+ مقاومت می‌دهد."
        missing = [f for f in check_fidelity(src, tgt_missing) if f.category == "placeholder"]
        self.assertEqual(len(missing), 1)
        self.assertNotIn("% d", missing[0].message)
        self.assertNotIn("% f", missing[0].message)
        self.assertIn("%(user)s", missing[0].message)

        with _temp_cwd() as tmp:
            en_p = tmp / "en.json"
            fa_p = tmp / "fa.json"
            en_p.write_text(
                json.dumps({"a": "Grants +12% frost resistance.", "b": "Down 18.6% due to fees.", "c": "Level %d"}),
                encoding="utf-8",
            )
            fa_p.write_text(
                json.dumps({"a": "۱۲٪+ مقاومت در برابر یخبندان می‌دهد.", "b": "۱۸٫۶ درصد کاهش یافت.", "c": "سطح %d"}),
                encoding="utf-8",
            )
            self.assertEqual(check_i18n(en_p, fa_p), [])

            fa_p.write_text(
                json.dumps({"a": "۱۲٪+ مقاومت می‌دهد.", "b": "۱۸٫۶ درصد کاهش یافت.", "c": "سطح"}),
                encoding="utf-8",
            )
            i18n_bad = check_i18n(en_p, fa_p)
            self.assertEqual(len(i18n_bad), 1)
            self.assertEqual(i18n_bad[0].key, "c")

    def test_all_22_routed_styles_supported_programmatically_and_via_cli(self) -> None:
        self.assertGreaterEqual(len(VALID_STYLES), 22)
        for style in VALID_STYLES:
            self.assertEqual(lint_text("سلام، این یک متن تمیز است.", style=style), [], style)

        with _temp_cwd() as tmp:
            sample_md = tmp / "sample.md"
            sample_md.write_text("در باز بود و باران می‌بارید.\n", encoding="utf-8")
            runner = CliRunner()
            for style in ("mystery", "philosophy", "transcreation", "memoir", "game"):
                res = runner.invoke(cli, ["lint", str(sample_md), "--style", style, "--json"])
                self.assertEqual(res.exit_code, 0, f"{style}: {res.output}")

    def test_json_linting_ignores_syntax_and_catches_real_value_defects(self) -> None:
        clean_json = json.dumps(
            {
                "@metadata": {"author": "should be skipped"},
                "hud_hp_low": "<color=#ff4444>هشدار: جان کم است!</color> همین حالا بانداژ بزن.",
                "toast_gold_short": "نقره‌ی کافی برای {item} نداری.",
            },
            ensure_ascii=False,
            indent=2,
        )
        self.assertEqual(lint_json_text(clean_json, style="game"), [])

        bad_json = json.dumps(
            {
                "ok": "همه‌چیز خوب است.",
                "bad": "كتاب خوب — ارزش خواندن دارد.",
            },
            ensure_ascii=False,
            indent=2,
        )
        issues = lint_json_text(bad_json, style="game")
        cats = {i.category for i in issues}
        self.assertIn("em-dash", cats)
        self.assertIn("arabic", cats)
        self.assertTrue(all(i.line_number >= 3 and i.snippet.startswith("[bad]") for i in issues))

        with _temp_cwd() as tmp:
            jpath = tmp / "ui.json"
            jpath.write_text(clean_json, encoding="utf-8")
            res = CliRunner().invoke(cli, ["lint", str(jpath), "--style", "game", "--json"])
            self.assertEqual(res.exit_code, 0, res.output)

    def test_colloquial_3sg_verbs_not_flagged_as_hekasre(self) -> None:
        self.assertEqual(find_hekasre("ساعت کاری نداره شما چقدر عجله دارید."), [])
        self.assertEqual(find_hekasre("بگو داره من رو می‌بینه و بگه تو کجایی."), [])
        self.assertTrue(find_hekasre("کتابه من کجاست؟"))

    def test_round3_skill_outputs_pass_all_fixed_checks(self) -> None:
        r3 = PROJECT_ROOT / "docs" / "research" / "real-texts" / "round3"
        cases = [
            ("literary", "literary.en.md", "literary.skill.md"),
            ("mystery", "mystery.en.md", "mystery.skill.md"),
            ("scientific", "scientific.en.md", "scientific.skill.md"),
            ("philosophy", "philosophy.en.md", "philosophy.skill.md"),
            ("financial", "financial.en.md", "financial.skill.md"),
            ("transcreation", "transcreation.en.md", "transcreation.skill.md"),
            ("game", "game.en.json", "game.skill.json"),
            ("memoir", "memoir.en.md", "memoir.skill.md"),
        ]
        for style, src_name, tgt_name in cases:
            src_path = r3 / src_name
            tgt_path = r3 / tgt_name
            tgt_text = tgt_path.read_text(encoding="utf-8")
            if tgt_path.suffix == ".json":
                issues = lint_json_text(tgt_text, style=style)
                self.assertEqual(check_i18n(src_path, tgt_path), [], tgt_name)
            else:
                issues = lint_text(tgt_text, style=style)
            self.assertEqual(issues, [], f"{tgt_name}: {issues}")
            self.assertEqual(check_fidelity(src_path.read_text(encoding="utf-8"), tgt_text), [], tgt_name)


class TestRound3GuidesAndEvalHarvest(unittest.TestCase):
    def test_guides_include_round3_improvements(self) -> None:
        refs = PROJECT_ROOT / ".claude" / "skills" / "tarjoman" / "references"
        fid = (refs / "fidelity.md").read_text(encoding="utf-8")
        self.assertIn("neither A nor B", fid)
        self.assertNotIn("\u2014", fid)
        self.assertNotIn("\u2013", fid)

        mys = (refs / "mystery.md").read_text(encoding="utf-8")
        self.assertIn("بازجویی رسمی امروزی", mys)
        sci = (refs / "scientific.md").read_text(encoding="utf-8")
        self.assertIn("پرانتز انگلیسی", sci)
        trn = (refs / "transcreation.md").read_text(encoding="utf-8")
        self.assertIn("tarjoman verify", trn)
        game = (refs / "game.md").read_text(encoding="utf-8")
        self.assertIn("تقصیرشو", game)

    def test_round3_harvested_samples_and_negatives(self) -> None:
        samples = load_samples(PROJECT_ROOT / "docs" / "research" / "eval-set" / "samples.jsonl")
        by_id = {s["id"]: s for s in samples}
        for sid in ("real-r3-sci", "real-r3-phil", "real-r3-mkt", "real-r3-mem"):
            self.assertIn(sid, by_id)
            self.assertEqual(style_findings(by_id[sid]["natural"], STYLE_CATEGORIES), 0, sid)
            self.assertGreater(style_findings(by_id[sid]["literal"], STYLE_CATEGORIES), 0, sid)
        for nid in ("neg-29", "neg-30"):
            self.assertIn(nid, by_id)
            txt = by_id[nid]["natural"]
            self.assertEqual(StylisticPolishStage.polish(txt), txt, nid)
            self.assertEqual(fix_text(txt).text, txt, nid)


if __name__ == "__main__":
    unittest.main()
