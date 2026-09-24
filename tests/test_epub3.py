"""
Tests for the Tarjoman EPUB 3 Composer (Super-Skill v2).

Covers:
- Full EPUB 3 structure: mimetype (first, uncompressed), container.xml,
  content.opf (metadata/manifest/spine), toc.xhtml nav document, chapters,
  CSS with strict RTL
- Metadata: title, author, language, identifier
- Strict RTL orientation: dir="rtl", xml:lang="fa", direction/text-align CSS
- Bidi isolation for code blocks, formulas, and numeric spans (dir="ltr")
- ZIP validity: opens with zipfile, file list sane, XHTML well-formed XML
- Chapters: heading split, paragraph chunking, escaping (XSS-safe)
- CLI: `tarjoman compose epub ...` writes a valid .epub file
"""
from __future__ import annotations

import io
import unittest
import xml.etree.ElementTree as ET
import zipfile

from click.testing import CliRunner

from tarjoman.cli import cli
from tarjoman.composers.epub3 import Epub3Composer


SAMPLE_FA = (
    "# فصل اول\n\n"
    "او با لبخندی آرام گفت: «این یک متن پاکیزه است.»\n\n"
    "فرمول انرژی $E=mc^2$ در متن آمده و عدد ۱۲۳ نیز هست.\n\n"
    "# فصل دوم\n\n"
    "در پایان این بخش، کد زیر را ببینید:\n\n"
    "```python\nprint('سلام')\n```\n\n"
    "منبع: https://example.com/article برای مطالعه بیشتر."
)


def _open_epub(epub_bytes: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(epub_bytes))


class TestEpub3Structure(unittest.TestCase):
    """EPUB 3 package structure and W3C compliance."""

    def setUp(self) -> None:
        self.composer = Epub3Composer()
        self.epub_bytes = self.composer.compose(SAMPLE_FA, title="کتاب آزمایشی")

    def test_valid_zip_archive(self) -> None:
        with _open_epub(self.epub_bytes) as zf:
            bad = zf.testzip()
            self.assertIsNone(bad)
            self.assertGreater(len(zf.namelist()), 5)

    def test_mimetype_first_and_uncompressed(self) -> None:
        with _open_epub(self.epub_bytes) as zf:
            infos = zf.infolist()
            self.assertEqual(infos[0].filename, "mimetype")
            self.assertEqual(infos[0].compress_type, zipfile.ZIP_STORED)
            self.assertEqual(zf.read("mimetype").decode("ascii"), "application/epub+zip")

    def test_container_xml(self) -> None:
        with _open_epub(self.epub_bytes) as zf:
            container = zf.read("META-INF/container.xml").decode("utf-8")
        root = ET.fromstring(container)
        self.assertIn("container", root.tag)
        self.assertIn("OEBPS/content.opf", container)

    def test_opf_metadata_manifest_spine(self) -> None:
        with _open_epub(self.epub_bytes) as zf:
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        root = ET.fromstring(opf)
        self.assertIn("package", root.tag)
        self.assertIn("<metadata", opf)
        self.assertIn("<manifest", opf)
        self.assertIn("<spine", opf)
        self.assertIn("کتاب آزمایشی", opf)
        # nav + css + chapters present in manifest
        self.assertIn('properties="nav"', opf)
        self.assertIn("book.css", opf)
        self.assertIn("chapter-1.xhtml", opf)

    def test_nav_document(self) -> None:
        with _open_epub(self.epub_bytes) as zf:
            toc = zf.read("OEBPS/toc.xhtml").decode("utf-8")
        root = ET.fromstring(toc)
        self.assertIn("html", root.tag)
        self.assertIn('epub:type="toc"', toc)
        self.assertIn("فصل اول", toc)
        self.assertIn("فصل دوم", toc)

    def test_chapters_are_well_formed_xml(self) -> None:
        with _open_epub(self.epub_bytes) as zf:
            chapter_files = sorted(
                n for n in zf.namelist() if n.startswith("OEBPS/chapter-")
            )
        self.assertGreaterEqual(len(chapter_files), 2)
        with _open_epub(self.epub_bytes) as zf:
            for fname in chapter_files:
                doc = zf.read(fname).decode("utf-8")
                root = ET.fromstring(doc)  # raises if malformed
                self.assertIn("html", root.tag)


class TestEpub3Metadata(unittest.TestCase):
    """Title, author, language, and identifier handling."""

    def test_author_and_language(self) -> None:
        composer = Epub3Composer()
        epub_bytes = composer.compose(
            "متن نمونه.", title="عنوان", author="مترجم", language="fa"
        )
        with _open_epub(epub_bytes) as zf:
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        self.assertIn("مترجم", opf)
        self.assertIn("<dc:language>fa</dc:language>", opf)

    def test_custom_identifier(self) -> None:
        composer = Epub3Composer()
        epub_bytes = composer.compose("متن نمونه.", identifier="my-book-123")
        with _open_epub(epub_bytes) as zf:
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        self.assertIn("my-book-123", opf)

    def test_list_input_accepted(self) -> None:
        composer = Epub3Composer()
        epub_bytes = composer.compose(["بند اول.", "بند دوم."], title="فهرستی")
        with _open_epub(epub_bytes) as zf:
            self.assertIn("OEBPS/chapter-1.xhtml", zf.namelist())


class TestEpub3Rtl(unittest.TestCase):
    """Strict RTL orientation on every content document."""

    def test_chapter_rtl_attributes(self) -> None:
        composer = Epub3Composer()
        epub_bytes = composer.compose("متن نمونه.", title="راست‌به‌چپ")
        with _open_epub(epub_bytes) as zf:
            doc = zf.read("OEBPS/chapter-1.xhtml").decode("utf-8")
            toc = zf.read("OEBPS/toc.xhtml").decode("utf-8")
            css = zf.read("OEBPS/styles/book.css").decode("utf-8")
        self.assertIn('dir="rtl"', doc)
        self.assertIn('xml:lang="fa"', doc)
        self.assertIn('dir="rtl"', toc)
        self.assertIn("direction: rtl;", css)
        self.assertIn("text-align: right;", css)


class TestEpub3BidiIsolation(unittest.TestCase):
    """Code, formulas, and numbers are LTR-isolated inside RTL chapters."""

    def test_code_math_url_isolated(self) -> None:
        composer = Epub3Composer()
        epub_bytes = composer.compose(SAMPLE_FA, title="آزمون جداسازی")
        with _open_epub(epub_bytes) as zf:
            docs = "\n".join(
                zf.read(n).decode("utf-8")
                for n in zf.namelist()
                if n.startswith("OEBPS/chapter-")
            )
        self.assertIn('<pre dir="ltr">', docs)
        self.assertIn('class="math"', docs)
        self.assertIn('dir="ltr"', docs)

    def test_typst_style_isolate_helper(self) -> None:
        from tarjoman.composers.typst_pdf import TypstPdfComposer

        out = TypstPdfComposer.isolate_bidi_spans("متن با [12] و واژه test در آن.")
        self.assertIn("[12]", out)
        self.assertIn("test", out)


class TestEpub3Escaping(unittest.TestCase):
    """XHTML escaping: hostile input cannot break the package."""

    def test_xss_escaped(self) -> None:
        composer = Epub3Composer()
        epub_bytes = composer.compose(
            "<script>alert('xss')</script>", title="<tag>عنوان</tag>"
        )
        with _open_epub(epub_bytes) as zf:
            doc = zf.read("OEBPS/chapter-1.xhtml").decode("utf-8")
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        self.assertNotIn("<script>alert", doc)
        self.assertIn("&lt;script&gt;", doc)
        self.assertNotIn("<tag>عنوان</tag>", opf)

    def test_chapter_docs_still_well_formed(self) -> None:
        composer = Epub3Composer()
        epub_bytes = composer.compose("<b>bold & raw</b>")
        with _open_epub(epub_bytes) as zf:
            doc = zf.read("OEBPS/chapter-1.xhtml").decode("utf-8")
        ET.fromstring(doc)


class TestEpub3Cli(unittest.TestCase):
    """`tarjoman compose epub` writes a valid .epub file."""

    def test_compose_epub_subcommand(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("fa.txt", "w", encoding="utf-8") as f:
                f.write(SAMPLE_FA)
            result = runner.invoke(
                cli,
                [
                    "compose",
                    "epub",
                    "fa.txt",
                    "-o",
                    "book.epub",
                    "--title",
                    "کتاب آزمایشی",
                ],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            with open("book.epub", "rb") as f:
                epub_bytes = f.read()
            with _open_epub(epub_bytes) as zf:
                self.assertIsNone(zf.testzip())
                self.assertEqual(
                    zf.read("mimetype").decode("ascii"), "application/epub+zip"
                )


class TestEpub3Inspect(unittest.TestCase):
    """inspect_epub reports structural flags."""

    def test_inspect_flags(self) -> None:
        composer = Epub3Composer()
        epub_bytes = composer.compose(SAMPLE_FA, title="بازرسی")
        info = Epub3Composer.inspect_epub(epub_bytes)
        self.assertTrue(info["mimetype_ok"])
        self.assertTrue(info["rtl_ok"])
        self.assertTrue(info["opf_ok"])
        self.assertIn("OEBPS/toc.xhtml", info["files"])


if __name__ == "__main__":
    unittest.main()
