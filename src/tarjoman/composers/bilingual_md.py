"""
Bilingual Side-by-Side Markdown Composer.
Generates structured comparison tables aligning English and Persian paragraphs.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Union

from tarjoman.composers.base import BaseComposer


class BilingualMarkdownComposer(BaseComposer):
    """
    Composes bilingual comparative Markdown tables for side-by-side review.
    """

    DEFAULT_TITLE = "بررسی تطبیقی دو زبانه (Bilingual Side-by-Side Review)"

    def compose(
        self,
        source_text: Union[str, List[str]],
        target_text: Union[str, List[str]],
        title: Optional[str] = DEFAULT_TITLE,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """
        Produce a clean Markdown table comparing source and target paragraphs.

        Args:
            source_text: Source English text (str) or pre-split list of paragraphs.
            target_text: Target Persian text (str) or pre-split list of paragraphs.
            title: Optional title header. If None or empty, header is omitted.

        Returns:
            Formatted Markdown table string.
        """
        if isinstance(source_text, str):
            src_paras = self.split_paragraphs(source_text)
        else:
            src_paras = [p.strip() for p in source_text if p.strip()]

        if isinstance(target_text, str):
            tgt_paras = self.split_paragraphs(target_text)
        else:
            tgt_paras = [p.strip() for p in target_text if p.strip()]

        lines: List[str] = []
        if title:
            lines.append(f"# {title.strip()}\n")

        lines.append("| متن اصلی انگلیسی | ترجمه فارسی صیقل‌خورده |")
        lines.append("| :--- | :--- |")

        total_rows = max(len(src_paras), len(tgt_paras))
        for i in range(total_rows):
            src_cell = src_paras[i] if i < len(src_paras) else ""
            tgt_cell = tgt_paras[i] if i < len(tgt_paras) else ""

            # Escape pipes and internal newlines for Markdown table integrity
            # ponytail: replace raw newlines with <br> to keep table rows on single lines
            clean_src = self._escape_cell(src_cell)
            clean_tgt = self._escape_cell(tgt_cell)

            lines.append(f"| {clean_src} | {clean_tgt} |")

        return "\n".join(lines)

    @staticmethod
    def _escape_cell(text: str) -> str:
        """Escape Markdown table delimiters and newline breaks."""
        if not text:
            return ""
        # Escape pipe symbols
        escaped = text.replace("|", r"\|")
        # Replace line breaks with HTML break tag
        escaped = re.sub(r"\r?\n+", "<br>", escaped)
        return escaped
