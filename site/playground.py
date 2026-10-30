"""Bridge between the browser page and groundcheck, run inside Pyodide.

Sources arrive as a JSON list so the page never builds Python objects itself,
and the report goes back as the same dictionary the CLI prints with --json.
"""

from __future__ import annotations

import json

from groundcheck import check


def analyse(answer: str, sources_json: str, threshold: float) -> str:
    sources = [source for source in json.loads(sources_json) if source.strip()]
    return json.dumps(check(answer, sources, support_threshold=threshold).to_dict())
