"""Text primitives — number extraction is the highest-stakes piece."""

from __future__ import annotations

from groundcheck.text import (
    content_tokens,
    extract_numbers,
    has_negation,
    split_sentences,
)


def values(text):
    return [(n.value, n.is_percent) for n in extract_numbers(text)]


def test_extracts_percent_currency_and_magnitude():
    assert values("Revenue grew 47% to $4.2M.") == [(47.0, True), (4_200_000.0, False)]


def test_thousands_separator():
    assert values("A population of 1,234,567.") == [(1_234_567.0, False)]


def test_million_word_suffix():
    assert values("3.5 million users.") == [(3_500_000.0, False)]


def test_ignores_numbers_glued_to_letters():
    # Q3, H1, GPT-4, v2 are labels, not statistics.
    assert values("In Q3 the GPT-4 model shipped v2.") == []


def test_percent_does_not_match_bare_number():
    pct = extract_numbers("47%")[0]
    bare = extract_numbers("47")[0]
    assert not pct.matches(bare)


def test_magnitude_matches_expanded():
    assert extract_numbers("4.2M")[0].matches(extract_numbers("4200000")[0])


def test_sentence_split_respects_abbreviations():
    assert split_sentences("Dr. Smith rose. It grew! Ok?") == [
        "Dr. Smith rose.", "It grew!", "Ok?"]


def test_content_tokens_drop_stopwords():
    assert "the" not in content_tokens("the revenue of the company")
    assert "revenue" in content_tokens("the revenue of the company")


def test_negation_detected():
    assert has_negation("the drug did not reduce mortality")
    assert not has_negation("the drug reduced mortality")
