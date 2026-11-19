# 🏛️ Tarjoman (موتور جامع ترجمه و نشر «ترجمان»)

<div align="center">

**The Autonomous Persian Translation & Publishing Super-Skill for AI Agents (Claude Code, Hermes, Cursor) & Human Translators**

[![Version](https://img.shields.io/badge/version-v2.3.0-blue.svg)](https://github.com/Erfix404/tarjoman/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-495%20passing-brightgreen.svg)](#benchmarks--quality-evidence)
[![Benchmarks](https://img.shields.io/badge/benchmarks-10%2F10%20domains%20100%25%20PASS-success.svg)](#benchmarks--quality-evidence)
[![Creator](https://img.shields.io/badge/creator-Erfan%20Ashouri%20%28%40Erfix404%29-orange.svg)](https://github.com/Erfix404)
[![Multi-Agent](https://img.shields.io/badge/agents-Claude%20Code%20%7C%20Hermes%20%7C%20Cursor-purple.svg)](#multi-agent-super-skill-integration)
[![Typography](https://img.shields.io/badge/typography-Zero%20Em--Dash%20Guarantee-magenta.svg)](#pillar-4-zero-em-dash--strict-orthography-guarantee)
[![Publishing](https://img.shields.io/badge/publishing-W3C%20EPUB%203%20RTL%20%2B%20Typst%20PDF-red.svg)](#pillar-8-publication-ready-multi-format-composers)

---

Tarjoman transforms AI agents into a **full-fledged professional Persian publishing house**. It wraps a deterministic 5-pass translation pipeline, anti-calque linguistic purity engine, Persian de-AI humanizer, and publication-grade multi-format composers into a single skill that any AI coding agent can invoke.

ترجمان، عامل‌های هوش مصنوعی را به یک **انتشارات حرفه‌ای فارسی تمام‌عیار** تبدیل می‌کند. خط لوله‌ی پنج‌مرحله‌ای ترجمه، موتور خالص‌سازی ضد گرته‌برداری، انسانی‌ساز متن فارسی و ابزارهای نشر چندقالبی، همگی در قالب یک مهارت واحد گردآمده‌اند که هر عامل هوشمند برنامه‌نویسی می‌تواند آن را فراخوانی کند.

**[راهنمای فارسی: نصب و شروع سریع](README.fa.md)** · [Core Architecture](#8-core-architectural-pillars) · [Quick Start](#quickstart--cli-guide) · [Python API](#python-api) · [Benchmarks](#benchmarks--quality-evidence) · [Agent Integration](#multi-agent-super-skill-integration) · [Contributing](#contributing--license)

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

### Multi-Agent Skill Installer (`tarjoman install`)

Install the skillpack (or modern Cursor `.mdc` rules) and optional MCP server configuration into any workspace in one command:

```bash
tarjoman install --target claude --with-mcp       # .claude/skills/tarjoman + .mcp.json
tarjoman install --target cursor --with-mcp       # .cursor/rules/tarjoman.mdc + .cursor/mcp.json
tarjoman install --target antigravity --with-mcp  # .agent/skills/tarjoman + .mcp.json
tarjoman install --target codex --with-mcp        # .codex/skills/tarjoman + .mcp.json
tarjoman install --target hermes --with-mcp       # .hermes/skills/tarjoman + .mcp.json
```

### Claude Code CLI

Copy the skill folder into your Claude Code skills, then install the checking tools:

```bash
git clone https://github.com/Erfix404/tarjoman.git
mkdir -p ~/.claude/skills
cp -r tarjoman/.claude/skills/tarjoman ~/.claude/skills/   # or <project>/.claude/skills/
pip install git+https://github.com/Erfix404/tarjoman.git    # tarjoman lint / verify / srt check
```

Then just ask Claude Code: "Translate chapter1.md into Persian with tarjoman." The agent does the translation itself; the CLI only checks it. Full Persian guide: [README.fa.md](README.fa.md).

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

### MCP Server (`tarjoman mcp`)

Any MCP-compatible agent (Claude Code, Claude Desktop, Cursor, Hermes, Antigravity) can connect over stdio to invoke `tarjoman_route_guide`, `tarjoman_lint`, `tarjoman_fix_safe`, `tarjoman_verify`, `tarjoman_book_context`, `tarjoman_srt_check`, and `tarjoman_i18n_check` directly:

```json
{
  "mcpServers": {
    "tarjoman": {
      "command": "tarjoman",
      "args": ["mcp"]
    }
  }
}
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

> **Note on CLI translation:** Tarjoman does not bundle an LLM client. The AI coding agent performs the actual translation using the skill, while the CLI provides deterministic checking, preprocessing, book-project tracking, subtitle tools, and publishing composers. By default, `tarjoman translate` runs the 5-pass pipeline using `EchoDraftBackend` unless a custom `TranslationBackend` is wired in via the Python API.

### Translate a Document

```bash
# Auto-detect domain and run the 5-pass pipeline (uses EchoDraftBackend by default)
tarjoman translate article.txt

# Specify domain and output file
tarjoman translate paper.txt --domain scientific --output paper_fa.txt
```

### Manage a Book Project

```bash
# Initialize a book project (creates manifest.json, terms.tsv, and style.md)
tarjoman book init "My Novel" -o ./my-book

# Suggest recurring names and terms from the English source before translating
tarjoman book candidates chapter1.en.md --project ./my-book

# Seed a book project with curated starter glossaries (technical-ai, medical-patient, financial, legal-licenses)
tarjoman book glossary list
tarjoman book glossary import ./my-book technical-ai --json

# Register character voices, transliterations, and تو/شما address rules
tarjoman book characters ./my-book --add "Alice:آلیس:formal:تو" --list

# Record domain-tagged terms (keeps terms.db and terms.tsv in sync)
tarjoman book terms ./my-book --add "Oh dear=وای خدا:literary"

# Extract compact, chunk-relevant memory (only matched terms/characters + scene + previous tail)
tarjoman book context ./my-book chapter2.en.md --prev chapter1.fa.md --tail 2 --json

# Check translated chapter against termbase, characters, register, and completeness
tarjoman book check ./my-book chapter1.en.md chapter1.fa.md --json

# Check progress and resumable chunk manifest
tarjoman book status ./my-book
tarjoman book manifest ./my-book
```

### EPUB Extraction, Merge & Roundtrip

```bash
# Extract EPUB chapters into marker-delimited [#node_id] Markdown files for agent translation
tarjoman epub extract input.epub -o ./epub_work --json

# Merge translated [#node_id] files back into a strict RTL Persian EPUB 3
tarjoman epub merge input.epub ./epub_work -o output_fa.epub --json

# Structural EPUB parse and RTL recompose roundtrip (or pass custom translations via EpubRoundtripComposer)
tarjoman epub roundtrip input.epub --output output_fa.epub
```

### Safe Orthography Auto-Fixing, Linting, Verification, Localization & Subtitles

```bash
# Apply safe, non-semantic orthography fixes (Arabic ی/ک, ZWNJ, tanvin, punctuation; shields code/LaTeX/URLs/placeholders)
tarjoman fix translated_text.txt --in-place
tarjoman fix translated_text.txt --dry-run --json

# Lint Persian text (filter by style, hard errors only, or structured JSON)
tarjoman lint translated_text.txt --style literary --errors-only --json

# Run MQM quality audit
tarjoman audit translated_text.txt

# Completeness: paragraphs, numbers, citations, URLs, code, LaTeX, placeholders, headings, tables
tarjoman verify source.md translated.md --json

# Localization check for JSON, ARB, PO, and YAML files (keys, placeholders, HTML tags, count plurals, length ratio)
tarjoman i18n check locales/en.json locales/fa.json --max-ratio 1.8 --json

# Clean PDF-extracted text before translating (headers, page numbers, hyphen breaks, wrapped lines)
tarjoman prep book.txt -o book.clean.txt

# Subtitles (SRT & WebVTT): text-only timeline-safe workflow (extract -> translate -> merge -> check)
tarjoman srt extract film.en.vtt -o film.cues.txt
tarjoman srt merge film.en.vtt film.fa.cues.txt -o film.fa.vtt
tarjoman srt check film.fa.srt --source film.en.srt --json
```

> Research notes & blind two-axis evaluation: [docs/research/translation-quality-roadmap.md](docs/research/translation-quality-roadmap.md), Round 3 blind Hydrogen A/B study ([docs/research/real-texts/round3/README.md](docs/research/real-texts/round3/README.md), Skill 7–1 over raw baseline), the 104-sample naturalness eval set across all 22 routed styles ([`benchmarks/eval_naturalness.py`](benchmarks/eval_naturalness.py)), blind position-randomized A/B judge ([`benchmarks/run_judge.py`](benchmarks/run_judge.py)), plus Persian guides in `.claude/skills/tarjoman/references/`: `fidelity.md` (Khazaeifar fidelity, equal-effect worksheet, blind review & selective back-translation), `editor-najafi.md`, `naturalize.md`, `colloquialize.md`, and `book.md` (style anchoring).

### Multi-Format Composing

```bash
# Compose Typst source (and optionally compile to PDF)
tarjoman compose typst translated.md -o book.typ --style book --compile

# Compose interactive HTML reader
tarjoman compose html source.md translated.md -o reader.html

# Compose W3C EPUB 3 RTL e-book
tarjoman compose epub translated.md -o book.epub --title "My Book"

# Compose bilingual Markdown comparison table
tarjoman compose bilingual source.md translated.md -o bilingual.md
```

### Domain Detection

```bash
# Detect the domain of a text
tarjoman route "The court hereby declares..."
# → Domain: legal (Confidence: 74.0%)
```

---

## Python API

```python
from tarjoman.core.pipeline import TranslationPipeline
from tarjoman.domains.router import DomainRouter
from tarjoman.stages.humanizer import PersianHumanizer
from tarjoman.stages.anti_calque import AntiCalqueEngine

# 1. Route to the correct domain
router = DomainRouter()
profile, confidence = router.route(
    "The cellular membrane exhibits selective permeability..."
)

# 2. Run the 5-pass translation pipeline
pipeline = TranslationPipeline()
segments, audit = pipeline.run(
    raw_text="The cellular membrane exhibits selective permeability...",
    profile=profile,
)

# 3. Access translation results
for seg in segments:
    print(seg.translated_text)

print(f"MQM Score: {audit.quality_score:.1f}")
critical = [f for f in audit.findings if f.severity == "critical"]
print(f"Critical findings: {len(critical)}")

# 4. Humanize existing Persian text (strip AI artifacts)
humanized = PersianHumanizer.humanize(
    "این موضوع دارای اهمیت ویژه‌ای می‌باشد.",
    register="formal-human",
)
# → "این موضوع دارای اهمیت ویژه‌ای است."

# 5. Detect calques in Persian text
calques = AntiCalqueEngine.detect_calques("او نقش مهمی بازی می‌کند.")
# → ["نقش مهمی بازی می‌کند"]
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

**Unit Tests**: 495 passing (`unittest` CI suite) / 519 passing (`pytest`)

```bash
python -m unittest discover -s tests -p "test_*.py"
pytest  # Also collects standalone test_* functions
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
├── glossaries/            # Curated domain starter glossaries (.tsv) & loader
├── memory/                # Long-form book support
│   ├── cache.py           # SHA-256 chunk caching
│   ├── character_bible.py # Character & Style Bible
│   ├── consistency.py     # Cross-chapter term/name/register checks
│   ├── context_builder.py # Smart chunk-relevant book context builder
│   ├── fidelity.py        # Completeness checks (verify)
│   ├── manifest.py        # Book manifest management
│   ├── scene_continuity.py# Scene Continuity Tracker
│   ├── state_manager.py   # Project termbase & voice ledger
│   └── termbase.py        # Dynamic terminology extraction (SQLite)
├── parsers/               # Input parsers & preprocessors
│   ├── epub_parser.py     # EPUB structure parser
│   ├── epub_workflow.py   # EPUB extract/merge marker workflow
│   ├── i18n.py            # Localization checker (JSON/ARB/PO/YAML)
│   ├── srt.py             # Subtitle (SRT & WebVTT) extract, merge & check
│   ├── term_candidates.py # Recurring name/term candidate extractor
│   └── text_prep.py       # PDF-extracted text cleaner
├── fixer.py               # Safe orthography-only auto-fixer
├── installer.py           # Multi-platform skill & MCP installer
├── linter.py              # Persian linguistic & typography linter (style/severity/JSON)
├── mcp_server.py          # Zero-dependency stdio JSON-RPC 2.0 MCP server
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

**Acknowledgements**: some ideas were adapted from Kaman AI Translator, «لحن من» (lahne-man), hermes-literary-translation-mastery, Paknevis and SubFarsiPro. See [docs/CREDITS.md](docs/CREDITS.md).

---

<div align="center">

*Built with obsessive attention to Persian linguistic purity.*

**[Tarjoman](https://github.com/Erfix404/tarjoman)** · Created by [Erfan Ashouri (@Erfix404)](https://github.com/Erfix404)

</div>
