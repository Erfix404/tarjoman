"""Pack B: EPUB roundtrip parser/composer, fallback, and 34-verb ZWNJ engine."""
from __future__ import annotations

import io
import zipfile

from tarjoman.composers.epub_roundtrip import EpubRoundtripComposer
from tarjoman.parsers.epub_parser import EpubParser
from tarjoman.stages.anti_calque import AntiCalqueEngine

CH1 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Ch One</title></head>
<body><p>Hello <em>world</em> and <code>x = 1</code></p><p>Second para</p></body></html>"""

CH2 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Ch Two</title></head>
<body><h1>Title here</h1><p>See <a href="https://example.com">click</a> and <strong>bold</strong></p></body></html>"""

OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Mini</dc:title><dc:language>en</dc:language><dc:creator>Tester</dc:creator>
</metadata><manifest>
<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
<item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>
<item id="css" href="styles.css" media-type="text/css"/>
<item id="img" href="img.png" media-type="image/png"/>
</manifest><spine><itemref idref="ch1"/><itemref idref="ch2"/></spine></package>"""

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
</rootfiles></container>"""


def make_mini_epub() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", OPF, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/ch1.xhtml", CH1, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/ch2.xhtml", CH2, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/styles.css", "p { color: red; }", compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/img.png", b"\x89PNG\r\n\x1a\n", compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def test_epub_parser_extracts_nodes_with_inline_tags() -> None:
    parsed = EpubParser().parse(make_mini_epub())
    assert len(parsed.chapters) == 2
    assert parsed.metadata["title"] == "Mini"
    html_all = " ".join(n.html_content for c in parsed.chapters for n in c.text_nodes)
    for tag in ("<em>", "<code>", "<a ", "<strong>"):
        assert tag in html_all, f"missing inline tag {tag}"
    assert all(n.id.startswith(n.chapter_id) for c in parsed.chapters for n in c.text_nodes)


def test_epub_roundtrip_composer_rtl_and_vazirmatn() -> None:
    parsed = EpubParser().parse(make_mini_epub())
    translations = {n.id: f"ترجمه {n.id}" for c in parsed.chapters for n in c.text_nodes}
    out = EpubRoundtripComposer().compose(parsed, translations=translations)
    zf = zipfile.ZipFile(io.BytesIO(out))
    infos = zf.infolist()
    assert infos[0].filename == "mimetype"
    assert infos[0].compress_type == zipfile.ZIP_STORED
    assert zf.read("mimetype").decode("ascii") == "application/epub+zip"
    # Original assets preserved.
    assert zf.read("OEBPS/styles.css").decode() == "p { color: red; }"
    assert zf.read("OEBPS/img.png") == b"\x89PNG\r\n\x1a\n"
    opf = zf.read("OEBPS/content.opf").decode("utf-8")
    assert "<dc:language>fa</dc:language>" in opf
    assert 'page-progression-direction="rtl"' in opf
    for chapter in parsed.chapters:
        body = zf.read(chapter.href).decode("utf-8")
        assert 'dir="rtl"' in body
        assert 'lang="fa"' in body
        assert "Vazirmatn" in body
        assert f"ترجمه {chapter.id}_node_0" in body


def test_epub_roundtrip_fallback() -> None:
    parsed = EpubParser().parse(make_mini_epub())
    originals = {n.id: n.html_content for c in parsed.chapters for n in c.text_nodes}
    ids = list(originals)
    # None / empty / whitespace translations fall back to source without crashing.
    translations = {ids[0]: None, ids[1]: "", ids[2]: "   "}  # type: ignore[dict-item]

    def boom(node):  # type: ignore[no-untyped-def]
        raise RuntimeError("translator down")

    out = EpubRoundtripComposer().compose(
        parsed, translations=translations, node_translator=boom
    )
    zf = zipfile.ZipFile(io.BytesIO(out))
    bodies = " ".join(
        zf.read(c.href).decode("utf-8") for c in parsed.chapters
    )
    for nid, src in originals.items():
        assert src in bodies, f"fallback lost for {nid}"


def test_34_verbs_zwnj_normalization() -> None:
    zwnj = "‌"
    positives = {
        "می رود": f"می{zwnj}رود",
        "نمی گوید": f"نمی{zwnj}گوید",
        "می خواند": f"می{zwnj}خواند",
        "می نوشت": f"می{zwnj}نوشت",
        "می سازد": f"می{zwnj}سازد",
        "می بیند": f"می{zwnj}بیند",
        "می شنود": f"می{zwnj}شنود",
        "نمی خرد": f"نمی{zwnj}خرد",
    }
    for src, expected in positives.items():
        assert AntiCalqueEngine.normalize_zwnj(src) == expected, src
    for untouched in ("شیمی", "زمین", "صمیمی", "امید", "عظیم", "مینی‌مالیستی"):
        assert AntiCalqueEngine.normalize_zwnj(untouched) == untouched, untouched
