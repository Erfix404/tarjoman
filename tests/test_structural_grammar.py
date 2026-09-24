"""Tests for TRN-013: Structural Grammar, Ezafe Chain Smoothing (v2.2.0).

Covers:
- StylisticPolishStage.smooth_ezafe_chains (3+ smoothing, 1-2 preservation,
  verbatim spans, edge cases) + polish() integration
- STRUCTURAL_GRAMMAR_PROMPT / NeutralLinguisticFraming NP + a/an guidance
- Linter categories ezafe-chain + generic-article (package + skill script)
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest

from tarjoman import linter
from tarjoman.stages.draft import STRUCTURAL_GRAMMAR_PROMPT as REEXPORTED_PROMPT
from tarjoman.stages.stage2_draft import (
    STRUCTURAL_GRAMMAR_PROMPT,
    NeutralLinguisticFraming,
)
from tarjoman.stages.stage4_polish import StylisticPolishStage


def _load_skill_linter():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".claude",
        "skills",
        "tarjoman",
        "scripts",
        "linter.py",
    )
    spec = importlib.util.spec_from_file_location("trn013_skill_linter", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["trn013_skill_linter"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("trn013_skill_linter", None)
    return module


SKILL_LINTER = _load_skill_linter()


class TestSmoothEzafeChains(unittest.TestCase):
    def test_three_ezafe_chain_is_smoothed(self) -> None:
        out = StylisticPolishStage.smooth_ezafe_chains(
            "برنامه‌ی توسعه‌ی سامانه‌ی نظارت"
        )
        self.assertIn("مربوط به", out)
        # Original heavy chain must be broken.
        self.assertNotEqual(out, "برنامه‌ی توسعه‌ی سامانه‌ی نظارت")

    def test_kasra_chain_is_smoothed(self) -> None:
        out = StylisticPolishStage.smooth_ezafe_chains("کتابِ تاریخِ تمدنِ باستان")
        self.assertIn("مربوط به", out)

    def test_four_link_chain_is_smoothed(self) -> None:
        out = StylisticPolishStage.smooth_ezafe_chains(
            "دانشکده‌ی مهندسیِ دانشگاهِ تهران"
        )
        self.assertIn("مربوط به", out)

    def test_two_ezafe_phrase_preserved(self) -> None:
        text = "کتابخانه‌ی مرکزیِ دانشگاه"
        self.assertEqual(StylisticPolishStage.smooth_ezafe_chains(text), text)

    def test_single_ezafe_phrase_preserved(self) -> None:
        for text in ("دانشکده‌ی مهندسی", "کتابِ من"):
            self.assertEqual(StylisticPolishStage.smooth_ezafe_chains(text), text)

    def test_verbatim_code_span_preserved(self) -> None:
        text = "کد `برنامه‌ی توسعه‌ی سامانه‌ی نظارت` دست‌نخورده است."
        out = StylisticPolishStage.smooth_ezafe_chains(text)
        self.assertIn("`برنامه‌ی توسعه‌ی سامانه‌ی نظارت`", out)

    def test_verbatim_math_and_url_preserved(self) -> None:
        text = (
            "فرمول $E=mc^2$ و پیوند https://example.com/x "
            "برنامه‌ی توسعه‌ی سامانه‌ی نظارت است."
        )
        out = StylisticPolishStage.smooth_ezafe_chains(text)
        self.assertIn("$E=mc^2$", out)
        self.assertIn("https://example.com/x", out)
        self.assertIn("مربوط به", out)

    def test_edge_cases(self) -> None:
        self.assertEqual(StylisticPolishStage.smooth_ezafe_chains(""), "")
        latin = "The quick brown fox jumps."
        self.assertEqual(StylisticPolishStage.smooth_ezafe_chains(latin), latin)
        mixed = "Hello برنامه‌ی توسعه‌ی سامانه‌ی نظارت world."
        self.assertIn(
            "مربوط به", StylisticPolishStage.smooth_ezafe_chains(mixed)
        )

    def test_polish_pipeline_integrates_smoothing(self) -> None:
        out = StylisticPolishStage.polish("برنامه‌ی توسعه‌ی سامانه‌ی نظارت.")
        self.assertIn("مربوط به", out)
        # Short phrases still untouched through the full pipeline.
        self.assertEqual(
            StylisticPolishStage.polish("دانشکده‌ی مهندسی"), "دانشکده‌ی مهندسی"
        )


class TestStructuralGrammarPrompt(unittest.TestCase):
    def test_np_sequence_present(self) -> None:
        self.assertIn("M1 -> N -> M3 -> M2 -> M4/M5", STRUCTURAL_GRAMMAR_PROMPT)

    def test_six_a_an_rules_present(self) -> None:
        for marker in (
            "zero mark",
            "yeki az",
            "noei / goonei az",
            "pas az anke",
            "marbut be",
        ):
            self.assertIn(marker, STRUCTURAL_GRAMMAR_PROMPT.lower())

    def test_wrap_injects_guidance(self) -> None:
        wrapped = NeutralLinguisticFraming().wrap("Some English text.")
        self.assertIn("M1 -> N -> M3 -> M2 -> M4/M5", wrapped)
        self.assertIn("Some English text.", wrapped)

    def test_draft_module_reexport(self) -> None:
        self.assertEqual(REEXPORTED_PROMPT, STRUCTURAL_GRAMMAR_PROMPT)


class TestStructuralLinter(unittest.TestCase):
    def test_ezafe_chain_detected(self) -> None:
        issues = linter.lint_text("برنامه‌ی توسعه‌ی سامانه‌ی نظارت")
        self.assertTrue(
            any(i.category == "ezafe-chain" for i in issues),
            f"expected ezafe-chain, got {[i.category for i in issues]}",
        )
        hit = next(i for i in issues if i.category == "ezafe-chain")
        self.assertIn("smooth_ezafe_chains", hit.suggestion)

    def test_short_ezafe_no_false_positive(self) -> None:
        for text in (
            "دانشکده‌ی مهندسی",
            "کتابخانه‌ی مرکزیِ دانشگاه",
            "او با لبخندی آرام گفت: «این یک متن کاملاً پاکیزه و "
            "بدون کوچک‌ترین ایراد نگارشی است.»",
        ):
            cats = {i.category for i in linter.lint_text(text)}
            self.assertNotIn("ezafe-chain", cats, f"false positive: {text!r}")

    def test_generic_article_detected(self) -> None:
        issues = linter.lint_text("یک پزشک باید همدل باشد.")
        self.assertTrue(
            any(i.category == "generic-article" for i in issues),
            f"expected generic-article, got {[i.category for i in issues]}",
        )

    def test_generic_article_no_false_positive(self) -> None:
        for text in (
            "یک کتاب روی میز است.",
            "این یک متن نمونه برای کامپایل تایپست است.",
            "او با آرامش گفت: «این یک ترجمه دقیق است.»",
            "یک سیب از درخت افتاد.",
        ):
            cats = {i.category for i in linter.lint_text(text)}
            self.assertNotIn("generic-article", cats, f"false positive: {text!r}")

    def test_skill_linter_parity(self) -> None:
        pkg_cats = {
            i.category
            for i in linter.lint_text(
                "برنامه‌ی توسعه‌ی سامانه‌ی نظارت\nیک پزشک باید همدل باشد."
            )
        }
        skill_cats = {
            i.category
            for i in SKILL_LINTER.lint_text(
                "برنامه‌ی توسعه‌ی سامانه‌ی نظارت\nیک پزشک باید همدل باشد."
            )
        }
        self.assertIn("ezafe-chain", pkg_cats)
        self.assertIn("generic-article", pkg_cats)
        self.assertEqual(pkg_cats & {"ezafe-chain", "generic-article"}, skill_cats)


if __name__ == "__main__":
    unittest.main()
