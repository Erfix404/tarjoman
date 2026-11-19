#!/usr/bin/env python3
"""Blind, position-randomized A/B two-axis judge for Persian translation quality.

Compares two candidate outputs (A vs B) on the Tarjoman eval set using two
independent 1-5 axes:
- Accuracy (meaning preservation, numbers, negations, hedges, completeness)
- Fluency (natural Persian prose/dialogue in the genre's expected register)

To eliminate position bias, each sample deterministically randomizes whether
Candidate A or Candidate B is shown first, then maps the blind verdict back.

Supports offline CI modes (`--provider heuristic` and `--provider dry-run`),
custom Python judge callables, and zero-dependency OpenAI-compatible or
Anthropic REST providers (`urllib.request`).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"
for _p in (str(PROJECT_ROOT), str(BENCHMARKS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from eval_naturalness import (  # noqa: E402
    DEFAULT_SAMPLES,
    SIGNAL_CATEGORIES,
    STYLE_CATEGORIES,
    load_samples,
)
from tarjoman.linter import lint_text  # noqa: E402
from tarjoman.memory.fidelity import check_fidelity  # noqa: E402

JudgeFn = Callable[[str, str, str, str], Dict[str, Any]]

PAIRWISE_JUDGE_PROMPT = """You are a senior English-to-Persian translation evaluator and a native Persian speaker.
Compare CANDIDATE 1 and CANDIDATE 2 blindly on two separate 1-5 axes. Do not let one axis influence the other, and ignore presentation order.

ACCURACY (1-5): Is all meaning from SOURCE preserved with nothing added, dropped, or distorted? Verify numbers, named entities, negations, and limiting hedges («فقط», «هنوز», «مگر»).
FLUENCY (1-5): Would a native Persian reader believe this was originally written in Persian in the expected register for genre `{genre}`? Penalize «توسط» passives, needless «یک», repeated pronouns, noun chains, calqued idioms, mixed formal/colloquial verbs, and foreign em-dashes.

Reply ONLY with valid JSON:
{{"accuracy_1": <1-5>, "fluency_1": <1-5>, "accuracy_2": <1-5>, "fluency_2": <1-5>, "winner": "1" | "2" | "tie", "reason": "<concise explanation>"}}

SOURCE:
{source}

CANDIDATE 1:
{cand1}

CANDIDATE 2:
{cand2}
"""


def _strip_json_fences(raw: str) -> str:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return text


def parse_judge_json(raw: str) -> Dict[str, Any]:
    """Parse and validate a pairwise judge JSON response."""
    cleaned = _strip_json_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid judge JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Judge response must be a JSON object.")

    parsed: Dict[str, Any] = {}
    for key in ("accuracy_1", "fluency_1", "accuracy_2", "fluency_2"):
        if key not in data:
            raise ValueError(f"Missing required score key: {key}")
        try:
            val = float(data[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Score {key} is not numeric: {data[key]!r}") from exc
        if not 1.0 <= val <= 5.0:
            raise ValueError(f"Score {key} out of [1, 5] range: {val}")
        parsed[key] = round(val, 3)

    winner = str(data.get("winner", "")).strip().lower()
    if winner not in {"1", "2", "tie"}:
        raise ValueError(f"Invalid blind winner {data.get('winner')!r}; expected '1', '2', or 'tie'.")
    parsed["winner"] = winner
    parsed["reason"] = str(data.get("reason", "")).strip()
    return parsed


def _heuristic_scores(source: str, text: str) -> tuple[float, float]:
    fidelity_issues = check_fidelity(source, text)
    acc = max(1.0, 5.0 - float(len(fidelity_issues)))

    lint_issues = lint_text(text)
    style_pen = sum(1.0 for i in lint_issues if i.category in STYLE_CATEGORIES)
    typo_cats = SIGNAL_CATEGORIES - STYLE_CATEGORIES
    typo_pen = sum(0.5 for i in lint_issues if i.category in typo_cats)
    flu = max(1.0, 5.0 - style_pen - typo_pen)
    return round(acc, 3), round(flu, 3)


def heuristic_judge(source: str, cand1: str, cand2: str, genre: str = "") -> Dict[str, Any]:
    """Deterministic offline proxy using check_fidelity + lint_text."""
    del genre
    acc1, flu1 = _heuristic_scores(source, cand1)
    acc2, flu2 = _heuristic_scores(source, cand2)
    tot1 = acc1 + flu1
    tot2 = acc2 + flu2
    if tot1 - tot2 >= 0.5:
        winner = "1"
    elif tot2 - tot1 >= 0.5:
        winner = "2"
    else:
        winner = "tie"
    return {
        "accuracy_1": acc1,
        "fluency_1": flu1,
        "accuracy_2": acc2,
        "fluency_2": flu2,
        "winner": winner,
        "reason": f"heuristic proxy (tot1={tot1:.1f}, tot2={tot2:.1f})",
    }


def dry_run_judge(source: str, cand1: str, cand2: str, genre: str = "") -> Dict[str, Any]:
    """Validate prompt construction and output schema with zero network calls."""
    _ = PAIRWISE_JUDGE_PROMPT.format(genre=genre or "general", source=source, cand1=cand1, cand2=cand2)
    return {
        "accuracy_1": 3.0,
        "fluency_1": 3.0,
        "accuracy_2": 3.0,
        "fluency_2": 3.0,
        "winner": "tie",
        "reason": "dry-run placeholder verdict",
    }


def openai_judge(
    prompt: str,
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Call an OpenAI-compatible Chat Completions endpoint via urllib."""
    key = api_key or os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    endpoint = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    url = f"{endpoint}/chat/completions"
    payload = {
        "model": model or "gpt-4o-mini",
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return parse_judge_json(content)


def anthropic_judge(
    prompt: str,
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Call the Anthropic Messages API via urllib."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    payload = {
        "model": model or "claude-3-5-sonnet-latest",
        "max_tokens": 512,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    blocks = body.get("content", [])
    text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
    return parse_judge_json(text)


def load_candidates_map(path: Path) -> Dict[str, str]:
    """Load JSONL lines of {'id': ..., 'translation': ...} into a dict."""
    mapping: Dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            sid = str(row["id"])
            mapping[sid] = str(row["translation"])
    return mapping


def _resolve_provider(
    provider: str,
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> JudgeFn:
    norm = provider.strip().lower()
    if norm == "heuristic":
        return heuristic_judge
    if norm == "dry-run":
        return dry_run_judge
    if norm == "openai":
        return lambda src, c1, c2, g: openai_judge(
            PAIRWISE_JUDGE_PROMPT.format(genre=g or "general", source=src, cand1=c1, cand2=c2),
            model=model,
            base_url=base_url,
        )
    if norm == "anthropic":
        return lambda src, c1, c2, g: anthropic_judge(
            PAIRWISE_JUDGE_PROMPT.format(genre=g or "general", source=src, cand1=c1, cand2=c2),
            model=model,
        )
    raise ValueError(f"Unsupported judge provider: {provider!r}")


def evaluate_pairwise(
    samples: List[Dict[str, Any]],
    cand_a: Union[Dict[str, str], Path],
    cand_b: Union[Dict[str, str], Path],
    *,
    provider: str = "heuristic",
    judge_fn: Optional[JudgeFn] = None,
    seed: int = 42,
    limit: Optional[int] = None,
    only_verified: bool = False,
    include_negatives: bool = False,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Run blind position-randomized A/B evaluation over matching sample IDs."""
    map_a = load_candidates_map(Path(cand_a)) if not isinstance(cand_a, dict) else cand_a
    map_b = load_candidates_map(Path(cand_b)) if not isinstance(cand_b, dict) else cand_b
    scorer = judge_fn or _resolve_provider(provider, model=model, base_url=base_url)

    filtered: List[Dict[str, Any]] = []
    for sample in samples:
        if not include_negatives and sample.get("type") == "negative":
            continue
        if only_verified and sample.get("human_verified") is not True:
            continue
        sid = str(sample["id"])
        if sid in map_a and sid in map_b:
            filtered.append(sample)
    if limit is not None and limit >= 0:
        filtered = filtered[:limit]

    rng = random.Random(seed)
    items: List[Dict[str, Any]] = []
    by_genre: Dict[str, Dict[str, Any]] = {}

    for sample in filtered:
        sid = str(sample["id"])
        genre = str(sample.get("genre", "general"))
        text_a = map_a[sid]
        text_b = map_b[sid]
        swapped = rng.choice([True, False])
        cand1, cand2 = (text_b, text_a) if swapped else (text_a, text_b)

        raw_verdict = scorer(sample["source"], cand1, cand2, genre)
        if not isinstance(raw_verdict, dict):
            raise ValueError(f"Judge callable must return a dict, got {type(raw_verdict).__name__}")
        verdict = parse_judge_json(json.dumps(raw_verdict, ensure_ascii=False))

        if swapped:
            a_acc, a_flu = verdict["accuracy_2"], verdict["fluency_2"]
            b_acc, b_flu = verdict["accuracy_1"], verdict["fluency_1"]
            winner_map = {"1": "B", "2": "A", "tie": "tie"}
        else:
            a_acc, a_flu = verdict["accuracy_1"], verdict["fluency_1"]
            b_acc, b_flu = verdict["accuracy_2"], verdict["fluency_2"]
            winner_map = {"1": "A", "2": "B", "tie": "tie"}
        true_winner = winner_map[verdict["winner"]]

        items.append(
            {
                "id": sid,
                "genre": genre,
                "human_verified": bool(sample.get("human_verified", False)),
                "swapped": swapped,
                "a_accuracy": a_acc,
                "a_fluency": a_flu,
                "b_accuracy": b_acc,
                "b_fluency": b_flu,
                "winner": true_winner,
                "reason": verdict["reason"],
            }
        )

        g_bucket = by_genre.setdefault(
            genre,
            {
                "count": 0,
                "wins_a": 0,
                "wins_b": 0,
                "ties": 0,
                "_a_acc": 0.0,
                "_a_flu": 0.0,
                "_b_acc": 0.0,
                "_b_flu": 0.0,
            },
        )
        g_bucket["count"] += 1
        if true_winner == "A":
            g_bucket["wins_a"] += 1
        elif true_winner == "B":
            g_bucket["wins_b"] += 1
        else:
            g_bucket["ties"] += 1
        g_bucket["_a_acc"] += a_acc
        g_bucket["_a_flu"] += a_flu
        g_bucket["_b_acc"] += b_acc
        g_bucket["_b_flu"] += b_flu

    n = len(items)
    wins_a = sum(1 for it in items if it["winner"] == "A")
    wins_b = sum(1 for it in items if it["winner"] == "B")
    ties = sum(1 for it in items if it["winner"] == "tie")

    for genre, b in by_genre.items():
        cnt = max(1, b["count"])
        by_genre[genre] = {
            "count": b["count"],
            "wins_a": b["wins_a"],
            "wins_b": b["wins_b"],
            "ties": b["ties"],
            "a_mean_accuracy": round(b["_a_acc"] / cnt, 3),
            "a_mean_fluency": round(b["_a_flu"] / cnt, 3),
            "b_mean_accuracy": round(b["_b_acc"] / cnt, 3),
            "b_mean_fluency": round(b["_b_flu"] / cnt, 3),
        }

    summary = {
        "evaluated": n,
        "wins_a": wins_a,
        "wins_b": wins_b,
        "ties": ties,
        "a_win_rate": round(wins_a / n, 4) if n else 0.0,
        "b_win_rate": round(wins_b / n, 4) if n else 0.0,
        "a_mean_accuracy": round(sum(i["a_accuracy"] for i in items) / n, 3) if n else 0.0,
        "a_mean_fluency": round(sum(i["a_fluency"] for i in items) / n, 3) if n else 0.0,
        "b_mean_accuracy": round(sum(i["b_accuracy"] for i in items) / n, 3) if n else 0.0,
        "b_mean_fluency": round(sum(i["b_fluency"] for i in items) / n, 3) if n else 0.0,
    }

    return {
        "meta": {
            "provider": provider if judge_fn is None else "custom",
            "model": model,
            "seed": seed,
            "only_verified": only_verified,
            "include_negatives": include_negatives,
        },
        "summary": summary,
        "by_genre": dict(sorted(by_genre.items())),
        "items": items,
    }


def _print_report(report: Dict[str, Any]) -> None:
    s = report["summary"]
    m = report["meta"]
    print(f"Blind A/B Two-Axis Evaluation (provider={m['provider']}, seed={m['seed']})")
    print("=" * 60)
    print(f"Evaluated: {s['evaluated']} sample(s)")
    print(
        f"System A : Accuracy={s['a_mean_accuracy']:.2f}/5  "
        f"Fluency={s['a_mean_fluency']:.2f}/5  Wins={s['wins_a']} ({s['a_win_rate']*100:.1f}%)"
    )
    print(
        f"System B : Accuracy={s['b_mean_accuracy']:.2f}/5  "
        f"Fluency={s['b_mean_fluency']:.2f}/5  Wins={s['wins_b']} ({s['b_win_rate']*100:.1f}%)"
    )
    print(f"Ties     : {s['ties']}")
    if report["by_genre"]:
        print("\nBy genre (A acc/flu vs B acc/flu | A/B/tie):")
        for genre, g in report["by_genre"].items():
            print(
                f"  {genre:<14} "
                f"A={g['a_mean_accuracy']:.2f}/{g['a_mean_fluency']:.2f} vs "
                f"B={g['b_mean_accuracy']:.2f}/{g['b_mean_fluency']:.2f} "
                f"({g['wins_a']}/{g['wins_b']}/{g['ties']})"
            )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES, help="Eval set JSONL path")
    parser.add_argument("--cand-a", type=Path, default=None, help="Candidate A JSONL ({id, translation})")
    parser.add_argument("--cand-b", type=Path, default=None, help="Candidate B JSONL ({id, translation})")
    parser.add_argument(
        "--self-demo",
        action="store_true",
        help="Compare eval set's literal (A) vs natural (B) samples offline",
    )
    parser.add_argument(
        "--provider",
        choices=["heuristic", "dry-run", "openai", "anthropic"],
        default="heuristic",
        help="Judge backend provider",
    )
    parser.add_argument("--model", default=None, help="Model name for openai/anthropic providers")
    parser.add_argument("--base-url", default=None, help="Custom base URL for OpenAI-compatible APIs")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for blind A/B order")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate at most N samples")
    parser.add_argument("--only-verified", action="store_true", help="Restrict to human_verified samples")
    parser.add_argument("--include-negatives", action="store_true", help="Include negative samples")
    parser.add_argument("--output", type=Path, default=None, help="Write JSON report to this path")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Print JSON report to stdout")
    args = parser.parse_args(argv)

    if not args.self_demo and (args.cand_a is None or args.cand_b is None):
        parser.error("Provide both --cand-a and --cand-b, or pass --self-demo.")

    samples = load_samples(args.samples)
    if args.self_demo:
        cand_a = {str(s["id"]): str(s["literal"]) for s in samples}
        cand_b = {str(s["id"]): str(s["natural"]) for s in samples}
    else:
        cand_a = args.cand_a
        cand_b = args.cand_b

    try:
        report = evaluate_pairwise(
            samples,
            cand_a,
            cand_b,
            provider=args.provider,
            seed=args.seed,
            limit=args.limit,
            only_verified=args.only_verified,
            include_negatives=args.include_negatives,
            model=args.model,
            base_url=args.base_url,
        )
    except (RuntimeError, ValueError, urllib.error.URLError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
