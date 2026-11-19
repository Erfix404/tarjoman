# -*- coding: utf-8 -*-
"""Validation tests for the naturalize + colloquialize package.

The two guides live next to the other references:
    .claude/skills/tarjoman/references/naturalize.md
    .claude/skills/tarjoman/references/colloquialize.md

Eval samples:
    docs/research/naturalize-eval-samples.jsonl

These tests lock the package contract: both guides open with
«در یک نگاه», the golden pairs stay in the naturalize guide, the
SKILL patch routes to both guides, the samples are well-formed,
and no foreign em-dash or level-mixing example slips in as correct.
"""
import json
import os
import re
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFS = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman", "references")
NATURALIZE = os.path.join(REFS, "naturalize.md")
COLLOQUIALIZE = os.path.join(REFS, "colloquialize.md")
SKILL = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman", "SKILL.md")
SAMPLES = os.path.join(PROJECT_ROOT, "docs", "research", "naturalize-eval-samples.jsonl")

FIELDS = {"id", "feature", "expected", "register", "level", "before", "after", "note"}
EXPECTED_VALUES = {"rewrite", "no_change", "keep_quote", "warn_keep", "keep_placeholders", "preserve_qualifiers"}
FEATURES = {"naturalize", "colloquialize"}
LEVELS = {"مؤدب", "خودمانی"}
EM_DASHES = (chr(0x2014), chr(0x2013))  # foreign em-dash / en-dash, built by code point so this file stays clean
BAD_MIX = "می‌خواهم برم"
PERSIAN = re.compile(r"[؀-ۿ]")

GOLDEN = [
    "از کجا شارژ می‌شی؟",
    "از چه جور جاهایی انرژی می‌گیری؟",
    "بعضیا اول دلشون رو گوش می‌دن",
    "بعضیا به حرف دلشون و احساس درونشون گوش می‌دن",
]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_samples():
    with open(SAMPLES, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def glance_bullets(text):
    lines = text.splitlines()
    start = lines.index("## در یک نگاه")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
    return [l for l in lines[start:end] if l.startswith("- ")]


class TestGuides(unittest.TestCase):
    def test_guides_exist(self):
        self.assertTrue(os.path.exists(NATURALIZE))
        self.assertTrue(os.path.exists(COLLOQUIALIZE))

    def test_guides_open_with_glance(self):
        for path in (NATURALIZE, COLLOQUIALIZE):
            text = read(path)
            head = "\n".join(text.splitlines()[:8])
            self.assertIn("## در یک نگاه", head, path)
            bullets = glance_bullets(text)
            self.assertTrue(3 <= len(bullets) <= 8, (path, len(bullets)))

    def test_naturalize_keeps_golden_pairs(self):
        text = read(NATURALIZE)
        for pair in GOLDEN:
            self.assertIn(pair, text)

    def test_naturalize_states_register_preserved_and_attestation(self):
        text = read(NATURALIZE)
        self.assertIn("پیشنهادی", text)
        self.assertIn("colloquialize.md", text)

    def test_colloquialize_builds_on_colloquial_guide(self):
        text = read(COLLOQUIALIZE)
        self.assertIn("colloquial.md", text)
        self.assertIn("مؤدب", text)
        self.assertIn("خودمانی", text)
        self.assertIn("naturalize.md", text)


class TestSkillPatch(unittest.TestCase):
    def test_skill_mentions_both_guides(self):
        self.assertTrue(os.path.exists(SKILL))
        text = read(SKILL)
        self.assertIn("naturalize.md", text)
        self.assertIn("colloquialize.md", text)

    def test_skill_routes_to_both_guides_after_patch(self):
        text = read(SKILL)
        self.assertIn("references/naturalize.md", text)
        self.assertIn("references/colloquialize.md", text)


class TestSamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_samples()

    def test_samples_exist_and_are_substantial(self):
        self.assertTrue(os.path.exists(SAMPLES))
        self.assertGreaterEqual(len(self.rows), 17)

    def test_schema_complete(self):
        for r in self.rows:
            self.assertEqual(set(r), FIELDS, r.get("id"))
            self.assertIn(r["feature"], FEATURES, r["id"])
            for k in ("id", "register", "before", "after", "note"):
                self.assertIsInstance(r[k], str, (r["id"], k))
                self.assertTrue(r[k].strip(), (r["id"], k))

    def test_ids_unique_and_before_differs_from_after(self):
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        for r in self.rows:
            if r["expected"] == "rewrite":
                self.assertNotEqual(r["before"], r["after"], r["id"])
            self.assertTrue(PERSIAN.search(r["before"]), r["id"])
            self.assertTrue(PERSIAN.search(r["after"]), r["id"])

    def test_levels(self):
        for r in self.rows:
            if r["feature"] == "colloquialize":
                self.assertIn(r["level"], LEVELS, r["id"])
            else:
                self.assertIsNone(r["level"], r["id"])

    def test_both_features_and_registers_covered(self):
        feats = {r["feature"] for r in self.rows}
        self.assertEqual(feats, FEATURES)
        regs = {r["register"] for r in self.rows}
        self.assertGreaterEqual(len(regs), 4)


class TestV2Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nat = read(NATURALIZE)
        cls.col = read(COLLOQUIALIZE)
        cls.skill = read(SKILL)
        cls.rows = load_samples()

    def test_naturalize_intensity_section(self):
        self.assertIn("## شدت روان‌سازی", self.nat)
        self.assertIn("سبک", self.nat)
        self.assertIn("کامل", self.nat)
        for phrase in ("یه کم", "دست به متنش نزن", "فقط غلط‌هاشو بگیر"):
            self.assertIn(phrase, self.nat)
        self.assertIn("با شدت سبک", self.nat)
        self.assertIn("با شدت کامل", self.nat)
        self.assertIn("یادداشت تحویل", self.nat)

    def test_trigger_phrases_in_both_guides(self):
        for phrase in ("روانش کن", "طبیعیش کن", "حس ترجمه‌شو بگیر", "مثل آدم بنویس", "خشک و کتابیه", "make it sound natural", "humanize this"):
            self.assertIn(phrase, self.nat, phrase)
        for phrase in ("خودمونیش کن", "محاوره‌ایش کن", "به زبان خودمون بنویس", "make it casual", "say it like you'd text it"):
            self.assertIn(phrase, self.col, phrase)

    def test_trigger_phrases_in_skill_patch(self):
        for phrase in ("روانش کن", "حس ترجمه‌شو بگیر", "خودمونیش کن", "محاوره‌ایش کن"):
            self.assertIn(phrase, self.skill, phrase)

    def test_chain_order_present(self):
        self.assertIn("ترتیب اجرا", self.col)
        self.assertIn("خودمونی‌سازی آخر", self.col)
        self.assertIn("هرگز بعد از خودمونی‌سازی", self.col)
        self.assertIn("editor.md", self.col)
        self.assertIn("خودمونی‌سازی آخر", self.skill)

    def test_delivery_note_in_both_checklists(self):
        self.assertIn("یادداشت تحویل (۲ تا ۳ خط، اجباری)", self.nat)
        self.assertIn("یادداشت تحویل (۲ تا ۳ خط، اجباری)", self.col)

    def test_subtitle_rule_in_colloquialize(self):
        self.assertIn("subtitles.md", self.col)
        self.assertIn("۴۲ حرف", self.col)
        self.assertIn("زیرنویس", self.col)

    def test_book_consistency_in_both_guides(self):
        for text in (self.nat, self.col):
            self.assertIn("book.md", text)
            self.assertIn("شیوه‌نامه", text)

    def test_expected_field_values(self):
        for r in self.rows:
            self.assertIn(r["expected"], EXPECTED_VALUES, r["id"])

    def test_negative_samples(self):
        negatives = [r for r in self.rows if r["expected"] != "rewrite"]
        self.assertGreaterEqual(len(self.rows), 17)
        self.assertGreaterEqual(len(negatives), 5)

    def test_legal_warn_keep_sample_unchanged(self):
        legal = [r for r in self.rows if r["expected"] == "warn_keep"]
        self.assertTrue(legal)
        for r in legal:
            self.assertEqual(r["before"], r["after"], r["id"])
            self.assertEqual(r["feature"], "colloquialize", r["id"])

    def test_placeholder_sample_byte_identical(self):
        rows = [r for r in self.rows if r["expected"] == "keep_placeholders"]
        self.assertTrue(rows)
        for r in rows:
            for ph in ("{count}", "%s"):
                self.assertIn(ph, r["before"], r["id"])
                self.assertIn(ph, r["after"], r["id"])
                self.assertEqual(r["before"].count(ph), r["after"].count(ph), r["id"])


class TestCleanliness(unittest.TestCase):
    def test_no_foreign_em_dash_in_guides_or_samples(self):
        for path in (NATURALIZE, COLLOQUIALIZE, SAMPLES):
            text = read(path)
            for dash in EM_DASHES:
                self.assertNotIn(dash, text, (path, dash))

    def test_level_mixing_never_presented_as_correct(self):
        for path in (NATURALIZE, COLLOQUIALIZE, SAMPLES):
            for line in read(path).splitlines():
                if BAD_MIX in line:
                    self.assertTrue(
                        "ممنوع" in line or "غلط" in line,
                        (path, line),
                    )


if __name__ == "__main__":
    unittest.main()
