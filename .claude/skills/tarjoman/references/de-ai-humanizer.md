# De-AI Humanizer Reference (v2.3.0)

> Persian AI footprint eradication: 18 AI-Tells methodology, Tanvin auto-repair,
> fake Tanvin correction, and Code & Markdown Table Shielding.

## Overview

> **Safe vs. suggest-only.** `PersianHumanizer.humanize()` applies only rewrites that are safe regardless of context. Rules whose right answer depends on meaning are reported by `tarjoman lint` as `ai-tell` (via `PersianHumanizer.detect()`) and left to the translator's judgment.

The `PersianHumanizer` class (`tarjoman.stages.humanizer`) applies automated
de-AI transformations to Persian text produced by language models, making it
read as natural, human-written Persian while preserving all technical content
(code blocks, inline code, markdown tables) byte-for-byte.

## Code & Markdown Table Shielding

Before any transformation, the humanizer shields:
- **Fenced code blocks** (``` or ~~~)
- **Inline code** (\`...\`)
- **Markdown table rows** (`^[ \t]*\|.*$`)

Uses collision-safe private-use codepoints (U+E000, U+E001) and letter-only
index tokens that survive digit conversion and typography normalization.

After all transformations, shielded regions are restored byte-identical.

## 18 AI-Tell Patterns (T1–T18)

### T1: Copula inflation (تورم افعال ربطی)

| Before (AI) | After (Human) |
|---|---|
| می‌باشد | است |
| به شمار می‌رود | است |
| محسوب می‌شود | است |
| به حساب می‌آید | است |
| گردیده است | شده است |
| می‌گردد | (not auto-rewritten: also «گشتن», «دنبال کلید می‌گردد») |

### T2: Ceremonial filler announcements (اطلاعیه‌های متکلفانه)

Removed entirely:
- لازم به ذکر است که
- شایان ذکر است که
- باید خاطرنشان کرد که
- قابل توجه است که
- همان‌طور که می‌دانید

### T3: Significance inflation (اغراق در اهمیت)

| Before | After |
|---|---|
| از اهمیت ویژه‌ای برخوردار است | مهم است |
| نقش بسزایی ایفا می‌کند | نقش مهمی دارد |
| جایگاه ویژه‌ای دارد | مهم است |

### T4: Generic openers/closers (مقدمه‌ها و مؤخره‌های کلیشه‌ای)

Removed: در دنیای امروز، در عصر دیجیتال، امروزه با پیشرفت تکنولوژی،
با گسترش روزافزون اینترنت، در نهایت می‌توان گفت.
«به طور کلی» is kept: it usually carries meaning.

### T5: «در راستای» abuse

| Before | After |
|---|---|
| در راستای | برای |
| در همین راستا | (removed) |
| در جهت نیل به | برای |

### T6: Promotional emptiness (مبالغه‌های توخالی)

Suggest-only (lint category `ai-tell`): بی‌نظیر، فوق‌العاده، مثال‌زدنی، منحصربه‌فرد.
Never deleted automatically: «غذای فوق‌العاده‌ای» became «غذای‌ای», and «فوق‌العاده سرد» is a legitimate intensifier. Keep the adjective if the source really says it; otherwise cut it or make it concrete.

### T7: Rule of three (تثلیث‌های ماشینی)

Detection only — needs semantic context to rewrite safely.

### T8: Negative parallelism (نه تنها ... بلکه)

Detection only — semantic rewrite needed.

### T9: Tacked-on analysis clauses

Suggest-only (lint category `ai-tell`): که نشان‌دهنده‌ی ... است، که بیانگر ...، که حاکی از ....
Never deleted automatically, because the clause often holds a fact («که نشان‌دهنده‌ی تورم شدید است»). Rewrite it as a plain statement instead.

### T10: Vague authority (ارجاعات مجهول)

Detection only — needs named source to fix.

### T11: False ranges (دامنه‌های ساختگی)

Detection only — semantic.

### T12: Em dashes & English punctuation

ZERO em-dash guarantee: all `—` and `–` converted to `، ` (Persian comma + space).

### T13: Calque phrases (گرته‌برداری‌ها)

| Before | After |
|---|---|
| در پایان روز | در نهایت (suggest-only: often literal, «در پایان روز به خانه برگشتیم») |
| نگاهی بیندازیم به | ببینیم |
| حس ایجاد کردن | معنادار بودن |

### T14: همچنین pileup

Consecutive «همچنین»/«علاوه بر این» at sentence starts reduced.

### T15: Fake tanvin on Persian words

| Wrong | Correct |
|---|---|
| گاهاً | گاهی |
| دوماً | دوم اینکه |
| ناچاراً | به‌ناچار |

### T16: Bold-header bullet lists

Detection only — structural.

### T17: Sycophantic chat residue

Removed: سؤال بسیار خوبی است!، البته!، خوشحال می‌شوم کمک کنم،
امیدوارم مفید بوده باشد.

### T18: Universal tells

Detection only — needs editorial judgment (elegant variation, passive hiding
actor, excessive hedging, aphorism formulas).

## Tanvin Auto-Repair

Arabic loanwords that require tanvin are auto-repaired:

لطفا → لطفاً، حتما → حتماً، دقیقا → دقیقاً، واقعا → واقعاً،
کاملا → کاملاً، تقریبا → تقریباً، قطعا → قطعاً، اصلا → اصلاً،
معمولا → معمولاً، احتمالا → احتمالاً، اولا → اولاً، عملا → عملاً،
مثلا → مثلاً، ضمنا → ضمناً.

## Register Guidelines

- **formal-human** (default): All 18 rules applied. Suitable for proposals,
  reports, website copy, documentation.
- **colloquial**: Future extension — would skip T1 (colloquial copula forms
  are valid) and relax T4 (openers allowed in social).

## Linter Integration

The `tarjoman lint` command and both linter modules now detect:

- **hekasre**: Ezafe kasre confused with the colloquial clitic «ـه».
  `find_hekasre()` returns tier A (high confidence) and tier B (medium) results.
- **tanvin**: Missing tanvin on Arabic loans (`لطفا`) and fake tanvin on
  Persian words (`گاهاً`).

## API

```python
from tarjoman.stages.humanizer import PersianHumanizer

# Full pipeline (shield → de-AI → tanvin → restore)
result = PersianHumanizer.humanize(text, register="formal-human")

# Individual components
from tarjoman.stages.humanizer import protect_regions, restore_regions
masked, tokens = protect_regions(text)
# ... process masked text ...
restored = restore_regions(processed, tokens)
```
