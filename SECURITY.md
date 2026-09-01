# Security Policy

## Reporting a vulnerability

Email **henrry.220267@gmail.com** with `SECURITY` in the subject line, or open a
[private security advisory](../../security/advisories/new).

Please don't open a public issue for anything exploitable.

Include what you have: the affected file, what an attacker gets out of it, and
a way to reproduce if you have one. A rough report beats a polished one that
never gets sent.

I'll acknowledge within 72 hours and tell you whether I think it's a real issue
and roughly when it'll be fixed.

## Supported versions

The latest release on `main`. This is a small project — there are no backported
security branches.

## Scope

Findings that count:

- A determinism break — the same answer and sources producing a different
  report across runs. Determinism is the property that lets this gate CI, so
  losing it is the serious defect.
- Catastrophic mis-grounding: a fabricated number reported as supported, which
  defeats the tool's highest-value check.
- Any code path that makes a network call or executes input. groundcheck is
  pure and offline by design.

Findings that don't:

- Ordinary false positives or false negatives from the lexical heuristic. It is
  documented as a heuristic, not an oracle; tune `--threshold` or open a normal
  issue.
- Requests to support semantic (embedding/NLI) matching — that is a feature
  direction, not a defect.
