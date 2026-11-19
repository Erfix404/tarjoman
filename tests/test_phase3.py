"""Tests for Phase 3 upgrades: blind A/B judge, expanded eval set, starter glossaries, installer, and guides."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from click.testing import CliRunner

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"
if str(BENCHMARKS_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS_DIR))

from eval_naturalness import STYLE_CATEGORIES, load_samples, style_findings  # noqa: E402
from run_judge import (  # noqa: E402
    dry_run_judge,
    evaluate_pairwise,
    heuristic_judge,
    main as judge_main,
    parse_judge_json,
)
from tarjoman.cli import cli  # noqa: E402
from tarjoman.fixer import fix_text  # noqa: E402
from tarjoman.glossaries import (  # noqa: E402
    import_glossary_to_project,
    list_glossaries,
    load_glossary,
)
from tarjoman.installer import VALID_TARGETS, install_skill  # noqa: E402
from tarjoman.memory.termbase import Termbase  # noqa: E402
from tarjoman.stages.stage4_polish import StylisticPolishStage  # noqa: E402


@contextmanager
def _temp_cwd() -> Iterator[Path]:
    """Windows-safe temporary directory helper restoring cwd before cleanup."""
    prev = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        os.chdir(tmp_path)
        try:
            yield tmp_path
        finally:
            os.chdir(prev)


class TestRunJudge(unittest.TestCase):
    def test_parse_judge_json_handles_fences_and_rejects_invalid(self) -> None:
        raw = 'Here is the score:\n```json\n{"accuracy_1": 5, "fluency_1": 4, "accuracy_2": 3, "fluency_2": 2, "winner": "1", "reason": "better prose"}\n```'
        parsed = parse_judge_json(raw)
        self.assertEqual(parsed["winner"], "1")
        self.assertEqual(parsed["accuracy_1"], 5.0)
        self.assertEqual(parsed["fluency_2"], 2.0)

        with self.assertRaises(ValueError):
            parse_judge_json('{"accuracy_1": 6, "fluency_1": 4, "accuracy_2": 3, "fluency_2": 2, "winner": "1"}')
        with self.assertRaises(ValueError):
            parse_judge_json('{"accuracy_1": 5, "fluency_1": 4, "accuracy_2": 3, "fluency_2": 2, "winner": "X"}')

    def test_position_randomization_unswaps_scores_and_winners(self) -> None:
        samples = [
            {
                "id": f"s-{i}",
                "genre": "narrative",
                "source": f"Source sentence {i}.",
                "literal": f"LIT-{i}",
                "natural": f"NAT-{i}",
                "human_verified": True,
            }
            for i in range(12)
        ]
        cand_a = {s["id"]: s["literal"] for s in samples}
        cand_b = {s["id"]: s["natural"] for s in samples}

        def custom_judge(source: str, c1: str, c2: str, genre: str) -> dict:
            del source, genre
            # Always score NAT 5/5 and LIT 2/2 regardless of presentation slot.
            if c1.startswith("NAT"):
                return {
                    "accuracy_1": 5,
                    "fluency_1": 5,
                    "accuracy_2": 2,
                    "fluency_2": 2,
                    "winner": "1",
                    "reason": "slot 1 natural",
                }
            return {
                "accuracy_1": 2,
                "fluency_1": 2,
                "accuracy_2": 5,
                "fluency_2": 5,
                "winner": "2",
                "reason": "slot 2 natural",
            }

        report = evaluate_pairwise(samples, cand_a, cand_b, judge_fn=custom_judge, seed=7)
        swapped_flags = {item["swapped"] for item in report["items"]}
        self.assertEqual(swapped_flags, {True, False})
        self.assertEqual(report["summary"]["wins_b"], 12)
        self.assertEqual(report["summary"]["wins_a"], 0)
        self.assertEqual(report["summary"]["b_mean_accuracy"], 5.0)
        self.assertEqual(report["summary"]["a_mean_fluency"], 2.0)

    def test_heuristic_and_dry_run_providers(self) -> None:
        samples = load_samples(PROJECT_ROOT / "docs" / "research" / "eval-set" / "samples.jsonl")
        cand_a = {s["id"]: s["literal"] for s in samples}
        cand_b = {s["id"]: s["natural"] for s in samples}

        rep_heur = evaluate_pairwise(samples, cand_a, cand_b, provider="heuristic", limit=20)
        self.assertEqual(rep_heur["summary"]["evaluated"], 20)
        self.assertGreater(rep_heur["summary"]["wins_b"], rep_heur["summary"]["wins_a"])
        self.assertGreater(rep_heur["summary"]["b_mean_fluency"], rep_heur["summary"]["a_mean_fluency"])

        rep_dry = evaluate_pairwise(samples, cand_a, cand_b, provider="dry-run", limit=5)
        self.assertEqual(rep_dry["summary"]["ties"], 5)

        # Smoke direct call to heuristic_judge and dry_run_judge
        d = dry_run_judge("Hello", "سلام", "درود", "chat")
        self.assertEqual(d["winner"], "tie")
        h = heuristic_judge("Hello world.", "این توسط ما انجام گردید.", "ما این کار را انجام دادیم.", "technical")
        self.assertEqual(h["winner"], "2")

    def test_run_judge_cli_self_demo_and_output(self) -> None:
        import contextlib
        import io

        with _temp_cwd() as tmp:
            out_path = tmp / "judge_report.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = judge_main(
                    [
                        "--self-demo",
                        "--provider",
                        "heuristic",
                        "--limit",
                        "10",
                        "--output",
                        str(out_path),
                        "--json",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertTrue(out_path.is_file())
            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(data, json.loads(buf.getvalue()))
            self.assertEqual(data["summary"]["evaluated"], 10)
            self.assertGreater(data["summary"]["wins_b"], data["summary"]["wins_a"])


class TestEvalExpansion(unittest.TestCase):
    def test_new_genres_negatives_and_human_verified_field(self) -> None:
        samples = load_samples(PROJECT_ROOT / "docs" / "research" / "eval-set" / "samples.jsonl")
        by_id = {s["id"]: s for s in samples}

        for sid in ("game-01", "game-02", "scr-01", "scr-02", "mem-01", "mem-02", "com-01", "com-02"):
            self.assertIn(sid, by_id)
            self.assertIn("human_verified", by_id[sid])
            self.assertFalse(by_id[sid]["human_verified"])
            self.assertEqual(style_findings(by_id[sid]["natural"], STYLE_CATEGORIES), 0, sid)
            self.assertGreater(style_findings(by_id[sid]["literal"], STYLE_CATEGORIES), 0, sid)

        for nid in ("neg-27", "neg-28"):
            self.assertIn(nid, by_id)
            text = by_id[nid]["natural"]
            self.assertEqual(StylisticPolishStage.polish(text), text, nid)
            self.assertEqual(fix_text(text).text, text, nid)

    def test_only_verified_filter_on_judge(self) -> None:
        samples = load_samples(PROJECT_ROOT / "docs" / "research" / "eval-set" / "samples.jsonl")
        cand_a = {s["id"]: s["literal"] for s in samples}
        cand_b = {s["id"]: s["natural"] for s in samples}
        report = evaluate_pairwise(samples, cand_a, cand_b, provider="heuristic", only_verified=True)
        self.assertEqual(report["summary"]["evaluated"], 0)


class TestStarterGlossaries(unittest.TestCase):
    def test_list_and_load_all_starter_glossaries(self) -> None:
        metas = list_glossaries()
        names = {m.name for m in metas}
        self.assertEqual(names, {"technical-ai", "medical-patient", "financial", "legal-licenses"})
        for meta in metas:
            self.assertGreaterEqual(meta.term_count, 25, meta.name)
            entries = load_glossary(meta.name)
            self.assertEqual(len(entries), meta.term_count)
            for entry in entries:
                self.assertNotIn("\u2014", entry.fa_term)
                self.assertNotIn("\u2013", entry.fa_term)

        with self.assertRaises(FileNotFoundError):
            load_glossary("nonexistent-glossary")

    def test_import_glossary_to_project_and_overwrite_semantics(self) -> None:
        with _temp_cwd() as tmp:
            proj = tmp / "my_book"
            runner = CliRunner()
            res_init = runner.invoke(cli, ["book", "init", "AI Book", "-o", str(proj)])
            self.assertEqual(res_init.exit_code, 0, res_init.output)

            res_list = runner.invoke(cli, ["book", "glossary", "list", "--json"])
            self.assertEqual(res_list.exit_code, 0, res_list.output)
            list_data = json.loads(res_list.output)
            self.assertEqual(len(list_data["glossaries"]), 4)

            # Seed one colliding custom term first
            tb = Termbase(db_path=proj / "terms.db")
            try:
                tb.record_term("token", "نشانه‌ی سفارشی", domain="technical-ai")
            finally:
                tb.close()

            res_imp1 = runner.invoke(cli, ["book", "glossary", "import", str(proj), "technical-ai", "--json"])
            self.assertEqual(res_imp1.exit_code, 0, res_imp1.output)
            imp1 = json.loads(res_imp1.output)
            self.assertEqual(imp1["skipped"], 1)
            self.assertGreaterEqual(imp1["added"], 25)

            # Custom value preserved when overwrite=False
            tb = Termbase(db_path=proj / "terms.db")
            try:
                self.assertEqual(tb.resolve_term("token", "technical-ai"), "نشانه‌ی سفارشی")
                self.assertEqual(tb.resolve_term("inference", "technical-ai"), "استنتاج")
            finally:
                tb.close()

            # Overwrite updates the colliding term and updates terms.tsv too
            summary2 = import_glossary_to_project(proj, "technical-ai", overwrite=True)
            self.assertEqual(summary2["updated"], 1)
            tb = Termbase(db_path=proj / "terms.db")
            try:
                self.assertEqual(tb.resolve_term("token", "technical-ai"), "توکن")
            finally:
                tb.close()
            self.assertIn("token\tتوکن\ttechnical-ai", (proj / "terms.tsv").read_text(encoding="utf-8"))

            res_bad = runner.invoke(cli, ["book", "glossary", "import", str(proj), "no-such-pack"])
            self.assertEqual(res_bad.exit_code, 1)


class TestMultiPlatformInstaller(unittest.TestCase):
    def test_install_all_targets_and_mcp_merge(self) -> None:
        for target in VALID_TARGETS:
            with _temp_cwd() as tmp:
                # Dry-run writes nothing
                dry = install_skill(target, dest_root=tmp, with_mcp=True, dry_run=True)
                self.assertTrue(dry["dry_run"])
                self.assertGreater(len(dry["written"]), 0)
                self.assertFalse(Path(dry["install_dir"]).exists())

                # Real install creates expected files
                res = install_skill(target, dest_root=tmp, with_mcp=True)
                self.assertGreater(len(res["written"]), 0)
                if target == "cursor":
                    mdc = tmp / ".cursor" / "rules" / "tarjoman.mdc"
                    self.assertTrue(mdc.is_file())
                    mdc_text = mdc.read_text(encoding="utf-8")
                    self.assertTrue(mdc_text.startswith("---"))
                    self.assertIn("alwaysApply:", mdc_text)
                    mcp_path = tmp / ".cursor" / "mcp.json"
                else:
                    skill_md = Path(res["install_dir"]) / "SKILL.md"
                    self.assertTrue(skill_md.is_file(), target)
                    self.assertTrue((Path(res["install_dir"]) / "references" / "fidelity.md").is_file(), target)
                    mcp_path = tmp / ".mcp.json"

                mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
                self.assertEqual(mcp_data["mcpServers"]["tarjoman"], {"command": "tarjoman", "args": ["mcp"]})

                # Re-running without --force skips existing files; with --force overwrites
                res_skip = install_skill(target, dest_root=tmp, with_mcp=True, force=False)
                self.assertEqual(res_skip["written"], [])
                self.assertGreater(len(res_skip["skipped"]), 0)

                res_force = install_skill(target, dest_root=tmp, with_mcp=True, force=True)
                self.assertEqual(res_force["skipped"], [])
                self.assertGreater(len(res_force["written"]), 0)

    def test_mcp_merge_preserves_existing_servers_and_cli_json(self) -> None:
        with _temp_cwd() as tmp:
            cursor_dir = tmp / ".cursor"
            cursor_dir.mkdir(parents=True)
            (cursor_dir / "mcp.json").write_text(
                json.dumps({"mcpServers": {"existing": {"command": "foo"}}}),
                encoding="utf-8",
            )
            runner = CliRunner()
            res = runner.invoke(
                cli,
                ["install", "--target", "cursor", "--dest", str(tmp), "--with-mcp", "--json"],
            )
            self.assertEqual(res.exit_code, 0, res.output)
            payload = json.loads(res.output)
            self.assertEqual(payload["target"], "cursor")
            merged = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
            self.assertIn("existing", merged["mcpServers"])
            self.assertIn("tarjoman", merged["mcpServers"])


class TestPhase3Guides(unittest.TestCase):
    def test_fidelity_and_book_guides_include_phase3_protocols(self) -> None:
        refs = PROJECT_ROOT / ".claude" / "skills" / "tarjoman" / "references"
        fid_text = (refs / "fidelity.md").read_text(encoding="utf-8")
        self.assertIn("بازبینی نابینا", fid_text)
        self.assertIn("بازترجمه‌ی معکوس", fid_text)
        self.assertNotIn("\u2014", fid_text)
        self.assertNotIn("\u2013", fid_text)

        book_text = (refs / "book.md").read_text(encoding="utf-8")
        self.assertIn("Style Anchoring", book_text)
        self.assertIn("tarjoman book glossary", book_text)


if __name__ == "__main__":
    unittest.main()
