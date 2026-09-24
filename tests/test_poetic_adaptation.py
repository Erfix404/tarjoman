"""Tests for PoeticAdapter verse detection and adaptation (Pack C)."""
from __future__ import annotations

import unittest

from tarjoman.stages import PoeticAdapter

VERSE = (
    "Rise up, rise up, my merry men\n"
    "The dawn is breaking clear\n"
    "Take up your swords and follow me\n"
    "For winter draweth near"
)

PROSE = (
    "The committee convened on Tuesday morning to discuss the quarterly "
    "financial report and the proposed amendments to the regulatory framework "
    "governing international trade agreements between member states."
)


class TestPoeticAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = PoeticAdapter()

    def test_verse_detected_as_poetic(self) -> None:
        self.assertTrue(self.adapter.is_poetic(VERSE))

    def test_prose_not_poetic(self) -> None:
        self.assertFalse(self.adapter.is_poetic(PROSE))
        self.assertFalse(self.adapter.is_poetic(""))
        self.assertFalse(self.adapter.is_poetic("   "))

    def test_keyword_triggers_poetic(self) -> None:
        self.assertTrue(self.adapter.is_poetic("She sang a song of the sea."))

    def test_classify_song(self) -> None:
        self.assertEqual(
            self.adapter.classify_verse_type("A song the sailors sing at dawn\nchorus of the tide"),
            "song",
        )

    def test_classify_riddle(self) -> None:
        self.assertEqual(
            self.adapter.classify_verse_type("A riddle: I speak without a mouth\nWhat am I?"),
            "riddle",
        )

    def test_classify_hymn(self) -> None:
        self.assertEqual(
            self.adapter.classify_verse_type("A hymn of praise and glory\nchant it evermore"),
            "hymn",
        )

    def test_classify_prose(self) -> None:
        self.assertEqual(self.adapter.classify_verse_type(PROSE), "prose")

    def test_classify_plain_verse_defaults_to_poem(self) -> None:
        self.assertEqual(self.adapter.classify_verse_type(VERSE), "poem")

    def test_extract_stanzas(self) -> None:
        text = "line one\nline two\n\nline three\nline four"
        stanzas = self.adapter.extract_stanzas(text)
        self.assertEqual(stanzas, [["line one", "line two"], ["line three", "line four"]])

    def test_adapt_to_persian_verse(self) -> None:
        out = self.adapter.adapt_to_persian_verse("Morning comes\nBirds awake")
        self.assertIn("قالب: couplet", out)
        self.assertIn("وزن: fa'ulun", out)
        self.assertIn("مصرع 1: Morning comes", out)
        self.assertIn("مصرع 2: Birds awake", out)

    def test_format_bilingual_verse(self) -> None:
        out = self.adapter.format_bilingual_verse("Morning comes", "صبح آمد")
        self.assertIn("EN: Morning comes", out)
        self.assertIn("FA: صبح آمد", out)


if __name__ == "__main__":
    unittest.main()
