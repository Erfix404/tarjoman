# Translation Evaluation Research

## Problem with the current benchmark

The baseline benchmark can run with EchoDraftBackend and still pass its internal audit. Therefore it validates pipeline mechanics, not translation quality.

The new system separates:
- mechanics,
- constraints,
- translation quality,
- human preference.

## COMET / XCOMET

Sources:
- https://github.com/Unbabel/COMET
- https://unbabel.github.io/COMET/

COMET provides learned machine-translation evaluation. Current project documentation also describes:
- reference-based scoring,
- reference-free quality estimation,
- XCOMET error spans with minor/major/critical labels,
- DocCOMET/document context support,
- system comparison/statistical testing.

Persian is among languages represented by the underlying multilingual model family, but every chosen model/license must be verified before packaging.

### Use in Tarjoman
COMET is an optional heavy eval dependency, never a runtime requirement for normal translation.

Use cases:
- nightly/manual benchmark,
- provider/model bake-off,
- release candidate quality report,
- document-level evaluation experiment.

## chrF++ / SacreBLEU

Use as reproducible lexical metrics when reference translations exist. Do not use BLEU alone as the product quality definition; literary/contextual improvements can be poorly captured by sentence-level overlap.

## MQM-style human review

Human evaluation is needed for:
- adequacy/meaning,
- omission/addition,
- terminology,
- fluency,
- grammar,
- style/register,
- locale conventions,
- critical domain errors.

Severity:
- critical,
- major,
- minor.

For high-risk domains, release evaluation should oversample numbers, obligations, drug/dose terms, negation, and conditionals.

## LLM-as-judge

Allowed only as a secondary signal.

Rules:
- judge prompt/version stored,
- preferably different model/provider from generator for important experiments,
- source + candidate + rubric shown,
- blind model labels when comparing providers,
- never replace hard invariants or human RC review.

## Golden corpus design

Directory concept:

~~~text
evals/golden/
  general/
  literary/
  scientific/
  philosophy/
  legal/
  technical/
  medical/
  media/
  financial/
  classical/
  transcreation/
  subtitles/
  meetings/
  lectures/
  adversarial/
~~~

Each case stores:
- source,
- optional human reference(s),
- required terms,
- forbidden/allowed variants,
- protected spans,
- metadata/domain/register,
- expected invariant checks,
- provenance/license.

## Metrics report

A benchmark run should output JSON + Markdown with:
- corpus version,
- provider/model,
- prompt/profile versions,
- cost/tokens,
- latency,
- exact constraint pass rates,
- chrF/BLEU if applicable,
- COMET/XCOMET if enabled,
- MQM finding counts,
- human review status,
- failures by domain.

## Regression policy

Prefer **non-regression against a frozen baseline** to an arbitrary universal score.

When comparing two systems on adequate sample sizes, use paired/statistical comparison rather than declaring a winner from a tiny score difference.

## Naming policy

Current `AuditReport.quality_score` should be renamed/reframed to something like `constraint_score` or removed from marketing. It does not measure full semantic translation quality.
