from __future__ import annotations

import pytest

from traceforge.analyzer import analyze_spans
from traceforge.costs import CostModel
from traceforge.demo import demo_payload
from traceforge.models import Span
from traceforge.parser import parse_payload


def _span(
    span_id: str,
    parent_id: str | None,
    start_ms: int,
    end_ms: int,
) -> Span:
    return Span(
        trace_id="trace",
        span_id=span_id,
        parent_span_id=parent_id,
        name=span_id,
        start_ns=start_ms * 1_000_000,
        end_ns=end_ms * 1_000_000,
    )


def test_critical_path_uses_exclusive_parent_time() -> None:
    spans = [
        _span("root", None, 0, 100),
        _span("branch-a", "root", 10, 70),
        _span("leaf", "branch-a", 20, 60),
        _span("branch-b", "root", 75, 95),
    ]

    trace = analyze_spans(spans, generated_at="fixed").traces[0]

    assert trace.duration_ms == 100
    assert trace.critical_path.span_ids == ("root", "branch-a", "leaf")
    assert trace.critical_path.duration_ms == 80


def test_demo_finds_tool_error_retry_tokens_and_cost() -> None:
    result = analyze_spans(
        parse_payload(demo_payload()),
        cost_model=CostModel.demo(),
        generated_at="fixed",
    )
    trace = result.traces[0]

    assert result.span_count == 6
    assert trace.tool_calls == 3
    assert len(trace.tool_errors) == 1
    assert trace.tool_errors[0].tool_name == "get_weather"
    assert trace.tool_errors[0].error_type == "TimeoutError"
    assert len(trace.retry_loops) == 1
    assert trace.retry_loops[0].attempts == 2
    assert trace.retry_loops[0].recovered is True
    assert trace.retry_loops[0].wasted_ms == 300
    assert trace.input_tokens == 2370
    assert trace.output_tokens == 460
    assert trace.cost_usd == pytest.approx(0.0052625)


def test_unpriced_model_keeps_tokens_without_inventing_cost() -> None:
    model = CostModel.from_dict(
        {
            "name": "strict",
            "models": {
                "known": {"input_per_1m": 1, "output_per_1m": 2},
            },
        }
    )
    span = Span(
        trace_id="t",
        span_id="s",
        parent_span_id=None,
        name="chat",
        start_ns=0,
        end_ns=10,
        attributes={
            "gen_ai.request.model": "unknown",
            "gen_ai.usage.input_tokens": 100,
            "gen_ai.usage.output_tokens": 20,
        },
    )

    trace = analyze_spans([span], cost_model=model, generated_at="fixed").traces[0]

    assert trace.cost_usd == 0
    assert trace.model_usage[0].priced is False
    assert trace.input_tokens == 100
