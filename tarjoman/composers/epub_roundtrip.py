"""EPUB3 roundtrip composer: translated nodes -> valid RTL EPUB3 bytes."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Callable, Dict, Optional, Union

from bs4 import BeautifulSoup

from tarjoman.parsers.epub_parser import NODE_ATTR, ParsedEpub, TextNode

RTL_STYLE = (
    "@font-face { font-family: 'Vazirmatn'; src: local('Vazirmatn'), "
    "local('Vazirmatn-Regular'); } body { font-family: 'Vazirmatn', "
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
    "direction: rtl; text-align: right; }"
)


class EpubRoundtripComposer:
    """Rebuild a valid EPUB3 archive from a parsed book with translated nodes."""

    def compose(
        self,
        parsed_epub: ParsedEpub,
        translations: Optional[Dict[str, str]] = None,
        node_translator: Optional[Callable[[TextNode], str]] = None,
        output_path: Optional[Union[str, Path]] = None,
    ) -> bytes:
        translations = translations or {}
        updated: Dict[str, bytes] = {}
        for chapter in parsed_epub.chapters:
            soup = chapter.soup
            for tag_name in ("html", "body"):
                tag = soup.find(tag_name)
                if tag is not None:
                    tag["dir"] = "rtl"
                    tag["lang"] = "fa"
                    tag["xml:lang"] = "fa"
            head = soup.find("head")
            if head is not None and "Vazirmatn" not in head.decode_contents():
                style = soup.new_tag("style")
                style.string = RTL_STYLE
                head.append(style)
            by_id = {n.id: n for n in chapter.text_nodes}
            elements = soup.find_all(attrs={NODE_ATTR: True})
            if len(elements) < len(chapter.text_nodes):
                # Fallback: DOM order when the marker attribute is missing.
                from tarjoman.parsers.epub_parser import BLOCK_TAGS

                elements = list(soup.find_all(BLOCK_TAGS))[: len(chapter.text_nodes)]
                pairs = list(zip(chapter.text_nodes, elements))
            else:
                lookup = {e[NODE_ATTR]: e for e in elements}
                pairs = [(by_id[nid], lookup[nid]) for nid in by_id if nid in lookup]
            for node, el in pairs:
                try:
                    new_html: Optional[str] = (
                        translations[node.id]
                        if node.id in translations
                        else (node_translator(node) if node_translator else None)
                    )
                except Exception:
                    new_html = None
                if not new_html or not new_html.strip():
                    new_html = node.html_content  # fallback: preserve source
                el.clear()
                frag = BeautifulSoup(new_html, "html.parser")
                container = frag.body if frag.body else frag
                for child in list(container.contents):
                    el.append(child.extract())
            updated[chapter.href] = str(soup).encode("utf-8")

        opf_text = parsed_epub.raw_files[parsed_epub.opf_path].decode("utf-8")
        opf_text = re.sub(
            r"<dc:language>.*?</dc:language>", "<dc:language>fa</dc:language>", opf_text
        )
        if "page-progression-direction" in opf_text:
            opf_text = re.sub(
                r'page-progression-direction="[^"]*"',
                'page-progression-direction="rtl"',
                opf_text,
            )
        else:
            opf_text = opf_text.replace("<spine", '<spine page-progression-direction="rtl"', 1)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            for name, blob in parsed_epub.raw_files.items():
                if name == "mimetype":
                    continue
                if name in updated:
                    zf.writestr(name, updated[name], compress_type=zipfile.ZIP_DEFLATED)
                elif name == parsed_epub.opf_path:
                    zf.writestr(name, opf_text.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
                else:
                    zf.writestr(name, blob, compress_type=zipfile.ZIP_DEFLATED)
        result = buf.getvalue()
        if output_path is not None:
            Path(output_path).write_bytes(result)
        return result
