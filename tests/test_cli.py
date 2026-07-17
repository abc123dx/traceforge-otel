from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from traceforge.cli import app
from traceforge.demo import demo_payload

runner = CliRunner()


def test_demo_command_shows_findings() -> None:
    result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0
    assert "TraceForge" in result.stdout
    assert "get_weather" in result.stdout
    assert "2 attempts" in result.stdout


def test_analyze_and_report_commands_write_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "trace.json"
    output_json = tmp_path / "analysis.json"
    output_html = tmp_path / "report.html"
    source.write_text(json.dumps(demo_payload()), encoding="utf-8")

    analyzed = runner.invoke(
        app,
        ["analyze", str(source), "--output", str(output_json)],
    )
    reported = runner.invoke(
        app,
        ["report", str(source), "--output", str(output_html)],
    )

    assert analyzed.exit_code == 0
    assert reported.exit_code == 0
    assert json.loads(output_json.read_text())["summary"]["span_count"] == 6
    assert output_html.read_text().startswith("<!doctype html>")
