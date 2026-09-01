"""The grounding checker — each finding kind, in both directions."""

from __future__ import annotations

from groundcheck.checker import check
from groundcheck.model import Severity

SOURCES = [
    "The company reported revenue of $3.1 million in the third quarter, "
    "up from $2.8 million a year earlier. Headcount was flat at 45 employees.",
    "Customer satisfaction scores improved during the period and the support "
    "team resolved tickets faster than before.",
]


def kinds(answer, sources=SOURCES, **kw):
    return [f.kind for f in check(answer, sources, **kw).findings]


# ── fabricated numbers: the headline signal ─────────────────────────────────

def test_fabricated_percentage_is_flagged_high():
    r = check("Profit margins expanded to 47%.", SOURCES)
    fab = [f for f in r.findings if f.kind == "fabricated-number"]
    assert fab and fab[0].severity == Severity.HIGH
    assert "47%" in fab[0].evidence


def test_real_number_is_not_flagged():
    # $3.1 million is in source 1.
    assert "fabricated-number" not in kinds("Revenue was $3.1 million.")


def test_percentage_not_satisfied_by_bare_number():
    # Source has "45" (employees) but no "45%"; a claimed 45% is still fabricated.
    assert "fabricated-number" in kinds("Attrition was 45%.")


# ── supported vs unsupported ────────────────────────────────────────────────

def test_grounded_claim_is_supported():
    r = check("The company reported revenue of $3.1 million in the third quarter.",
              SOURCES)
    assert r.supported_claims == r.total_claims
    assert r.score == 100


def test_number_anchor_rescues_a_terse_grounded_claim():
    """A claim with matched figures but only moderate wording overlap must not
    be flagged unsupported — matched numbers are strong grounding evidence."""
    r = check("Revenue reached $3.1 million.", SOURCES)
    assert "unsupported-claim" not in [f.kind for f in r.findings]
    assert r.claims[0].supported


def test_off_topic_claim_is_unsupported():
    r = check("The company opened three new offices in Europe.", SOURCES)
    assert "unsupported-claim" in [f.kind for f in r.findings]
    assert not r.claims[0].supported


def test_connective_sentences_are_ignored():
    # "This is notable." carries no checkable assertion.
    r = check("This is notable.", SOURCES)
    assert r.total_claims == 0
    assert r.score == 100


# ── citations ───────────────────────────────────────────────────────────────

def test_citation_to_wrong_source_is_flagged():
    # Customer-satisfaction content lives in source 2; citing 1 is wrong.
    r = check("Customer satisfaction improved [1].", SOURCES)
    assert "broken-citation" in [f.kind for f in r.findings]


def test_citation_to_correct_source_is_clean():
    r = check("Customer satisfaction scores improved and tickets resolved faster [2].",
              SOURCES)
    assert "broken-citation" not in [f.kind for f in r.findings]


def test_out_of_range_citation_is_flagged():
    r = check("Revenue was $3.1 million [9].", SOURCES)
    broken = [f for f in r.findings if f.kind == "broken-citation"]
    assert broken and "out of range" in broken[0].evidence


# ── contradiction ───────────────────────────────────────────────────────────

def test_negation_contradiction_is_flagged():
    sources = ["The treatment did not reduce mortality in the trial cohort."]
    r = check("The treatment reduced mortality in the trial cohort.", sources)
    assert "contradiction" in [f.kind for f in r.findings]


def test_no_contradiction_when_polarity_agrees():
    sources = ["The treatment did not reduce mortality in the trial cohort."]
    r = check("The treatment did not reduce mortality in the trial cohort.", sources)
    assert "contradiction" not in [f.kind for f in r.findings]


# ── no sources / scoring ────────────────────────────────────────────────────

def test_no_sources_is_reported_once():
    r = check("Anything at all here.", [])
    assert [f.kind for f in r.findings] == ["no-sources"]


def test_score_is_percentage_of_supported_claims():
    answer = ("Revenue was $3.1 million in the third quarter. "     # supported
              "Margins hit 47%. "                                    # fabricated
              "They opened offices in Europe.")                      # unsupported
    r = check(answer, SOURCES)
    assert r.total_claims == 3
    assert r.supported_claims == 1
    assert r.score == 33


def test_findings_sorted_worst_first():
    answer = "They opened offices in Europe. Margins hit 47%."
    r = check(answer, SOURCES)
    sevs = [int(f.severity) for f in r.findings]
    assert sevs == sorted(sevs, reverse=True)


def test_report_json_is_complete():
    r = check("Margins hit 47%.", SOURCES)
    d = r.to_dict()
    assert set(d) >= {"score", "total_claims", "supported_claims",
                      "worst_severity", "findings", "claims"}
    assert d["worst_severity"] == "high"
