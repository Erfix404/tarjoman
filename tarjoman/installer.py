"""Multi-platform skillpack and MCP config installer for Tarjoman."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VALID_TARGETS = ("claude", "cursor", "antigravity", "codex", "hermes")


def _locate_source_root(source_root: Optional[Path] = None) -> Path:
    root = Path(source_root) if source_root is not None else Path(__file__).resolve().parent.parent
    skill_md = root / ".claude" / "skills" / "tarjoman" / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(
            f"Canonical Tarjoman skillpack not found under {root / '.claude' / 'skills' / 'tarjoman'}"
        )
    return root


def _build_cursor_mdc(cursorrules_text: str) -> str:
    frontmatter = "\n".join(
        [
            "---",
            "description: Tarjoman Persian translation, typography, anti-calque, and QC rules",
            'globs: ""',
            "alwaysApply: false",
            "---",
            "",
        ]
    )
    return frontmatter + cursorrules_text.lstrip("\ufeff")


def _plan_skill_tree_files(
    source_root: Path,
    target_dir: Path,
    skill_md_source: Path,
) -> List[Tuple[Path, Path]]:
    canonical_dir = source_root / ".claude" / "skills" / "tarjoman"
    pairs: List[Tuple[Path, Path]] = [(skill_md_source, target_dir / "SKILL.md")]

    refs_dir = canonical_dir / "references"
    for ref_file in sorted(refs_dir.glob("*.md")):
        pairs.append((ref_file, target_dir / "references" / ref_file.name))

    linter_src = canonical_dir / "scripts" / "linter.py"
    if linter_src.is_file():
        pairs.append((linter_src, target_dir / "scripts" / "linter.py"))

    return pairs


def _write_or_skip_copy(
    src: Path,
    dst: Path,
    *,
    dry_run: bool,
    force: bool,
    written: List[str],
    skipped: List[str],
) -> None:
    if dst.exists() and not force:
        skipped.append(str(dst))
        return
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    written.append(str(dst))


def _write_or_skip_text(
    content: str,
    dst: Path,
    *,
    dry_run: bool,
    force: bool,
    written: List[str],
    skipped: List[str],
) -> None:
    if dst.exists() and not force:
        skipped.append(str(dst))
        return
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
    written.append(str(dst))


def _merge_mcp_config(
    mcp_path: Path,
    *,
    dry_run: bool,
    force: bool,
    written: List[str],
    skipped: List[str],
) -> Dict[str, Any]:
    tarjoman_entry = {"command": "tarjoman", "args": ["mcp"]}
    existing: Dict[str, Any] = {}
    if mcp_path.exists():
        raw = mcp_path.read_text(encoding="utf-8")
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            if not force:
                raise ValueError(f"Invalid JSON in existing MCP config {mcp_path}: {exc}") from exc
            loaded = {}
        if isinstance(loaded, dict):
            existing = loaded

    servers = existing.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    else:
        servers = dict(servers)

    if "tarjoman" in servers and not force:
        skipped.append(str(mcp_path))
        merged = {**existing, "mcpServers": servers}
        return merged

    servers["tarjoman"] = tarjoman_entry
    merged = {**existing, "mcpServers": servers}
    if not dry_run:
        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    written.append(str(mcp_path))
    return merged


def install_skill(
    target: str,
    dest_root: Optional[Path] = None,
    *,
    with_mcp: bool = False,
    dry_run: bool = False,
    force: bool = False,
    source_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Install Tarjoman skillpack/rules (and optional MCP config) for a target agent."""
    norm = target.strip().lower()
    if norm not in VALID_TARGETS:
        raise ValueError(f"Unsupported install target {target!r}. Choose from: {', '.join(VALID_TARGETS)}")

    src_root = _locate_source_root(source_root)
    dst_root = (Path(dest_root) if dest_root is not None else Path.cwd()).resolve()

    written: List[str] = []
    skipped: List[str] = []

    if norm == "cursor":
        rules_src = src_root / "agent-packs" / "cursor" / ".cursorrules"
        if not rules_src.is_file():
            rules_src = src_root / ".cursorrules"
        install_dir = dst_root / ".cursor" / "rules"
        mdc_path = install_dir / "tarjoman.mdc"
        mdc_text = _build_cursor_mdc(rules_src.read_text(encoding="utf-8"))
        _write_or_skip_text(
            mdc_text,
            mdc_path,
            dry_run=dry_run,
            force=force,
            written=written,
            skipped=skipped,
        )
        mcp_path = dst_root / ".cursor" / "mcp.json"
    else:
        dir_map = {
            "claude": dst_root / ".claude" / "skills" / "tarjoman",
            "antigravity": dst_root / ".agent" / "skills" / "tarjoman",
            "codex": dst_root / ".codex" / "skills" / "tarjoman",
            "hermes": dst_root / ".hermes" / "skills" / "tarjoman",
        }
        install_dir = dir_map[norm]
        canonical_skill = src_root / ".claude" / "skills" / "tarjoman" / "SKILL.md"
        hermes_skill = src_root / "agent-packs" / "hermes" / "SKILL.md"
        skill_src = hermes_skill if norm == "hermes" and hermes_skill.is_file() else canonical_skill
        for src, dst in _plan_skill_tree_files(src_root, install_dir, skill_src):
            _write_or_skip_copy(
                src,
                dst,
                dry_run=dry_run,
                force=force,
                written=written,
                skipped=skipped,
            )
        mcp_path = dst_root / ".mcp.json"

    mcp_info: Optional[Dict[str, Any]] = None
    if with_mcp:
        mcp_payload = _merge_mcp_config(
            mcp_path,
            dry_run=dry_run,
            force=force,
            written=written,
            skipped=skipped,
        )
        mcp_info = {"path": str(mcp_path), "config": mcp_payload}

    return {
        "target": norm,
        "dest_root": str(dst_root),
        "install_dir": str(install_dir),
        "dry_run": dry_run,
        "with_mcp": with_mcp,
        "written": written,
        "skipped": skipped,
        "mcp_config": mcp_info,
    }


__all__ = ["VALID_TARGETS", "install_skill"]
