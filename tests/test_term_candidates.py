"""Terminology candidates: recurring names and terms, without sentence-opener noise."""
from click.testing import CliRunner

from tarjoman.cli import cli
from tarjoman.parsers.term_candidates import candidates_to_tsv, extract_candidates

TEXT = """The Queen rode north. Alice followed the Queen. "Stop," said Alice.
Then the White Rabbit ran past. The White Rabbit looked at her watch.
Alice saw the Cheshire Cat. Ten people waited. Ten more came.
"""


def test_recurring_names_are_found_and_openers_ignored():
    terms = {c.term: c.count for c in extract_candidates(TEXT, min_count=2)}
    assert terms.get("Alice") == 3
    assert terms.get("Queen") == 2
    assert terms.get("White Rabbit") == 2
    assert "The" not in terms and "Then" not in terms
    assert "Ten" not in terms  # only ever sentence-initial


def test_known_terms_are_skipped_case_insensitively():
    terms = [c.term for c in extract_candidates(TEXT, min_count=2, known=["alice"])]
    assert "Alice" not in terms
    assert "Queen" in terms


def test_min_count_and_order():
    found = extract_candidates(TEXT, min_count=2)
    assert found[0].term == "Alice"
    assert all(c.count >= 2 for c in found)


def test_tsv_has_header_and_examples():
    tsv = candidates_to_tsv(extract_candidates(TEXT, min_count=2))
    assert tsv.startswith("english_term\tcount\texample\n")
    assert "Alice\t3\t" in tsv


def test_cli_candidates_writes_file(tmp_path):
    src = tmp_path / "book.txt"
    src.write_text(TEXT, encoding="utf-8")
    out = tmp_path / "candidates.tsv"
    res = CliRunner().invoke(cli, ["book", "candidates", str(src), "--min-count", "2", "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert "Alice" in out.read_text(encoding="utf-8")
