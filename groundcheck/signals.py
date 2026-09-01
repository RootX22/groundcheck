"""The deterministic support signals.

Each function answers one narrow, testable question about a claim against a
source. The checker composes them; keeping them separate is what makes the whole
thing auditable — you can point at exactly why a claim was flagged, which an
LLM-judge cannot do.
"""

from __future__ import annotations

from .text import Number, content_tokens, extract_numbers, has_negation


def _bigrams(tokens: list[str]) -> set[tuple[str, str]]:
    return set(zip(tokens, tokens[1:]))


def overlap_score(claim: str, source: str) -> float:
    """How well a claim's content is covered by a source, in [0, 1].

    Recall-oriented on purpose: the question is "how much of the CLAIM is found
    in the source", not the symmetric Jaccard. A short claim inside a long
    source should score high, and it would not under a symmetric measure that is
    dragged down by everything else in the source.

    Unigram coverage is blended with a bigram bonus so that word order carries
    some weight — "prices rose" and "rose prices" should not look identical —
    without demanding an exact phrase match.
    """
    claim_tokens = content_tokens(claim)
    if not claim_tokens:
        return 1.0        # nothing contentful to support (e.g. "It did.")

    source_tokens = content_tokens(source)
    source_set = set(source_tokens)
    if not source_set:
        return 0.0

    covered = sum(1 for t in claim_tokens if t in source_set)
    unigram = covered / len(claim_tokens)

    claim_bg = _bigrams(claim_tokens)
    if claim_bg:
        source_bg = _bigrams(source_tokens)
        bigram = len(claim_bg & source_bg) / len(claim_bg)
    else:
        bigram = unigram

    # Weighted toward unigram coverage (the primary signal) with the bigram
    # term rewarding preserved phrasing.
    return round(0.7 * unigram + 0.3 * bigram, 4)


def best_overlap(claim: str, sources: list[str]) -> tuple[int, float]:
    """Index and score of the source that best supports the claim."""
    best_i, best_s = -1, 0.0
    for i, src in enumerate(sources):
        s = overlap_score(claim, src)
        if s > best_s:
            best_i, best_s = i, s
    return best_i, best_s


def unsupported_numbers(claim: str, sources: list[str]) -> list[Number]:
    """Numbers in the claim that appear in no source — likely fabricated.

    This is the highest-value signal. An LLM inventing a statistic is both the
    most damaging hallucination and the easiest to catch deterministically: a
    number is either present in the sources or it is not. Percentages only match
    percentages (see Number.matches), so "47%" is never satisfied by a bare 47.
    """
    claim_numbers = extract_numbers(claim)
    if not claim_numbers:
        return []

    source_numbers: list[Number] = []
    for src in sources:
        source_numbers.extend(extract_numbers(src))

    missing = []
    for cn in claim_numbers:
        if not any(cn.matches(sn) for sn in source_numbers):
            missing.append(cn)
    return missing


def negation_conflict(claim: str, source: str, *, overlap_threshold: float = 0.6) -> bool:
    """True when claim and source are about the same thing but disagree on polarity.

    The pattern this catches: the source says "the drug did NOT reduce
    mortality", the answer says "the drug reduced mortality". High content
    overlap, opposite negation. It is a heuristic — it cannot understand
    double negatives or scope — so it is reported at low confidence, never as a
    hard failure.
    """
    if overlap_score(claim, source) < overlap_threshold:
        return False
    return has_negation(claim) != has_negation(source)
