# Tarjoman Repository Polish Report (v2.3.0)

**Date**: 2026-09-24
**Branch**: `main`
**Version**: v2.3.0 (commit `49cc49b`)
**Skill used**: `codebase-design`

---

## 1. What Was Done

### 1.1 `pyproject.toml` — Package Metadata Updated

- `authors` → `Erfan Ashouri <ashorierfan66@gmail.com>`
- `maintainers` → `Erfan Ashouri (@Erfix404) <ashorierfan66@gmail.com>`
- `description` → "Autonomous Persian Translation & Publishing Super-Skill for AI Agents"
- Added 12-element `keywords` list (translation, persian, farsi, agent, claude-code, hermes-agent, anti-calque, epub, typst, bilingual, humanizer, natural-language)
- Added 13 standard `classifiers` (Production/Stable, MIT, Python 3.10-3.12, Persian Natural Language, AI, i18n, Linguistic)
- Added `[project.urls]` with Homepage, Repository, Issues, Author pointing to `github.com/Erfix404/tarjoman`

### 1.2 `README.md` — Complete Revamp (Professional Showcase)

Old README (stale: "96 Passing", old description) replaced with a modern showcase:

- **Header**: `# 🏛️ Tarjoman (موتور جامع ترجمه و نشر «ترجمان»)` + tagline + 9 centered Shields.io badges (version, license, Python, 343 tests, 10/10 benchmarks, creator, multi-agent, zero-em-dash, EPUB3+Typst)
- **Bilingual executive summary** (English + natural elegant Persian)
- **Core Problem & Value Proposition** (calques table, AI-slop, orthography, amnesia, bidi corruption)
- **8 Core Architectural Pillars** (5-pass pipeline ASCII diagram, anti-calque Najafi/Guilani, T1-T18 humanizer table, zero-em-dash, 10 domains table, dual-level terminology, book continuity, 4 composers)
- **Multi-Agent Super-Skill Integration** (Claude Code, Hermes `skill_view`, Cursor `.cursorrules`)
- **Installation** (`pip install -e .`, optional `[pdf]`, `[dev]` extras)
- **Quickstart & CLI Guide** (translate, book init/translate/status, epub roundtrip, lint/audit, compose typst/html/epub/markdown, route)
- **Python API snippet** (runnable: DomainRouter → DomainRegistry → TranslationPipeline → PersianHumanizer → AntiCalqueEngine)
- **Benchmarks table** (10 domains, all PASS) + test count
- **Creator card** for Erfan Ashouri (عرفان عاشوری) with GitHub avatar link
- **Contributing & License** (CONTRIBUTING.md + MIT links)

API signatures were verified against the actual code before documenting:
- `DomainRouter.route(text)` → domain type; `DomainRegistry.get_profile(domain_type)`
- `TranslationPipeline().run(raw_text, profile)` → `(segments, audit_report)`; `seg.translated_text`; `audit.score`
- `PersianHumanizer.humanize(text, register="formal-human")` (classmethod)
- `AntiCalqueEngine.detect_calques(text)` (classmethod → `List[str]`)

### 1.3 Root Directory Cleanup

- Created `docs/reports/`
- Moved `.claude_humanizer_report.md` → `docs/reports/v2.3.0_humanizer_report.md`
- Repo root now contains only standard files (`README.md`, `CONTRIBUTING.md`, `LICENSE`, `pyproject.toml`, `AGENTS.md`, `.cursorrules`, source dirs)

## 2. Verification Evidence

### Tests
```
.venv/bin/pytest → 343 passed, 15 warnings (pre-existing Click deprecation warnings only), 0 failures
```

### Benchmarks
```
.venv/bin/python benchmarks/run_benchmarks.py → All 10 Domain Verification Benchmarks PASSED (10/10), all scores 100.0, 0.60s
```

## 3. Notes / Deviations

- CLI subcommand names taken from the actual `tarjoman/cli.py` dispatch (`book`, `epub`, `compose`, `lint`, `audit`, `translate`, `route`, `scene`). The compose examples show the real composer set (typst, html, epub, markdown) per the `composers/` directory.
- The existing README already had solid content; the revamp refreshed stale data (96 → 343 tests), restructured to the required 8-pillar format, added bilingual summary, creator card, and verified API examples.
- Benchmark scores in README are stated as "≥ 90.0" thresholds; actual run achieved 100.0 across all domains.
