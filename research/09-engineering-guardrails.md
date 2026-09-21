# Coding-Agent Engineering Guardrails

This research/engineering note explains failure patterns that Architecture Zero turns into mandatory rules.

## 1. Typical agent failure modes

### Architecture drift
An agent notices a local inconvenience and introduces a new DB/queue/framework.

Control:
no architecture-level dependency or boundary change without ADR.

### Dependency leakage
An optional speech/server library gets imported from package top-level and breaks lightweight installs.

Control:
base-install import test and import-boundary CI.

### Fake completion
A happy-path test passes while actual provider/model is mocked.

Control:
separate mechanics tests from real-quality scheduled evals; package exit criteria name both.

### Documentation hallucination
README gains flags not implemented by CLI.

Control:
doc examples have executable smoke tests; documentation truth audit before release.

### Cache corruption/staleness
Agent keys cache by source text but forgets glossary/model/context.

Control:
cache key contract is architecture-owned and tested.

### Silent fallback
Agent catches provider failure and changes model/cloud tier.

Control:
fallback only via explicit policy and provenance.

### Unsafe semantic cleanup
Agent adds regex that rewrites meaning.

Control:
safe autofix whitelist; semantic rules become findings/review.

### Format destruction
Agent gives raw XML/timecode/markup to LLM.

Control:
canonical IR + protected spans + per-format round-trip tests.

### Model-license mistake
Agent sees an MIT/Apache repository and assumes model weights/training data share it.

Control:
separate code/model/dataset lineage in ModelManifest; production license gate.

### Speech demo promoted to server
Local demo endpoint with upload/no auth becomes “production”.

Control:
server security baseline and persistent job/artifact store.

## 2. PR checklist for agents

Before coding:
- cite Work Package ID,
- identify current contracts,
- identify tests to add,
- identify optional dependency impact,
- check license manifests for any model/data.

Before merge:
- no architecture decision changed,
- tests success + failure path,
- no secret/source logging,
- docs reflect code,
- migration/compatibility considered,
- performance/eval measured if behavior changed,
- no unexplained TODO in acceptance scope.

## 3. Stop conditions

Agent must stop the specific package and propose ADR when:
- public schema/API must change incompatibly,
- a new persistent datastore/service is proposed,
- model/license status is unclear for production,
- security/privacy boundary changes,
- migration may lose data,
- cache semantics need to change,
- provider fallback semantics change,
- a new language/runtime becomes core.

## 4. Allowed implementation freedom without ADR

Agent may choose:
- private function names,
- internal helper decomposition,
- equivalent standard-library algorithm,
- test organization,
- performance improvement with identical public semantics,
- adapter-local implementation detail consistent with capability contract.

The PR must still document material dependency/performance changes.

## 5. “Evidence, not confidence”

An agent statement like “production ready”, “high quality”, “safe”, “faster”, or “compatible” needs:
- test,
- benchmark,
- eval,
- license evidence,
- or a clearly scoped limitation.

Unmeasured claims do not enter release docs.
