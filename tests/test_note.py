"""The reviewer note: each blocking claim next to the closest source passage."""

from __future__ import annotations

import json

from groundcheck import cli
from groundcheck.checker import check
from groundcheck.signals import closest_passage

REPORT = (
    "Revenue rose to $3.1 million in the third quarter. "
    "Operating costs were flat. The board approved a new office lease."
)


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_closest_passage_is_the_source_sentence_sharing_most_words():
    assert closest_passage("Third quarter revenue reached $4 million.", ["x.", REPORT]) == (
        1, "Revenue rose to $3.1 million in the third quarter.")


def test_no_shared_words_means_no_passage():
    assert closest_passage("Profit margins expanded to 47%.", [REPORT]) is None


def test_findings_carry_the_closest_passage():
    [finding] = check("Third quarter revenue reached $4 million.", [REPORT]).findings
    assert finding.closest_source == 0
    assert finding.closest_passage.startswith("Revenue rose to $3.1 million")
    assert finding.to_dict()["closest_passage"] == finding.closest_passage


def test_note_puts_the_claim_over_the_closest_passage_without_a_score(tmp_path):
    src = write(tmp_path, "report.txt", REPORT)
    ans = write(tmp_path, "answer.txt", "Third quarter revenue reached $4 million.")
    note = tmp_path / "note.md"
    rc = cli.main(["--answer", ans, "--source", src, "--fail-on", "high", "--note", str(note)])
    text = note.read_text()
    assert rc == cli.EXIT_UNGROUNDED
    assert "> Third quarter revenue reached $4 million." in text
    assert "> Revenue rose to $3.1 million in the third quarter." in text
    assert "/100" not in text


def test_note_says_so_when_the_sources_have_nothing_close(tmp_path):
    data = write(tmp_path, "in.json", json.dumps(
        {"answer": "Profit margins expanded to 47%.", "sources": [REPORT]}))
    note = tmp_path / "note.md"
    cli.main(["--json-input", data, "--fail-on", "high", "--note", str(note)])
    assert "No sentence in the sources shares its wording." in note.read_text()


def test_note_lists_only_findings_at_the_fail_on_level(tmp_path):
    data = write(tmp_path, "in.json", json.dumps({
        "answer": "The board approved a new office lease [2].",
        "sources": [REPORT, "Unrelated text about weather patterns."]}))
    note = tmp_path / "note.md"
    assert cli.main(["--json-input", data, "--fail-on", "high", "--note", str(note)]) == 0
    assert note.read_text().startswith("### groundcheck: nothing blocking")


def test_note_appends_so_a_ci_job_summary_keeps_earlier_steps(tmp_path):
    note = tmp_path / "summary.md"
    note.write_text("earlier step\n")
    data = write(tmp_path, "in.json",
                 json.dumps({"answer": "Margins hit 47%.", "sources": [REPORT]}))
    cli.main(["--json-input", data, "--note", str(note)])
    assert note.read_text().startswith("earlier step\n")
