"""Regression tests for problems found by translating real texts (2026-11).

Each case comes from the A/B test in docs/research/real-texts/: a lint
finding that was wrong on correct Persian, or a real error it missed.
"""
import unittest

from tarjoman.linter import find_hekasre, lint_text


def cats(text):
    return [i.category for i in lint_text(text)]


class TestHekasreRealH(unittest.TestCase):
    def test_pronounced_h_is_not_hekasre(self) -> None:
        for text in ("وقتی توفان اندوه خودش را خرج کرد", "راه من", "کوه او", "گروه ما", "میوه من"):
            self.assertEqual(find_hekasre(text), [], text)

    def test_real_hekasre_still_flagged(self) -> None:
        self.assertTrue(find_hekasre("کتابه من کجاست؟"))


class TestColloquialZwnj(unittest.TestCase):
    def test_glued_mi_flagged(self) -> None:
        for text in ("نمیدونم، خسته‌ام", "اگه بد بود میرم", "باشه میبینمت"):
            self.assertIn("zwnj", cats(text), text)

    def test_nouns_starting_with_mi_untouched(self) -> None:
        for text in ("میز را آوردم و میوه خوردم.", "میمون را دیدم.", "میدان شلوغ بود.", "میهمان آمد."):
            self.assertNotIn("zwnj", cats(text), text)

    def test_correct_colloquial_untouched(self) -> None:
        self.assertEqual(cats("نمی‌دونم، می‌رم خونه. می‌بینمت."), [])

    def test_persian_comma_is_a_word_boundary(self) -> None:
        self.assertIn("spelling", cats("این سئوال، مهم است."))


class TestCountPlural(unittest.TestCase):
    def test_plural_after_count_flagged(self) -> None:
        for text in ("آیا {count} فایل‌ها حذف شوند؟", "۳ کتاب‌ها خریدم."):
            self.assertIn("spelling", cats(text), text)

    def test_years_and_singular_untouched(self) -> None:
        for text in ("در سال ۲۰۲۰ شرکت‌ها رشد کردند.", "{count} فایل حذف شد.", "۳ تا از کتاب‌ها را خواندم."):
            self.assertNotIn("spelling", cats(text), text)


class TestSpeakerLabels(unittest.TestCase):
    def test_chat_label_not_bidi_noise(self) -> None:
        self.assertNotIn("bidi-isolate", cats("A: امشب هنوز میای؟"))
        self.assertNotIn("bidi-isolate", cats("Sarah: باشه، می‌بینمت."))


if __name__ == "__main__":
    unittest.main()


class TestRoundTwoFindings(unittest.TestCase):
    """Round 2: genres, news, editor mode and the book workflow."""

    def test_announcements_and_office_verbs_flagged(self) -> None:
        for text in (
            "لازم به ذکر است که این روش هزینه‌بر است.",
            "شایان ذکر است که نتایج قطعی نیست.",
            "این ابزار نقش مهمی ایفا می‌نماید.",
            "در این راستا، ابزار مفید است.",
            "در نهایت، می‌توان گفت که این خوب است.",
        ):
            self.assertIn("ai-tell", cats(text), text)

    def test_plain_verbs_untouched(self) -> None:
        for text in ("این کار را نمی‌کند.", "نمایش فیلم شروع شد.", "نماینده آمد.", "در نهایت به خانه رفت."):
            self.assertNotIn("ai-tell", cats(text), text)

    def test_latin_decimal_between_persian_digits(self) -> None:
        self.assertIn("punct", cats("نرخ به ۹.۵ درصد رسید."))
        self.assertNotIn("punct", cats("نرخ به ۹٫۵ درصد رسید."))


class TestBookTermsTsv(unittest.TestCase):
    def test_terms_added_by_cli_reach_tsv_and_check_reads_tsv(self) -> None:
        import tempfile
        from pathlib import Path

        from click.testing import CliRunner

        from tarjoman.cli import cli

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "book"
            self.assertEqual(runner.invoke(cli, ["book", "init", "کتاب", "-o", str(project)]).exit_code, 0)
            runner.invoke(cli, ["book", "terms", str(project), "--add", "Duchess=دوشس"])
            self.assertIn("Duchess\tدوشس", (project / "terms.tsv").read_text(encoding="utf-8"))
            # A term added by hand to the TSV is checked too.
            with (project / "terms.tsv").open("a", encoding="utf-8") as f:
                f.write("Oh dear\tوای خدا\t\t\n")
            src = Path(tmp) / "en.md"
            tgt = Path(tmp) / "fa.md"
            src.write_text("'Oh dear!' said the Duchess.\n", encoding="utf-8")
            tgt.write_text("دوشس گفت: «ای وای!»\n", encoding="utf-8")
            result = runner.invoke(cli, ["book", "check", str(project), str(src), str(tgt)])
            self.assertIn("Oh dear", result.output)
