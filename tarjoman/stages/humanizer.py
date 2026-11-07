"""
Persian De-AI Humanizer for Tarjoman v2.3.0.

Implements the 18 AI-Tells methodology (T1-T18), Code & Markdown Table Shielding,
Tanvin auto-repair for Arabic loanwords, and fake Tanvin correction on Persian words.

Derived from the persian-writing skill's ``persian_cleanup.py`` (protect/restore
regions, tanvin repairs) and ``fa_lint.py`` (hekasre detection, tanvin lists) —
adapted for Tarjoman's translation pipeline.
"""
from __future__ import annotations

import re
from typing import List, Sequence, Tuple

# ---------------------------------------------------------------------------
# Code & Markdown Table Shielding
# ---------------------------------------------------------------------------
# Typographic rules are correct for prose and destructive inside code blocks,
# inline code, and markdown table rows. Shield them before processing,
# restore byte-identical afterwards.

_PROTECT_OPEN = ""
_PROTECT_CLOSE = ""

_FENCED_CODE = re.compile(
    r"^[ \t]*(`{3,}|~{3,})[^\n]*\n(?:.*?\n)??[ \t]*\1[^\n]*$",
    re.MULTILINE | re.DOTALL,
)
_TABLE_ROW = re.compile(r"^[ \t]*\|.*$", re.MULTILINE)
_INLINE_CODE = re.compile(r"`[^`\n]+`")


def _encode_index(i: int) -> str:
    """Index -> letters only (no digits, which convert_digits would rewrite)."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(ord("A") + r) + s
    return s


def protect_regions(text: str) -> Tuple[str, List[str]]:
    """Replace code fences, table rows, and inline code with placeholders.

    Returns (masked_text, tokens). Restore with :func:`restore_regions`.
    """
    tokens: List[str] = []

    def _stash(m: re.Match) -> str:
        tokens.append(m.group(0))
        return f"{_PROTECT_OPEN}{_encode_index(len(tokens) - 1)}{_PROTECT_CLOSE}"

    for pattern in (_FENCED_CODE, _TABLE_ROW, _INLINE_CODE):
        text = pattern.sub(_stash, text)
    return text, tokens


def restore_regions(text: str, tokens: Sequence[str]) -> str:
    """Put the protected regions back exactly as they were."""
    for i, original in enumerate(tokens):
        text = text.replace(
            f"{_PROTECT_OPEN}{_encode_index(i)}{_PROTECT_CLOSE}", original
        )
    return text


# ---------------------------------------------------------------------------
# Tanvin: Arabic loanwords that REQUIRE tanvin (safe auto-repair)
# ---------------------------------------------------------------------------
TANVIN_NEEDED = {
    "لطفا": "لطفاً",
    "حتما": "حتماً",
    "دقیقا": "دقیقاً",
    "واقعا": "واقعاً",
    "کاملا": "کاملاً",
    "تقریبا": "تقریباً",
    "قطعا": "قطعاً",
    "اصلا": "اصلاً",
    "معمولا": "معمولاً",
    "احتمالا": "احتمالاً",
    "اولا": "اولاً",
    "عملا": "عملاً",
    "مثلا": "مثلاً",
    "ضمنا": "ضمناً",
    "فعلا": "فعلاً",
    "اتفاقا": "اتفاقاً",
    "مخصوصا": "مخصوصاً",
    "اساسا": "اساساً",
}

# Fake tanvin: Persian words that wrongly carry tanvin
FAKE_TANVIN = {
    "گاهاً": "گاهی",
    "گاها": "گاهی",
    "دوماً": "دوم اینکه",
    "سوماً": "سوم اینکه",
    "ناچاراً": "به‌ناچار",
    "زباناً": "به زبان",
    "تلفناً": "تلفنی",
    "خواهشاً": "خواهش می‌کنم",
}

# Persian-aware word boundaries for tanvin matching
_FA_B_L = r"(?<![؀-ۿ‌])"
_FA_B_R = r"(?![؀-ۿًٌٍَُِّ‌])"

# ---------------------------------------------------------------------------
# T1-T18: AI-Tell de-AI regex patterns
# ---------------------------------------------------------------------------

# T1: Copula inflation (می‌باشد disease)
_T1_PATTERNS = [
    (re.compile(r"\bمی‌باشد\b"), "است"),
    (re.compile(r"\bمی‌باشند\b"), "هستند"),
    (re.compile(r"\bنمی‌باشد\b"), "نیست"),
    (re.compile(r"\bنمی‌باشند\b"), "نیستند"),
    (re.compile(r"\bبه شمار می‌رود\b"), "است"),
    (re.compile(r"\bبه شمار می‌روند\b"), "هستند"),
    (re.compile(r"\bمحسوب می‌شود\b"), "است"),
    (re.compile(r"\bمحسوب می‌شوند\b"), "هستند"),
    (re.compile(r"\bبه حساب می‌آید\b"), "است"),
    (re.compile(r"\bبه حساب می‌آیند\b"), "هستند"),
    (re.compile(r"\bگردیده است\b"), "شده است"),
    (re.compile(r"\bگردیده‌اند\b"), "شده‌اند"),
    # «می‌گردد/می‌گردند» are NOT rewritten: they are also the present tense
    # of «گشتن» (to search): «دنبال کلید می‌گردد».
    (re.compile(r"\bگردید\b"), "شد"),
    (re.compile(r"\bگردیدند\b"), "شدند"),
]

# T2: Ceremonial filler announcements — remove entirely
_T2_PATTERNS = [
    re.compile(r"لازم به ذکر است که\s*"),
    re.compile(r"شایان ذکر است که\s*"),
    re.compile(r"باید خاطرنشان کرد که\s*"),
    re.compile(r"قابل توجه است که\s*"),
    re.compile(r"همان‌طور که می‌دانید[،,]?\s*"),
    re.compile(r"لازم به توضیح است که\s*"),
]

# T3: Significance inflation
_T3_PATTERNS = [
    (re.compile(r"از اهمیت ویژه‌ای برخوردار است"), "مهم است"),
    (re.compile(r"از اهمیت ویژه‌ای برخوردارند"), "مهم هستند"),
    (re.compile(r"نقش بسزایی ایفا می‌کند"), "نقش مهمی دارد"),
    (re.compile(r"نقش بسزایی ایفا می‌کنند"), "نقش مهمی دارند"),
    (re.compile(r"جایگاه ویژه‌ای دارد"), "مهم است"),
    (re.compile(r"گامی مهم در راستای"), "قدمی برای"),
    (re.compile(r"تحولی شگرف"), "تحولی"),
]

# T4: Generic openers/closers — remove
_T4_PATTERNS = [
    re.compile(r"در دنیای امروز[،,]?\s*"),
    re.compile(r"در عصر دیجیتال[،,]?\s*"),
    re.compile(r"امروزه با پیشرفت تکنولوژی[،,]?\s*"),
    re.compile(r"با گسترش روزافزون اینترنت[،,]?\s*"),
    re.compile(r"در نهایت می‌توان گفت\s*"),
    # «به طور کلی» is NOT removed: it often carries meaning (in general).
    re.compile(r"آینده‌ای روشن در انتظار[^\n،.]*"),
]

# T5: «در راستای» abuse
_T5_PATTERNS = [
    (re.compile(r"در راستای\b"), "برای"),
    (re.compile(r"در همین راستا[،,]?\s*"), ""),
    (re.compile(r"در جهت نیل به\b"), "برای"),
]

# T6: Promotional emptiness. Detection only (see LINT_AI_TELL_PATTERNS):
# deleting the adjective broke words («غذای فوق‌العاده‌ای» → «غذای‌ای») and
# «فوق‌العاده سرد» is a legitimate intensifier.

# T9: Tacked-on analysis clauses. Detection only: deleting the clause
# deleted content («... که نشان‌دهنده‌ی تورم شدید است»).

# T12: Em dashes & English punctuation rhythm — ZERO em-dash guarantee
_T12_EM_DASH = re.compile(r"\s*[—–]\s*")

# T13: Calque phrases
_T13_PATTERNS = [
    # «در پایان روز» is NOT rewritten: it is often literal (end of the day).
    (re.compile(r"نگاهی بیندازیم به"), "ببینیم"),
    (re.compile(r"حس ایجاد کردن"), "معنادار بودن"),
]

# T17: Sycophantic chat residue
_T17_PATTERNS = [
    re.compile(r"سؤال بسیار خوبی است!\s*"),
    re.compile(r"سوال بسیار خوبی است!\s*"),
    re.compile(r"البته!\s*"),
    re.compile(r"خوشحال می‌شوم کمک کنم[.!]?\s*"),
    re.compile(r"امیدوارم مفید بوده باشد[.!]?\s*"),
    re.compile(r"خوشحالم که می‌توانم کمک کنم[.!]?\s*"),
]


# ---------------------------------------------------------------------------
# Suggest-only AI tells. These are never rewritten automatically, because the
# right fix depends on meaning. The linter reports them and the agent (or a
# human editor) decides. Each entry: (label, regex, advice).
# ---------------------------------------------------------------------------
LINT_AI_TELL_PATTERNS: List[Tuple[str, str, str]] = [
    (
        "T6 promotional adjective",
        # «فوق‌العاده» is left out: it is an everyday intensifier.
        r"بی‌نظیر|مثال‌زدنی|منحصربه‌فرد|بی‌رقیب",
        "Keep only if the source really says it; otherwise cut or make concrete.",
    ),
    (
        "T9 tacked-on analysis clause",
        r"که\s+(?:نشان‌دهنده‌ی|نشان‌دهنده|بیانگر|حاکی از|گواهی است بر)",
        "Say the conclusion plainly or as its own sentence; don't delete facts.",
    ),
    (
        "T3 significance inflation",
        r"از (?:اهمیت|جایگاه) (?:ویژه‌ای|بالایی|زیادی|خاصی|فراوانی) برخوردار",
        "Usually «مهم است»، or show why it matters.",
    ),
    (
        "T2 throat-clearing",
        r"باید توجه داشت که|لازم است اشاره شود|ذکر این نکته ضروری است",
        "Delete the announcement and state the point.",
    ),
    (
        "T4 essay opener/closer",
        r"به بررسی\s+[^.،\n]{1,40}?\s+(?:می‌پردازیم|خواهیم پرداخت|پرداخته شده)|در نتیجه[،,]?\s*می‌توان گفت",
        "Start with the content itself: «در این مقاله ... را بررسی می‌کنیم» or drop it.",
    ),
    # «در پایان روز» is reported once, by the calque table (anti_calque.py).
    (
        "T13 calque: help you to",
        r"کمک می‌کند تا",
        "Usually «کمک می‌کند که» or rephrase: «با این ابزار ... می‌شود».",
    ),
    (
        "T13 calque: دست پیدا کردن",
        r"دست\s+پیدا\s+(?:کرد|کن|می‌کن)",
        "Prefer «رسیدن به» / «به دست آوردن».",
    ),
    (
        "T4 cliché opener",
        r"در دنیای (?:پرشتاب |پرسرعت )?امروز|در عصر حاضر|در دنیای مدرن",
        "Cut it and start with the real point.",
    ),
    (
        "T3 role inflation",
        r"نقش (?:کلیدی|حیاتی|بسزایی|محوری|اساسی)[^.،\n]{0,40}? ایفا",
        "Say what it actually does: «X باعث Y می‌شود».",
    ),
    (
        "T3 one-of-the-most",
        r"یکی از (?:مهم‌ترین|بهترین|بزرگ‌ترین|کلیدی‌ترین) [^.،\n]{1,30}? (?:است|به شمار می‌رود)",
        "Often filler; state the specific claim or drop the ranking.",
    ),
    (
        "T13 calque: lead to",
        r"منجر به [^.،\n]{1,30}? (?:می‌شود|شد|شده|خواهد شد|می‌گردد)",
        "Usually «باعث ... می‌شود» or a direct verb: «هزینه‌ها کم شد».",
    ),
    (
        "T13 calque: significantly",
        r"به (?:طور|طرز|شکل) (?:قابل توجهی|چشمگیری)",
        "Prefer «خیلی/بسیار» or the actual number.",
    ),
    (
        "T13 calque: provide/enable",
        r"(?:امکان|زمینه)[^.،\n]{0,30}? را (?:[^.،\n]{0,15} )?فراهم (?:می‌کند|می‌آورد|کرده|ساخته)",
        "Usually «با X می‌شود ...» or «X به شما اجازه می‌دهد» → «با X می‌توانید ...».",
    ),
    (
        "T13 calque: ensure",
        r"اطمینان حاصل (?:کنید|نمایید|کن|شود)",
        "«مطمئن شوید» / «حواستان باشد».",
    ),
    (
        "T13 calque: keep in mind",
        r"در نظر داشته باشید که",
        "Usually cut, or «یادتان باشد».",
    ),
    (
        "T13 calque: as a",
        r"به(?:‌| )عنوان یک ",
        "Drop «یک»: «به‌عنوان مدیر», or rephrase: «من که مدیرم ...».",
    ),
    (
        "T13 calque: let's",
        r"بیایید (?:نگاهی|با هم|به|شروع)",
        "«حالا ... را ببینیم» / «شروع کنیم».",
    ),
    (
        "T13 calque: deep dive",
        r"نگاهی عمیق(?:‌تر)?|غوطه‌ور (?:شویم|می‌شویم)|شیرجه (?:بزنیم|می‌زنیم)",
        "«دقیق‌تر بررسی کنیم».",
    ),
    (
        "T18 journey/world metaphor",
        r"سفر (?:یادگیری|موفقیت|توسعه|برنامه‌نویسی)|سفر (?:شما|خود) به سوی|دنیای (?:شگفت‌انگیز|جذاب|هیجان‌انگیز)",
        "Drop the metaphor and say it plainly.",
    ),
    (
        "T18 unlock potential",
        r"پتانسیل (?:کامل|واقعی)|کلید (?:موفقیت|طلایی)",
        "Marketing cliché; say the concrete benefit.",
    ),
    (
        "T18 whether-you-are",
        r"چه (?:یک )?[^.،\n]{1,25}? باشید(?: و)? چه",
        "Often an English template; usually cut or «برای ... و ... فرقی نمی‌کند».",
    ),
    (
        "T8 negative parallelism",
        r"نه تنها [^.\n]{1,60}? بلکه|این (?:فقط|تنها) [^.\n]{1,40}? نیست[،,]? بلکه",
        "One «نه تنها ... بلکه» per text at most; often plain «و» is enough.",
    ),
    (
        "T17 chatbot closer",
        r"امیدوارم (?:این [^.\n]{1,20}? )?(?:مفید|کمک‌کننده) (?:باشد|بوده باشد)|اگر سؤال(?:ی)? (?:دیگری )?داشتید[^.\n]{0,20}?(?:بپرسید|در خدمتم)",
        "Delete unless the source really ends this way.",
    ),
    (
        "T14 connective pileup",
        r"(?:^|[.؟!]\s+)(?:علاوه بر این|همچنین|به علاوه|از سوی دیگر)،",
        "Vary or drop sentence-initial connectives; Persian chains with «و» or nothing.",
    ),
    (
        "T13 calque: chat idioms",
        r"هیچ نگرانی(?:‌ای)? (?:نیست|وجود ندارد)|احساس راحتی کنید|(?:به|پیش) (?:شما|تو) برمی‌گرد(?:م|یم)|نتوانست کمکی کند|یک نفس عمیق (?:گرفت|کشید)|راهش را [^.،\n]{0,20}?(?:ساخت|پیدا کرد)",
        "Literal English idiom: «اشکالی نداره»، «راحت بپرسید»، «خبرتان می‌کنم»، «نتوانست جلوی ... را بگیرد»، «نفس عمیقی کشید»، «رفت».",
    ),
    (
        "T4 summary closer",
        r"(?:^|[.؟!]\s+)(?:به طور خلاصه|به‌طور خلاصه|در جمع‌بندی|در مجموع)[،,]",
        "Usually cut: the reader just read it.",
    ),
]


class PersianHumanizer:
    """De-AI and humanize Persian text.

    Implements the 18 AI-Tells methodology with Code & Markdown Table
    Shielding and Tanvin auto-repair/fake-tanvin correction.
    """

    @classmethod
    def humanize(cls, text: str, register: str = "formal-human") -> str:
        """Apply full de-AI humanization pipeline.

        1. Shield code fences, inline code, and markdown table rows.
        2. Apply T1-T18 de-AI transformations.
        3. Auto-repair tanvin for Arabic loanwords.
        4. Correct fake tanvin on Persian words.
        5. Restore shielded regions byte-for-byte.

        Args:
            text: Input Persian text (may contain markdown/code).
            register: Target register. Currently ``"formal-human"``
                      (default) applies all rules.

        Returns:
            Humanized text with code/tables intact.
        """
        if not text:
            return text

        # Step 1: Shield code & tables
        masked, tokens = protect_regions(text)

        # Step 2: De-AI transformations (T1-T18)
        masked = cls._apply_de_ai(masked)

        # Step 3: Tanvin auto-repair (Arabic loanwords)
        masked = cls._repair_tanvin(masked)

        # Step 4: Fake tanvin correction (Persian words)
        masked = cls._fix_fake_tanvin(masked)

        # Step 5: Restore shielded regions
        return restore_regions(masked, tokens)

    @classmethod
    def _apply_de_ai(cls, text: str) -> str:
        """Apply T1-T18 AI-tell transformations."""
        # T1: Copula inflation
        for pat, replacement in _T1_PATTERNS:
            text = pat.sub(replacement, text)

        # T2: Ceremonial filler announcements
        for pat in _T2_PATTERNS:
            text = pat.sub("", text)

        # T3: Significance inflation
        for pat, replacement in _T3_PATTERNS:
            text = pat.sub(replacement, text)

        # T4: Generic openers/closers
        for pat in _T4_PATTERNS:
            text = pat.sub("", text)

        # T5: «در راستای» abuse
        for pat, replacement in _T5_PATTERNS:
            text = pat.sub(replacement, text)

        # T6: Promotional emptiness — detection only (see detect()).

        # T7: Rule of three — detection only (needs semantic context);
        # we flag but don't auto-rewrite triads as that risks losing meaning.

        # T8: Negative parallelism — detection only (semantic rewrite needed).

        # T9: Tacked-on analysis clauses — detection only (see detect()).

        # T10: Vague authority — detection only (needs source citation).

        # T11: False ranges — detection only (semantic).

        # T12: Em dashes — ZERO em-dash guarantee
        text = _T12_EM_DASH.sub("، ", text)

        # T13: Calque phrases
        for pat, replacement in _T13_PATTERNS:
            text = pat.sub(replacement, text)

        # T14: همچنین pileup — reduce consecutive «همچنین»/«علاوه بر این»
        # at sentence start to connective «و» or nothing.
        text = re.sub(
            r"(?<=\.\s)همچنین[،,]?\s*(?=همچنین|علاوه بر این)", "", text
        )

        # T15: Fake tanvin on Persian words (handled in _fix_fake_tanvin)

        # T16: Bold-header bullet lists — detection only (structural).

        # T17: Sycophantic chat residue
        for pat in _T17_PATTERNS:
            text = pat.sub("", text)

        # T18: Universal tells — detection only (needs editorial judgment).

        # Clean up double spaces left by removals
        text = re.sub(r"  +", " ", text)
        # Clean up leading space after newline
        text = re.sub(r"\n ", "\n", text)

        return text

    @classmethod
    def detect(cls, text: str) -> List[Tuple[str, str, str]]:
        """Return suggest-only AI tells as [(label, matched_text, advice)].

        Code fences, inline code and table rows are ignored.
        """
        if not text:
            return []
        masked, _ = protect_regions(text)
        found: List[Tuple[str, str, str]] = []
        for label, pattern, advice in LINT_AI_TELL_PATTERNS:
            for m in re.finditer(pattern, masked):
                found.append((label, m.group(0), advice))
        return found

    @classmethod
    def _repair_tanvin(cls, text: str) -> str:
        """Auto-repair missing tanvin on standard Arabic loanwords."""
        for bare, correct in TANVIN_NEEDED.items():
            text = re.sub(_FA_B_L + re.escape(bare) + _FA_B_R, correct, text)
        return text

    @classmethod
    def _fix_fake_tanvin(cls, text: str) -> str:
        """Replace fake tanvin on Persian words with correct forms."""
        for fake, fix in FAKE_TANVIN.items():
            text = re.sub(_FA_B_L + re.escape(fake) + _FA_B_R, fix, text)
        return text
