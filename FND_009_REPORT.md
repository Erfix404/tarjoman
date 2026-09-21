# Work Package FND-009: Persian Quality Split — Completion Report

## 1. Executive Summary
- **Package ID:** FND-009
- **Title:** Persian quality split
- **Phase:** 1 (Foundation)
- **Status:** COMPLETED
- **Branch:** `phase/1-foundation`
- **Dependencies Verified:** FND-001 (DONE), FND-002 (DONE)
- **Downstream Packages Unblocked:**
  - `FND-010` (Versioned behavior and compliance registries, READY)
  - `FND-012` (Architecture-conformance CI, PLANNED)
  - `TRN-007` (Context builder, PLANNED)
  - `ASR-007` (Persian spoken normalization, PLANNED)
  - `TTS-003` (SpeechTextNormalizer, PLANNED)
- **Architecture References:**
  - `ARCHITECTURE_ZERO.md` §8 (Persian Quality Engine: §8.1 Auto-fix safe layer, §8.2 Diagnostic layer)
  - `ARCHITECTURE_ZERO.md` §19 (Locked Decision D09: "Regex anti-calque rules become diagnostics by default; unsafe semantic auto-rewrites are removed")
  - `ARCHITECTURE_ZERO.md` §22.2 (Package ownership: `core.quality` owns deterministic Persian normalization + typed findings; must not own model calls)
  - `AGENTS.md` (Mandatory invariants: "Runtime evaluation never mutates the candidate it scores")
  - `WORKPACKAGES.json` (FND-009 acceptance criteria verified)

---

## 2. Architecture & Design Principles (Codebase Design Skill)

In accordance with the **codebase-design** principles, the Persian quality module is structured as **deep modules** placed across a clean architectural seam:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Tarjoman Quality Seam                           │
├───────────────────────────────────┬────────────────────────────────────┤
│   Auto-Fix Normalization Layer    │     Diagnostic Inspection Layer    │
│  (safe, deterministic, idempotent)│    (read-only, typed findings)     │
│        PersianNormalizer          │           CalqueDetector           │
│       normalize_persian()         │          detect_calques()          │
├───────────────────────────────────┼────────────────────────────────────┤
│ • Arabic Kaf/Yeh/Teh-Marbuta/Heh  │ • 14 Najafi/Samii detection rules  │
│ • Strict ZWNJ affixes & clitics   │ • Structured QualityFinding models │
│ • Punctuation & spacing hygiene   │ • Exact character span offsets     │
│ • Zero em-dash policy (comma/paren│ • False-positive guards for idioms │
│ • Code block / token protection   │ • Code block masking protection    │
│ • Invariant: N(N(x)) == N(x)      │ • Invariant: Text NEVER mutated    │
└───────────────────────────────────┴────────────────────────────────────┘
```

### 2.1 Deep Module Characteristics
1. **Small, Ergonomic Surface Area:**
   - Normalization: `normalize_persian(text, ...) -> str` and `PersianNormalizer.normalize(text) -> str`.
   - Diagnostics: `detect_calques(text, ...) -> List[QualityFinding]` and `CalqueDetector.detect(text) -> List[QualityFinding]`.
2. **Encapsulated Complexity:**
   All regex compilations, Unicode directional isolates hygiene, character table lookups, ZWNJ affix boundary edge-cases, code block masking, and Najafi/Samii linguistic rationale dictionaries remain internal to the implementations.
3. **Strict Seam Isolation:**
   - Normalization is **pure auto-fix**: It only applies deterministic, non-semantic typographical rules that cannot corrupt meaning.
   - Calque detection is **pure diagnostic**: In accordance with Locked Decision D09 and AGENTS.md ("Runtime evaluation never mutates the candidate it scores"), it never silently rewrites or substitutes text. It returns structured findings for review or downstream pipeline reflection.

---

## 3. Deliverables Implemented

### 3.1 Auto-Fix Safe Normalization Layer (`src/tarjoman/quality/normalizer.py`)
- **`PersianNormalizer` Class & `normalize_persian` Function:**
  - **Arabic Character Standardization:** Converts `ك` -> `ک`, `ي` -> `ی`, `ى` -> `ی`, `ة` -> `ه`, `ۀ` -> `هٔ`, removes decorative tatweel/kashida (`ـ`), and normalizes Arabic-Indic digits to Persian digits.
  - **Strict ZWNJ Normalization (`‌`):** Deduplicates consecutive ZWNJs (`‌{2,}` -> `‌`), cleans spaces around ZWNJs, cleans stray boundary ZWNJs, fixes verbal prefixes (`می‌` and `نمی‌`), and standardizes suffixes (`ها`, `های...`, `تر`, `ترین`, `ه‌ای`, pronominal clitics `ام/ات/اش/مان/تان/شان`, and derivational affixes `مند/وار/ساز/سازی/پذیر/شناس/گرا`).
  - **Zero Em-Dash Policy:** Converts lingering em-dashes (`—`), en-dashes (`–`), and double-hyphens (`--`) into balanced Persian syntactic commas (`،`) or parentheses (`(...)`) depending on `em_dash_target`.
  - **Punctuation Hygiene:** Normalizes guillemets (`«...»`), ensures spaces after commas (`،`), periods (`.`), colons (`:`), semicolons (`؛`), exclamation marks (`!`), and question marks (`؟`), eliminates spaces before punctuation, and deduplicates commas and non-ellipsis periods.
  - **Directional Formatting Hygiene:** Strips invisible Unicode directional markers (`‎`, `‏`, `‪`–`‮`, `⁦`–`⁩`, `﻿`).
  - **Code Block Preservation:** Shields fenced code blocks (```` ```...``` ````) and inline code (`` `...` ``) from text modifications.
  - **Strict Idempotence Invariant:** Guaranteed and verified on clean, messy, and multiline texts:
    $$\forall x \in \text{Strings}, \quad \text{normalize}(\text{normalize}(x)) == \text{normalize}(x)$$

### 3.2 Diagnostic Calque Detection Layer (`src/tarjoman/quality/calque_detector.py`)
- **`QualityFinding` (Pydantic Model):**
  - `rule_id: str`: Machine-readable rule identifier (e.g. `CALQUE_PASSIVE_BY`, `CALQUE_PLAY_ROLE`, `CALQUE_COUNT_ON`, `CALQUE_AT_END_OF_DAY`, `CALQUE_MAKE_SENSE`, etc.).
  - `severity: str`: Severity level (`"critical"`, `"major"`, or `"minor"`).
  - `message: str`: Concise descriptive diagnostic.
  - `start: int`: 0-based character start index in source text.
  - `end: int`: 0-based character end index in source text.
  - `matched_text: str`: Exact matched slice from source text (`text[start:end] == matched_text`).
  - `suggested_fix: Optional[str]`: Idiomatic Persian suggestion based on Najafi and Samii Guilani authorities.
  - `explanation: str`: Linguistic authority justification citing Abolhassan Najafi (*غلط ننویسیم*) or Ahmad Samii Guilani (*نگارش و ویرایش*).
- **`CalqueDetector` Class & `detect_calques` Function:**
  - Implements 14 classical Persian anti-calque rules:
    1. `CALQUE_PASSIVE_BY`: Passive voice constructed with 'توسط' (passive by-agent).
    2. `CALQUE_PLAY_ROLE`: 'نقش بازی کردن' -> 'نقش ایفا کردن / سهم داشتن'.
    3. `CALQUE_COUNT_ON`: 'روی ... حساب کردن' -> 'به ... اعتماد کردن / بر ... تکیه کردن'.
    4. `CALQUE_ACT_AS`: 'به عنوان ... عمل کردن' -> 'در جایگاه ... بودن'.
    5. `CALQUE_AT_END_OF_DAY`: 'در پایان روز' -> 'در نهایت / سرانجام / روی‌هم‌رفته'.
    6. `CALQUE_MAKE_SENSE`: 'حس ایجاد کردن / معنا می‌دهد' -> 'منطقی بودن / معقول بودن'.
    7. `CALQUE_MAKE_DECISION`: 'یک تصمیم گرفتن' -> 'تصمیم گرفتن / تصمیمی اتخاذ کردن'.
    8. `CALQUE_OPEN_FIRE`: 'آتش گشودن' -> 'شلیک کردن / تیراندازی کردن'.
    9. `CALQUE_STRANGELY_ENOUGH`: 'به اندازه کافی عجیب است' -> 'شگفتا / عجیب آن‌که'.
    10. `CALQUE_POINT_OF_VIEW`: 'نقطه نظر' -> 'دیدگاه / نظر'.
    11. `CALQUE_APPLY_TO`: 'به کار بردن برای' -> 'درباره ... صدق کردن / شامل ... شدن'.
    12. `CALQUE_TAKE_BATH`: 'حمام گرفتن' -> 'دوش گرفتن / حمام کردن'.
    13. `CALQUE_GREEN_LIGHT`: 'چراغ سبز نشان دادن' -> 'موافقت کردن / اجازه دادن'.
    14. `CALQUE_END_OF_LINE`: 'به پایان خط رسیدن' -> 'به بن‌بست رسیدن / درمانده شدن'.
  - **False-Positive Guards:**
    - Literal children playing ("بچه‌ها در حیاط بازی می‌کردند") does not trigger `CALQUE_PLAY_ROLE`.
    - Literal fire ("آتش بخاری را خاموش کرد", "آتش زبانه کشید") does not trigger `CALQUE_OPEN_FIRE`.
    - Legitimate "در پایان" ("در پایان فصل", "در پایان کتاب", "در پایان ماه", "در پایان جلسه") does not trigger `CALQUE_AT_END_OF_DAY`.
    - Authentic Persian passives without 'توسط' ("کتاب نوشته شد", "طرح تصویب شد") do not trigger `CALQUE_PASSIVE_BY`.
    - Authentic meaning and sensation ("عشق به جهان معنا می‌دهد", "این موسیقی حس آرامش ایجاد می‌کند") do not trigger `CALQUE_MAKE_SENSE`.
    - Authentic decisions without 'یک' ("آن‌ها تصمیم گرفتند") do not trigger `CALQUE_MAKE_DECISION`.
    - Literal accounting and paper calculations ("حساب بانکی", "روی کاغذ حساب کرد") do not trigger `CALQUE_COUNT_ON`.
    - Code blocks and inline code are masked and completely ignored when `skip_code_blocks=True`.

### 3.3 Package Integration & Backward Compatibility
- **`src/tarjoman/quality/__init__.py`:**
  Exports `PersianNormalizer`, `normalize_persian`, `CalqueDetector`, `detect_calques`, and `QualityFinding`.
- **`src/tarjoman/stages/anti_calque.py`:**
  Preserves full backward compatibility with existing Stage 4 polishers and tests (`eliminate_calques`, `refine_sentence`, `detect_calques` returning `List[str]`), while exposing `detect_calques_structured(text)` as a bridge to typed `QualityFinding` items.

### 3.4 Roadmap & Work Package Tracking
- Updated `WORKPACKAGES.json`: Promoted `FND-009` status from `READY` to `DONE`.

---

## 4. Verification & Testing Evidence

### 4.1 Pytest Execution
- **Test Suite:** `tests/test_persian_quality_split.py` + all existing test suites.
- **Command:** `.venv/bin/pytest`
- **Result:** **426 passed** (388 existing tests + 38 new FND-009 tests), 9 click deprecation warnings, 0 failures in 5.11s.

### 4.2 Comprehensive 10-Domain Benchmark
- **Command:** `.venv/bin/python benchmarks/run_benchmarks.py`
- **Result:** **10/10 Domains PASSED** (literary, scientific, philosophy, legal, technical, medical, media, financial, classical, transcreation) with 100.0 audit scores in 0.48s.

### 4.3 Acceptance Criteria Checklist
- [x] `normalization idempotence tests`: Verified across clean text, messy text, Arabic variants, ZWNJ prefixes/suffixes, punctuation hygiene, zero em-dash conversion, code blocks, and a 25-sentence diverse realistic corpus.
- [x] `anti-calque rules default diagnostic`: Locked Decision D09 enforced — calques are reported as structured `QualityFinding` models without blind auto-replacement or mutation.
- [x] `false-positive regression cases`: Extensive suite of authentic Persian counter-examples verified not to misfire (literal playing, literal fire, authentic "در پایان", passives without 'توسط', authentic "معنا دادن", literal calculations, code blocks).
- [x] All 388 existing tests pass with zero regressions (total 426 tests pass).
- [x] All 10 domain benchmarks pass.

---

## 5. PR Evidence & Architectural Invariants

| Requirement | Evidence / Conformance |
|---|---|
| **Work Package ID** | `FND-009` |
| **Dependencies Verified** | `FND-001` (DONE), `FND-002` (DONE) |
| **Files Changed/Added** | `src/tarjoman/quality/__init__.py`<br>`src/tarjoman/quality/normalizer.py`<br>`src/tarjoman/quality/calque_detector.py`<br>`src/tarjoman/stages/anti_calque.py`<br>`tests/test_persian_quality_split.py`<br>`WORKPACKAGES.json` |
| **Architecture Decisions** | **D09** (Regex anti-calque rules become diagnostics by default; unsafe semantic auto-rewrites removed)<br>**§8.1** (Deterministic auto-fix safe normalization layer)<br>**§8.2** (Diagnostic inspection layer with typed findings)<br>**§22.2** (`core.quality` owns deterministic Persian normalization + typed findings; must not own model calls) |
| **Mandatory Invariants** | Runtime evaluation never mutates the candidate it scores; normalization is strictly idempotent; diagnostic detector returns typed Pydantic findings with exact character spans. |
| **Schema/Migration Impact** | None; pure quality layer modules. |
| **Dependency/License Impact** | Zero external dependencies added; relies purely on Python standard library and Pydantic. |
| **Benchmark Impact** | 10/10 domain benchmarks pass in 0.48s with 100.0 audit scores. |
| **Known Limitations** | Semantic revision suggestions based on LLM reflection are owned by revision stages in Stage 3, not deterministic core quality. |

---

## 6. Conclusion
Work Package FND-009 is fully implemented, verified, and complete in accordance with `ARCHITECTURE_ZERO.md` §8, §19 (D09), §22.2, and `ROADMAP.md`. All acceptance criteria have passed with executable evidence.
