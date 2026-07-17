from __future__ import annotations

import json
from io import StringIO

from rich.console import Console

from traceforge.analyzer import analyze_spans
from traceforge.costs import CostModel
from traceforge.demo import demo_payload
from traceforge.models import AnalysisResult, Span
from traceforge.parser import parse_payload
from traceforge.reports import render_html, render_json, render_terminal


def _result() -> AnalysisResult:
    return analyze_spans(
        parse_payload(demo_payload()),
        source="unit test",
        cost_model=CostModel.demo(),
        generated_at="2026-01-01T00:00:00+00:00",
    )


def test_json_report_has_stable_schema() -> None:
    payload = json.loads(render_json(_result()))

    assert payload["schema_version"] == "1.0"
    assert payload["summary"]["retry_loops"] == 1
    assert payload["traces"][0]["critical_path"]["span_names"]


def test_html_report_is_self_contained() -> None:
    html = render_html(_result())

    assert html.startswith("<!doctype html>")
    assert "TraceForge" in html
    assert "get_weather" in html
    assert "<script src=" not in html
    assert "<link rel=" not in html


def test_terminal_treats_trace_markup_as_literal_text() -> None:
    spans = [
        Span(
            trace_id="[cyan]trace[/cyan]",
            span_id="root",
            parent_span_id=None,
            name="[red]root[/red]",
            start_ns=0,
            end_ns=100_000_000,
        ),
        Span(
            trace_id="[cyan]trace[/cyan]",
            span_id="attempt-1",
            parent_span_id="root",
            name="tool.lookup",
            start_ns=10_000_000,
            end_ns=40_000_000,
            attributes={
                "gen_ai.tool.name": "[bold]lookup[/bold]",
                "error.type": "[yellow]timeout[/yellow]",
            },
            status_code="ERROR",
        ),
        Span(
            trace_id="[cyan]trace[/cyan]",
            span_id="attempt-2",
            parent_span_id="root",
            name="tool.lookup",
            start_ns=45_000_000,
            end_ns=80_000_000,
            attributes={
                "gen_ai.tool.name": "[bold]lookup[/bold]",
                "gen_ai.request.retry_number": 1,
            },
            status_code="OK",
        ),
    ]
    result = analyze_spans(
        spans,
        source="[magenta]trace.json[/magenta]",
        generated_at="fixed",
    )
    stream = StringIO()
    render_terminal(
        result,
        Console(file=stream, color_system=None, force_terminal=False, width=240),
    )
    output = stream.getvalue()

    assert "[magenta]trace.json[/magenta]" in output
    assert "[cyan]trace[" in output
    assert "[red]root[/red]" in output
    assert "[bold]lookup[/bold]" in output
    assert "[yellow]timeout[/yellow]" in output
