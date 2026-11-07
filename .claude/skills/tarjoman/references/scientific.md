# Scientific Translation Reference Guide (راهنمای ترجمه علمی و دانشگاهی)

## Overview
The Scientific domain profile is tailored for peer-reviewed journal papers, academic textbooks, dissertations, and research monographs. Precision, terminological consistency, objective passive/active balance, and strict bidi (bidirectional) text handling are paramount.

---

## 1. Mathematical Formulas & LaTeX Preservation

Mathematical expressions, formulas, and symbols must remain completely uncorrupted:
- **Inline Formulas**: Retain `$E=mc^2$`, `$p < 0.05$`, `$\alpha = 0.01$` verbatim within dollar signs.
- **Display Equations**: Retain `$$...$$` blocks verbatim.
- **Directional Isolation**: When an inline formula appears inside Persian RTL text, ensure it is directionally isolated so that minus signs, inequality operators, and subscripts do not flip across RTL/LTR boundary.

Example:
- *Source*: The empirical findings indicate a statistically significant correlation ($p < 0.01$) between the two variables.
- *Persian*: یافته‌های تجربی نشان‌دهنده همبستگی معنادار از نظر آماری ($p < 0.01$) میان این دو متغیر است.

---

## 2. Directional Isolation & English Technical Terms

When an untranslated English term, acronym, or gene/protein identifier appears within Persian prose:
1. Wrap with Unicode directional isolates or parentheses: `(Machine Learning)` or `DNA`.
2. First occurrence: Provide the standard Persian academic equivalent followed by the English original in parentheses:
   - *Example*: «یادگیری تقویتی (Reinforcement Learning)»
3. Subsequent occurrences: Use the Persian equivalent consistently without repeating the English acronym unless disambiguation requires it.

---

## 3. Bibliographic Citations & Reference Markers

Academic citation keys must be preserved untouched:
- Numeric brackets: `[1]`, `[1, 3-5]`, `[12]`
- Author-year citations: `(Smith et al., 2020)`, `(Goodfellow and Bengio, 2016)`
- In Persian text, place brackets after the Persian punctuation or clause boundary consistently:
  - *Example*: «این فرضیه پیش‌تر در مطالعات متعددی مورد تأیید قرار گرفته است [12].»

---

## 4. Academic Tone & Register

- **Impersonal Rigor**: Persian academic prose prefers an objective, rigorous tone. Avoid casual expressions or emotional phrasing.
- **Methodological Passives**: While literary translation bans passives, scientific methodology often employs legitimate passive constructions when the researcher is irrelevant:
  - *Legitimate*: نمونه‌ها در دمای منفی بیست درجه سانتی‌گراد نگهداری شدند.
  - *Calqued (Banned)*: نمونه‌ها توسط محققان در دمای منفی بیست درجه سانتی‌گراد نگهداری شدند. (Never use `توسط` with passive!)
- **Numbers and Digits**: Retain **Western Latin digits** (`0123456789`) in scientific papers for measurements, statistical coefficients, sample sizes ($N=150$), and tables to ensure proper alignment.

---

## 5. Standard Academic Terminology Map
| English Source | Standard Academic Persian | Avoid (Calques/Casual) |
|---|---|---|
| Empirical evidence | شواهد تجربی | مدارک امپیریکال |
| Statistically significant | از نظر آماری معنادار | معنی‌دار از نظر آمار |
| Hypothesis | فرضیه | حدس علمی |
| Independent variable | متغیر مستقل | متغیر خودکفا |
| Controlled trial | کارآزمایی کنترل‌شده | آزمایش کنترل |
| Methodology | روش‌شناسی | متدولوژی |
| Qualitative analysis | تحلیل کیفی | آنالیز کیفی |

---

## نمونه‌های بد ← خوب (فارسی)

این نمونه‌ها مهم‌تر از قاعده‌های بالا هستند: پیش از ترجمه، چند بار بخوانشان. الگو در همه یکی است: ساختار انگلیسی را رها کن، معنا را با فعل فارسی بگو، «توسط» و «یک» و ضمیرهای اضافه را حذف کن، و اصطلاح جاافتاده‌ی همان رشته را به کار ببر.

| انگلیسی | ترجمه‌ی ماشینی | فارسی خوب |
|---|---|---|
| These results suggest that the treatment may be effective. | این نتایج پیشنهاد می‌کنند که درمان ممکن است مؤثر باشد. | این نتایج نشان می‌دهد درمان احتمالاً مؤثر است. |
| Data were collected from 120 participants. | داده‌ها از ۱۲۰ شرکت‌کننده جمع‌آوری شدند. | از 120 شرکت‌کننده داده گردآوری شد. |
| A significant correlation was observed between X and Y (p < 0.05). | یک همبستگی معنادار بین X و Y مشاهده شد (p < 0.05). | میان X و Y همبستگی معناداری دیده شد (p < 0.05). |
| Further research is needed to confirm these findings. | تحقیقات بیشتری مورد نیاز است تا این یافته‌ها را تأیید کند. | برای تأیید این یافته‌ها پژوهش بیشتری لازم است. |
| In this paper, we propose a novel method for… | در این مقاله، ما یک روش نوین را برای … پیشنهاد می‌کنیم. | در این مقاله روش تازه‌ای برای … پیشنهاد می‌کنیم. |
| This is consistent with previous studies [12]. | این با مطالعات قبلی سازگار است [12]. | این یافته با پژوهش‌های پیشین همخوان است [12]. |
