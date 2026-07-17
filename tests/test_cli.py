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
    assert "共 2 次尝试" in result.stdout


def test_help_is_chinese_and_keeps_public_commands_and_flags() -> None:
    result = runner.invoke(app, ["analyze", "--help"])
    missing = runner.invoke(app, ["analyze"])

    assert result.exit_code == 0
    assert missing.exit_code == 2
    assert "用法：" in result.stdout
    assert "分析轨迹并输出 Rich 终端摘要" in result.stdout
    assert "显示此帮助信息并退出" in result.stdout
    assert "缺少参数" in missing.stderr
    assert "--format" in result.stdout
    assert "--cost-model" in result.stdout
    assert "--output" in result.stdout


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
