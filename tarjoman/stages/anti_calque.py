"""
Linguistic Anti-Calque Engine for Persian Translation — Super-Skill v2.

Detects and eliminates structural and lexical calques (گرته‌برداری‌های نحوی و واژگانی)
based on classical Persian linguistic authorities:
- Abolhassan Najafi (غلط ننویسیم)
- Ahmad Samii Guilani (نگارش و ویرایش)
- Hermes Translation Methodology

v2 additions over the original 12-rule engine:
- Expanded Najafi/Samii syntactic and lexical rules: generic passive-by fallback
  (توسط / به‌وسیله / از سوی with any passive verb), به اجرا درآوردن، به کار گرفتن،
  اعمال کردن، به عمل آوردن، اقدام/مبادرت به، مورد استفاده قرار دادن/گرفتن،
  تحت پوشش قرار دادن، در اختیار قرار دادن، دارای بودن، می‌باشد، گردید،
  در رابطه با / در ارتباط با / در خصوص، جهت (for برای), درحالی‌که، از آنجا که،
  بنابراین، عنوان کردن، قلمداد/تلقی کردن، به‌عنوان orthographic join.
- Guaranteed ZERO em-dash policy (:meth:`eliminate_em_dashes`): paired dashes
  become parentheses, lone dashes become Persian commas. No ``—`` / ``–`` / ``--``
  survives.
- Persian guillemet normalization (:meth:`normalize_quotes`): straight, curly,
  and single quotes all become ``«»``.
- Strict ZWNJ normalization (:meth:`normalize_zwnj`): verbal prefixes, plurals,
  comparatives, clitics, ه‌ای, silent-heh ezafe ی, subjunctive ب/ن prefixes.
- Arabic character standardization (:meth:`standardize_arabic_chars`):
  ي → ی, ك → ک, ى → ی, ة → ه, tatweel removal.
- One-call pipeline (:meth:`normalize_persian_typography`).
- Verbatim masking helpers for composers (:func:`mask_verbatim_spans`,
  :func:`restore_verbatim_spans`).
- Shared lint pattern table (:data:`LINT_CALQUE_PATTERNS`) consumed by both
  the in-package linter (``tarjoman/linter.py``) and the skillpack script
  (``.claude/skills/tarjoman/scripts/linter.py``).
"""
from __future__ import annotations

import re
from typing import Dict, List, Pattern, Tuple

# -----------------------------------------------------------------------------
# Shared helpers & constants
# -----------------------------------------------------------------------------

#: Zero-Width Non-Joiner (نیم‌فاصله)
ZWNJ = "‌"

#: Bidi isolates used by composers to protect LTR spans inside RTL text.
LRI = "⁦"  # U+2066 LEFT-TO-RIGHT ISOLATE
PDI = "⁩"  # U+2069 POP DIRECTIONAL ISOLATE

#: Arabic → Persian character map (unmasking step).
ARABIC_CHAR_MAP: Dict[str, str] = {
    "ي": "ی",
    "ك": "ک",
    "ى": "ی",
    "ة": "ه",
}

#: Tatweel (کشیda) — always stripped in standard Persian orthography.
_TATWEEL_RE: Pattern = re.compile("ـ")

#: 34-verb ZWNJ engine: strict present/past stems for common Persian verbs.
#: Ceiling: only these attested stems; new verbs extend this alternation.
_VERB_34_STEMS = (
    r"(?:رو|رفت|آی|آمد|گو|گفت|زن|زد|بین|دید|گذار|گذاشت|خوان|نوشت|دان|"
    r"رسید|رس|بر|برد|خور|پوش|خواب|ایست|نشین|شنو|شنید|پرس|خر|خرید|فروش|"
    r"فروخت|آور|آورد|افت|افتاد|فرست|بند|بست|شوی|شست|ساز|ساخت|پز|پخت|"
    r"سوز|سوخت|ترس|کش|کشت|میر|مرد|تاب|روی|پیچ)\w*"
)
#: Strict left boundary (start / whitespace / brackets / quotes / ZWNJ) so
#: embedded «می» words (صمیمی، زمین، شیمی، امید) are never touched.
_VERB_34_RE: Pattern = re.compile(
    r"(?<![^\s\(\[\{«\"'‌])(می|نمی)\s+(" + _VERB_34_STEMS + r")",
    re.UNICODE,
)

#: Generic کردن-family verb alternation reused by new lexical rules.
_KARDAN_VERBS = (
    r"(?:کردن|کرد|کردند|کردم|کردی|کردیم|کرده است|کرده‌اند|کرده|"
    r"(?:ن?می‌|ن?می\s+)کند|(?:ن?می‌|ن?می\s+)کنند|بکند|بکنند|نکند|نکنند)"
)

#: Generic دادن-family verb alternation reused by new lexical rules.
_DADAN_VERBS = (
    r"(?:دادن|داد|دادند|دادم|داده است|داده‌اند|داده|"
    r"(?:ن?می‌|ن?می\s+)دهد|(?:ن?می‌|ن?می\s+)دهند|بدهد|بدهند|ندهید)"
)

#: Generic گرفتن-family verb alternation reused by new lexical rules.
_GEREFTAN_VERBS = (
    r"(?:گرفتن|گرفت|گرفتند|گرفتم|گرفته است|گرفته‌اند|گرفته|"
    r"(?:ن?می‌|ن?می\s+)گیرد|(?:ن?می‌|ن?می\s+)گیرند|بگیرد|بگیرند)"
)


def _norm_verb(v: str) -> str:
    """Collapse a spaced verbal prefix (``می کند``) into ZWNJ form (``می‌کند``)."""
    return re.sub(r"^(ن?می)\s+", r"\1‌", v)


# -----------------------------------------------------------------------------
# Verbatim masking (for composers: protect code / math / URLs from normalization)
# -----------------------------------------------------------------------------

_VERBATIM_PATTERN: Pattern = re.compile(
    r"(```[^\n]*\n.*?```)"  # fenced code blocks (may span lines)
    r"|(`[^`\n]+`)"  # inline code
    r"|(\$\$.+?\$\$|(?<!\\)\$.+?(?<!\\)\$|\\\[.+?\\\]|\\\(.+?\\\))"  # math
    r"|(https?://[^\s<>\]\)\}«»\"']+|[\w.+-]+@[\w-]+\.[\w.]+)",  # URLs & emails
    re.UNICODE | re.DOTALL,
)


def mask_verbatim_spans(text: str) -> Tuple[str, Dict[str, str]]:
    """
    Replace code / math / URL / email spans with opaque placeholders.

    Returns:
        (masked_text, table) where table maps placeholder → original span.
    """
    if not text:
        return text, {}
    table: Dict[str, str] = {}

    def _mask(m: re.Match) -> str:
        token = f"⟦VERBATIM_{len(table)}⟧"
        table[token] = m.group(0)
        return token

    return _VERBATIM_PATTERN.sub(_mask, text), table


def restore_verbatim_spans(text: str, table: Dict[str, str]) -> str:
    """Restore spans previously masked by :func:`mask_verbatim_spans`."""
    for token, original in table.items():
        text = text.replace(token, original)
    return text


class AntiCalqueEngine:
    """
    Rule-based anti-calque transformer, detector, and typography normalizer.
    """

    # =========================================================================
    # Original 12 rules (preserved verbatim for backward compatibility)
    # =========================================================================

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
        r"\bنقطه[‌\s\-]?(نظرات|نظرها|نظر)\b", re.UNICODE
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

    # =========================================================================
    # v2 syntactic rules (Najafi / Samii)
    # =========================================================================

    # 13. Generic passive-by fallback: توسط / به‌وسیله / از سوی + ANY passive verb
    #     Runs AFTER the specific rule above (which already consumed its matches).
    _PASSIVE_BY_GENERIC_PATTERN: Pattern = re.compile(
        r"(?:توسط|به‌وسیله|از\s+سوی)\s+([^،.؟!:\n]{1,60}?)\s+"
        r"((?:\S+\s+)?(?:شد(?:ه(?: است|‌اند)?|ند)?|گردید(?:ند)?|گردیده(?: است|‌اند)?|"
        r"(?:ن?می‌|ن?می\s+)شوند?|بشو(?:د|ند)|نشو(?:د|ند)))",
        re.UNICODE,
    )

    # 14. می‌باشد family -> است family (Najafi: بودن، نه باشیدن)
    _MIBASHAD_PATTERN: Pattern = re.compile(
        r"\b(ن?می‌باشد|ن?می‌باشند|ن?می‌باشم|ن?می‌باشی|ن?می‌باشیم|ن?می‌باشید)\b",
        re.UNICODE,
    )
    _MIBASHAD_MAP: Dict[str, str] = {
        "می‌باشم": "هستم",
        "می‌باشی": "هستی",
        "می‌باشد": "است",
        "می‌باشیم": "هستیم",
        "می‌باشید": "هستید",
        "می‌باشند": "هستند",
        "نمی‌باشد": "نیست",
        "نمی‌باشند": "نیستند",
        "نمی‌باشم": "نیستم",
        "نمی‌باشی": "نیستی",
        "نمی‌باشیم": "نیستیم",
        "نمی‌باشید": "نیستید",
    }

    # 15. گردید family -> شد family (Najafi: شدن، نه گردیدن)
    _GARDID_PATTERN: Pattern = re.compile(
        r"\b((?:ن?می‌|ن?می\s+)گردد|(?:ن?می‌|ن?می\s+)گردند|بگردد|بگردند|نگردد|نگردند|"
        r"گردید|گردیدند|گردیده است|گردیده‌اند|گردیده|گردیدن)\b",
        re.UNICODE,
    )
    _GARDID_MAP: Dict[str, str] = {
        "می‌گردد": "می‌شود",
        "نمی‌گردد": "نمی‌شود",
        "می‌گردند": "می‌شوند",
        "نمی‌گردند": "نمی‌شوند",
        "بگردد": "بشود",
        "بگردند": "بشوند",
        "نگردد": "نشود",
        "نگردند": "نشوند",
        "گردید": "شد",
        "گردیدند": "شدند",
        "گردیده": "شده",
        "گردیده است": "شده است",
        "گردیده‌اند": "شده‌اند",
        "گردیدن": "شدن",
    }

    # 16. دارای X بودن -> X داشتن
    _DARAYE_PATTERN: Pattern = re.compile(
        r"\bدارای\s+([^،.\n]+?)\s+(ن?می‌باشد|ن?می‌باشند|است|هست|بود|نبود|خواهد بود|باشد|باشند|هستند)\b",
        re.UNICODE,
    )
    _DARAYE_MAP: Dict[str, str] = {
        "است": "دارد",
        "هست": "دارد",
        "هستند": "دارند",
        "بود": "داشت",
        "نبود": "نداشت",
        "خواهد بود": "خواهد داشت",
        "باشد": "داشته باشد",
        "باشند": "داشته باشند",
        "می‌باشد": "دارد",
        "می‌باشند": "دارند",
        "نمی‌باشد": "ندارد",
    }

    # 17. درحالی‌که / از آنجا که / بنابراین (orthographic joins)
    _DAR_HALI_KE_PATTERN: Pattern = re.compile(r"\bدر\s+حالی\s+که\b", re.UNICODE)
    _AZ_ANJAYI_PATTERN: Pattern = re.compile(r"\bاز\s+آنجایی\s+که\b", re.UNICODE)
    _BANA_BAR_IN_PATTERN: Pattern = re.compile(r"\bبنا\s+بر\s+این\b", re.UNICODE)

    # 18. به‌عنوان orthographic join (bare uses; the عمل‌کردن construction
    #     is already eliminated by rule 4 which runs first).
    _BE_ONVAN_PATTERN: Pattern = re.compile(r"\bبه\s+عنوان\b", re.UNICODE)

    # =========================================================================
    # v2 lexical rules (Najafi / Samii)
    # =========================================================================

    # 19. به اجرا درآوردن -> اجرا کردن
    _BE_EJRA_PATTERN: Pattern = re.compile(
        r"\bبه\s+اجرا\s+در(آوردن|آورد|آورده است|آورده‌اند|آورده|(?:می‌|می\s+)آورد|آوردند|آوردم|بیاورد)\b",
        re.UNICODE,
    )
    _BE_EJRA_MAP: Dict[str, str] = {
        "آوردن": "اجرا کردن",
        "آورد": "اجرا کرد",
        "آورده": "اجرا کرده",
        "آورده است": "اجرا کرده است",
        "آورده‌اند": "اجرا کرده‌اند",
        "می‌آورد": "اجرا می‌کند",
        "آوردند": "اجرا کردند",
        "آوردم": "اجرا کردم",
        "بیاورد": "اجرا بکند",
    }

    # 20. به کار گرفتن -> به کار بردن
    _BE_KAR_GEREFTAN_PATTERN: Pattern = re.compile(
        rf"\bبه\s+کار\s+(گرفتن|گرفت|گرفتند|گرفتم|گرفته است|گرفته‌اند|گرفته|"
        rf"(?:می‌|می\s+)گیرد|(?:می‌|می\s+)گیرند|بگیرد|بگیرند)\b",
        re.UNICODE,
    )
    _BE_KAR_MAP: Dict[str, str] = {
        "گرفتن": "به کار بردن",
        "گرفت": "به کار برد",
        "گرفتند": "به کار بردند",
        "گرفتم": "به کار بردم",
        "گرفته": "به کار برده",
        "گرفته است": "به کار برده است",
        "گرفته‌اند": "به کار برده‌اند",
        "می‌گیرد": "به کار می‌برد",
        "می‌گیرند": "به کار می‌برند",
        "بگیرد": "به کار ببرد",
        "بگیرند": "به کار ببرند",
    }

    # 21. اعمال کردن -> اجرا کردن (keep conjugation, swap the noun)
    _EMAL_PATTERN: Pattern = re.compile(rf"\bاعمال\s+({_KARDAN_VERBS})\b", re.UNICODE)

    # 22. به عمل آوردن -> انجام دادن
    _BE_AMAL_PATTERN: Pattern = re.compile(
        r"\bبه\s+عمل\s+(آوردن|آورد|آورده است|آورده‌اند|آورده|(?:می‌|می\s+)آورد|آوردند|آوردم|بیاورد)\b",
        re.UNICODE,
    )
    _BE_AMAL_MAP: Dict[str, str] = {
        "آوردن": "انجام دادن",
        "آورد": "انجام داد",
        "آورده": "انجام داده",
        "آورده است": "انجام داده است",
        "آورده‌اند": "انجام داده‌اند",
        "می‌آورد": "انجام می‌دهد",
        "آوردند": "انجام دادند",
        "آوردم": "انجام دادم",
        "بیاورد": "انجام بدهد",
    }

    # 23. اقدام/مبادرت به X کردن -> X کردن (drop the hollow light verb)
    _EGHDAM_PATTERN: Pattern = re.compile(
        rf"\b(?:اقدام|مبادرت)\s+به\s+(\S+)\s+({_KARDAN_VERBS})\b",
        re.UNICODE,
    )

    # 24. مورد استفاده قرار دادن/گرفتن -> به کار بردن/رفتن
    _MORDE_ESTEFADE_PATTERN: Pattern = re.compile(
        r"\bمورد\s+استفاده\s+قرار\s+"
        r"(دادن|داد|دادند|داده است|داده‌اند|(?:می‌|می\s+)دهد|(?:می‌|می\s+)دهند|بدهد|"
        r"گرفتن|گرفت|گرفتند|گرفته است|گرفته‌اند|(?:می‌|می\s+)گیرد|بگیرد)\b",
        re.UNICODE,
    )
    _MORDE_ESTEFADE_MAP: Dict[str, str] = {
        "دادن": "به کار بردن",
        "داد": "به کار برد",
        "دادند": "به کار بردند",
        "داده است": "به کار برده است",
        "داده‌اند": "به کار برده‌اند",
        "می‌دهد": "به کار می‌برد",
        "می‌دهند": "به کار می‌برند",
        "بدهد": "به کار ببرد",
        "گرفتن": "به کار رفتن",
        "گرفت": "به کار رفت",
        "گرفتند": "به کار رفتند",
        "گرفته است": "به کار رفته است",
        "گرفته‌اند": "به کار رفته‌اند",
        "می‌گیرد": "به کار می‌رود",
        "بگیرد": "به کار برود",
    }

    # 25. در اختیار X قرار دادن -> در اختیار X گذاشتن (object preserved)
    _DAR_EKHTIYAR_PATTERN: Pattern = re.compile(
        rf"\bدر\s+اختیار\s+([^،.؟!:\n]{{1,60}}?)\s+قرار\s+({_DADAN_VERBS})\b",
        re.UNICODE,
    )
    _DAR_EKHTIYAR_MAP: Dict[str, str] = {
        "دادن": "گذاشتن",
        "داد": "گذاشت",
        "دادند": "گذاشتند",
        "دادم": "گذاشتم",
        "داده": "گذاشته",
        "داده است": "گذاشته است",
        "داده‌اند": "گذاشته‌اند",
        "می‌دهد": "می‌گذارد",
        "می‌دهند": "می‌گذارند",
        "بدهد": "بگذارد",
        "بدهند": "بگذارند",
        "ندهید": "نگذارید",
    }

    # 26. تحت X قرار دادن -> X دادن (drop the hollow قرار)
    _TAHTE_PATTERN: Pattern = re.compile(
        rf"\bتحت\s+(پوشش|حمایت|درمان|نظارت|فشار|تعقیب|پیگرد)\s+قرار\s+({_DADAN_VERBS})\b",
        re.UNICODE,
    )

    # 27. در رابطه با / در ارتباط با / در خصوص -> درباره
    _DAR_RABETE_PATTERN: Pattern = re.compile(
        r"\bدر\s+(?:رابطه|ارتباط)\s+با\b|\bدر\s+خصوص\b", re.UNICODE
    )

    # 28. جهت (= برای) -> برای (guarded: از/بدین/همین/این/آن/چه جهت stay)
    _JAHAT_PATTERN: Pattern = re.compile(
        r"(از|بدین|همین|این|آن|چه)\s+جهت\b|\bجهت\b",
        re.UNICODE,
    )

    # 29. عنوان کردن (to mention/address) -> مطرح کردن
    _ONVAN_PATTERN: Pattern = re.compile(rf"\bعنوان\s+({_KARDAN_VERBS})\b", re.UNICODE)

    # 30. قلمداد/تلقی کردن -> دانستن
    _GHALAMDAD_PATTERN: Pattern = re.compile(
        r"\b(?:قلمداد|تلقی)\s+"
        r"(کردن|کرد|کردند|کرده است|کرده‌اند|کرده|(?:می‌|می\s+)کند|(?:می‌|می\s+)کنند|بکند|بکنند)\b",
        re.UNICODE,
    )
    _GHALAMDAD_MAP: Dict[str, str] = {
        "کردن": "دانستن",
        "کرد": "دانست",
        "کردند": "دانستند",
        "کرده": "دانسته",
        "کرده است": "دانسته است",
        "کرده‌اند": "دانسته‌اند",
        "می‌کند": "می‌داند",
        "می‌کنند": "می‌دانند",
        "بکند": "بداند",
        "بکنند": "بدانند",
    }

    # =========================================================================
    # v2.1 reverse technical calques (گرته‌برداری‌های معکوس فنی)
    # Ceiling: only the attested dev-doc phrasings below; new verbs join the
    # _TECH_ON_VERBS alternation instead of growing new rules.
    # =========================================================================

    # 31. «TECH-VERB بر روی OBJ» (run/click/call/deploy on) -> «روی OBJ TECH-VERB»
    _TECH_ON_VERBS = r"(?:اجرا|کلیک|فراخوانی|پیاده‌سازی)"
    _TECH_ON_PATTERN: Pattern = re.compile(
        r"\b(?P<tech_verb>" + _TECH_ON_VERBS + r")\s+(?P<tech_v>" + _KARDAN_VERBS + r")\s+بر\s+روی\s+(?P<tech_obj>[^،.؟!:\n]{1,60})"
        r"|\bاستقرار\s+(?P<est_v>" + _DADAN_VERBS + r")\s+بر\s+روی\s+(?P<est_obj>[^،.؟!:\n]{1,60})"
        r"|\bبالا\s+(?P<bala_v>آوردن|آورد|آوردند|آورده است|آورده‌اند|آورده|(?:می‌|می\s+)آورد|بیاورد)\s+بر\s+روی\s+(?P<bala_obj>[^،.؟!:\n]{1,60})",
        re.UNICODE,
    )

    # 32. اتصال زدن-family -> متصل شدن-family (the «به X» complement stays put)
    _ETTESAL_PATTERN: Pattern = re.compile(
        r"\bاتصال\s+(زدن|زد|زدند|زده است|زده‌اند|زده|(?:ن?می‌|ن?می\s+)زند|(?:ن?می‌|ن?می\s+)زنند|بزن|بزنند|نزن)\b",
        re.UNICODE,
    )
    _ETTESAL_MAP: Dict[str, str] = {
        "زدن": "متصل شدن",
        "زد": "متصل شد",
        "زدند": "متصل شدند",
        "زده": "متصل شده",
        "زده است": "متصل شده است",
        "زده‌اند": "متصل شده‌اند",
        "می‌زند": "متصل می‌شود",
        "نمی‌زند": "متصل نمی‌شود",
        "می‌زنند": "متصل می‌شوند",
        "بزن": "متصل شو",
        "بزنند": "متصل شوند",
        "نزن": "متصل نشو",
    }

    # 33. استقرار + دادن-family -> مستقر + کردن-family
    _ESTEGHRAR_PATTERN: Pattern = re.compile(
        r"\bاستقرار\s+(" + _DADAN_VERBS + r")\b",
        re.UNICODE,
    )
    _ESTEGHRAR_MAP: Dict[str, str] = {
        "دادن": "مستقر کردن",
        "داد": "مستقر کرد",
        "دادند": "مستقر کردند",
        "دادم": "مستقر کردم",
        "داده": "مستقر کرده",
        "داده است": "مستقر کرده است",
        "داده‌اند": "مستقر کرده‌اند",
        "می‌دهد": "مستقر می‌کند",
        "می‌دهند": "مستقر می‌کنند",
        "بدهد": "مستقر بکند",
        "بدهند": "مستقر بکنند",
        "ندهید": "مستقر نکنید",
    }

    # 34. ارور + گرفتن-family (either order) -> خطا + گرفتن-family (noun swap only)
    _ERROR_GET_PATTERN: Pattern = re.compile(
        r"\b(ارور)\s+(" + _GEREFTAN_VERBS + r")\b|\b(" + _GEREFTAN_VERBS + r")\s+(ارور)\b",
        re.UNICODE,
    )

    # =========================================================================
    # Original auxiliary mappings (preserved verbatim)
    # =========================================================================
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

    # =========================================================================
    # ZERO em-dash policy
    # =========================================================================

    #: Paired dashes (parenthetical insertion) -> Persian parentheses.
    _PAIRED_DASH_PATTERN: Pattern = re.compile(
        r"[—–]\s*([^—–\n]{1,200}?)\s*[—–]"
        r"|(?<!\S)--\s*([^—–\n]{1,200}?)\s*--(?!\S)",
        re.UNICODE,
    )
    #: Lone dashes -> Persian comma. ``--`` only counts when standalone
    #: (so CLI flags like ``--output`` are never touched).
    _LONE_DASH_PATTERN: Pattern = re.compile(
        r"\s*[—–]\s*|(?<!\S)--(?!\S)",
        re.UNICODE,
    )

    @classmethod
    def eliminate_em_dashes(cls, text: str) -> str:
        """
        Enforce the ZERO em-dash policy.

        - Paired dashes (an insertion between two dashes) become Persian
          parentheses: ``او آمد — خسته — رفت`` → ``او آمد (خسته) رفت``.
        - Lone dashes become Persian commas (ویرگول فارسی ``،``).
        - Standalone double hyphens (``--``) are treated as em-dashes, except
          inside tokens such as CLI flags (``--output`` is preserved).

        Guarantees: no ``—``, ``–``, or standalone ``--`` remains.
        """
        if not text:
            return text

        def _pair(m: re.Match) -> str:
            inner = (m.group(1) if m.group(1) is not None else m.group(2) or "").strip()
            inner = inner.strip("،").strip()
            return f"({inner})" if inner else ""

        result = cls._PAIRED_DASH_PATTERN.sub(_pair, text)
        result = cls._LONE_DASH_PATTERN.sub("، ", result)
        # Tidy artifacts of the conversion.
        result = re.sub(r"\(\s*،\s*", "(", result)
        result = re.sub(r"\s*،\s*\)", ")", result)
        result = re.sub(r"[،,]{2,}", "،", result)
        result = re.sub(r"^[،\s]+", "", result)
        result = re.sub(r"[ ]{2,}", " ", result)
        return result.strip() if text.strip() != text else result

    # =========================================================================
    # Typography normalization (quotes / ZWNJ / Arabic chars)
    # =========================================================================

    _DOUBLE_QUOTE_PATTERN: Pattern = re.compile(r'"([^"\n]+)"', re.UNICODE)
    _CURLY_QUOTE_PATTERN: Pattern = re.compile(r'["“”]([^"“”\n]+)["“”]', re.UNICODE)
    _SINGLE_QUOTE_PATTERN: Pattern = re.compile(
        r"(?<!\w)'([^'\n]+?)'(?!\w)", re.UNICODE
    )
    _SINGLE_CURVY_QUOTE_PATTERN: Pattern = re.compile(
        r"(?<!\w)[‘’]([^‘’\n]+?)[‘’](?!\w)", re.UNICODE
    )

    #: Words after which a bare ی must NOT be joined (به/که/چه/نه + ی-initial word
    #: is correct with a space: «به یاد»، «که یاور»).
    _YE_EXCLUSIONS = frozenset({"به", "که", "چه", "نه"})

    @classmethod
    def standardize_arabic_chars(cls, text: str) -> str:
        """
        Normalize Arabic letters to standard Persian characters.

        - ي → ی, ك → ک, ى → ی, ة → ه
        - Strips tatweel (ـ).
        """
        if not text:
            return text
        for ar, fa in ARABIC_CHAR_MAP.items():
            text = text.replace(ar, fa)
        return _TATWEEL_RE.sub("", text)

    @classmethod
    def normalize_quotes(cls, text: str) -> str:
        """
        Convert all straight / curly / single quotation marks to Persian
        guillemets (``«»``). Apostrophes inside words (children's) are kept.
        """
        if not text:
            return text
        text = cls._DOUBLE_QUOTE_PATTERN.sub(r"«\1»", text)
        text = cls._CURLY_QUOTE_PATTERN.sub(r"«\1»", text)
        text = cls._SINGLE_QUOTE_PATTERN.sub(r"«\1»", text)
        text = cls._SINGLE_CURVY_QUOTE_PATTERN.sub(r"«\1»", text)
        # Clean internal spacing inside Persian quotes.
        text = re.sub(r"«\s+", "«", text)
        text = re.sub(r"\s+»", "»", text)
        return text

    @classmethod
    def normalize_zwnj(cls, text: str) -> str:
        """
        Apply strict Zero-Width Non-Joiner (نیم‌فاصله) rules:

        - Verbal prefixes: می‌ / نمی‌
        - Subjunctive/imperative prefixes: ب‌ / ن‌ (``ب خوان`` → ``بخوان``)
        - Plural suffixes: ها / های
        - Comparative suffixes: تر / ترین
        - Pronominal clitics: ام / ات / اش / مان / تان / شان
        - Indefinite: ه‌ای (``خانه ای`` → ``خانه‌ای``)
        - Silent-heh ezafe: ه‌ی (``خانه ی من`` → ``خانه‌ی من``,
          except after به/که/چه/نه)
        """
        if not text:
            return text
        zwnj = ZWNJ

        # 1. Verbal prefixes: می‌, نمی‌ (34-verb strict engine, then generic fallback)
        text = _VERB_34_RE.sub(rf"\1{zwnj}\2", text)
        text = re.sub(r"(?<![آ-یء-ي])(ن?می)\s+([آ-یء-ي])", rf"\1{zwnj}\2", text)

        # 2. (Removed) Joining a standalone «ب»/«ن» to the next word broke
        #    list items and abbreviations («الف، ب و ج» → «ب‌و ج»), and the
        #    joined form «ب‌خوان» is itself wrong Persian (it is «بخوان»).

        # 3. Plural suffixes: ‌ها, ‌های
        text = re.sub(r"([آ-یء-ي])\s+(های|ها)(?![آ-یء-ي])", rf"\1{zwnj}\2", text)

        # 4. Comparative suffixes: تر, ‌ترین
        text = re.sub(r"([آ-یء-ي])\s+(ترین|تر)(?![آ-یء-ي])", rf"\1{zwnj}\2", text)

        # 5. Pronominal clitics: ‌ام, ‌ات, ‌اش, ‌مان, ‌تان, ‌شان
        text = re.sub(
            r"([آ-یء-ي])\s+(ام|ات|اش|مان|تان|شان)(?![آ-یء-ي])",
            rf"\1{zwnj}\2",
            text,
        )

        # 6. Indefinite suffix: ‌ه‌ای
        text = re.sub(r"([آ-یء-ي]ه)\s+ای(?![آ-یء-ي])", rf"\1{zwnj}ای", text)

        # 7. Silent-heh ezafe ی (guarded against به/که/چه/نه).
        def _join_heh_ye(m: re.Match) -> str:
            word = m.group(1)
            if word in cls._YE_EXCLUSIONS:
                return m.group(0)
            return f"{word}{zwnj}ی"

        text = re.sub(
            r"([آ-یء-ي]+ه)\s+ی(?![آ-یء-ي])",
            _join_heh_ye,
            text,
        )

        # Clean duplicate ZWNJs and spacing around ZWNJ.
        text = re.sub(rf"{zwnj}{{2,}}", zwnj, text)
        text = re.sub(rf"\s+{zwnj}|{zwnj}\s+", zwnj, text)
        return text

    @classmethod
    def normalize_persian_typography(cls, text: str) -> str:
        """
        One-call v2 typography pipeline: Arabic standardization → ZERO
        em-dash → Persian quotes → strict ZWNJ → light spacing tidy.
        """
        if not text:
            return text
        result = cls.standardize_arabic_chars(text)
        result = cls.eliminate_em_dashes(result)
        result = cls.normalize_quotes(result)
        result = cls.normalize_zwnj(result)
        result = re.sub(r"\s+([،؛؟!.:»])", r"\1", result)
        result = re.sub(r"[ \t]{2,}", " ", result)
        return result.strip() if text.strip() == text.strip() else result

    # =========================================================================
    # Calque elimination (original 12 + v2 rules)
    # =========================================================================

    @classmethod
    def eliminate_calques(cls, text: str) -> str:
        """
        Replace banned calques with idiomatic Persian constructions.
        Runs the original 12 rules first (unchanged semantics), then the
        v2 Najafi/Samii syntactic and lexical rules.
        """
        if not text:
            return text

        result = text

        # ---- Original rules 1–12 (unchanged) ----
        # 1. Passive by-agent with 'توسط' -> به دست \1 \2
        result = cls._PASSIVE_BY_PATTERN.sub(r"به دست \1 \2", result)

        # 2. Playing a role -> ایفا کردن
        def _replace_play_role(m: re.Match) -> str:
            role_part = m.group(2) or "نقش"
            intervening = m.group(3) or ""
            # «نقش هملت را بازی کرد» is literal acting, not a calque.
            if re.search(r"(?:^|\s)را(?:\s|$)", intervening):
                return m.group(0)
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
        # «در پایان روز» is NOT auto-rewritten: it is just as often literal
        # («در پایان روز به خانه برگشتیم»). The linter reports it instead.

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

        # ---- v2 syntactic rules 13–18 ----
        # 13. Generic passive-by fallback -> به دست
        result = cls._PASSIVE_BY_GENERIC_PATTERN.sub(r"به دست \1 \2", result)

        # Normalize «به وسیله» spelling before further rules.
        result = re.sub(r"\bبه\s+وسیله\b", "به‌وسیله", result)

        # 14. می‌باشد family -> است family
        def _replace_mibashad(m: re.Match) -> str:
            return cls._MIBASHAD_MAP.get(m.group(1), "است")

        result = cls._MIBASHAD_PATTERN.sub(_replace_mibashad, result)

        # 15. گردید family -> شد family
        def _replace_gardid(m: re.Match) -> str:
            verb = _norm_verb(m.group(1))
            # Present/subjunctive «گرد» is also the stem of «گشتن» (to search,
            # wander): «دنبال کلید می‌گردد». Only past forms of «گردیدن»
            # are unambiguous, so only those are rewritten.
            if "گردید" not in verb:
                return m.group(0)
            return cls._GARDID_MAP.get(verb, "شد")

        result = cls._GARDID_PATTERN.sub(_replace_gardid, result)

        # 16. دارای X بودن -> X داشتن
        def _replace_daraye(m: re.Match) -> str:
            possessed = m.group(1).strip()
            mapped = cls._DARAYE_MAP.get(m.group(2), "دارد")
            return f"{possessed} {mapped}"

        result = cls._DARAYE_PATTERN.sub(_replace_daraye, result)

        # 17. Orthographic joins.
        result = cls._DAR_HALI_KE_PATTERN.sub("درحالی‌که", result)
        result = cls._AZ_ANJAYI_PATTERN.sub("از آنجا که", result)
        result = cls._BANA_BAR_IN_PATTERN.sub("بنابراین", result)

        # 18. Bare به عنوان -> به‌عنوان (the عمل‌کردن form is gone by now).
        result = cls._BE_ONVAN_PATTERN.sub("به‌عنوان", result)

        # ---- v2 lexical rules 19–30 ----
        # 19. به اجرا درآوردن -> اجرا کردن
        def _replace_be_ejra(m: re.Match) -> str:
            return cls._BE_EJRA_MAP.get(_norm_verb(m.group(1)), "اجرا کردن")

        result = cls._BE_EJRA_PATTERN.sub(_replace_be_ejra, result)

        # 20. به کار گرفتن -> به کار بردن
        def _replace_be_kar(m: re.Match) -> str:
            return cls._BE_KAR_MAP.get(_norm_verb(m.group(1)), "به کار بردن")

        result = cls._BE_KAR_GEREFTAN_PATTERN.sub(_replace_be_kar, result)

        # 21. اعمال + کرد-family -> اجرا + کرد-family
        result = cls._EMAL_PATTERN.sub(r"اجرا \1", result)

        # 22. به عمل آوردن -> انجام دادن
        def _replace_be_amal(m: re.Match) -> str:
            return cls._BE_AMAL_MAP.get(_norm_verb(m.group(1)), "انجام دادن")

        result = cls._BE_AMAL_PATTERN.sub(_replace_be_amal, result)

        # 23. اقدام/مبادرت به X کردن -> X کردن
        result = cls._EGHDAM_PATTERN.sub(r"\1 \2", result)

        # 24. مورد استفاده قرار دادن/گرفتن -> به کار بردن/رفتن
        def _replace_morde(m: re.Match) -> str:
            return cls._MORDE_ESTEFADE_MAP.get(_norm_verb(m.group(1)), "به کار بردن")

        result = cls._MORDE_ESTEFADE_PATTERN.sub(_replace_morde, result)

        # 25. در اختیار X قرار دادن -> در اختیار X گذاشتن
        def _replace_ekhtiyar(m: re.Match) -> str:
            holder = (m.group(1) or "").strip()
            raw = _norm_verb(m.group(2))
            mapped = cls._DAR_EKHTIYAR_MAP.get(raw, "گذاشتن")
            if holder:
                return f"در اختیار {holder} {mapped}"
            return f"در اختیار {mapped}"

        result = cls._DAR_EKHTIYAR_PATTERN.sub(_replace_ekhtiyar, result)

        # 26. تحت X قرار دادن -> X دادن
        result = cls._TAHTE_PATTERN.sub(r"\1 \2", result)

        # 27. در رابطه با / در ارتباط با / در خصوص -> درباره
        result = cls._DAR_RABETE_PATTERN.sub("درباره", result)

        # 28. جهت (= برای) -> برای, guarded against از/بدین/همین/این/آن/چه جهت
        # «جهت» is NOT auto-rewritten: the noun sense (direction) is too
        # common («جهت باد عوض شد»). The linter reports the «برای» sense.

        # 29. عنوان + کرد-family -> مطرح + کرد-family
        result = cls._ONVAN_PATTERN.sub(r"مطرح \1", result)

        # 30. قلمداد/تلقی + کرد-family -> دانستن-family
        def _replace_ghalamdad(m: re.Match) -> str:
            return cls._GHALAMDAD_MAP.get(_norm_verb(m.group(1)), "دانستن")

        result = cls._GHALAMDAD_PATTERN.sub(_replace_ghalamdad, result)

        # ---- v2.1 reverse technical calques 31–34 ----
        # 31. «VERB بر روی OBJ» -> «روی OBJ VERB»
        def _replace_tech_on(m: re.Match) -> str:
            if m.group("tech_verb"):
                return f"روی {m.group('tech_obj').strip()} {m.group('tech_verb')} {_norm_verb(m.group('tech_v'))}"
            if m.group("est_v") is not None:
                return f"روی {m.group('est_obj').strip()} استقرار {_norm_verb(m.group('est_v'))}"
            return f"روی {m.group('bala_obj').strip()} بالا {_norm_verb(m.group('bala_v'))}"

        result = cls._TECH_ON_PATTERN.sub(_replace_tech_on, result)

        # 32. اتصال زدن -> متصل شدن
        def _replace_ettesal(m: re.Match) -> str:
            return cls._ETTESAL_MAP.get(_norm_verb(m.group(1)), "متصل شدن")

        result = cls._ETTESAL_PATTERN.sub(_replace_ettesal, result)

        # 33. استقرار دادن -> مستقر کردن (also fixes rule-31 output «روی OBJ استقرار دادن»)
        def _replace_esteghrar(m: re.Match) -> str:
            return cls._ESTEGHRAR_MAP.get(_norm_verb(m.group(1)), "مستقر کردن")

        result = cls._ESTEGHRAR_PATTERN.sub(_replace_esteghrar, result)

        # 34. ارور + گرفتن-family (either order) -> خطا + گرفتن-family (noun swap only)
        def _replace_error(m: re.Match) -> str:
            if m.group(1):
                return f"خطا {_norm_verb(m.group(2))}"
            return f"{_norm_verb(m.group(3))} خطا"

        result = cls._ERROR_GET_PATTERN.sub(_replace_error, result)

        return result

    @classmethod
    def refine_sentence(cls, text: str) -> str:
        """Alias to eliminate_calques."""
        return cls.eliminate_calques(text)

    @classmethod
    def detect_calques(cls, text: str) -> List[str]:
        """
        Detect calques in the given text and return list of detected occurrences.
        Covers the original 12 rules plus the v2 Najafi/Samii rules.
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
            (cls._PASSIVE_BY_GENERIC_PATTERN, "مجهول با عامل (توسط/به‌وسیله/از سوی)"),
            (cls._MIBASHAD_PATTERN, "می‌باشد"),
            (cls._GARDID_PATTERN, "گردید"),
            (cls._DARAYE_PATTERN, "دارای بودن"),
            (cls._BE_EJRA_PATTERN, "به اجرا درآوردن"),
            (cls._BE_KAR_GEREFTAN_PATTERN, "به کار گرفتن"),
            (cls._EMAL_PATTERN, "اعمال کردن"),
            (cls._BE_AMAL_PATTERN, "به عمل آوردن"),
            (cls._EGHDAM_PATTERN, "اقدام/مبادرت به"),
            (cls._MORDE_ESTEFADE_PATTERN, "مورد استفاده قرار دادن"),
            (cls._DAR_EKHTIYAR_PATTERN, "در اختیار قرار دادن"),
            (cls._TAHTE_PATTERN, "تحت پوشش قرار دادن"),
            (cls._DAR_RABETE_PATTERN, "در رابطه با"),
            (cls._ONVAN_PATTERN, "عنوان کردن"),
            (cls._GHALAMDAD_PATTERN, "قلمداد/تلقی کردن"),
            (cls._TECH_ON_PATTERN, "فعل فنی + بر روی (reverse technical calque)"),
            (cls._ETTESAL_PATTERN, "اتصال زدن"),
            (cls._ESTEGHRAR_PATTERN, "استقرار دادن"),
            (cls._ERROR_GET_PATTERN, "گرفتن ارور"),
        ]

        for pat, _label in patterns:
            for match in pat.finditer(text):
                detected.append(match.group(0).strip())

        return detected


# -----------------------------------------------------------------------------
# Shared lint pattern table (label, regex-string) for both linter front-ends.
# -----------------------------------------------------------------------------
LINT_CALQUE_PATTERNS: List[Tuple[str, str]] = [
    ("توسط (passive-by calque)", r"\bتوسط\b"),
    # Found by translating real texts (docs/research/real-texts/).
    ("با علم به اینکه (knowing that calque)", r"با\s+علم\s+به\s+(?:این|آن)\s*‌?که"),
    ("نیاز داشتن که (need to calque; use «باید»)", r"نیاز\s+(?:دار\w*|داشت\w*|خواه\w*\s+داشت)\s+که"),
    ("برای حدود (for about calque)", r"برای\s+حدود\b"),
    (
        "تجاوز از دوز (do not exceed calque; use «بیشتر از … نخورید»)",
        r"از\s+[^.،\n]{0,30}(?:دوز|مقدار|قرص|کپسول)[^.،\n]{0,20}تجاوز\s+نکن\w*",
    ),
    (
        "تجربه کردن علائم (experience symptoms calque)",
        r"(?:علائم|علایم|نشانه‌های|عوارض)[^.\n]{0,40}تجربه\s+(?:کرد\w*|کنید|می‌کن\w*)",
    ),
    ("مخفف چت انگلیسی در متن فارسی (lol/lmao/idk)", r"(?<![A-Za-z])(?:lol|lmao|lmfao|idk|omg)(?![A-Za-z])"),
    ("به‌وسیله/از سوی (passive-by calque)", r"\bبه\s*وسیله[‌ی]?\b|\bاز\s+سوی\b"),
    (
        "نقش بازی کردن (play a role calque)",
        r"نقش(?:ی)?(?:\s+[^\n،.]*)?\s+بازی\s+(?:کردن|کرد|کرده|کرده‌اند|کردند|می‌کند|می‌کرد|کنند|کند)",
    ),
    (
        "روی ... حساب کردن (count on calque)",
        r"روی\s+[^\n،.]+?\s+حساب\s+(?:کردن|کرد|کرده|کردند|می‌کنم|می‌کنی|می‌کند|کنید|کنیم|کن|نکن)",
    ),
    (
        "به عنوان ... عمل کردن (act as calque)",
        r"به\s*عنوانِ?\s+[^\n،.]+?\s+عمل\s+(?:کردن|کرد|می‌کند|کردند)",
    ),
    ("در پایان روز (at the end of the day calque)", r"در پایان روز(?!\s*(?:کاری|اول|دوم|سوم|بعد|قبل|جمعه|شنبه))"),
    ("حس ایجاد کردن (makes sense calque)", r"حس ایجاد\s+(?:می‌کند|می‌کرد|کرد|کردن)"),
    (
        "یک تصمیم گرفتن (make a decision calque)",
        r"یک\s+تصمیم\s+(?:گرفتن|گرفت|گرفتند|گرفته|می‌گیرد|می‌گیرند)",
    ),
    ("آتش گشودن (open fire calque)", r"آتش\s+(?:گشودن|گشود|گشودند|گشوده)"),
    ("حمام گرفتن (take a bath calque)", r"حمام\s+(?:گرفتن|گرفت|گرفتند|می‌گیرد)"),
    ("نقطه نظر (point of view calque)", r"نقطه[‌\s\-]?(?:نظر|نظرات|نظرها)"),
    (
        "چراغ سبز نشان دادن (give green light calque)",
        r"چراغ\s+سبز\s+(?:[^.،\n]{0,30}?\s+)?نشان\s+(?:دادن|داد|دادند|می‌دهد)",
    ),
    (
        "به پایان خط رسیدن (reach end of the line calque)",
        r"به پایان خط\s+(?:رسیدن|رسید|رسیدند|می‌رسد)",
    ),
    ("به اجرا درآوردن (execute calque)", r"به\s+اجرا\s+درآورد\w*|به\s+اجرا\s+در(?:آورد|آورده|می‌آورد)\w*"),
    (
        "به کار گرفتن (utilize calque)",
        r"به\s+کار\s+(?:گرفتن|گرفت\w*|می‌گیرد|می‌گیرند|بگیرد|بگیرند)",
    ),
    ("اعمال کردن (apply calque)", r"اعمال\s+(?:کردن|کرد\w*|می‌کند|می‌کنند)"),
    ("به عمل آوردن (perform calque)", r"به\s+عمل\s+آورد\w*|به\s+عمل\s+(?:آورد|آورده|می‌آورد)\w*"),
    ("اقدام/مبادرت به (proceed calque)", r"(?:اقدام|مبادرت)\s+به\b"),
    (
        "مورد استفاده قرار دادن/گرفتن (use calque)",
        r"مورد\s+استفاده\s+قرار\s+(?:داد\w*|ده\w*|گرفت\w*|گیر\w*)",
    ),
    (
        "تحت ... قرار دادن (under-coverage calque)",
        r"تحت\s+(?:پوشش|حمایت|درمان|نظارت|فشار|تعقیب|پیگرد)\s+قرار\s+داد\w*",
    ),
    ("در اختیار قرار دادن (provide calque)", r"در\s+اختیار\s+قرار\s+داد\w*"),
    ("دارای بودن (possess calque)", r"\bدارای\b"),
    ("می‌باشد (copula calque)", r"\bن?می‌باش(?:م|ی|یم|ید|ند)?\b"),
    (
        "گردید (archaic passive calque)",
        # Present «می‌گردد/بگردد» is left out: it is also «گشتن» (to search).
        r"\bگردید(?:ند)?\b|\bگردیده(?: است|‌اند)?\b|\bگردیدن\b",
    ),
    (
        "در رابطه با/در ارتباط با/در خصوص (regarding calque)",
        r"در\s+(?:رابطه|ارتباط)\s+با|در\s+خصوص",
    ),
    (
        "جهت به‌معنای برای (purpose calque)",
        # Only the «برای» sense before typical purpose nouns; «جهت باد» is a noun.
        r"\bجهت\s+(?:اطلاع|استفاده|دریافت|ثبت|انجام|بررسی|تهیه|ارسال|رفاه|حفظ|کسب|ورود|خرید|پرداخت)\b",
    ),
    ("در حالی که جدا نوشته شده (orthography)", r"\bدر\s+حالی\s+که\b"),
    ("از آنجایی که (orthography)", r"از\s+آنجایی\s+که"),
    ("بنا بر این جدا نوشته شده (orthography)", r"\bبنا\s+بر\s+این\b"),
    ("عنوان کردن (mention calque)", r"\bعنوان\s+(?:کرد\w*|می‌کن\w*|کن\w*)\b"),
    ("قلمداد/تلقی کردن (consider calque)", r"(?:قلمداد|تلقی)\s+(?:کرد\w*|می‌کن\w*)\b"),
    ("وی به‌جای او (pronoun calque)", r"\bوی\b"),
    (
        "فعل فنی + بر روی (reverse technical calque)",
        r"(?:اجرا|کلیک|فراخوانی|پیاده‌سازی)\s+(?:کرد\w*|می‌کن\w*|کن\w*)\s+بر\s+روی",
    ),
    (
        "استقرار دادن بر روی (reverse technical calque)",
        r"استقرار\s+(?:داد\w*|ده\w*)\s+بر\s+روی",
    ),
    (
        "بالا آوردن بر روی (reverse technical calque)",
        r"بالا\s+آورد\w*\s+بر\s+روی",
    ),
    ("اتصال زدن به (reverse technical calque)", r"اتصال\s+(?:زد\w*|زن\w*|بزن\w*)"),
    ("استقرار دادن (reverse technical calque)", r"استقرار\s+(?:داد\w*|ده\w*)\b"),
    (
        "گرفتن ارور (reverse technical calque)",
        r"ارور\s+(?:گرفت\w*|گیر\w*)|(?:گرفتن|گرفت\w*|گیر\w*)\s+ارور",
    ),
]

#: Standalone double-hyphen (em-dash category): matched only when the token is
#: separated by whitespace so CLI flags like ``--output`` are never flagged.
LINT_DOUBLE_HYPHEN_RE = r"(?<!\S)--(?!\S)"

#: Straight / curly quotation marks that must become «».
LINT_STRAIGHT_QUOTE_RES = (
    r'"[^"\n]+"',
    r"(?<!\w)'[^'\n]+?'(?!\w)",
    r"[“”][^“”\n]+[“”]",
    r"(?<!\w)[‘’][^‘’\n]+[‘’](?!\w)",
)

#: Missing-ZWNJ detectors (verbal می/نمی written with a space).
LINT_ZWNJ_RES = (
    r"\bمی\s+[آ-ی]",
    r"\bنمی\s+[آ-ی]",
)

#: Non-standard Arabic characters (unmasked ي ك) plus rarely-correct forms.
LINT_ARABIC_CHARS = ("ي", "ك", "ى", "ة", "ـ")
