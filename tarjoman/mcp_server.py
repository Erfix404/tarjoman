"""Zero-dependency JSON-RPC 2.0 MCP server over stdio for Tarjoman."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TextIO, Tuple

from tarjoman import __version__
from tarjoman.domains.router import DomainRouter
from tarjoman.fixer import fix_text
from tarjoman.linter import VALID_STYLES, issues_to_dict, lint_text
from tarjoman.memory.context_builder import build_book_context
from tarjoman.memory.fidelity import check_fidelity
from tarjoman.parsers.i18n import check_i18n
from tarjoman.parsers.srt import check_srt

_DEFAULT_REFS_DIR = (
    Path(__file__).resolve().parent.parent / ".claude" / "skills" / "tarjoman" / "references"
)

_MODE_GUIDE_MAP: Dict[str, List[str]] = {
    "edit": ["editor.md", "editor-najafi.md"],
    "naturalize": ["naturalize.md"],
    "colloquialize": ["colloquialize.md", "colloquial.md"],
    "subtitles": ["subtitles.md", "colloquial.md"],
    "chat": ["colloquial.md"],
}

_DOMAIN_GUIDE_MAP: Dict[str, List[str]] = {
    "literary": ["literary.md", "fidelity.md"],
    "scientific": ["scientific.md"],
    "philosophy": ["philosophy.md"],
    "legal": ["legal.md"],
    "technical": ["technical.md"],
    "medical": ["medical.md"],
    "media": ["media.md"],
    "financial": ["financial.md"],
    "classical": ["classical.md"],
    "transcreation": ["transcreation.md"],
}

_CHAT_RE = re.compile(r"\b(?:lol|lmao|idk|omg|btw|imho|brb|gonna|wanna)\b", re.IGNORECASE)
_SRT_RE = re.compile(r"(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}\s*-->\s*(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}")
_PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")


def _extract_glance(guide_path: Path) -> str:
    if not guide_path.exists():
        return ""
    lines = guide_path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index("## در یک نگاه")
    except ValueError:
        return "\n".join(lines[:15]).strip()
    out: List[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if line.strip():
            out.append(line)
    return "\n".join(out).strip()


def _tool_route_guide(
    args: Dict[str, Any], refs_dir: Path = _DEFAULT_REFS_DIR
) -> Dict[str, Any]:
    text = args.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("'text' must be a non-empty string.")
    mode = str(args.get("mode") or "translate").strip().lower()
    if mode not in ("translate", "edit", "naturalize", "colloquialize", "subtitles", "chat"):
        raise ValueError(f"Unsupported mode '{mode}'.")

    confidence = 1.0
    domain = mode
    if mode in _MODE_GUIDE_MAP:
        guide_names = list(_MODE_GUIDE_MAP[mode])
    else:
        if _SRT_RE.search(text) or text.lstrip().startswith("WEBVTT"):
            domain = "subtitles"
            guide_names = list(_MODE_GUIDE_MAP["subtitles"])
        elif _CHAT_RE.search(text):
            domain = "chat"
            confidence = 0.85
            guide_names = list(_MODE_GUIDE_MAP["chat"])
        elif _PERSIAN_RE.search(text) and not re.search(r"[A-Za-z]{4,}", text):
            domain = "edit"
            confidence = 0.80
            guide_names = list(_MODE_GUIDE_MAP["edit"])
        else:
            profile, confidence = DomainRouter().route(text)
            domain = profile.id.value
            guide_names = list(_DOMAIN_GUIDE_MAP.get(domain, ["literary.md"]))

    guides = []
    for name in guide_names:
        path = refs_dir / name
        guides.append(
            {
                "name": name,
                "path": f".claude/skills/tarjoman/references/{name}",
                "glance": _extract_glance(path),
            }
        )
    return {
        "mode": mode,
        "domain": domain,
        "confidence": confidence,
        "guides": guides,
    }


def _tool_lint(args: Dict[str, Any]) -> Dict[str, Any]:
    text = args.get("text")
    if not isinstance(text, str):
        raise ValueError("'text' must be a string.")
    style = args.get("style")
    only = args.get("only")
    errors_only = bool(args.get("errors_only", False))
    issues = lint_text(text, style=style)
    if only:
        wanted = {str(c).lower() for c in only}
        issues = [i for i in issues if i.category.lower() in wanted]
    if errors_only:
        issues = [i for i in issues if i.severity == "error"]
    return issues_to_dict("<inline>", issues)


def _tool_fix_safe(args: Dict[str, Any]) -> Dict[str, Any]:
    text = args.get("text")
    if not isinstance(text, str):
        raise ValueError("'text' must be a string.")
    res = fix_text(text)
    return {
        "text": res.text,
        "changed": res.changed,
        "total_fixes": res.total_fixes,
        "counts": res.counts,
    }


def _tool_verify(args: Dict[str, Any]) -> Dict[str, Any]:
    source = args.get("source")
    target = args.get("target")
    if not isinstance(source, str) or not isinstance(target, str):
        raise ValueError("'source' and 'target' must be strings.")
    findings = check_fidelity(source, target)
    return {
        "passed": len(findings) == 0,
        "total": len(findings),
        "findings": [{"category": f.category, "message": f.message} for f in findings],
    }


def _tool_book_context(args: Dict[str, Any]) -> Dict[str, Any]:
    project_dir = args.get("project_dir")
    source_chunk = args.get("source_chunk")
    if not isinstance(project_dir, str) or not isinstance(source_chunk, str):
        raise ValueError("'project_dir' and 'source_chunk' must be strings.")
    prev = args.get("previous_translation")
    tail = int(args.get("tail_paragraphs", 2))
    return build_book_context(
        project_dir=project_dir,
        source_chunk=source_chunk,
        previous_translation=prev if isinstance(prev, str) else None,
        tail_paragraphs=tail,
    )


def _tool_srt_check(args: Dict[str, Any]) -> Dict[str, Any]:
    target_text = args.get("target_text")
    if not isinstance(target_text, str):
        raise ValueError("'target_text' must be a string.")
    source_text = args.get("source_text")
    max_chars = int(args.get("max_chars", 42))
    max_lines = int(args.get("max_lines", 2))
    max_cps = float(args.get("max_cps", 17.0))
    findings = check_srt(
        source_text if isinstance(source_text, str) else None,
        target_text,
        max_chars=max_chars,
        max_lines=max_lines,
        max_cps=max_cps,
    )
    return {
        "passed": len(findings) == 0,
        "total": len(findings),
        "findings": [
            {"cue": f.cue, "category": f.category, "message": f.message}
            for f in findings
        ],
    }


def _tool_i18n_check(args: Dict[str, Any]) -> Dict[str, Any]:
    source_path = args.get("source_path")
    target_path = args.get("target_path")
    if not isinstance(source_path, str) or not isinstance(target_path, str):
        raise ValueError("'source_path' and 'target_path' must be strings.")
    ratio_raw = args.get("max_length_ratio")
    ratio = float(ratio_raw) if ratio_raw is not None else None
    findings = check_i18n(source_path, target_path, max_length_ratio=ratio)
    return {
        "passed": len(findings) == 0,
        "total": len(findings),
        "findings": [
            {"key": f.key, "category": f.category, "message": f.message}
            for f in findings
        ],
    }


_TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "tarjoman_route_guide",
        "description": "Detect the translation/editing domain and return the matching Persian reference guide paths and «در یک نگاه» summaries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Source or Persian text sample."},
                "mode": {
                    "type": "string",
                    "enum": ["translate", "edit", "naturalize", "colloquialize", "subtitles", "chat"],
                    "default": "translate",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "tarjoman_lint",
        "description": "Lint Persian text for orthography errors, calques, AI tells, register leaks, and bidi issues.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "style": {"type": "string", "enum": list(VALID_STYLES)},
                "only": {"type": "array", "items": {"type": "string"}},
                "errors_only": {"type": "boolean", "default": False},
            },
            "required": ["text"],
        },
    },
    {
        "name": "tarjoman_fix_safe",
        "description": "Apply safe, non-semantic orthography fixes (Arabic ی/ک, ZWNJ, tanvin, punctuation) while shielding code, LaTeX, URLs, and placeholders.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "tarjoman_verify",
        "description": "Check completeness/fidelity between source and Persian translation (paragraphs, numbers, citations, URLs, code, LaTeX, placeholders, headings, tables).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
            },
            "required": ["source", "target"],
        },
    },
    {
        "name": "tarjoman_book_context",
        "description": "Extract minimal chunk-relevant book memory (matched glossary terms, character voices, scene state, cascades, and previous tail).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string"},
                "source_chunk": {"type": "string"},
                "previous_translation": {"type": "string"},
                "tail_paragraphs": {"type": "integer", "default": 2},
            },
            "required": ["project_dir", "source_chunk"],
        },
    },
    {
        "name": "tarjoman_srt_check",
        "description": "Validate translated SRT or WebVTT subtitle text for timing alignment, line length, reading speed, and residue.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_text": {"type": "string"},
                "source_text": {"type": "string"},
                "max_chars": {"type": "integer", "default": 42},
                "max_lines": {"type": "integer", "default": 2},
                "max_cps": {"type": "number", "default": 17.0},
            },
            "required": ["target_text"],
        },
    },
    {
        "name": "tarjoman_i18n_check",
        "description": "Validate localized JSON, ARB, PO, or YAML files against source keys, placeholders, HTML tags, count plurals, and length limits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string"},
                "target_path": {"type": "string"},
                "max_length_ratio": {"type": "number"},
            },
            "required": ["source_path", "target_path"],
        },
    },
]


class TarjomanMcpServer:
    """Stdio JSON-RPC 2.0 server exposing Tarjoman deterministic tools."""

    def __init__(self, refs_dir: Optional[Path] = None) -> None:
        self.refs_dir = refs_dir or _DEFAULT_REFS_DIR
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "tarjoman_route_guide": lambda a: _tool_route_guide(a, refs_dir=self.refs_dir),
            "tarjoman_lint": _tool_lint,
            "tarjoman_fix_safe": _tool_fix_safe,
            "tarjoman_verify": _tool_verify,
            "tarjoman_book_context": _tool_book_context,
            "tarjoman_srt_check": _tool_srt_check,
            "tarjoman_i18n_check": _tool_i18n_check,
        }

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }

    @staticmethod
    def _ok(req_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return self._error(
                request.get("id") if isinstance(request, dict) else None,
                -32600,
                "Invalid JSON-RPC 2.0 request.",
            )
        method = request.get("method")
        req_id = request.get("id")
        if method == "notifications/initialized" or (
            isinstance(method, str) and method.startswith("notifications/") and req_id is None
        ):
            return None
        if req_id is None:
            return None
        if not isinstance(method, str):
            return self._error(req_id, -32600, "Missing method.")

        if method == "initialize":
            return self._ok(
                req_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "tarjoman", "version": __version__},
                },
            )
        if method == "ping":
            return self._ok(req_id, {})
        if method == "tools/list":
            return self._ok(req_id, {"tools": _TOOL_DEFINITIONS})
        if method == "tools/call":
            params = request.get("params")
            if not isinstance(params, dict):
                return self._error(req_id, -32602, "params must be an object.")
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(tool_name, str) or tool_name not in self._handlers:
                return self._error(req_id, -32602, f"Unknown tool: {tool_name!r}")
            if not isinstance(arguments, dict):
                return self._error(req_id, -32602, "arguments must be an object.")
            try:
                payload = self._handlers[tool_name](arguments)
            except ValueError as exc:
                return self._error(req_id, -32602, str(exc))
            except Exception as exc:
                err_payload = {"error": str(exc)}
                return self._ok(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(err_payload, ensure_ascii=False),
                            }
                        ],
                        "isError": True,
                    },
                )
            return self._ok(
                req_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload, ensure_ascii=False, indent=2),
                        }
                    ],
                    "structuredContent": payload,
                    "isError": False,
                },
            )

        return self._error(req_id, -32601, f"Method not found: {method}")

    def serve_stdio(
        self, stdin: Optional[TextIO] = None, stdout: Optional[TextIO] = None
    ) -> None:
        in_stream = stdin if stdin is not None else sys.stdin
        out_stream = stdout if stdout is not None else sys.stdout
        for raw in in_stream:
            line = raw.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                resp: Optional[Dict[str, Any]] = self._error(None, -32700, f"Parse error: {exc}")
            else:
                resp = self.handle_request(req)
            if resp is not None:
                out_stream.write(json.dumps(resp, ensure_ascii=False) + "\n")
                out_stream.flush()
