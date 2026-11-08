"""Regression guard for the naturalness eval set (docs/research/eval-set).

The lint can only catch translationese that has a surface pattern, so the
bar is "never worse than now", not "everything": no natural sample or
negative may get a style finding, and the literal side must stay detected in
at least as many samples as when the set was last measured.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "benchmarks"))

from eval_naturalness import STYLE_CATEGORIES, separation, style_findings  # noqa: E402

SAMPLES = os.path.join(ROOT, "docs", "research", "eval-set", "samples.jsonl")


def load():
    with open(SAMPLES, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestEvalSet(unittest.TestCase):
    def setUp(self) -> None:
        self.samples = load()

    def test_ids_unique_and_fields_present(self) -> None:
        ids = [s["id"] for s in self.samples]
        self.assertEqual(len(ids), len(set(ids)))
        for s in self.samples:
            for key in ("genre", "source", "literal", "natural", "calques"):
                self.assertIn(key, s, s["id"])

    def test_covers_every_style_the_skill_routes(self) -> None:
        genres = {s["genre"] for s in self.samples}
        for g in ("chat", "narrative", "dialogue", "subtitles", "technical", "ui", "scientific",
                  "medical", "legal", "news", "financial", "philosophy", "classical",
                  "transcreation", "edit", "poetry"):
            self.assertIn(g, genres)

    def test_natural_side_never_flagged(self) -> None:
        for s in self.samples:
            self.assertEqual(style_findings(s["natural"], STYLE_CATEGORIES), 0, s["id"])

    def test_detection_does_not_regress(self) -> None:
        by_genre = separation(self.samples)
        caught = sum(v[0] for v in by_genre.values())
        total = sum(v[1] for v in by_genre.values())
        self.assertGreaterEqual(total, 58)
        self.assertGreaterEqual(caught, 41, f"{caught}/{total}")


if __name__ == "__main__":
    unittest.main()
