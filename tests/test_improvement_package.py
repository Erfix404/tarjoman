# -*- coding: utf-8 -*-
"""Validation tests for the book-study improvement package.

Contents under test:
    .claude/skills/tarjoman/references/anti-calque.md   (updated in place)
    .claude/skills/tarjoman/references/editor-najafi.md (new, editor track)
    .claude/skills/tarjoman/references/fidelity.md      (new, Khazaeifar)
    docs/research/improvement-eval-samples.jsonl
    .claude/skills/tarjoman/SKILL.md (routes to the new guides, equal-effect worksheet in step 1)

These tests lock the package contract: the mother principle and the
living-speech test head the anti-calque additions, the gap-118 correction
is applied to the old guide text, the two-tier rulings and the protection
list are present, the editor-track items stay out of anti-calque, the
fidelity protocol carries the defense test and the two new QA error
types, and no foreign em-dash slips in.
"""
import json
import os
import re
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFS = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman", "references")
ANTI = os.path.join(REFS, "anti-calque.md")
EDITOR_NAJAFI = os.path.join(REFS, "editor-najafi.md")
FIDELITY = os.path.join(REFS, "fidelity.md")
SKILL = os.path.join(PROJECT_ROOT, ".claude", "skills", "tarjoman", "SKILL.md")
SAMPLES = os.path.join(PROJECT_ROOT, "docs", "research", "improvement-eval-samples.jsonl")

FIELDS = {"id", "area", "expected", "before", "after", "note"}
AREAS = {"anti-calque", "tier", "protection", "editor", "fidelity"}
EXPECTED_VALUES = {"rewrite", "no_change", "disclose"}
EM_DASHES = (chr(0x2014), chr(0x2013))  # foreign em-dash / en-dash, built by code point so this file stays clean
PERSIAN = re.compile(r"[؀-ۿ]")


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


class TestFilesExist(unittest.TestCase):
    def test_files_exist(self):
        for path in (ANTI, EDITOR_NAJAFI, FIDELITY, SAMPLES, SKILL):
            self.assertTrue(os.path.exists(path), path)

    def test_new_guides_open_with_glance(self):
        for path in (EDITOR_NAJAFI, FIDELITY):
            text = read(path)
            head = "\n".join(text.splitlines()[:8])
            self.assertIn("## در یک نگاه", head, path)
            bullets = glance_bullets(text)
            self.assertTrue(3 <= len(bullets) <= 8, (path, len(bullets)))


class TestAntiCalqueAdditions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(ANTI)

    def test_original_sections_kept(self):
        for marker in ("## ۱. مجهول با «توسط»", "## ۵. ساختار جمله", "توسط تولستوی"):
            self.assertIn(marker, self.text)

    def test_mother_principle_and_living_speech_test(self):
        self.assertIn("اصل مادر", self.text)
        self.assertIn("معادل ثابت", self.text)
        self.assertIn("نرخ بیکاری", self.text)
        self.assertIn("گفتار زنده", self.text)
        self.assertIn("فقط مترجم‌ها می‌نویسند", self.text)

    def test_new_family_sections(self):
        for marker in ("## ۷.", "## ۸.", "## ۹.", "## ۱۰.", "## ۱۱."):
            self.assertIn(marker, self.text)

    def test_gap118_correction_applied(self):
        self.assertIn("اثر تحریم‌ها در اقتصاد", self.text)
        self.assertNotIn("اثر تحریم‌ها بر اقتصاد", self.text)
        self.assertIn("اثر داشتن در", self.text)
        self.assertNotIn("اثر داشتن بر", self.text)

    def test_headline_gaps_present(self):
        for phrase in ("در راستای", "انتظار می‌رود", "انجام وظیفه", "وقت صرف کردن",
                       "گمان نمی‌کنم", "هیچ‌کدامتان", "بستگی دارد", "فرق داشتن با"):
            self.assertIn(phrase, self.text, phrase)

    def test_two_tier_rulings_present_as_tiers(self):
        self.assertIn("احکام دوطبقه", self.text)
        for phrase in ("در رابطه با", "به‌خاطر", "می‌باشد", "نمودن"):
            self.assertIn(phrase, self.text, phrase)

    def test_protection_list_present(self):
        self.assertIn("فهرست حفاظت", self.text)
        for phrase in ("شرایط", "علیه", "یکم", "احترام گذاشتن", "نقشِ تنها"):
            self.assertIn(phrase, self.text, phrase)

    def test_editor_items_not_in_anti_calque(self):
        # Arabic feminine adjectives and tanwin rules live in the editor track.
        self.assertNotIn("غیرمترقّبه", self.text)
        self.assertNotIn("تنوین بر واژه‌ی فارسی", self.text)


class TestEditorTrack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(EDITOR_NAJAFI)

    def test_editor_families_present(self):
        for phrase in ("تنوین", "صفت مؤنث عربی", "غیرقابل", "نوین", "نشانگر", "گذاشتن و گزاردن"):
            self.assertIn(phrase, self.text, phrase)

    def test_editor_points_back_to_editor_guide(self):
        self.assertIn("editor.md", self.text)


class TestFidelity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(FIDELITY)

    def test_protocol_present(self):
        for phrase in ("از ثبات شروع کن", "تست دفاع", "تأثیر برابر", "خوانش مستقل"):
            self.assertIn(phrase, self.text, phrase)

    def test_new_qa_error_types(self):
        self.assertIn("ثبات زائد", self.text)
        self.assertIn("تغییر بی‌دلیل", self.text)

    def test_relay_disclosure_and_no_softening(self):
        self.assertIn("واسطه", self.text)
        self.assertIn("افشا", self.text)
        self.assertIn("ملایم‌سازی ممنوع", self.text)

    def test_no_add_omit_boundary_kept(self):
        self.assertIn("چیزی نساز", self.text)


class TestSkillPatch(unittest.TestCase):
    def test_skill_mentions_new_guides_and_worksheet(self):
        text = read(SKILL)
        self.assertIn("fidelity.md", text)
        self.assertIn("editor-najafi.md", text)
        self.assertIn("برگه‌ی تأثیر برابر", text)

    def test_skill_routes_after_patch(self):
        text = read(SKILL)
        self.assertIn("references/fidelity.md", text)
        self.assertIn("references/editor-najafi.md", text)
        self.assertLessEqual(len(text.splitlines()), 110)


class TestSamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_samples()

    def test_samples_substantial(self):
        self.assertGreaterEqual(len(self.rows), 20)

    def test_schema_complete(self):
        for r in self.rows:
            self.assertEqual(set(r), FIELDS, r.get("id"))
            self.assertIn(r["area"], AREAS, r["id"])
            self.assertIn(r["expected"], EXPECTED_VALUES, r["id"])
            for k in FIELDS:
                self.assertIsInstance(r[k], str, (r["id"], k))
                self.assertTrue(r[k].strip(), (r["id"], k))

    def test_ids_unique_and_expected_semantics(self):
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        for r in self.rows:
            self.assertTrue(PERSIAN.search(r["before"]), r["id"])
            self.assertTrue(PERSIAN.search(r["after"]), r["id"])
            if r["expected"] == "rewrite":
                self.assertNotEqual(r["before"], r["after"], r["id"])
            if r["expected"] == "no_change":
                self.assertEqual(r["before"], r["after"], r["id"])

    def test_all_areas_covered(self):
        self.assertEqual({r["area"] for r in self.rows}, AREAS)

    def test_locked_examples(self):
        by_id = {r["id"]: r for r in self.rows}
        self.assertIn("میزان بیکاری", by_id["imp-ac-01"]["after"])
        self.assertIn("در اقتصاد", by_id["imp-ac-12"]["after"])
        self.assertEqual(by_id["imp-prot-01"]["before"], by_id["imp-prot-01"]["after"])
        self.assertNotEqual(by_id["imp-fid-01"]["before"], by_id["imp-fid-01"]["after"])


class TestCleanliness(unittest.TestCase):
    def test_no_foreign_em_dash(self):
        for path in (ANTI, EDITOR_NAJAFI, FIDELITY, SAMPLES):
            text = read(path)
            for dash in EM_DASHES:
                self.assertNotIn(dash, text, (path, dash))


if __name__ == "__main__":
    unittest.main()
