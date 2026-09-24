"""
Tests for Long-Form Book Translation Infrastructure (Super-Skill v2).

Covers:
- manifest.py: SHA-256 content hashing, chapter/chunk metadata, status and
  word counts, resumable workflow (skip already-translated hashes),
  JSON serialization round-trip
- character_bible.py: voice profiles (names, Persian transliterations,
  gender, tone, تو/شما address pronouns), serialization, queries
- termbase.py: SQLite-backed domain-tagged store, search, resolve,
  usage tracking, cascade re-translation detection and acknowledgement
- memory/__init__.py: clean public exports
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tarjoman.memory import (
    BookManifestManager,
    CharacterBible,
    CharacterProfile,
    Termbase,
    sha256_text,
)


class TestSha256Hashing(unittest.TestCase):
    """Deterministic SHA-256 content hashing for chunk caching."""

    def test_known_digest(self) -> None:
        expected = hashlib.sha256("سلام".encode("utf-8")).hexdigest()
        self.assertEqual(sha256_text("سلام"), expected)
        self.assertEqual(len(sha256_text("anything")), 64)

    def test_content_sensitivity(self) -> None:
        self.assertNotEqual(sha256_text("متن الف"), sha256_text("متن ب"))
        self.assertEqual(sha256_text("تکرار"), sha256_text("تکرار"))


class TestBookManifestManager(unittest.TestCase):
    """Manifest management, caching, resume, and serialization."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manifest_path = Path(self.temp_dir.name) / "manifest.json"
        self.mgr = BookManifestManager(
            title="Test Book", manifest_path=self.manifest_path
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_chunks_and_word_counts(self) -> None:
        self.mgr.add_chunk(1, "Call me Ishmael.")
        self.mgr.add_chunk(1, "Some years ago.")
        chapter = self.mgr.get_chapter(1)
        self.assertIsNotNone(chapter)
        assert chapter is not None
        self.assertEqual(len(chapter.chunks), 2)
        self.assertEqual(chapter.source_words, 6)
        self.assertEqual(chapter.status, "pending")

    def test_duplicate_content_hash_deduplicates(self) -> None:
        first = self.mgr.add_chunk(1, "Same text.")
        second = self.mgr.add_chunk(1, "Same text.")
        self.assertEqual(first.content_hash, second.content_hash)
        chapter = self.mgr.get_chapter(1)
        assert chapter is not None
        self.assertEqual(len(chapter.chunks), 1)

    def test_resume_skips_translated_hashes(self) -> None:
        src = "Call me Ishmael."
        self.assertFalse(self.mgr.is_translated(1, src))
        self.mgr.add_chunk(1, src)
        self.mgr.mark_translated(1, src, "مرا اسماعیل صدا بزنید.")
        self.assertTrue(self.mgr.is_translated(1, src))
        # Same chapter/position but different content is NOT done.
        self.assertFalse(self.mgr.is_translated(1, "Different text."))
        # Resume list excludes the translated chunk.
        pending = self.mgr.pending_chunks(1)
        self.assertEqual(pending, [])

    def test_mark_failed_and_pending(self) -> None:
        self.mgr.add_chunk(2, "Failing chunk here.")
        self.mgr.mark_failed(2, "Failing chunk here.")
        pending = self.mgr.pending_chunks(2)
        self.assertEqual(len(pending), 1)
        chapter = self.mgr.get_chapter(2)
        assert chapter is not None
        self.assertEqual(chapter.status, "failed")

    def test_stats_progress(self) -> None:
        self.mgr.add_chunk(1, "One two.")
        self.mgr.add_chunk(1, "Three four.")
        self.mgr.mark_translated(1, "One two.", "یک دو.")
        stats = self.mgr.get_stats()
        self.assertEqual(stats["total_chunks"], 2)
        self.assertEqual(stats["translated_chunks"], 1)
        self.assertEqual(stats["pending_chunks"], 1)
        self.assertAlmostEqual(stats["progress"], 0.5)

    def test_save_and_load_roundtrip(self) -> None:
        self.mgr.add_chunk(1, "Call me Ishmael.")
        self.mgr.mark_translated(1, "Call me Ishmael.", "مرا اسماعیل صدا بزنید.")
        self.mgr.save()
        self.assertTrue(self.manifest_path.exists())

        fresh = BookManifestManager(manifest_path=self.manifest_path)
        self.assertEqual(fresh.title, "Test Book")
        self.assertTrue(fresh.is_translated(1, "Call me Ishmael."))
        stats = fresh.get_stats()
        self.assertEqual(stats["translated_chunks"], 1)

    def test_manifest_json_schema(self) -> None:
        self.mgr.add_chunk(1, "Sample.")
        self.mgr.save()
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(data["manifest_version"], "2.0")
        self.assertEqual(data["title"], "Test Book")
        chapter = data["chapters"][0]
        self.assertIn("chunks", chapter)
        self.assertIn("content_hash", chapter["chunks"][0])


class TestCharacterBible(unittest.TestCase):
    """Character voices, transliterations, pronouns, queries, persistence."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.bible_path = Path(self.temp_dir.name) / "characters.json"
        self.bible = CharacterBible(bible_path=self.bible_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_record_and_query(self) -> None:
        self.bible.record_character(
            name="Rustam",
            persian_name="رستم",
            gender="male",
            tone="epic_formal",
            default_address="شما",
            speech_quirks=["archaic vocabulary"],
        )
        profile = self.bible.get_character("Rustam")
        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(profile.persian_name, "رستم")
        self.assertEqual(profile.gender, "male")
        self.assertEqual(profile.tone, "epic_formal")

    def test_case_insensitive_lookup(self) -> None:
        self.bible.record_character("Sohrab", persian_name="سهراب")
        self.assertIsNotNone(self.bible.get_character("sohrab"))
        self.assertIsNone(self.bible.get_character("Unknown"))

    def test_address_pronouns(self) -> None:
        self.bible.record_character("Elder", default_address="تو")
        self.bible.record_character("King", default_address="شما")
        self.assertEqual(self.bible.address_pronoun("Elder"), "تو")
        self.assertEqual(self.bible.address_pronoun("King"), "شما")
        self.assertEqual(self.bible.address_pronoun("Stranger"), "شما")

    def test_invalid_pronoun_defaults_to_shoma(self) -> None:
        profile = self.bible.record_character("Weird", default_address=" худ ")
        self.assertEqual(profile.default_address, "شما")

    def test_list_filter_and_search(self) -> None:
        self.bible.record_character("A", tone="epic_formal", gender="male")
        self.bible.record_character("B", tone="colloquial", gender="female")
        self.assertEqual(len(self.bible.list_characters(tone="epic_formal")), 1)
        self.assertEqual(len(self.bible.list_characters(gender="female")), 1)
        self.assertEqual(len(self.bible.search("colloquial")), 1)
        self.assertEqual(self.bible.count(), 2)

    def test_remove_character(self) -> None:
        self.bible.record_character("Temp")
        self.assertTrue(self.bible.remove_character("temp"))
        self.assertFalse(self.bible.remove_character("temp"))

    def test_save_and_load_roundtrip(self) -> None:
        self.bible.record_character("Rustam", persian_name="رستم", tone="epic_formal")
        self.bible.save()
        fresh = CharacterBible(bible_path=self.bible_path)
        profile = fresh.get_character("rustam")
        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(profile.persian_name, "رستم")

    def test_profile_dataclass_roundtrip(self) -> None:
        profile = CharacterProfile(
            name="X", persian_name="ایکس", gender="female", tone="literary"
        )
        restored = CharacterProfile.from_dict(profile.to_dict())
        self.assertEqual(restored.persian_name, "ایکس")


class TestTermbase(unittest.TestCase):
    """SQLite termbase: domain tagging, search, cascade re-translation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "terms.db"
        self.tb = Termbase(db_path=self.db_path)

    def tearDown(self) -> None:
        self.tb.close()
        self.temp_dir.cleanup()

    def test_record_and_resolve(self) -> None:
        self.tb.record_term("attention mechanism", "سازوکار توجه", domain="scientific")
        self.assertEqual(self.tb.resolve_term("attention mechanism"), "سازوکار توجه")
        # Case-insensitive fallback
        self.assertEqual(self.tb.resolve_term("Attention Mechanism"), "سازوکار توجه")
        self.assertTrue(self.tb.has_term("attention mechanism"))
        self.assertFalse(self.tb.has_term("missing term"))

    def test_domain_tagging_and_filter(self) -> None:
        self.tb.record_term("deep learning", "یادگیری عمیق", domain="scientific")
        self.tb.record_term("injunction", "دستور موقت", domain="legal")
        sci = self.tb.get_all_terms(domain="scientific")
        self.assertIn("deep learning", sci)
        self.assertNotIn("injunction", sci)
        self.assertEqual(self.tb.count(domain="legal"), 1)

    def test_search(self) -> None:
        self.tb.record_term("tokenization", "نشانه‌گذاری", domain="technical", notes="NLP")
        hits = self.tb.search("token")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].fa_term, "نشانه‌گذاری")
        # Persian-side search
        hits_fa = self.tb.search("نشانه")
        self.assertEqual(len(hits_fa), 1)
        # Domain-scoped search excludes other domains
        self.assertEqual(self.tb.search("token", domain="legal"), [])

    def test_cascade_retranslation_detection(self) -> None:
        self.tb.record_term("quantum", "کوانتومی", domain="scientific")
        self.tb.record_usage("quantum", chapter_id=1, segment_id=3, domain="scientific")
        self.tb.record_usage("quantum", chapter_id=2, segment_id=1, domain="scientific")

        event = self.tb.update_term("quantum", "کوانتمی", domain="scientific")
        self.assertEqual(event.old_fa_term, "کوانتومی")
        self.assertEqual(event.new_fa_term, "کوانتمی")
        self.assertEqual(event.affected_segments, [(1, 3), (2, 1)])
        self.assertEqual(self.tb.resolve_term("quantum"), "کوانتمی")

    def test_pending_and_acknowledge_cascades(self) -> None:
        self.tb.record_term("photon", "فوتون")
        self.tb.record_usage("photon", 1, 1)
        self.tb.update_term("photon", "فتون")
        pending = self.tb.pending_cascades()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].en_term, "photon")
        removed = self.tb.acknowledge_cascade("PHOTON")
        self.assertEqual(removed, 1)
        self.assertEqual(self.tb.pending_cascades(), [])

    def test_in_memory_database(self) -> None:
        mem = Termbase(db_path=":memory:")
        try:
            mem.record_term("test", "آزمون")
            self.assertEqual(mem.resolve_term("test"), "آزمون")
        finally:
            mem.close()

    def test_persistence_across_instances(self) -> None:
        self.tb.record_term("gravity", "گرانش", domain="scientific")
        self.tb.close()
        reopened = Termbase(db_path=self.db_path)
        try:
            self.assertEqual(reopened.resolve_term("gravity"), "گرانش")
        finally:
            reopened.close()


class TestMemoryExports(unittest.TestCase):
    """memory/__init__.py exposes the v2 infrastructure cleanly."""

    def test_public_names(self) -> None:
        import tarjoman.memory as mem

        for name in (
            "ResumableCache",
            "StateManager",
            "BookManifestManager",
            "ChapterRecord",
            "ChunkRecord",
            "sha256_text",
            "CharacterBible",
            "CharacterProfile",
            "Termbase",
            "TermRecord",
            "CascadeEvent",
        ):
            self.assertTrue(hasattr(mem, name), f"memory.{name} missing")


if __name__ == "__main__":
    unittest.main()
