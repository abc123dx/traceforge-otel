from __future__ import annotations

import json
from pathlib import Path

import pytest

from traceforge.demo import demo_payload
from traceforge.parser import TraceParseError, load_spans, parse_jsonl, parse_payload


def test_parses_otlp_resource_spans_and_typed_attributes() -> None:
    spans = parse_payload(demo_payload())

    assert len(spans) == 6
    assert spans[0].resource["service.name"] == "travel-agent"
    assert spans[1].attributes["gen_ai.usage.input_tokens"] == 920
    assert spans[2].status_code == "ERROR"
    assert spans[2].events[0].attributes["exception.type"] == "TimeoutError"


def test_parses_flat_jsonl_and_iso_timestamps() -> None:
    text = "\n".join(
        [
            json.dumps(
                {
                    "trace_id": "trace-1",
                    "span_id": "span-1",
                    "name": "root",
                    "start_time": "2026-01-02T03:04:05Z",
                    "end_time": "2026-01-02T03:04:05.250Z",
                    "attributes": {"answer": 42},
                }
            ),
            "",
        ]
    )

    spans = parse_jsonl(text)

    assert len(spans) == 1
    assert spans[0].duration_ms == pytest.approx(250.0)
    assert spans[0].attributes == {"answer": 42}


def test_auto_detects_jsonl_extension(tmp_path: Path) -> None:
    source = tmp_path / "trace.jsonl"
    source.write_text(
        '{"trace_id":"t","span_id":"s","name":"x","start_ns":1,"end_ns":2}\n',
        encoding="utf-8",
    )

    assert load_spans(source)[0].span_id == "s"


def test_rejects_missing_identifiers() -> None:
    with pytest.raises(TraceParseError, match="traceId 和 spanId"):
        parse_payload(
            {
                "name": "broken",
                "startTimeUnixNano": "1",
                "endTimeUnixNano": "2",
            }
        )
