from __future__ import annotations

import json
import re

from claude_tap.viewer import _generate_html_viewer
from scripts.analyze_trace_compaction import (
    analyze_paths,
    compact_jsonl,
    load_jsonl_records,
    restore_compact_jsonl,
    result_to_dict,
    write_jsonl_records,
)


def _write_jsonl(path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def _normalize_generated_html(html: str) -> str:
    html = re.sub(r'const __TRACE_JSONL_PATH__ = ".*?";', 'const __TRACE_JSONL_PATH__ = "<trace>";', html)
    return re.sub(r'const __TRACE_HTML_PATH__ = ".*?";', 'const __TRACE_HTML_PATH__ = "<html>";', html)


def test_analyze_paths_estimates_input_prefix_savings(tmp_path) -> None:
    trace = tmp_path / "trace_prefix.jsonl"
    first = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "A"}]}
    second = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "B"}]}
    third = {"type": "function_call_output", "call_id": "call_1", "output": "C"}
    _write_jsonl(
        trace,
        [
            {"request": {"body": {"input": [first]}}, "response": {"body": {"id": "resp_1"}}},
            {"request": {"body": {"input": [first, second]}}, "response": {"body": {"id": "resp_2"}}},
            {"request": {"body": {"input": [first, second, third]}}, "response": {"body": {"id": "resp_3"}}},
        ],
    )

    result = analyze_paths([trace])

    assert result.files == 1
    assert result.records == 3
    assert result.context_fields == 3
    assert result.compacted_fields == 2
    assert result.prefix_items == 3
    assert result.saved_bytes > 0
    assert result.estimated_compact_bytes < result.canonical_record_bytes


def test_analyze_paths_does_not_compact_unrelated_context(tmp_path) -> None:
    trace = tmp_path / "trace_no_prefix.jsonl"
    _write_jsonl(
        trace,
        [
            {"request": {"body": {"messages": [{"role": "user", "content": "A"}]}}},
            {"request": {"body": {"messages": [{"role": "user", "content": "B"}]}}},
        ],
    )

    result = analyze_paths([trace])

    assert result.context_fields == 2
    assert result.compacted_fields == 0
    assert result.saved_bytes == 0


def test_result_to_dict_reports_top_savings(tmp_path) -> None:
    trace = tmp_path / "trace_top.jsonl"
    message = {"role": "user", "content": "repeat " * 80}
    _write_jsonl(
        trace,
        [
            {"request": {"body": {"messages": [message]}}},
            {"request": {"body": {"messages": [message, {"role": "assistant", "content": "next"}]}}},
        ],
    )

    payload = result_to_dict(analyze_paths([trace]), top=1)

    assert payload["files"] == 1
    assert payload["top_savings"][0]["field"] == "request.body.messages"
    assert payload["top_savings"][0]["prefix_items"] == 1
    assert payload["context_field_bytes"] > 0
    assert payload["prefix_candidate_bytes"] > 0


def test_compact_restore_round_trip_keeps_exported_html_equivalent(tmp_path) -> None:
    original_trace = tmp_path / "original.jsonl"
    compact_trace = tmp_path / "compact.jsonl"
    restored_trace = tmp_path / "restored.jsonl"
    original_html = tmp_path / "original.html"
    restored_html = tmp_path / "restored.html"

    first = {
        "role": "user",
        "content": [{"type": "text", "text": "Please inspect the trace history. " + "shared context " * 80}],
    }
    second = {
        "role": "assistant",
        "content": [{"type": "text", "text": "I inspected the first batch."}],
    }
    third = {
        "role": "user",
        "content": [{"type": "text", "text": "Continue with the next batch."}],
    }
    records = [
        {
            "request": {
                "method": "POST",
                "path": "/v1/messages",
                "body": {"model": "claude-test", "messages": [first]},
            },
            "response": {"status": 200, "body": {"content": [{"type": "text", "text": "First response"}]}},
        },
        {
            "request": {
                "method": "POST",
                "path": "/v1/messages",
                "body": {"model": "claude-test", "messages": [first, second]},
            },
            "response": {"status": 200, "body": {"content": [{"type": "text", "text": "Second response"}]}},
        },
        {
            "request": {
                "method": "POST",
                "path": "/v1/messages",
                "body": {"model": "claude-test", "messages": [first, second, third]},
            },
            "response": {"status": 200, "body": {"content": [{"type": "text", "text": "Third response"}]}},
        },
    ]
    write_jsonl_records(original_trace, records)

    compact_jsonl(original_trace, compact_trace)
    restore_compact_jsonl(compact_trace, restored_trace)

    compacted_records = load_jsonl_records(compact_trace)
    assert compact_trace.stat().st_size < original_trace.stat().st_size
    assert compacted_records[1]["request"]["body"]["messages"]["$prefix_len"] == 1
    assert compacted_records[2]["request"]["body"]["messages"]["$prefix_len"] == 2
    assert load_jsonl_records(restored_trace) == load_jsonl_records(original_trace)

    _generate_html_viewer(original_trace, original_html)
    _generate_html_viewer(restored_trace, restored_html)

    assert _normalize_generated_html(restored_html.read_text(encoding="utf-8")) == _normalize_generated_html(
        original_html.read_text(encoding="utf-8")
    )
