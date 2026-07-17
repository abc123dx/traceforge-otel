"""供 ``traceforge demo`` 使用的确定性真实感 Agent 轨迹。"""

from __future__ import annotations

from typing import Any

BASE_NS = 1_735_689_600_000_000_000
TRACE_ID = "7f3a2c0917b34f5aa891cd79e6f92410"


def _attribute(key: str, value: str | int | float | bool) -> dict[str, Any]:
    if isinstance(value, bool):
        wrapped: dict[str, Any] = {"boolValue": value}
    elif isinstance(value, int):
        wrapped = {"intValue": str(value)}
    elif isinstance(value, float):
        wrapped = {"doubleValue": value}
    else:
        wrapped = {"stringValue": value}
    return {"key": key, "value": wrapped}


def _span(
    span_id: str,
    parent_id: str,
    name: str,
    start_ms: int,
    end_ms: int,
    attributes: list[tuple[str, str | int | float | bool]],
    *,
    status: str = "STATUS_CODE_OK",
    status_message: str = "",
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "traceId": TRACE_ID,
        "spanId": span_id,
        "parentSpanId": parent_id,
        "name": name,
        "kind": "SPAN_KIND_INTERNAL",
        "startTimeUnixNano": str(BASE_NS + start_ms * 1_000_000),
        "endTimeUnixNano": str(BASE_NS + end_ms * 1_000_000),
        "attributes": [_attribute(key, value) for key, value in attributes],
        "status": {"code": status, "message": status_message},
        "events": events or [],
    }


def demo_payload() -> dict[str, Any]:
    """返回包含一条 Agent 轨迹的合成 OTLP/HTTP JSON 导出。"""

    spans = [
        _span(
            "0000000000000001",
            "",
            "travel-assistant.run",
            0,
            2800,
            [
                ("gen_ai.operation.name", "invoke_agent"),
                ("agent.name", "travel-assistant"),
                ("session.id", "demo-session-42"),
            ],
        ),
        _span(
            "0000000000000002",
            "0000000000000001",
            "规划行程",
            100,
            800,
            [
                ("gen_ai.operation.name", "chat"),
                ("gen_ai.provider.name", "demo-cloud"),
                ("gen_ai.request.model", "demo-agent-1"),
                ("gen_ai.response.model", "demo-agent-1"),
                ("gen_ai.usage.input_tokens", 920),
                ("gen_ai.usage.output_tokens", 140),
            ],
        ),
        _span(
            "0000000000000003",
            "0000000000000001",
            "tool.get_weather",
            850,
            1150,
            [
                ("gen_ai.operation.name", "execute_tool"),
                ("gen_ai.tool.name", "get_weather"),
                ("gen_ai.tool.call.id", "call_weather_1"),
                ("gen_ai.request.retry_number", 0),
                ("error.type", "upstream_timeout"),
                ("error.message", "天气服务超过 250 ms 截止时间"),
            ],
            status="STATUS_CODE_ERROR",
            status_message="上游超时",
            events=[
                {
                    "name": "exception",
                    "timeUnixNano": str(BASE_NS + 1140 * 1_000_000),
                    "attributes": [
                        _attribute("exception.type", "TimeoutError"),
                        _attribute(
                            "exception.message",
                            "天气服务超过 250 ms 截止时间",
                        ),
                    ],
                }
            ],
        ),
        _span(
            "0000000000000004",
            "0000000000000001",
            "tool.get_weather",
            1180,
            1550,
            [
                ("gen_ai.operation.name", "execute_tool"),
                ("gen_ai.tool.name", "get_weather"),
                ("gen_ai.tool.call.id", "call_weather_2"),
                ("gen_ai.request.retry_number", 1),
                ("server.address", "weather.demo.internal"),
            ],
        ),
        _span(
            "0000000000000005",
            "0000000000000001",
            "tool.search_flights",
            1600,
            1950,
            [
                ("gen_ai.operation.name", "execute_tool"),
                ("gen_ai.tool.name", "search_flights"),
                ("gen_ai.tool.call.id", "call_flights_1"),
                ("server.address", "flights.demo.internal"),
            ],
        ),
        _span(
            "0000000000000006",
            "0000000000000001",
            "生成答复",
            2000,
            2650,
            [
                ("gen_ai.operation.name", "chat"),
                ("gen_ai.provider.name", "demo-cloud"),
                ("gen_ai.request.model", "demo-agent-1"),
                ("gen_ai.response.model", "demo-agent-1"),
                ("gen_ai.usage.input_tokens", 1450),
                ("gen_ai.usage.output_tokens", 320),
                ("gen_ai.response.finish_reasons", "stop"),
            ],
        ),
    ]
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attribute("service.name", "travel-agent"),
                        _attribute("service.version", "2.4.0"),
                        _attribute("deployment.environment.name", "demo"),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "demo.agent.instrumentation", "version": "1.0.0"},
                        "spans": spans,
                    }
                ],
            }
        ]
    }
