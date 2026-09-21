# Persian Quality Engineering Research

## Why Persian needs its own quality layer

English→Persian quality errors are not limited to lexical translation. Production output must control:

- Arabic vs Persian Yeh/Kaf variants,
- ZWNJ/half-space,
- punctuation and quote direction,
- RTL/LTR mixing,
- digits by domain,
- Ezafe and compound forms,
- spoken vs written register,
- calques from English syntax,
- names/transliteration consistency,
- technical English terms inside Persian,
- formal/informal pronouns and verbs,
- dialogue rhythm,
- code/math/identifier isolation.

## Existing Persian NLP/tooling

### Hazm
Source: https://github.com/roshan-research/hazm

Provides normalization, tokenization, lemmatization, POS/dependency tools, embeddings/corpora helpers.

Use: optional NLP adapter and reference behavior, not a mandatory core dependency.

### DadmaTools
Source: https://github.com/Dadmatech/DadmaTools

Provides Persian normalization, POS/dependency processing, spell checking, informal→formal and other NLP tasks.

Use: evaluate specifically for formalization/spell/NLP assistance.

### Parsivar
Source: https://github.com/ICTRC/Parsivar

Provides normalization, half-space correction, tokenization, stemming, POS/shallow/dependency parsing, spell checking.

Use: comparison adapter; pin/version if adopted.

### Virastar family
Sources:
- https://github.com/aziz/virastar
- Python/other ports exist.

Strong deterministic Persian typography rules inspired many cleaners: character normalization, punctuation spacing, ZWNJ and digit behavior.

Use: differential tests and rule inspiration; do not blindly port code without license/behavior review.

## Engineering split required

### 1. Normalizer
Pure/deterministic, idempotent where possible.

Examples:
- `ي → ی`
- `ك → ک`
- duplicate spaces
- punctuation spacing
- controlled ZWNJ
- profile-driven digits

Tests should prove:
`normalize(normalize(x)) == normalize(x)` for the supported rule set whenever practical.

### 2. Linter
Finds suspicious patterns and produces typed findings.

Examples:
- calque candidates,
- unbalanced quotes,
- stray Arabic characters,
- untranslated fragments,
- inconsistent term forms,
- RTL/LTR hazards.

### 3. Semantic reviewer
Uses document context and/or a model to propose meaning-preserving rewrites.

This is where calque cleanup belongs when substitution is not mechanically safe.

## Anti-calque policy

The current repository's anti-calque ambition is valuable but unconditional regex semantic transformations are too dangerous for production.

New severity model:
- `safe_autofix` — mechanical and semantics-neutral,
- `warning` — likely issue, human/model review,
- `error` — hard policy violation,
- `semantic_review` — needs context before rewriting.

A rule must include:
- rule ID,
- explanation,
- examples/counterexamples,
- domain applicability,
- severity,
- auto-fix safety,
- tests including false-positive cases.

## Style system

A “domain” is not enough. Separate dimensions:

### Domain
legal, medical, scientific, technical, literary, etc.

### Register
formal, neutral, conversational, literary, classical.

### Audience
general, specialist, student, patient/user-facing, executive.

### Localization
Iranian Persian is default; Dari/Tajik are future explicit profiles rather than accidental variation.

### Preservation policy
names, brands, code, math, units, references, English technical terms, digits.

Style profiles should be data files with schema/version validation.

## Spoken → written Persian

For ASR/meeting/lecture mode:
- keep raw transcript immutable,
- create a cleaned transcript as a derived artifact,
- create formalized written Persian as another derived artifact,
- summaries/notes cite raw/clean segment IDs.

This preserves evidence while allowing polished output.

## Persian-specific eval cases

Golden set must contain:
- `می رود / می‌رود` patterns,
- plural/possessive suffixes,
- Ezafe variants,
- mixed LTR code and URLs,
- English acronyms,
- Persian/Arabic digits,
- dates and currency,
- colloquial→formal samples,
- dialogue,
- ambiguous “توسط” cases,
- phrases that look like calques but are legitimate,
- technical loanwords with approved glossary forms.

## Recommendation

Treat Persian quality as a **versioned compiler/linter subsystem** with clear invariants, not an unbounded list of regex replacements.
