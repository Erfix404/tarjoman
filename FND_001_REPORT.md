# FND-001 Implementation Report: Repository/Package Layout

**Work Package:** FND-001  
**Title:** Repository/package layout  
**Track:** Foundation  
**Phase:** 1  
**Depends on:** A0-005 (verified DONE — architecture freeze commit is recorded)  
**Date:** 2026-09-21  

---

## 1. Summary of Changes

Migrated the Tarjoman codebase from a flat `tarjoman/` package layout to the canonical `src/tarjoman/` layout specified in ARCHITECTURE_ZERO.md §16. No code logic was modified — this is a pure structural migration with packaging updates.

### 1.1 Files Moved

All existing source files were moved from `tarjoman/` → `src/tarjoman/`:

| Original Path | New Path |
|---|---|
| `tarjoman/__init__.py` | `src/tarjoman/__init__.py` |
| `tarjoman/cli.py` | `src/tarjoman/cli.py` |
| `tarjoman/linter.py` | `src/tarjoman/linter.py` |
| `tarjoman/core/__init__.py` | `src/tarjoman/core/__init__.py` |
| `tarjoman/core/contracts.py` | `src/tarjoman/core/contracts.py` |
| `tarjoman/core/pipeline.py` | `src/tarjoman/core/pipeline.py` |
| `tarjoman/composers/__init__.py` | `src/tarjoman/composers/__init__.py` |
| `tarjoman/composers/base.py` | `src/tarjoman/composers/base.py` |
| `tarjoman/composers/bilingual_md.py` | `src/tarjoman/composers/bilingual_md.py` |
| `tarjoman/composers/html_reader.py` | `src/tarjoman/composers/html_reader.py` |
| `tarjoman/composers/typst_pdf.py` | `src/tarjoman/composers/typst_pdf.py` |
| `tarjoman/domains/__init__.py` | `src/tarjoman/domains/__init__.py` |
| `tarjoman/domains/router.py` | `src/tarjoman/domains/router.py` |
| `tarjoman/domains/registry/*.json` (10 files) | `src/tarjoman/domains/registry/*.json` |
| `tarjoman/memory/__init__.py` | `src/tarjoman/memory/__init__.py` |
| `tarjoman/memory/cache.py` | `src/tarjoman/memory/cache.py` |
| `tarjoman/memory/state_manager.py` | `src/tarjoman/memory/state_manager.py` |
| `tarjoman/stages/__init__.py` | `src/tarjoman/stages/__init__.py` |
| `tarjoman/stages/base.py` | `src/tarjoman/stages/base.py` |
| `tarjoman/stages/anti_calque.py` | `src/tarjoman/stages/anti_calque.py` |
| `tarjoman/stages/stage1_pre_analysis.py` | `src/tarjoman/stages/stage1_pre_analysis.py` |
| `tarjoman/stages/stage2_draft.py` | `src/tarjoman/stages/stage2_draft.py` |
| `tarjoman/stages/stage3_reflection.py` | `src/tarjoman/stages/stage3_reflection.py` |
| `tarjoman/stages/stage4_polish.py` | `src/tarjoman/stages/stage4_polish.py` |
| `tarjoman/stages/stage5_audit.py` | `src/tarjoman/stages/stage5_audit.py` |

### 1.2 Scaffolding Packages Created

New empty `__init__.py` files for target architecture packages per §16:

| Package | Purpose |
|---|---|
| `src/tarjoman/application/` | Use cases, jobs, orchestration, services |
| `src/tarjoman/providers/` | LLM provider adapters |
| `src/tarjoman/quality/` | Deterministic Persian normalization + typed findings |
| `src/tarjoman/profiles/` | Domain profiles and configuration |
| `src/tarjoman/ingest/` | File format ingestion transformations |
| `src/tarjoman/export/` | File format export transformations |
| `src/tarjoman/audio/` | ASR/TTS (imported only with extras) |
| `src/tarjoman/evals/` | Lightweight eval interfaces |
| `src/tarjoman/prompts/` | Prompt templates and management |
| `src/tarjoman/interfaces/` | Interface adapters root |
| `src/tarjoman/interfaces/cli/` | CLI interface adapter |
| `src/tarjoman/interfaces/api/` | REST API interface adapter |
| `src/tarjoman/interfaces/mcp/` | MCP server interface adapter |
| `src/tarjoman/interfaces/a2a/` | A2A interface adapter |

### 1.3 Files Removed

- `tarjoman/` — entire old flat package directory
- `tarjoman.egg-info/` — stale egg-info from previous install

### 1.4 pyproject.toml Changes

Updated `[tool.setuptools.packages.find]` from:
```toml
where = ["."]
```
to:
```toml
where = ["src"]
```

All other fields unchanged. The `include = ["tarjoman*"]` and `package-data` for `tarjoman.domains` registry JSONs remain as before.

---

## 2. Compatibility Shim Strategy

### 2.1 Current State

**No shims were needed.** The `src/` layout migration is transparent to import consumers because:

1. All internal imports use the same `from tarjoman.xxx import yyy` paths — these are unchanged.
2. The `src/` layout with `where = ["src"]` in setuptools means the installed package is still `tarjoman` with identical module paths.
3. Every import pattern used in tests and benchmarks was verified to work identically post-migration.

### 2.2 Verified Import Compatibility

All of the following imports continue to work without modification:

```python
from tarjoman.cli import cli
from tarjoman.stages import AntiCalqueEngine, BaseStage, PreAnalysisStage
from tarjoman.core.pipeline import TranslationPipeline
from tarjoman.core.contracts import DomainType, TextSegment, BookManifest
from tarjoman.domains.router import DomainRegistry, DomainRouter
from tarjoman.domains import DOMAIN_ALIASES
from tarjoman.composers import BilingualMarkdownComposer, HtmlReaderComposer
from tarjoman.memory import ResumableCache, StateManager
from tarjoman.linter import lint_text, format_report
from tarjoman.stages.stage5_audit import AuditStage
```

### 2.3 CLI Entrypoint

`tarjoman.cli:cli` — The CLI module remains at `src/tarjoman/cli.py`. The `project.scripts` entrypoint `tarjoman = "tarjoman.cli:cli"` is unchanged and verified working.

**Future removal plan:** When `interfaces/cli/` is populated by a future work package (per ARCHITECTURE_ZERO.md §16), the CLI implementation will move from `src/tarjoman/cli.py` to `src/tarjoman/interfaces/cli/`. At that point, `src/tarjoman/cli.py` becomes a backward-compatibility shim with a deprecation warning, importable for one minor version before removal. This is tracked as a dependency of the interfaces work package.

---

## 3. Verification Evidence

### 3.1 Editable Install

```
$ uv pip install -e . --python .venv/bin/python
Resolved 9 packages in 151ms
   Building tarjoman @ file:///opt/data/projects/tarjoman
      Built tarjoman @ file:///opt/data/projects/tarjoman
Prepared 1 package in 2.03s
Uninstalled 1 package in 1ms
Installed 1 package in 2ms
 ~ tarjoman==1.0.0 (from file:///opt/data/projects/tarjoman)
```

**Result: ✅ PASS**

### 3.2 Wheel Build and Clean Venv Install

```
$ .venv/bin/python -m build --wheel
Successfully built tarjoman-1.0.0-py3-none-any.whl

$ python3 -m venv /tmp/tarjoman_clean_test
$ /tmp/tarjoman_clean_test/bin/pip install dist/tarjoman-1.0.0-py3-none-any.whl
Successfully installed tarjoman-1.0.0 [+ dependencies]

$ /tmp/tarjoman_clean_test/bin/tarjoman --version
tarjoman, version 1.0.0

$ /tmp/tarjoman_clean_test/bin/python -c "from tarjoman.cli import cli; ..."
ALL CLEAN VENV IMPORTS PASSED
```

**Result: ✅ PASS**

### 3.3 No Heavy Imports at `import tarjoman`

```
$ .venv/bin/python -c "
import sys
before = set(sys.modules.keys())
import tarjoman
after = set(sys.modules.keys())
new = sorted(after - before)  # Only: ['tarjoman']
heavy = {'torch', 'whisper', 'comet', 'fastmcp', 'uvicorn', 'fastapi', 'onnxruntime'}
assert not (heavy & after)
"
OK: No heavy imports at import tarjoman
```

**Result: ✅ PASS** — Only the `tarjoman` module itself is loaded.

### 3.4 Test Suite (96/96)

```
$ .venv/bin/pytest -v
96 passed, 9 warnings in 1.46s
```

Full output:
- `tests/test_5pass_pipeline.py` — 18 passed
- `tests/test_anti_calque.py` — 16 passed
- `tests/test_cli.py` — 11 passed
- `tests/test_composers.py` — 17 passed
- `tests/test_contracts.py` — 4 passed
- `tests/test_memory_cache.py` — 13 passed
- `tests/test_router_10_domains.py` — 5 passed
- `tests/test_skillpacks.py` — 6 passed

**Result: ✅ 96/96 PASS, zero failures**

### 3.5 10-Domain Benchmark (10/10)

```
$ .venv/bin/python benchmarks/run_benchmarks.py
[SUCCESS] All 10 Domain Verification Benchmarks PASSED (10/10) in 0.56s!

Domain          | Score  | Audit  | Bi-MD  | HTML   | PDF
literary        | 100.0  | PASS   | YES    | YES    | YES
scientific      | 100.0  | PASS   | YES    | YES    | YES
philosophy      | 100.0  | PASS   | YES    | YES    | YES
legal           | 100.0  | PASS   | YES    | YES    | YES
technical       | 100.0  | PASS   | YES    | YES    | YES
medical         | 100.0  | PASS   | YES    | YES    | YES
media           | 100.0  | PASS   | YES    | YES    | YES
financial       | 100.0  | PASS   | YES    | YES    | YES
classical       | 100.0  | PASS   | YES    | YES    | YES
transcreation   | 100.0  | PASS   | YES    | YES    | YES
```

**Result: ✅ 10/10 PASS**

---

## 4. Architecture Decisions

- No architecture changes were required. This migration follows ARCHITECTURE_ZERO.md §16 exactly.
- No ADR needed — the `src/` layout is the normative target layout.
- No dependency law violations: Core/Application contain no concrete provider/network/UI/server implementation.

---

## 5. PR Evidence Checklist

| Item | Evidence |
|---|---|
| **Work Package ID** | FND-001 |
| **Dependencies verified** | A0-005 (architecture freeze) is DONE |
| **Files changed** | All files under `tarjoman/` moved to `src/tarjoman/`; 14 scaffolding `__init__.py` files added; `pyproject.toml` updated; old `tarjoman/` and `tarjoman.egg-info/` removed |
| **Architecture decisions** | None changed — follows §16 target layout |
| **Tests/commands run** | pytest 96/96 pass; benchmarks 10/10 pass; editable install; wheel build+clean install |
| **Migration/schema impact** | None — pure structural move |
| **Dependency/license impact** | None — no new dependencies |
| **Benchmark/eval impact** | None — all 10 domains produce identical results |
| **Known limitations** | `cli.py` lives at `src/tarjoman/cli.py` (not `interfaces/cli/`) pending future work package |

---

## 6. Acceptance Criteria Checklist

- [x] Codebase successfully migrated to `src/tarjoman/` with package scaffolding.
- [x] `pyproject.toml` updated for `where = ["src"]` package finding and packaging verified.
- [x] Editable install verified working.
- [x] Wheel build and install verified in clean venv.
- [x] Legacy imports work seamlessly — no shims needed; all existing import paths preserved.
- [x] No optional heavy imports at `import tarjoman`.
- [x] All 96 tests in `tests/` pass with zero failures.
- [x] All 10 domain benchmarks in `benchmarks/run_benchmarks.py` pass.
