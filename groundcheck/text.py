"""Text primitives: sentence splitting, content-word tokenising, and — the part
that carries the most weight — number extraction and normalisation.

Everything here is deterministic and dependency-free. That is the whole premise
of the tool: the same answer and sources always produce the same verdict, so it
can gate a CI pipeline the way a linter does, rather than a probabilistic
LLM-as-judge that gives a different score each run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A compact English stopword list. Kept deliberately small — only true function
# words — so that content words which carry meaning ("revenue", "increased")
# survive to be matched. Over-aggressive stopword lists strip the very words
# that distinguish a supported claim from an unsupported one.
STOPWORDS = frozenset("""
a an the this that these those and or but nor so yet for as of at by to from in
on with without into onto upon is are was were be been being am do does did done
has have had having will would shall should can could may might must it its it's
they them their there here he she his her we us our you your i me my mine
which who whom whose what when where why how than then also very just too not no
if else while about over under again further once each any all both few more most
other some such only own same s t can't don't
""".split())

# Negation cues, used to catch "source says X is NOT true, answer says it is".
NEGATIONS = frozenset("""
not no never none cannot can't won't doesn't don't didn't isn't aren't wasn't
weren't without neither nor fails failed unable lacks lacking excludes excluding
""".split())

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

# Sentence splitter: break on . ! ? followed by whitespace, but not inside a
# decimal number or a common abbreviation. Good enough for prose answers; a
# perfect segmenter is not needed because scoring is per-claim-fuzzy anyway.
_ABBREV = {"mr", "mrs", "ms", "dr", "prof", "inc", "ltd", "co", "vs", "etc",
           "e.g", "i.e", "fig", "no", "st", "jan", "feb", "mar", "apr", "jun",
           "jul", "aug", "sep", "oct", "nov", "dec"}
_SENT_END = re.compile(r"([.!?])\s+")

# Numbers, including currency, percentages, thousands separators, decimals, and
# magnitude suffixes (k, m, bn). This regex is intentionally broad: a fabricated
# statistic is the highest-stakes hallucination, so we would rather examine a
# borderline token than miss "$4.2M".
_NUMBER = re.compile(
    r"""
    (?<![A-Za-z])                           # not glued to a letter: skip Q3, H1, v2
    (?<![A-Za-z]-)                          # not a model/version name: GPT-4, llama-2
    (?P<currency>[$£€])?\s*
    (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?   # 1,234 or 1,234.5
          | \d+\.\d+                        # 3.14
          | \d+)                            # 42
    \s*(?P<suffix>%|percent|k|m|bn|b|mm|thousand|million|billion|trillion)?
    (?![A-Za-z])                            # and not glued to a trailing letter
    """,
    re.IGNORECASE | re.VERBOSE,
)

_MAGNITUDE = {
    "k": 1_000, "thousand": 1_000,
    "m": 1_000_000, "mm": 1_000_000, "million": 1_000_000,
    "b": 1_000_000_000, "bn": 1_000_000_000, "billion": 1_000_000_000,
    "trillion": 1_000_000_000_000,
}


@dataclass(frozen=True)
class Number:
    """A number found in text, normalised to a comparable value.

    `value` folds in the magnitude suffix (so "4.2M" -> 4200000.0) and marks
    percentages, so "47%" in the answer only matches "47%" in a source, never a
    bare "47". Conflating those is exactly how a fabricated-percentage check
    would produce false negatives.
    """

    raw: str
    value: float
    is_percent: bool

    def matches(self, other: Number, *, rel_tol: float = 0.001) -> bool:
        if self.is_percent != other.is_percent:
            return False
        if self.value == other.value:
            return True
        scale = max(abs(self.value), abs(other.value), 1.0)
        return abs(self.value - other.value) / scale <= rel_tol


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    # Protect abbreviations by temporarily masking their trailing dot.
    protected = text
    for ab in _ABBREV:
        protected = re.sub(rf"\b({re.escape(ab)})\.", r"\1\0", protected, flags=re.IGNORECASE)

    pieces = _SENT_END.sub(r"\1\n", protected).split("\n")
    out = []
    for p in pieces:
        s = p.replace("\0", ".").strip()
        if s:
            out.append(s)
    return out


def content_tokens(text: str) -> list[str]:
    """Lowercased content words, stopwords removed. The unit of overlap scoring."""
    return [w for w in (m.group(0).lower() for m in _WORD.finditer(text))
            if w not in STOPWORDS and len(w) > 1]


def all_tokens(text: str) -> list[str]:
    """Every word lowercased, stopwords kept — used for negation detection."""
    return [m.group(0).lower() for m in _WORD.finditer(text)]


def extract_numbers(text: str) -> list[Number]:
    numbers = []
    for m in _NUMBER.finditer(text):
        raw_num = m.group("num").replace(",", "")
        try:
            value = float(raw_num)
        except ValueError:
            continue
        suffix = (m.group("suffix") or "").lower()
        is_percent = suffix in ("%", "percent")
        if suffix in _MAGNITUDE:
            value *= _MAGNITUDE[suffix]
        numbers.append(Number(raw=m.group(0).strip(), value=value,
                              is_percent=is_percent))
    return numbers


def has_negation(text: str) -> bool:
    return bool(NEGATIONS & set(all_tokens(text)))
