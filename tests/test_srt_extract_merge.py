"""Text-only subtitle workflow: extract the dialogue, merge the translation back."""
from click.testing import CliRunner

from tarjoman.cli import cli
from tarjoman.parsers.srt import extract_for_translation, merge_translation, parse_srt

SRC = """1
00:00:01,000 --> 00:00:02,500
Hello there.

2
00:00:03,000 --> 00:00:05,000
How are
you?

3
00:00:06,000 --> 00:00:07,000
Bye.
"""

GOOD = """[#1]
سلام.

[#2]
حالت چطوره؟

[#3]
خداحافظ.
"""


def test_extract_keeps_only_text_with_markers():
    text = extract_for_translation(SRC)
    assert "00:00" not in text
    assert text.index("[#1]") < text.index("[#2]") < text.index("[#3]")
    assert "How are\nyou?" in text


def test_merge_keeps_source_timing_and_indices():
    out = merge_translation(SRC, GOOD)
    cues = parse_srt(out)
    src = parse_srt(SRC)
    assert [(c.index, c.start_ms, c.end_ms) for c in cues] == [(c.index, c.start_ms, c.end_ms) for c in src]
    assert cues[1].lines == ["حالت چطوره؟"]
    assert "00:00:03,000 --> 00:00:05,000" in out


def test_round_trip_of_extract_then_merge_with_same_text_is_stable():
    extracted = extract_for_translation(SRC)
    out = merge_translation(SRC, extracted)
    assert [c.lines for c in parse_srt(out)] == [c.lines for c in parse_srt(SRC)]


def test_merge_refuses_missing_marker():
    bad = GOOD.replace("[#2]\nحالت چطوره؟\n\n", "")
    try:
        merge_translation(SRC, bad)
    except ValueError as exc:
        assert "[#2]" in str(exc)
    else:
        raise AssertionError("merge should refuse a missing marker")


def test_merge_refuses_duplicate_and_out_of_order():
    dup = GOOD + "\n[#1]\nتکراری\n"
    try:
        merge_translation(SRC, dup)
    except ValueError as exc:
        assert "more than once" in str(exc)
    else:
        raise AssertionError("merge should refuse a duplicate marker")
    swapped = "[#2]\nب\n\n[#1]\nالف\n\n[#3]\nج\n"
    try:
        merge_translation(SRC, swapped)
    except ValueError as exc:
        assert "out of order" in str(exc)
    else:
        raise AssertionError("merge should refuse out-of-order markers")


def test_merge_refuses_empty_translation_of_nonempty_cue():
    bad = GOOD.replace("[#3]\nخداحافظ.", "[#3]")
    try:
        merge_translation(SRC, bad)
    except ValueError as exc:
        assert "[#3] is empty" in str(exc)
    else:
        raise AssertionError("merge should refuse an empty translation")


def test_cli_extract_then_merge(tmp_path):
    runner = CliRunner()
    src = tmp_path / "in.srt"
    src.write_text(SRC, encoding="utf-8")
    ext = tmp_path / "text.txt"
    res = runner.invoke(cli, ["srt", "extract", str(src), "-o", str(ext)])
    assert res.exit_code == 0, res.output
    tr = tmp_path / "fa.txt"
    tr.write_text(GOOD, encoding="utf-8")
    out = tmp_path / "fa.srt"
    res = runner.invoke(cli, ["srt", "merge", str(src), str(tr), "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert parse_srt(out.read_text(encoding="utf-8"))[0].lines == ["سلام."]
    bad = tmp_path / "bad.txt"
    bad.write_text("[#1]\nفقط یکی\n", encoding="utf-8")
    res = runner.invoke(cli, ["srt", "merge", str(src), str(bad), "-o", str(out)])
    assert res.exit_code == 1
    assert "Merge refused" in res.output
