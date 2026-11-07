"""
Subtitle (SRT) parsing and checks for a translated subtitle file.

A subtitle translation can read well and still be broken on screen: a cue
merged into its neighbour shifts every later line out of sync, a three-line
cue covers the picture, and a long line flashes by too fast to read.
``check_srt`` compares the translated file with the source and reports:

- cues: different cue count, or a cue whose timing changed.
- lines: a cue with more than ``max_lines`` lines.
- length: a line longer than ``max_chars`` characters.
- speed: reading speed above ``max_cps`` characters per second.
- untranslated: a cue identical to the source text (Latin letters only).
- residue: chatbot or markdown residue in a cue («ترجمه:»، "Here is the
  translation", code fences, bullets, bold).
- empty: a cue whose source has text but whose translation is empty.

The ideas of short screen-friendly lines, strict one-to-one cue order and
cleaning model preambles out of each line come from SubFarsiPro
(https://github.com/rootrager/subfarsipro); the code here is original.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
_TAG_RE = re.compile(r"<[^>]+>|\{\\[^}]*\}")
_RESIDUE_RE = re.compile(
    r"^\s*(?:ترجمه|فارسی|translation|persian|farsi)\s*:|here(?:'s| is) (?:the|your) translation|"
    r"^\s*(?:sure|of course)[,!]|بفرمایید[،,]? (?:این|اینم) (?:هم )?ترجمه|```|^\s*[-*•]\s|\*\*",
    re.IGNORECASE | re.MULTILINE,
)

#: Netflix's Persian style guide uses 42 characters per line; 2 lines max.
DEFAULT_MAX_CHARS = 42
DEFAULT_MAX_LINES = 2
#: Characters per second; adult programmes commonly cap at 17.
DEFAULT_MAX_CPS = 17.0


@dataclass
class Cue:
    index: str
    start_ms: int
    end_ms: int
    lines: List[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def duration_s(self) -> float:
        return max(0.001, (self.end_ms - self.start_ms) / 1000.0)


@dataclass
class SrtFinding:
    category: str
    cue: str
    message: str


def _ms(h: str, m: str, s: str, ms: str) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms.ljust(3, "0"))


def parse_srt(text: str) -> List[Cue]:
    """Parse SRT text into cues. Tolerates a BOM, CRLF and missing indices."""
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    cues: List[Cue] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        time_at: Optional[int] = next((i for i, ln in enumerate(lines) if _TIME_RE.search(ln)), None)
        if time_at is None:
            continue
        m = _TIME_RE.search(lines[time_at])
        index = lines[time_at - 1].strip() if time_at > 0 else str(len(cues) + 1)
        cues.append(
            Cue(
                index=index,
                start_ms=_ms(*m.groups()[:4]),
                end_ms=_ms(*m.groups()[4:]),
                lines=[ln.strip() for ln in lines[time_at + 1 :] if ln.strip()],
            )
        )
    return cues


def _visible(line: str) -> str:
    return _TAG_RE.sub("", line).replace("‌", "").replace("‏", "").replace("‎", "")


def check_cue(
    cue: Cue,
    source: Optional[Cue] = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_lines: int = DEFAULT_MAX_LINES,
    max_cps: float = DEFAULT_MAX_CPS,
) -> List[SrtFinding]:
    out: List[SrtFinding] = []
    if source is not None and source.lines and not cue.lines:
        out.append(SrtFinding("empty", cue.index, "Translation is empty but the source cue has text."))
        return out
    if len(cue.lines) > max_lines:
        out.append(SrtFinding("lines", cue.index, f"{len(cue.lines)} lines (max {max_lines})."))
    for line in cue.lines:
        n = len(_visible(line))
        if n > max_chars:
            out.append(SrtFinding("length", cue.index, f"{n} chars (max {max_chars}): «{line[:50]}»"))
    chars = sum(len(_visible(ln)) for ln in cue.lines)
    cps = chars / cue.duration_s
    if cue.lines and cps > max_cps:
        out.append(
            SrtFinding(
                "speed",
                cue.index,
                f"{cps:.1f} chars/sec over {cue.duration_s:.2f}s (max {max_cps:g}). Shorten the line.",
            )
        )
    if _RESIDUE_RE.search(cue.text):
        out.append(SrtFinding("residue", cue.index, f"Chatbot/markdown residue: «{cue.text[:50]}»"))
    if (
        source is not None
        and re.search(r"[A-Za-z]{3,}", source.text)
        and _visible(source.text).strip().casefold() == _visible(cue.text).strip().casefold()
    ):
        out.append(SrtFinding("untranslated", cue.index, f"Same as the source: «{cue.text[:50]}»"))
    return out


def check_srt(
    source_text: Optional[str],
    target_text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_lines: int = DEFAULT_MAX_LINES,
    max_cps: float = DEFAULT_MAX_CPS,
) -> List[SrtFinding]:
    """Check a translated SRT, optionally against its source SRT."""
    target = parse_srt(target_text)
    source = parse_srt(source_text) if source_text is not None else None
    findings: List[SrtFinding] = []
    if source is not None:
        if len(source) != len(target):
            findings.append(
                SrtFinding(
                    "cues",
                    "-",
                    f"Source has {len(source)} cues, translation has {len(target)}. "
                    "Cues must map one to one; a merged or split cue desyncs every later line.",
                )
            )
        for s, t in zip(source, target):
            if (s.start_ms, s.end_ms) != (t.start_ms, t.end_ms):
                findings.append(SrtFinding("cues", t.index, "Timing differs from the source cue."))
                break  # one report is enough: everything after is likely shifted
    for i, cue in enumerate(target):
        src = source[i] if source is not None and i < len(source) else None
        findings.extend(check_cue(cue, src, max_chars, max_lines, max_cps))
    return findings
