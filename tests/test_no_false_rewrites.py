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


class TestEvalSetNegatives(unittest.TestCase):
    """Negative cases in docs/research/eval-set must survive polishing unchanged."""

    def test_eval_set_negatives_unchanged(self) -> None:
        import json
        import os

        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docs", "research", "eval-set", "samples.jsonl",
        )
        with open(path, encoding="utf-8") as f:
            samples = [json.loads(line) for line in f if line.strip()]
        negatives = [s for s in samples if s.get("type") == "negative"]
        self.assertTrue(negatives)
        for sample in negatives:
            text = sample["natural"]
            self.assertEqual(StylisticPolishStage.polish(text), text, sample["id"])


class TestAiTellCatalog(unittest.TestCase):
    """The expanded suggest-only catalog catches typical agent prose but not plain Persian."""

    AGENT_TEXT = (
        "در دنیای پرشتاب امروز، هوش مصنوعی نقش کلیدی ایفا می‌کند. این ابزار نه تنها سریع است "
        "بلکه دقیق هم هست. علاوه بر این، استفاده از آن به طور قابل توجهی منجر به کاهش "
        "هزینه‌ها می‌شود. بیایید نگاهی عمیق‌تر به آن بیندازیم. امیدوارم این مطلب مفید باشد."
    )

    PLAIN_TEXT = [
        "علی دنبال کلیدش می‌گردد.",
        "سفر ما به شیراز خیلی خوب بود.",
        "چه خبر؟ دیروز رفتم سینما.",
        "به عنوان معلم در روستا کار می‌کند.",
        "قیمت‌ها بالا رفت و مردم کمتر خرید کردند.",
    ]

    def test_agent_text_flagged(self) -> None:
        labels = {d[0] for d in PersianHumanizer.detect(self.AGENT_TEXT)}
        self.assertGreaterEqual(len(labels), 8, labels)

    def test_plain_text_not_flagged(self) -> None:
        for text in self.PLAIN_TEXT:
            self.assertEqual(PersianHumanizer.detect(text), [], text)

    def test_detect_never_rewrites(self) -> None:
        # detect() is read-only; humanize() must not touch these meaning-bearing tells.
        out = PersianHumanizer.humanize("این تغییر منجر به کاهش هزینه‌ها شد.")
        self.assertIn("منجر به کاهش هزینه‌ها شد", out)
