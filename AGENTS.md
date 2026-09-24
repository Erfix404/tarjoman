# AGENTS.md — Tarjoman Autonomous Translation & Publishing Super-Skill

## Mission
Tarjoman is an open-source, production-grade autonomous English-to-Persian translation and publishing super-skill for AI agents (Claude Code, Hermes Agent, Cursor).

## Core Directives
1. Zero Em-dash Guarantee: Never output foreign em-dashes (— or --); convert to Persian syntax, commas, or parentheses.
2. Anti-Calque Enforcement: Strictly apply Abolhassan Najafi & Ahmad Samii Gilani rules against syntactic/lexical calques.
3. Dual-Level Terminology: Support system-docs (keep developer terms English in LTR isolates) and journal (scholarly Persian).
4. Long-form Book Resumability: Character & Style Bible, Scene Continuity Tracker, and SHA-256 chunk caching.
5. Publishing Composers: W3C EPUB 3 RTL roundtrip and Typst PDF typesetting with Vazirmatn font.
6. Minimal Code Discipline: Shortest correct diffs, 100% test pass rate with pytest.
