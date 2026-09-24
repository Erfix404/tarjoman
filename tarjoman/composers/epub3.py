"""
EPUB 3 Composer for Tarjoman Universal Translation Engine.

Builds W3C-compliant EPUB 3 e-books from Persian (RTL) translations:

- ``mimetype`` (stored uncompressed, first entry of the ZIP)
- ``META-INF/container.xml``
- ``OEBPS/content.opf`` (package document: metadata, manifest, spine)
- ``OEBPS/toc.xhtml`` (EPUB 3 navigation document)
- Chapter XHTML documents (``OEBPS/chapter-N.xhtml``)
- ``OEBPS/styles/book.css`` with strict RTL orientation

Strict RTL orientation is enforced on every content document:
``dir="rtl"``, ``xml:lang="fa"``, and CSS
``direction: rtl; text-align: right;``. Code blocks, formulas, and numeric
spans are bidi-isolated (``dir="ltr"``) so LTR content never corrupts the
RTL layout.
"""
from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from tarjoman.composers.base import BaseComposer
from tarjoman.stages.anti_calque import mask_verbatim_spans

BOOK_CSS = """/* Tarjoman EPUB3 book stylesheet — strict RTL Persian layout */
html, body {
  direction: rtl;
  text-align: right;
}
body {
  font-family: "Vazirmatn", "Noto Naskh Arabic", serif;
  line-height: 2;
  margin: 0 5%;
  padding: 0;
}
h1, h2, h3, h4 {
  text-align: center;
  line-height: 1.8;
  page-break-after: avoid;
}
p {
  text-align: justify;
  text-indent: 1.5em;
  margin: 0.5em 0;
}
[dir="ltr"], pre, code {
  direction: ltr;
  text-align: left;
  unicode-bidi: isolate;
}
pre {
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 0.8em;
  overflow-x: auto;
  white-space: pre-wrap;
}
code {
  font-family: monospace;
  font-size: 0.9em;
}
blockquote {
  margin: 1em 2em;
  padding-right: 1em;
  border-right: 3px solid #888;
}
"""

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


class Epub3Composer(BaseComposer):
    """
    Composes W3C EPUB 3 e-books from Persian text.

    Small interface: :meth:`compose` returns EPUB bytes (or writes a file),
    :meth:`compose_to_file` writes directly to ``*.epub``.
    """

    #: Headings ``# …`` become chapter documents; bare prose is chunked.
    MAX_PARAGRAPHS_PER_CHAPTER = 40

    def __init__(self, max_paragraphs_per_chapter: int = MAX_PARAGRAPHS_PER_CHAPTER) -> None:
        self.max_paragraphs_per_chapter = max(1, max_paragraphs_per_chapter)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def compose(
        self,
        text: Union[str, List[str]],
        title: Optional[str] = None,
        author: Optional[str] = None,
        language: str = "fa",
        identifier: Optional[str] = None,
        output_path: Optional[Union[str, Path]] = None,
        *args: Any,
        **kwargs: Any,
    ) -> bytes:
        """
        Build an EPUB 3 book from Persian text.

        Args:
            text: Persian text (str) or a list of chapter/paragraph strings.
            title: Book title (defaults to «بدون عنوان»).
            author: Author or translator attribution.
            language: BCP-47 language tag (default ``fa``).
            identifier: Unique publication identifier (auto-generated if omitted).
            output_path: Optional path — when given, the EPUB is also written
                to this ``*.epub`` file.

        Returns:
            The complete EPUB archive as bytes.
        """
        paragraphs = self._coerce_paragraphs(text)
        chapters = self._split_chapters(paragraphs)

        book_title = (title or "بدون عنوان").strip()
        book_id = identifier or f"tarjoman-{abs(hash(book_title)) % 10**10:010d}"

        chapter_docs = [
            (f"chapter-{n}.xhtml", self._chapter_title(c), c)
            for n, c in enumerate(chapters, start=1)
        ]

        opf = self._build_opf(
            title=book_title,
            author=author,
            language=language,
            identifier=book_id,
            chapter_files=[doc for doc, _t, _c in chapter_docs],
        )
        nav = self._build_nav(
            title=book_title,
            chapters=[(doc, t) for doc, t, _c in chapter_docs],
        )

        epub_bytes = self._package_epub(chapter_docs, opf, nav)

        if output_path:
            out = Path(output_path)
            if out.parent and str(out.parent) not in ("", "."):
                out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(epub_bytes)

        return epub_bytes

    def compose_to_file(
        self,
        text: Union[str, List[str]],
        output_path: Union[str, Path],
        title: Optional[str] = None,
        author: Optional[str] = None,
        language: str = "fa",
        identifier: Optional[str] = None,
    ) -> Path:
        """Build an EPUB 3 book and write it to ``output_path``. Returns the path."""
        out = Path(output_path)
        self.compose(
            text,
            title=title,
            author=author,
            language=language,
            identifier=identifier,
            output_path=out,
        )
        return out

    # ------------------------------------------------------------------
    # Structure helpers
    # ------------------------------------------------------------------

    def _coerce_paragraphs(self, text: Union[str, List[str]]) -> List[str]:
        if isinstance(text, str):
            return self.split_paragraphs(text)
        return [p.strip() for p in text if p and p.strip()]

    def _split_chapters(self, paragraphs: List[str]) -> List[List[str]]:
        chapters: List[List[str]] = []
        current: List[str] = []
        for para in paragraphs:
            if re.match(r"^#{1,6}\s+\S", para.strip()) and current:
                chapters.append(current)
                current = [para]
            else:
                current.append(para)
            if len(current) >= self.max_paragraphs_per_chapter:
                chapters.append(current)
                current = []
        if current:
            chapters.append(current)
        return chapters or [[]]

    def _chapter_title(self, chapter: List[str]) -> str:
        for para in chapter:
            m = re.match(r"^#{1,6}\s+(.+)$", para.strip().split("\n")[0])
            if m:
                return m.group(1).strip()
        first = (chapter[0] if chapter else "")[:40].strip()
        return first or "فصل"

    # ------------------------------------------------------------------
    # XHTML rendering (strict RTL + LTR bidi isolation)
    # ------------------------------------------------------------------

    _FENCED_CODE_RE: Pattern = re.compile(r"```([^\n]*)\n(.*?)```", re.DOTALL)
    _INLINE_CODE_RE: Pattern = re.compile(r"`([^`\n]+)`")
    _MATH_RE: Pattern = re.compile(
        r"(\$\$.+?\$\$|(?<!\\)\$.+?(?<!\\)\$|\\\[.+?\\\]|\\\(.+?\\\))"
    )
    _URL_RE: Pattern = re.compile(r"(https?://[^\s<>\]\)\}«»\"']+)")

    @classmethod
    def _escape_prose(cls, prose: str) -> str:
        # Stash LTR runs BEFORE escaping so entity text produced by
        # html.escape (e.g. "&lt;") is never mistaken for Latin words —
        # wrapping inside an entity would emit invalid XML ("&<span...").
        stashed: List[str] = []

        def _stash(m: re.Match) -> str:
            stashed.append(m.group(0))
            return f"⟦LTR_{len(stashed) - 1}⟧"

        tmp = re.sub(r"[A-Za-z][A-Za-z0-9_./:@-]*", _stash, prose)
        tmp = re.sub(r"(?<!\d)([0-9۰-۹]+(?:[./:][0-9۰-۹]+)+)", _stash, tmp)
        escaped = html.escape(tmp, quote=False)
        for i, span in enumerate(stashed):
            escaped = escaped.replace(
                f"⟦LTR_{i}⟧",
                f'<span dir="ltr">{html.escape(span, quote=False)}</span>',
            )
        return escaped.replace("\n", "<br/>")

    @classmethod
    def render_paragraph(cls, para: str) -> str:
        """Render one paragraph to an XHTML fragment (strict RTL)."""
        stripped = para.strip()
        if not stripped:
            return ""
        head = re.match(r"^(#{1,6})\s+(.+)$", stripped.split("\n")[0])
        if head and "\n" not in stripped:
            level = min(len(head.group(1)) + 1, 4)
            return f"<h{level}>{html.escape(head.group(2).strip(), quote=False)}</h{level}>"

        masked, table = mask_verbatim_spans(stripped)
        escaped_table = {tok: ("__RAW__", orig) for tok, orig in table.items()}

        out: List[str] = []
        for chunk in re.split(r"(⟦VERBATIM_\d+⟧)", masked):
            raw = escaped_table.get(chunk)
            if raw is None:
                out.append(cls._escape_prose(chunk))
                continue
            _tag, original = raw
            if original.startswith("```"):
                lines = original.split("\n")
                body = "\n".join(lines[1:])
                if body.endswith("```"):
                    body = body[: -len("```")]
                out.append(
                    f'<pre dir="ltr"><code>{html.escape(body.strip(chr(10)), quote=False)}</code></pre>'
                )
            elif original.startswith("`"):
                out.append(
                    f'<code dir="ltr">{html.escape(original[1:-1], quote=False)}</code>'
                )
            elif original.startswith("http") or "@" in original:
                safe = html.escape(original, quote=True)
                out.append(
                    f'<a dir="ltr" href="{safe}">{html.escape(original, quote=False)}</a>'
                )
            else:  # math
                out.append(
                    f'<span dir="ltr" class="math">{html.escape(original, quote=False)}</span>'
                )
        return f"<p>{''.join(out)}</p>"

    def _render_chapter_doc(
        self, filename: str, title: str, chapter: List[str], language: str
    ) -> str:
        body = "\n    ".join(
            frag for para in chapter if (frag := self.render_paragraph(para))
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{language}" lang="{language}" dir="rtl">
<head>
  <title>{html.escape(title, quote=False)}</title>
  <link rel="stylesheet" type="text/css" href="styles/book.css"/>
</head>
<body dir="rtl">
  <section>
    <h2>{html.escape(title, quote=False)}</h2>
    {body}
  </section>
</body>
</html>
"""

    # ------------------------------------------------------------------
    # Package documents
    # ------------------------------------------------------------------

    def _build_opf(
        self,
        title: str,
        author: Optional[str],
        language: str,
        identifier: str,
        chapter_files: List[str],
    ) -> str:
        creator = (
            f"\n    <dc:creator>{html.escape(author.strip(), quote=False)}</dc:creator>"
            if author and author.strip()
            else ""
        )
        manifest_items = "\n".join(
            f'    <item id="ch{n}" href="{fname}" media-type="application/xhtml+xml"/>'
            for n, fname in enumerate(chapter_files, start=1)
        )
        spine_items = "\n".join(
            f'    <itemref idref="ch{n}"/>' for n in range(1, len(chapter_files) + 1)
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0" unique-identifier="book-id" xmlns="http://www.idpf.org/2007/opf" xml:lang="{language}" dir="rtl">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:tarjoman:{html.escape(identifier, quote=True)}</dc:identifier>
    <dc:title dir="rtl">{html.escape(title, quote=False)}</dc:title>{creator}
    <dc:language>{html.escape(language, quote=True)}</dc:language>
    <meta property="dcterms:modified">2026-09-23T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="toc.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css" href="styles/book.css" media-type="text/css"/>
{manifest_items}
  </manifest>
  <spine>
{spine_items}
  </spine>
</package>
"""

    def _build_nav(self, title: str, chapters: List[tuple]) -> str:
        items = "\n".join(
            f'      <li><a href="{fname}">{html.escape(ctitle, quote=False)}</a></li>'
            for fname, ctitle in chapters
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="fa" lang="fa" dir="rtl">
<head>
  <title>{html.escape(title, quote=False)} — فهرست</title>
</head>
<body dir="rtl">
  <nav epub:type="toc">
    <h1>فهرست</h1>
    <ol>
{items}
    </ol>
  </nav>
</body>
</html>
"""

    def _package_epub(
        self,
        chapter_docs: List[tuple],
        opf: str,
        nav: str,
    ) -> bytes:
        import io

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            # mimetype MUST be the first entry and stored uncompressed.
            zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            zf.writestr("META-INF/container.xml", CONTAINER_XML, compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("OEBPS/toc.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("OEBPS/styles/book.css", BOOK_CSS, compress_type=zipfile.ZIP_DEFLATED)
            for n, (fname, title, chapter) in enumerate(chapter_docs, start=1):
                doc = self._render_chapter_doc(fname, title, chapter, "fa")
                zf.writestr(f"OEBPS/{fname}", doc, compress_type=zipfile.ZIP_DEFLATED)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Introspection (used by tests & tooling)
    # ------------------------------------------------------------------

    @staticmethod
    def inspect_epub(epub_bytes: bytes) -> Dict[str, Any]:
        """Parse EPUB bytes and return structural info (mimetype, files, RTL flags)."""
        import io

        info: Dict[str, Any] = {"files": [], "mimetype_ok": False, "rtl_ok": False, "opf_ok": False}
        with zipfile.ZipFile(io.BytesIO(epub_bytes)) as zf:
            info["files"] = zf.namelist()
            try:
                info["mimetype_ok"] = zf.read("mimetype").decode("ascii").strip() == "application/epub+zip"
            except Exception:
                info["mimetype_ok"] = False
            try:
                toc = zf.read("OEBPS/toc.xhtml").decode("utf-8")
                info["rtl_ok"] = 'dir="rtl"' in toc and 'xml:lang="fa"' in toc
            except Exception:
                info["rtl_ok"] = False
            try:
                opf = zf.read("OEBPS/content.opf").decode("utf-8")
                info["opf_ok"] = "<manifest" in opf and "<spine" in opf and "<metadata" in opf
            except Exception:
                info["opf_ok"] = False
        return info
