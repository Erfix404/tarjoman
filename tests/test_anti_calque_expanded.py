"""
Tests for the expanded Anti-Calque & Typography Engine (Super-Skill v2).

Covers:
- Najafi/Samii syntactic rules: generic passive-by fallback, می‌باشد,
  گردید, دارای, orthographic joins (درحالی‌که/از آنجا که/بنابراین),
  به‌عنوان joining
- Najafi/Samii lexical rules: به اجرا درآوردن, به کار گرفتن, اعمال کردن,
  به عمل آوردن, اقدام/مبادرت به, مورد استفاده قرار دادن, در اختیار قرار دادن,
  تحت پوشش قرار دادن, در رابطه با, جهت→برای, عنوان کردن, قلمداد/تلقی کردن
- Backward compatibility: the original 12 rules keep their exact behavior
- Guaranteed ZERO em-dash policy: —, –, and standalone -- eliminated;
  paired dashes become parentheses, lone dashes become Persian commas
- Persian guillemets: straight/curly/single quotes → «»
- Strict ZWNJ: verbal prefixes, ب/ن prefixes, plurals, comparatives,
  clitics, ه‌ای, silent-heh ezafe ی
- Arabic character normalization: ي→ی, ك→ک, ى→ی, ة→ه, tatweel removal
- Expanded detect_calques coverage
"""
from __future__ import annotations

import unittest

from tarjoman.stages.anti_calque import (
    AntiCalqueEngine,
    mask_verbatim_spans,
    restore_verbatim_spans,
)


class TestOriginalTwelveRulesPreserved(unittest.TestCase):
    """The original 12 transformations keep their exact v1 behavior."""

    def test_passive_by_specific(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("کتاب توسط نویسنده نوشته شد.")
        self.assertNotIn("توسط", cleaned)
        self.assertIn("به دست نویسنده نوشته شد", cleaned)

    def test_play_role(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("این عامل نقش مهمی بازی کرد.")
        self.assertNotIn("بازی کرد", cleaned)
        self.assertIn("ایفا کرد", cleaned)

    def test_count_on(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("روی او حساب کن.")
        self.assertNotIn("حساب کن", cleaned)
        self.assertIn("به او اعتماد کن", cleaned)

    def test_end_of_day(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("در پایان روز باید تصمیم بگیریم.")
        self.assertNotIn("در پایان روز", cleaned)
        self.assertIn("در نهایت", cleaned)

    def test_makes_sense(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("این نظریه کاملاً حس ایجاد می‌کند.")
        self.assertNotIn("حس ایجاد می‌کند", cleaned)
        self.assertIn("منطقی است", cleaned)

    def test_legitimate_makes_sense_untouched(self) -> None:
        legit = "عشق به جهان معنا می‌دهد."
        self.assertEqual(AntiCalqueEngine.eliminate_calques(legit), legit)

    def test_act_as(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("او به عنوان مدیر عمل کرد.")
        self.assertNotIn("عمل کرد", cleaned)
        self.assertIn("در جایگاه مدیر بود", cleaned)

    def test_make_decision(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("آن‌ها یک تصمیم گرفتند.")
        self.assertNotIn("یک تصمیم گرفتند", cleaned)
        self.assertIn("تصمیمی اتخاذ کردند", cleaned)

    def test_open_fire(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("نیروها به سوی دشمن آتش گشودند.")
        self.assertNotIn("آتش گشودند", cleaned)
        self.assertIn("شلیک کردند", cleaned)

    def test_take_bath(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("او هر روز صبح حمام می‌گیرد.")
        self.assertNotIn("حمام می‌گیرد", cleaned)
        self.assertIn("دوش می‌گیرد", cleaned)

    def test_point_of_view(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("نقطه نظرات کارشناسان بررسی شد.")
        self.assertNotIn("نقطه نظرات", cleaned)
        self.assertIn("دیدگاه‌ها", cleaned)

    def test_green_light(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("مدیریت چراغ سبز نشان داد.")
        self.assertNotIn("چراغ سبز نشان داد", cleaned)
        self.assertIn("موافقت کرد", cleaned)

    def test_end_of_line(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("مذاکرات صلح به پایان خط رسید.")
        self.assertNotIn("به پایان خط رسید", cleaned)
        self.assertIn("به بن‌بست رسید", cleaned)


class TestSyntacticCalquesV2(unittest.TestCase):
    """Najafi/Samii syntactic rules introduced in Super-Skill v2."""

    def test_generic_passive_by_fallback(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("این طرح توسط کمیته بررسی شد.")
        self.assertNotIn("توسط", cleaned)
        self.assertIn("به دست کمیته بررسی شد", cleaned)

    def test_generic_passive_by_az_sou(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("بیانیه از سوی سخنگو منتشر شد.")
        self.assertNotIn("از سوی", cleaned)
        self.assertIn("به دست سخنگو منتشر شد", cleaned)

    def test_generic_passive_preserves_simple_tavassot(self) -> None:
        # A bare «توسط» without a passive verb stays (no false active rewrite).
        text = "او توسط دوستش آمد."
        self.assertEqual(AntiCalqueEngine.eliminate_calques(text), text)

    def test_mibashad_copula(self) -> None:
        self.assertIn(
            "است",
            AntiCalqueEngine.eliminate_calques("این گزارش دقیق می‌باشد."),
        )
        cleaned = AntiCalqueEngine.eliminate_calques("این گزارش دقیق می‌باشد.")
        self.assertNotIn("می‌باشد", cleaned)

        plural = AntiCalqueEngine.eliminate_calques("آن‌ها آماده می‌باشند.")
        self.assertNotIn("می‌باشند", plural)
        self.assertIn("هستند", plural)

    def test_gardid_archaic_passive(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("این قانون تصویب گردید.")
        self.assertNotIn("گردید", cleaned)
        self.assertIn("شد", cleaned)

    def test_daraye_possession(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("این سازمان دارای اعتبار است.")
        self.assertNotIn("دارای", cleaned)
        self.assertIn("اعتبار دارد", cleaned)

    def test_orthographic_joins(self) -> None:
        self.assertIn(
            "درحالی‌که",
            AntiCalqueEngine.eliminate_calques("او رفت در حالی که باران می‌بارید."),
        )
        self.assertIn(
            "از آنجا که",
            AntiCalqueEngine.eliminate_calques("او ماند از آنجایی که خسته بود."),
        )
        self.assertIn(
            "بنابراین",
            AntiCalqueEngine.eliminate_calques("باران آمد بنا بر این ماندیم."),
        )

    def test_be_onvan_join(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("او به عنوان نویسنده شناخته می‌شود.")
        self.assertIn("به‌عنوان", cleaned)

    def test_vasila_normalization(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("کار به وسیله او انجام شد.")
        self.assertNotIn("به وسیله", cleaned)


class TestLexicalCalquesV2(unittest.TestCase):
    """Najafi/Samii lexical rules introduced in Super-Skill v2."""

    def test_be_ejra_daravardan(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("آن‌ها طرح را به اجرا درآوردند.")
        self.assertNotIn("به اجرا درآوردند", cleaned)
        self.assertIn("اجرا کردند", cleaned)

    def test_be_kar_gereftan(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("او این روش را به کار گرفت.")
        self.assertNotIn("به کار گرفت", cleaned)
        self.assertIn("به کار برد", cleaned)

    def test_emal_kardan(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("آن‌ها فشار را اعمال کردند.")
        self.assertNotIn("اعمال کردند", cleaned)
        self.assertIn("اجرا کردند", cleaned)

    def test_be_amal_avardan(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("او کار را به عمل آورد.")
        self.assertNotIn("به عمل آورد", cleaned)
        self.assertIn("انجام داد", cleaned)

    def test_eghdam_be(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("او اقدام به ترک کرد.")
        self.assertNotIn("اقدام به", cleaned)
        self.assertIn("ترک کرد", cleaned)

    def test_morde_estefade(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("این ابزار مورد استفاده قرار گرفت.")
        self.assertNotIn("مورد استفاده قرار گرفت", cleaned)
        self.assertIn("به کار رفت", cleaned)

    def test_dar_ekhtiyar(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("کتاب را در اختیار نهاد قرار داد.")
        self.assertNotIn("قرار داد", cleaned)
        self.assertIn("گذاشت", cleaned)

    def test_tahte_pushesh(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("بیمار تحت پوشش قرار داده شد.")
        self.assertNotIn("قرار داده شد", cleaned)

    def test_dar_rabete(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("در رابطه با این موضوع صحبت کردیم.")
        self.assertNotIn("در رابطه با", cleaned)
        self.assertIn("درباره", cleaned)

    def test_jahat_purpose(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("جهت اطلاع شما می‌گویم.")
        self.assertNotIn("جهت اطلاع", cleaned)
        self.assertIn("برای اطلاع", cleaned)

    def test_jahat_guarded_compounds(self) -> None:
        # از جهت / بدین جهت / جهتِ+X (direction sense) must not change.
        self.assertEqual(
            AntiCalqueEngine.eliminate_calques("از جهت شمال آمد."),
            "از جهت شمال آمد.",
        )

    def test_onvan_kardan(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("مسئله را عنوان کرد.")
        self.assertNotIn("عنوان کرد", cleaned)
        self.assertIn("مطرح کرد", cleaned)

    def test_ghalamdad_kardan(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_calques("او را مقصر قلمداد کرد.")
        self.assertNotIn("قلمداد کرد", cleaned)
        self.assertIn("دانست", cleaned)


class TestZeroEmDashPolicy(unittest.TestCase):
    """Guaranteed ZERO em-dash: no —, –, or standalone -- may survive."""

    def test_lone_em_dash_becomes_persian_comma(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_em_dashes("او آمد — خسته و تنها.")
        self.assertNotIn("—", cleaned)
        self.assertNotIn("–", cleaned)
        self.assertIn("،", cleaned)

    def test_en_dash_eliminated(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_em_dashes("سال‌های ۱۳۵۰ – ۱۳۶۰ شمسی.")
        self.assertNotIn("–", cleaned)
        self.assertNotIn("—", cleaned)

    def test_standalone_double_hyphen_eliminated(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_em_dashes("هوا تاریک بود -- خیلی تاریک.")
        self.assertNotIn("--", cleaned)
        self.assertNotIn("—", cleaned)

    def test_paired_dashes_become_parentheses(self) -> None:
        cleaned = AntiCalqueEngine.eliminate_em_dashes("او آمد — خسته — و رفت.")
        self.assertNotIn("—", cleaned)
        self.assertIn("(", cleaned)
        self.assertIn(")", cleaned)
        self.assertIn("خسته", cleaned)

    def test_cli_flags_preserved(self) -> None:
        text = "run with --output file --verbose mode"
        self.assertEqual(AntiCalqueEngine.eliminate_em_dashes(text), text)

    def test_idempotent_and_complete(self) -> None:
        samples = [
            "الف — ب",
            "الف – ب",
            "الف -- ب",
            "الف — ب — ج",
        ]
        for sample in samples:
            once = AntiCalqueEngine.eliminate_em_dashes(sample)
            twice = AntiCalqueEngine.eliminate_em_dashes(once)
            self.assertNotIn("—", once)
            self.assertNotIn("–", once)
            self.assertNotIn("--", once.replace("—", ""))
            self.assertEqual(once, twice)


class TestPersianGuillemets(unittest.TestCase):
    """Straight/curly/single quotes all become «»."""

    def test_ascii_double_quotes(self) -> None:
        self.assertEqual(
            AntiCalqueEngine.normalize_quotes('او گفت: "سلام."'),
            "او گفت: «سلام.»",
        )

    def test_curly_double_quotes(self) -> None:
        self.assertEqual(
            AntiCalqueEngine.normalize_quotes("او گفت: “سلام.”"),
            "او گفت: «سلام.»",
        )

    def test_single_quotes(self) -> None:
        self.assertEqual(
            AntiCalqueEngine.normalize_quotes("او گفت: 'سلام.'"),
            "او گفت: «سلام.»",
        )

    def test_apostrophe_preserved(self) -> None:
        text = "children's books are fun"
        self.assertEqual(AntiCalqueEngine.normalize_quotes(text), text)


class TestStrictZwnj(unittest.TestCase):
    """ZWNJ normalization: verbs, prefixes, plurals, comparatives, clitics."""

    def test_verbal_prefixes(self) -> None:
        zwnj = "‌"
        self.assertEqual(
            AntiCalqueEngine.normalize_zwnj("او می رود و نمی داند"),
            f"او می{zwnj}رود و نمی{zwnj}داند",
        )

    def test_subjunctive_prefix(self) -> None:
        zwnj = "‌"
        self.assertEqual(
            AntiCalqueEngine.normalize_zwnj("ب خوان و ن رو"),
            f"ب{zwnj}خوان و ن{zwnj}رو",
        )

    def test_plural_suffix(self) -> None:
        zwnj = "‌"
        self.assertEqual(
            AntiCalqueEngine.normalize_zwnj("کتاب ها خوب است"),
            f"کتاب{zwnj}ها خوب است",
        )

    def test_comparative_suffix(self) -> None:
        zwnj = "‌"
        self.assertEqual(
            AntiCalqueEngine.normalize_zwnj("بزرگ تر است"),
            f"بزرگ{zwnj}تر است",
        )

    def test_pronominal_clitic(self) -> None:
        zwnj = "‌"
        out = AntiCalqueEngine.normalize_zwnj("کتاب ام را بده")
        self.assertIn(f"کتاب{zwnj}ام", out)

    def test_indefinite_hae(self) -> None:
        zwnj = "‌"
        self.assertEqual(
            AntiCalqueEngine.normalize_zwnj("خانه ای زیبا"),
            f"خانه{zwnj}ای زیبا",
        )

    def test_silent_heh_ezafe(self) -> None:
        zwnj = "‌"
        self.assertEqual(
            AntiCalqueEngine.normalize_zwnj("خانه ی من"),
            f"خانه{zwnj}ی من",
        )

    def test_be_yaad_not_joined(self) -> None:
        # «به یاد» keeps its space (exclusion guard).
        self.assertEqual(AntiCalqueEngine.normalize_zwnj("به یاد او"), "به یاد او")


class TestArabicNormalization(unittest.TestCase):
    """Arabic letters unmasked to standard Persian characters."""

    def test_kaf_and_ya(self) -> None:
        out = AntiCalqueEngine.standardize_arabic_chars("كتاب علمي")
        self.assertEqual(out, "کتاب علمی")
        self.assertNotIn("ك", out)
        self.assertNotIn("ي", out)

    def test_alef_maqsura_and_ta_marbuta(self) -> None:
        out = AntiCalqueEngine.standardize_arabic_chars("على مدرسة")
        self.assertNotIn("ى", out)
        self.assertNotIn("ة", out)

    def test_tatweel_removed(self) -> None:
        out = AntiCalqueEngine.standardize_arabic_chars("کتـاب")
        self.assertNotIn("ـ", out)
        self.assertEqual(out, "کتاب")


class TestDetectCalquesExpanded(unittest.TestCase):
    """detect_calques covers the v2 Najafi/Samii rules too."""

    def test_v2_rules_detected(self) -> None:
        text = (
            "این طرح توسط کمیته بررسی شد و می‌باشد و به اجرا درآورده شد "
            "و مورد استفاده قرار گرفت درباره جهت اطلاع."
        )
        detected = AntiCalqueEngine.detect_calques(text)
        joined = " ".join(detected)
        self.assertIn("توسط", joined)
        self.assertIn("می‌باشد", joined)
        self.assertIn("به اجرا درآورده", joined)
        self.assertIn("مورد استفاده قرار گرفت", joined)

    def test_clean_text_detects_nothing(self) -> None:
        clean = "او با لبخندی آرام گفت: «این متن پاکیزه است.»"
        self.assertEqual(AntiCalqueEngine.detect_calques(clean), [])


class TestNormalizeTypographyPipeline(unittest.TestCase):
    """The one-call typography pipeline composes all normalizers."""

    def test_end_to_end(self) -> None:
        raw = 'او گفت: "سلام — دوست من" و كتاب علمي را خواند.'
        out = AntiCalqueEngine.normalize_persian_typography(raw)
        self.assertNotIn("—", out)
        self.assertNotIn('"', out)
        self.assertNotIn("ك", out)
        self.assertNotIn("ي", out)
        self.assertIn("«", out)
        self.assertIn("»", out)

    def test_verbatim_mask_roundtrip(self) -> None:
        raw = "ببین `code --flag` و $E=mc^2$ را نگه دار."
        masked, table = mask_verbatim_spans(raw)
        self.assertIn("⟦VERBATIM_", masked)
        self.assertEqual(restore_verbatim_spans(masked, table), raw)


if __name__ == "__main__":
    unittest.main()
