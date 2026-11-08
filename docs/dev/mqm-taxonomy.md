# Multidimensional Quality Metrics (MQM) Reference Guide (راهنمای ارزیابی کیفی MQM در ترجمان)

## Overview
The **Multidimensional Quality Metrics (MQM)** framework is the international translation industry standard (codified in ISO 5060 and ASTM F2575) for analytical translation quality assessment. Tarjoman implements an automated, objective MQM engine to grade and audit translations.

---

## 1. Core Dimensions & Error Typology

Tarjoman evaluates translations across four primary error dimensions:

### 1. Accuracy (صحت و امانت‌داری)
Measures how faithfully the target text reflects the meaning of the source text.
- **Omission (حذف)**: Meaningful words, clauses, or numbers present in source are missing in target.
  - *Code*: `MQM-NUM-OMISSION`, `MQM-ACC-OMISSION`
- **Addition (افزودن ناموجه)**: Information or unwarranted claims added without source justification.
  - *Code*: `MQM-ACC-ADDITION`
- **Mistranslation (ترجمه نادرست)**: Incorrect lexical choice leading to distorted meaning.
  - *Code*: `MQM-ACC-MISTRANSLATION`
- **Untranslated Content (ترجمه‌نشده)**: English segments inadvertently left untranslated.
  - *Code*: `MQM-ACC-UNTRANSLATED`

### 2. Fluency & Typography (روانی، سجاوندی و سلامت زبان)
Measures whether the target text reads as natural, grammatically correct Persian.
- **Banned Calque (گرته‌برداری ممنوع)**: Use of passive-by `توسط`, structural calques, or banned idiomatic borrowings.
  - *Code*: `MQM-CALQUE-BANNED`
- **Punctuation & Quote Parity (سجاوندی و گیومه)**: Mismatched Persian quotation marks (`«` vs `»`) or lingering em-dashes (`—`).
  - *Code*: `MQM-PUNCT-QUOTES`, `MQM-PUNCT-EMDASH`
- **Orthography & ZWNJ (املا و نیم‌فاصله)**: Missing ZWNJ in prefixes (`می‌`) or suffixes (`ها`), or Arabic letters (`ي`, `ك`).
  - *Code*: `MQM-ORTH-ZWNJ`, `MQM-ORTH-ARABIC-CHAR`

### 3. Terminology & Consistency (هماهنگی و واژگان تخصصی)
Measures adherence to domain glossary and consistency of domain terms.
- **Inconsistent Term (عدم یکدستی واژگان)**: A recurring concept translated with multiple conflicting terms in the same document.
  - *Code*: `MQM-TERM-INCONSISTENCY`
- **Non-Standard Term (عدم رعایت اصطلاح استاندارد)**: Ignoring the mandatory domain profile terminology map.
  - *Code*: `MQM-TERM-NONSTANDARD`

### 4. Verity & Formatting (صحت صوری و محافظت از ساختار)
Measures integrity of non-linguistic technical assets.
- **Protected Token Lost (از بین رفتن توکن محافظت‌شده)**: Corruption of masked formulas (`$E=mc^2$`), code fences, citations, or URLs.
  - *Code*: `MQM-PROTECTED-TOKEN-LOST`

---

## 2. Error Severity Weights & Formulas

Errors are categorized into three severity tiers:

| Severity Level | Penalty Weight ($w_i$) | Description |
|---|---|---|
| **Critical (بحرانی)** | **10.0** | Falsifies meaning, alters medical dosages, corrupts code/formulas, or introduces major legal liability. |
| **Major (عمده)** | **5.0** | Substantial inaccuracy, omitted sentence/clause, or egregious calque corrupting comprehension. |
| **Minor (جزئی)** | **1.0** | Typographic slip, missing ZWNJ, minor punctuation imbalance, or slight stylistic roughness. |

### Quality Score Calculation Formula

$$\text{Total Penalty} = \sum_{i} (\text{count}_i \times w_i)$$

$$\text{Penalty per Word} = \frac{\text{Total Penalty}}{\max(\text{Word Count}, 1)}$$

$$\text{Quality Score} = \max\left(0.0, 100.0 - \left(\frac{\text{Total Penalty}}{\max(\text{Word Count}, 1)} \times 100\right)\right)$$

*Alternatively, for segment-based audits with baseline penalty scaling:*
$$\text{Quality Score} = \max\left(0.0, 100.0 - \text{Total Penalty}\right)$$

### Audit Verdict Thresholds
- **Pass / Gold Standard**: Score $\ge 90.0$ (Zero critical errors, minor flaws $\le 2$).
- **Pass / Acceptable**: Score $\ge 80.0$ (Zero critical errors, acceptable for publication with minor edit).
- **Fail / Rejected**: Score $< 80.0$ or any **Critical Error** detected (Requires automatic re-run or human translator intervention).
