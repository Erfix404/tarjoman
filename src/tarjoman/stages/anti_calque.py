"""
Linguistic Anti-Calque Engine for Persian Translation.

Detects and eliminates structural and lexical calques (گرته‌برداری‌های نحوی و واژگانی)
based on classical Persian linguistic authorities:
- Abolhassan Najafi (غلط ننویسیم)
- Ahmad Samii Guilani (نگارش و ویرایش)
- Hermes Translation Methodology
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Pattern, Tuple


class AntiCalqueEngine:
    """
    Rule-based anti-calque transformer and detector.
    """

    # 1. Passive by-agent with 'توسط'
    _PASSIVE_BY_PATTERN: Pattern = re.compile(
        r"توسط\s+([^،.\n]+?)\s+(نوشته شد(?:ه است)?|تصویب شد(?:ه است)?|ساخته شد(?:ه است)?|"
        r"به قتل رسید(?:ه است)?|کشته شد(?:ه است)?|انجام شد(?:ه است)?|منتشر شد(?:ه است)?|"
        r"بیان شد(?:ه است)?|ایجاد شد(?:ه است)?|پذیرفته شد(?:ه است)?|اجرا شد(?:ه است)?)",
        re.UNICODE,
    )

    # 2. Playing a role -> ایفا کردن
    _PLAY_ROLE_PATTERN: Pattern = re.compile(
        r"(?:(یک)\s+)?(نقش(?:ی)?(?:\s+(?:کلیدی|مهم|اساسی|محوری|تعیین‌کننده|عمده|برجسته))?)"
        r"(.*?)\bبازی\s+(کردن|کرد|کرده است|کرده‌اند|کردند|(?:می‌|می\s+)کرد|(?:می‌|می\s+)کردند|(?:می‌|می\s+)کند|(?:می‌|می\s+)کنند|کند|کنند)\b",
        re.UNICODE,
    )

    # 3. Rely on / Count on -> اعتماد کردن / تکیه کردن
    _COUNT_ON_PATTERN: Pattern = re.compile(
        r"روی\s+([^،.\n]+?)\s+حساب\s+(کردن|کرد|کرده است|کرده|(?:می‌|می\s+)کند|(?:می‌|می\s+)کنند|(?:می‌|می\s+)کنم|"
        r"(?:می‌|می\s+)کنی|(?:می‌|می\s+)کنیم|(?:می‌|می\s+)کنید|کردند|کردم|کردی|کردیم|کن|نکن|کنید|نکنید|نکنم|نکند)",
        re.UNICODE,
    )

    # 4. Act as -> در جایگاه ... بودن
    _ACT_AS_PATTERN: Pattern = re.compile(
        r"به عنوانِ?\s+([^،.\n]+?)\s+عمل\s+(کردن|کرد|کرده است|کرده|(?:می‌|می\s+)کند|(?:می‌|می\s+)کنند|کردند|(?:می‌|می\s+)کرد|(?:می‌|می\s+)کردند)",
        re.UNICODE,
    )

    # 5. At the end of the day -> در نهایت / عاقبت
    _END_OF_DAY_PATTERN: Pattern = re.compile(r"\bدر پایان روز\b", re.UNICODE)

    # 6. Makes sense -> منطقی است / معقول است
    _MAKES_SENSE_PATTERN: Pattern = re.compile(
        r"\bحس ایجاد\s+((?:می‌|می\s+)کند|(?:می‌|می\s+)کرد|کرد|(?:نمی‌|نمی\s+)کند|(?:نمی‌|نمی\s+)کرد|نکرد|کردن)\b", re.UNICODE
    )
    _MAKES_SENSE_CONTEXTUAL_PATTERN: Pattern = re.compile(
        r"\b(این\s+(?:حرف|ادعا|موضوع|نکته))\s+(معنا|معنی)\s+((?:می‌|می\s+)دهد|(?:نمی‌|نمی\s+)دهد|داد)\b",
        re.UNICODE,
    )

    # 7. Make a decision -> تصمیم‌گیری کردن / تصمیمی اتخاذ کردن
    _MAKE_DECISION_PATTERN: Pattern = re.compile(
        r"\bیک\s+تصمیم\s+(گرفتن|گرفت|گرفتند|گرفته است|گرفته‌اند|(?:می‌|می\s+)گیرد|(?:می‌|می\s+)گیرند|بگیرد|بگیرند|"
        r"گرفتیم|گرفتم|بگیریم|بگیرم)\b",
        re.UNICODE,
    )

    # 8. Open fire -> شلیک کردن / تیراندازی کردن
    _OPEN_FIRE_PATTERN: Pattern = re.compile(
        r"\bآتش\s+(گشودن|گشود|گشودند|(?:می‌|می\s+)گشایند|(?:می‌|می\s+)گشاید|گشوده شد|گشوده شده است)\b",
        re.UNICODE,
    )

    # 9. Take a bath / shower -> حمام کردن / دوش گرفتن
    _TAKE_BATH_PATTERN: Pattern = re.compile(
        r"\bحمام\s+(گرفتن|گرفت|گرفتند|(?:می‌|می\s+)گیرد|(?:می‌|می\s+)گیرند|بگیرد|بگیرند|بگیرید|گرفته است)\b",
        re.UNICODE,
    )

    # 10. Point of view -> دیدگاه / دیدگاه‌ها
    _POINT_OF_VIEW_PATTERN: Pattern = re.compile(
        r"\bنقطه[‌\s]?(نظرات|نظرها|نظر)\b", re.UNICODE
    )

    # 11. Give green light -> موافقت کردن / اجازه دادن
    _GREEN_LIGHT_PATTERN: Pattern = re.compile(
        r"\bچراغ\s+سبز\s+نشان\s+(دادن|داد|دادند|(?:می‌|می\s+)دهد|(?:می‌|می\s+)دهند|داده است|داده‌اند|دهد|دهند)\b",
        re.UNICODE,
    )

    # 12. Reach the end of the line -> به بن‌بست رسیدن / درمانده شدن
    _END_OF_LINE_PATTERN: Pattern = re.compile(
        r"\bبه پایان خط\s+(رسیدن|رسید|رسیدند|(?:می‌|می\s+)رسد|(?:می‌|می\s+)رسند|رسیده است|رسیده‌اند|برسد|برسند)\b",
        re.UNICODE,
    )

    # Auxiliary mappings
    _COUNT_ON_VERB_MAP: Dict[str, str] = {
        "کردن": "کردن",
        "کرد": "کرد",
        "کرده است": "کرده است",
        "کرده": "کرده",
        "می‌کند": "می‌کند",
        "می‌کنند": "می‌کنند",
        "می‌کنم": "می‌کنم",
        "می‌کنی": "می‌کنی",
        "می‌کنیم": "می‌کنیم",
        "می‌کنید": "می‌کنید",
        "کردند": "کردند",
        "کردم": "کردم",
        "کردی": "کردی",
        "کردیم": "کردیم",
        "کن": "کن",
        "نکن": "نکن",
        "کنید": "کنید",
        "نکنید": "نکنید",
        "نکنم": "نکنم",
        "نکند": "نکند",
    }

    _ACT_AS_VERB_MAP: Dict[str, str] = {
        "کردن": "بودن",
        "کرد": "بود",
        "کرده است": "بوده است",
        "کرده": "بوده",
        "می‌کند": "است",
        "می‌کنند": "هستند",
        "کردند": "بودند",
        "می‌کرد": "بود",
        "می‌کردند": "بودند",
    }

    _MAKES_SENSE_VERB_MAP: Dict[str, str] = {
        "می‌کند": "منطقی است",
        "نمی‌کند": "منطقی نیست",
        "کرد": "منطقی بود",
        "نکرد": "منطقی نبود",
        "می‌کرد": "منطقی به نظر می‌رسید",
        "نمی‌کرد": "منطقی به نظر نمی‌رسید",
        "کردن": "منطقی بودن",
    }

    _DECISION_VERB_MAP: Dict[str, str] = {
        "گرفتن": "تصمیم‌گیری کردن",
        "گرفت": "تصمیمی اتخاذ کرد",
        "گرفتند": "تصمیمی اتخاذ کردند",
        "گرفته است": "تصمیمی اتخاذ کرده است",
        "گرفته‌اند": "تصمیمی اتخاذ کرده‌اند",
        "می‌گیرد": "تصمیمی اتخاذ می‌کند",
        "می‌گیرند": "تصمیمی اتخاذ می‌کنند",
        "بگیرد": "تصمیمی اتخاذ کند",
        "بگیرند": "تصمیمی اتخاذ کنند",
        "گرفتیم": "تصمیمی اتخاذ کردیم",
        "گرفتم": "تصمیمی اتخاذ کردم",
        "بگیریم": "تصمیمی اتخاذ کنیم",
        "بگیرم": "تصمیمی اتخاذ کنم",
    }

    _OPEN_FIRE_MAP: Dict[str, str] = {
        "گشودن": "تیراندازی کردن",
        "گشود": "شلیک کرد",
        "گشودند": "شلیک کردند",
        "می‌گشاید": "شلیک می‌کند",
        "می‌گشایند": "شلیک می‌کنند",
        "گشوده شد": "شلیک شد",
        "گشوده شده است": "شلیک شده است",
    }

    _TAKE_BATH_MAP: Dict[str, str] = {
        "گرفتن": "دوش گرفتن",
        "گرفت": "دوش گرفت",
        "گرفتند": "دوش گرفتند",
        "می‌گیرد": "دوش می‌گیرد",
        "می‌گیرند": "دوش می‌گیرند",
        "بگیرد": "دوش بگیرد",
        "بگیرید": "دوش بگیرید",
        "بگیرند": "دوش بگیرند",
        "گرفته است": "دوش گرفته است",
    }

    _GREEN_LIGHT_MAP: Dict[str, str] = {
        "دادن": "موافقت کردن",
        "داد": "موافقت کرد",
        "دادند": "موافقت کردند",
        "می‌دهد": "موافقت می‌کند",
        "می‌دهند": "موافقت می‌کنند",
        "داده است": "موافقت کرده است",
        "داده‌اند": "موافقت کرده‌اند",
        "دهد": "موافقت کند",
        "دهند": "موافقت کنند",
    }

    _END_OF_LINE_MAP: Dict[str, str] = {
        "رسیدن": "به بن‌بست رسیدن",
        "رسید": "به بن‌بست رسید",
        "رسیدند": "به بن‌بست رسیدند",
        "می‌رسد": "به بن‌بست می‌رسد",
        "می‌رسند": "به بن‌بست می‌رسند",
        "رسیده است": "به بن‌بست رسیده است",
        "رسیده‌اند": "به بن‌بست رسیده‌اند",
        "برسد": "به بن‌بست برسد",
        "برسند": "به بن‌بست برسند",
    }

    @classmethod
    def eliminate_calques(cls, text: str) -> str:
        """
        Replace banned calques with idiomatic Persian constructions.
        """
        if not text:
            return text

        result = text

        def _norm_verb(v: str) -> str:
            return re.sub(r"^(ن?می)\s+", r"\1‌", v)

        # 1. Passive by-agent with 'توسط' -> به دست \1 \2
        result = cls._PASSIVE_BY_PATTERN.sub(r"به دست \1 \2", result)

        # 2. Playing a role -> ایفا کردن
        def _replace_play_role(m: re.Match) -> str:
            role_part = m.group(2) or "نقش"
            intervening = m.group(3) or ""
            verb = _norm_verb(m.group(4))
            return f"{role_part}{intervening}ایفا {verb}"

        result = cls._PLAY_ROLE_PATTERN.sub(_replace_play_role, result)

        # 3. Rely on / Count on -> به \1 اعتماد کردن
        def _replace_count_on(m: re.Match) -> str:
            complement = m.group(1).strip()
            raw_verb = _norm_verb(m.group(2))
            mapped_verb = cls._COUNT_ON_VERB_MAP.get(raw_verb, "اعتماد کردن")
            return f"به {complement} اعتماد {mapped_verb}"

        result = cls._COUNT_ON_PATTERN.sub(_replace_count_on, result)

        # 4. Act as -> در جایگاه \1 بودن
        def _replace_act_as(m: re.Match) -> str:
            role = m.group(1).strip()
            raw_verb = _norm_verb(m.group(2))
            mapped_verb = cls._ACT_AS_VERB_MAP.get(raw_verb, "بودن")
            return f"در جایگاه {role} {mapped_verb}"

        result = cls._ACT_AS_PATTERN.sub(_replace_act_as, result)

        # 5. At the end of the day -> در نهایت
        result = cls._END_OF_DAY_PATTERN.sub("در نهایت", result)

        # 6. Makes sense -> منطقی است
        def _replace_makes_sense(m: re.Match) -> str:
            verb = _norm_verb(m.group(1))
            return cls._MAKES_SENSE_VERB_MAP.get(verb, "منطقی است")

        result = cls._MAKES_SENSE_PATTERN.sub(_replace_makes_sense, result)

        def _replace_makes_sense_contextual(m: re.Match) -> str:
            subject = m.group(1)
            verb = _norm_verb(m.group(3))
            if "نمی" in verb:
                return f"{subject} منطقی نیست"
            elif verb == "داد":
                return f"{subject} منطقی بود"
            return f"{subject} منطقی است"

        result = cls._MAKES_SENSE_CONTEXTUAL_PATTERN.sub(_replace_makes_sense_contextual, result)

        # 7. Make a decision -> تصمیم‌گیری کردن / تصمیمی اتخاذ کردن
        def _replace_decision(m: re.Match) -> str:
            raw_verb = _norm_verb(m.group(1))
            return cls._DECISION_VERB_MAP.get(raw_verb, "تصمیم‌گیری کردن")

        result = cls._MAKE_DECISION_PATTERN.sub(_replace_decision, result)

        # 8. Open fire -> شلیک کردن
        def _replace_open_fire(m: re.Match) -> str:
            raw_verb = _norm_verb(m.group(1))
            return cls._OPEN_FIRE_MAP.get(raw_verb, "شلیک کردن")

        result = cls._OPEN_FIRE_PATTERN.sub(_replace_open_fire, result)

        # 9. Take a bath / shower -> دوش گرفتن
        def _replace_take_bath(m: re.Match) -> str:
            raw_verb = _norm_verb(m.group(1))
            return cls._TAKE_BATH_MAP.get(raw_verb, "دوش گرفتن")

        result = cls._TAKE_BATH_PATTERN.sub(_replace_take_bath, result)

        # 10. Point of view -> دیدگاه / دیدگاه‌ها
        def _replace_pov(m: re.Match) -> str:
            matched_suffix = m.group(1)
            if matched_suffix in ("نظرات", "نظرها"):
                return "دیدگاه‌ها"
            return "دیدگاه"

        result = cls._POINT_OF_VIEW_PATTERN.sub(_replace_pov, result)

        # 11. Green light -> موافقت کردن
        def _replace_green_light(m: re.Match) -> str:
            raw_verb = _norm_verb(m.group(1))
            return cls._GREEN_LIGHT_MAP.get(raw_verb, "موافقت کردن")

        result = cls._GREEN_LIGHT_PATTERN.sub(_replace_green_light, result)

        # 12. Reach the end of the line -> به بن‌بست رسیدن
        def _replace_end_of_line(m: re.Match) -> str:
            raw_verb = _norm_verb(m.group(1))
            return cls._END_OF_LINE_MAP.get(raw_verb, "به بن‌بست رسیدن")

        result = cls._END_OF_LINE_PATTERN.sub(_replace_end_of_line, result)

        return result

    @classmethod
    def refine_sentence(cls, text: str) -> str:
        """Alias to eliminate_calques."""
        return cls.eliminate_calques(text)

    @classmethod
    def detect_calques(cls, text: str) -> List[str]:
        """
        Detect calques in the given text and return list of detected occurrences.
        """
        if not text:
            return []

        detected: List[str] = []

        patterns: List[Tuple[Pattern, str]] = [
            (cls._PASSIVE_BY_PATTERN, "توسط (مجهول با عامل)"),
            (cls._PLAY_ROLE_PATTERN, "نقش بازی کردن"),
            (cls._COUNT_ON_PATTERN, "روی کسی حساب کردن"),
            (cls._ACT_AS_PATTERN, "به عنوان عمل کردن"),
            (cls._END_OF_DAY_PATTERN, "در پایان روز"),
            (cls._MAKES_SENSE_PATTERN, "حس ایجاد می‌کند"),
            (cls._MAKES_SENSE_CONTEXTUAL_PATTERN, "معنا می‌دهد (makes sense)"),
            (cls._MAKE_DECISION_PATTERN, "یک تصمیم گرفتن"),
            (cls._OPEN_FIRE_PATTERN, "آتش گشودن"),
            (cls._TAKE_BATH_PATTERN, "حمام گرفتن"),
            (cls._POINT_OF_VIEW_PATTERN, "نقطه نظر"),
            (cls._GREEN_LIGHT_PATTERN, "چراغ سبز نشان دادن"),
            (cls._END_OF_LINE_PATTERN, "به پایان خط رسیدن"),
        ]

        for pat, _label in patterns:
            for match in pat.finditer(text):
                detected.append(match.group(0).strip())

        return detected
