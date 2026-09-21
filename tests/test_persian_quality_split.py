"""
Tests for Work Package FND-009: Persian Quality Split.

Verifies:
1. Auto-Fix Safe Normalization Layer (idempotence invariant, Arabic normalization,
   ZWNJ hygiene, punctuation hygiene, zero em-dash policy).
2. Diagnostic Calque Detection Layer (D09 non-destructive inspection, structured QualityFinding).
3. False-Positive Regression Protections (authentic Persian idioms, literal contexts, code blocks).
4. Backward Compatibility with existing stages and contracts.
"""
from __future__ import annotations

import unittest

from tarjoman.quality import (
    CalqueDetector,
    PersianNormalizer,
    QualityFinding,
    detect_calques,
    normalize_persian,
)
from tarjoman.stages.anti_calque import AntiCalqueEngine


class TestPersianNormalizationIdempotence(unittest.TestCase):
    """Verifies strict idempotence: normalize(normalize(text)) == normalize(text)."""

    def setUp(self) -> None:
        self.normalizer = PersianNormalizer()

    def test_idempotence_clean_text(self) -> None:
        """Clean Persian text remains unchanged across single and double pass."""
        text = "این یک متن تمیز و فصیح فارسی است که هیچ ایرادی ندارد."
        p1 = self.normalizer.normalize(text)
        p2 = self.normalizer.normalize(p1)
        self.assertEqual(p1, text)
        self.assertEqual(p2, text)

    def test_idempotence_empty_and_whitespace(self) -> None:
        """Empty and whitespace-only strings normalize idempotently."""
        self.assertEqual(self.normalizer.normalize(""), "")
        self.assertEqual(self.normalizer.normalize("   "), "")
        self.assertEqual(self.normalizer.normalize("\n\n\t  \n"), "")
        self.assertEqual(normalize_persian(""), "")

    def test_idempotence_arabic_chars(self) -> None:
        """Arabic Kaf, Yeh, Teh Marbuta, and Heh-Yeh normalize idempotently."""
        raw = "كتاب علمي و پزشكي در دانشگاه با ارادة و تجربة اساتيد و خانۀ زيبا."
        p1 = self.normalizer.normalize(raw)
        p2 = self.normalizer.normalize(p1)
        self.assertEqual(p1, p2)
        # Check standard Persian characters are present
        self.assertNotIn("ك", p1)
        self.assertNotIn("ي", p1)
        self.assertIn("کتاب علمی و پزشکی", p1)
        self.assertIn("اراده و تجربه", p1)
        self.assertIn("خانهٔ", p1)

    def test_idempotence_zwnj_prefixes(self) -> None:
        """Verbal prefixes (می‌ and نمی‌) normalize with ZWNJ and remain idempotent."""
        raw = "او می رود و نمی داند که آنها چه می کنند و چه نمی گویند."
        p1 = self.normalizer.normalize(raw)
        p2 = self.normalizer.normalize(p1)
        self.assertEqual(p1, p2)
        z = "‌"
        self.assertIn(f"می{z}رود", p1)
        self.assertIn(f"نمی{z}داند", p1)
        self.assertIn(f"می{z}کنند", p1)
        self.assertIn(f"نمی{z}گویند", p1)

    def test_idempotence_zwnj_suffixes(self) -> None:
        """Plural, comparative, indefinite, and pronominal suffixes normalize idempotently."""
        raw = "کتاب ها و کتاب هایم و بزرگ تر و سریع ترین راه در خانه ای زیبا با دست اش."
        p1 = self.normalizer.normalize(raw)
        p2 = self.normalizer.normalize(p1)
        self.assertEqual(p1, p2)
        z = "‌"
        self.assertIn(f"کتاب{z}ها", p1)
        self.assertIn(f"کتاب{z}هایم", p1)
        self.assertIn(f"بزرگ{z}تر", p1)
        self.assertIn(f"سریع{z}ترین", p1)
        self.assertIn(f"خانه{z}ای", p1)
        self.assertIn(f"دست{z}اش", p1)

    def test_idempotence_zwnj_deduplication_and_boundary_cleanup(self) -> None:
        """Duplicate ZWNJs and boundary ZWNJs are cleaned idempotently."""
        raw = "متن با ‌‌‌ سه نیم‌فاصله و نیم‌فاصله در آغاز ‌کلمه و پایان کلمه‌ ."
        p1 = self.normalizer.normalize(raw)
        p2 = self.normalizer.normalize(p1)
        self.assertEqual(p1, p2)
        self.assertNotIn("‌‌", p1)

    def test_idempotence_punctuation_hygiene(self) -> None:
        """Punctuation spacing and duplicate marks are cleaned idempotently."""
        raw = "این یک متن ،، خیلی سریع ، نوشته شد .آیا موافقید ؟بله !حتما ."
        p1 = self.normalizer.normalize(raw)
        p2 = self.normalizer.normalize(p1)
        self.assertEqual(p1, p2)
        self.assertNotIn(" ،", p1)
        self.assertNotIn(" .", p1)
        self.assertNotIn(" ؟", p1)
        self.assertNotIn(" !", p1)
        self.assertNotIn("،،", p1)
        self.assertIn("، خیلی سریع، نوشته شد. آیا موافقید؟ بله! حتما.", p1)

    def test_idempotence_guillemets_and_colon(self) -> None:
        """Persian quotes («...») and colons normalize idempotently."""
        raw = 'او گفت:"سلام دنیا" و سپس رفت.'
        p1 = self.normalizer.normalize(raw)
        p2 = self.normalizer.normalize(p1)
        self.assertEqual(p1, p2)
        self.assertIn("گفت: «سلام دنیا»", p1)

        # Space around quotes
        spaced_raw = "او « کتاب » را خواند."
        p1_sp = self.normalizer.normalize(spaced_raw)
        p2_sp = self.normalizer.normalize(p1_sp)
        self.assertEqual(p1_sp, p2_sp)
        self.assertIn("«کتاب» را", p1_sp)

    def test_idempotence_zero_em_dash_comma_policy(self) -> None:
        """Zero em-dash conversion to Persian syntactic commas is idempotent."""
        # Single em-dash
        single_raw = "او آمد — خسته و تنها."
        p1_s = self.normalizer.normalize(single_raw)
        p2_s = self.normalizer.normalize(p1_s)
        self.assertEqual(p1_s, p2_s)
        self.assertNotIn("—", p1_s)
        self.assertIn("،", p1_s)

        # Paired em-dashes
        paired_raw = "علی — برادر رستم — دیروز به شهر آمد."
        p1_p = self.normalizer.normalize(paired_raw)
        p2_p = self.normalizer.normalize(p1_p)
        self.assertEqual(p1_p, p2_p)
        self.assertNotIn("—", p1_p)
        self.assertEqual(p1_p, "علی، برادر رستم، دیروز به شهر آمد.")

    def test_idempotence_zero_em_dash_parentheses_policy(self) -> None:
        """Zero em-dash conversion to parentheses is idempotent."""
        norm_paren = PersianNormalizer(em_dash_target="parentheses")
        paired_raw = "علی — برادر رستم — دیروز به شهر آمد."
        p1 = norm_paren.normalize(paired_raw)
        p2 = norm_paren.normalize(p1)
        self.assertEqual(p1, p2)
        self.assertNotIn("—", p1)
        self.assertEqual(p1, "علی (برادر رستم) دیروز به شهر آمد.")

    def test_idempotence_multiline_markdown(self) -> None:
        """Multiline markdown documents preserve structure and normalize idempotently."""
        raw = """
# عنوان اصلی

این پاراگراف اول است كه با ك و ي عربي نوشته شده است .

## بخش دوم

پاراگراف دوم با « كوتيشن » و فاصله هاي اضافي      در خط.

- آیتم اول :توضیح
- آیتم دوم با — خط تیره
"""
        p1 = self.normalizer.normalize(raw)
        p2 = self.normalizer.normalize(p1)
        self.assertEqual(p1, p2)
        self.assertIn("# عنوان اصلی", p1)
        self.assertIn("## بخش دوم", p1)
        self.assertNotIn("ك", p1)
        self.assertNotIn("ي", p1)

    def test_idempotence_code_blocks_preservation(self) -> None:
        """Code blocks are untouched by normalization and idempotent."""
        raw = """متن پیش از کد.
```python
def example():
    # ك و ي و —
    x = "تست"
    return x
```
متن پس از كد با ك و ي عربي."""
        p1 = self.normalizer.normalize(raw)
        p2 = self.normalizer.normalize(p1)
        self.assertEqual(p1, p2)
        self.assertIn("# ك و ي و —", p1)
        self.assertIn("متن پس از کد با ک و ی عربی.", p1)

    def test_idempotence_large_corpus_loop(self) -> None:
        """Batch test across 25 diverse realistic corpus strings."""
        corpus = [
            "دانش پژوهان — كه در حال تحقيق بودند — نتايج را منتشر كردند.",
            "او مي گفت:«دانشگاه ها بايد به علم و فن آوري مجهز شوند».",
            "سريع ترين راه براي رسيدن به هدف ، تلاش مستمر است .آيا اينطور نيست ؟",
            "قيمت اين محصول 1,500 دلار و نسخه سيستم عامل 2.7 است.",
            "خانه اي در انتهاي كوچه با درخت هاي سرسبز وجود داشت.",
            "مدير عامل گفت:«ما بايد به سرعت پيش برويم».",
            "نتايج اوليه — هرچند اميدبخش بود — نياز به تاييد نهايي دارد.",
            "بزرگ ترين افتخار يك نويسنده ، رضايت خوانندگان است .",
            "آدرس وبگاه ما https://tarjoman.org/docs است كه مي توانيد ببينيد.",
            "متن با ‎‏ كاراكترهاي مخفي دوجهته ﻿ و فاصله.",
            "خط اول\n\n\nخط دوم\n\n\n\nخط سوم",
            "«سلام»گفت و سپس دور شد.",
            "پروژه هاي جديد با رويكرد بهينه سازي و استاندارد سازي.",
            "آيا شما آماده ايد ؟بله ، ما آماده ايم !",
            "كتاب هاي تاريخي و ادبي در كتابخانه ملي.",
            "او هرگز نمي توانست باور كند كه چه اتفاقي افتاده است.",
            "اين موضوع — همانطور كه پيش تر گفتم — اهميت فراواني دارد.",
            "دست هايش مي لرزيد و نمي دانست چه بگويد.",
            "گفت :«بله» .سپس رفت .",
            "متن با پرانتز ( توضيح اضافي ) در داخل جمله.",
            "تيم هاي فني در حال توسعه سامانه ها هستند.",
            "يكي از بزرگ ترين مشكلات ، كمبود منابع است .",
            "در اين باره — بايد توجه داشت — كه زمان اندك است.",
            "پيش بيني ها نشان مي دهد كه رشد اقتصادي ادامه دارد.",
            "پايان متن نمونه براي بررسي جامع برابري و يكنواختي.",
        ]

        for idx, text in enumerate(corpus):
            p1 = self.normalizer.normalize(text)
            p2 = self.normalizer.normalize(p1)
            self.assertEqual(p1, p2, f"Corpus test {idx} failed strict idempotence:\n{text}")


class TestDiagnosticVsAutoFixSplit(unittest.TestCase):
    """Verifies D09: calques flagged as structured findings without blind auto-replacement."""

    def setUp(self) -> None:
        self.detector = CalqueDetector()

    def test_detect_calques_does_not_mutate_input(self) -> None:
        """Diagnostic detection must never mutate or rewrite the input string (D09)."""
        input_text = "در پایان روز روی او حساب کن و بدان که او یک نقش مهم بازی می‌کند."
        copied_text = str(input_text)
        findings = self.detector.detect(input_text)
        self.assertEqual(input_text, copied_text)
        self.assertGreater(len(findings), 0)

    def test_quality_finding_attributes(self) -> None:
        """Verify QualityFinding typed model has all required fields."""
        finding = QualityFinding(
            rule_id="CALQUE_AT_END_OF_DAY",
            severity="major",
            message="کاربرد در پایان روز",
            start=0,
            end=12,
            matched_text="در پایان روز",
            suggested_fix="در نهایت / سرانجام",
            explanation="گرته‌برداری از at the end of the day",
        )
        self.assertEqual(finding.rule_id, "CALQUE_AT_END_OF_DAY")
        self.assertEqual(finding.severity, "major")
        self.assertEqual(finding.start, 0)
        self.assertEqual(finding.end, 12)
        self.assertEqual(finding.matched_text, "در پایان روز")
        self.assertEqual(finding.suggested_fix, "در نهایت / سرانجام")
        self.assertIn("at the end of the day", finding.explanation)

    def test_character_spans_are_exact(self) -> None:
        """Verify matched spans text[start:end] == matched_text."""
        text = "در پایان روز روی او حساب کن و بدان که او یک نقش کلیدی بازی می‌کند."
        findings = self.detector.detect(text)
        self.assertGreaterEqual(len(findings), 3)
        for f in findings:
            self.assertEqual(text[f.start:f.end], f.matched_text)

    def test_rule_calque_passive_by(self) -> None:
        """Verify CALQUE_PASSIVE_BY detection."""
        text = "این کتاب توسط نویسنده مشهور نوشته شد."
        findings = self.detector.detect(text)
        rule_findings = [f for f in findings if f.rule_id == "CALQUE_PASSIVE_BY"]
        self.assertEqual(len(rule_findings), 1)
        f = rule_findings[0]
        self.assertEqual(f.severity, "major")
        self.assertIn("توسط", f.matched_text)
        self.assertIn("نوشته شد", f.matched_text)
        self.assertIsNotNone(f.suggested_fix)

    def test_rule_calque_play_role(self) -> None:
        """Verify CALQUE_PLAY_ROLE detection."""
        text = "او یک نقش کلیدی در موفقیت پروژه بازی می‌کند."
        findings = self.detector.detect(text)
        rule_findings = [f for f in findings if f.rule_id == "CALQUE_PLAY_ROLE"]
        self.assertEqual(len(rule_findings), 1)
        f = rule_findings[0]
        self.assertEqual(f.severity, "major")
        self.assertIn("ایفا کردن", f.suggested_fix or "")

    def test_rule_calque_count_on(self) -> None:
        """Verify CALQUE_COUNT_ON detection."""
        text = "شما می‌توانید روی کمک ما حساب کنید."
        findings = self.detector.detect(text)
        rule_findings = [f for f in findings if f.rule_id == "CALQUE_COUNT_ON"]
        self.assertEqual(len(rule_findings), 1)
        f = rule_findings[0]
        self.assertEqual(f.severity, "major")
        self.assertIn("اعتماد کردن", f.suggested_fix or "")

    def test_rule_calque_act_as(self) -> None:
        """Verify CALQUE_ACT_AS detection."""
        text = "او به عنوان مدیر پروژه عمل کرد."
        findings = self.detector.detect(text)
        rule_findings = [f for f in findings if f.rule_id == "CALQUE_ACT_AS"]
        self.assertEqual(len(rule_findings), 1)
        f = rule_findings[0]
        self.assertIn("جایگاه", f.suggested_fix or "")

    def test_rule_calque_at_end_of_day(self) -> None:
        """Verify CALQUE_AT_END_OF_DAY detection."""
        text = "در پایان روز همه ما باید متحد باشیم."
        findings = self.detector.detect(text)
        rule_findings = [f for f in findings if f.rule_id == "CALQUE_AT_END_OF_DAY"]
        self.assertEqual(len(rule_findings), 1)
        f = rule_findings[0]
        self.assertEqual(f.matched_text, "در پایان روز")
        self.assertIn("در نهایت", f.suggested_fix or "")

    def test_rule_calque_make_sense(self) -> None:
        """Verify CALQUE_MAKE_SENSE detection."""
        text = "این نظریه کاملاً حس ایجاد می‌کند."
        findings = self.detector.detect(text)
        rule_findings = [f for f in findings if f.rule_id == "CALQUE_MAKE_SENSE"]
        self.assertEqual(len(rule_findings), 1)
        f = rule_findings[0]
        self.assertIn("منطقی", f.suggested_fix or "")

    def test_rule_calque_make_decision(self) -> None:
        """Verify CALQUE_MAKE_DECISION detection."""
        text = "آن‌ها در جلسه یک تصمیم گرفتند."
        findings = self.detector.detect(text)
        rule_findings = [f for f in findings if f.rule_id == "CALQUE_MAKE_DECISION"]
        self.assertEqual(len(rule_findings), 1)
        f = rule_findings[0]
        self.assertIn("یک تصمیم گرفتند", f.matched_text)

    def test_rule_calque_open_fire(self) -> None:
        """Verify CALQUE_OPEN_FIRE detection."""
        text = "نیروهای نظامی به سوی اهداف آتش گشودند."
        findings = self.detector.detect(text)
        rule_findings = [f for f in findings if f.rule_id == "CALQUE_OPEN_FIRE"]
        self.assertEqual(len(rule_findings), 1)
        f = rule_findings[0]
        self.assertIn("شلیک", f.suggested_fix or "")

    def test_rule_calque_strangely_enough(self) -> None:
        """Verify CALQUE_STRANGELY_ENOUGH detection."""
        text = "به اندازه کافی عجیب است که کسی در جلسه حاضر نشد."
        findings = self.detector.detect(text)
        rule_findings = [f for f in findings if f.rule_id == "CALQUE_STRANGELY_ENOUGH"]
        self.assertEqual(len(rule_findings), 1)
        f = rule_findings[0]
        self.assertIn("شگفتا", f.suggested_fix or "")

    def test_rule_calque_point_of_view(self) -> None:
        """Verify CALQUE_POINT_OF_VIEW detection."""
        text = "نقطه نظرات مختلف در نشست مطرح شد."
        findings = self.detector.detect(text)
        rule_findings = [f for f in findings if f.rule_id == "CALQUE_POINT_OF_VIEW"]
        self.assertEqual(len(rule_findings), 1)
        f = rule_findings[0]
        self.assertIn("دیدگاه", f.suggested_fix or "")

    def test_rule_calque_apply_to(self) -> None:
        """Verify CALQUE_APPLY_TO detection."""
        text = "به کار بردن برای همه افراد توصیه نمی‌شود."
        findings = self.detector.detect(text)
        rule_findings = [f for f in findings if f.rule_id == "CALQUE_APPLY_TO"]
        self.assertEqual(len(rule_findings), 1)
        f = rule_findings[0]
        self.assertIn("صدق کردن", f.suggested_fix or "")

    def test_multi_calques_sorted_order(self) -> None:
        """Multiple calques in one passage are returned in ascending start order."""
        text = "در پایان روز روی او حساب کن و بدان که این طرح حس ایجاد می‌کند."
        findings = detect_calques(text)
        self.assertGreaterEqual(len(findings), 3)
        for i in range(len(findings) - 1):
            self.assertLessEqual(findings[i].start, findings[i + 1].start)


class TestFalsePositiveRegressionCases(unittest.TestCase):
    """Verifies legitimate Persian expressions and literal contexts do NOT trigger calque rules."""

    def setUp(self) -> None:
        self.detector = CalqueDetector()

    def test_literal_playing_games_not_calque(self) -> None:
        """Literal children playing games must NOT trigger CALQUE_PLAY_ROLE."""
        sentences = [
            "بچه‌ها بعد از ظهر در حیاط بازی می‌کردند.",
            "آن‌ها با توپ فوتبال در زمین بازی کردند.",
            "بازی کردن با آتش برای کودکان خطرناک است.",
            "او ساعت‌ها بازی و تفریح کرد.",
        ]
        for s in sentences:
            findings = self.detector.detect(s)
            play_role = [f for f in findings if f.rule_id == "CALQUE_PLAY_ROLE"]
            self.assertEqual(len(play_role), 0, f"False positive on: {s}")

    def test_literal_fire_not_calque(self) -> None:
        """Literal fire statements must NOT trigger CALQUE_OPEN_FIRE."""
        sentences = [
            "آتش بخاری را خاموش کرد و پنجره را بست.",
            "آتش اردوگاه به آرامی زبانه کشید.",
            "آن‌ها در شب سرد زمستانی آتش روشن کردند.",
            "آتش زدن جنگل‌ها جرم بزرگی است.",
        ]
        for s in sentences:
            findings = self.detector.detect(s)
            fire = [f for f in findings if f.rule_id == "CALQUE_OPEN_FIRE"]
            self.assertEqual(len(fire), 0, f"False positive on: {s}")

    def test_legitimate_end_of_phrases_not_calque(self) -> None:
        """Valid uses of 'در پایان' (end of chapter/book/month) must NOT trigger CALQUE_AT_END_OF_DAY."""
        sentences = [
            "در پایان فصل اول خلاصه مباحث آورده شده است.",
            "در پایان کتاب فهرست منابع ذکر شده است.",
            "در پایان ماه گزارش مالی تهیه می‌شود.",
            "در پایان جلسه اعضا به توافق رسیدند.",
            "در پایان سال مالی سود شرکت محاسبه شد.",
        ]
        for s in sentences:
            findings = self.detector.detect(s)
            eod = [f for f in findings if f.rule_id == "CALQUE_AT_END_OF_DAY"]
            self.assertEqual(len(eod), 0, f"False positive on: {s}")

    def test_legitimate_persian_passive_not_calque(self) -> None:
        """Authentic Persian passives without 'توسط' must NOT trigger CALQUE_PASSIVE_BY."""
        sentences = [
            "این کتاب در سال گذشته نوشته شد.",
            "لایحه بودجه در مجلس تصویب شد.",
            "پل جدید با موفقیت ساخته شد.",
            "پروژه طبق برنامه انجام شد.",
            "مقاله علمی در مجله منتشر شد.",
        ]
        for s in sentences:
            findings = self.detector.detect(s)
            passive = [f for f in findings if f.rule_id == "CALQUE_PASSIVE_BY"]
            self.assertEqual(len(passive), 0, f"False positive on: {s}")

    def test_legitimate_meaning_and_sense_not_calque(self) -> None:
        """Authentic expressions like 'عشق به جهان معنا می‌دهد' must NOT trigger CALQUE_MAKE_SENSE."""
        sentences = [
            "عشق به جهان معنا می‌دهد و زندگی را زیبا می‌کند.",
            "این موسیقی دلنشین حس آرامش عمیقی ایجاد می‌کند.",
            "دیدن این منظره حس امید ایجاد کرد.",
        ]
        for s in sentences:
            findings = self.detector.detect(s)
            sense = [f for f in findings if f.rule_id == "CALQUE_MAKE_SENSE"]
            self.assertEqual(len(sense), 0, f"False positive on: {s}")

    def test_legitimate_decision_not_calque(self) -> None:
        """Standard 'تصمیم گرفتن' without numeral 'یک' must NOT trigger CALQUE_MAKE_DECISION."""
        sentences = [
            "آن‌ها سرانجام تصمیم گرفتند به سفر بروند.",
            "مدیران شرکت برای حل بحران تصمیم گرفتند.",
            "ما باید سریعاً تصمیم بگیریم.",
        ]
        for s in sentences:
            findings = self.detector.detect(s)
            dec = [f for f in findings if f.rule_id == "CALQUE_MAKE_DECISION"]
            self.assertEqual(len(dec), 0, f"False positive on: {s}")

    def test_literal_counting_and_banking_not_calque(self) -> None:
        """Literal accounting, banking, or paper calculation must NOT trigger CALQUE_COUNT_ON."""
        sentences = [
            "حساب بانکی او به دلیل بدهی مسدود شد.",
            "حسابداری شرکت سود سالانه را محاسبه کرد.",
            "او هزینه‌ها را روی کاغذ حساب کرد.",
            "صورت‌حساب ماهانه ارسال شد.",
        ]
        for s in sentences:
            findings = self.detector.detect(s)
            count_on = [f for f in findings if f.rule_id == "CALQUE_COUNT_ON"]
            self.assertEqual(len(count_on), 0, f"False positive on: {s}")

    def test_code_blocks_and_technical_tokens_not_detected(self) -> None:
        """Calque phrases inside fenced code blocks or inline code are ignored."""
        text = """این یک راهنما است.
```python
# در پایان روز روی او حساب کن
def play_role():
    pass
```
اینجا متن عادی بدون هیچ گرته‌برداری است."""
        findings = self.detector.detect(text)
        self.assertEqual(len(findings), 0)

        # Inline code ignored
        inline_text = "کد `روی او حساب کن` یک متد است."
        findings_inline = self.detector.detect(inline_text)
        self.assertEqual(len(findings_inline), 0)


class TestPackageIntegrationAndBackwardCompatibility(unittest.TestCase):
    """Verifies public exports and backward compatibility with existing components."""

    def test_quality_package_exports(self) -> None:
        """tarjoman.quality exposes PersianNormalizer, normalize_persian, CalqueDetector, detect_calques, QualityFinding."""
        import tarjoman.quality as tq

        self.assertTrue(hasattr(tq, "PersianNormalizer"))
        self.assertTrue(hasattr(tq, "normalize_persian"))
        self.assertTrue(hasattr(tq, "CalqueDetector"))
        self.assertTrue(hasattr(tq, "detect_calques"))
        self.assertTrue(hasattr(tq, "QualityFinding"))

    def test_anti_calque_engine_backward_compatibility(self) -> None:
        """AntiCalqueEngine public methods remain functional."""
        text = "کتاب توسط نویسنده نوشته شد."
        eliminated = AntiCalqueEngine.eliminate_calques(text)
        self.assertNotIn("توسط", eliminated)

        detected_str = AntiCalqueEngine.detect_calques(text)
        self.assertIsInstance(detected_str, list)
        self.assertGreater(len(detected_str), 0)

        # Structured detector delegation
        structured = AntiCalqueEngine.detect_calques_structured(text)
        self.assertIsInstance(structured, list)
        self.assertGreater(len(structured), 0)
        self.assertIsInstance(structured[0], QualityFinding)


if __name__ == "__main__":
    unittest.main()
