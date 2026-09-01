"""Findings, severities, and the report shape."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Severity(IntEnum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass
class Finding:
    """One grounding problem with one claim.

    `kind` is the stable rule id. `claim` is the exact sentence from the answer,
    quoted verbatim so the operator can find it. `evidence` explains what was or
    was not found in the sources — never a guess.
    """

    kind: str
    severity: Severity
    claim: str
    detail: str
    evidence: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "severity": self.severity.label,
            "claim": self.claim,
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass
class ClaimResult:
    text: str
    supported: bool
    best_source: int          # index of the best-matching source, -1 if none
    support_score: float      # 0..1 lexical overlap with the best source
    findings: list[Finding] = field(default_factory=list)


@dataclass
class Report:
    claims: list[ClaimResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def total_claims(self) -> int:
        return len(self.claims)

    @property
    def supported_claims(self) -> int:
        return sum(1 for c in self.claims if c.supported)

    @property
    def score(self) -> int:
        """Groundedness as a 0..100 percentage of claims that are supported.

        A report with no checkable claims scores 100 — there is nothing
        ungrounded, and penalising an answer for being short would be wrong.
        """
        if not self.claims:
            return 100
        return round(self.supported_claims / self.total_claims * 100)

    def worst(self) -> Severity:
        return max((f.severity for f in self.findings), default=Severity.INFO)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "total_claims": self.total_claims,
            "supported_claims": self.supported_claims,
            "worst_severity": self.worst().label,
            "findings": [f.to_dict() for f in self.findings],
            "claims": [
                {"text": c.text, "supported": c.supported,
                 "support_score": round(c.support_score, 3),
                 "best_source": c.best_source}
                for c in self.claims
            ],
        }
