# Competitive Feature Matrix and Priorities

Legend:
- ✅ strong/present in referenced pattern
- ◐ partial/varies
- — not a core focus
- **P0/P1/P2** = Tarjoman implementation priority

| Capability | Baseline Tarjoman | Translation Agent | OmegaT/CAT pattern | DocuTranslate pattern | Meetily/NeurAI pattern | Tarjoman target |
|---|---:|---:|---:|---:|---:|---|
| Real provider backend | — | ✅ | external MT | ✅ | ✅ | **P0** |
| Reflection/revision | ◐ rules | ✅ | — | ◐ | ◐ | **P0** |
| Persian-specific quality | ✅ concept | — | locale-dependent | — | ✅ in NeurAI | **P0 moat** |
| Translation memory | ◐ JSON cache | — | ✅ | ◐ | — | **P0/P1** |
| Glossary/termbase | ◐ TSV | ✅ idea | ✅ | ✅ | — | **P0** |
| Fuzzy/context reuse | — | ◐ | ✅ | ◐ | — | **P1** |
| Document-level context | ◐ | ✅ | ✅ project | ✅ | ✅ | **P0** |
| Independent MT metrics | — | BLEU experiments | — | — | domain evals vary | **P0** |
| Human review workflow | — | — | ✅ | ◐ | ◐ | **P1** |
| Format preservation | output-only | — | ✅ | ✅ | exports | **P1** |
| Subtitles | — | — | plugins | some | some | **P1** |
| Audio transcription | — | — | — | — | ✅ | **P1** |
| Persian TTS | — | — | — | — | adjacent pattern | **P1 optional profile** |
| Voice cloning | — | — | — | — | ✅ in speech tools | **P1, consent + license gated** |
| Pronunciation/G2P lexicon | — | — | glossary only | — | varies | **P1 TTS moat** |
| Model license gate | — | — | — | — | varies | **P0 platform rule** |
| Meeting/lecture notes | — | — | — | — | ✅ | **P1** |
| Local-only mode | core can be local | depends model | ✅ | ✅ | ✅ | **P0 policy** |
| REST API | — | library | — | ✅ | ✅ | **P1** |
| MCP | prompt skills only | — | — | ✅ optional | skills | **P1** |
| A2A | — | — | — | — | — | **P2 optional** |
| Provenance | limited | limited | project history | ◐ | ◐ | **P0** |
| Resumable jobs | ◐ cache | — | ✅ project | ◐ | ✅ | **P0** |
| Typed migrations | — | — | project formats | varies | ✅ examples | **P0** |
| Privacy enforcement | — | provider-dependent | local | configurable | ✅ | **P0** |

## Highest-value differentiators

### 1. Persian quality that is measurable
Not just “uses a good LLM”. Tarjoman owns Persian normalization, terminology, register, RTL structure, and a regression corpus.

### 2. Professional continuity
TM + glossary + project context mean chapter 30 sounds like chapter 1 and a recurring technical term stays consistent.

### 3. One artifact engine for text + speech
The same quality/evaluation/publishing pipeline can turn:
- English article → Persian article,
- book → consistent translation project,
- meeting audio → formal Persian minutes,
- lecture audio → structured notes,
- video → bilingual subtitles.

### 4. Agent-first without agent lock-in
CLI/Python remain deterministic; MCP makes the same capabilities discoverable to agents.

### 5. Honest trust layer
Every output carries provenance and quality findings. Format limitations and model uncertainty are explicit.

## Features deliberately not prioritized early

- autonomous web research inside every translation,
- multi-agent swarm as mandatory translation strategy,
- exact PDF layout reconstruction,
- large multi-tenant SaaS control plane,
- desktop app,
- custom model training.

These are expensive and do not strengthen the core moat before quality/data contracts are stable.
