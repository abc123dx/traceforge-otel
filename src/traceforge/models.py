"""解析、分析与渲染共用的强类型领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class SpanEvent:
    """OpenTelemetry span 事件。"""

    name: str
    time_ns: int
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "time_ns": self.time_ns,
            "attributes": self.attributes,
        }


@dataclass(frozen=True, slots=True)
class Span:
    """与 OTLP JSON 表示无关的规范化 span。"""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start_ns: int
    end_ns: int
    attributes: dict[str, Any] = field(default_factory=dict)
    status_code: str = "UNSET"
    status_message: str = ""
    kind: str = "INTERNAL"
    events: tuple[SpanEvent, ...] = ()
    resource: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return max(0, self.end_ns - self.start_ns) / 1_000_000

    @property
    def is_error(self) -> bool:
        if self.status_code.upper() == "ERROR":
            return True
        if any(key in self.attributes for key in ("error.type", "exception.type")):
            return True
        return any(event.name == "exception" for event in self.events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_ns": self.start_ns,
            "end_ns": self.end_ns,
            "duration_ms": round(self.duration_ms, 6),
            "attributes": self.attributes,
            "status_code": self.status_code,
            "status_message": self.status_message,
            "kind": self.kind,
            "events": [event.to_dict() for event in self.events],
            "resource": self.resource,
        }


@dataclass(frozen=True, slots=True)
class CriticalPath:
    """一条轨迹中成本最高的因果路径。"""

    span_ids: tuple[str, ...]
    span_names: tuple[str, ...]
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_ids": list(self.span_ids),
            "span_names": list(self.span_names),
            "duration_ms": round(self.duration_ms, 6),
        }


@dataclass(frozen=True, slots=True)
class ToolError:
    """一次失败的工具调用。"""

    span_id: str
    tool_name: str
    error_type: str
    message: str
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "tool_name": self.tool_name,
            "error_type": self.error_type,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 6),
        }


@dataclass(frozen=True, slots=True)
class RetryLoop:
    """从同级 span 推断出的潜在重试序列。"""

    signature: str
    attempts: int
    span_ids: tuple[str, ...]
    recovered: bool
    wasted_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "attempts": self.attempts,
            "span_ids": list(self.span_ids),
            "recovered": self.recovered,
            "wasted_ms": round(self.wasted_ms, 6),
        }


@dataclass(frozen=True, slots=True)
class ModelUsage:
    """单个模型的 Token 与成本汇总。"""

    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    priced: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "cost_usd": round(self.cost_usd, 8),
            "priced": self.priced,
        }


@dataclass(frozen=True, slots=True)
class TraceSummary:
    """单条 OpenTelemetry 轨迹的分析结果。"""

    trace_id: str
    span_count: int
    duration_ms: float
    critical_path: CriticalPath
    tool_calls: int
    tool_errors: tuple[ToolError, ...]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model_usage: tuple[ModelUsage, ...]
    retry_loops: tuple[RetryLoop, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_count": self.span_count,
            "duration_ms": round(self.duration_ms, 6),
            "critical_path": self.critical_path.to_dict(),
            "tool_calls": self.tool_calls,
            "tool_errors": [error.to_dict() for error in self.tool_errors],
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "cost_usd": round(self.cost_usd, 8),
            "model_usage": [usage.to_dict() for usage in self.model_usage],
            "retry_loops": [loop.to_dict() for loop in self.retry_loops],
        }


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """适合序列化为 JSON 的顶层分析结果。"""

    source: str
    generated_at: str
    traces: tuple[TraceSummary, ...]
    cost_model_name: str | None

    @property
    def span_count(self) -> int:
        return sum(trace.span_count for trace in self.traces)

    @property
    def input_tokens(self) -> int:
        return sum(trace.input_tokens for trace in self.traces)

    @property
    def output_tokens(self) -> int:
        return sum(trace.output_tokens for trace in self.traces)

    @property
    def cost_usd(self) -> float:
        return sum(trace.cost_usd for trace in self.traces)

    @property
    def tool_calls(self) -> int:
        return sum(trace.tool_calls for trace in self.traces)

    @property
    def tool_error_count(self) -> int:
        return sum(len(trace.tool_errors) for trace in self.traces)

    @property
    def retry_loop_count(self) -> int:
        return sum(len(trace.retry_loops) for trace in self.traces)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "source": self.source,
            "generated_at": self.generated_at,
            "cost_model": self.cost_model_name,
            "summary": {
                "trace_count": len(self.traces),
                "span_count": self.span_count,
                "tool_calls": self.tool_calls,
                "tool_errors": self.tool_error_count,
                "retry_loops": self.retry_loop_count,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.input_tokens + self.output_tokens,
                "cost_usd": round(self.cost_usd, 8),
            },
            "traces": [trace.to_dict() for trace in self.traces],
        }
