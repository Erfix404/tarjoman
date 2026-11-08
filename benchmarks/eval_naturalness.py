#!/usr/bin/env python3
"""
Naturalness evaluation for Tarjoman (Persian translation & editing).

Two modes:

1. Self-check (default): measures the *tool* on the eval set.
   - Every negative sample (correct Persian) must pass the automatic polish
     unchanged and should trigger no style finding.
   - For positive samples, reports how many style findings the lint gives
     the literal (translationese) version vs the natural one. A useful
     detector flags the literal side more often.

2. Candidate scoring (--candidates FILE.jsonl): scores a translator's output.
   Each line is {"id": ..., "translation": ...}. For every sample it reports
   style findings per 100 words, so two versions of the skill (or two
   models) can be compared on the same sources. This is a cheap automatic
   proxy only; real quality needs a judge (see --judge-prompt) or a human,
   scoring accuracy and fluency separately.

Usage:
    python benchmarks/eval_naturalness.py
    python benchmarks/eval_naturalness.py --candidates out.jsonl
    python benchmarks/eval_naturalness.py --judge-prompt dlg-01
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tarjoman.linter import lint_text  # noqa: E402
from tarjoman.stages.stage4_polish import StylisticPolishStage  # noqa: E402

DEFAULT_SAMPLES = PROJECT_ROOT / "docs" / "research" / "eval-set" / "samples.jsonl"
STYLE_CATEGORIES = {"ai-tell", "calque"}
# Typography and structure signals that also betray a literal translation
# (English dash, English quotes, Latin decimal point, redundant «یک», ezafe chains).
SIGNAL_CATEGORIES = STYLE_CATEGORIES | {"em-dash", "quote-style", "punct", "generic-article", "ezafe-chain"}

JUDGE_PROMPT = """You are a professional English-to-Persian translation reviewer and a native Persian speaker.
Score the candidate translation on two separate axes, each 1-5. Do not let one axis influence the other.

ACCURACY (1-5): Is every piece of meaning in the source present, with nothing added, dropped or distorted? Check numbers, names, negations and hedges.
FLUENCY (1-5): Would a native Persian reader believe this was originally written in Persian, in the register the genre needs ({genre})? Penalize English structure: «توسط» passives, needless «یک», repeated pronouns, noun chains, calqued idioms, and mixed formal/colloquial forms.

Then list each translationese phrase you found, with a natural rewrite.

Reply as JSON: {{"accuracy": n, "fluency": n, "translationese": [{{"phrase": "...", "rewrite": "..."}}]}}

SOURCE:
{source}

CANDIDATE:
{candidate}
"""


def load_samples(path: Path) -> List[Dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def style_findings(text: str, categories=STYLE_CATEGORIES) -> int:
    return sum(1 for i in lint_text(text) if i.category in categories)


def separation(samples: List[Dict], categories=STYLE_CATEGORIES) -> Dict[str, List[int]]:
    """Per genre: [samples where literal gets more findings than natural, total]."""
    out: Dict[str, List[int]] = {}
    for s in samples:
        if s.get("type") == "negative":
            continue
        row = out.setdefault(s.get("genre", "?"), [0, 0])
        row[1] += 1
        if style_findings(s["literal"], categories) > style_findings(s["natural"], categories):
            row[0] += 1
    return out


def word_count(text: str) -> int:
    return max(1, len(re.findall(r"\S+", text)))


def self_check(samples: List[Dict]) -> bool:
    ok = True
    negatives = [s for s in samples if s.get("type") == "negative"]
    positives = [s for s in samples if s.get("type") != "negative"]

    print(f"Negative samples (must stay unchanged): {len(negatives)}")
    for s in negatives:
        text = s["natural"]
        changed = StylisticPolishStage.polish(text) != text
        flagged = style_findings(text)
        status = "FAIL" if changed else ("WARN" if flagged else "ok")
        if changed:
            ok = False
        print(f"  [{status}] {s['id']}: changed={changed} style_findings={flagged}")

    print(f"\nPositive samples (literal vs natural): {len(positives)}")
    literal_total = natural_total = caught = 0
    for s in positives:
        lit, nat = style_findings(s["literal"]), style_findings(s["natural"])
        literal_total += lit
        natural_total += nat
        caught += 1 if lit > nat else 0
        print(f"  {s['id']:<10} literal={lit} natural={nat}")
    if positives:
        print(
            f"\nDetector separates literal from natural in {caught}/{len(positives)} samples "
            f"(findings: literal={literal_total}, natural={natural_total})."
        )
        by_genre = separation(samples)
        with_typo = separation(samples, SIGNAL_CATEGORIES)
        print("\nBy genre (style only | style + typography):")
        for genre in sorted(by_genre):
            a, n = by_genre[genre]
            b, _ = with_typo[genre]
            print(f"  {genre:<14} {a}/{n} | {b}/{n}")
        total_typo = sum(v[0] for v in with_typo.values())
        print(f"  {'all':<14} {caught}/{len(positives)} | {total_typo}/{len(positives)}")
    return ok


def score_candidates(samples: List[Dict], cand_path: Path) -> None:
    by_id = {s["id"]: s for s in samples}
    with cand_path.open(encoding="utf-8") as f:
        cands = [json.loads(line) for line in f if line.strip()]
    total_findings = total_words = 0
    for c in cands:
        sample = by_id.get(c["id"])
        if not sample:
            print(f"  [skip] unknown id {c['id']}")
            continue
        text = c["translation"]
        n, w = style_findings(text), word_count(text)
        total_findings += n
        total_words += w
        print(f"  {c['id']:<10} findings={n} per100w={100 * n / w:.1f}")
    if total_words:
        print(f"\nOverall: {100 * total_findings / total_words:.2f} style findings per 100 words (lower is better).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--judge-prompt", metavar="ID", default=None, help="Print an LLM-judge prompt for one sample")
    args = parser.parse_args()

    samples = load_samples(args.samples)
    if args.judge_prompt:
        sample = next((s for s in samples if s["id"] == args.judge_prompt), None)
        if not sample:
            print(f"No sample with id {args.judge_prompt}", file=sys.stderr)
            return 2
        print(JUDGE_PROMPT.format(genre=sample.get("genre", ""), source=sample["source"], candidate="<paste translation>"))
        return 0
    if args.candidates:
        score_candidates(samples, args.candidates)
        return 0
    return 0 if self_check(samples) else 1


if __name__ == "__main__":
    sys.exit(main())
