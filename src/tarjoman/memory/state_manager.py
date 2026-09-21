"""
State Manager for Tarjoman Long-Form Book and Multi-Chapter Projects.

Manages:
1. Dynamic Termbase: Persistent TSV mapping of english_term -> persian_translation.
2. Character Voice Ledger: Dialogue registers, address pronouns, speech quirks for literary fiction.
3. Sliding Context Window: Chronologically ordered context accumulation up to token/word limits.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class StateManager:
    """
    Project-level state manager coordinating dynamic terminology, character voice styles,
    and rolling context windows across chapters.
    """

    def __init__(
        self,
        termbase_path: Optional[Union[str, Path]] = None,
        voice_ledger_path: Optional[Union[str, Path]] = None,
    ) -> None:
        self.termbase_path = Path(termbase_path) if termbase_path else None
        self.voice_ledger_path = Path(voice_ledger_path) if voice_ledger_path else None
        self._lock = threading.Lock()
        self._termbase: Dict[str, Dict[str, str]] = {}
        self._voice_ledger: Dict[str, Dict[str, Any]] = {}

        self._load_termbase()
        self._load_voice_ledger()

    # -------------------------------------------------------------------------
    # Dynamic Termbase (TSV)
    # -------------------------------------------------------------------------

    def _load_termbase(self) -> None:
        if not self.termbase_path or not self.termbase_path.exists():
            return
        try:
            with open(self.termbase_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for idx, line in enumerate(lines):
                line = line.rstrip("\r\n")
                if not line:
                    continue
                parts = line.split("\t")
                if idx == 0 and parts[0].strip().lower() in ("english_term", "en_term", "english"):
                    continue
                en = parts[0].strip()
                fa = parts[1].strip() if len(parts) > 1 else ""
                domain = parts[2].strip() if len(parts) > 2 else ""
                notes = parts[3].strip() if len(parts) > 3 else ""
                if en and fa:
                    self._termbase[en] = {
                        "fa_term": fa,
                        "domain": domain,
                        "notes": notes,
                    }
        except Exception:
            pass

    def _save_termbase(self) -> None:
        if not self.termbase_path:
            return
        parent = self.termbase_path.parent
        if parent and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)

        target_dir = str(parent) if str(parent) else "."
        # ponytail: TSV storage for terminology; upgrade to SQLite FTS5 when terms exceed 10k.
        fd, temp_path = tempfile.mkstemp(
            dir=target_dir, prefix=".tb_tmp_", suffix=".tsv"
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write("english_term\tpersian_translation\tdomain\tnotes\n")
                for en, data in self._termbase.items():
                    f.write(
                        f"{en}\t{data['fa_term']}\t{data['domain']}\t{data['notes']}\n"
                    )
            os.replace(temp_path, self.termbase_path)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

    def record_term(
        self,
        en_term: str,
        fa_term: str,
        domain: str = "",
        notes: str = "",
    ) -> None:
        """
        Record or update a term translation in the dynamic termbase.
        """
        en_clean = en_term.strip()
        fa_clean = fa_term.strip()
        if not en_clean or not fa_clean:
            return
        with self._lock:
            self._termbase[en_clean] = {
                "fa_term": fa_clean,
                "domain": domain.strip(),
                "notes": notes.strip(),
            }
            self._save_termbase()

    def resolve_term(self, en_term: str) -> Optional[str]:
        """
        Resolve English term to Persian translation. Supports exact and case-insensitive match.
        """
        with self._lock:
            key = en_term.strip()
            if key in self._termbase:
                return self._termbase[key]["fa_term"]
            key_lower = key.lower()
            for k, v in self._termbase.items():
                if k.lower() == key_lower:
                    return v["fa_term"]
            return None

    def get_all_terms(self, domain: Optional[str] = None) -> Dict[str, str]:
        """
        Return dictionary of english_term -> persian_translation, optionally filtered by domain.
        """
        with self._lock:
            if domain is None or domain == "":
                return {en: data["fa_term"] for en, data in self._termbase.items()}
            domain_lower = domain.lower()
            return {
                en: data["fa_term"]
                for en, data in self._termbase.items()
                if data.get("domain", "").lower() == domain_lower
            }

    def has_term(self, en_term: str) -> bool:
        """
        Check if an English term exists in the termbase.
        """
        return self.resolve_term(en_term) is not None

    # -------------------------------------------------------------------------
    # Character Voice Ledger
    # -------------------------------------------------------------------------

    def _load_voice_ledger(self) -> None:
        if not self.voice_ledger_path or not self.voice_ledger_path.exists():
            return
        try:
            with open(self.voice_ledger_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._voice_ledger = data
        except Exception:
            pass

    def _save_voice_ledger(self) -> None:
        if not self.voice_ledger_path:
            return
        parent = self.voice_ledger_path.parent
        if parent and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)

        target_dir = str(parent) if str(parent) else "."
        fd, temp_path = tempfile.mkstemp(
            dir=target_dir, prefix=".vl_tmp_", suffix=".json"
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(self._voice_ledger, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.voice_ledger_path)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

    def record_voice_profile(
        self, character_name: str, voice_data: Dict[str, Any]
    ) -> None:
        """
        Record or update character dialogue settings (register, pronoun address, speech quirks).
        """
        name_clean = character_name.strip()
        if not name_clean:
            return
        with self._lock:
            self._voice_ledger[name_clean] = dict(voice_data)
            self._save_voice_ledger()

    def get_voice_profile(self, character_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve character voice settings by name (exact or case-insensitive).
        """
        name_clean = character_name.strip()
        with self._lock:
            if name_clean in self._voice_ledger:
                return dict(self._voice_ledger[name_clean])
            name_lower = name_clean.lower()
            for k, v in self._voice_ledger.items():
                if k.lower() == name_lower:
                    return dict(v)
            return None

    # -------------------------------------------------------------------------
    # Sliding Context Window
    # -------------------------------------------------------------------------

    @staticmethod
    def build_sliding_context(
        previous_paragraphs: List[str], max_words: int = 200
    ) -> str:
        """
        Build sliding context window from immediately preceding paragraphs
        up to max_words in length, preserving chronological order.
        """
        if not previous_paragraphs or max_words <= 0:
            return ""

        # ponytail: Simple word-count sliding window; add semantic embedding ranking when paragraph pool exceeds 500.
        selected: List[str] = []
        current_words = 0

        for para in reversed(previous_paragraphs):
            para_clean = para.strip()
            if not para_clean:
                continue
            words = para_clean.split()
            count = len(words)
            if current_words + count <= max_words:
                selected.append(para_clean)
                current_words += count
            else:
                if not selected:
                    # If single most recent paragraph exceeds max_words, take final words
                    tail = words[-max_words:]
                    selected.append(" ".join(tail))
                break

        selected.reverse()
        return "\n\n".join(selected)
