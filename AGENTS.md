# AGENTS.md — Tarjoman implementation contract

This file is the short execution contract for coding agents. It cannot override `ARCHITECTURE_ZERO.md`, accepted ADRs, or `ROADMAP.md`.

## Current state

- Architecture: `TARJOMAN-A0-PROD-3`
- Roadmap: `TARJOMAN-RM-3`
- Status: `FROZEN_IMPLEMENTATION`
- Production implementation is authorized only through READY Work Packages and their dependency gates.

## Frozen baseline

- Owner-approved candidate SHA: `bc43c1bb8b0bf6986d4353766591278a1f0b91a3`
- The exact architecture freeze commit is recorded in `ARCHITECTURE_MANIFEST.json`.
- Do not reinterpret or silently amend Architecture Zero; use ADRs for architecture changes.

## Before every coding task

1. Read `ARCHITECTURE_ZERO.md`.
2. Read accepted ADRs in `docs/adr/`.
3. Find the exact Work Package in `WORKPACKAGES.json` and `ROADMAP.md`.
4. Confirm every `depends_on` package is DONE.
5. Read relevant `research/` and `review/` evidence.
6. Inspect current code/tests before editing.

## Scope law

A task must name exactly one Work Package ID unless the roadmap explicitly couples packages.

Implement only:
- the package deliverable,
- its acceptance criteria,
- tests/docs/migration directly required to satisfy them.

Do not perform unrelated refactors.

## Stop and propose ADR when

The implementation would change:
- public API/schema/status vocabulary,
- DB/storage model or migration semantics,
- cache/TM identity,
- security/privacy/network boundary,
- model/license policy,
- provider fallback semantics,
- core language/runtime,
- persistence service/topology,
- architecture-layer dependencies.

Do not guess through these.

## Mandatory invariants

- Core/Application contain no concrete provider/network/UI/server implementation.
- Heavy speech/eval/server dependencies stay optional.
- No silent model/cloud/language/quality fallback.
- Result Cache != Translation Memory.
- Public job states are exactly: QUEUED, RUNNING, WAITING_REVIEW, SUCCEEDED, FAILED, CANCELLED.
- Source/protected structure is fail-closed.
- Large binary artifacts are not SQLite BLOBs.
- `local_only` means no unapproved network egress.
- Unknown/non-eligible model licenses do not pass automatically.
- No `shell=True` for production external processes.
- No raw source/audio/secrets in normal logs.
- Runtime evaluation never mutates the candidate it scores.
- No feature/flag is documented before executable tests prove it exists.

## PR evidence

Every PR must state:
- Work Package ID,
- dependencies verified,
- files changed,
- architecture decisions touched,
- tests/commands run,
- migration/schema impact,
- dependency/license impact,
- benchmark/eval impact,
- known limitations,
- acceptance criteria checklist.

## Definition of DONE

A Work Package is DONE only when every acceptance item in `WORKPACKAGES.json` has evidence and review verifies no architecture violation.
