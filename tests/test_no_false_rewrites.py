"""Negative tests: correct Persian must survive the automatic passes unchanged.

Every sentence here was once damaged by a context-blind rewrite rule. The
automatic layer may only fix safe things (characters, ZWNJ, quotes, tanvin);
meaning-dependent rules are reported by the linter instead.
"""
from __future__ import annotations

import unittest

from tarjoman.linter import find_hekasre, lint_text
from tarjoman.stages.anti_calque import AntiCalqueEngine
from tarjoman.stages.humanizer import PersianHumanizer
from tarjoman.stages.stage4_polish import StylisticPolishStage

CORRECT_SENTENCES = [
    "علی دنبال کلیدش می‌گردد.",
    "در پایان روز به خانه برگشتیم.",
    "جهت باد عوض شد.",
    "هوا فوق‌العاده سرد بود و غذای فوق‌العاده‌ای خوردیم.",
    "قیمت‌ها ده درصد بالا رفت که نشان‌دهنده‌ی تورم شدید است.",
    "به طور کلی سه راه داریم: الف، ب و ج.",
    "او نقش هملت را بازی کرد.",
]


class TestNoFalseRewrites(unittest.TestCase):
    def test_humanizer_preserves(self) -> None:
        for text in CORRECT_SENTENCES:
            self.assertEqual(PersianHumanizer.humanize(text), text, text)

    def test_anti_calque_preserves(self) -> None:
        for text in CORRECT_SENTENCES:
            self.assertEqual(AntiCalqueEngine.eliminate_calques(text), text, text)

    def test_full_polish_preserves(self) -> None:
        for text in CORRECT_SENTENCES:
            self.assertEqual(StylisticPolishStage.polish(text), text, text)


class TestHekasreFalsePositives(unittest.TestCase):
    def test_common_words_not_flagged(self) -> None:
        for text in ("باید توجه داشت که", "این کار انجام شده است.", "همه ما", "گفته من"):
            self.assertEqual(find_hekasre(text), [], text)

    def test_real_hekasre_still_flagged(self) -> None:
        self.assertTrue(find_hekasre("کتابه من کجاست؟"))


class TestAiTellLint(unittest.TestCase):
    def test_typical_agent_paragraph_reported(self) -> None:
        text = (
            "در این مقاله، ما به بررسی این موضوع می‌پردازیم. باید توجه داشت که "
            "این مسئله از اهمیت بالایی برخوردار است."
        )
        cats = [i.category for i in lint_text(text)]
        self.assertGreaterEqual(cats.count("ai-tell"), 3)


if __name__ == "__main__":
    unittest.main()
