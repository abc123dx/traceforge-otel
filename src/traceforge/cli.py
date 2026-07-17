"""TraceForge 的 Typer 命令行界面。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from rich.console import Console
from rich.markup import escape as rich_escape
from typer import rich_utils
from typer.core import TyperCommand, TyperGroup

from traceforge import __version__
from traceforge.analyzer import analyze_spans
from traceforge.costs import CostModel, CostModelError
from traceforge.demo import demo_payload
from traceforge.models import AnalysisResult
from traceforge.parser import TraceParseError, load_spans, parse_payload
from traceforge.reports import render_terminal, write_html, write_json


def _localize_builtin_options(params: list[Any]) -> list[Any]:
    help_by_name = {
        "help": "显示此帮助信息并退出。",
        "install_completion": "为当前 shell 安装自动补全。",
        "show_completion": "显示当前 shell 的自动补全脚本，便于复制或自定义。",
    }
    for param in params:
        name = getattr(param, "name", None)
        localized_help = help_by_name.get(name) if isinstance(name, str) else None
        if localized_help is not None:
            param.help = localized_help
    return params


def _translate_click_message(message: str) -> str:
    replacements = (
        ("Got unexpected extra arguments", "存在意外的额外参数"),
        ("Got unexpected extra argument", "存在意外的额外参数"),
        ("Missing argument", "缺少参数"),
        ("Missing option", "缺少选项"),
        ("Missing parameter", "缺少参数"),
        ("Missing command.", "缺少命令。"),
        ("Invalid value for", "参数值无效："),
        ("Invalid value:", "值无效："),
        ("No such option:", "未知选项："),
        ("No such command", "未知命令"),
        ("Possible options:", "可选项："),
        ("Did you mean", "你是否想输入"),
        ("Path ", "路径 "),
        ("File ", "文件 "),
        ("Directory ", "目录 "),
        ("does not exist.", "不存在。"),
        ("is not readable.", "不可读。"),
        ("is a directory.", "是目录。"),
    )
    for source, target in replacements:
        message = message.replace(source, target)
    return message


_original_rich_format_error = rich_utils.rich_format_error


def _rich_format_error_zh(error: Any) -> None:
    original_format_message = error.format_message
    error.format_message = lambda: _translate_click_message(original_format_message())
    _original_rich_format_error(error)


class ChineseTyperGroup(TyperGroup):
    """将 Typer 顶层命令的用法标题汉化。"""

    def get_usage(self, ctx: Any) -> str:
        return super().get_usage(ctx).replace("Usage:", "用法：", 1)

    def get_params(self, ctx: Any) -> list[Any]:
        return _localize_builtin_options(super().get_params(ctx))


class ChineseTyperCommand(TyperCommand):
    """将 Typer 子命令的用法标题汉化。"""

    def get_usage(self, ctx: Any) -> str:
        return super().get_usage(ctx).replace("Usage:", "用法：", 1)

    def get_params(self, ctx: Any) -> list[Any]:
        return _localize_builtin_options(super().get_params(ctx))


rich_utils.ARGUMENTS_PANEL_TITLE = "参数"
rich_utils.OPTIONS_PANEL_TITLE = "选项"
rich_utils.COMMANDS_PANEL_TITLE = "命令"
rich_utils.ERRORS_PANEL_TITLE = "错误"
rich_utils.DEFAULT_STRING = "[默认值: {}]"
rich_utils.ENVVAR_STRING = "[环境变量: {}]"
rich_utils.DEPRECATED_STRING = "（已弃用）"
rich_utils.REQUIRED_LONG_STRING = "[必填]"
rich_utils.ABORTED_TEXT = "已中止。"
rich_utils.RICH_HELP = "运行 [blue]'{command_path} {help_option}'[/] 查看帮助。"
rich_utils.rich_format_error = _rich_format_error_zh  # type: ignore[assignment]


app = typer.Typer(
    name="traceforge",
    help="将 OpenTelemetry AI Agent 轨迹转化为性能、可靠性与成本洞察。",
    no_args_is_help=True,
    rich_markup_mode="rich",
    cls=ChineseTyperGroup,
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
            help="显示已安装版本并退出。",
        ),
    ] = False,
) -> None:
    """在本地分析导出的轨迹，不向任何位置发送遥测数据。"""


def _abort(message: str) -> NoReturn:
    err_console.print(f"[bold red]错误：[/bold red] {rich_escape(message)}")
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


@app.command(cls=ChineseTyperCommand)
def analyze(
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="OTLP JSON 或 JSONL span 文件。",
        ),
    ],
    input_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="输入格式：auto、otlp、json 或 jsonl。",
        ),
    ] = "auto",
    cost_model: Annotated[
        Path | None,
        typer.Option(
            "--cost-model",
            exists=True,
            dir_okay=False,
            help="JSON 模型价格配置。",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="同时将完整分析写入 JSON。"),
    ] = None,
    compact: Annotated[
        bool,
        typer.Option("--compact", help="写入紧凑 JSON，不进行缩进。"),
    ] = False,
) -> None:
    """分析轨迹并输出 Rich 终端摘要。"""

    result = _analyze_file(source, input_format, cost_model)
    render_terminal(result, console)
    if output is not None:
        write_json(result, output, pretty=not compact)
        console.print(f"\n[green]JSON 已写入：[/green] {rich_escape(str(output))}")


@app.command(cls=ChineseTyperCommand)
def report(
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="OTLP JSON 或 JSONL span 文件。",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="HTML 报告输出路径。"),
    ] = Path("traceforge-report.html"),
    input_format: Annotated[
        str,
        typer.Option("--format", "-f", help="输入格式：auto、otlp、json 或 jsonl。"),
    ] = "auto",
    cost_model: Annotated[
        Path | None,
        typer.Option(
            "--cost-model",
            exists=True,
            dir_okay=False,
            help="JSON 模型价格配置。",
        ),
    ] = None,
    json_output: Annotated[
        Path | None,
        typer.Option("--json-output", help="可选：同时写入分析 JSON。"),
    ] = None,
) -> None:
    """创建可离线查看的自包含 HTML 报告。"""

    result = _analyze_file(source, input_format, cost_model)
    write_html(result, output)
    if json_output is not None:
        write_json(result, json_output)
    console.print(f"[bold green]HTML 报告已写入：[/bold green] {rich_escape(str(output))}")


@app.command(cls=ChineseTyperCommand)
def demo(
    save_trace: Annotated[
        Path | None,
        typer.Option("--save-trace", help="保存合成 OTLP JSON 输入。"),
    ] = None,
    html: Annotated[
        Path | None,
        typer.Option("--html", help="同时写入自包含 HTML 报告。"),
    ] = None,
    json_output: Annotated[
        Path | None,
        typer.Option("--json-output", help="同时写入分析 JSON。"),
    ] = None,
) -> None:
    """分析一次包含工具调用失败与重试的内置 Agent 运行。"""

    payload = demo_payload()
    result = analyze_spans(
        parse_payload(payload),
        source="内置演示",
        cost_model=CostModel.demo(),
    )
    render_terminal(result, console)
    if save_trace is not None:
        save_trace.parent.mkdir(parents=True, exist_ok=True)
        save_trace.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        console.print(f"\n[green]演示轨迹已写入：[/green] {rich_escape(str(save_trace))}")
    if html is not None:
        write_html(result, html)
        console.print(f"[green]HTML 报告已写入：[/green] {rich_escape(str(html))}")
    if json_output is not None:
        write_json(result, json_output)
        console.print(f"[green]JSON 已写入：[/green] {rich_escape(str(json_output))}")
