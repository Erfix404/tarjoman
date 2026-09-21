# Translation Systems Research

This file records design patterns worth adopting, not code to copy.

## 1. Andrew Ng — translation-agent

Source: https://github.com/andrewyng/translation-agent

Pattern:
1. initial LLM translation,
2. reflection/constructive critique,
3. revised translation.

Useful lessons:
- reflection is a valid strategy but should be a configurable strategy, not the only architecture,
- glossary and regional/style steering are first-class,
- long-form/document context matters,
- authors explicitly warn the project is experimental and that evaluation is difficult.

Tarjoman adoption:
- keep generate → critique → revise,
- separate generator and evaluator,
- record prompt/model versions,
- evaluate at document level as well as segment level.

## 2. OmegaT — professional CAT workflow

Source: https://github.com/omegat-org/omegat

Relevant capabilities:
- translation memory,
- fuzzy matches,
- glossary,
- search,
- reuse across updated projects.

Tarjoman adoption:
- a real TM and termbase are more important than adding more prompt text,
- support interoperable TMX/TBX/XLIFF paths,
- show/retrieve prior translations as context,
- preserve project history and reviewer decisions.

License note: OmegaT is GPLv3. Use architectural ideas/standards; do not copy GPL implementation into MIT code.

## 3. OmegaT AI plugin

Source: https://github.com/Nic-J/omegat-ai-plugin

Relevant patterns:
- glossary enforcement,
- surrounding context,
- document summary injected into requests,
- translation-memory cache,
- batch pre-translation,
- optional second QA pass,
- local Ollama + cloud providers.

Tarjoman adoption:
- project summary + neighboring context + TM retrieval,
- cache keyed by translation-relevant configuration,
- separate translator and QA model possible,
- batch pretranslation with resumable status.

## 4. LibreTranslate / Argos Translate

Sources:
- https://github.com/LibreTranslate/LibreTranslate
- https://github.com/argosopentech/argos-translate

Relevant patterns:
- self-hosted/offline translation service,
- simple stable API,
- language packages/local models,
- separation between API product and translation engine.

Tarjoman adoption:
- optional local/NMT adapter,
- never couple orchestration to a single LLM API,
- local-only project policy.

License caution:
- LibreTranslate is AGPLv3,
- Argos Translate states MIT/CC0 dual licensing.
Do not copy incompatible service code without review.

## 5. DocuTranslate

Source: https://github.com/xunbu/docutranslate

Relevant patterns:
- many file formats,
- auto glossary,
- concurrent LLM translation,
- REST/Web UI,
- MCP integration,
- explicit warning that PDF conversion may lose layout.

Tarjoman adoption:
- adapter model for file formats,
- async bounded concurrency,
- honest format-fidelity guarantees,
- MCP as optional interface.

## 6. Formatted document translation

Source: https://github.com/kukas/document-translation

Important idea:
formatted documents need extraction of translatable text and reinsertion/alignment of markup. Sending raw document markup to an LLM is not a reliable fidelity strategy.

Tarjoman adoption:
- canonical IR with inline protected/structural spans,
- format-specific exporter owns reinsertion,
- fidelity tests per format.

## 7. Subtitle translation systems

Sources:
- https://github.com/machinewrapped/llm-subtrans
- https://github.com/rockbenben/subtitle-translator

Relevant patterns:
- structural separation keeps timecodes/cue IDs away from the model,
- neighboring cues improve dialogue coherence,
- bilingual outputs,
- local cache,
- transcription + speaker context can improve translation.

Tarjoman adoption:
- subtitle adapter in early format phase,
- timecodes as exact protected structure,
- configurable context window,
- bilingual review export.

## 8. Traditional NMT and speech translation

Useful optional backends include NLLB/Marian/Argos-like services and speech translation systems such as SeamlessM4T. They are valuable for offline/fallback/bake-off scenarios but should not be embedded into the lightweight core.

## Synthesis

The strongest production architecture is not “five prompts in a row”. It combines:

**CAT discipline** (TM/glossary/versioning/review)  
+ **LLM flexibility** (context/style/reflection)  
+ **deterministic structure protection**  
+ **provider neutrality**  
+ **independent evaluation**.

That is the design adopted in Architecture Zero.
