"""
Character Bible for Tarjoman Long-Form Literary Translation (Super-Skill v2).

Tracks per-character voice consistency across chapters: canonical names,
Persian transliterations/translations, gender, tone/register, and the address
pronoun (تو / شما) each character uses toward others.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

ADDRESS_PRONOUNS = ("تو", "شما")

VOICE_PRESETS: Dict[str, Dict[str, Any]] = {
    "formal_scholar": {
        "tone": "formal_scholar",
        "default_address": "شما",
        "speech_quirks": ["مطنطن", "کلمات فاخر و کهن", "ساختار نحوی فخیم", "عدم استفاده از واژگان عامیانه"],
        "notes": "دانشمند، استاد و ادیب با لحن رسمی و فخیم",
    },
    "colloquial_rustic": {
        "tone": "colloquial_rustic",
        "default_address": "تو",
        "speech_quirks": ["شکسته‌نویسی شیرین محلی", "اصطلاحات عامیانه صمیمی", "تکیه‌کلام‌های روستایی و خودمانی"],
        "notes": "شخصیت روستایی یا صمیمی با زبان گفتاری شیرین",
    },
    "aristocratic_cynic": {
        "tone": "aristocratic_cynic",
        "default_address": "شما",
        "speech_quirks": ["طعنه‌آمیز", "کنایه‌دار", "لحن سرد و اشرافی", "مودب اما تحقیرآمیز"],
        "notes": "اشراف‌زاده بدبین و متفرعن",
    },
    "disciplinarian": {
        "tone": "disciplinarian",
        "default_address": "شما",
        "speech_quirks": ["دستوری", "نظامی", "جملات کوتاه و قاطع", "بدون حاشیه و مقتدر"],
        "notes": "سخت‌گیر، مقتدر و منظم",
    },
}


@dataclass
class CharacterProfile:
    """Voice profile for a single character."""

    name: str
    persian_name: str = ""
    gender: str = ""  # "male" | "female" | "" (unknown)
    tone: str = ""  # e.g. "epic_formal", "colloquial", "archaic"
    default_address: str = "شما"  # تو | شما — how this character addresses others
    speech_quirks: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterProfile":
        quirks = data.get("speech_quirks", [])
        return cls(
            name=str(data.get("name", "")),
            persian_name=str(data.get("persian_name", "")),
            gender=str(data.get("gender", "")),
            tone=str(data.get("tone", "")),
            default_address=str(data.get("default_address", "شما")),
            speech_quirks=list(quirks) if isinstance(quirks, list) else [],
            notes=str(data.get("notes", "")),
        )


class CharacterBible:
    """
    Registry of character voices with JSON serialization and queries.

    Small interface: upsert profiles, query by name (case-insensitive),
    list by tone/gender, serialize to ``characters.json``.
    """

    def __init__(
        self, bible_path: Optional[Union[str, Path]] = None, _skip_load: bool = False
    ) -> None:
        self.bible_path = Path(bible_path) if bible_path else None
        self._characters: Dict[str, CharacterProfile] = {}
        if self.bible_path and self.bible_path.exists() and not _skip_load:
            self.load(self.bible_path)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def upsert_character(self, profile: CharacterProfile) -> CharacterProfile:
        """Insert or replace the profile for ``profile.name`` (keyed lowercase)."""
        name = profile.name.strip()
        if not name:
            raise ValueError("CharacterProfile requires a non-empty name.")
        profile.name = name
        if profile.default_address not in ADDRESS_PRONOUNS:
            profile.default_address = "شما"
        self._characters[name.lower()] = profile
        return profile

    def record_character(
        self,
        name: str,
        persian_name: str = "",
        gender: str = "",
        tone: str = "",
        default_address: str = "شما",
        speech_quirks: Optional[List[str]] = None,
        notes: str = "",
    ) -> CharacterProfile:
        """Convenience upsert from scalar fields."""
        return self.upsert_character(
            CharacterProfile(
                name=name,
                persian_name=persian_name,
                gender=gender,
                tone=tone,
                default_address=default_address,
                speech_quirks=list(speech_quirks or []),
                notes=notes,
            )
        )

    def remove_character(self, name: str) -> bool:
        """Remove a profile; True when something was removed."""
        return self._characters.pop(name.strip().lower(), None) is not None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_character(self, name: str) -> Optional[CharacterProfile]:
        """Retrieve a profile by name (exact, then case-insensitive)."""
        key = name.strip().lower()
        return self._characters.get(key)

    def address_pronoun(self, speaker: str, default: str = "شما") -> str:
        """Return how ``speaker`` addresses others (تو / شما)."""
        profile = self.get_character(speaker)
        if profile and profile.default_address in ADDRESS_PRONOUNS:
            return profile.default_address
        return default

    def list_characters(
        self, tone: Optional[str] = None, gender: Optional[str] = None
    ) -> List[CharacterProfile]:
        """List profiles, optionally filtered by tone and/or gender."""
        out = list(self._characters.values())
        if tone:
            out = [c for c in out if c.tone.lower() == tone.lower()]
        if gender:
            out = [c for c in out if c.gender.lower() == gender.lower()]
        return sorted(out, key=lambda c: c.name.lower())

    def search(self, query: str) -> List[CharacterProfile]:
        """Substring search over names, Persian names, tones, and quirks."""
        q = query.strip().lower()
        if not q:
            return []
        hits: List[CharacterProfile] = []
        for profile in self._characters.values():
            haystack = " ".join(
                [profile.name, profile.persian_name, profile.tone, profile.notes]
                + profile.speech_quirks
            ).lower()
            if q in haystack:
                hits.append(profile)
        return hits

    def count(self) -> int:
        return len(self._characters)

    # ------------------------------------------------------------------
    # Voice presets
    # ------------------------------------------------------------------

    def list_voice_presets(self) -> List[str]:
        """Return available voice preset keys."""
        return list(VOICE_PRESETS)

    def get_voice_preset(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """Return the preset dict for ``preset_name``, or None."""
        preset = VOICE_PRESETS.get(preset_name)
        return dict(preset) if preset else None

    def create_from_preset(
        self,
        name: str,
        preset_name: str,
        persian_name: str = "",
        gender: str = "",
        **overrides: Any,
    ) -> CharacterProfile:
        """Create a CharacterProfile from a preset merged with ``overrides``."""
        preset = VOICE_PRESETS.get(preset_name)
        if preset is None:
            raise ValueError(f"Unknown voice preset: {preset_name}")
        fields: Dict[str, Any] = {
            "tone": preset["tone"],
            "default_address": preset["default_address"],
            "speech_quirks": list(preset["speech_quirks"]),
            "notes": preset["notes"],
        }
        fields.update(overrides)
        return self.record_character(
            name, persian_name=persian_name, gender=gender, **fields
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bible_version": "2.0",
            "characters": [c.to_dict() for c in self.list_characters()],
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], bible_path: Optional[Union[str, Path]] = None
    ) -> "CharacterBible":
        bible = cls(bible_path=bible_path, _skip_load=True)
        for raw in data.get("characters", []):
            try:
                bible.upsert_character(CharacterProfile.from_dict(raw))
            except ValueError:
                continue
        return bible

    def save(self, path: Optional[Union[str, Path]] = None) -> Path:
        target = Path(path) if path else self.bible_path
        if target is None:
            raise ValueError("No bible path configured; pass `path` explicitly.")
        if target.parent and str(target.parent) not in ("", "."):
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.bible_path = target
        return target

    def load(self, path: Union[str, Path]) -> "CharacterBible":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        fresh = self.from_dict(data, bible_path=path)
        self._characters = fresh._characters
        self.bible_path = Path(path)
        return self
