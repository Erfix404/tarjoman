"""Tests for SceneContinuityTracker and SceneState (Pack C)."""
from __future__ import annotations

import unittest
from pathlib import Path

from click.testing import CliRunner

from tarjoman.memory import SceneContinuityTracker, SceneState


class TestSceneState(unittest.TestCase):
    def test_dict_roundtrip(self) -> None:
        state = SceneState(
            chapter_id="ch1", segment_id="s2", pov="first_person",
            location="Library", atmosphere="gloomy",
            pronoun_references={"he": "Dr. Jekyll"},
            active_characters=["Jekyll"], notes="n",
        )
        restored = SceneState.from_dict(state.to_dict())
        self.assertEqual(restored, state)


class TestSceneContinuityTracker(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = SceneContinuityTracker()

    def test_record_and_current(self) -> None:
        state = self.tracker.record_scene(
            "ch1", segment_id="s1", pov="first_person",
            location="Library", atmosphere="gloomy",
            pronoun_references={"he": "Dr. Jekyll"},
            active_characters=["Jekyll"],
        )
        self.assertEqual(self.tracker.get_current_state(), state)
        self.assertEqual(len(self.tracker.get_history()), 1)
        self.assertEqual(state.atmosphere, "gloomy")

    def test_update_pronoun(self) -> None:
        self.tracker.record_scene("ch1", pronoun_references={"he": "Jekyll"})
        self.tracker.update_pronoun("he", "Hyde")
        self.assertEqual(
            self.tracker.get_current_state().pronoun_references["he"], "Hyde"
        )

    def test_pov_shift_warning(self) -> None:
        self.tracker.record_scene("ch1", pov="first_person")
        warnings = self.tracker.check_continuity(
            SceneState(chapter_id="ch2", pov="third_person")
        )
        self.assertTrue(any("POV shift" in w for w in warnings))

    def test_pronoun_clash_warning(self) -> None:
        self.tracker.record_scene("ch1", pronoun_references={"he": "Jekyll"})
        warnings = self.tracker.check_continuity(
            SceneState(chapter_id="ch2", pronoun_references={"he": "Hyde"})
        )
        self.assertTrue(any("Pronoun clash" in w for w in warnings))

    def test_location_jump_needs_transition(self) -> None:
        self.tracker.record_scene(
            "ch1", location="Library", active_characters=["Alice"]
        )
        jump = SceneState(
            chapter_id="ch2", location="Garden", active_characters=["Bob"]
        )
        self.assertTrue(
            any("Location jump" in w for w in self.tracker.check_continuity(jump))
        )
        bridged = SceneState(
            chapter_id="ch2", location="Garden", active_characters=["Alice", "Bob"]
        )
        self.assertFalse(
            [w for w in self.tracker.check_continuity(bridged) if "Location jump" in w]
        )

    def test_no_warnings_for_same_state(self) -> None:
        self.tracker.record_scene("ch1", pov="third_person", location="Library")
        warnings = self.tracker.check_continuity(
            SceneState(chapter_id="ch1", pov="third_person", location="Library")
        )
        self.assertEqual(warnings, [])

    def test_context_summary(self) -> None:
        self.tracker.record_scene(
            "ch1", pov="first_person", location="Library",
            atmosphere="gloomy", pronoun_references={"he": "Dr. Jekyll"},
        )
        summary = self.tracker.get_context_summary()
        self.assertEqual(
            summary,
            "[POV: first_person | Location: Library | "
            "Atmosphere: gloomy | Pronouns: he=Dr. Jekyll]",
        )

    def test_empty_summary(self) -> None:
        self.assertEqual(self.tracker.get_context_summary(), "")

    def test_save_load_persistence(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            self.tracker.record_scene(
                "ch1", pov="first_person", location="Library",
                pronoun_references={"he": "Jekyll"},
            )
            self.tracker.record_scene("ch2", pov="first_person", location="Garden")
            path = self.tracker.save(Path("scene.json"))
            self.assertTrue(path.exists())
            fresh = SceneContinuityTracker(state_path=path)
            self.assertEqual(len(fresh.get_history()), 2)
            current = fresh.get_current_state()
            self.assertIsNotNone(current)
            assert current is not None
            self.assertEqual(current.chapter_id, "ch2")
            self.assertEqual(current.location, "Garden")


if __name__ == "__main__":
    unittest.main()
