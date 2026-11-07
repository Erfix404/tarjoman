"""Tests for Tarjoman v2.3.0: Persian De-AI Humanizer, Hekasre, Tanvin, Shielding.

Covers:
- All 18 AI-tell patterns (T1-T18)
- Code & Markdown table shielding (fenced code, inline code, table rows)
- find_hekasre detection accuracy
- Tanvin repair and fake tanvin replacement
- End-to-end integration via StylisticPolishStage.polish
- Linter detection of hekasre and tanvin issues
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest

from tarjoman.stages.humanizer import (
    PersianHumanizer,
    protect_regions,
    restore_regions,
    TANVIN_NEEDED,
    FAKE_TANVIN,
)
from tarjoman.stages.stage4_polish import StylisticPolishStage
from tarjoman import linter


def _load_skill_linter():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".claude", "skills", "tarjoman", "scripts", "linter.py",
    )
    spec = importlib.util.spec_from_file_location("deai_skill_linter", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["deai_skill_linter"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("deai_skill_linter", None)
    return module


SKILL_LINTER = _load_skill_linter()


# =========================================================================
# Code & Markdown Table Shielding
# =========================================================================
class TestShielding(unittest.TestCase):
    """Test protect_regions / restore_regions byte-for-byte preservation."""

    def test_fenced_code_block_preserved(self) -> None:
        code = '```python\nx = "hello — world"\nprint(x)\n```'
        text = f"متن فارسی\n{code}\nادامه متن"
        masked, tokens = protect_regions(text)
        self.assertNotIn("```", masked)
        restored = restore_regions(masked, tokens)
        self.assertEqual(restored, text)

    def test_tilde_fenced_code_preserved(self) -> None:
        code = '~~~bash\necho "test — dash"\n~~~'
        text = f"متن\n{code}\nپایان"
        masked, tokens = protect_regions(text)
        self.assertNotIn("~~~", masked)
        restored = restore_regions(masked, tokens)
        self.assertEqual(restored, text)

    def test_inline_code_preserved(self) -> None:
        text = "از دستور `git commit --amend` استفاده کنید."
        masked, tokens = protect_regions(text)
        self.assertNotIn("`git commit --amend`", masked)
        restored = restore_regions(masked, tokens)
        self.assertEqual(restored, text)

    def test_markdown_table_rows_preserved(self) -> None:
        table = "| ستون ۱ | ستون ۲ |\n| --- | --- |\n| داده | مقدار |"
        text = f"متن قبل\n{table}\nمتن بعد"
        masked, tokens = protect_regions(text)
        self.assertNotIn("|", masked)
        restored = restore_regions(masked, tokens)
        self.assertEqual(restored, text)

    def test_multiple_regions_preserved(self) -> None:
        text = "متن `code1` و `code2` و\n```\nblock\n```\nپایان"
        masked, tokens = protect_regions(text)
        restored = restore_regions(masked, tokens)
        self.assertEqual(restored, text)

    def test_humanize_preserves_code(self) -> None:
        code_block = '```\nمی‌باشد — test\n```'
        text = f"این متن می‌باشد.\n{code_block}\nادامه"
        result = PersianHumanizer.humanize(text)
        # The mi-bashad in prose should be replaced
        self.assertNotIn("می‌باشد", result.split("```")[0])
        # The code block should be byte-identical
        self.assertIn(code_block, result)

    def test_humanize_preserves_inline_code(self) -> None:
        text = "نتیجه `می‌باشد` را ببینید. این می‌باشد."
        result = PersianHumanizer.humanize(text)
        self.assertIn("`می‌باشد`", result)
        # The plain text one should be replaced
        parts = result.split("`")
        plain = parts[0] + parts[-1]
        self.assertNotIn("می‌باشد", plain)

    def test_humanize_preserves_table(self) -> None:
        table = "| می‌باشد | لطفا |"
        text = f"متن\n{table}\nمتن"
        result = PersianHumanizer.humanize(text)
        self.assertIn(table, result)


# =========================================================================
# T1: Copula inflation
# =========================================================================
class TestT1CopulaInflation(unittest.TestCase):
    def test_mi_bashad_replaced(self) -> None:
        self.assertIn("است", PersianHumanizer.humanize("این مهم می‌باشد."))
        self.assertNotIn("می‌باشد", PersianHumanizer.humanize("این مهم می‌باشد."))

    def test_nmi_bashad_replaced(self) -> None:
        result = PersianHumanizer.humanize("این مهم نمی‌باشد.")
        self.assertIn("نیست", result)

    def test_be_shomar_miravad(self) -> None:
        result = PersianHumanizer.humanize("این به شمار می‌رود.")
        self.assertIn("است", result)

    def test_mahsub_mishavad(self) -> None:
        result = PersianHumanizer.humanize("این ابزاری قدرتمند محسوب می‌شود.")
        self.assertIn("است", result)
        self.assertNotIn("محسوب می‌شود", result)

    def test_be_hesab_miayad(self) -> None:
        result = PersianHumanizer.humanize("این به حساب می‌آید.")
        self.assertIn("است", result)

    def test_gardide_ast(self) -> None:
        result = PersianHumanizer.humanize("تکمیل گردیده است.")
        self.assertIn("شده است", result)

    def test_migardad(self) -> None:
        result = PersianHumanizer.humanize("انجام می‌گردد.")
        self.assertIn("می‌شود", result)

    def test_gardid(self) -> None:
        result = PersianHumanizer.humanize("اعلام گردید.")
        self.assertIn("شد", result)


# =========================================================================
# T2: Ceremonial filler announcements
# =========================================================================
class TestT2CeremonialFillers(unittest.TestCase):
    def test_lazem_be_zekr(self) -> None:
        result = PersianHumanizer.humanize("لازم به ذکر است که پشتیبانی ارائه می‌شود.")
        self.assertNotIn("لازم به ذکر است که", result)
        self.assertIn("پشتیبانی", result)

    def test_shayan_zekr(self) -> None:
        result = PersianHumanizer.humanize("شایان ذکر است که این مهم است.")
        self.assertNotIn("شایان ذکر است که", result)

    def test_bayad_khaterneshan(self) -> None:
        result = PersianHumanizer.humanize("باید خاطرنشان کرد که نتایج مثبت بود.")
        self.assertNotIn("باید خاطرنشان کرد که", result)

    def test_qabel_tavajoh(self) -> None:
        result = PersianHumanizer.humanize("قابل توجه است که کیفیت بالاست.")
        self.assertNotIn("قابل توجه است که", result)


# =========================================================================
# T3: Significance inflation
# =========================================================================
class TestT3SignificanceInflation(unittest.TestCase):
    def test_ahamiyat_vizheh(self) -> None:
        result = PersianHumanizer.humanize("سئو از اهمیت ویژه‌ای برخوردار است.")
        self.assertIn("مهم است", result)
        self.assertNotIn("اهمیت ویژه", result)

    def test_naqsh_besazayi(self) -> None:
        result = PersianHumanizer.humanize("فناوری نقش بسزایی ایفا می‌کند.")
        self.assertIn("نقش مهمی دارد", result)

    def test_jaygah_vizheh(self) -> None:
        result = PersianHumanizer.humanize("ایران جایگاه ویژه‌ای دارد.")
        self.assertIn("مهم است", result)


# =========================================================================
# T4: Generic openers/closers
# =========================================================================
class TestT4GenericOpenersClosers(unittest.TestCase):
    def test_dar_donyaye_emruz(self) -> None:
        result = PersianHumanizer.humanize("در دنیای امروز فناوری مهم است.")
        self.assertNotIn("در دنیای امروز", result)
        self.assertIn("فناوری", result)

    def test_dar_asre_digital(self) -> None:
        result = PersianHumanizer.humanize("در عصر دیجیتال اینترنت ضروری است.")
        self.assertNotIn("در عصر دیجیتال", result)

    def test_dar_nahayat_mitavan_goft(self) -> None:
        result = PersianHumanizer.humanize("در نهایت می‌توان گفت موفق بودیم.")
        self.assertNotIn("در نهایت می‌توان گفت", result)

    def test_be_tor_kolli(self) -> None:
        result = PersianHumanizer.humanize("به طور کلی نتایج مثبت بود.")
        self.assertNotIn("به طور کلی", result)


# =========================================================================
# T5: «در راستای» abuse
# =========================================================================
class TestT5DarRastaye(unittest.TestCase):
    def test_dar_rastaye(self) -> None:
        result = PersianHumanizer.humanize("در راستای بهبود کیفیت اقدام شد.")
        self.assertIn("برای", result)
        self.assertNotIn("در راستای", result)

    def test_dar_hamin_rasta(self) -> None:
        result = PersianHumanizer.humanize("در همین راستا تغییرات اعمال شد.")
        self.assertNotIn("در همین راستا", result)


# =========================================================================
# T6: Promotional emptiness
# =========================================================================
class TestT6PromotionalEmptiness(unittest.TestCase):
    def test_bi_nazir_removed(self) -> None:
        result = PersianHumanizer.humanize("خدمات بی‌نظیر ما")
        self.assertNotIn("بی‌نظیر", result)

    def test_fogh_oladeh_removed(self) -> None:
        result = PersianHumanizer.humanize("تجربه‌ای فوق‌العاده")
        self.assertNotIn("فوق‌العاده", result)

    def test_mesal_zadani_removed(self) -> None:
        result = PersianHumanizer.humanize("کیفیت مثال‌زدنی ارائه می‌دهیم.")
        self.assertNotIn("مثال‌زدنی", result)


# =========================================================================
# T9: Tacked-on analysis clauses
# =========================================================================
class TestT9AnalysisClauses(unittest.TestCase):
    def test_neshan_dahandeye(self) -> None:
        text = "فروش افزایش یافت، که نشان‌دهنده‌ی رشد بازار است."
        result = PersianHumanizer.humanize(text)
        self.assertNotIn("که نشان‌دهنده‌ی", result)

    def test_biangar(self) -> None:
        text = "نتایج مثبت بود، که بیانگر موفقیت می‌باشد."
        result = PersianHumanizer.humanize(text)
        self.assertNotIn("که بیانگر", result)

    def test_haki_az(self) -> None:
        text = "آمار بالا رفت، که حاکی از بهبود است."
        result = PersianHumanizer.humanize(text)
        self.assertNotIn("که حاکی از", result)


# =========================================================================
# T12: Em dashes
# =========================================================================
class TestT12EmDashes(unittest.TestCase):
    def test_em_dash_removed(self) -> None:
        result = PersianHumanizer.humanize("متن — توضیح — ادامه")
        self.assertNotIn("—", result)
        self.assertIn("،", result)

    def test_en_dash_removed(self) -> None:
        result = PersianHumanizer.humanize("متن – توضیح")
        self.assertNotIn("–", result)


# =========================================================================
# T13: Calque phrases
# =========================================================================
class TestT13Calques(unittest.TestCase):
    def test_dar_payane_ruz(self) -> None:
        result = PersianHumanizer.humanize("در پایان روز باید تصمیم بگیریم.")
        self.assertNotIn("در پایان روز", result)
        self.assertIn("در نهایت", result)

    def test_negahi_biandazim(self) -> None:
        result = PersianHumanizer.humanize("نگاهی بیندازیم به نتایج.")
        self.assertIn("ببینیم", result)


# =========================================================================
# T17: Sycophantic chat residue
# =========================================================================
class TestT17Sycophancy(unittest.TestCase):
    def test_soal_besyar_khubi(self) -> None:
        result = PersianHumanizer.humanize("سؤال بسیار خوبی است! بله ممکن است.")
        self.assertNotIn("سؤال بسیار خوبی است!", result)

    def test_omidvaram_mofid(self) -> None:
        result = PersianHumanizer.humanize("امیدوارم مفید بوده باشد.")
        self.assertNotIn("امیدوارم مفید بوده باشد", result)

    def test_khoshal_misham(self) -> None:
        result = PersianHumanizer.humanize("خوشحال می‌شوم کمک کنم. چه سوالی دارید؟")
        self.assertNotIn("خوشحال می‌شوم کمک کنم", result)


# =========================================================================
# Tanvin: Auto-repair Arabic loanwords
# =========================================================================
class TestTanvinRepair(unittest.TestCase):
    def test_all_tanvin_needed_words(self) -> None:
        for bare, correct in TANVIN_NEEDED.items():
            result = PersianHumanizer.humanize(f"او {bare} آمد.")
            self.assertIn(correct, result, f"Failed for {bare} -> {correct}")

    def test_lotfan(self) -> None:
        result = PersianHumanizer.humanize("لطفا این کار را بکنید.")
        self.assertIn("لطفاً", result)

    def test_hatman(self) -> None:
        result = PersianHumanizer.humanize("حتما بیایید.")
        self.assertIn("حتماً", result)

    def test_daghighan(self) -> None:
        result = PersianHumanizer.humanize("دقیقا همین‌طور است.")
        self.assertIn("دقیقاً", result)

    def test_tanvin_already_present_unchanged(self) -> None:
        text = "لطفاً این کار را بکنید."
        result = PersianHumanizer.humanize(text)
        self.assertIn("لطفاً", result)


# =========================================================================
# Fake Tanvin correction
# =========================================================================
class TestFakeTanvin(unittest.TestCase):
    def test_gahan(self) -> None:
        result = PersianHumanizer.humanize("گاهاً این اتفاق می‌افتد.")
        self.assertIn("گاهی", result)
        self.assertNotIn("گاهاً", result)

    def test_doman(self) -> None:
        result = PersianHumanizer.humanize("دوماً باید توجه کرد.")
        self.assertIn("دوم اینکه", result)

    def test_nacharan(self) -> None:
        result = PersianHumanizer.humanize("ناچاراً قبول کردیم.")
        self.assertIn("به‌ناچار", result)

    def test_all_fake_tanvin_words(self) -> None:
        for fake, fix in FAKE_TANVIN.items():
            result = PersianHumanizer.humanize(f"او {fake} رفت.")
            self.assertIn(fix, result, f"Failed for {fake} -> {fix}")


# =========================================================================
# Hekasre detection
# =========================================================================
class TestFindHekasre(unittest.TestCase):
    def test_basic_hekasre_detected(self) -> None:
        results = linter.find_hekasre("کتابه من")
        self.assertTrue(len(results) > 0)
        self.assertIn("کتابِ", results[0][1])

    def test_known_noun_not_flagged(self) -> None:
        results = linter.find_hekasre("خانه من")
        self.assertEqual(len(results), 0, "خانه is a known noun, should not flag")

    def test_multiple_known_nouns_not_flagged(self) -> None:
        for noun in ["برنامه", "نامه", "مدرسه", "پروژه", "مقاله"]:
            results = linter.find_hekasre(f"{noun} من")
            self.assertEqual(len(results), 0, f"{noun} should not be flagged")

    def test_tier_a_non_noun(self) -> None:
        results = linter.find_hekasre("کتابه من")
        tier_a = [r for r in results if r[2] == "A"]
        self.assertTrue(len(tier_a) > 0, "Should have tier A for non-noun stem")

    def test_pronoun_trigger(self) -> None:
        results = linter.find_hekasre("کتابه تو")
        self.assertTrue(len(results) > 0)


# =========================================================================
# End-to-end: StylisticPolishStage.polish integration
# =========================================================================
class TestPolishIntegration(unittest.TestCase):
    def test_polish_removes_mi_bashad(self) -> None:
        result = StylisticPolishStage.polish("این مهم می‌باشد.")
        self.assertNotIn("می‌باشد", result)

    def test_polish_repairs_tanvin(self) -> None:
        result = StylisticPolishStage.polish("لطفا بیایید.")
        self.assertIn("لطفاً", result)

    def test_polish_fixes_fake_tanvin(self) -> None:
        result = StylisticPolishStage.polish("گاهاً اتفاق می‌افتد.")
        self.assertNotIn("گاهاً", result)
        self.assertIn("گاهی", result)

    def test_polish_removes_ceremonial_filler(self) -> None:
        result = StylisticPolishStage.polish("لازم به ذکر است که سیستم فعال است.")
        self.assertNotIn("لازم به ذکر است که", result)

    def test_polish_removes_generic_opener(self) -> None:
        result = StylisticPolishStage.polish("در دنیای امروز فناوری مهم است.")
        self.assertNotIn("در دنیای امروز", result)

    def test_polish_preserves_code_fence(self) -> None:
        code = '```\ntest — code\n```'
        text = f"متن\n{code}\nادامه"
        result = StylisticPolishStage.polish(text)
        self.assertIn(code, result)

    def test_polish_em_dash_zero(self) -> None:
        result = StylisticPolishStage.polish("متن — توضیح")
        self.assertNotIn("—", result)


# =========================================================================
# Linter: hekasre and tanvin categories
# =========================================================================
class TestLinterHekasre(unittest.TestCase):
    def test_linter_detects_hekasre(self) -> None:
        issues = linter.lint_text("کتابه من خوب است.")
        cats = {i.category for i in issues}
        self.assertIn("hekasre", cats)

    def test_linter_no_false_positive_known_noun(self) -> None:
        issues = linter.lint_text("خانه من بزرگ است.")
        hekasre_issues = [i for i in issues if i.category == "hekasre"]
        self.assertEqual(len(hekasre_issues), 0)


class TestLinterTanvin(unittest.TestCase):
    def test_linter_detects_missing_tanvin(self) -> None:
        issues = linter.lint_text("لطفا بیایید.")
        cats = {i.category for i in issues}
        self.assertIn("tanvin", cats)

    def test_linter_detects_fake_tanvin(self) -> None:
        issues = linter.lint_text("گاهاً این اتفاق می‌افتد.")
        tanvin_issues = [i for i in issues if i.category == "tanvin"]
        self.assertTrue(len(tanvin_issues) > 0)

    def test_linter_no_tanvin_when_correct(self) -> None:
        issues = linter.lint_text("لطفاً بیایید.")
        tanvin_issues = [i for i in issues if i.category == "tanvin"]
        self.assertEqual(len(tanvin_issues), 0)


# =========================================================================
# Skill linter: hekasre and tanvin categories
# =========================================================================
class TestSkillLinterHekasre(unittest.TestCase):
    def test_skill_linter_detects_hekasre(self) -> None:
        issues = SKILL_LINTER.lint_text("کتابه من خوب است.")
        cats = {i.category for i in issues}
        self.assertIn("hekasre", cats)

    def test_skill_linter_no_false_positive(self) -> None:
        issues = SKILL_LINTER.lint_text("خانه من بزرگ است.")
        hekasre_issues = [i for i in issues if i.category == "hekasre"]
        self.assertEqual(len(hekasre_issues), 0)


class TestSkillLinterTanvin(unittest.TestCase):
    def test_skill_linter_detects_missing_tanvin(self) -> None:
        issues = SKILL_LINTER.lint_text("لطفا بیایید.")
        cats = {i.category for i in issues}
        self.assertIn("tanvin", cats)

    def test_skill_linter_detects_fake_tanvin(self) -> None:
        issues = SKILL_LINTER.lint_text("گاهاً رخ می‌دهد.")
        tanvin_issues = [i for i in issues if i.category == "tanvin"]
        self.assertTrue(len(tanvin_issues) > 0)


# =========================================================================
# Version check
# =========================================================================
class TestVersion(unittest.TestCase):
    def test_version_is_2_3_0(self) -> None:
        import tarjoman
        self.assertEqual(tarjoman.__version__, "2.3.0")

    def test_pyproject_version(self) -> None:
        # tomllib is stdlib only from Python 3.11; the package supports 3.10.
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pyproject.toml"
        )
        with open(path, encoding="utf-8") as f:
            match = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "2.3.0")


# =========================================================================
# Empty / edge-case inputs
# =========================================================================
class TestEdgeCases(unittest.TestCase):
    def test_empty_string(self) -> None:
        self.assertEqual(PersianHumanizer.humanize(""), "")

    def test_none_safe(self) -> None:
        # polish() should handle empty gracefully
        self.assertEqual(StylisticPolishStage.polish(""), "")

    def test_pure_code_unchanged(self) -> None:
        code = '```\nx = 1\ny = 2\n```'
        result = PersianHumanizer.humanize(code)
        self.assertEqual(result, code)

    def test_no_persian_text_passthrough(self) -> None:
        text = "Hello world. This is English only."
        result = PersianHumanizer.humanize(text)
        # Should pass through (no Persian tells to fix)
        self.assertEqual(result, text)


if __name__ == "__main__":
    unittest.main()
