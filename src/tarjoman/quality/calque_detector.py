"""
Diagnostic Calque Detection Layer — Architecture Zero §8.2, Locked Decision D09.

Provides non-destructive, read-only diagnostic inspection of Persian texts for
structural and lexical calques (گرته‌برداری‌های نحوی و واژگانی).

Based on classical Persian linguistic authorities:
- Abolhassan Najafi (غلط ننویسیم)
- Ahmad Samii Guilani (نگارش و ویرایش)
- Hermes Translation Methodology

Invariants enforced:
- D09: Does NOT mutate, rewrite, or auto-fix the text.
- Returns typed, structured QualityFinding objects with exact character spans.
- False-positive guards distinguish authentic Persian idioms from calques.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Pattern, Tuple

from pydantic import BaseModel, Field


class QualityFinding(BaseModel):
    """Structured diagnostic finding produced by quality inspection.

    Architecture Zero §8.2 & §22.2:
    Typed finding contract containing rule identity, severity, span offsets,
    matched snippet, explanation, and non-destructive suggested fix.
    """

    rule_id: str = Field(..., description="Unique machine-readable identifier for the rule.")
    severity: str = Field(..., description="Severity level: critical, major, or minor.")
    message: str = Field(..., description="Concise human-readable diagnostic message.")
    start: int = Field(..., ge=0, description="0-based character start index in source text.")
    end: int = Field(..., ge=0, description="0-based character end index in source text.")
    matched_text: str = Field(..., description="Exact matched text slice from source.")
    suggested_fix: Optional[str] = Field(None, description="Recommended idiomatic replacement.")
    explanation: str = Field(..., description="Linguistic explanation from Najafi/Samii authorities.")


class CalqueDetector:
    """Non-destructive Persian calque detector.

    Scans text for syntactic and lexical calques without mutating input.
    Guarded against false positives in literal contexts and code blocks.
    """

    # 1. Passive by-agent with 'توسط' (Najafi: غلط ننویسیم)
    _PASSIVE_BY_PATTERN: Pattern = re.compile(
        r"توسط\s+([^،.\n]+?)\s+((?:نوشته|تصویب|ساخته|به قتل رسید|کشته|انجام|منتشر|بیان|ایجاد|"
        r"پذیرفته|اجرا|طراحی|برگزار|تولید|ارسال|فرستاده|کشف|معرفی|انتخاب|امضا|گزارش|تعریف|مطرح)"
        r"\s+(?:ن?شده[\s‌]*(?:است|اند|اید|ایم)|ن?شدند|ن?شد))",
        re.UNICODE,
    )

    # 2. Playing a role -> نقش بازی کردن (Samii Guilani)
    _PLAY_ROLE_PATTERN: Pattern = re.compile(
        r"(?:یک\s+)?نقش(?:ی)?(?:\s+(?:کلیدی|مهم|اساسی|محوری|تعیین‌کننده|تعیین[\s‌]*کننده|عمده|برجسته|بزرگ))?"
        r".*?\bبازی\s+(?:کردن|کرد|کرده[\s‌]*(?:است|اند|ام|ای|ایم|اید)|کردند|(?:ن?می[\s‌]*)کرد|"
        r"(?:ن?می[\s‌]*)کردند|(?:ن?می[\s‌]*)کند|(?:ن?می[\s‌]*)کنند|کند|کنند)\b",
        re.UNICODE,
    )

    # 3. Rely on / Count on -> روی ... حساب کردن (Najafi)
    _COUNT_ON_PATTERN: Pattern = re.compile(
        r"روی\s+([^،.\n]+?)\s+حساب\s+(?:کرده[\s‌]*(?:است|اند|اید|ایم|ام|ای)|کردند|کردیم|کردید|کردم|"
        r"کردی|کردن|کرد|(?:ن?می[\s‌]*)(?:کنیم|کنید|کنند|کنم|کنی|کند)|نکنید|نکنیم|نکنند|نکنم|نکنی|نکن|"
        r"کنید|کنیم|کنند|کنم|کنی|کن)",
        re.UNICODE,
    )

    # 4. Act as -> به عنوانِ ... عمل کردن
    _ACT_AS_PATTERN: Pattern = re.compile(
        r"به عنوانِ?\s+([^،.\n]+?)\s+عمل\s+(?:کرده[\s‌]*(?:است|اند|اید|ایم|ام|ای)|کردند|کردیم|کردید|"
        r"کردم|کردی|کردن|کرد|(?:ن?می[\s‌]*)(?:کنیم|کنید|کنند|کنم|کنی|کند))",
        re.UNICODE,
    )

    # 5. At the end of the day -> در پایان روز
    _AT_END_OF_DAY_PATTERN: Pattern = re.compile(r"\bدر پایان روز\b", re.UNICODE)

    # 6. Make sense -> حس ایجاد کردن / معنا می‌دهد (contextual)
    _MAKE_SENSE_PATTERN: Pattern = re.compile(
        r"\bحس ایجاد\s+(?:ن?می[\s‌]*(?:کند|کرد)|کردن|کرد|نکرد)\b",
        re.UNICODE,
    )
    _MAKE_SENSE_CONTEXTUAL_PATTERN: Pattern = re.compile(
        r"\b(این\s+(?:حرف|ادعا|موضوع|نکته|طرح|ایده|سخن))\s+(معنا|معنی)\s+(?:ن?می[\s‌]*دهد|داد|نداد)\b",
        re.UNICODE,
    )

    # 7. Make a decision -> یک تصمیم گرفتن
    _MAKE_DECISION_PATTERN: Pattern = re.compile(
        r"\bیک\s+تصمیم\s+(?:گرفته[\s‌]*(?:است|اند|اید|ایم|ام|ای)|گرفتند|گرفتیم|گرفتید|گرفتم|گرفتی|"
        r"گرفتن|گرفت|(?:ن?می[\s‌]*)(?:گیریم|گیرید|گیرند|گیرم|گیری|گیرد)|"
        r"(?:ب|ن)(?:گیریم|گیرید|گیرند|گیرم|گیری|گیرد))\b",
        re.UNICODE,
    )

    # 8. Open fire -> آتش گشودن (Najafi)
    _OPEN_FIRE_PATTERN: Pattern = re.compile(
        r"\bآتش\s+(?:گشوده[\s‌]*(?:شده[\s‌]*است|شدند|شد)|گشودند|گشودیم|گشودید|گشودم|گشودی|"
        r"گشودن|گشود|(?:ن?می[\s‌]*)(?:گشایند|گشاییم|گشایید|گشایم|گشایی|گشاید))\b",
        re.UNICODE,
    )

    # 9. Strangely enough -> به اندازه کافی عجیب است
    _STRANGELY_ENOUGH_PATTERN: Pattern = re.compile(
        r"\bبه اندازه[‌\s]کافی عجیب\s*(?:است|بود)?\b",
        re.UNICODE,
    )

    # 10. Point of view -> نقطه نظر (Najafi)
    _POINT_OF_VIEW_PATTERN: Pattern = re.compile(
        r"\bنقطه[‌\s]?(?:نظرات|نظرها|نظر)\b",
        re.UNICODE,
    )

    # 11. Apply to -> به کار بردن برای
    _APPLY_TO_PATTERN: Pattern = re.compile(
        r"\bبه\s*کار\s+(?:بردن|برده[\s‌]*(?:شدن|شده[\s‌]*است|شدند|شد)|می[\s‌]*رود|می[\s‌]*روند|رفت)\s+برای\b|"
        r"\bبرای\s+([^،.\n]+?)\s+به\s*کار\s+(?:بردن|برده[\s‌]*(?:شدن|شده[\s‌]*است|شدند|شد)|می[\s‌]*رود|می[\s‌]*روند|رفت)\b",
        re.UNICODE,
    )

    # 12. Take a bath / shower -> حمام گرفتن
    _TAKE_BATH_PATTERN: Pattern = re.compile(
        r"\bحمام\s+(?:گرفته[\s‌]*(?:است|اند|اید|ایم|ام|ای)|گرفتند|گرفتیم|گرفتید|گرفتم|گرفتی|"
        r"گرفتن|گرفت|(?:ن?می[\s‌]*)(?:گیریم|گیرید|گیرند|گیرم|گیری|گیرد)|"
        r"(?:ب|ن)(?:گیریم|گیرید|گیرند|گیرم|گیری|گیرد))\b",
        re.UNICODE,
    )

    # 13. Give green light -> چراغ سبز نشان دادن
    _GREEN_LIGHT_PATTERN: Pattern = re.compile(
        r"\bچراغ\s+سبز\s+نشان\s+(?:داده[\s‌]*(?:است|اند|اید|ایم|ام|ای)|دادند|دادیم|دادید|دادم|دادی|"
        r"دادن|داد|(?:ن?می[\s‌]*)(?:دهیم|دهید|دهند|دهم|دهی|دهد)|(?:ب|ن)(?:دهیم|دهید|دهند|دهم|دهی|دهد))\b",
        re.UNICODE,
    )

    # 14. Reach end of line -> به پایان خط رسیدن
    _END_OF_LINE_PATTERN: Pattern = re.compile(
        r"\bبه پایان خط\s+(?:رسیده[\s‌]*(?:است|اند|اید|ایم|ام|ای)|رسیدند|رسیدیم|رسیدید|رسیدم|رسیدی|"
        r"رسیدن|رسید|(?:ن?می[\s‌]*)(?:رسیم|رسید|رسند|رسم|رسی|رسد)|(?:ب|ن)(?:رسیم|رسید|رسند|رسم|رسی|رسد))\b",
        re.UNICODE,
    )

    def __init__(self, skip_code_blocks: bool = True) -> None:
        self.skip_code_blocks = skip_code_blocks

    @staticmethod
    def _mask_code_blocks(text: str) -> str:
        """Mask code blocks with equal-length spaces to preserve character indices."""
        def _mask(m: re.Match) -> str:
            return "".join("\n" if c == "\n" else " " for c in m.group(0))

        masked = re.sub(r"```[\s\S]*?```", _mask, text)
        masked = re.sub(r"`[^`\n]+`", _mask, masked)
        return masked

    def detect(self, text: str) -> List[QualityFinding]:
        """Detect calques in Persian text and return structured diagnostic findings.

        In accordance with Locked Decision D09, this operation does NOT mutate text.
        """
        if not text:
            return []

        search_text = self._mask_code_blocks(text) if self.skip_code_blocks else text
        findings: List[QualityFinding] = []

        rules: List[Tuple[str, str, str, Pattern, Optional[str], str]] = [
            (
                "CALQUE_PASSIVE_BY",
                "major",
                "کاربرد ساختار مجهول با «توسط» (گرته‌برداری نحوی از passive by-agent)",
                self._PASSIVE_BY_PATTERN,
                "استفاده از ساختار معلوم یا عبارت «به دستِ»",
                "ساختار مجهول با ذکر عامل توسط، گرته‌برداری نحوی از زبان‌های اروپایی است. "
                "در فارسی فصیح مجهول بدون عامل به کار می‌رود یا از ساختار معلوم یا عبارت «به دستِ» استفاده می‌شود (ابوالحسن نجفی، غلط ننویسیم).",
            ),
            (
                "CALQUE_PLAY_ROLE",
                "major",
                "کاربرد اصطلاح «نقش بازی کردن» به جای «نقش ایفا کردن» (گرته‌برداری از play a role)",
                self._PLAY_ROLE_PATTERN,
                "نقش ایفا کردن / اثرگذار بودن / سهم داشتن",
                "عبارت «نقش بازی کردن» در معنای اثرگذاری یا سهم داشتن، گرته‌برداری از «to play a role» است. "
                "در فارسی فصیح باید از «نقش داشتن»، «نقش ایفا کردن» یا «سهم داشتن» استفاده شود (احمد سمیعی گیلانی).",
            ),
            (
                "CALQUE_COUNT_ON",
                "major",
                "کاربرد «روی ... حساب کردن» (گرته‌برداری از to count on)",
                self._COUNT_ON_PATTERN,
                "به ... اعتماد کردن / بر ... تکیه کردن",
                "«روی کسی یا چیزی حساب کردن» در معنای اتکا و اعتماد، گرته‌برداری از «count on / rely on» است. "
                "در فارسی اصیل باید از «به ... اعتماد کردن» یا «بر ... تکیه کردن» استفاده شود (ابوالحسن نجفی).",
            ),
            (
                "CALQUE_ACT_AS",
                "minor",
                "کاربرد «به عنوان ... عمل کردن» (گرته‌برداری از to act as)",
                self._ACT_AS_PATTERN,
                "در جایگاه ... بودن / در نقش ... خدمت کردن",
                "ترکیب «به عنوانِ ... عمل کردن» گرته‌برداری لفظ‌به‌لفظ از «to act as» است. "
                "معادل‌های فصیح فارسی شامل «در جایگاهِ ... بودن»، «به منزلهٔ ... عمل کردن» یا «در نقشِ ... بودن» است.",
            ),
            (
                "CALQUE_AT_END_OF_DAY",
                "major",
                "کاربرد «در پایان روز» در معنای سرانجام (گرته‌برداری از at the end of the day)",
                self._AT_END_OF_DAY_PATTERN,
                "در نهایت / سرانجام / روی‌هم‌رفته",
                "«در پایان روز» در معنای نتیجه‌گیری نهایی، گرته‌برداری از عبارت اصطلاحی انگلیسی «at the end of the day» است. "
                "در فارسی باید از «در نهایت»، «سرانجام»، «عاقبت» یا «روی‌هم‌رفته» استفاده شود.",
            ),
            (
                "CALQUE_MAKE_SENSE",
                "major",
                "کاربرد «حس ایجاد کردن» یا «معنا دادن» در معنای معقول بودن (گرته‌برداری از make sense)",
                self._MAKE_SENSE_PATTERN,
                "منطقی بودن / معقول بودن / توجیه‌پذیر بودن",
                "«حس ایجاد کردن» ترجمهٔ نادرست و تحت‌اللفظی «to make sense» است. "
                "در فارسی فصیح باید از «منطقی بودن»، «معقول بودن» یا «معنا داشتن» استفاده شود.",
            ),
            (
                "CALQUE_MAKE_SENSE",
                "major",
                "کاربرد «معنا دادن» در معنای معقول بودن (گرته‌برداری از make sense)",
                self._MAKE_SENSE_CONTEXTUAL_PATTERN,
                "منطقی بودن / معقول بودن",
                "کاربرد «معنا دادن» با فاعل‌هایی چون «این حرف/ادعا»، گرته‌برداری از «makes sense» است. "
                "در فارسی فصیح: «منطقی است» یا «معقول به نظر می‌رسد».",
            ),
            (
                "CALQUE_MAKE_DECISION",
                "minor",
                "کاربرد «یک تصمیم گرفتن» با عدد یک (گرته‌برداری از make a decision)",
                self._MAKE_DECISION_PATTERN,
                "تصمیم گرفتن / تصمیم‌گیری کردن / تصمیمی اتخاذ کردن",
                "استفاده از عدد «یک» پیش از تصمیم گرته‌برداری از ساختار اسامی شمارا در انگلیسی (make a decision) است. "
                "در فارسی فصیح: «تصمیم گرفتن»، «تصمیم‌گیری کردن» یا «تصمیمی اتخاذ کردن» به کار می‌رود.",
            ),
            (
                "CALQUE_OPEN_FIRE",
                "major",
                "کاربرد «آتش گشودن» به جای شلیک کردن (گرته‌برداری از to open fire)",
                self._OPEN_FIRE_PATTERN,
                "تیراندازی کردن / شلیک کردن",
                "«آتش گشودن» گرته‌برداری از اصطلاح نظامی انگلیسی «to open fire» است. "
                "در فارسی فصیح باید از «تیراندازی کردن» یا «شلیک کردن» استفاده شود (ابوالحسن نجفی).",
            ),
            (
                "CALQUE_STRANGELY_ENOUGH",
                "major",
                "کاربرد «به اندازه کافی عجیب است» (گرته‌برداری از strangely enough)",
                self._STRANGELY_ENOUGH_PATTERN,
                "شگفتا / عجیب آن‌که / شگفت‌آور آن‌که",
                "«به اندازه کافی عجیب است» گرته‌برداری لفظ‌به‌لفظ از «strangely enough» یا «oddly enough» است. "
                "معادل‌های اصیل فارسی: «شگفتا»، «عجیب آن‌که» یا «شگفت‌آور آن‌که» است.",
            ),
            (
                "CALQUE_POINT_OF_VIEW",
                "minor",
                "کاربرد «نقطه نظر» به جای دیدگاه (گرته‌برداری از point of view)",
                self._POINT_OF_VIEW_PATTERN,
                "دیدگاه / نگرش / نظر",
                "«نقطه نظر» گرته‌برداری از «point of view» فرانسوی و انگلیسی است. "
                "معادل اصیل و مصوب در فارسی «دیدگاه» یا «نظر» است (ابوالحسن نجفی، غلط ننویسیم).",
            ),
            (
                "CALQUE_APPLY_TO",
                "minor",
                "کاربرد «به کار بردن برای» در معنای شمول (گرته‌برداری از apply to)",
                self._APPLY_TO_PATTERN,
                "درباره ... صدق کردن / شامل ... شدن / بر ... اطلاق شدن",
                "عبارت «به کار بردن برای» در معنای شمول قانون یا مفهوم، گرته‌برداری از «to apply to» است. "
                "در فارسی فصیح: «درباره ... صدق کردن»، «شاملِ ... شدن» یا «بر ... اطلاق شدن» به کار می‌رود.",
            ),
            (
                "CALQUE_TAKE_BATH",
                "minor",
                "کاربرد «حمام گرفتن» به جای دوش گرفتن یا حمام کردن (گرته‌برداری از take a bath)",
                self._TAKE_BATH_PATTERN,
                "دوش گرفتن / حمام کردن",
                "«حمام گرفتن» گرته‌برداری از «take a bath» است. در فارسی: «دوش گرفتن» یا «حمام کردن» صحیح است.",
            ),
            (
                "CALQUE_GREEN_LIGHT",
                "minor",
                "کاربرد «چراغ سبز نشان دادن» (گرته‌برداری از give the green light)",
                self._GREEN_LIGHT_PATTERN,
                "موافقت کردن / اجازه دادن",
                "«چراغ سبز نشان دادن» گرته‌برداری از اصطلاح غربی است. معادل‌های فصیح: «موافقت کردن»، «اجازه دادن» یا «مجوز دادن» است.",
            ),
            (
                "CALQUE_END_OF_LINE",
                "major",
                "کاربرد «به پایان خط رسیدن» در معنای درماندگی (گرته‌برداری از reach the end of the line)",
                self._END_OF_LINE_PATTERN,
                "به بن‌بست رسیدن / درمانده شدن",
                "«به پایان خط رسیدن» گرته‌برداری از اصطلاح انگلیسی است. در فارسی اصیل: «به بن‌بست رسیدن» یا «درمانده شدن» به کار می‌رود.",
            ),
        ]

        for rule_id, severity, message, pattern, fix, explanation in rules:
            for match in pattern.finditer(search_text):
                start, end = match.span()
                matched_str = text[start:end]

                # False-positive guard 1: CALQUE_PLAY_ROLE requires "نقش" in matched phrase
                if rule_id == "CALQUE_PLAY_ROLE" and "نقش" not in matched_str:
                    continue

                # False-positive guard 2: CALQUE_COUNT_ON literal counting on paper/tools
                if rule_id == "CALQUE_COUNT_ON":
                    complement = match.group(1).strip()
                    if complement in ("کاغذ", "ماشین‌حساب", "چرتکه"):
                        continue

                findings.append(
                    QualityFinding(
                        rule_id=rule_id,
                        severity=severity,
                        message=message,
                        start=start,
                        end=end,
                        matched_text=matched_str,
                        suggested_fix=fix,
                        explanation=explanation,
                    )
                )

        # Sort findings deterministically by start position, then end position
        findings.sort(key=lambda f: (f.start, f.end))
        return findings


def detect_calques(text: str, skip_code_blocks: bool = True) -> List[QualityFinding]:
    """Inspect Persian text and return structured diagnostic findings without mutating text.

    Architecture Zero §8.2, Locked Decision D09.
    """
    return CalqueDetector(skip_code_blocks=skip_code_blocks).detect(text)
