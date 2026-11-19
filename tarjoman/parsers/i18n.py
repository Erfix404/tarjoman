"""Localization file checker (JSON, ARB, PO, YAML) for Tarjoman."""
from __future__ import annotations

import ast
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from tarjoman.linter import _COUNT_PLURAL_RE

_PLACEHOLDER_RE = re.compile(
    r"\{\{[^}\n]+\}\}"
    r"|(?<!\{)\{[A-Za-z_][A-Za-z0-9_]*(?::[^}\n]+)?\}(?!\})"
    r"|(?<![0-9۰-۹])%(?:\([A-Za-z_][A-Za-z0-9_]*\))?[#0\-+]*[0-9]*(?:\.[0-9]+)?[sdifuxXeEgG]"
    r"|%\d+\$[sdif]"
    r"|\$[1-9](?![0-9.,])"
)
_HTML_TAG_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9:-]*)(?:\s[^>\n]*)?/?>")
_URL_RE = re.compile(r"https?://\S+")


@dataclass
class I18nFinding:
    key: str
    category: str
    message: str


def _flatten_json(obj: Any, prefix: str = "", out: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str) or k.startswith("@"):
                continue
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                _flatten_json(v, full_key, out)
            elif isinstance(v, str):
                out[full_key] = v
    return out


def _unquote_po(fragment: str) -> str:
    return str(ast.literal_eval(fragment))


def _parse_po(text: str) -> Dict[str, str]:
    entries: Dict[str, str] = {}
    msgctxt: Optional[str] = None
    msgid_parts: List[str] = []
    msgstr_parts: List[str] = []
    mode: Optional[str] = None

    def _flush() -> None:
        nonlocal msgctxt, msgid_parts, msgstr_parts, mode
        if msgid_parts or msgstr_parts:
            msgid = "".join(msgid_parts)
            msgstr = "".join(msgstr_parts)
            if msgid:
                key = f"{msgctxt}::{msgid}" if msgctxt else msgid
                entries[key] = msgstr
        msgctxt = None
        msgid_parts = []
        msgstr_parts = []
        mode = None

    for raw in text.replace("\r\n", "\n").splitlines():
        line = raw.strip()
        if not line:
            _flush()
            continue
        if line.startswith("#"):
            continue
        if line.startswith("msgctxt "):
            _flush()
            msgctxt = _unquote_po(line[len("msgctxt ") :].strip())
            mode = "msgctxt"
        elif line.startswith("msgid "):
            if mode == "msgstr":
                _flush()
            msgid_parts.append(_unquote_po(line[len("msgid ") :].strip()))
            mode = "msgid"
        elif line.startswith("msgstr "):
            msgstr_parts.append(_unquote_po(line[len("msgstr ") :].strip()))
            mode = "msgstr"
        elif line.startswith("msgstr["):
            idx_end = line.find("]")
            if idx_end != -1:
                if line[7:idx_end] == "0":
                    msgstr_parts.append(_unquote_po(line[idx_end + 1 :].strip()))
                mode = "msgstr_plural"
        elif line.startswith('"') and line.endswith('"'):
            piece = _unquote_po(line)
            if mode == "msgid":
                msgid_parts.append(piece)
            elif mode == "msgstr":
                msgstr_parts.append(piece)
            elif mode == "msgctxt":
                msgctxt = (msgctxt or "") + piece
    _flush()
    return entries


def _strip_yaml_comment(raw: str) -> str:
    in_single = False
    in_double = False
    for idx, ch in enumerate(raw):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single and (idx == 0 or raw[idx - 1] != "\\"):
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and (idx == 0 or raw[idx - 1].isspace()):
            return raw[:idx].rstrip()
    return raw.rstrip()


def _parse_yaml_scalar(val: str) -> str:
    val = val.strip()
    if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
        try:
            return str(ast.literal_eval(val))
        except Exception:
            return val[1:-1]
    if len(val) >= 2 and val.startswith("'") and val.endswith("'"):
        return val[1:-1].replace("''", "'")
    return val


def _parse_yaml_map(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    stack: List[Tuple[int, str]] = []
    for raw in text.replace("\r\n", "\n").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()
        if stripped in ("---", "..."):
            continue
        if stripped.startswith("- "):
            continue
        cleaned = _strip_yaml_comment(raw)
        if ":" not in cleaned:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key_part, _, val_part = cleaned.lstrip(" ").partition(":")
        key = _parse_yaml_scalar(key_part)
        if not key:
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        val_trimmed = val_part.strip()
        if not val_trimmed:
            stack.append((indent, key))
        else:
            prefix = ".".join(item[1] for item in stack)
            full_key = f"{prefix}.{key}" if prefix else key
            out[full_key] = _parse_yaml_scalar(val_trimmed)
    return out


def load_i18n_file(path: Union[str, Path]) -> Dict[str, str]:
    """Load string translations from .json, .arb, .po, or .yaml/.yml."""
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8-sig")
    suffix = file_path.suffix.lower()
    if suffix in (".json", ".arb"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object in {file_path}")
        return _flatten_json(data)
    if suffix == ".po":
        return _parse_po(text)
    if suffix in (".yaml", ".yml"):
        return _parse_yaml_map(text)
    raise ValueError(f"Unsupported i18n format '{suffix}' (supported: .json, .arb, .po, .yaml, .yml)")


def _tag_multiset(text: str) -> Counter[str]:
    return Counter(f"{m.group(1)}{m.group(2).lower()}" for m in _HTML_TAG_RE.finditer(text))


def check_i18n_maps(
    source: Dict[str, str],
    target: Dict[str, str],
    max_length_ratio: Optional[float] = None,
) -> List[I18nFinding]:
    """Check aligned source->target localization dictionaries."""
    findings: List[I18nFinding] = []

    for key in sorted(source):
        if key not in target:
            findings.append(
                I18nFinding(key, "missing-key", f"Key «{key}» is missing in target.")
            )
    for key in sorted(target):
        if key not in source:
            findings.append(
                I18nFinding(key, "extra-key", f"Extra key «{key}» is not present in source.")
            )

    for key in sorted(set(source) & set(target)):
        src = source[key]
        tgt = target[key]
        if src.strip() and not tgt.strip():
            findings.append(
                I18nFinding(key, "empty", f"Translation for «{key}» is empty.")
            )
            continue

        src_ph = Counter(_PLACEHOLDER_RE.findall(src))
        tgt_ph = Counter(_PLACEHOLDER_RE.findall(tgt))
        if src_ph != tgt_ph:
            findings.append(
                I18nFinding(
                    key,
                    "placeholder",
                    f"Placeholder mismatch for «{key}»: source={dict(src_ph)}, target={dict(tgt_ph)}.",
                )
            )

        src_tags = _tag_multiset(src)
        tgt_tags = _tag_multiset(tgt)
        if src_tags != tgt_tags:
            findings.append(
                I18nFinding(
                    key,
                    "html-tag",
                    f"HTML tag mismatch for «{key}»: source={dict(src_tags)}, target={dict(tgt_tags)}.",
                )
            )

        cp = _COUNT_PLURAL_RE.search(tgt)
        if cp:
            findings.append(
                I18nFinding(
                    key,
                    "count-plural",
                    f"Plural noun after count in «{key}»: «{cp.group(0)}». Use singular in Persian.",
                )
            )

        stripped_src = _URL_RE.sub(" ", _PLACEHOLDER_RE.sub(" ", src))
        ascii_words = re.findall(r"[A-Za-z]{2,}", stripped_src)
        if len(ascii_words) >= 2 and tgt.strip().casefold() == src.strip().casefold():
            findings.append(
                I18nFinding(
                    key,
                    "untranslated",
                    f"Key «{key}» appears untranslated («{tgt[:50]}»).",
                )
            )

        if (
            max_length_ratio is not None
            and len(src.strip()) >= 12
            and len(tgt.strip()) > len(src.strip()) * max_length_ratio
        ):
            findings.append(
                I18nFinding(
                    key,
                    "length",
                    f"Translation for «{key}» is {len(tgt.strip())} chars vs source {len(src.strip())} "
                    f"(exceeds {max_length_ratio:g}x ratio).",
                )
            )

    return findings


def check_i18n(
    source_path: Union[str, Path],
    target_path: Union[str, Path],
    max_length_ratio: Optional[float] = None,
) -> List[I18nFinding]:
    """Load source and target localization files and validate all entries."""
    return check_i18n_maps(
        load_i18n_file(source_path),
        load_i18n_file(target_path),
        max_length_ratio=max_length_ratio,
    )
