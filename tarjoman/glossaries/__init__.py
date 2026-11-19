"""Bundled curated domain starter glossaries for Tarjoman."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from tarjoman.memory.termbase import Termbase

GLOSSARY_DIR = Path(__file__).resolve().parent

GLOSSARY_DESCRIPTIONS: Dict[str, str] = {
    "technical-ai": "AI, LLM, and software engineering terminology",
    "medical-patient": "Patient-facing clinical & pharmacy terminology",
    "financial": "Accounting, macroeconomics, and markets terminology",
    "legal-licenses": "Contracts, IP, and software licensing terminology",
}


@dataclass(frozen=True)
class GlossaryMeta:
    name: str
    domain: str
    description: str
    term_count: int
    path: Path


@dataclass(frozen=True)
class GlossaryEntry:
    en_term: str
    fa_term: str
    domain: str
    notes: str = ""


def _parse_tsv(path: Path) -> List[GlossaryEntry]:
    entries: List[GlossaryEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("english_term\t"):
            continue
        cols = line.split("\t")
        en = cols[0].strip() if len(cols) > 0 else ""
        fa = cols[1].strip() if len(cols) > 1 else ""
        domain = cols[2].strip() if len(cols) > 2 else path.stem
        notes = cols[3].strip() if len(cols) > 3 else ""
        if en and fa:
            entries.append(GlossaryEntry(en_term=en, fa_term=fa, domain=domain, notes=notes))
    return entries


def list_glossaries() -> List[GlossaryMeta]:
    """List all bundled starter glossaries sorted by name."""
    metas: List[GlossaryMeta] = []
    for path in sorted(GLOSSARY_DIR.glob("*.tsv")):
        name = path.stem
        entries = _parse_tsv(path)
        domain = entries[0].domain if entries else name
        metas.append(
            GlossaryMeta(
                name=name,
                domain=domain,
                description=GLOSSARY_DESCRIPTIONS.get(name, f"{name} starter glossary"),
                term_count=len(entries),
                path=path,
            )
        )
    return metas


def load_glossary(name: str) -> List[GlossaryEntry]:
    """Load all entries from a named starter glossary."""
    clean = name.strip()
    if clean.endswith(".tsv"):
        clean = clean[:-4]
    path = GLOSSARY_DIR / f"{clean}.tsv"
    if not path.exists():
        available = ", ".join(m.name for m in list_glossaries())
        raise FileNotFoundError(f"Unknown glossary {name!r}. Available: {available}")
    return _parse_tsv(path)


def _read_full_tsv(tsv_path: Path) -> Dict[str, Tuple[str, str, str]]:
    rows: Dict[str, Tuple[str, str, str]] = {}
    if not tsv_path.exists():
        return rows
    for line in tsv_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("english_term\t"):
            continue
        cols = line.split("\t")
        en = cols[0].strip() if len(cols) > 0 else ""
        fa = cols[1].strip() if len(cols) > 1 else ""
        domain = cols[2].strip() if len(cols) > 2 else ""
        notes = cols[3].strip() if len(cols) > 3 else ""
        if en and fa:
            rows[en] = (fa, domain, notes)
    return rows


def import_glossary_to_project(
    project_dir: Path,
    name: str,
    *,
    overwrite: bool = False,
) -> Dict[str, object]:
    """Import a starter glossary into a book project's terms.db and terms.tsv."""
    project = Path(project_dir)
    if not project.is_dir():
        raise NotADirectoryError(f"Book project directory does not exist: {project}")

    entries = load_glossary(name)
    clean_name = name[:-4] if name.strip().endswith(".tsv") else name.strip()
    tsv_path = project / "terms.tsv"
    tsv_rows = _read_full_tsv(tsv_path)

    added = 0
    updated = 0
    skipped = 0

    termbase = Termbase(db_path=project / "terms.db")
    try:
        for entry in entries:
            existing_db = termbase.resolve_term(entry.en_term, entry.domain or None) or termbase.resolve_term(
                entry.en_term
            )
            existing_tsv = tsv_rows.get(entry.en_term, ("", "", ""))[0]
            existing = existing_db or existing_tsv

            if existing:
                if overwrite and existing != entry.fa_term:
                    termbase.record_term(
                        entry.en_term,
                        entry.fa_term,
                        domain=entry.domain,
                        notes=entry.notes,
                    )
                    tsv_rows[entry.en_term] = (entry.fa_term, entry.domain, entry.notes)
                    updated += 1
                else:
                    skipped += 1
                continue

            termbase.record_term(
                entry.en_term,
                entry.fa_term,
                domain=entry.domain,
                notes=entry.notes,
            )
            tsv_rows[entry.en_term] = (entry.fa_term, entry.domain, entry.notes)
            added += 1

        # Keep terms.tsv synced cleanly with all existing + newly imported terms
        for en_db, fa_db in termbase.get_all_terms().items():
            if en_db not in tsv_rows:
                tsv_rows[en_db] = (fa_db, "", "")
    finally:
        termbase.close()

    out_lines = ["english_term\tpersian_term\tdomain\tnotes"]
    for en in sorted(tsv_rows):
        fa, dom, notes = tsv_rows[en]
        out_lines.append(f"{en}\t{fa}\t{dom}\t{notes}")
    tsv_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    return {
        "glossary": clean_name,
        "project": str(project),
        "total_in_glossary": len(entries),
        "added": added,
        "updated": updated,
        "skipped": skipped,
    }


__all__ = [
    "GLOSSARY_DIR",
    "GLOSSARY_DESCRIPTIONS",
    "GlossaryEntry",
    "GlossaryMeta",
    "import_glossary_to_project",
    "list_glossaries",
    "load_glossary",
]
