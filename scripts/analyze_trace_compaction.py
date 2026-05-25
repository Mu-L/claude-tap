#!/usr/bin/env python3
"""Estimate trace JSONL prefix compaction potential."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONTEXT_FIELDS = (
    ("request", "body", "messages"),
    ("request", "body", "input"),
)


@dataclass(frozen=True)
class FieldSavings:
    path: Path
    line: int
    field: str
    item_count: int
    prefix_items: int
    original_bytes: int
    compact_bytes: int

    @property
    def saved_bytes(self) -> int:
        return self.original_bytes - self.compact_bytes


@dataclass
class AnalysisResult:
    files: int = 0
    records: int = 0
    invalid_lines: int = 0
    raw_bytes: int = 0
    canonical_record_bytes: int = 0
    estimated_compact_bytes: int = 0
    context_fields: int = 0
    compacted_fields: int = 0
    prefix_items: int = 0
    field_savings: list[FieldSavings] = field(default_factory=list)

    @property
    def saved_bytes(self) -> int:
        return self.canonical_record_bytes - self.estimated_compact_bytes

    @property
    def saved_percent(self) -> float:
        if self.canonical_record_bytes == 0:
            return 0.0
        return self.saved_bytes / self.canonical_record_bytes * 100

    @property
    def raw_saved_percent(self) -> float:
        if self.raw_bytes == 0:
            return 0.0
        return self.saved_bytes / self.raw_bytes * 100


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def encoded_size(value: Any) -> int:
    return len(canonical_json(value).encode("utf-8"))


def get_nested(root: Any, path: tuple[str, ...]) -> Any:
    current = root
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def common_prefix_len(left: list[Any], right: list[Any]) -> int:
    count = 0
    for left_item, right_item in zip(left, right):
        if canonical_json(left_item) != canonical_json(right_item):
            break
        count += 1
    return count


def compact_field_payload(previous_line: int, prefix_len: int, delta_items: list[Any]) -> dict[str, Any]:
    return {
        "$prefix_ref": previous_line,
        "$prefix_len": prefix_len,
        "$delta": delta_items,
    }


def trace_paths(inputs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        if item.is_file():
            paths.append(item)
        elif item.is_dir():
            paths.extend(sorted(path for path in item.rglob("*.jsonl") if path.is_file()))
    return sorted(dict.fromkeys(paths))


def analyze_file(path: Path, max_records: int | None = None) -> AnalysisResult:
    result = AnalysisResult(files=1)
    previous_fields: dict[str, tuple[int, list[Any]]] = {}
    processed = 0

    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if max_records is not None and processed >= max_records:
                break
            stripped = raw_line.strip()
            if not stripped:
                continue
            result.raw_bytes += len(raw_line)
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                result.invalid_lines += 1
                continue

            processed += 1
            result.records += 1
            record_bytes = encoded_size(record)
            result.canonical_record_bytes += record_bytes
            compact_record_bytes = record_bytes

            for field_path in CONTEXT_FIELDS:
                value = get_nested(record, field_path)
                if not isinstance(value, list):
                    continue
                field_name = ".".join(field_path)
                result.context_fields += 1
                original_bytes = encoded_size(value)
                previous = previous_fields.get(field_name)
                previous_fields[field_name] = (line_number, value)
                if previous is None:
                    continue

                previous_line, previous_value = previous
                prefix_len = common_prefix_len(previous_value, value)
                if prefix_len == 0:
                    continue
                payload = compact_field_payload(previous_line, prefix_len, value[prefix_len:])
                compact_bytes = encoded_size(payload)
                if compact_bytes >= original_bytes:
                    continue

                savings = FieldSavings(
                    path=path,
                    line=line_number,
                    field=field_name,
                    item_count=len(value),
                    prefix_items=prefix_len,
                    original_bytes=original_bytes,
                    compact_bytes=compact_bytes,
                )
                result.field_savings.append(savings)
                result.compacted_fields += 1
                result.prefix_items += prefix_len
                compact_record_bytes -= savings.saved_bytes

            result.estimated_compact_bytes += compact_record_bytes

    return result


def merge_results(results: list[AnalysisResult]) -> AnalysisResult:
    merged = AnalysisResult()
    for result in results:
        merged.files += result.files
        merged.records += result.records
        merged.invalid_lines += result.invalid_lines
        merged.raw_bytes += result.raw_bytes
        merged.canonical_record_bytes += result.canonical_record_bytes
        merged.estimated_compact_bytes += result.estimated_compact_bytes
        merged.context_fields += result.context_fields
        merged.compacted_fields += result.compacted_fields
        merged.prefix_items += result.prefix_items
        merged.field_savings.extend(result.field_savings)
    return merged


def analyze_paths(inputs: list[Path], max_records_per_file: int | None = None) -> AnalysisResult:
    return merge_results([analyze_file(path, max_records_per_file) for path in trace_paths(inputs)])


def format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{value} B"
        amount /= 1024
    return f"{value} B"


def result_to_dict(result: AnalysisResult, top: int) -> dict[str, Any]:
    top_savings = sorted(result.field_savings, key=lambda item: item.saved_bytes, reverse=True)[:top]
    return {
        "files": result.files,
        "records": result.records,
        "invalid_lines": result.invalid_lines,
        "raw_bytes": result.raw_bytes,
        "canonical_record_bytes": result.canonical_record_bytes,
        "estimated_compact_bytes": result.estimated_compact_bytes,
        "saved_bytes": result.saved_bytes,
        "saved_percent": result.saved_percent,
        "raw_saved_percent": result.raw_saved_percent,
        "context_fields": result.context_fields,
        "compacted_fields": result.compacted_fields,
        "prefix_items": result.prefix_items,
        "top_savings": [
            {
                "path": str(item.path),
                "line": item.line,
                "field": item.field,
                "item_count": item.item_count,
                "prefix_items": item.prefix_items,
                "original_bytes": item.original_bytes,
                "compact_bytes": item.compact_bytes,
                "saved_bytes": item.saved_bytes,
            }
            for item in top_savings
        ],
    }


def print_text_report(result: AnalysisResult, top: int) -> None:
    print("Trace prefix compaction estimate")
    print(f"Files: {result.files}")
    print(f"Records: {result.records}")
    print(f"Invalid lines: {result.invalid_lines}")
    print(f"Raw JSONL bytes: {format_bytes(result.raw_bytes)}")
    print(f"Canonical record bytes: {format_bytes(result.canonical_record_bytes)}")
    print(f"Estimated compact bytes: {format_bytes(result.estimated_compact_bytes)}")
    print(f"Estimated savings: {format_bytes(result.saved_bytes)} ({result.saved_percent:.2f}% canonical)")
    print(f"Context fields scanned: {result.context_fields}")
    print(f"Compacted fields: {result.compacted_fields}")
    print(f"Prefix items reused: {result.prefix_items}")

    top_savings = sorted(result.field_savings, key=lambda item: item.saved_bytes, reverse=True)[:top]
    if not top_savings:
        return
    print()
    print("Top savings:")
    for item in top_savings:
        print(
            f"- {item.path}:{item.line} {item.field} "
            f"items={item.item_count} prefix={item.prefix_items} "
            f"saved={format_bytes(item.saved_bytes)}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Trace JSONL file or directory paths")
    parser.add_argument("--max-records-per-file", type=int, default=None)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = analyze_paths(args.paths, args.max_records_per_file)
    if args.json:
        print(json.dumps(result_to_dict(result, args.top), ensure_ascii=False, indent=2))
    else:
        print_text_report(result, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
