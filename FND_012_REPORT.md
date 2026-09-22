# FND-012 — Architecture-conformance CI (Phase 1 close-out)

**Work Package:** FND-012 — Architecture-conformance CI
**Branch:** `phase/1-foundation`
**Architecture:** TARJOMAN-A0-PROD-3 · Roadmap TARJOMAN-RM-3 · Status FROZEN_IMPLEMENTATION
**Dependencies verified:** FND-001, FND-002, FND-003, FND-004, FND-005, FND-006, FND-007, FND-008, FND-009, FND-010, FND-011 — all DONE in WORKPACKAGES.json
**Date:** 2026-09-22

## Scope

Exactly one Work Package (FND-012). Deliverable: architecture-conformance CI —
clean base install without speech/eval/server extras, and CI-failing
import-boundary checks. No unrelated refactors, no architecture changes, no ADR
required (no public API/schema/storage/security/model/provider/runtime change).

## Files changed

- `pyproject.toml` — base deps pinned to exactly `pydantic`, `click`, `jinja2`,
  `packaging`; extras structured as orthogonal groups `pdf`, `server`,
  `speech`, `eval`, `dev`, `all` (added `packaging`, `server`, `speech`,
  `eval`, `all`).
- `src/tarjoman/quality/conformance.py` — NEW. `ArchitectureConformanceChecker`
  (stdlib-only): `ast`-based import scan of `src/tarjoman/`, SQL migration
  scan, secret-structure/redaction scan. Rules: `RULE_CORE_ISOLATION`,
  `RULE_INTERFACE_ISOLATION`, `RULE_NO_HEAVY_BASE_IMPORTS`,
  `RULE_DATABASE_INVARIANTS`, `RULE_SECRET_REDACTION`, plus
  `RULE_LAYER_DIRECTION` (application/adapter direction). `check()` returns
  `List[ArchitectureViolation]` (rule, file, line, message);
  `enforce()` raises `ArchitectureViolationError`; `check_snippet()` checks
  in-memory sources for tests. Lazy (function-level) extra imports are legal;
  only module top-level heavy imports fail.
- `src/tarjoman/quality/__init__.py` — exposes checker, violation types,
  rule IDs, `format_report`.
- `tests/test_architecture_conformance.py` — NEW. 24 tests + 9 subtests:
  clean base import in isolated subprocesses with extras blocked
  (`sys.modules[name] = None`), in-process blocked-import test, <200ms
  top-package import, no heavy module loaded, minimal base-deps assertion,
  checker passes on clean tree, synthetic violations per rule (core/fastapi,
  core/torch, core/storage, cli→api, BLOB SQL, quality/onnxruntime,
  secret literal, application/storage), lazy-import allowed, negative-control
  diagnostics, §22.2 ownership tests (no network/DB in core contracts,
  canonical D38 job vocabulary incl. jobs CHECK constraint, no BLOB in shipped
  migrations, redaction structure), rule-set coverage.
- `.github/workflows/test.yml` — triggers extended to `push: [main,
  phase/**]` + all PRs to `main`; new `architecture-conformance` job
  (4-python matrix): `pip install -e .` WITHOUT extras → clean-import probe
  → `pytest tests/test_architecture_conformance.py` → full unittest suite →
  benchmark suite. Existing `test` job unchanged.
- `WORKPACKAGES.json` — FND-012 status READY → DONE.
- `FND_012_REPORT.md` — this report.

## Architecture decisions touched

None. All rules encode frozen decisions D03/D16/D19/D20/D38 (§22, §23.2,
§25.5, §47). One scoping note (documented, not a change): normative
base-core isolation covers `core.contracts/errors/config/logging`; the legacy
`core/pipeline.py` 5-pass wiring (imports `tarjoman.stages`) is out of scope
for `RULE_CORE_ISOLATION` pending its planned move to the application layer
under the TRN track — recorded here so CI intent is explicit.

## Tests / commands run

- `python3 -m pytest tests/test_architecture_conformance.py -q` → **24 passed, 9 subtests passed**
- `python3 -m pytest tests/ -q` → **529 passed** (505 pre-existing + 24 new), 124 subtests, 0 failures
- `python3 benchmarks/run_benchmarks.py` → **10/10 domain benchmarks PASSED**
- Negative control: injected `import fastapi` into a temp-tree copy of
  `core/errors.py` → `check()` reports `RULE_CORE_ISOLATION` + `enforce()`
  raises (verified before writing report; tree copy discarded).
- Cold `import tarjoman` ≈ 1.5ms (well under the 200ms budget).

## Migration / schema impact

None. Migration 001 untouched; checker read-verifies it (no BLOB, jobs CHECK
holds canonical states, FK/WAL/busy-timeout owned by `DatabaseManager`).

## Dependency / license impact

Base gains `packaging>=23.0` (already used by `profiles/registry.py`, now
declared). Heavy libs remain extras-only; no new runtime dependency, no model
or license-policy change.

## Benchmark / eval impact

None beyond gating: benchmarks pass unchanged (10/10).

## Known limitations

- Checker is static (`ast` + regex on SQL/strings); it cannot catch dynamic
  imports (`importlib.import_module` with computed names) — acceptable for the
  FND-012 CI gate; runtime capability errors (`CapabilityUnavailableError`)
  remain the backstop.
- `RedactionFilter`/error-pattern regexes are structural-checked (presence +
  wiring), not semantically fuzzed — covered by FND-011 tests.
- `typst` is imported lazily inside `composers/typst_pdf.py` (function level)
  and is therefore conformant; the checker explicitly permits this pattern.

## Acceptance criteria checklist

- [x] base job installs without speech/eval/server extras — `pip install -e .`
      without extras; isolated-subprocess tests prove `tarjoman`, `core`,
      `quality`, `storage`, `profiles` import with all heavy extras blocked;
      no heavy module in `sys.modules` after base import; import <200ms.
- [x] architecture violations fail CI — `architecture-conformance` job runs
      base-only install + conformance tests + full suite + benchmarks on
      `main`/`phase/**` pushes and PRs; synthetic violations for every rule
      fail with file/line diagnostics; negative control verified.
- [x] All 505 existing tests pass with zero failures (529 total incl. 24 new).
- [x] All 10 domain benchmarks pass.
- [x] Updated CI workflow covers phase branches and PRs.

## PR evidence (per AGENTS.md)

Work Package ID: FND-012 · dependencies verified above · files changed above ·
no architecture decisions changed · tests/commands above · no migration impact ·
dependency impact (`packaging` declared) · benchmarks 10/10 · limitations above.
