"""Compose the signals into a per-claim grounding report.

The orchestration also parses inline citations like `[1]` or `[2, 3]`, because
one of the most useful checks is not "is this supported by *some* source" but
"is this supported by the source it *cites*" — a broken citation is a specific,
fixable defect that points the reader at the wrong evidence.
"""

from __future__ import annotations

import re

from .model import ClaimResult, Finding, Report, Severity
from .signals import best_overlap, negation_conflict, overlap_score, unsupported_numbers
from .text import content_tokens, extract_numbers, split_sentences

# [1]  [2,3]  [1, 2]  — citation markers pointing at 1-based source indices.
_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

# Below this overlap a claim is considered unsupported by a given source.
DEFAULT_SUPPORT_THRESHOLD = 0.5
# A citation must clear at least this to count as actually backing its sentence.
CITATION_THRESHOLD = 0.35
# Claims shorter than this (in content words) are treated as connective tissue
# ("This is important.") and not scored for support — they carry no checkable
# assertion, and flagging them is noise.
MIN_CONTENT_WORDS = 3


def _parse_citations(sentence: str) -> list[int]:
    idxs = []
    for m in _CITATION.finditer(sentence):
        for part in m.group(1).split(","):
            idxs.append(int(part.strip()))
    return idxs


def check(answer: str, sources: list[str], *,
          support_threshold: float = DEFAULT_SUPPORT_THRESHOLD) -> Report:
    report = Report()
    if not sources:
        # With no sources every factual claim is unsupported by definition;
        # rather than flood the report, say so once.
        report.findings.append(Finding(
            kind="no-sources", severity=Severity.HIGH, claim="",
            detail="No sources were provided, so nothing in the answer can be grounded.",
        ))

    for raw_sentence in split_sentences(answer):
        # Strip citation markers before scoring so "[1]" tokens do not pollute
        # the content overlap.
        cited = _parse_citations(raw_sentence)
        # Remove citation markers, then tidy the whitespace they leave behind so
        # the quoted claim reads cleanly ("47% ." -> "47%.").
        sentence = _CITATION.sub("", raw_sentence)
        sentence = re.sub(r"\s+([.,;:!?])", r"\1", sentence)
        sentence = re.sub(r"\s{2,}", " ", sentence).strip()

        content = content_tokens(sentence)
        claim_numbers = extract_numbers(sentence)
        numbers_missing = unsupported_numbers(sentence, sources) if sources else []

        # A sentence with too little content and no numbers is connective tissue.
        if len(content) < MIN_CONTENT_WORDS and not claim_numbers:
            continue

        best_i, best_s = best_overlap(sentence, sources) if sources else (-1, 0.0)

        # A specific figure that is present in the sources is strong grounding
        # evidence — stronger than generic word overlap. "Revenue was $3.1M" and
        # a source saying "revenue of $3.1 million in the third quarter" share
        # only moderate wording but are unmistakably the same claim. So a claim
        # whose numbers all check out counts as supported at a lower overlap bar,
        # rather than being flagged unsupported on wording alone.
        number_anchored = (
            bool(claim_numbers) and not numbers_missing
            and best_s >= support_threshold * 0.6
        )
        supported = (
            bool(sources) and not numbers_missing
            and (best_s >= support_threshold or number_anchored)
        )

        claim = ClaimResult(text=sentence, supported=supported,
                            best_source=best_i, support_score=best_s)

        # ── fabricated numbers: the headline finding ────────────────────────
        for n in numbers_missing:
            f = Finding(
                kind="fabricated-number", severity=Severity.HIGH, claim=sentence,
                detail=(f"The figure '{n.raw}' does not appear in any source. "
                        "Invented statistics are the highest-risk hallucination."),
                evidence=f"'{n.raw}' not found in {len(sources)} source(s)",
            )
            claim.findings.append(f)
            report.findings.append(f)

        # ── unsupported claim ───────────────────────────────────────────────
        if sources and not supported and not numbers_missing:
            f = Finding(
                kind="unsupported-claim", severity=Severity.MEDIUM, claim=sentence,
                detail=("This statement is not backed by any source "
                        f"(best overlap {best_s:.0%}, threshold "
                        f"{support_threshold:.0%})."),
                evidence=(f"closest: source [{best_i + 1}]" if best_i >= 0
                          else "no overlapping source"),
            )
            claim.findings.append(f)
            report.findings.append(f)

        # ── broken citation: cites a source that does not support it ────────
        for c in cited:
            if not (1 <= c <= len(sources)):
                f = Finding(
                    kind="broken-citation", severity=Severity.MEDIUM, claim=sentence,
                    detail=f"Cites source [{c}], which does not exist "
                           f"({len(sources)} source(s) provided).",
                    evidence=f"[{c}] out of range",
                )
            else:
                cite_score = overlap_score(sentence, sources[c - 1])
                if cite_score >= CITATION_THRESHOLD:
                    continue
                f = Finding(
                    kind="broken-citation", severity=Severity.LOW, claim=sentence,
                    detail=(f"Cites source [{c}] but that source barely supports the "
                            f"statement (overlap {cite_score:.0%}). The citation may "
                            "point at the wrong source."),
                    evidence=f"[{c}] overlap {cite_score:.0%}",
                )
            claim.findings.append(f)
            report.findings.append(f)

        # ── contradiction: same topic, opposite polarity ───────────────────
        if sources and best_i >= 0 and negation_conflict(sentence, sources[best_i]):
            f = Finding(
                kind="contradiction", severity=Severity.LOW, claim=sentence,
                detail=("This closely matches a source but disagrees on negation — "
                        "the source may state the opposite. Verify by hand; this "
                        "is a heuristic and cannot read scope."),
                evidence=f"polarity mismatch with source [{best_i + 1}]",
            )
            claim.findings.append(f)
            report.findings.append(f)

        report.claims.append(claim)

    report.findings.sort(key=lambda f: -int(f.severity))
    return report
