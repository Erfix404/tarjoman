# Tarjoman Research Index

**Research date:** 2026-09-21  
**Purpose:** evidence used to design TARJOMAN-A0-PROD-2.  
**Rule:** these files explain why decisions were made; `ARCHITECTURE_ZERO.md` is normative.

## Files

1. `01-baseline-audit.md` — current fork code/test/documentation audit.
2. `02-translation-landscape.md` — reflection agents, CAT/TM, local MT, document/subtitle systems.
3. `03-persian-quality.md` — Persian normalization, register, terminology, anti-calque engineering.
4. `04-evaluation.md` — independent metrics, COMET/XCOMET, golden corpus, human MQM.
5. `05-audio-meeting-notes.md` — meeting/lecture transcription systems and Persian-first candidates.
6. `06-agent-interop.md` — MCP/A2A and agent-facing architecture.
7. `07-feature-matrix.md` — capability comparison and resulting priorities.
8. `08-persian-tts.md` — deep audit of nimaone/persian_tts and current Persian TTS candidates.
9. `09-engineering-guardrails.md` — implementation constraints for coding agents.
10. `source-register.md` — source URLs and code-reuse/license cautions.

## Research method

- inspected fork source tree and key implementation/tests,
- inspected upstream/public repositories and current documentation,
- compared architectural patterns rather than copying implementation,
- treated vendor/project marketing claims as leads, not proof,
- preferred independently testable design rules.

## Important uncertainty

The exact “voice meeting → Persian notes” project remembered by the owner cannot be proven from the description alone. Research found several strong candidates, especially Persian-first NeurAI, Persian STT Pipeline, Persian Meeting Assistant, and the commercial Orca transcription flow. The architecture therefore adopts the useful patterns without assuming one is the exact remembered project.
