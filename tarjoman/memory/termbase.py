"""
SQLite-backed Terminology Store for Tarjoman (Super-Skill v2).

Domain-tagged English → Persian term storage with FTS-friendly search and
cascade re-translation tracking: when a term's Persian equivalent changes,
:text:`affected_segments` records which ``(chapter_id, segment_id)`` pairs
used the old translation so the pipeline can re-translate exactly those.
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


@dataclass
class TermRecord:
    en_term: str
    fa_term: str
    domain: str = ""
    notes: str = ""
    updated_at: str = ""


@dataclass
class CascadeEvent:
    en_term: str
    old_fa_term: str
    new_fa_term: str
    affected_segments: List[Tuple[int, int]]
    created_at: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS terms (
    en_term TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    fa_term TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (en_term, domain)
);
CREATE TABLE IF NOT EXISTS term_usage (
    en_term TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    chapter_id INTEGER NOT NULL,
    segment_id INTEGER NOT NULL,
    PRIMARY KEY (en_term, domain, chapter_id, segment_id)
);
CREATE TABLE IF NOT EXISTS cascade_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    en_term TEXT NOT NULL,
    old_fa_term TEXT NOT NULL,
    new_fa_term TEXT NOT NULL,
    affected_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Termbase:
    """
    SQLite termbase with domain tagging, search, and cascade re-translation.

    Small interface: :meth:`record_term`, :meth:`resolve_term`,
    :meth:`search`, :meth:`record_usage`, :meth:`update_term` (cascade),
    :meth:`pending_cascades` / :meth:`acknowledge_cascade`.
    Thread-safe via a single lock; ``:memory:`` supported for tests.
    """

    def __init__(self, db_path: Union[str, Path] = "terms.db") -> None:
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        if self.db_path != ":memory:":
            parent = Path(self.db_path).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Terms
    # ------------------------------------------------------------------

    @staticmethod
    def _norm(text: str) -> str:
        return text.strip()

    def record_term(
        self, en_term: str, fa_term: str, domain: str = "", notes: str = ""
    ) -> TermRecord:
        """Insert or replace a term translation."""
        en, fa, dom = self._norm(en_term), self._norm(fa_term), self._norm(domain)
        if not en or not fa:
            raise ValueError("Both en_term and fa_term are required.")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO terms(en_term, domain, fa_term, notes, updated_at)"
                " VALUES(?, ?, ?, ?, ?)",
                (en, dom, fa, notes.strip(), now),
            )
            self._conn.commit()
        return TermRecord(en_term=en, fa_term=fa, domain=dom, notes=notes.strip(), updated_at=now)

    def resolve_term(self, en_term: str, domain: Optional[str] = None) -> Optional[str]:
        """Resolve English → Persian; exact, then domain-scoped, then case-insensitive."""
        key = self._norm(en_term)
        if not key:
            return None
        with self._lock:
            cur = self._conn.cursor()
            if domain is not None:
                row = cur.execute(
                    "SELECT fa_term FROM terms WHERE en_term = ? AND domain = ?",
                    (key, self._norm(domain)),
                ).fetchone()
                if row:
                    return row["fa_term"]
            row = cur.execute(
                "SELECT fa_term FROM terms WHERE en_term = ?", (key,)
            ).fetchone()
            if row:
                return row["fa_term"]
            row = cur.execute(
                "SELECT fa_term FROM terms WHERE LOWER(en_term) = LOWER(?) LIMIT 1",
                (key,),
            ).fetchone()
            return row["fa_term"] if row else None

    def has_term(self, en_term: str, domain: Optional[str] = None) -> bool:
        return self.resolve_term(en_term, domain) is not None

    def get_all_terms(self, domain: Optional[str] = None) -> Dict[str, str]:
        with self._lock:
            cur = self._conn.cursor()
            if domain:
                rows = cur.execute(
                    "SELECT en_term, fa_term FROM terms WHERE LOWER(domain) = LOWER(?)",
                    (self._norm(domain),),
                ).fetchall()
            else:
                rows = cur.execute("SELECT en_term, fa_term FROM terms").fetchall()
            return {r["en_term"]: r["fa_term"] for r in rows}

    def search(self, query: str, domain: Optional[str] = None, limit: int = 50) -> List[TermRecord]:
        """Substring search over English/Persian terms and notes."""
        q = f"%{query.strip()}%"
        if not query.strip():
            return []
        with self._lock:
            cur = self._conn.cursor()
            if domain:
                rows = cur.execute(
                    "SELECT en_term, fa_term, domain, notes, updated_at FROM terms"
                    " WHERE (en_term LIKE ? OR fa_term LIKE ? OR notes LIKE ?)"
                    " AND LOWER(domain) = LOWER(?) LIMIT ?",
                    (q, q, q, self._norm(domain), limit),
                ).fetchall()
            else:
                rows = cur.execute(
                    "SELECT en_term, fa_term, domain, notes, updated_at FROM terms"
                    " WHERE en_term LIKE ? OR fa_term LIKE ? OR notes LIKE ? LIMIT ?",
                    (q, q, q, limit),
                ).fetchall()
            return [TermRecord(**dict(r)) for r in rows]

    def count(self, domain: Optional[str] = None) -> int:
        with self._lock:
            cur = self._conn.cursor()
            if domain:
                row = cur.execute(
                    "SELECT COUNT(*) AS n FROM terms WHERE LOWER(domain) = LOWER(?)",
                    (self._norm(domain),),
                ).fetchone()
            else:
                row = cur.execute("SELECT COUNT(*) AS n FROM terms").fetchone()
            return int(row["n"])

    # ------------------------------------------------------------------
    # Usage tracking + cascade re-translation
    # ------------------------------------------------------------------

    def record_usage(
        self, en_term: str, chapter_id: int, segment_id: int, domain: str = ""
    ) -> None:
        """Note that a segment used a term (drives cascade detection)."""
        en = self._norm(en_term)
        if not en:
            return
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO term_usage(en_term, domain, chapter_id, segment_id)"
                " VALUES(?, ?, ?, ?)",
                (en, self._norm(domain), int(chapter_id), int(segment_id)),
            )
            self._conn.commit()

    def affected_segments(self, en_term: str) -> List[Tuple[int, int]]:
        """Return ``(chapter_id, segment_id)`` pairs recorded for ``en_term``."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT chapter_id, segment_id FROM term_usage WHERE LOWER(en_term) = LOWER(?)"
                " ORDER BY chapter_id, segment_id",
                (self._norm(en_term),),
            ).fetchall()
            return [(int(r["chapter_id"]), int(r["segment_id"])) for r in rows]

    def update_term(
        self, en_term: str, new_fa_term: str, domain: str = "", notes: str = ""
    ) -> CascadeEvent:
        """
        Change a term's Persian equivalent and log a cascade event listing the
        segments that used the old translation (re-translate exactly those).
        """
        en = self._norm(en_term)
        old = self.resolve_term(en, domain or None) or ""
        record = self.record_term(en, new_fa_term, domain, notes)
        affected = self.affected_segments(en)
        import json as _json

        event = CascadeEvent(
            en_term=en,
            old_fa_term=old,
            new_fa_term=record.fa_term,
            affected_segments=affected,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO cascade_log(en_term, old_fa_term, new_fa_term, affected_json, created_at)"
                " VALUES(?, ?, ?, ?, ?)",
                (en, old, record.fa_term, _json.dumps(affected), event.created_at),
            )
            self._conn.commit()
        return event

    def pending_cascades(self) -> List[CascadeEvent]:
        """Return all logged cascade events (oldest first)."""
        import json as _json

        with self._lock:
            rows = self._conn.execute(
                "SELECT en_term, old_fa_term, new_fa_term, affected_json, created_at"
                " FROM cascade_log ORDER BY id"
            ).fetchall()
            return [
                CascadeEvent(
                    en_term=r["en_term"],
                    old_fa_term=r["old_fa_term"],
                    new_fa_term=r["new_fa_term"],
                    affected_segments=[tuple(p) for p in _json.loads(r["affected_json"])],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def acknowledge_cascade(self, en_term: str) -> int:
        """Clear cascade log entries for ``en_term``; returns rows removed."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM cascade_log WHERE LOWER(en_term) = LOWER(?)",
                (self._norm(en_term),),
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
