"""Typer command-line interface for TraceForge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.markup import escape as rich_escape

from traceforge import __version__
from traceforge.analyzer import analyze_spans
from traceforge.costs import CostModel, CostModelError
from traceforge.demo import demo_payload
from traceforge.models import AnalysisResult
from traceforge.parser import TraceParseError, load_spans, parse_payload
from traceforge.reports import render_terminal, write_html, write_json

app = typer.Typer(
    name="traceforge",
    help="Turn OpenTelemetry AI-agent traces into performance, reliability, and cost insights.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()
err_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"traceforge {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the installed version and exit.",
        ),
    ] = False,
) -> None:
    """Analyze exported traces without sending telemetry anywhere."""


def _abort(message: str) -> NoReturn:
    err_console.print(f"[bold red]error:[/bold red] {rich_escape(message)}")
    raise typer.Exit(code=2)


def _cost_model(path: Path | None) -> CostModel | None:
    if path is None:
        return None
    try:
        return CostModel.from_path(path)
    except CostModelError as exc:
        _abort(str(exc))


def _analyze_file(source: Path, input_format: str, cost_path: Path | None) -> AnalysisResult:
    try:
        spans = load_spans(source, input_format)
    except TraceParseError as exc:
        _abort(str(exc))
    return analyze_spans(
        spans,
        source=str(source),
        cost_model=_cost_model(cost_path),
    )


@app.command()
def analyze(
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="OTLP JSON or JSONL span file.",
        ),
    ],
    input_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Input format: auto, otlp, json, or jsonl.",
        ),
    ] = "auto",
    cost_model: Annotated[
        Path | None,
        typer.Option(
            "--cost-model",
            exists=True,
            dir_okay=False,
            help="JSON model-pricing configuration.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Also write the full analysis as JSON."),
    ] = None,
    compact: Annotated[
        bool,
        typer.Option("--compact", help="Write compact JSON instead of indented JSON."),
    ] = False,
) -> None:
    """Analyze traces and print a Rich terminal summary."""

    result = _analyze_file(source, input_format, cost_model)
    render_terminal(result, console)
    if output is not None:
        write_json(result, output, pretty=not compact)
        console.print(f"\n[green]JSON written:[/green] {rich_escape(str(output))}")


@app.command()
def report(
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="OTLP JSON or JSONL span file.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Destination HTML report."),
    ] = Path("traceforge-report.html"),
    input_format: Annotated[
        str,
        typer.Option("--format", "-f", help="Input format: auto, otlp, json, or jsonl."),
    ] = "auto",
    cost_model: Annotated[
        Path | None,
        typer.Option(
            "--cost-model",
            exists=True,
            dir_okay=False,
            help="JSON model-pricing configuration.",
        ),
    ] = None,
    json_output: Annotated[
        Path | None,
        typer.Option("--json-output", help="Optionally write the analysis JSON too."),
    ] = None,
) -> None:
    """Create a self-contained HTML report that works offline."""

    result = _analyze_file(source, input_format, cost_model)
    write_html(result, output)
    if json_output is not None:
        write_json(result, json_output)
    console.print(f"[bold green]HTML report written:[/bold green] {rich_escape(str(output))}")


@app.command()
def demo(
    save_trace: Annotated[
        Path | None,
        typer.Option("--save-trace", help="Save the synthetic OTLP JSON input."),
    ] = None,
    html: Annotated[
        Path | None,
        typer.Option("--html", help="Also write a self-contained HTML report."),
    ] = None,
    json_output: Annotated[
        Path | None,
        typer.Option("--json-output", help="Also write analysis JSON."),
    ] = None,
) -> None:
    """Analyze a built-in agent run with a failed-and-retried tool call."""

    payload = demo_payload()
    result = analyze_spans(
        parse_payload(payload),
        source="built-in demo",
        cost_model=CostModel.demo(),
    )
    render_terminal(result, console)
    if save_trace is not None:
        save_trace.parent.mkdir(parents=True, exist_ok=True)
        save_trace.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        console.print(f"\n[green]Demo trace written:[/green] {rich_escape(str(save_trace))}")
    if html is not None:
        write_html(result, html)
        console.print(f"[green]HTML report written:[/green] {rich_escape(str(html))}")
    if json_output is not None:
        write_json(result, json_output)
        console.print(f"[green]JSON written:[/green] {rich_escape(str(json_output))}")
