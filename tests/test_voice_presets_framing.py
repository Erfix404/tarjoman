"""Tests for CharacterBible voice presets and neutral linguistic framing (Pack C)."""
from __future__ import annotations

import unittest

from tarjoman.core.contracts import DomainProfile, TextSegment
from tarjoman.memory.character_bible import CharacterBible, VOICE_PRESETS
from tarjoman.stages.draft import (
    NeutralLinguisticFraming as DraftAliasFraming,
)
from tarjoman.stages.stage2_draft import (
    EchoDraftBackend,
    NeutralLinguisticFraming,
    SemanticDraftStage,
    sanitize_for_neutral_framing,
)


def _profile() -> DomainProfile:
    return DomainProfile(
        id="literary", title_fa="ادبی",
        description="literary", system_prompt="translate",
    )


class TestVoicePresets(unittest.TestCase):
    def setUp(self) -> None:
        self.bible = CharacterBible()

    def test_preset_keys(self) -> None:
        self.assertEqual(
            set(self.bible.list_voice_presets()),
            {"formal_scholar", "colloquial_rustic", "aristocratic_cynic", "disciplinarian"},
        )
        self.assertEqual(set(VOICE_PRESETS), set(self.bible.list_voice_presets()))

    def test_get_preset(self) -> None:
        preset = self.bible.get_voice_preset("formal_scholar")
        self.assertIsNotNone(preset)
        assert preset is not None
        self.assertEqual(preset["default_address"], "شما")
        self.assertIn("مطنطن", preset["speech_quirks"])
        self.assertIsNone(self.bible.get_voice_preset("nonexistent"))

    def test_create_from_preset(self) -> None:
        profile = self.bible.create_from_preset(
            "Colin", "disciplinarian", persian_name="کالین"
        )
        self.assertEqual(profile.tone, "disciplinarian")
        self.assertEqual(profile.default_address, "شما")
        self.assertIn("دستوری", profile.speech_quirks)
        self.assertIsNotNone(self.bible.get_character("Colin"))

    def test_create_from_preset_with_overrides(self) -> None:
        profile = self.bible.create_from_preset(
            "Sara", "colloquial_rustic", default_address="شما", gender="female"
        )
        self.assertEqual(profile.default_address, "شما")
        self.assertEqual(profile.gender, "female")
        self.assertEqual(profile.tone, "colloquial_rustic")

    def test_unknown_preset_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.bible.create_from_preset("X", "nope")


class TestNeutralLinguisticFraming(unittest.TestCase):
    SOURCE = (
        "Published by Penguin Books\n"
        "All rights reserved\n"
        "ISBN 9780134685991\n"
        "Copyright 2020 Example Press\n"
        "The night was quiet and still."
    )

    def test_sanitize_strips_boilerplate(self) -> None:
        cleaned = sanitize_for_neutral_framing(self.SOURCE)
        self.assertNotIn("Penguin", cleaned)
        self.assertNotIn("All rights reserved", cleaned)
        self.assertNotIn("9780134685991", cleaned)
        self.assertIn("quiet", cleaned)

    def test_wrap_neutral_prompt(self) -> None:
        wrapped = NeutralLinguisticFraming().wrap("sample text")
        self.assertIn("linguistic text excerpt", wrapped)
        self.assertIn("sample text", wrapped)

    def test_draft_alias_module_matches(self) -> None:
        self.assertIs(DraftAliasFraming, NeutralLinguisticFraming)

    def test_stage_applies_framing_by_default(self) -> None:
        stage = SemanticDraftStage(backend=EchoDraftBackend())
        result = stage.process([TextSegment(id=1, source_text=self.SOURCE)], _profile())
        out = result.segments[0].translated_text or ""
        self.assertNotIn("Penguin", out)
        self.assertNotIn("All rights reserved", out)
        self.assertIn("quiet", out)

    def test_stage_opt_out_preserves_source(self) -> None:
        stage = SemanticDraftStage(backend=EchoDraftBackend(), neutral_framing=False)
        result = stage.process([TextSegment(id=1, source_text=self.SOURCE)], _profile())
        self.assertEqual(result.segments[0].translated_text, self.SOURCE)


if __name__ == "__main__":
    unittest.main()
