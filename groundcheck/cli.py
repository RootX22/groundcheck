"""Command-line interface.

Two input shapes, because groundcheck sits in two places:

  * ad hoc:  --answer answer.txt --source a.txt --source b.txt
  * pipeline: a JSON file/stdin {"answer": "...", "sources": ["...", "..."]},
    which is what a RAG service emits and what a CI step feeds in.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .checker import DEFAULT_SUPPORT_THRESHOLD, check
from .model import Report, Severity

EXIT_OK = 0            # score at or above --fail-under and no blocking findings
EXIT_UNGROUNDED = 1    # below threshold, or a finding at/above --fail-on
EXIT_USAGE = 2

_COLOURS = {
    Severity.HIGH: "\033[31m",
    Severity.MEDIUM: "\033[33m",
    Severity.LOW: "\033[36m",
    Severity.INFO: "\033[2m",
}
_RESET = "\033[0m"


def _use_colour(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path) as fh:
        return fh.read()


def _load_inputs(args) -> tuple[str, list[str]]:
    """Resolve the answer and sources from either the flag or the JSON form."""
    if args.json_input is not None:
        raw = _read(args.json_input)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON input: {exc}") from exc
        answer = data.get("answer")
        sources = data.get("sources")
        if not isinstance(answer, str) or not isinstance(sources, list):
            raise ValueError('JSON must have a string "answer" and a list "sources"')
        return answer, [str(s) for s in sources]

    if not args.answer:
        raise ValueError("provide --answer FILE (with --source), or --json-input")
    answer = _read(args.answer)
    sources = [_read(s) for s in (args.source or [])]
    return answer, sources


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="groundcheck",
        description="A deterministic groundedness linter for RAG/LLM answers. "
                    "Flags fabricated numbers, unsupported claims, and broken "
                    "citations. A heuristic, not a truth oracle.",
        epilog="Exit codes: 0 grounded, 1 below threshold or blocking finding, 2 usage.",
    )
    p.add_argument("--answer", metavar="FILE", help="the answer text ('-' for stdin)")
    p.add_argument("--source", action="append", metavar="FILE",
                   help="a source document (repeatable)")
    p.add_argument("--json-input", metavar="FILE",
                   help='JSON {"answer":..., "sources":[...]} (\'-\' for stdin)')
    p.add_argument("--json", action="store_true", help="emit the report as JSON")
    p.add_argument("--threshold", type=float, default=DEFAULT_SUPPORT_THRESHOLD,
                   metavar="F",
                   help="overlap below which a claim is unsupported (0..1, "
                        f"default {DEFAULT_SUPPORT_THRESHOLD})")
    p.add_argument("--fail-under", type=int, default=None, metavar="SCORE",
                   help="exit non-zero if the grounding score is below this (0..100)")
    p.add_argument("--fail-on", default="never",
                   choices=["low", "medium", "high", "never"],
                   help="exit non-zero on a finding at/above this severity")
    p.add_argument("-V", "--version", action="version",
                   version=f"groundcheck {__version__}")
    return p


def _render_text(report: Report, stream) -> None:
    colour = _use_colour(stream)

    def paint(sev, text):
        return f"{_COLOURS[sev]}{text}{_RESET}" if colour else text

    bar_score = report.score
    print(f"\n  groundcheck — grounding score {bar_score}/100", file=stream)
    print(f"  {report.supported_claims}/{report.total_claims} claim(s) supported",
          file=stream)
    print(file=stream)

    if not report.findings:
        print("  no grounding problems found", file=stream)
        return

    for f in report.findings:
        tag = paint(f.severity, f"[{f.severity.label.upper():^6}]")
        print(f"  {tag} {f.kind}", file=stream)
        if f.claim:
            print(f"          claim: “{f.claim}”", file=stream)
        print(f"          {f.detail}", file=stream)
        if f.evidence:
            print(f"          {f.evidence}", file=stream)
        print(file=stream)

    counts: dict[str, int] = {}
    for f in report.findings:
        counts[f.severity.label] = counts.get(f.severity.label, 0) + 1
    summary = "  ".join(f"{n} {s}" for s, n in counts.items())
    print(f"  {len(report.findings)} finding(s): {summary}", file=stream)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not (0.0 <= args.threshold <= 1.0):
        print("groundcheck: --threshold must be between 0 and 1", file=sys.stderr)
        return EXIT_USAGE

    try:
        answer, sources = _load_inputs(args)
    except (ValueError, OSError) as exc:
        print(f"groundcheck: {exc}", file=sys.stderr)
        return EXIT_USAGE

    report = check(answer, sources, support_threshold=args.threshold)

    if args.json:
        json.dump(report.to_dict(), sys.stdout, indent=2)
        print()
    else:
        _render_text(report, sys.stdout)

    exit_code = EXIT_OK
    if args.fail_under is not None and report.score < args.fail_under:
        exit_code = EXIT_UNGROUNDED
    if args.fail_on != "never":
        threshold = Severity[args.fail_on.upper()]
        if any(f.severity >= threshold for f in report.findings):
            exit_code = EXIT_UNGROUNDED
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
