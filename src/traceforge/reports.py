"""Rich terminal, JSON, and self-contained HTML report rendering."""

from __future__ import annotations

import json
from html import escape as html_escape
from pathlib import Path

from rich.console import Console
from rich.markup import escape as rich_escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from traceforge.models import AnalysisResult


def _format_cost(value: float) -> str:
    return f"${value:,.8f}".rstrip("0").rstrip(".")


def _cost_label(result: AnalysisResult) -> str:
    if result.cost_model_name is None:
        return "not configured"
    return _format_cost(result.cost_usd)


def render_terminal(result: AnalysisResult, console: Console) -> None:
    """Render an analysis result as compact Rich tables."""

    title = Text("TraceForge", style="bold cyan")
    title.append("  agent trace intelligence", style="dim")
    console.print(Panel(title, border_style="cyan", padding=(0, 1)))

    metrics = Table(show_header=False, box=None, pad_edge=False)
    metrics.add_column(style="dim")
    metrics.add_column(style="bold")
    metrics.add_column(style="dim")
    metrics.add_column(style="bold")
    metrics.add_row("Traces", str(len(result.traces)), "Spans", str(result.span_count))
    metrics.add_row(
        "Tool calls",
        str(result.tool_calls),
        "Tool errors",
        str(result.tool_error_count),
    )
    metrics.add_row(
        "Tokens",
        f"{result.input_tokens:,} in / {result.output_tokens:,} out",
        "Estimated cost",
        _cost_label(result),
    )
    metrics.add_row(
        "Retry loops",
        str(result.retry_loop_count),
        "Source",
        rich_escape(result.source),
    )
    console.print(metrics)

    traces = Table(title="Trace overview", header_style="bold cyan")
    traces.add_column("Trace", no_wrap=True)
    traces.add_column("Latency", justify="right")
    traces.add_column("Critical path", justify="right")
    traces.add_column("Tools", justify="right")
    traces.add_column("Errors", justify="right")
    traces.add_column("Tokens", justify="right")
    traces.add_column("Cost", justify="right")
    for trace in result.traces:
        cost = _format_cost(trace.cost_usd) if result.cost_model_name else "—"
        traces.add_row(
            f"{rich_escape(trace.trace_id[:12])}…",
            f"{trace.duration_ms:,.1f} ms",
            f"{trace.critical_path.duration_ms:,.1f} ms",
            str(trace.tool_calls),
            str(len(trace.tool_errors)),
            f"{trace.input_tokens + trace.output_tokens:,}",
            cost,
        )
    console.print(traces)

    for trace in result.traces:
        path = " → ".join(rich_escape(name) for name in trace.critical_path.span_names) or "n/a"
        trace_label = rich_escape(trace.trace_id[:12])
        console.print(f"[bold]Critical path[/bold] [dim]{trace_label}…[/dim]  {path}")
        for error in trace.tool_errors:
            message = f": {error.message}" if error.message else ""
            console.print(
                f"  [red]✗ {rich_escape(error.tool_name)}[/red] "
                f"[dim]({rich_escape(error.error_type)}, {error.duration_ms:.1f} ms)"
                f"{rich_escape(message)}[/dim]"
            )
        for loop in trace.retry_loops:
            state = "recovered" if loop.recovered else "failed"
            console.print(
                f"  [yellow]↻ {rich_escape(loop.signature)}[/yellow] {loop.attempts} attempts, "
                f"{loop.wasted_ms:.1f} ms before final attempt [dim]({state})[/dim]"
            )


def render_json(result: AnalysisResult, *, pretty: bool = True) -> str:
    """Serialize an analysis result to stable JSON."""

    return json.dumps(
        result.to_dict(),
        indent=2 if pretty else None,
        ensure_ascii=False,
        sort_keys=False,
    )


def _trace_sections(result: AnalysisResult) -> str:
    sections: list[str] = []
    for trace in result.traces:
        model_rows = "".join(
            "<tr>"
            f"<td>{html_escape(usage.model)}</td>"
            f"<td>{usage.calls}</td>"
            f"<td>{usage.input_tokens:,}</td>"
            f"<td>{usage.output_tokens:,}</td>"
            f"<td>{_format_cost(usage.cost_usd) if usage.priced else 'unpriced'}</td>"
            "</tr>"
            for usage in trace.model_usage
        )
        if not model_rows:
            model_rows = (
                '<tr><td colspan="5" class="empty">No model usage attributes found.</td></tr>'
            )
        error_rows = "".join(
            "<tr>"
            f"<td>{html_escape(error.tool_name)}</td>"
            f"<td><code>{html_escape(error.error_type)}</code></td>"
            f"<td>{html_escape(error.message or 'No message')}</td>"
            f"<td>{error.duration_ms:.1f} ms</td>"
            "</tr>"
            for error in trace.tool_errors
        )
        if not error_rows:
            error_rows = '<tr><td colspan="4" class="ok">No failed tool calls.</td></tr>'
        retry_rows = "".join(
            "<tr>"
            f"<td><code>{html_escape(loop.signature)}</code></td>"
            f"<td>{loop.attempts}</td>"
            f"<td>{loop.wasted_ms:.1f} ms</td>"
            f"<td>{'Recovered' if loop.recovered else 'Failed'}</td>"
            "</tr>"
            for loop in trace.retry_loops
        )
        if not retry_rows:
            retry_rows = '<tr><td colspan="4" class="ok">No retry loops inferred.</td></tr>'
        path = "".join(
            f'<span class="path-node">{index + 1}. {html_escape(name)}</span>'
            for index, name in enumerate(trace.critical_path.span_names)
        )
        sections.append(
            f"""
            <section class="trace">
              <div class="trace-head">
                <div>
                  <p class="eyebrow">TRACE</p>
                  <h2>{html_escape(trace.trace_id)}</h2>
                </div>
                <div class="latency">{trace.duration_ms:,.1f}<small> ms total</small></div>
              </div>
              <div class="path">
                <div><strong>Critical path</strong>
                  <span class="muted">{trace.critical_path.duration_ms:,.1f} ms causal work</span>
                </div>
                <div class="path-flow">{path or '<span class="muted">Unavailable</span>'}</div>
              </div>
              <h3>Model usage</h3>
              <table><thead><tr><th>Model</th><th>Calls</th><th>Input</th>
                <th>Output</th><th>Estimated cost</th></tr></thead>
                <tbody>{model_rows}</tbody></table>
              <h3>Tool failures</h3>
              <table><thead><tr><th>Tool</th><th>Error</th><th>Message</th>
                <th>Latency</th></tr></thead><tbody>{error_rows}</tbody></table>
              <h3>Retry loops</h3>
              <table><thead><tr><th>Signature</th><th>Attempts</th><th>Wasted</th>
                <th>Outcome</th></tr></thead><tbody>{retry_rows}</tbody></table>
            </section>
            """
        )
    return "\n".join(sections)


def render_html(result: AnalysisResult) -> str:
    """Render a zero-dependency, self-contained HTML report."""

    priced_cost = _cost_label(result)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="generator" content="TraceForge">
  <title>TraceForge report</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg:#080b12;--card:#101521;--card2:#151c2b;--line:#283249;
      --text:#e8eefc;--muted:#94a3bd;--cyan:#49d9ff;--mint:#6fffc1;
      --amber:#ffd166;--red:#ff6b81;
    }}
    * {{ box-sizing:border-box }}
    body {{
      margin:0;background:
        radial-gradient(circle at 10% -10%,#16375a 0,transparent 32rem),
        radial-gradient(circle at 100% 0,#153c35 0,transparent 28rem),var(--bg);
      color:var(--text);font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;
    }}
    main {{ width:min(1180px,calc(100% - 32px));margin:auto;padding:56px 0 80px }}
    header {{ display:flex;align-items:end;justify-content:space-between;gap:24px;
      margin-bottom:30px }}
    h1 {{ font-size:clamp(34px,7vw,68px);letter-spacing:-.05em;line-height:.9;margin:8px 0 }}
    h1 span {{ color:var(--cyan) }} h2 {{ font-size:18px;word-break:break-all;margin:3px 0 }}
    h3 {{ margin:28px 0 10px }} p {{ margin:0 }} .eyebrow {{
      color:var(--mint);font-size:11px;font-weight:800;letter-spacing:.18em
    }}
    .muted,small {{ color:var(--muted);font-weight:400 }}
    .stamp {{ color:var(--muted);text-align:right }}
    .cards {{ display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:28px }}
    .card {{ background:linear-gradient(145deg,var(--card2),var(--card));
      border:1px solid var(--line);
      border-radius:14px;padding:18px;min-height:104px }}
    .card b {{ display:block;font-size:26px;letter-spacing:-.04em;margin-top:12px }}
    .card span {{ color:var(--muted);font-size:12px }}
    .trace {{ background:rgba(16,21,33,.94);border:1px solid var(--line);
      border-radius:18px;padding:26px;margin-top:18px;box-shadow:0 24px 70px #0005 }}
    .trace-head {{ display:flex;justify-content:space-between;gap:20px;align-items:start }}
    .latency {{ color:var(--cyan);font-size:28px;font-weight:800;white-space:nowrap }}
    .path {{ background:#0b101a;border:1px solid var(--line);border-radius:12px;
      padding:16px;margin-top:18px }}
    .path-flow {{ display:flex;flex-wrap:wrap;gap:7px;margin-top:12px }}
    .path-node {{ border:1px solid #2f5260;background:#102632;color:#c9f5ff;
      border-radius:999px;padding:5px 10px;font-size:12px }}
    table {{ width:100%;border-collapse:collapse;display:table;overflow:auto }}
    th,td {{ border-bottom:1px solid var(--line);text-align:left;padding:10px 8px;
      vertical-align:top }}
    th {{ color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em }}
    code {{ color:var(--amber);font-family:ui-monospace,SFMono-Regular,monospace }}
    .ok {{ color:var(--mint) }} .empty {{ color:var(--muted) }}
    footer {{ color:var(--muted);margin-top:28px;font-size:12px }}
    @media(max-width:900px) {{ .cards {{ grid-template-columns:repeat(3,1fr) }} }}
    @media(max-width:560px) {{ header {{ display:block }}
      .stamp {{ text-align:left;margin-top:18px }}
      .cards {{ grid-template-columns:repeat(2,1fr) }} .trace {{ padding:18px }}
      table {{ display:block }} }}
    @media print {{ body {{ background:#fff;color:#111 }} .trace,.card {{ box-shadow:none }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div><p class="eyebrow">LOCAL-FIRST AGENT OBSERVABILITY</p>
      <h1>Trace<span>Forge</span></h1>
      <p class="muted">OpenTelemetry performance, reliability &amp; cost intelligence.</p>
    </div>
    <div class="stamp">Generated {html_escape(result.generated_at)}<br>
      {html_escape(result.source)}</div>
  </header>
  <div class="cards">
    <div class="card"><span>Traces</span><b>{len(result.traces)}</b></div>
    <div class="card"><span>Spans</span><b>{result.span_count}</b></div>
    <div class="card"><span>Total tokens</span>
      <b>{result.input_tokens + result.output_tokens:,}</b></div>
    <div class="card"><span>Tool calls</span><b>{result.tool_calls}</b></div>
    <div class="card"><span>Tool errors</span><b>{result.tool_error_count}</b></div>
    <div class="card"><span>Estimated cost</span><b>{html_escape(priced_cost)}</b></div>
  </div>
  {_trace_sections(result)}
  <footer>Generated locally by TraceForge. Inputs and report data never leave this machine.</footer>
</main>
</body>
</html>
"""


def write_json(result: AnalysisResult, path: Path, *, pretty: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json(result, pretty=pretty) + "\n", encoding="utf-8")


def write_html(result: AnalysisResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(result), encoding="utf-8")
