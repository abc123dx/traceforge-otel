"""Trace analysis for latency, critical path, tools, retries, tokens, and cost."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from traceforge.costs import CostModel
from traceforge.models import (
    AnalysisResult,
    CriticalPath,
    ModelUsage,
    RetryLoop,
    Span,
    ToolError,
    TraceSummary,
)

INPUT_TOKEN_KEYS = (
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.prompt_tokens",
    "llm.token_count.prompt",
    "input_tokens",
)
OUTPUT_TOKEN_KEYS = (
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.completion_tokens",
    "llm.token_count.completion",
    "output_tokens",
)
MODEL_KEYS = (
    "gen_ai.response.model",
    "gen_ai.request.model",
    "llm.model_name",
    "model",
)
TOOL_NAME_KEYS = (
    "gen_ai.tool.name",
    "tool.name",
    "tool_name",
)
OPERATION_KEYS = (
    "gen_ai.operation.name",
    "otel.operation.name",
)
RETRY_KEYS = (
    "gen_ai.request.retry_number",
    "gen_ai.retry.count",
    "retry.count",
    "retry_number",
)


@dataclass(slots=True)
class _UsageAccumulator:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    priced: bool = False


def _attribute(span: Span, keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in span.attributes:
            return span.attributes[key]
    return default


def _as_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _model_name(span: Span) -> str | None:
    value = _attribute(span, MODEL_KEYS)
    return str(value) if value not in (None, "") else None


def _operation_name(span: Span) -> str:
    return str(_attribute(span, OPERATION_KEYS, span.name)).lower()


def _tool_name(span: Span) -> str | None:
    value = _attribute(span, TOOL_NAME_KEYS)
    if value not in (None, ""):
        return str(value)
    operation = _operation_name(span)
    if operation in {"execute_tool", "tool", "tool_call"} or span.name.lower().startswith("tool."):
        return span.name.removeprefix("tool.")
    return None


def _union_ns(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    total = 0
    current_start, current_end = sorted(intervals)[0]
    for start, end in sorted(intervals)[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    return total + current_end - current_start


def _critical_path(spans: list[Span]) -> CriticalPath:
    if not spans:
        return CriticalPath((), (), 0.0)
    by_id = {span.span_id: span for span in spans}
    children: dict[str, list[Span]] = defaultdict(list)
    for span in spans:
        parent_id = span.parent_span_id
        if parent_id is not None and parent_id in by_id:
            children[parent_id].append(span)
    for child_list in children.values():
        child_list.sort(key=lambda item: (item.start_ns, item.end_ns, item.span_id))

    memo: dict[str, tuple[int, tuple[Span, ...]]] = {}
    visiting: set[str] = set()

    def visit(span: Span) -> tuple[int, tuple[Span, ...]]:
        if span.span_id in memo:
            return memo[span.span_id]
        if span.span_id in visiting:
            return 0, ()
        visiting.add(span.span_id)
        direct_children = children.get(span.span_id, [])
        covered = _union_ns(
            [
                (max(span.start_ns, child.start_ns), min(span.end_ns, child.end_ns))
                for child in direct_children
                if min(span.end_ns, child.end_ns) > max(span.start_ns, child.start_ns)
            ]
        )
        self_time = max(0, span.end_ns - span.start_ns - covered)
        best_child_score = 0
        best_child_path: tuple[Span, ...] = ()
        for child in direct_children:
            child_score, child_path = visit(child)
            if child_score > best_child_score:
                best_child_score = child_score
                best_child_path = child_path
        visiting.remove(span.span_id)
        result = self_time + best_child_score, (span, *best_child_path)
        memo[span.span_id] = result
        return result

    roots = [span for span in spans if span.parent_span_id not in by_id]
    candidates = roots or spans
    best_score = -1
    best_path: tuple[Span, ...] = ()
    for candidate in candidates:
        score, path = visit(candidate)
        if score > best_score:
            best_score, best_path = score, path
    return CriticalPath(
        span_ids=tuple(span.span_id for span in best_path),
        span_names=tuple(span.name for span in best_path),
        duration_ms=max(0, best_score) / 1_000_000,
    )


def _error_details(span: Span) -> tuple[str, str]:
    error_type = str(
        span.attributes.get(
            "error.type",
            span.attributes.get("exception.type", "span_error"),
        )
    )
    message = str(
        span.attributes.get(
            "error.message",
            span.attributes.get("exception.message", span.status_message),
        )
    )
    for event in span.events:
        if event.name == "exception":
            error_type = str(event.attributes.get("exception.type", error_type))
            message = str(event.attributes.get("exception.message", message))
            break
    return error_type, message


def _tool_errors(spans: list[Span]) -> tuple[ToolError, ...]:
    errors: list[ToolError] = []
    for span in spans:
        tool_name = _tool_name(span)
        if tool_name is None or not span.is_error:
            continue
        error_type, message = _error_details(span)
        errors.append(
            ToolError(
                span_id=span.span_id,
                tool_name=tool_name,
                error_type=error_type,
                message=message,
                duration_ms=span.duration_ms,
            )
        )
    return tuple(errors)


def _retry_signature(span: Span) -> str:
    tool_name = _tool_name(span)
    if tool_name is not None:
        return f"tool:{tool_name}"
    model = _model_name(span)
    if model is not None:
        return f"model:{_operation_name(span)}:{model}"
    return f"span:{span.name}"


def _has_explicit_retry(span: Span) -> bool:
    return _as_nonnegative_int(_attribute(span, RETRY_KEYS, 0)) > 0


def _retry_loops(spans: list[Span]) -> tuple[RetryLoop, ...]:
    groups: dict[tuple[str | None, str], list[Span]] = defaultdict(list)
    for span in spans:
        groups[(span.parent_span_id, _retry_signature(span))].append(span)

    loops: list[RetryLoop] = []
    for (_, signature), attempts in groups.items():
        attempts.sort(key=lambda item: (item.start_ns, item.end_ns, item.span_id))
        if len(attempts) < 2:
            continue
        failed_before_last = any(span.is_error for span in attempts[:-1])
        explicitly_marked = any(_has_explicit_retry(span) for span in attempts)
        if not (failed_before_last or explicitly_marked):
            continue
        loops.append(
            RetryLoop(
                signature=signature,
                attempts=len(attempts),
                span_ids=tuple(span.span_id for span in attempts),
                recovered=not attempts[-1].is_error,
                wasted_ms=sum(span.duration_ms for span in attempts[:-1]),
            )
        )
    return tuple(sorted(loops, key=lambda loop: (-loop.wasted_ms, loop.signature)))


def _model_usage(
    spans: list[Span],
    cost_model: CostModel | None,
) -> tuple[tuple[ModelUsage, ...], int, int, float]:
    usage: dict[str, _UsageAccumulator] = defaultdict(_UsageAccumulator)
    total_input = 0
    total_output = 0
    total_cost = 0.0
    for span in spans:
        input_tokens = _as_nonnegative_int(_attribute(span, INPUT_TOKEN_KEYS, 0))
        output_tokens = _as_nonnegative_int(_attribute(span, OUTPUT_TOKEN_KEYS, 0))
        model = _model_name(span)
        if model is None and not (input_tokens or output_tokens):
            continue
        model = model or "unknown"
        accumulator = usage[model]
        accumulator.calls += 1
        accumulator.input_tokens += input_tokens
        accumulator.output_tokens += output_tokens
        total_input += input_tokens
        total_output += output_tokens
        if cost_model is not None:
            estimate = cost_model.estimate(model, input_tokens, output_tokens)
            if estimate is not None:
                accumulator.cost_usd += estimate
                accumulator.priced = True
                total_cost += estimate
    model_rows = tuple(
        ModelUsage(
            model=model,
            calls=values.calls,
            input_tokens=values.input_tokens,
            output_tokens=values.output_tokens,
            cost_usd=values.cost_usd,
            priced=values.priced,
        )
        for model, values in sorted(usage.items())
    )
    return model_rows, total_input, total_output, total_cost


def _analyze_trace(spans: list[Span], cost_model: CostModel | None) -> TraceSummary:
    ordered = sorted(spans, key=lambda span: (span.start_ns, span.end_ns, span.span_id))
    start_ns = min(span.start_ns for span in ordered)
    end_ns = max(span.end_ns for span in ordered)
    tool_errors = _tool_errors(ordered)
    usage, input_tokens, output_tokens, cost_usd = _model_usage(ordered, cost_model)
    return TraceSummary(
        trace_id=ordered[0].trace_id,
        span_count=len(ordered),
        duration_ms=(end_ns - start_ns) / 1_000_000,
        critical_path=_critical_path(ordered),
        tool_calls=sum(_tool_name(span) is not None for span in ordered),
        tool_errors=tool_errors,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        model_usage=usage,
        retry_loops=_retry_loops(ordered),
    )


def analyze_spans(
    spans: list[Span],
    *,
    source: str = "<memory>",
    cost_model: CostModel | None = None,
    generated_at: str | None = None,
) -> AnalysisResult:
    """Analyze normalized spans, grouped by trace ID."""

    if not spans:
        raise ValueError("At least one span is required.")
    grouped: dict[str, list[Span]] = defaultdict(list)
    for span in spans:
        grouped[span.trace_id].append(span)
    traces = tuple(
        _analyze_trace(trace_spans, cost_model)
        for _, trace_spans in sorted(grouped.items(), key=lambda item: item[0])
    )
    return AnalysisResult(
        source=source,
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        traces=traces,
        cost_model_name=cost_model.name if cost_model is not None else None,
    )
