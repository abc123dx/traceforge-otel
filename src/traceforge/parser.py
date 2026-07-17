"""OTLP JSON and JSONL span parsing."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from traceforge.models import Span, SpanEvent


class TraceParseError(ValueError):
    """Raised when trace input cannot be normalized."""


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default


def _decode_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    scalar_keys = (
        "stringValue",
        "string_value",
        "intValue",
        "int_value",
        "doubleValue",
        "double_value",
        "boolValue",
        "bool_value",
        "bytesValue",
        "bytes_value",
    )
    for key in scalar_keys:
        if key in value:
            raw = value[key]
            if key.startswith("int"):
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return raw
            return raw
    array_value = _first(value, "arrayValue", "array_value")
    if isinstance(array_value, dict):
        values = array_value.get("values", [])
        if isinstance(values, list):
            return [_decode_value(item) for item in values]
    kvlist_value = _first(value, "kvlistValue", "kvlist_value")
    if isinstance(kvlist_value, dict):
        values = kvlist_value.get("values", [])
        return _parse_attributes(values)
    return {str(key): _decode_value(item) for key, item in value.items()}


def _parse_attributes(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(key): _decode_value(value) for key, value in raw.items()}
    if isinstance(raw, list):
        result: dict[str, Any] = {}
        for item in raw:
            if not isinstance(item, dict) or "key" not in item:
                continue
            result[str(item["key"])] = _decode_value(item.get("value"))
        return result
    raise TraceParseError("Span attributes must be an object or OTLP key/value array.")


def _timestamp_ns(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise TraceParseError(f"{field} must be a timestamp, not a boolean.")
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                normalized = value.replace("Z", "+00:00")
                return int(datetime.fromisoformat(normalized).timestamp() * 1_000_000_000)
            except ValueError as exc:
                raise TraceParseError(f"Invalid {field}: {value!r}.") from exc
    raise TraceParseError(f"Missing or invalid {field}.")


def _status(raw: Any) -> tuple[str, str]:
    if not isinstance(raw, dict):
        return "UNSET", ""
    code = _first(raw, "code", "statusCode", "status_code", default="UNSET")
    message = str(_first(raw, "message", "description", default=""))
    if isinstance(code, int):
        return {0: "UNSET", 1: "OK", 2: "ERROR"}.get(code, str(code)), message
    normalized = str(code).upper().removeprefix("STATUS_CODE_")
    return normalized, message


def _kind(raw: Any) -> str:
    if isinstance(raw, int):
        return {
            0: "UNSPECIFIED",
            1: "INTERNAL",
            2: "SERVER",
            3: "CLIENT",
            4: "PRODUCER",
            5: "CONSUMER",
        }.get(raw, str(raw))
    return str(raw or "INTERNAL").upper().removeprefix("SPAN_KIND_")


def _parse_events(raw: Any) -> tuple[SpanEvent, ...]:
    if not isinstance(raw, list):
        return ()
    events: list[SpanEvent] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        time_value = _first(item, "timeUnixNano", "time_unix_nano", "timestamp", default=0)
        events.append(
            SpanEvent(
                name=str(item.get("name", "event")),
                time_ns=_timestamp_ns(time_value, "event timestamp") if time_value else 0,
                attributes=_parse_attributes(item.get("attributes")),
            )
        )
    return tuple(events)


def _resource_attributes(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    if "attributes" in raw:
        return _parse_attributes(raw["attributes"])
    return _parse_attributes(raw)


def _iter_raw_spans(payload: Any) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                raise TraceParseError("Every span in a JSON array must be an object.")
            yield item, _resource_attributes(item.get("resource"))
        return
    if not isinstance(payload, dict):
        raise TraceParseError("Trace input must be a JSON object or array.")

    resource_spans = _first(payload, "resourceSpans", "resource_spans")
    if isinstance(resource_spans, list):
        for resource_group in resource_spans:
            if not isinstance(resource_group, dict):
                continue
            resource = _resource_attributes(resource_group.get("resource"))
            scope_spans = _first(resource_group, "scopeSpans", "scope_spans", default=[])
            if not isinstance(scope_spans, list):
                continue
            for scope_group in scope_spans:
                if not isinstance(scope_group, dict):
                    continue
                spans = scope_group.get("spans", [])
                if not isinstance(spans, list):
                    continue
                for span in spans:
                    if isinstance(span, dict):
                        yield span, resource
        return

    spans = payload.get("spans")
    if isinstance(spans, list):
        top_resource = _resource_attributes(payload.get("resource"))
        for span in spans:
            if isinstance(span, dict):
                own_resource = _resource_attributes(span.get("resource"))
                yield span, own_resource or top_resource
        return

    yield payload, _resource_attributes(payload.get("resource"))


def _parse_span(raw: dict[str, Any], resource: dict[str, Any]) -> Span:
    trace_id = str(_first(raw, "traceId", "trace_id", default="")).strip()
    span_id = str(_first(raw, "spanId", "span_id", default="")).strip()
    if not trace_id or not span_id:
        raise TraceParseError("Every span needs a non-empty traceId and spanId.")

    start_raw = _first(
        raw,
        "startTimeUnixNano",
        "start_time_unix_nano",
        "start_ns",
        "startTime",
        "start_time",
    )
    end_raw = _first(
        raw,
        "endTimeUnixNano",
        "end_time_unix_nano",
        "end_ns",
        "endTime",
        "end_time",
    )
    start_ns = _timestamp_ns(start_raw, "span start time")
    if end_raw is None and "duration_ms" in raw:
        end_ns = start_ns + int(float(raw["duration_ms"]) * 1_000_000)
    else:
        end_ns = _timestamp_ns(end_raw, "span end time")
    if end_ns < start_ns:
        raise TraceParseError(f"Span {span_id} ends before it starts.")

    status_code, status_message = _status(raw.get("status"))
    if "status_code" in raw:
        status_code = str(raw["status_code"]).upper().removeprefix("STATUS_CODE_")
    if "status_message" in raw:
        status_message = str(raw["status_message"])
    parent = str(_first(raw, "parentSpanId", "parent_span_id", default="")).strip() or None

    return Span(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent,
        name=str(raw.get("name", "unnamed")),
        start_ns=start_ns,
        end_ns=end_ns,
        attributes=_parse_attributes(raw.get("attributes")),
        status_code=status_code,
        status_message=status_message,
        kind=_kind(raw.get("kind")),
        events=_parse_events(raw.get("events")),
        resource=resource,
    )


def parse_payload(payload: Any) -> list[Span]:
    """Normalize a decoded OTLP JSON payload or a list of flat spans."""

    spans = [_parse_span(raw, resource) for raw, resource in _iter_raw_spans(payload)]
    if not spans:
        raise TraceParseError("No spans were found in the input.")
    return spans


def parse_jsonl(text: str) -> list[Span]:
    """Normalize one flat or OTLP-wrapped span object per JSONL line."""

    spans: list[Span] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TraceParseError(f"Invalid JSON on line {line_number}: {exc.msg}.") from exc
        try:
            spans.extend(parse_payload(payload))
        except TraceParseError as exc:
            raise TraceParseError(f"Line {line_number}: {exc}") from exc
    if not spans:
        raise TraceParseError("No spans were found in the JSONL input.")
    return spans


def load_spans(path: Path, input_format: str = "auto") -> list[Span]:
    """Load spans from OTLP JSON or JSONL using explicit or inferred format."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TraceParseError(f"Could not read {path}: {exc}") from exc

    normalized_format = input_format.lower()
    if normalized_format not in {"auto", "otlp", "json", "jsonl"}:
        raise TraceParseError("Input format must be auto, otlp, json, or jsonl.")
    if normalized_format == "jsonl" or (
        normalized_format == "auto" and path.suffix.lower() in {".jsonl", ".ndjson"}
    ):
        return parse_jsonl(text)
    try:
        return parse_payload(json.loads(text))
    except json.JSONDecodeError as exc:
        if normalized_format == "auto":
            return parse_jsonl(text)
        raise TraceParseError(f"Invalid JSON: {exc.msg}.") from exc
