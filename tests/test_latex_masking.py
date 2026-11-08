"""Stage 1 protects LaTeX constructs that must survive translation byte for byte."""
from tarjoman.stages.stage1_pre_analysis import PreAnalysisStage

STAGE = PreAnalysisStage()


def _roundtrip(text):
    masked, tokens = STAGE.mask_text(text)
    return masked, tokens, PreAnalysisStage.restore_tokens(masked, tokens)


def test_equation_environment_is_masked_whole():
    text = "We show that\n\\begin{equation}\n  E = mc^2 \\label{eq:e}\n\\end{equation}\nholds."
    masked, tokens, restored = _roundtrip(text)
    assert "E = mc" not in masked
    assert restored == text
    assert len(tokens) == 1


def test_starred_environment_and_matching_end():
    text = "\\begin{align*} a &= b \\\\ c &= d \\end{align*} and \\begin{equation} x \\end{equation}"
    masked, tokens, restored = _roundtrip(text)
    assert "a &= b" not in masked and " x " not in masked
    assert restored == text


def test_bracket_math_is_masked():
    text = "Inline \\(x+y\\) and display \\[ \\int_0^1 f \\] done."
    masked, tokens, restored = _roundtrip(text)
    assert "int_0" not in masked and "x+y" not in masked
    assert restored == text


def test_citation_and_reference_commands_are_masked():
    text = "As shown in \\cite{smith2020,lee2021} and Fig.~\\ref{fig:one}, see \\citep[p.~4]{lee2021}."
    masked, tokens, restored = _roundtrip(text)
    assert "smith2020" not in masked and "fig:one" not in masked and "lee2021" not in masked
    assert "As shown in" in masked and "see" in masked  # prose stays translatable
    assert restored == text


def test_href_masks_url_but_keeps_link_text_translatable():
    text = "See \\href{https://example.org}{the project page}."
    masked, tokens, restored = _roundtrip(text)
    assert "example.org" not in masked
    assert "the project page" in masked
    assert restored == text


def test_plain_prose_and_currency_are_untouched():
    text = "The price rose to $50 from $40 last year."
    masked, tokens, restored = _roundtrip(text)
    assert tokens == {} and masked == text
