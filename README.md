# 🏛️ Tarjoman (موتور جامع ترجمه و نشر «ترجمان»)

<div align="center">

**The Autonomous Persian Translation & Publishing Super-Skill for AI Agents (Claude Code, Hermes, Cursor) & Human Translators**

[![Version](https://img.shields.io/badge/version-v2.3.0-blue.svg)](https://github.com/Erfix404/tarjoman/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-343%20passing-brightgreen.svg)](#benchmarks--quality-evidence)
[![Benchmarks](https://img.shields.io/badge/benchmarks-10%2F10%20domains%20100%25%20PASS-success.svg)](#benchmarks--quality-evidence)
[![Creator](https://img.shields.io/badge/creator-Erfan%20Ashouri%20%28%40Erfix404%29-orange.svg)](https://github.com/Erfix404)
[![Multi-Agent](https://img.shields.io/badge/agents-Claude%20Code%20%7C%20Hermes%20%7C%20Cursor-purple.svg)](#multi-agent-super-skill-integration)
[![Typography](https://img.shields.io/badge/typography-Zero%20Em--Dash%20Guarantee-magenta.svg)](#pillar-4-zero-em-dash--strict-orthography-guarantee)
[![Publishing](https://img.shields.io/badge/publishing-W3C%20EPUB%203%20RTL%20%2B%20Typst%20PDF-red.svg)](#pillar-8-publication-ready-multi-format-composers)

---

Tarjoman transforms AI agents into a **full-fledged professional Persian publishing house**. It wraps a deterministic 5-pass translation pipeline, anti-calque linguistic purity engine, Persian de-AI humanizer, and publication-grade multi-format composers into a single skill that any AI coding agent can invoke.

ترجمان، عامل‌های هوش مصنوعی را به یک **انتشارات حرفه‌ای فارسی تمام‌عیار** تبدیل می‌کند. خط لوله‌ی پنج‌مرحله‌ای ترجمه، موتور خالص‌سازی ضد گرته‌برداری، انسانی‌ساز متن فارسی و ابزارهای نشر چندقالبی، همگی در قالب یک مهارت واحد گردآمده‌اند که هر عامل هوشمند برنامه‌نویسی می‌تواند آن را فراخوانی کند.

[Core Architecture](#8-core-architectural-pillars) · [Quick Start](#quickstart--cli-guide) · [Python API](#python-api) · [Benchmarks](#benchmarks--quality-evidence) · [Agent Integration](#multi-agent-super-skill-integration) · [Contributing](#contributing--license)

</div>

---

## The Core Problem

Translating English into Persian using raw LLMs or traditional machine translation (Google Translate, DeepL) routinely produces prose plagued by systematic failures:

### Linguistic Calques (گرته‌برداری)

Blind translation of English syntactic patterns into Persian, creating unnatural constructions:

| Calque Pattern | Example | Natural Persian |
|:---|:---|:---|
| Passive «توسط» abuse | *این کار توسط تیم انجام شد* | *تیم این کار را انجام داد* |
| «نقش بازی کردن» | *آب نقش مهمی بازی می‌کند* | *آب اهمیت زیادی دارد* |
| «حس ایجاد کردن» | *این حس امنیت ایجاد می‌کند* | *این مایه‌ی آرامش است* |
| «روی چیزی حساب کردن» | *روی این فرصت حساب کنید* | *به این فرصت امیدوار باشید* |

### AI-Slop & Copula Inflation

Machine-generated Persian is saturated with ceremonial filler and inflated copulas:

- **می‌باشد** / **به شمار می‌رود** / **در راستای** / **لازم به ذکر است**
- Generic openers: *در دنیای امروز*، *در عصر دیجیتال*
- Promotional emptiness: *بی‌نظیر*، *فوق‌العاده*، *مثال‌زدنی*

### Broken Orthography

- Foreign em-dashes (`—`) that have no place in Persian punctuation
- Arabic `ي`/`ك` instead of Persian `ی`/`ک`
- Missing ZWNJ (نیم‌فاصله): `میکنم` instead of `می‌کنم`
- Missing or fake tanvin: `گاهاً` instead of `گاهی`

### Context Amnesia in Long Books

Inconsistent character names, terminology drift, and voice changes across chapters when translating book-length works.

### Bidi & Math Corruption

Inverted brackets, broken code fences, mangled formulas, and scrambled LTR terms inside RTL text.

**Tarjoman solves every one of these problems deterministically.**

---

## 8 Core Architectural Pillars

### Pillar 1: 5-Pass Reflective Translation Pipeline

Every text passes through five sequential stages that emulate how a professional human translator works:

```
Source Text
    │
    ▼
┌─────────────────────────────────────────────────┐
│  Pass 1 · Pre-Analysis & Token Masking          │
│  Shields code, math, URLs, emails, numbers      │
├─────────────────────────────────────────────────┤
│  Pass 2 · Contextual Semantic Draft             │
│  Domain-aware translation with termbase          │
├─────────────────────────────────────────────────┤
│  Pass 3 · Anti-Calque Cleansing & Reflection    │
│  4-axis MQM critique → iterative refinement     │
├─────────────────────────────────────────────────┤
│  Pass 4 · De-AI Humanizing & Stylistic Polish   │
│  18-pattern humanizer, cadence, typography      │
├─────────────────────────────────────────────────┤
│  Pass 5 · MQM Quality Audit                     │
│  Score ≥ 90.0, zero critical findings            │
└─────────────────────────────────────────────────┘
    │
    ▼
Publication-Ready Persian Text
```

### Pillar 2: Anti-Calque & Linguistic Purity Engine

Exhaustive rule sets drawn from the two definitive Persian editorial authorities:

- **Abolhassan Najafi** (*غلط ننویسیم*): canonical reference on Persian calques and usage errors
- **Ahmad Samii Guilani** (*نگارش و ویرایش*): comprehensive editing and style guide

The engine detects and eliminates structural calques (passive voice abuse, false compounds), lexical calques (loan-translations), and stylistic calques (unnatural word order).

### Pillar 3: Persian De-AI & Humanizer (T1-T18)

The `PersianHumanizer` applies 18 transformation patterns to strip machine-generated artifacts:

| ID | Pattern | Action |
|:---|:---|:---|
| T1 | Copula inflation (می‌باشد, به شمار می‌رود) | Rewrite to natural forms |
| T2 | Ceremonial fillers (لازم به ذکر, شایان ذکر) | Remove |
| T3 | Significance inflation (اهمیت ویژه, نقش بسزا) | Simplify |
| T4 | Generic openers/closers (در دنیای امروز) | Remove |
| T5 | «در راستای» abuse | Replace with «برای» |
| T6 | Promotional emptiness (بی‌نظیر, فوق‌العاده) | Strip |
| T7-T8 | Rule-of-three, negative parallelism | Detect & flag |
| T9 | Tacked-on analysis (نشان‌دهنده, بیانگر) | Simplify |
| T10-T11 | Vague authority, false ranges | Detect & flag |
| T12 | Foreign em-dashes and en-dashes | Convert to «،» |
| T13 | English calques in Persian | Rewrite idiomatically |
| T14 | همچنین pileup | Detect & flag |
| T15 | Fake tanvin (گاهاً → گاهی) | Correct |
| T16-T18 | Bold-header lists, chatbot markers, catch-all | Detect/remove |

Code blocks, inline code, and markdown tables are **shielded** before any transformation and restored byte-identical afterward.

### Pillar 4: Zero Em-Dash & Strict Orthography Guarantee

- **Zero foreign dashes**: every `—` and `–` is converted to Persian commas or parentheses
- **Standard Persian quotes**: `«...»` guillemets replace straight ASCII quotes
- **Clean ZWNJ**: proper half-space insertion for verb prefixes and compound words
- **Tanvin auto-repair**: 18 Arabic loanwords get correct tanvin (لطفا → لطفاً)
- **Fake tanvin correction**: 8 Persian words wrongly carrying tanvin (گاهاً → گاهی)
- **Arabic character normalization**: `ي` → `ی`, `ك` → `ک`

### Pillar 5: 10 Specialized Domain Profiles

Each domain profile carries its own terminology, style constraints, and quality thresholds:

| # | Domain | Key Characteristics |
|:---|:---|:---|
| 1 | **Literary & Fiction** | Dialogue tag inversion, poetic cadence, narrative register |
| 2 | **Scientific & Academic** | Formal academic prose, citation preservation |
| 3 | **Philosophy & Humanities** | Conceptual precision, Continental terminology |
| 4 | **Legal & Statutory** | Statutory language, clause numbering integrity |
| 5 | **Technical & Engineering** | Code-aware, LTR isolate preservation |
| 6 | **Medical & Clinical** | Clinical terminology, dosage precision |
| 7 | **Media & Journalism** | News style, headline conventions |
| 8 | **Financial & Economics** | Monetary formatting, indicator terminology |
| 9 | **Classical & Historical** | Archaic register, classical Persian vocabulary |
| 10 | **Transcreation & Creative** | Brand voice adaptation, creative liberty |

### Pillar 6: Dual-Level Technical Terminology

Two terminology modes for technical content:

- **System-Docs Mode**: developer-facing terms stay in English inside Unicode LTR isolates (`⁦term⁩`), so code references remain copy-pasteable
- **Journal/Scholarly Mode**: all terms rendered in formal Persian with parenthetical English on first occurrence

### Pillar 7: Long-Form Book Continuity Engine

Purpose-built for translating entire books across hundreds of pages:

- **Character & Style Bible**: tracks character names, speech patterns, and relationships for consistency across chapters
- **Scene Continuity Tracker**: monitors POV, location, atmosphere, and timeline
- **SHA-256 Chunk Caching**: resumable translation with content-addressed caching so interrupted jobs pick up exactly where they stopped
- **Dynamic Termbase**: auto-extracts and aligns terminology in `terms.tsv`

### Pillar 8: Publication-Ready Multi-Format Composers

| Format | Description |
|:---|:---|
| **W3C EPUB 3 RTL** | True bidirectional ebook with chapter navigation, RTL styling, and metadata |
| **Typst PDF** | Vector-grade Persian typesetting with Vazirmatn font (A4 / Book layouts) |
| **Interactive HTML Reader** | Synchronized bilingual scrolling, glassmorphism UI, real-time search |
| **Bilingual Markdown** | Segment-aligned tables for human post-editing (MTPE) |

---

## Multi-Agent Super-Skill Integration

Tarjoman is designed as a **skill** that AI coding agents load and invoke autonomously.

### Claude Code CLI

Add the skill directory to your Claude Code skills:

```bash
# Symlink or copy the skill pack
cp -r agent-packs/cursor/ ~/.claude/skills/tarjoman

# Invoke directly
/tarjoman translate my_article.txt --domain technical
```

### Hermes Agent

```python
# Hermes autonomous agent integration
skill_view(name='tarjoman')
```

### Cursor / Windsurf

The `.cursorrules` file at the repository root provides editor-level integration. Copy it to your project:

```bash
cp .cursorrules /path/to/your/project/.cursorrules
```

---

## Installation & Requirements

### Prerequisites

- Python 3.10 or later
- (Optional) [Typst](https://typst.app/) for PDF compilation

### Install

```bash
# Clone the repository
git clone https://github.com/Erfix404/tarjoman.git
cd tarjoman

# Install in editable mode
pip install -e .

# With PDF support
pip install -e ".[pdf]"

# With development tools
pip install -e ".[dev]"
```

---

## Quickstart & CLI Guide

### Translate a Document

```bash
# Auto-detect domain and translate
tarjoman translate article.txt

# Specify domain and output file
tarjoman translate paper.txt --domain scientific --output paper_fa.txt
```

### Manage a Book Project

```bash
# Initialize a book project
tarjoman book init "My Novel" --source-dir chapters/

# Translate all chapters
tarjoman book translate

# Check progress
tarjoman book status
```

### EPUB Roundtrip

```bash
# Translate an EPUB preserving structure and styling
tarjoman epub roundtrip input.epub --output output_fa.epub
```

### Quality Linting & Auto-Fixing

```bash
# Lint Persian text for calques, typography, and orthography issues
tarjoman lint translated_text.txt

# Run MQM quality audit
tarjoman audit translated_text.txt

# Completeness: dropped/summarized paragraphs, numbers, citation markers, URLs, code
tarjoman verify source.md translated.md

# Clean PDF-extracted text before translating (headers, page numbers, hyphen breaks, wrapped lines)
tarjoman prep book.txt -o book.clean.txt
```

### Multi-Format Composing

```bash
# Compose Typst PDF
tarjoman compose typst source.txt translated.txt --output book.pdf

# Compose interactive HTML reader
tarjoman compose html source.txt translated.txt --output reader.html

# Compose EPUB
tarjoman compose epub source.txt translated.txt --output book.epub

# Compose bilingual Markdown
tarjoman compose markdown source.txt translated.txt --output bilingual.md
```

### Domain Detection

```bash
# Detect the domain of a text
tarjoman route "The court hereby declares..."
# → Legal & Statutory (confidence: 0.94)
```

---

## Python API

```python
from tarjoman.core.pipeline import TranslationPipeline
from tarjoman.core.contracts import DomainProfile, DomainType
from tarjoman.domains.router import DomainRegistry, DomainRouter
from tarjoman.stages.humanizer import PersianHumanizer
from tarjoman.stages.anti_calque import AntiCalqueEngine

# 1. Route to the correct domain
router = DomainRouter()
domain_type = router.route("The cellular membrane exhibits selective permeability...")
profile = DomainRegistry.get_profile(domain_type)

# 2. Run the 5-pass translation pipeline
pipeline = TranslationPipeline()
segments, audit = pipeline.run(
    raw_text="The cellular membrane exhibits selective permeability...",
    profile=profile,
)

# 3. Access translation results
for seg in segments:
    print(seg.translated_text)

print(f"MQM Score: {audit.score}")
print(f"Critical findings: {len(audit.critical_findings)}")

# 4. Humanize existing Persian text (strip AI artifacts)
humanized = PersianHumanizer.humanize(
    "این موضوع دارای اهمیت ویژه‌ای می‌باشد.",
    register="formal-human",
)
# → "این موضوع اهمیت زیادی دارد."

# 5. Detect calques in Persian text
calques = AntiCalqueEngine.detect_calques("او نقش مهمی بازی می‌کند.")
# → ["نقش بازی کردن → idiomatic rewrite needed"]
```

---

## Benchmarks & Quality Evidence

All 10 domain benchmarks pass with MQM scores ≥ 90.0 and zero critical findings.

Run the benchmark suite:

```bash
python benchmarks/run_benchmarks.py
```

| # | Domain | MQM Score | Critical | Status |
|:---|:---|:---:|:---:|:---:|
| 1 | Literary & Fiction | ≥ 90.0 | 0 | ✅ PASS |
| 2 | Scientific & Academic | ≥ 90.0 | 0 | ✅ PASS |
| 3 | Philosophy & Humanities | ≥ 90.0 | 0 | ✅ PASS |
| 4 | Legal & Statutory | ≥ 90.0 | 0 | ✅ PASS |
| 5 | Technical & Engineering | ≥ 90.0 | 0 | ✅ PASS |
| 6 | Medical & Clinical | ≥ 90.0 | 0 | ✅ PASS |
| 7 | Media & Journalism | ≥ 90.0 | 0 | ✅ PASS |
| 8 | Financial & Economics | ≥ 90.0 | 0 | ✅ PASS |
| 9 | Classical & Historical | ≥ 90.0 | 0 | ✅ PASS |
| 10 | Transcreation & Creative | ≥ 90.0 | 0 | ✅ PASS |

**Unit Tests**: 343 passing (265 core + 78 humanizer/de-AI)

```bash
pytest  # Run full test suite
```

---

## Project Structure

```
tarjoman/
├── core/                  # Pipeline orchestration & data contracts
│   ├── pipeline.py        # TranslationPipeline (5-pass)
│   └── contracts.py       # TextSegment, DomainProfile, AuditReport
├── stages/                # Pipeline stages
│   ├── stage1_pre_analysis.py   # Token masking (code, math, URLs)
│   ├── stage2_draft.py          # Semantic drafting with termbase
│   ├── stage3_reflection.py     # 4-axis MQM reflection
│   ├── stage4_polish.py         # Typography, cadence, anti-calque
│   ├── stage5_audit.py          # Quality audit & scoring
│   ├── anti_calque.py           # Najafi/Guilani rule engine
│   ├── humanizer.py             # PersianHumanizer (T1-T18)
│   └── poetic_adapter.py        # Verse classification & adaptation
├── composers/             # Multi-format output
│   ├── typst_pdf.py       # Typst PDF composer
│   ├── epub3.py           # W3C EPUB 3 RTL composer
│   ├── epub_roundtrip.py  # EPUB translation roundtrip
│   ├── html_reader.py     # Interactive bilingual HTML
│   └── bilingual_md.py    # Segment-aligned Markdown
├── domains/               # 10 specialized domain profiles
│   └── router.py          # DomainRouter & DomainRegistry
├── memory/                # Long-form book support
│   ├── character_bible.py # Character & Style Bible
│   ├── scene_continuity.py# Scene Continuity Tracker
│   ├── cache.py           # SHA-256 chunk caching
│   ├── termbase.py        # Dynamic terminology extraction
│   └── manifest.py        # Book manifest management
├── parsers/               # Input parsers
│   └── epub_parser.py     # EPUB structure parser
├── linter.py              # Persian linguistic & typography linter
└── cli.py                 # Click CLI entry point
```

---

## Creator & Maintainer

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/Erfix404">
        <img src="https://github.com/Erfix404.png" width="120px;" alt="Erfan Ashouri"/>
        <br />
        <sub><b>Erfan Ashouri (عرفان عاشوری)</b></sub>
      </a>
      <br />
      <sub>Creator, Author & Maintainer</sub>
      <br />
      <a href="https://github.com/Erfix404">@Erfix404</a>
    </td>
  </tr>
</table>

---

## Contributing & License

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding guidelines, and the pull request process.

**License**: [MIT](LICENSE)

**Acknowledgements**: some ideas were adapted from Kaman AI Translator, «لحن من» (lahne-man) and hermes-literary-translation-mastery. See [docs/CREDITS.md](docs/CREDITS.md).

---

<div align="center">

*Built with obsessive attention to Persian linguistic purity.*

**[Tarjoman](https://github.com/Erfix404/tarjoman)** · Created by [Erfan Ashouri (@Erfix404)](https://github.com/Erfix404)

</div>
