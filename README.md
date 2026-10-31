# groundcheck

[![CI](https://github.com/RootX22/groundcheck/actions/workflows/ci.yml/badge.svg)](https://github.com/RootX22/groundcheck/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-0e75b6.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![Dependencies: none](https://img.shields.io/badge/runtime%20deps-none-5ee1a0)

A **deterministic groundedness linter** for RAG and LLM answers. It reads an
answer and the sources it was supposed to be based on, and flags the claims that
aren't actually supported — above all, **fabricated numbers**.

**[Try it in your browser](https://rootx22.github.io/groundcheck/)**: paste an
answer and its sources and see what it flags. It runs groundcheck itself through
Pyodide, so nothing you paste leaves the page and no model is called. The same
page is on [Hugging Face Spaces](https://huggingface.co/spaces/Root-2c/groundcheck).

```console
$ groundcheck --answer answer.txt --source q3-report.txt --fail-on high

  groundcheck — grounding score 33/100
  1/3 claim(s) supported

  [ HIGH ] fabricated-number
          claim: "Profit margins expanded to 47%."
          The figure '47%' does not appear in any source. Invented
          statistics are the highest-risk hallucination.
          '47%' not found in 1 source(s)

  [MEDIUM] unsupported-claim
          claim: "The company opened three new offices in Europe."
          This statement is not backed by any source (best overlap 12%).

$ echo $?
1
```

## The problem

RAG answers look grounded and often aren't. A model given a financial report
will happily write "margins expanded to 47%" when the report never mentions
margins at all. Invented statistics are the highest-stakes hallucination —
they're specific, quotable, and wrong — and they're the ones a human skimming
the answer is least likely to catch.

The usual fix is an **LLM-as-judge**: ask a second model whether the answer is
grounded. It's slow, it costs a call per check, and — the disqualifying part —
it's **non-deterministic**. You cannot gate a CI pipeline on a check that
returns a different score each run.

groundcheck takes the opposite approach. Every signal is **transparent and
deterministic**: a number is either in the sources or it isn't, a claim's words
either overlap a source or they don't. The same input always yields the same
verdict, so it fits where an LLM judge can't — as a **lint gate in CI**, run on
every answer, with a stable exit code.

It is a **heuristic, not a truth oracle** — the same way a spell-checker flags
suspicious words without understanding the sentence. It catches the fabrications
and misattributions that matter, and it says plainly where it's guessing.

## What it catches

| Finding | Severity | What it means |
|---|---|---|
| `fabricated-number` | high | A figure in the answer (`47%`, `$4.2M`, `1,200`) appears in **no** source. Percentages only match percentages, so a claimed `45%` is never satisfied by a bare `45`. |
| `unsupported-claim` | medium | A sentence whose content barely overlaps any source. |
| `broken-citation` | medium/low | A `[2]` that points at a source which doesn't support the sentence — a misattribution. |
| `contradiction` | low | The answer closely matches a source but flips its negation ("did **not** reduce" → "reduced"). |
| `no-sources` | high | Nothing was provided to ground against. |

A **grounding score** (0–100) is the percentage of checkable claims that are
supported. Connective sentences ("This is important.") carry no claim and don't
count.

## Install

```bash
pip install git+https://github.com/RootX22/groundcheck.git
```

Or run from a clone — **no runtime dependencies**, standard library only:

```bash
git clone https://github.com/RootX22/groundcheck.git
python3 -m groundcheck --json-input response.json
```

## Usage

Two input shapes, because groundcheck sits in two places.

**Ad hoc**, from files:

```bash
groundcheck --answer answer.txt --source doc1.txt --source doc2.txt
```

**In a pipeline** — the JSON your RAG service already produces:

```bash
echo '{"answer": "...", "sources": ["...", "..."]}' | groundcheck --json-input -
```

| Flag | Meaning |
|---|---|
| `--answer FILE` / `--source FILE` | The answer and each source (`--source` repeatable) |
| `--json-input FILE` | `{"answer": ..., "sources": [...]}` (`-` for stdin) |
| `--json` | Emit the full report as JSON |
| `--threshold F` | Overlap below which a claim is unsupported (0–1, default 0.5) |
| `--fail-under N` | Exit non-zero if the grounding score is below N |
| `--fail-on LEVEL` | Exit non-zero on a finding at/above `low`/`medium`/`high` |

**Exit codes:** `0` grounded, `1` below threshold or a blocking finding, `2`
usage. With neither `--fail-under` nor `--fail-on`, it only reports (exit 0).

## In CI

Gate a RAG regression suite on groundedness:

```yaml
- name: Check answer grounding
  run: |
    pip install git+https://github.com/RootX22/groundcheck.git
    for case in fixtures/*.json; do
      groundcheck --json-input "$case" --fail-on high --fail-under 70
    done
```

Any answer that invents a statistic (`--fail-on high`) or drops below 70%
grounded fails the build.

## As a library

```python
from groundcheck import check

report = check(answer_text, [source1, source2])
print(report.score)                       # 0..100
for f in report.findings:
    print(f.severity.label, f.kind, f.claim)
```

`check()` is pure and deterministic — no I/O, no network, no model. Given the
same strings it returns the same report, which is what makes it testable and
CI-safe.

## How the number check works

The load-bearing signal. Every number is extracted and normalised so that
comparisons are meaningful across formats:

- `4.2M`, `4.2 million`, and `4200000` compare equal
- `47%` compares equal only to `47%`, never to a bare `47`
- digits glued to letters (`Q3`, `GPT-4`, `v2`) are treated as labels, not
  statistics, and ignored

A claim's number is a fabrication only if it matches **no** number in **any**
source. And a matched figure works in the other direction too: a terse claim
like "Revenue reached $3.1M" whose figure is present in a source is treated as
grounded even when its wording overlap is modest — a matched statistic is
stronger evidence than shared words.

## Limitations

Stated plainly, because a groundedness tool that overclaims is self-refuting:

- **Lexical, not semantic.** It matches words and numbers, not meaning. A claim
  paraphrased with entirely different vocabulary can read as unsupported; a
  wrong claim built from the source's own words can read as supported. It is a
  first-pass filter, not a fact-checker.
- **English-tuned** stopwords and tokenisation.
- **Negation is shallow** — it catches simple polarity flips, not scope,
  quantifiers, or double negatives, so `contradiction` is low-confidence by
  design.
- It tells you what to **look at**, not what is true. Every finding is a prompt
  to verify, and the number checks are the ones you can most often trust
  outright.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

## Licence

MIT
