"""CLI: input shapes, exit codes, output."""

from __future__ import annotations

import json

from groundcheck import cli

SOURCES_JSON = {
    "answer": "Revenue was $3.1 million. Margins hit 47%.",
    "sources": ["The company reported revenue of $3.1 million in the quarter."],
}


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_json_input_and_fail_on_high(tmp_path, capsys):
    f = write(tmp_path, "in.json", json.dumps(SOURCES_JSON))
    rc = cli.main(["--json-input", f, "--fail-on", "high"])
    assert rc == cli.EXIT_UNGROUNDED          # fabricated 47%
    assert "fabricated-number" in capsys.readouterr().out


def test_fail_under_threshold(tmp_path, capsys):
    f = write(tmp_path, "in.json", json.dumps(SOURCES_JSON))
    # 1 of 2 claims supported -> score 50. --fail-under 80 must trip.
    assert cli.main(["--json-input", f, "--fail-under", "80"]) == cli.EXIT_UNGROUNDED
    assert cli.main(["--json-input", f, "--fail-under", "40"]) == cli.EXIT_OK


def test_answer_and_source_files(tmp_path, capsys):
    a = write(tmp_path, "answer.txt", "Revenue was $3.1 million.")
    s = write(tmp_path, "src.txt", "The company reported revenue of $3.1 million.")
    rc = cli.main(["--answer", a, "--source", s])
    assert rc == cli.EXIT_OK


def test_json_output_is_valid(tmp_path, capsys):
    f = write(tmp_path, "in.json", json.dumps(SOURCES_JSON))
    cli.main(["--json-input", f, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["score"] == 50
    assert any(fi["kind"] == "fabricated-number" for fi in payload["findings"])


def test_missing_inputs_is_usage_error(capsys):
    assert cli.main([]) == cli.EXIT_USAGE


def test_bad_threshold_is_usage_error(capsys):
    assert cli.main(["--answer", "-", "--threshold", "5"]) == cli.EXIT_USAGE


def test_malformed_json_is_usage_error(tmp_path, capsys):
    f = write(tmp_path, "bad.json", "{not json")
    assert cli.main(["--json-input", f]) == cli.EXIT_USAGE
    assert "invalid JSON" in capsys.readouterr().err


def test_text_output_not_coloured_when_piped(tmp_path, capsys):
    f = write(tmp_path, "in.json", json.dumps(SOURCES_JSON))
    cli.main(["--json-input", f])
    assert "\033[" not in capsys.readouterr().out


def test_default_exit_is_zero_without_gates(tmp_path, capsys):
    # Findings exist but no --fail-on/--fail-under: reporting mode, exit 0.
    f = write(tmp_path, "in.json", json.dumps(SOURCES_JSON))
    assert cli.main(["--json-input", f]) == cli.EXIT_OK
