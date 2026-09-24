"""EPUB roundtrip parser: zip -> chapters -> text nodes with inline HTML."""
from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Union

from bs4 import BeautifulSoup

#: Block elements whose inner HTML becomes a translatable text node.
BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li", "dt", "dd")

#: Marker attribute linking a DOM element back to its TextNode id.
NODE_ATTR = "data-tarjoman-node-id"


@dataclass
class TextNode:
    id: str
    chapter_id: str
    html_content: str
    tag_name: str
    attributes: dict = field(default_factory=dict)


@dataclass
class EpubChapter:
    id: str
    href: str  # archive path, e.g. OEBPS/ch1.xhtml
    title: str
    soup: BeautifulSoup
    text_nodes: List[TextNode] = field(default_factory=list)


@dataclass
class ParsedEpub:
    metadata: dict
    chapters: List[EpubChapter]
    opf_path: str
    raw_files: Dict[str, bytes]


class EpubParser:
    """Parse an EPUB archive into chapters with inline-tag-preserving text nodes."""

    def parse(self, epub_input: Union[str, Path, bytes]) -> ParsedEpub:
        if isinstance(epub_input, bytes):
            data = epub_input
        else:
            data = Path(epub_input).read_bytes()
        zf = zipfile.ZipFile(BytesIO(data))
        raw_files: Dict[str, bytes] = {n: zf.read(n) for n in zf.namelist()}

        container = ET.fromstring(raw_files["META-INF/container.xml"])
        rootfile = next(e for e in container.iter() if e.tag.endswith("rootfile"))
        opf_path: str = rootfile.attrib["full-path"]
        opf_dir = posixpath.dirname(opf_path)

        opf = ET.fromstring(raw_files[opf_path])
        ns = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}

        def _text(tag: str) -> str:
            el = opf.find(f"opf:metadata/dc:{tag}", ns)
            return (el.text or "").strip() if el is not None and el.text else ""

        metadata = {
            "title": _text("title"),
            "language": _text("language"),
            "creator": _text("creator"),
        }
        manifest = {
            i.attrib["id"]: (i.attrib.get("href", ""), i.attrib.get("media-type", ""))
            for i in opf.findall("opf:manifest/opf:item", ns)
        }
        spine_refs = [
            i.attrib["idref"] for i in opf.findall("opf:spine/opf:itemref", ns) if "idref" in i.attrib
        ]

        chapters: List[EpubChapter] = []
        for idx, idref in enumerate(spine_refs):
            href, media_type = manifest.get(idref, ("", ""))
            if "html" not in media_type and "xhtml" not in media_type:
                continue
            arch_href = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
            content = raw_files[arch_href].decode("utf-8")
            soup = BeautifulSoup(content, "html.parser")
            chapter_id = idref or f"chapter_{idx}"
            title_el = soup.find("title")
            title = title_el.get_text(strip=True) if title_el else chapter_id
            chapter = EpubChapter(id=chapter_id, href=arch_href, title=title, soup=soup)
            for i, el in enumerate(soup.find_all(BLOCK_TAGS)):
                if not el.get_text(strip=True):
                    continue
                node_id = f"{chapter_id}_node_{i}"
                attrs = {k: v for k, v in el.attrs.items()}
                el[NODE_ATTR] = node_id
                chapter.text_nodes.append(
                    TextNode(
                        id=node_id,
                        chapter_id=chapter_id,
                        html_content=el.decode_contents(),
                        tag_name=el.name,
                        attributes=attrs,
                    )
                )
            chapters.append(chapter)
        return ParsedEpub(metadata=metadata, chapters=chapters, opf_path=opf_path, raw_files=raw_files)
