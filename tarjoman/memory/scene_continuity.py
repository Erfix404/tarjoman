"""Scene continuity tracker for long-form literary translation (Pack C).

Tracks POV, spatial location, atmosphere, and pronoun reference mapping
across chapters and segments so translation prompts stay consistent.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class SceneState:
    """Snapshot of narrative state at one chapter/segment."""

    chapter_id: str
    segment_id: str = ""
    pov: str = "third_person"
    location: str = ""
    atmosphere: str = ""
    pronoun_references: Dict[str, str] = field(default_factory=dict)
    active_characters: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneState":
        return cls(
            chapter_id=str(data.get("chapter_id", "")),
            segment_id=str(data.get("segment_id", "")),
            pov=str(data.get("pov", "third_person")),
            location=str(data.get("location", "")),
            atmosphere=str(data.get("atmosphere", "")),
            pronoun_references=dict(data.get("pronoun_references", {}) or {}),
            active_characters=list(data.get("active_characters", []) or []),
            notes=str(data.get("notes", "")),
        )


class SceneContinuityTracker:
    """Registry of scene states with continuity checks and JSON persistence."""

    def __init__(
        self,
        state_path: Optional[Union[str, Path]] = None,
        _skip_load: bool = False,
    ) -> None:
        self.state_path = Path(state_path) if state_path else None
        self._history: List[SceneState] = []
        self._current: Optional[SceneState] = None
        if self.state_path and self.state_path.exists() and not _skip_load:
            self.load(self.state_path)

    def record_scene(
        self,
        chapter_id: str,
        segment_id: str = "",
        pov: str = "third_person",
        location: str = "",
        atmosphere: str = "",
        pronoun_references: Optional[Dict[str, str]] = None,
        active_characters: Optional[List[str]] = None,
        notes: str = "",
    ) -> SceneState:
        state = SceneState(
            chapter_id=chapter_id,
            segment_id=segment_id,
            pov=pov,
            location=location,
            atmosphere=atmosphere,
            pronoun_references=dict(pronoun_references or {}),
            active_characters=list(active_characters or []),
            notes=notes,
        )
        self._history.append(state)
        self._current = state
        return state

    def update_pronoun(self, pronoun: str, entity: str) -> None:
        """Update the referent of ``pronoun`` in the current state."""
        if self._current is None:
            self._current = SceneState(chapter_id="")
        self._current.pronoun_references[pronoun] = entity

    def get_current_state(self) -> Optional[SceneState]:
        return self._current

    def get_history(self) -> List[SceneState]:
        return list(self._history)

    def check_continuity(self, new_state: SceneState) -> List[str]:
        """Warn on abrupt POV shifts, location jumps, or pronoun clashes."""
        warnings: List[str] = []
        prev = self._current
        if prev is None:
            return warnings
        if new_state.pov and prev.pov and new_state.pov != prev.pov:
            warnings.append(f"POV shift: {prev.pov} -> {new_state.pov}")
        if new_state.location and prev.location and new_state.location != prev.location:
            if not set(new_state.active_characters) & set(prev.active_characters):
                warnings.append(
                    f"Location jump: {prev.location} -> {new_state.location}"
                )
        for pronoun, entity in new_state.pronoun_references.items():
            if pronoun in prev.pronoun_references:
                old = prev.pronoun_references[pronoun]
                if old and entity and old != entity:
                    warnings.append(
                        f"Pronoun clash: '{pronoun}' was {old}, now {entity}"
                    )
        return warnings

    def get_context_summary(self) -> str:
        """Compact context string for injection into translation prompts."""
        if self._current is None:
            return ""
        s = self._current
        pronouns = ", ".join(
            f"{k}={v}" for k, v in s.pronoun_references.items()
        )
        return (
            f"[POV: {s.pov} | Location: {s.location} | "
            f"Atmosphere: {s.atmosphere} | Pronouns: {pronouns}]"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tracker_version": "2.1",
            "history": [s.to_dict() for s in self._history],
            "current": self._current.to_dict() if self._current else None,
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        state_path: Optional[Union[str, Path]] = None,
    ) -> "SceneContinuityTracker":
        tracker = cls(state_path=state_path, _skip_load=True)
        for raw in data.get("history", []):
            try:
                tracker._history.append(SceneState.from_dict(raw))
            except Exception:
                continue
        current = data.get("current")
        if current:
            try:
                tracker._current = SceneState.from_dict(current)
            except Exception:
                tracker._current = tracker._history[-1] if tracker._history else None
        elif tracker._history:
            tracker._current = tracker._history[-1]
        return tracker

    def save(self, path: Optional[Union[str, Path]] = None) -> Path:
        target = Path(path) if path else self.state_path
        if target is None:
            raise ValueError("No state path configured; pass `path` explicitly.")
        if target.parent and str(target.parent) not in ("", "."):
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.state_path = target
        return target

    def load(self, path: Union[str, Path]) -> "SceneContinuityTracker":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        fresh = self.from_dict(data, state_path=path)
        self._history = fresh._history
        self._current = fresh._current
        self.state_path = Path(path)
        return self
