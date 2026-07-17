"""渲染 Rich 终端、JSON 与自包含 HTML 报告。"""

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
        return "未配置"
    return _format_cost(result.cost_usd)


def render_terminal(result: AnalysisResult, console: Console) -> None:
    """以紧凑的 Rich 表格渲染分析结果。"""

    title = Text("TraceForge", style="bold cyan")
    title.append("  Agent 轨迹智能分析", style="dim")
    console.print(Panel(title, border_style="cyan", padding=(0, 1)))

    metrics = Table(show_header=False, box=None, pad_edge=False)
    metrics.add_column(style="dim")
    metrics.add_column(style="bold")
    metrics.add_column(style="dim")
    metrics.add_column(style="bold")
    metrics.add_row("轨迹", str(len(result.traces)), "Span 数", str(result.span_count))
    metrics.add_row(
        "工具调用",
        str(result.tool_calls),
        "工具错误",
        str(result.tool_error_count),
    )
    metrics.add_row(
        "Token",
        f"{result.input_tokens:,} 输入 / {result.output_tokens:,} 输出",
        "估算成本",
        _cost_label(result),
    )
    metrics.add_row(
        "重试循环",
        str(result.retry_loop_count),
        "来源",
        rich_escape(result.source),
    )
    console.print(metrics)

    traces = Table(title="轨迹概览", header_style="bold cyan")
    traces.add_column("轨迹", no_wrap=True)
    traces.add_column("延迟", justify="right")
    traces.add_column("关键路径", justify="right")
    traces.add_column("工具", justify="right")
    traces.add_column("错误", justify="right")
    traces.add_column("Token", justify="right")
    traces.add_column("成本", justify="right")
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
        path = " → ".join(rich_escape(name) for name in trace.critical_path.span_names) or "无"
        trace_label = rich_escape(trace.trace_id[:12])
        console.print(f"[bold]关键路径[/bold] [dim]{trace_label}…[/dim]  {path}")
        for error in trace.tool_errors:
            message = f": {error.message}" if error.message else ""
            console.print(
                f"  [red]✗ {rich_escape(error.tool_name)}[/red] "
                f"[dim]({rich_escape(error.error_type)}, {error.duration_ms:.1f} ms)"
                f"{rich_escape(message)}[/dim]"
            )
        for loop in trace.retry_loops:
            state = "已恢复" if loop.recovered else "失败"
            console.print(
                f"  [yellow]↻ {rich_escape(loop.signature)}[/yellow] 共 {loop.attempts} 次尝试，"
                f"最终尝试前耗时 {loop.wasted_ms:.1f} ms [dim]({state})[/dim]"
            )


def render_json(result: AnalysisResult, *, pretty: bool = True) -> str:
    """将分析结果序列化为稳定 JSON。"""

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
            f"<td>{_format_cost(usage.cost_usd) if usage.priced else '未定价'}</td>"
            "</tr>"
            for usage in trace.model_usage
        )
        if not model_rows:
            model_rows = '<tr><td colspan="5" class="empty">未发现模型用量属性。</td></tr>'
        error_rows = "".join(
            "<tr>"
            f"<td>{html_escape(error.tool_name)}</td>"
            f"<td><code>{html_escape(error.error_type)}</code></td>"
            f"<td>{html_escape(error.message or '无错误消息')}</td>"
            f"<td>{error.duration_ms:.1f} ms</td>"
            "</tr>"
            for error in trace.tool_errors
        )
        if not error_rows:
            error_rows = '<tr><td colspan="4" class="ok">没有失败的工具调用。</td></tr>'
        retry_rows = "".join(
            "<tr>"
            f"<td><code>{html_escape(loop.signature)}</code></td>"
            f"<td>{loop.attempts}</td>"
            f"<td>{loop.wasted_ms:.1f} ms</td>"
            f"<td>{'已恢复' if loop.recovered else '失败'}</td>"
            "</tr>"
            for loop in trace.retry_loops
        )
        if not retry_rows:
            retry_rows = '<tr><td colspan="4" class="ok">未推断出重试循环。</td></tr>'
        path = "".join(
            f'<span class="path-node">{index + 1}. {html_escape(name)}</span>'
            for index, name in enumerate(trace.critical_path.span_names)
        )
        sections.append(
            f"""
            <section class="trace">
              <div class="trace-head">
                <div>
                  <p class="eyebrow">轨迹</p>
                  <h2>{html_escape(trace.trace_id)}</h2>
                </div>
                <div class="latency">{trace.duration_ms:,.1f}<small> ms 总计</small></div>
              </div>
              <div class="path">
                <div><strong>关键路径</strong>
                  <span class="muted">{trace.critical_path.duration_ms:,.1f} ms 因果工作</span>
                </div>
                <div class="path-flow">{path or '<span class="muted">不可用</span>'}</div>
              </div>
              <h3>模型用量</h3>
              <table><thead><tr><th>模型</th><th>调用</th><th>输入</th>
                <th>输出</th><th>估算成本</th></tr></thead>
                <tbody>{model_rows}</tbody></table>
              <h3>工具失败</h3>
              <table><thead><tr><th>工具</th><th>错误</th><th>消息</th>
                <th>延迟</th></tr></thead><tbody>{error_rows}</tbody></table>
              <h3>重试循环</h3>
              <table><thead><tr><th>特征</th><th>尝试次数</th><th>无效耗时</th>
                <th>结果</th></tr></thead><tbody>{retry_rows}</tbody></table>
            </section>
            """
        )
    return "\n".join(sections)


def render_html(result: AnalysisResult) -> str:
    """渲染零依赖、自包含的 HTML 报告。"""

    priced_cost = _cost_label(result)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="generator" content="TraceForge">
  <title>TraceForge 分析报告</title>
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
    <div><p class="eyebrow">本地优先的 AGENT 可观测性</p>
      <h1>Trace<span>Forge</span></h1>
      <p class="muted">OpenTelemetry 性能、可靠性与成本智能分析。</p>
    </div>
    <div class="stamp">生成时间：{html_escape(result.generated_at)}<br>
      {html_escape(result.source)}</div>
  </header>
  <div class="cards">
    <div class="card"><span>轨迹</span><b>{len(result.traces)}</b></div>
    <div class="card"><span>Span 数</span><b>{result.span_count}</b></div>
    <div class="card"><span>Token 总量</span>
      <b>{result.input_tokens + result.output_tokens:,}</b></div>
    <div class="card"><span>工具调用</span><b>{result.tool_calls}</b></div>
    <div class="card"><span>工具错误</span><b>{result.tool_error_count}</b></div>
    <div class="card"><span>估算成本</span><b>{html_escape(priced_cost)}</b></div>
  </div>
  {_trace_sections(result)}
  <footer>由 TraceForge 在本地生成；输入和报告数据始终留在本机。</footer>
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
