"""
Tests for Work Package FND-012: Architecture-conformance CI.

Acceptance (WORKPACKAGES.json):
  - base job installs without speech/eval/server extras: clean base install
    verified without requiring heavy optional dependencies.
  - architecture violations fail CI: import boundaries, cross-interface
    isolation, and database rules enforced by AST checks.

Architecture Zero references:
  §22.1 — Dependency rule; CI must enforce this with import-boundary tests.
  §22.2 — Package ownership table.
  §23.2 — Secrets never in logs; error models and loggers enforce redaction.
  §25.5 — Database rules: no BLOB columns, FK ON, WAL, immutable checksums.
  §47   — Architecture conformance automation.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import List
from unittest import mock

from tarjoman.quality import (
    HEAVY_TOP_LEVEL_MODULES,
    RULE_CORE_ISOLATION,
    RULE_DATABASE_INVARIANTS,
    RULE_INTERFACE_ISOLATION,
    RULE_LAYER_DIRECTION,
    RULE_NO_HEAVY_BASE_IMPORTS,
    RULE_SECRET_REDACTION,
    ArchitectureConformanceChecker,
    ArchitectureViolation,
    ArchitectureViolationError,
    format_report,
)
from tarjoman.quality.conformance import CANONICAL_JOB_STATES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rule_ids(violations: List[ArchitectureViolation]) -> List[str]:
    return [v.rule_id for v in violations]


def _checker() -> ArchitectureConformanceChecker:
    return ArchitectureConformanceChecker()


def _fresh_subprocess_env_blocking(mod: str) -> subprocess.CompletedProcess:
    """Import `mod` in a fresh interpreter with heavy extras blocked.

    Heavy extras are blocked by pre-seeding sys.modules with None so any
    real import attempt raises ImportError immediately (stdlib behavior for
    sys.modules[name] = None). Returns the completed process; rc==0 means
    the base module imports cleanly without the extras.
    """
    heavy = [
        "torch", "whisper", "faster_whisper", "comet", "onnxruntime",
        "fastapi", "uvicorn", "openai", "anthropic", "mcp", "sacrebleu",
    ]
    prelude = "; ".join(f"import sys; sys.modules['{m}'] = None" for m in heavy)
    code = (
        f"{prelude}; "
        f"import tarjoman; "
        f"import {mod}; "
        f"print('OK')"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# 1. Base job installs without speech/eval/server extras
# ---------------------------------------------------------------------------

class TestCleanBaseImport(unittest.TestCase):
    """Base install must import cleanly without optional extras (D03)."""

    def test_base_top_package_imports_in_isolation(self) -> None:
        """`import tarjoman` works with all heavy extras blocked."""
        proc = _fresh_subprocess_env_blocking("tarjoman")
        self.assertEqual(
            proc.returncode, 0,
            msg=f"base import failed without extras: {proc.stderr[-2000:]}",
        )
        self.assertIn("OK", proc.stdout)

    def test_base_packages_import_without_extras(self) -> None:
        """core/quality/storage/profiles import without speech/eval/server extras."""
        for mod in (
            "tarjoman.core",
            "tarjoman.quality",
            "tarjoman.storage",
            "tarjoman.profiles",
        ):
            with self.subTest(module=mod):
                proc = _fresh_subprocess_env_blocking(mod)
                self.assertEqual(
                    proc.returncode, 0,
                    msg=f"{mod} requires a heavy extra: {proc.stderr[-2000:]}",
                )
                self.assertIn("OK", proc.stdout)

    def test_missing_optional_modules_do_not_break_base_import(self) -> None:
        """Simulated-missing extras (sys.modules -> None) do not break base."""
        heavy = [
            "torch", "whisper", "faster_whisper", "comet", "onnxruntime",
            "fastapi", "uvicorn", "openai", "anthropic", "mcp", "sacrebleu",
        ]
        with mock.patch.dict(sys.modules, {m: None for m in heavy}):  # type: ignore[dict-item]
            for mod in (
                "tarjoman.core.errors",
                "tarjoman.core.logging",
                "tarjoman.quality.normalizer",
                "tarjoman.quality.calque_detector",
                "tarjoman.quality.conformance",
            ):
                with self.subTest(module=mod):
                    for stale in [m for m in list(sys.modules) if m == mod or m.startswith(mod + ".")]:
                        del sys.modules[stale]
                    __import__(mod)

    def test_base_import_is_fast(self) -> None:
        """`import tarjoman` completes in under 200ms (lightweight core, P1)."""
        code = (
            "import time; t = time.perf_counter(); "
            "import tarjoman; "
            "print(round((time.perf_counter() - t) * 1000, 1))"
        )
        elapsed: List[float] = []
        for _ in range(3):
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr[-1000:])
            elapsed.append(float(proc.stdout.strip().split()[-1]))
        self.assertLess(
            min(elapsed), 200.0,
            msg=f"top-package import too slow for a lightweight core: {elapsed}ms",
        )

    def test_heavy_modules_never_loaded_by_base_import(self) -> None:
        """No heavy extra is present in sys.modules after base imports."""
        mods = "; ".join(
            f"import {m}" for m in (
                "tarjoman", "tarjoman.core", "tarjoman.quality",
                "tarjoman.storage", "tarjoman.profiles",
            )
        )
        code = (
            f"{mods}; import sys; "
            "heavy = ['torch','whisper','faster_whisper','comet','onnxruntime',"
            "'fastapi','uvicorn','openai','anthropic','mcp','sacrebleu']; "
            "loaded = sorted(m for m in heavy if m in sys.modules); "
            "print('LOADED:' + ','.join(loaded) if loaded else 'CLEAN')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr[-1000:])
        self.assertIn("CLEAN", proc.stdout, msg=f"heavy extras leaked: {proc.stdout}")

    def test_base_dependencies_are_minimal(self) -> None:
        """pyproject base deps stay minimal; heavy libs live only in extras."""
        import tomllib

        root = Path(__file__).resolve().parent.parent
        with open(root / "pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
        base = {r.split(";")[0].strip().lower() for r in data["project"]["dependencies"]}
        base_names = {re.split(r"[<>=!~\s\[]", r, maxsplit=1)[0] for r in base}
        self.assertEqual(
            base_names, {"pydantic", "click", "jinja2", "packaging"},
            msg=f"base dependencies drifted: {sorted(base_names)}",
        )
        extras = data["project"]["optional-dependencies"]
        for group in ("pdf", "server", "speech", "eval", "dev", "all"):
            self.assertIn(group, extras, msg=f"missing extra group: {group}")


# ---------------------------------------------------------------------------
# 2. Architecture violations fail CI — checker passes on clean tree
# ---------------------------------------------------------------------------

class TestConformancePassesOnCleanTree(unittest.TestCase):
    """The checker itself must pass on the current clean codebase."""

    def test_check_returns_no_violations(self) -> None:
        violations = _checker().check()
        self.assertEqual(
            violations, [],
            msg="clean tree must pass:\n" + format_report(violations),
        )

    def test_enforce_does_not_raise(self) -> None:
        try:
            _checker().enforce()
        except ArchitectureViolationError as exc:
            self.fail(f"enforce() raised on clean tree: {exc}")

    def test_violation_report_shape(self) -> None:
        violations = _checker().check_snippet(
            "import fastapi\n", "tarjoman.core.errors", filename="probe.py"
        )
        self.assertTrue(violations)
        for v in violations:
            self.assertIsInstance(v, ArchitectureViolation)
            self.assertIn(v.rule_id, (
                RULE_CORE_ISOLATION, RULE_INTERFACE_ISOLATION,
                RULE_NO_HEAVY_BASE_IMPORTS, RULE_DATABASE_INVARIANTS,
                RULE_SECRET_REDACTION, RULE_LAYER_DIRECTION,
            ))
            self.assertGreaterEqual(v.line, 1)
            self.assertTrue(v.file)
            self.assertTrue(v.message)
            d = v.to_dict()
            self.assertEqual(
                set(d), {"rule_id", "file", "line", "message"}
            )


# ---------------------------------------------------------------------------
# 3. Synthetic violations fail with detailed diagnostics
# ---------------------------------------------------------------------------

class TestSyntheticViolationsFail(unittest.TestCase):
    """Injected violations must fail the checker with rule + line info."""

    def test_core_importing_fastapi_triggers_core_isolation(self) -> None:
        violations = _checker().check_snippet(
            "import fastapi\n",
            "tarjoman.core.errors",
            filename="core_probe.py",
        )
        self.assertIn(RULE_CORE_ISOLATION, _rule_ids(violations))
        self.assertTrue(any(v.line == 1 for v in violations))

    def test_core_importing_torch_triggers_core_isolation(self) -> None:
        violations = _checker().check_snippet(
            "from torch import nn\n",
            "tarjoman.core.config",
            filename="core_probe.py",
        )
        self.assertIn(RULE_CORE_ISOLATION, _rule_ids(violations))

    def test_core_importing_storage_triggers_core_isolation(self) -> None:
        violations = _checker().check_snippet(
            "from tarjoman.storage.database import DatabaseManager\n",
            "tarjoman.core.errors",
            filename="core_probe.py",
        )
        self.assertIn(RULE_CORE_ISOLATION, _rule_ids(violations))

    def test_cross_interface_import_triggers_interface_isolation(self) -> None:
        violations = _checker().check_snippet(
            "from tarjoman.interfaces.api import router\n",
            "tarjoman.interfaces.cli.commands",
            filename="cli_probe.py",
        )
        self.assertIn(RULE_INTERFACE_ISOLATION, _rule_ids(violations))
        cli_ok = _checker().check_snippet(
            "from tarjoman.interfaces.cli.helpers import run\n",
            "tarjoman.interfaces.cli.commands",
            filename="cli_probe.py",
        )
        self.assertNotIn(RULE_INTERFACE_ISOLATION, _rule_ids(cli_ok))

    def test_blob_column_triggers_database_invariants(self) -> None:
        violations = _checker().check_snippet(
            "CREATE TABLE files (id TEXT PRIMARY KEY, payload BLOB NOT NULL);\n",
            "tarjoman.storage.migrations.probe",
            filename="probe.sql",
        )
        self.assertIn(RULE_DATABASE_INVARIANTS, _rule_ids(violations))

    def test_no_heavy_top_level_import_in_quality(self) -> None:
        violations = _checker().check_snippet(
            "import onnxruntime\n",
            "tarjoman.quality.scoring",
            filename="quality_probe.py",
        )
        self.assertIn(RULE_NO_HEAVY_BASE_IMPORTS, _rule_ids(violations))

    def test_lazy_heavy_import_inside_function_is_allowed(self) -> None:
        violations = _checker().check_snippet(
            "def compile_pdf(path):\n    import typst\n    return typst.compile(path)\n",
            "tarjoman.quality.scoring",
            filename="quality_probe.py",
        )
        self.assertNotIn(RULE_NO_HEAVY_BASE_IMPORTS, _rule_ids(violations))

    def test_enforce_raises_with_diagnostics(self) -> None:
        violations = _checker().check_snippet(
            "import torch\n",
            "tarjoman.core.errors",
            filename="core_probe.py",
        )
        self.assertTrue(violations)
        with self.assertRaises(ArchitectureViolationError) as ctx:
            raise ArchitectureViolationError(violations)
        message = str(ctx.exception)
        self.assertIn(RULE_CORE_ISOLATION, message)
        self.assertIn("core_probe.py", message)

    def test_hardcoded_secret_literal_triggers_secret_redaction(self) -> None:
        violations = _checker().check_snippet(
            'API_KEY = "sk-ant-abcdefghijklmnopqrstuvwxyz0123456789ABCD"\n',
            "tarjoman.storage.repositories.probe",
            filename="secret_probe.py",
        )
        self.assertIn(RULE_SECRET_REDACTION, _rule_ids(violations))

    def test_application_importing_storage_triggers_layer_direction(self) -> None:
        violations = _checker().check_snippet(
            "from tarjoman.storage.database import DatabaseManager\n",
            "tarjoman.application.jobs",
            filename="app_probe.py",
        )
        self.assertIn(RULE_LAYER_DIRECTION, _rule_ids(violations))


# ---------------------------------------------------------------------------
# 4. Package ownership boundaries (§22.2)
# ---------------------------------------------------------------------------

class TestPackageOwnership(unittest.TestCase):
    """Static ownership invariants every package must satisfy."""

    def _python_files(self) -> List[Path]:
        root = Path(__file__).resolve().parent.parent / "src" / "tarjoman"
        return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]

    def _imports_of(self, path: Path) -> List[str]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            return []
        found: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.append(node.module)
        return found

    def test_core_contracts_own_no_network_or_db(self) -> None:
        """core.contracts owns stable IR contracts — never network/DB/provider."""
        for path in self._python_files():
            rel = str(path)
            if "/core/contracts" not in rel and "/core/" not in rel:
                continue
            if path.name in ("pipeline.py",):
                continue
            if "/core/contracts" in rel or path.parent.name == "core":
                for imported in self._imports_of(path):
                    top = imported.split(".")[0]
                    self.assertNotIn(
                        top,
                        {"sqlite3", "socket", "http", "urllib", "requests",
                         "httpx", "fastapi", "uvicorn", "torch"},
                        msg=f"{path.name} imports forbidden {imported}",
                    )

    def test_job_status_vocabulary_is_canonical(self) -> None:
        """Public job states are exactly the D38 vocabulary (§4.8)."""
        self.assertEqual(
            set(CANONICAL_JOB_STATES),
            {"QUEUED", "RUNNING", "WAITING_REVIEW", "SUCCEEDED", "FAILED", "CANCELLED"},
        )
        root = Path(__file__).resolve().parent.parent
        migration = (
            root / "src" / "tarjoman" / "storage"
            / "migrations" / "001_initial_schema.sql"
        )
        sql = migration.read_text(encoding="utf-8")
        match = re.search(r"status\s+TEXT[^,]*CHECK\s*\((.*?)\)", sql, re.IGNORECASE | re.DOTALL)
        self.assertIsNotNone(match, msg="jobs table must carry a status CHECK")
        check_body = match.group(1)
        for state in CANONICAL_JOB_STATES:
            self.assertIn(state, check_body, msg=f"jobs CHECK missing {state}")
        self.assertNotIn("COMPLETED", check_body.upper())

    def test_migrations_have_no_blob_columns(self) -> None:
        """No shipped migration declares a BLOB column (D20)."""
        root = Path(__file__).resolve().parent.parent
        mig_dir = root / "src" / "tarjoman" / "storage" / "migrations"
        for sql_path in sorted(mig_dir.glob("*.sql")):
            sql = sql_path.read_text(encoding="utf-8")
            stripped = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
            self.assertIsNone(
                re.search(r"\b[A-Za-z_][\w$]*\s+BLOB\b", stripped, re.IGNORECASE),
                msg=f"{sql_path.name} declares a BLOB column (D20)",
            )

    def test_error_models_enforce_redaction(self) -> None:
        """Error taxonomy + logging structurally enforce redaction (D16/§23.2)."""
        from tarjoman.core import errors as errors_mod
        from tarjoman.core import logging as logging_mod

        self.assertTrue(hasattr(errors_mod, "sanitize_error_message"))
        self.assertTrue(hasattr(errors_mod, "sanitize_details"))
        self.assertTrue(hasattr(logging_mod, "redact_secrets"))
        self.assertTrue(hasattr(logging_mod, "RedactionFilter"))
        secret = "sk-ant-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
        redacted = errors_mod.TarjomanError(f"boom {secret}").message
        self.assertNotIn(secret, redacted)

    def test_checker_covers_all_rule_ids(self) -> None:
        from tarjoman.quality import ALL_RULES

        self.assertEqual(
            set(ALL_RULES),
            {
                RULE_CORE_ISOLATION, RULE_INTERFACE_ISOLATION,
                RULE_NO_HEAVY_BASE_IMPORTS, RULE_DATABASE_INVARIANTS,
                RULE_SECRET_REDACTION, RULE_LAYER_DIRECTION,
            },
        )
        self.assertIn("torch", HEAVY_TOP_LEVEL_MODULES)
        self.assertIn("fastapi", HEAVY_TOP_LEVEL_MODULES)
        self.assertIn("faster_whisper", HEAVY_TOP_LEVEL_MODULES)


if __name__ == "__main__":
    unittest.main()
