"""
Tests for Linguistic Anti-Calque Engine and Stylistic Polish Stage.
"""
import unittest

from tarjoman.core.contracts import (
    DomainProfile,
    DomainType,
    EmDashPolicy,
    TextSegment,
    TypographicRules,
)
from tarjoman.domains.router import DomainRegistry, DomainRouter
from tarjoman.stages.anti_calque import AntiCalqueEngine
from tarjoman.stages.stage4_polish import StylisticPolishStage


class TestAntiCalqueEngine(unittest.TestCase):
    """Unit tests for AntiCalqueEngine transformations and detection."""

    def test_passive_by_calque_removal(self):
        """Test passive 'توسط' removal and conversion to active/idiomatic form."""
        bad = "کتاب توسط نویسنده نوشته شد."
        cleaned = AntiCalqueEngine.eliminate_calques(bad)
        self.assertNotIn("توسط", cleaned)
        self.assertIn("به دست نویسنده نوشته شد", cleaned)

        # Additional passive tests
        bad2 = "این لایحه توسط مجلس تصویب شد."
        cleaned2 = AntiCalqueEngine.eliminate_calques(bad2)
        self.assertNotIn("توسط", cleaned2)
        self.assertIn("به دست مجلس تصویب شد", cleaned2)

        bad3 = "پل توسط مهندسان ساخته شد."
        cleaned3 = AntiCalqueEngine.eliminate_calques(bad3)
        self.assertNotIn("توسط", cleaned3)
        self.assertIn("به دست مهندسان ساخته شد", cleaned3)

    def test_play_role_calque_removal(self):
        """Test 'نقش بازی کردن' -> 'ایفا کردن' / 'سهم داشتن'."""
        bad = "او یک نقش کلیدی در پروژه بازی می‌کند."
        cleaned = AntiCalqueEngine.eliminate_calques(bad)
        self.assertNotIn("بازی می‌کند", cleaned)
        self.assertTrue("ایفا می‌کند" in cleaned or "دارد" in cleaned)

        bad2 = "این عامل نقش مهمی بازی کرد."
        cleaned2 = AntiCalqueEngine.eliminate_calques(bad2)
        self.assertNotIn("بازی کرد", cleaned2)
        self.assertIn("ایفا کرد", cleaned2)

        # Spaced prefix (می کند)
        bad_spaced = "او نقش مهمی بازی می کند"
        cleaned_spaced = AntiCalqueEngine.eliminate_calques(bad_spaced)
        self.assertNotIn("بازی می کند", cleaned_spaced)
        self.assertNotIn("بازی می‌کند", cleaned_spaced)
        self.assertIn("ایفا می‌کند", cleaned_spaced)

    def test_count_on_calque_removal(self):
        """Test 'روی کسی حساب کردن' -> 'به کسی اعتماد کردن'."""
        bad = "روی او حساب کن."
        cleaned = AntiCalqueEngine.eliminate_calques(bad)
        self.assertNotIn("حساب کن", cleaned)
        self.assertIn("به او اعتماد کن", cleaned)

        bad2 = "روی کمک من حساب نکن."
        cleaned2 = AntiCalqueEngine.eliminate_calques(bad2)
        self.assertNotIn("حساب نکن", cleaned2)
        self.assertIn("به کمک من اعتماد نکن", cleaned2)

        bad3 = "روی کسی حساب کردن در این شرایط اشتباه است."
        cleaned3 = AntiCalqueEngine.eliminate_calques(bad3)
        self.assertNotIn("حساب کردن", cleaned3)
        self.assertIn("به کسی اعتماد کردن", cleaned3)

    def test_end_of_day_is_detected_not_rewritten(self):
        """'در پایان روز' is often literal, so it is only detected."""
        text = "در پایان روز به خانه برگشتیم."
        self.assertEqual(AntiCalqueEngine.eliminate_calques(text), text)
        self.assertIn("در پایان روز", AntiCalqueEngine.detect_calques(text))

    def test_makes_sense_calque_removal(self):
        """Test 'حس ایجاد می‌کند' / contextual 'این ادعا معنا می‌دهد' -> 'منطقی است'."""
        bad = "این نظریه کاملاً حس ایجاد می‌کند."
        cleaned = AntiCalqueEngine.eliminate_calques(bad)
        self.assertNotIn("حس ایجاد می‌کند", cleaned)
        self.assertIn("منطقی است", cleaned)

        bad_neg = "این ادعا حس ایجاد نمی‌کند."
        cleaned_neg = AntiCalqueEngine.eliminate_calques(bad_neg)
        self.assertNotIn("حس ایجاد نمی‌کند", cleaned_neg)
        self.assertIn("منطقی نیست", cleaned_neg)

        bad_meaning = "این ادعا معنا می‌دهد."
        cleaned_meaning = AntiCalqueEngine.eliminate_calques(bad_meaning)
        self.assertNotIn("معنا می‌دهد", cleaned_meaning)
        self.assertIn("این ادعا منطقی است", cleaned_meaning)

        # Ensure legitimate usage is NOT corrupted
        legit = "عشق به جهان معنا می‌دهد."
        cleaned_legit = AntiCalqueEngine.eliminate_calques(legit)
        self.assertEqual(cleaned_legit, legit)

    def test_additional_calques(self):
        """Test remaining Najafi/Samii banned calques."""
        # به عنوان عمل کردن
        bad_act = "او به عنوان مدیر عمل کرد."
        cleaned_act = AntiCalqueEngine.eliminate_calques(bad_act)
        self.assertNotIn("عمل کرد", cleaned_act)
        self.assertIn("در جایگاه مدیر بود", cleaned_act)

        # یک تصمیم گرفتن
        bad_dec = "آن‌ها یک تصمیم گرفتند."
        cleaned_dec = AntiCalqueEngine.eliminate_calques(bad_dec)
        self.assertNotIn("یک تصمیم گرفتند", cleaned_dec)
        self.assertIn("تصمیمی اتخاذ کردند", cleaned_dec)

        # آتش گشودن
        bad_fire = "نیروها به سوی دشمن آتش گشودند."
        cleaned_fire = AntiCalqueEngine.eliminate_calques(bad_fire)
        self.assertNotIn("آتش گشودند", cleaned_fire)
        self.assertIn("شلیک کردند", cleaned_fire)

        # حمام گرفتن
        bad_bath = "او هر روز صبح حمام می‌گیرد."
        cleaned_bath = AntiCalqueEngine.eliminate_calques(bad_bath)
        self.assertNotIn("حمام می‌گیرد", cleaned_bath)
        self.assertIn("دوش می‌گیرد", cleaned_bath)

        # نقطه نظر(ات)
        bad_pov = "نقطه نظرات کارشناسان بررسی شد."
        cleaned_pov = AntiCalqueEngine.eliminate_calques(bad_pov)
        self.assertNotIn("نقطه نظرات", cleaned_pov)
        self.assertIn("دیدگاه‌ها", cleaned_pov)

        # چراغ سبز نشان دادن
        bad_green = "مدیریت چراغ سبز نشان داد."
        cleaned_green = AntiCalqueEngine.eliminate_calques(bad_green)
        self.assertNotIn("چراغ سبز نشان داد", cleaned_green)
        self.assertIn("موافقت کرد", cleaned_green)

        # به پایان خط رسیدن
        bad_end = "مذاکرات صلح به پایان خط رسید."
        cleaned_end = AntiCalqueEngine.eliminate_calques(bad_end)
        self.assertNotIn("به پایان خط رسید", cleaned_end)
        self.assertIn("به بن‌بست رسید", cleaned_end)

    def test_detect_calques(self):
        """Test detect_calques returns all matching banned phrases."""
        text = "در پایان روز روی او حساب کن و بدان که این طرح حس ایجاد می‌کند."
        detected = AntiCalqueEngine.detect_calques(text)
        self.assertGreaterEqual(len(detected), 3)
        self.assertTrue(any("در پایان روز" in d for d in detected))
        self.assertTrue(any("روی او حساب کن" in d for d in detected))
        self.assertTrue(any("حس ایجاد می‌کند" in d for d in detected))


class TestStylisticPolishStage(unittest.TestCase):
    """Unit tests for StylisticPolishStage typography and hygiene rules."""

    def test_dialogue_inversion(self):
        """Test dialogue tag inversion to subject-first syntax."""
        bad = '«ما باید برویم،» هری با نگرانی زمزمه کرد.'
        profile = DomainProfile(
            id=DomainType.LITERARY,
            title_fa="ادبی",
            description="",
            system_prompt="",
            typography=TypographicRules(invert_dialogue_tags=True, enforce_persian_quotes=True),
        )
        stage = StylisticPolishStage()
        res = stage.process([TextSegment(id=1, source_text="", translated_text=bad)], profile)
        self.assertTrue(res.segments[0].polished_text.startswith("هری با نگرانی زمزمه کرد:"))
        self.assertIn("«ما باید برویم.»", res.segments[0].polished_text)

        # Test exact prompt pattern: «...» هری با نگرانی گفت. -> هری با نگرانی گفت: «...»
        bad2 = '«...» هری با نگرانی گفت.'
        res2 = stage.process([TextSegment(id=2, source_text="", translated_text=bad2)], profile)
        self.assertEqual(res2.segments[0].polished_text, 'هری با نگرانی گفت: «...»')

        # Test plural speech verbs
        plural_text = '«کجا می‌روید؟» آنها پرسیدند.'
        res_plural = stage.process([TextSegment(id=3, source_text="", translated_text=plural_text)], profile)
        self.assertEqual(res_plural.segments[0].polished_text, 'آنها پرسیدند: «کجا می‌روید؟»')

        # Test consecutive dialogues without period swallowing
        multi_dialogue = '«سلام» هری گفت. «خداحافظ» ران گفت.'
        res_multi = stage.process([TextSegment(id=4, source_text="", translated_text=multi_dialogue)], profile)
        self.assertEqual(res_multi.segments[0].polished_text, 'هری گفت: «سلام.» ران گفت: «خداحافظ.»')

    def test_em_dash_handling(self):
        """Test ERADICATE, ADAPT, and PRESERVE em-dash policies."""
        text = "او آمد — خسته و تنها."

        # ERADICATE -> ،
        eradicated = StylisticPolishStage.apply_em_dash_policy(text, EmDashPolicy.ERADICATE)
        self.assertNotIn("—", eradicated)
        self.assertIn("،", eradicated)

        # ADAPT -> -
        adapted = StylisticPolishStage.apply_em_dash_policy(text, EmDashPolicy.ADAPT)
        self.assertNotIn("—", adapted)
        self.assertIn(" - ", adapted)

        # PRESERVE -> keeps —
        preserved = StylisticPolishStage.apply_em_dash_policy(text, EmDashPolicy.PRESERVE)
        self.assertIn("—", preserved)

    def test_persian_quotes_enforcement(self):
        """Test conversion of ASCII/curly double quotes to «...»."""
        ascii_text = 'او گفت: "این یک کتاب است."'
        converted = StylisticPolishStage.enforce_persian_quotes(ascii_text)
        self.assertEqual(converted, "او گفت: «این یک کتاب است.»")

        curly_text = "او گفت: “این یک کتاب است.”"
        converted_curly = StylisticPolishStage.enforce_persian_quotes(curly_text)
        self.assertEqual(converted_curly, "او گفت: «این یک کتاب است.»")

    def test_strict_zwnj(self):
        """Test strict ZWNJ insertion for prefixes, suffixes, and clitics."""
        zwnj = "‌"

        # Verbal prefix می‌ and نمی‌
        t1 = StylisticPolishStage.enforce_strict_zwnj("او می رود و نمی داند")
        self.assertEqual(t1, f"او می{zwnj}رود و نمی{zwnj}داند")

        # Plural suffixes ها and های
        t2 = StylisticPolishStage.enforce_strict_zwnj("کتاب ها و کتاب های خوب")
        self.assertEqual(t2, f"کتاب{zwnj}ها و کتاب{zwnj}های خوب")

        # Comparative suffixes تر and ترین
        t3 = StylisticPolishStage.enforce_strict_zwnj("بزرگ تر و سریع ترین راه")
        self.assertEqual(t3, f"بزرگ{zwnj}تر و سریع{zwnj}ترین راه")

        # Pronominal clitics
        t4 = StylisticPolishStage.enforce_strict_zwnj("کتاب ام و خانه ات و دست اش و دوست مان و کار تان و شهر شان")
        self.assertIn(f"کتاب{zwnj}ام", t4)
        self.assertIn(f"خانه{zwnj}ات", t4)
        self.assertIn(f"دست{zwnj}اش", t4)
        self.assertIn(f"دوست{zwnj}مان", t4)
        self.assertIn(f"کار{zwnj}تان", t4)
        self.assertIn(f"شهر{zwnj}شان", t4)

        # Indefinite suffix ه‌ای
        t5 = StylisticPolishStage.enforce_strict_zwnj("خانه ای زیبا و پرنده ای کوچک")
        self.assertEqual(t5, f"خانه{zwnj}ای زیبا و پرنده{zwnj}ای کوچک")

    def test_arabic_standardization(self):
        """Test standardization of Arabic kaf (ك) and ya (ي) to Persian characters."""
        arabic_text = "كتاب علمي و پزشكي"
        persian_text = StylisticPolishStage.standardize_arabic_chars(arabic_text)
        self.assertEqual(persian_text, "کتاب علمی و پزشکی")
        self.assertNotIn("ك", persian_text)
        self.assertNotIn("ي", persian_text)

    def test_punctuation_hygiene(self):
        """Test duplicate commas and spacing cleanup."""
        messy = "این متن ،، خیلی سریع ، نوشته شد .آیا موافقید ؟"
        clean = StylisticPolishStage.clean_punctuation_hygiene(messy)
        self.assertNotIn("،،", clean)
        self.assertNotIn(" ،", clean)
        self.assertNotIn(" .", clean)
        self.assertNotIn(" ؟", clean)
        self.assertIn("، ", clean)

        # Colon spacing before Persian quote
        colon_quote = "گفت:«سلام»"
        clean_colon = StylisticPolishStage.clean_punctuation_hygiene(colon_quote)
        self.assertEqual(clean_colon, "گفت: «سلام»")


class TestRouterReviewFixes(unittest.TestCase):
    """Tests for quick fixes in router.py from Task 2 review."""

    def test_novel_substring_collision_prevention(self):
        """Ensure 'درمان' or 'فرمان' does not falsely trigger 'رمان' pattern."""
        router = DomainRouter()
        # Text containing medical terms including درمان
        medical_sample = "پزشک برای درمان بیمار نسخه نوشت و دوز دارو را مشخص کرد."
        profile, conf = router.route(medical_sample)
        self.assertEqual(profile.id, DomainType.MEDICAL)

        # Pure literary text containing standalone رمان
        literary_sample = "این رمان زیبا با زبانی دلنشین داستان را روایت می‌کند."
        profile_lit, _ = router.route(literary_sample)
        self.assertEqual(profile_lit.id, DomainType.LITERARY)

    def test_override_arabic_normalization(self):
        """Ensure overrides with Arabic ي and ك resolve correctly."""
        router = DomainRouter()
        # Override with Arabic ي (علمي)
        p1, conf1 = router.route("sample text", override="علمي")
        self.assertEqual(p1.id, DomainType.SCIENTIFIC)
        self.assertEqual(conf1, 1.0)

        # Override with Arabic ك and ي (پزشكي)
        p2, conf2 = router.route("sample text", override="پزشكي")
        self.assertEqual(p2.id, DomainType.MEDICAL)
        self.assertEqual(conf2, 1.0)

    def test_list_all_ordered_by_domain_type(self):
        """Ensure list_all() returns profiles ordered strictly by DomainType enum."""
        registry = DomainRegistry()
        profiles = registry.list_all()
        expected_ids = [domain for domain in DomainType]
        actual_ids = [p.id for p in profiles]
        self.assertEqual(expected_ids, actual_ids)


if __name__ == "__main__":
    unittest.main()
