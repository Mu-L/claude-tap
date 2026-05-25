from __future__ import annotations

import json

from scripts.analyze_trace_compaction import analyze_paths, result_to_dict


def _write_jsonl(path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


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
