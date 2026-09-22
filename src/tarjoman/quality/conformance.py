"""
Architecture conformance checker — Architecture Zero §22, §23.2, §25.5, §47.

Enforces dependency direction, optional-dependency isolation, interface
separation, database invariants (D20), and secret-redaction structure (D16)
by statically analyzing Python imports (``ast``) and SQL migrations.

Locked decisions enforced here:
  D03 — Base installation stays lightweight; heavy AI/audio/eval/server
        features are extras and must never leak into base imports.
  D16 — Secrets and raw source content are never logged; error models and
        loggers enforce redaction.
  D19 — Module dependencies follow Core <- Application <-
        Infrastructure/Adapters <- Interfaces; reverse imports are forbidden.
  D20 — SQLite stores transactional metadata; large/binary artifacts live in
        a content-addressed filesystem store, never DB BLOB columns.

Work Package: FND-012 — Architecture-conformance CI.

This module is intentionally stdlib-only so the checker itself can never
introduce a base-dependency violation.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Rule identifiers
# ---------------------------------------------------------------------------

RULE_CORE_ISOLATION = "RULE_CORE_ISOLATION"
RULE_INTERFACE_ISOLATION = "RULE_INTERFACE_ISOLATION"
RULE_NO_HEAVY_BASE_IMPORTS = "RULE_NO_HEAVY_BASE_IMPORTS"
RULE_DATABASE_INVARIANTS = "RULE_DATABASE_INVARIANTS"
RULE_SECRET_REDACTION = "RULE_SECRET_REDACTION"
RULE_LAYER_DIRECTION = "RULE_LAYER_DIRECTION"

ALL_RULES: Tuple[str, ...] = (
    RULE_CORE_ISOLATION,
    RULE_INTERFACE_ISOLATION,
    RULE_NO_HEAVY_BASE_IMPORTS,
    RULE_DATABASE_INVARIANTS,
    RULE_SECRET_REDACTION,
    RULE_LAYER_DIRECTION,
)

# ---------------------------------------------------------------------------
# Forbidden dependency sets (§22.1)
# ---------------------------------------------------------------------------

#: Heavy optional third-party distributions that must never be imported by
#: base modules. Top-level package names as seen in ``import`` statements.
HEAVY_TOP_LEVEL_MODULES: frozenset = frozenset(
    {
        "torch",
        "whisper",
        "faster_whisper",
        "comet",
        "onnxruntime",
        "fastapi",
        "uvicorn",
        "openai",
        "anthropic",
        "mcp",
        "sacrebleu",
        "libreoffice",
        "uno",
    }
)

#: Concrete infrastructure packages that base-core modules must never import.
CORE_FORBIDDEN_TARJOMAN_PREFIXES: Tuple[str, ...] = (
    "tarjoman.storage",
    "tarjoman.providers",
    "tarjoman.interfaces",
    "tarjoman.audio",
    "tarjoman.stages",
)

#: Base-core modules under strict isolation. ``tarjoman.core.pipeline`` is
#: deliberately excluded: it is the legacy 5-pass wiring module scheduled to
#: move to the application layer (TRN track); contracts/errors/config/logging
#: are the normative base surface per §22.1.
BASE_CORE_PREFIXES: Tuple[str, ...] = (
    "tarjoman.core.contracts",
    "tarjoman.core.errors",
    "tarjoman.core.config",
    "tarjoman.core.logging",
)

#: Base scopes covered by RULE_NO_HEAVY_BASE_IMPORTS (top-level imports only;
#: lazy function-level imports of extras remain legal, e.g. ``typst``).
HEAVY_CHECK_SCOPES: Tuple[str, ...] = (
    "tarjoman.core",
    "tarjoman.quality",
    "tarjoman.storage",
)

#: Application must never depend on concrete infrastructure (§22.2).
APPLICATION_FORBIDDEN_PREFIXES: Tuple[str, ...] = (
    "tarjoman.storage",
    "tarjoman.providers",
    "tarjoman.interfaces",
    "tarjoman.audio",
)

#: Adapters must never call interface code (§22.1: adapters do not call CLI/API/MCP).
INFRASTRUCTURE_SCOPES: Tuple[str, ...] = (
    "tarjoman.storage",
    "tarjoman.providers",
    "tarjoman.memory",
    "tarjoman.ingest",
    "tarjoman.export",
    "tarjoman.audio",
)

INFRASTRUCTURE_FORBIDDEN_PREFIXES: Tuple[str, ...] = (
    "tarjoman.interfaces",
    "tarjoman.cli",
)

#: Canonical public job states (D38, §4.8) — enforced on the jobs CHECK constraint.
CANONICAL_JOB_STATES: Tuple[str, ...] = (
    "QUEUED",
    "RUNNING",
    "WAITING_REVIEW",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
)


# ---------------------------------------------------------------------------
# Report types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArchitectureViolation:
    """A single architecture-boundary violation.

    Attributes:
        rule_id: One of the ``RULE_*`` identifiers.
        file: Source file (absolute or root-relative) where found.
        line: 1-based line number (0 when the violation is file-level).
        message: Human-readable diagnostic for CI output.
    """

    rule_id: str
    file: str
    line: int
    message: str

    def to_dict(self) -> Dict[str, object]:
        """Serialize the violation to a plain dictionary."""
        return {
            "rule_id": self.rule_id,
            "file": self.file,
            "line": self.line,
            "message": self.message,
        }


class ArchitectureViolationError(Exception):
    """Raised by :meth:`ArchitectureConformanceChecker.enforce` on violation."""

    def __init__(self, violations: Sequence[ArchitectureViolation]) -> None:
        self.violations: List[ArchitectureViolation] = list(violations)
        summary = "\n".join(
            f"  [{v.rule_id}] {v.file}:{v.line}: {v.message}"
            for v in self.violations
        )
        super().__init__(
            f"Architecture conformance failed with "
            f"{len(self.violations)} violation(s):\n{summary}"
        )


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------


@dataclass
class _ImportRecord:
    """One resolved absolute import with its source location."""

    imported: str
    line: int
    toplevel: bool


class _ImportVisitor(ast.NodeVisitor):
    """Collects imports, tracking whether each is module top-level.

    Imports nested inside ``def``/``class`` bodies are lazy (legal for
    optional extras); only module-level imports participate in
    RULE_NO_HEAVY_BASE_IMPORTS.
    """

    def __init__(self, module_name: str) -> None:
        self._module_name = module_name
        self._depth = 0
        self.records: List[_ImportRecord] = []

    def _record(self, dotted: str, line: int) -> None:
        if dotted:
            self.records.append(
                _ImportRecord(
                    imported=dotted, line=line, toplevel=self._depth == 0
                )
            )

    def _resolve_relative(self, level: int, module: Optional[str]) -> str:
        if level == 0:
            return module or ""
        package = self._module_name.rpartition(".")[0]
        for _ in range(level - 1):
            package = package.rpartition(".")[0]
        if module:
            return f"{package}.{module}" if package else module
        return package

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self._record(alias.name, node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        base = self._resolve_relative(node.level, node.module)
        if node.names and any(a.name == "*" for a in node.names):
            self._record(base, node.lineno)
        else:
            for alias in node.names:
                full = f"{base}.{alias.name}" if base else alias.name
                self._record(full, node.lineno)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1


def _top_package(dotted: str) -> str:
    return dotted.split(".")[0]


def _module_name_for(path: Path, root: Path) -> str:
    """Derive dotted module name of ``path`` relative to package ``root``."""
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return path.stem
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    anchor = "tarjoman"
    if anchor in parts:
        parts = parts[parts.index(anchor):]
    else:
        parts = [anchor, *parts]
    return ".".join(parts)


def _in_scope(module: str, scopes: Tuple[str, ...]) -> bool:
    return module == scopes[0] or any(
        module == s or module.startswith(s + ".") for s in scopes
    )


def _matches_prefix(dotted: str, prefixes: Tuple[str, ...]) -> Optional[str]:
    for prefix in prefixes:
        if dotted == prefix or dotted.startswith(prefix + "."):
            return prefix
    return None


# ---------------------------------------------------------------------------
# SQL / secret helpers
# ---------------------------------------------------------------------------

_SQL_LINE_COMMENT_RE = re.compile(r"--.*?$", re.MULTILINE)
_SQL_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_BLOB_COLUMN_RE = re.compile(r"\b[A-Za-z_][\w$]*\s+BLOB\b", re.IGNORECASE)

# Patterns matching real hardcoded credentials (not regex source).
_SECRET_LITERAL_RES = (
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{34,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def _strip_sql_comments(sql: str) -> str:
    no_block = _SQL_BLOCK_COMMENT_RE.sub(" ", sql)
    return _SQL_LINE_COMMENT_RE.sub("", no_block)


def _looks_like_regex_source(value: str) -> bool:
    """Heuristic: redaction *patterns* contain regex syntax; real secrets do not."""
    markers = ("\\b", "\\s", "\\d", "\\w", "(?i)", "[A-Za-z", "[A-Z ", ".*?", "+)")
    return any(m in value for m in markers)


def _string_constants(tree: ast.AST) -> List[Tuple[str, int]]:
    found: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append((node.value, getattr(node, "lineno", 0)))
    return found


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------


class ArchitectureConformanceChecker:
    """AST-based architecture-boundary checker (§22, §23.2, §25.5, §47).

    Interface:
        - ``check()`` — scan the tree, return violations (pure result).
        - ``enforce()`` — like ``check()`` but raise on any violation (CI gate).
        - ``check_snippet()`` — check an in-memory source string (tests/synthetic).
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        if root is None:
            root = Path(__file__).resolve().parent.parent
        self.root: Path = Path(root)

    # -- public ---------------------------------------------------------
    def check(self) -> List[ArchitectureViolation]:
        """Scan the package tree and return all violations (empty when clean)."""
        violations: List[ArchitectureViolation] = []
        for path in sorted(self.root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            violations.extend(self._check_file(path))
        violations.extend(self._check_migrations())
        violations.extend(self._check_secret_structure())
        return sorted(violations, key=lambda v: (v.file, v.line, v.rule_id))

    def enforce(self) -> None:
        """Raise :class:`ArchitectureViolationError` if any violation exists."""
        violations = self.check()
        if violations:
            raise ArchitectureViolationError(violations)

    def check_snippet(
        self, source: str, module_name: str, filename: str = "<snippet>"
    ) -> List[ArchitectureViolation]:
        """Check an in-memory source string as ``module_name``.

        Used by tests to prove synthetic violations fail with diagnostics
        without touching the real tree. Non-Python snippets (e.g. raw SQL)
        fall back to SQL/secret scanning instead of raising SyntaxError.
        """
        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError:
            out: List[ArchitectureViolation] = []
            out.extend(self._check_sql_text(source, filename, checker="sql"))
            for pattern in _SECRET_LITERAL_RES:
                if pattern.search(source):
                    out.append(
                        ArchitectureViolation(
                            rule_id=RULE_SECRET_REDACTION,
                            file=filename,
                            line=1,
                            message=(
                                "hardcoded credential literal detected; secrets "
                                "must come from environment/keyring only (§23.2)"
                            ),
                        )
                    )
                    break
            return out
        visitor = _ImportVisitor(module_name)
        visitor.visit(tree)
        out = []
        for record in visitor.records:
            out.extend(
                self._check_import_rules(module_name, record, filename)
            )
        out.extend(self._check_sql_text(source, filename, checker="snippet"))
        out.extend(self._check_secret_literals(tree, filename))
        return out

    # -- per-file -------------------------------------------------------
    def _check_file(self, path: Path) -> List[ArchitectureViolation]:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            return [
                ArchitectureViolation(
                    rule_id=RULE_CORE_ISOLATION,
                    file=str(path),
                    line=exc.lineno or 0,
                    message=f"unparseable Python file: {exc.msg}",
                )
            ]
        module = _module_name_for(path, self.root)
        visitor = _ImportVisitor(module)
        visitor.visit(tree)
        display = str(path)
        out: List[ArchitectureViolation] = []
        for record in visitor.records:
            out.extend(self._check_import_rules(module, record, display))
        out.extend(self._check_sql_text(text, display, checker="py"))
        out.extend(self._check_secret_literals(tree, display))
        return out

    def _check_import_rules(
        self, module: str, record: _ImportRecord, display: str
    ) -> List[ArchitectureViolation]:
        out: List[ArchitectureViolation] = []
        imported = record.imported
        top = _top_package(imported)

        # RULE_CORE_ISOLATION — base-core modules only.
        if _in_scope(module, BASE_CORE_PREFIXES):
            hit = _matches_prefix(imported, CORE_FORBIDDEN_TARJOMAN_PREFIXES)
            if hit:
                out.append(
                    ArchitectureViolation(
                        rule_id=RULE_CORE_ISOLATION,
                        file=display,
                        line=record.line,
                        message=(
                            f"base-core module '{module}' must not import "
                            f"'{imported}' (forbidden scope '{hit}')"
                        ),
                    )
                )
            if top in HEAVY_TOP_LEVEL_MODULES:
                out.append(
                    ArchitectureViolation(
                        rule_id=RULE_CORE_ISOLATION,
                        file=display,
                        line=record.line,
                        message=(
                            f"base-core module '{module}' must not import "
                            f"heavy optional dependency '{imported}'"
                        ),
                    )
                )

        # RULE_NO_HEAVY_BASE_IMPORTS — top-level only; lazy imports are legal.
        if record.toplevel and _in_scope(module, HEAVY_CHECK_SCOPES):
            if top in HEAVY_TOP_LEVEL_MODULES:
                out.append(
                    ArchitectureViolation(
                        rule_id=RULE_NO_HEAVY_BASE_IMPORTS,
                        file=display,
                        line=record.line,
                        message=(
                            f"base module '{module}' must not top-level import "
                            f"heavy optional dependency '{imported}'; "
                            f"use a lazy function-level import inside the extra"
                        ),
                    )
                )

        # RULE_INTERFACE_ISOLATION — one interface never imports another.
        if module.startswith("tarjoman.interfaces."):
            parts = module.split(".")
            own = parts[2] if len(parts) > 2 else ""
            if imported.startswith("tarjoman.interfaces."):
                iparts = imported.split(".")
                other = iparts[2] if len(iparts) > 2 else ""
                if other and other != own:
                    out.append(
                        ArchitectureViolation(
                            rule_id=RULE_INTERFACE_ISOLATION,
                            file=display,
                            line=record.line,
                            message=(
                                f"interface '{own}' must not import interface "
                                f"'{other}' ('{imported}')"
                            ),
                        )
                    )

        # RULE_LAYER_DIRECTION — application and adapter direction.
        if module.startswith("tarjoman.application"):
            hit = _matches_prefix(imported, APPLICATION_FORBIDDEN_PREFIXES)
            if hit:
                out.append(
                    ArchitectureViolation(
                        rule_id=RULE_LAYER_DIRECTION,
                        file=display,
                        line=record.line,
                        message=(
                            f"application module '{module}' must not import "
                            f"concrete infrastructure '{imported}' "
                            f"(scope '{hit}'); depend on core ports instead"
                        ),
                    )
                )
        if _in_scope(module, INFRASTRUCTURE_SCOPES):
            hit = _matches_prefix(imported, INFRASTRUCTURE_FORBIDDEN_PREFIXES)
            if hit:
                out.append(
                    ArchitectureViolation(
                        rule_id=RULE_LAYER_DIRECTION,
                        file=display,
                        line=record.line,
                        message=(
                            f"infrastructure module '{module}' must not import "
                            f"interface code '{imported}'"
                        ),
                    )
                )
        return out

    # -- SQL ------------------------------------------------------------
    def _check_migrations(self) -> List[ArchitectureViolation]:
        out: List[ArchitectureViolation] = []
        migrations_dir = self.root / "storage" / "migrations"
        if migrations_dir.is_dir():
            for sql_path in sorted(migrations_dir.glob("*.sql")):
                try:
                    text = sql_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                out.extend(self._check_sql_text(text, str(sql_path), checker="sql"))
        return out

    def _check_sql_text(
        self, text: str, display: str, checker: str
    ) -> List[ArchitectureViolation]:
        """Flag BLOB column declarations (D20) in SQL or inline SQL strings."""
        haystack = text if checker == "sql" else self._inline_sql(text)
        if checker == "py" and not haystack:
            return []
        target = (
            _strip_sql_comments(haystack)
            if checker == "sql"
            else _strip_sql_comments(haystack)
        )
        out: List[ArchitectureViolation] = []
        for match in _BLOB_COLUMN_RE.finditer(target):
            line = target.count("\n", 0, match.start()) + 1
            out.append(
                ArchitectureViolation(
                    rule_id=RULE_DATABASE_INVARIANTS,
                    file=display,
                    line=line,
                    message=(
                        "SQLite schema must not declare BLOB columns for large "
                        f"files (D20); found '{match.group(0).strip()}'"
                    ),
                )
            )
        return out

    @staticmethod
    def _inline_sql(python_source: str) -> str:
        """Extract string chunks that look like inline CREATE TABLE statements."""
        try:
            tree = ast.parse(python_source)
        except SyntaxError:
            return ""
        chunks: List[str] = []
        for value, _ in _string_constants(tree):
            if "CREATE TABLE" in value.upper():
                chunks.append(value)
        return "\n".join(chunks)

    # -- secrets --------------------------------------------------------
    def _check_secret_structure(self) -> List[ArchitectureViolation]:
        """Verify error/logger modules structurally enforce redaction (D16)."""
        out: List[ArchitectureViolation] = []
        errors_path = self.root / "core" / "errors.py"
        logging_path = self.root / "core" / "logging.py"

        def _load(path: Path) -> Optional[ast.AST]:
            try:
                return ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                return None

        errors_tree = _load(errors_path) if errors_path.is_file() else None
        if errors_tree is None:
            out.append(
                ArchitectureViolation(
                    rule_id=RULE_SECRET_REDACTION,
                    file=str(errors_path),
                    line=0,
                    message="core/errors.py is missing or unparseable",
                )
            )
        else:
            defined = {
                node.name
                for node in errors_tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            classes = {
                node.name
                for node in errors_tree.body
                if isinstance(node, ast.ClassDef)
            }
            for required in ("sanitize_error_message", "sanitize_details"):
                if required not in defined:
                    out.append(
                        ArchitectureViolation(
                            rule_id=RULE_SECRET_REDACTION,
                            file=str(errors_path),
                            line=0,
                            message=(
                                f"core/errors.py must define '{required}' (§23.2)"
                            ),
                        )
                    )
            if "TarjomanError" not in classes:
                out.append(
                    ArchitectureViolation(
                        rule_id=RULE_SECRET_REDACTION,
                        file=str(errors_path),
                        line=0,
                        message="core/errors.py must define 'TarjomanError'",
                    )
                )
            else:
                for node in ast.walk(errors_tree):
                    if (
                        isinstance(node, ast.ClassDef)
                        and node.name == "TarjomanError"
                    ):
                        src = ast.dump(node)
                        if "sanitize_error_message" not in src:
                            out.append(
                                ArchitectureViolation(
                                    rule_id=RULE_SECRET_REDACTION,
                                    file=str(errors_path),
                                    line=node.lineno,
                                    message=(
                                        "TarjomanError must sanitize messages "
                                        "via sanitize_error_message (§23.2/D16)"
                                    ),
                                )
                            )

        logging_tree = _load(logging_path) if logging_path.is_file() else None
        if logging_tree is None:
            out.append(
                ArchitectureViolation(
                    rule_id=RULE_SECRET_REDACTION,
                    file=str(logging_path),
                    line=0,
                    message="core/logging.py is missing or unparseable",
                )
            )
        else:
            defined_logging = {
                node.name
                for node in ast.walk(logging_tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            logged_classes = {
                node.name
                for node in ast.walk(logging_tree)
                if isinstance(node, ast.ClassDef)
            }
            if "redact_secrets" not in defined_logging:
                out.append(
                    ArchitectureViolation(
                        rule_id=RULE_SECRET_REDACTION,
                        file=str(logging_path),
                        line=0,
                        message=(
                            "core/logging.py must define 'redact_secrets' (§23.2)"
                        ),
                    )
                )
            if "RedactionFilter" not in logged_classes:
                out.append(
                    ArchitectureViolation(
                        rule_id=RULE_SECRET_REDACTION,
                        file=str(logging_path),
                        line=0,
                        message=(
                            "core/logging.py must define 'RedactionFilter' (§23.2)"
                        ),
                    )
                )
        return out

    def _check_secret_literals(
        self, tree: ast.AST, display: str
    ) -> List[ArchitectureViolation]:
        """Flag hardcoded credential literals (patterns-as-regex are skipped)."""
        out: List[ArchitectureViolation] = []
        for value, lineno in _string_constants(tree):
            if _looks_like_regex_source(value):
                continue
            if "REDACTED" in value or "EXCLUDED" in value:
                continue
            for pattern in _SECRET_LITERAL_RES:
                if pattern.search(value):
                    out.append(
                        ArchitectureViolation(
                            rule_id=RULE_SECRET_REDACTION,
                            file=display,
                            line=lineno,
                            message=(
                                "hardcoded credential literal detected; secrets "
                                "must come from environment/keyring only (§23.2)"
                            ),
                        )
                    )
                    break
        return out


def format_report(violations: Sequence[ArchitectureViolation]) -> str:
    """Render violations as human-readable CI output."""
    if not violations:
        return "Architecture conformance: clean (no violations)."
    lines = [
        f"Architecture conformance: {len(violations)} violation(s) found:"
    ]
    for v in violations:
        lines.append(f"  [{v.rule_id}] {v.file}:{v.line}: {v.message}")
    return "\n".join(lines)


__all__ = [
    "RULE_CORE_ISOLATION",
    "RULE_INTERFACE_ISOLATION",
    "RULE_NO_HEAVY_BASE_IMPORTS",
    "RULE_DATABASE_INVARIANTS",
    "RULE_SECRET_REDACTION",
    "RULE_LAYER_DIRECTION",
    "ALL_RULES",
    "HEAVY_TOP_LEVEL_MODULES",
    "CANONICAL_JOB_STATES",
    "ArchitectureViolation",
    "ArchitectureViolationError",
    "ArchitectureConformanceChecker",
    "format_report",
]
