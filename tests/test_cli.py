"""
Tests for Tarjoman CLI Command Suite.

Covers:
- `cli --version` and general help
- `route` subcommand with raw string and file path
- `translate` subcommand with stdout, file output, and composers
- `compose` group: bilingual, html, and typst (with --compile)
- `audit` subcommand with MQM reporting
- `lint` subcommand on clean and faulty files
- `book` group: `book init` and `book status`
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from click.testing import CliRunner

from tarjoman.cli import cli


class TestCliSuite(unittest.TestCase):
    """Integration test suite for Tarjoman CLI commands."""

    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_version_option(self) -> None:
        """Verify tarjoman --version prints correct version string."""
        result = self.runner.invoke(cli, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("1.0.0", result.output)

    def test_route_command_string(self) -> None:
        """Verify route subcommand on inline text string."""
        text = "The twilight deepened across the valley as Elena whispered with deep sorrow."
        result = self.runner.invoke(cli, ["route", text])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Domain: literary", result.output)
        self.assertIn("Persian Title: ادبی", result.output)
        self.assertIn("Confidence:", result.output)

    def test_route_command_file(self) -> None:
        """Verify route subcommand on a text file."""
        with self.runner.isolated_filesystem():
            sample_file = Path("med_sample.txt")
            sample_file.write_text(
                "In this randomized clinical trial, patients received a therapeutic dosage of 50 mg/kg.",
                encoding="utf-8",
            )
            result = self.runner.invoke(cli, ["route", str(sample_file)])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Domain: medical", result.output)
            self.assertIn("پزشکی", result.output)

    def test_translate_command_stdout(self) -> None:
        """Verify translate command outputs translated text to stdout when no -o is provided."""
        with self.runner.isolated_filesystem():
            src_file = Path("source.txt")
            src_file.write_text("The developer installed dependencies using npm install in the repository.", encoding="utf-8")

            result = self.runner.invoke(cli, ["translate", str(src_file), "-d", "technical"])
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(len(result.output.strip()) > 0)

    def test_translate_command_output_file_and_composer(self) -> None:
        """Verify translate command with output path and composer option."""
        with self.runner.isolated_filesystem():
            src_file = Path("lit_input.txt")
            src_file.write_text("Marcus smiled faintly, his heart aching.", encoding="utf-8")
            out_file = Path("output.md")

            result = self.runner.invoke(
                cli,
                [
                    "translate",
                    str(src_file),
                    "-d",
                    "literary",
                    "-o",
                    str(out_file),
                    "--composer",
                    "bilingual",
                ],
            )
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("|", content)  # Markdown table delimiter
            self.assertIn("Translation saved to", result.output)

    def test_compose_bilingual_subcommand(self) -> None:
        """Verify compose bilingual command creates aligned Markdown table."""
        with self.runner.isolated_filesystem():
            src = Path("en.txt")
            tgt = Path("fa.txt")
            out = Path("bilingual.md")

            src.write_text("Hello world.\n\nSecond paragraph.", encoding="utf-8")
            tgt.write_text("سلام دنیا.\n\nبند دوم.", encoding="utf-8")

            result = self.runner.invoke(
                cli,
                ["compose", "bilingual", str(src), str(tgt), "-o", str(out)],
            )
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(out.exists())
            content = out.read_text(encoding="utf-8")
            self.assertIn("سلام دنیا", content)
            self.assertIn("Hello world", content)

    def test_compose_html_subcommand(self) -> None:
        """Verify compose html command creates standalone HTML reader."""
        with self.runner.isolated_filesystem():
            src = Path("en.txt")
            tgt = Path("fa.txt")
            out = Path("reader.html")

            src.write_text("Introduction to AI systems.", encoding="utf-8")
            tgt.write_text("مقدمه‌ای بر سامانه‌های هوش مصنوعی.", encoding="utf-8")

            result = self.runner.invoke(
                cli,
                [
                    "compose",
                    "html",
                    str(src),
                    str(tgt),
                    "-o",
                    str(out),
                    "--title",
                    "کتاب هوش مصنوعی",
                ],
            )
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(out.exists())
            content = out.read_text(encoding="utf-8")
            self.assertIn("<!DOCTYPE html>", content)
            self.assertIn("کتاب هوش مصنوعی", content)
            self.assertIn("Vazirmatn", content)

    def test_compose_typst_subcommand(self) -> None:
        """Verify compose typst generates Typst source and compiles PDF."""
        with self.runner.isolated_filesystem():
            tgt = Path("text.txt")
            tgt.write_text("این یک متن نمونه برای کامپایل تایپست است.", encoding="utf-8")
            out_typ = Path("doc.typ")

            result = self.runner.invoke(
                cli,
                [
                    "compose",
                    "typst",
                    str(tgt),
                    "-s",
                    "paper",
                    "-o",
                    str(out_typ),
                    "--compile",
                ],
            )
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(out_typ.exists())
            typ_code = out_typ.read_text(encoding="utf-8")
            self.assertIn('#set page(paper: "a4"', typ_code)

            out_pdf = Path("doc.pdf")
            self.assertTrue(out_pdf.exists())
            self.assertGreater(out_pdf.stat().st_size, 0)

    def test_audit_subcommand(self) -> None:
        """Verify audit subcommand runs Stage 5 MQM audit."""
        with self.runner.isolated_filesystem():
            target_file = Path("target.txt")
            target_file.write_text(
                "او با آرامش گفت: «این یک ترجمه دقیق است.»",
                encoding="utf-8",
            )
            result = self.runner.invoke(cli, ["audit", str(target_file), "-d", "literary"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Tarjoman MQM Audit", result.output)
            self.assertIn("Quality Score:", result.output)
            self.assertIn("Status: PASSED", result.output)

    def test_lint_subcommand_clean_and_faulty(self) -> None:
        """Verify lint subcommand passes clean files and flags faulty files."""
        with self.runner.isolated_filesystem():
            clean_file = Path("clean.md")
            clean_file.write_text("او گفت: «سلام بر شما.»", encoding="utf-8")

            res_clean = self.runner.invoke(cli, ["lint", str(clean_file)])
            self.assertEqual(res_clean.exit_code, 0)
            self.assertIn("PASSED", res_clean.output)

            faulty_file = Path("faulty.md")
            faulty_file.write_text("این جمله — خط تیره دارد و توسط او نوشته شد.", encoding="utf-8")

            res_faulty = self.runner.invoke(cli, ["lint", str(faulty_file)])
            self.assertNotEqual(res_faulty.exit_code, 0)
            self.assertIn("FAILED", res_faulty.output)
            self.assertIn("EM-DASH", res_faulty.output)
            self.assertIn("CALQUE", res_faulty.output)

    def test_book_init_and_status(self) -> None:
        """Verify book init creates project files and book status displays statistics."""
        with self.runner.isolated_filesystem():
            proj_dir = Path("my_persian_novel")

            init_res = self.runner.invoke(
                cli,
                ["book", "init", "The Great Odyssey", "-o", str(proj_dir)],
            )
            self.assertEqual(init_res.exit_code, 0)
            self.assertTrue(proj_dir.exists())

            manifest_file = proj_dir / "manifest.json"
            terms_file = proj_dir / "terms.tsv"
            self.assertTrue(manifest_file.exists())
            self.assertTrue(terms_file.exists())

            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            self.assertEqual(manifest_data["title"], "The Great Odyssey")
            self.assertEqual(manifest_data["total_chapters"], 1)

            # Add a couple of terms to terms.tsv
            with open(terms_file, "a", encoding="utf-8") as f:
                f.write("Odyssey\tادیسه\tliterary\tepic journey\n")
                f.write("Voyage\tسفر دریایی\tliterary\tjourney\n")

            status_res = self.runner.invoke(cli, ["book", "status", str(proj_dir)])
            self.assertEqual(status_res.exit_code, 0)
            self.assertIn("Book Project Status: The Great Odyssey", status_res.output)
            self.assertIn("Dynamic Terms: 2", status_res.output)
            self.assertIn("Chapters: 0 / 1", status_res.output)


if __name__ == "__main__":
    unittest.main()


class TestPackCCli(unittest.TestCase):
    """Pack C: `epub roundtrip` and `scene` command groups."""

    def setUp(self) -> None:
        self.runner = CliRunner()

    def _make_epub(self, path: Path) -> None:
        import zipfile

        container = (
            '<container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>'
        )
        opf = (
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>T</dc:title><dc:language>en</dc:language>"
            "<dc:creator>A</dc:creator></metadata>"
            '<manifest><item id="ch1" href="ch1.xhtml" '
            'media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="ch1"/></spine></package>'
        )
        ch1 = (
            "<html><head><title>Ch1</title></head>"
            "<body><p>Hello world</p></body></html>"
        )
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("META-INF/container.xml", container)
            zf.writestr("OEBPS/content.opf", opf)
            zf.writestr("OEBPS/ch1.xhtml", ch1)

    def test_epub_roundtrip_default_output(self) -> None:
        """Verify epub roundtrip composes a translated EPUB with default name."""
        with self.runner.isolated_filesystem():
            src = Path("book.epub")
            self._make_epub(src)
            result = self.runner.invoke(cli, ["epub", "roundtrip", str(src)])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Chapters: 1", result.output)
            self.assertIn("Text nodes: 1", result.output)
            self.assertTrue(Path("book_translated.epub").exists())

    def test_epub_roundtrip_custom_output_and_domain(self) -> None:
        """Verify epub roundtrip honors -o and --domain options."""
        with self.runner.isolated_filesystem():
            src = Path("book.epub")
            self._make_epub(src)
            result = self.runner.invoke(
                cli,
                ["epub", "roundtrip", str(src), "-o", "out.epub",
                 "--domain", "technical"],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("technical", result.output)
            self.assertTrue(Path("out.epub").exists())

    def test_scene_record_status_check_reset(self) -> None:
        """Verify scene record/status/check/reset lifecycle."""
        with self.runner.isolated_filesystem():
            state = "scene.json"
            result = self.runner.invoke(
                cli,
                ["scene", "record", "--chapter", "ch1", "--pov", "first_person",
                 "--location", "Library", "--atmosphere", "gloomy",
                 "--state-file", state],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Scene recorded", result.output)

            result = self.runner.invoke(cli, ["scene", "status", "--state-file", state])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("first_person", result.output)
            self.assertIn("Library", result.output)

            result = self.runner.invoke(cli, ["scene", "check", "--state-file", state])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Continuity OK", result.output)

            result = self.runner.invoke(cli, ["scene", "reset", "--state-file", state])
            self.assertEqual(result.exit_code, 0, result.output)

    def test_scene_status_empty(self) -> None:
        """Verify scene status with no recorded state."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(
                cli, ["scene", "status", "--state-file", "missing.json"]
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("No scene recorded", result.output)
