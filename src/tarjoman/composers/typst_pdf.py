"""
Typst PDF Publication Composer.
Generates RTL Persian Typst source code with Vazirmatn typography,
LaTeX-to-Typst math conversion, and multi-style layout (book, paper).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, List, Optional, Union

from tarjoman.composers.base import BaseComposer


class TypstPdfComposer(BaseComposer):
    """
    Composes publication-grade Typst source code for Persian books and academic papers.
    Includes automated math conversion and PDF compilation.
    """

    DEFAULT_FONT = "Vazirmatn"

    # Known mathematical operator and symbol mappings from LaTeX to Typst
    MATH_SYMBOL_MAP = {
        r"\times": "times",
        r"\cdot": "dot",
        r"\approx": "approx",
        r"\neq": "!=",
        r"\leq": "<=",
        r"\le": "<=",
        r"\geq": ">=",
        r"\ge": ">=",
        r"\infty": "infinity",
        r"\pm": "plus.minus",
        r"\mp": "minus.plus",
        r"\to": "->",
        r"\rightarrow": "->",
        r"\leftarrow": "<-",
        r"\Rightarrow": "=>",
        r"\Leftarrow": "<=",
        r"\Leftrightarrow": "<=>",
        r"\partial": "diff",
        r"\nabla": "nabla",
        r"\in": "in",
        r"\notin": "not in",
        r"\subset": "subset",
        r"\cup": "union",
        r"\cap": "sect",
        r"\forall": "forall",
        r"\exists": "exists",
        r"\sum": "sum",
        r"\int": "integral",
        r"\prod": "product",
    }

    def compose(
        self,
        text: Union[str, List[str]],
        title: Optional[str] = None,
        author: Optional[str] = None,
        style: str = "book",
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """
        Generate Typst source document from Persian text.

        Args:
            text: Persian text (str) or pre-split list of paragraphs.
            title: Optional document title.
            author: Optional author or translator attribution.
            style: Layout style: 'book' (A5) or 'paper' (A4).

        Returns:
            Formatted Typst source code string.
        """
        if isinstance(text, str):
            paragraphs = self.split_paragraphs(text)
        else:
            paragraphs = [p.strip() for p in text if p.strip()]

        lines: List[str] = []

        # 1. Page layout configuration
        style_clean = (style or "book").lower().strip()
        if style_clean == "paper":
            lines.append('#set page(paper: "a4", margin: (x: 2.5cm, y: 2.5cm), numbering: "1")')
        else:
            # Default: 'book' A5 format
            lines.append('#set page(paper: "a5", margin: (x: 1.8cm, top: 2.2cm, bottom: 2.2cm), numbering: "1")')

        # 2. Typography & RTL configuration
        lines.append(f'#set text(font: "{self.DEFAULT_FONT}", lang: "fa", dir: rtl, size: 11pt)')
        lines.append('#set par(justify: true, leading: 0.85em, first-line-indent: 1.5em)\n')

        # 3. Document metadata & Title Header
        if title:
            clean_title = title.strip()
            if style_clean == "paper":
                lines.append(f'= {clean_title}')
                if author:
                    lines.append(f'#align(center)[#text(size: 11pt, fill: rgb("#4b5563"))[{author.strip()}]]')
                lines.append("")
            else:
                lines.append(f'= {clean_title}\n')

        # 4. Process and format paragraphs with math conversion
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_lines = para.split("\n")
            processed_lines = []
            for line in para_lines:
                stripped_line = line.strip()
                heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped_line)
                if heading_match:
                    level = len(heading_match.group(1))
                    heading_text = heading_match.group(2)
                    typst_heading = "=" * level + " " + self.convert_latex_math(self._wrap_bare_latex_symbols(heading_text))
                    processed_lines.append(typst_heading)
                else:
                    processed_lines.append(self.convert_latex_math(self._wrap_bare_latex_symbols(line)))

            lines.append("\n".join(processed_lines))
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    @classmethod
    def convert_latex_math(cls, text: str) -> str:
        """
        Convert LaTeX math expressions to Typst-safe math representations.
        Handles inline $...$, display $$...$$, \\[...\\], and bare LaTeX expressions.

        Args:
            text: Input text containing LaTeX formulas or bare symbols.

        Returns:
            Text with converted Typst math syntax.
        """
        if not text:
            return ""

        # Case 1: Bare LaTeX expression without any math delimiters
        if "$" not in text and "\\" in text:
            return cls._convert_math_expression(text)

        # Case 2: Display math: $$...$$ or \[...\]
        def _rep_display(m: re.Match) -> str:
            inner = cls._convert_math_expression(m.group(1))
            return f"$ {inner} $"

        text = re.sub(r"\$\$(.+?)\$\$", _rep_display, text, flags=re.DOTALL)
        text = re.sub(r"\\\[(.+?)\\\]", _rep_display, text, flags=re.DOTALL)

        # Case 3: Inline math: $...$ or \(...\)
        def _rep_inline(m: re.Match) -> str:
            inner = cls._convert_math_expression(m.group(1))
            return f"${inner}$"

        text = re.sub(r"(?<!\\)\$(.+?)(?<!\\)\$", _rep_inline, text)
        text = re.sub(r"\\\((.+?)\\\)", _rep_inline, text)

        return text

    @classmethod
    def latex_to_typst_math(cls, text: str) -> str:
        """Alias for convert_latex_math."""
        return cls.convert_latex_math(text)

    @classmethod
    def _convert_math_expression(cls, expr: str) -> str:
        """Translate individual math expression from LaTeX to Typst syntax."""
        # Remove LaTeX \left and \right delimiters (Typst handles sizing automatically)
        expr = re.sub(r"\\left\s*([(\[{|.])", r"\1", expr)
        expr = re.sub(r"\\right\s*([)\]}|.])", r"\1", expr)
        expr = re.sub(r"\\(?:left|right)\b", "", expr)

        # Roots: \sqrt[n]{x} -> root(n, x), \sqrt{x} -> sqrt(x)
        expr = re.sub(r"\\sqrt\[([^{}]+)\]\{([^{}]+)\}", r"root(\1, \2)", expr)
        expr = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", expr)

        # Text and font commands inside math
        expr = re.sub(r"\\(?:text|mathrm|operatorname)\{([^{}]+)\}", r'"\1"', expr)
        expr = re.sub(r"\\mathbf\{([^{}]+)\}", r"bold(\1)", expr)
        expr = re.sub(r"\\mathit\{([^{}]+)\}", r"italic(\1)", expr)
        expr = re.sub(r'(?<!")\bsoftmax\b(?!")', '"softmax"', expr)

        # Subscripts and superscripts grouping: _{...} -> _(...)
        expr = re.sub(r"_\{([^{}]+)\}", r"_(\1)", expr)
        expr = re.sub(r"\^\{([^{}]+)\}", r"^(\1)", expr)

        # Fractions: \frac{a}{b} -> (a) / (b)
        while r"\frac" in expr:
            new_expr = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1) / (\2)", expr)
            if new_expr == expr:
                break
            expr = new_expr

        # Common operators and relation symbols
        for latex_sym, typst_sym in cls.MATH_SYMBOL_MAP.items():
            expr = expr.replace(latex_sym, typst_sym)

        # Strip remaining backslashes for Greek letters & math functions (\sigma -> sigma, \alpha -> alpha)
        expr = re.sub(r"\\([a-zA-Z]+)", r"\1", expr)

        # Normalize spaces around comparison and arithmetic operators safely
        expr = re.sub(r"\s*(<=|>=|!=|==|->|<-|=>)\s*", r" \1 ", expr)
        expr = re.sub(r"(?<![<>!=])=(?![=>])", " = ", expr)
        expr = re.sub(r"(?<!-)\+(?![\+])", " + ", expr)
        expr = re.sub(r"(?<![<-])-(?![->])", " - ", expr)

        # Convert adjacent single-letter variable products (e.g. mc^2 -> m c^2, E=mc^2 -> E = m c^2)
        # Typst treats adjacent letters without spaces as undefined multi-character identifiers
        reserved_two_letter = {"pi", "mu", "nu", "xi", "oo", "in", "ln", "lg"}

        def _split_vars(m: re.Match) -> str:
            word = m.group(0)
            if word.lower() in reserved_two_letter:
                return word
            return f"{word[0]} {word[1]}"

        expr = re.sub(r"\b[a-zA-Z]{2}\b", _split_vars, expr)
        expr = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", expr)
        expr = re.sub(r" +", " ", expr)

        return expr.strip()

    @staticmethod
    def _wrap_bare_latex_symbols(text: str) -> str:
        """
        Wrap bare LaTeX Greek letters or math symbols outside $ delimiters in $...$
        so Typst treats them as math rather than literal Latin prose words.
        """
        # Match backslash followed by Greek letters or math words not inside existing $ delimiters
        pattern = r"(?<![\$\\\w])\\(alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega|Delta|Gamma|Theta|Lambda|Xi|Pi|Sigma|Phi|Psi|Omega)(?![\$\w])"
        return re.sub(pattern, r"$\\\1$", text)

    def compile_pdf(self, typ_content: str, output_pdf_path: str) -> bool:
        """
        Compile Typst source text into a PDF document.
        Attempts Python `typst` library first, then falls back to `typst compile` CLI.

        Args:
            typ_content: Typst source code content.
            output_pdf_path: Destination file path for generated PDF.

        Returns:
            True if compilation succeeded and PDF was written, False otherwise.
        """
        out_dir = os.path.dirname(output_pdf_path)
        if out_dir and not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception:
                return False

        tmp_file_path = None
        try:
            # Write Typst code to temporary file
            with tempfile.NamedTemporaryFile(suffix=".typ", mode="w", encoding="utf-8", delete=False) as tf:
                tf.write(typ_content)
                tmp_file_path = tf.name

            # 1. Try Python `typst` package (compile to bytes and write via Python for Unicode path safety)
            try:
                import typst
                pdf_bytes = typst.compile(tmp_file_path)
                if pdf_bytes and len(pdf_bytes) > 0:
                    with open(output_pdf_path, "wb") as out_f:
                        out_f.write(pdf_bytes)
                    return True
            except Exception:
                pass

            # 2. Try CLI `typst compile`
            typst_cli = shutil.which("typst")
            if typst_cli:
                try:
                    proc = subprocess.run(
                        [typst_cli, "compile", tmp_file_path, output_pdf_path],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if proc.returncode == 0 and os.path.exists(output_pdf_path) and os.path.getsize(output_pdf_path) > 0:
                        return True
                except Exception:
                    pass

            return False
        finally:
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.remove(tmp_file_path)
                except Exception:
                    pass
