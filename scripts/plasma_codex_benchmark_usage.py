#!/usr/bin/env python3
"""Local, read-only Codex rollout token accounting for one bounded benchmark.

No discovery of session files, credentials, prompts or tool output. Only selected
telemetry event types are parsed. All output is a small, allowlisted JSON report.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
import uuid

FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens")
MAX_LINE = 16 * 1024 * 1024
MAX_EVENTS = 500000
SAFE_MODEL = re.compile(r"[a-zA-Z0-9._:/-]{1,100}\Z")
SAFE_EFFORT = {"minimal", "low", "medium", "high", "xhigh", "extra_high", "none"}


def clock(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires an explicit UTC offset")
    return parsed.astimezone(dt.timezone.utc)


def event_clock(event: dict) -> dt.datetime | None:
    try:
        return clock(event["timestamp"])
    except (KeyError, ValueError, TypeError):
        return None


def counters(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    if not all(type(value.get(key)) is int and 0 <= value[key] <= 2**63 - 1
               for key in FIELDS):
        return None
    if value["cached_input_tokens"] > value["input_tokens"]:
        return None
    return {key: value[key] for key in FIELDS}


def delta(end: dict, start: dict) -> dict | None:
    if any(end[k] < start[k] for k in FIELDS):
        return None
    result = {k: end[k] - start[k] for k in FIELDS}
    return result if result["cached_input_tokens"] <= result["input_tokens"] else None


def compact(value: object) -> str | None:
    if type(value) is not str or not SAFE_MODEL.fullmatch(value):
        return None
    return value


def read_rollout(path: Path):
    """Parse telemetry-only lines; never decode JSON for arbitrary messages."""
    with path.open("rb") as handle:
        for index, line in enumerate(handle, 1):
            if index > MAX_EVENTS:
                raise ValueError("TELEMETRY_EVENT_LIMIT")
            if len(line) > MAX_LINE:
                # Opaque messages may be huge; do not fail the entire rollout.
                continue
            if b'"type"' not in line:
                continue
            if re.search(rb'"type"\s*:\s*"turn_context"', line):
                # Find only allowlisted, scalar model/effort metadata in-place.
                # Do not decode the rest of the turn context.
                try:
                    ts = re.search(rb'"timestamp"\s*:\s*"([^"\\]{1,80})"', line)
                    model = re.search(rb'"model"\s*:\s*"([a-zA-Z0-9._:/-]{1,100})"', line)
                    effort = re.search(rb'"(?:reasoning_effort|effort)"\s*:\s*"([a-z_]{1,20})"', line)
                    if ts:
                        yield {"type": "turn_context", "timestamp": ts.group(1).decode("ascii"),
                               "payload": {"model": model.group(1).decode("ascii") if model else None,
                                           "reasoning_effort": effort.group(1).decode("ascii") if effort else None}}
                except UnicodeError:
                    pass
                continue
            if not any(re.search(rb'"type"\s*:\s*"' + kind + rb'"', line) for kind in
                       (b"token_usage_record", b"token_count", b"task_started",
                        b"task_complete", b"turn_aborted")):
                continue
            try:
                obj = json.loads(line)
            except (UnicodeError, ValueError):
                continue
            if type(obj) is dict and obj.get("type") == "token_usage_record":
                payload = obj.get("payload")
                if type(payload) is dict:
                    yield {"type": "token_usage_record", "timestamp": obj.get("timestamp"),
                           "response_id": compact(payload.get("response_id")),
                           "turn_id": compact(payload.get("turn_id")),
                           "usage": counters(payload.get("usage"))}
                continue
            if (type(obj) is dict and obj.get("type") == "event_msg" and
                    type(obj.get("payload")) is dict and
                    obj["payload"].get("type") in
                    {"token_count", "task_started", "task_complete", "turn_aborted"}):
                # Drop the original JSON object before yielding sanitized fields.
                payload = obj["payload"]
                kind = payload["type"]
                if kind == "token_count":
                    info = payload.get("info")
                    total = info.get("total_token_usage") if type(info) is dict else None
                    yield {"type": kind, "timestamp": obj.get("timestamp"),
                           "total": counters(total)}
                else:
                    yield {"type": kind, "timestamp": obj.get("timestamp"),
                           "turn_id": compact(payload.get("turn_id"))}


def extract(session: Path, start: dt.datetime, end: dt.datetime) -> dict:
    if end <= start:
        raise ValueError("BENCHMARK_WINDOW_INVALID")
    if session.is_symlink() or not session.is_file():
        raise ValueError("SESSION_FILE_INVALID")
    events = list(read_rollout(session))
    starts = [(i, e) for i, e in enumerate(events) if e["type"] == "task_started"
              and (t := event_clock(e)) is not None and start <= t <= end]
    result = {
        "schema": "plasma.codex.benchmark_usage.v1",
        "source": "codex_desktop_local_rollout",
        "scope": "single_completed_turn",
        "status": "NOT_AVAILABLE",
        "reason": None,
        "window_start_utc": start.isoformat(),
        "window_end_utc": end.isoformat(),
        "session_id": None,
        "turn_id": None,
        "model": None,
        "reasoning_effort": None,
        **{key: None for key in FIELDS},
        "accounting": None,
    }
    match = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27,36})\.jsonl\Z", session.name)
    if match:
        try:
            result["session_id"] = str(uuid.UUID(match.group(1)))
        except ValueError:
            pass
    if len(starts) != 1 or starts[0][1].get("turn_id") is None:
        result["reason"] = "TURN_BOUNDARY_AMBIGUOUS" if starts else "TURN_START_NOT_FOUND"
        return result
    i_start, first = starts[0]
    turn_id = first["turn_id"]
    result["turn_id"] = turn_id
    finishes = [(i, e) for i, e in enumerate(events) if i > i_start and
                e["type"] in ("task_complete", "turn_aborted") and
                e.get("turn_id") == turn_id and
                (t := event_clock(e)) is not None and t <= end]
    if len(finishes) != 1 or finishes[0][1]["type"] != "task_complete":
        result["reason"] = "TURN_COMPLETION_NOT_FOUND"
        return result
    i_end = finishes[0][0]
    metadata = [e for e in events[:i_end + 1] if e["type"] == "turn_context"
                and (t := event_clock(e)) is not None and t <= event_clock(events[i_end])]
    if metadata:
        m = metadata[-1].get("payload", {})
        result["model"] = compact(m.get("model"))
        effort = m.get("reasoning_effort")
        result["reasoning_effort"] = effort if effort in SAFE_EFFORT else None
    # Modern rollouts contain one record per model response. Deduplicate IDs
    # globally and reject ambiguous/malformed in-turn records. Never combine
    # these with legacy cumulative notifications; they overlap.
    request_rows = [(i, e) for i, e in enumerate(events) if
                    e["type"] == "token_usage_record"]
    inside_rows = [(i, e) for i, e in request_rows if i_start < i < i_end and
                   (e.get("turn_id") in (None, turn_id))]
    if inside_rows:
        all_ids = {}
        for i, row in request_rows:
            key = row.get("response_id")
            if key is None or row.get("usage") is None:
                if i_start < i < i_end:
                    result["reason"] = "REQUEST_RECORD_INVALID"
                    return result
                continue
            if key in all_ids and all_ids[key] != row["usage"]:
                result["reason"] = "REQUEST_RECORD_CONFLICT"
                return result
            all_ids[key] = row["usage"]
        outside_ids = {row.get("response_id") for i, row in request_rows
                       if not i_start < i < i_end}
        if any(row.get("response_id") in outside_ids for i, row in inside_rows):
            result["reason"] = "REQUEST_ID_CROSSES_TURN_BOUNDARY"
            return result
        in_scope = {}
        for i, row in inside_rows:
            key = row.get("response_id")
            if key is None or row.get("usage") is None:
                result["reason"] = "REQUEST_RECORD_INVALID"
                return result
            if key in in_scope and in_scope[key] != row["usage"]:
                result["reason"] = "REQUEST_RECORD_CONFLICT"
                return result
            in_scope[key] = row["usage"]
        totals = {k: sum(u[k] for u in in_scope.values()) for k in FIELDS}
        if (any(totals[k] > 2**63 - 1 for k in FIELDS) or
                totals["cached_input_tokens"] > totals["input_tokens"]):
            result["reason"] = "REQUEST_RECORD_OVERFLOW"
            return result
        result.update(totals)
        result["status"] = "REPORTED"
        result["accounting"] = "deduplicated_response_records"
        return result
    # Cumulative usage snapshots: subtract a proven pre-turn baseline.
    # Do not sum repeated last_token_usage or treat a session total as a turn.
    previous = [e["total"] for e in events[:i_start] if e["type"] == "token_count"
                and e.get("total") is not None]
    during = [e["total"] for e in events[i_start:i_end + 1]
              if e["type"] == "token_count" and e.get("total") is not None]
    if not previous:
        result["reason"] = "PRE_TURN_CUMULATIVE_BASELINE_MISSING"
        return result
    if not during:
        result["reason"] = "TURN_USAGE_SNAPSHOT_MISSING"
        return result
    series = [previous[-1], *during]
    if any(delta(b, a) is None for a, b in zip(series, series[1:])):
        result["reason"] = "COUNTER_RESET_OR_INCONSISTENCY"
        return result
    usage = delta(during[-1], previous[-1])
    if usage is None:
        result["reason"] = "COUNTER_RESET_OR_INCONSISTENCY"
        return result
    result.update(usage)
    result["status"] = "REPORTED"
    result["accounting"] = "cumulative_boundary_delta"
    return result


def path3(receipt: dict) -> dict:
    usage = receipt.get("codex_usage")
    nums = counters(usage)
    ok = type(usage) is dict and usage.get("status") == "reported" and nums is not None
    return {"source": "swpc_codex_exec_jsonl", "scope": "codex_exec_run",
            "status": "REPORTED" if ok else "NOT_AVAILABLE",
            "model": None, "reasoning_effort": None,
            "session_id": usage.get("session_id") if type(usage) is dict else None,
            **(nums if ok else dict.fromkeys(FIELDS)),
            "github_run_id": receipt.get("github_run_id")}


def compare(desktop: dict, receipt: dict) -> dict:
    swpc = path3(receipt)
    both = desktop.get("status") == "REPORTED" and swpc["status"] == "REPORTED"
    return {"schema": "plasma.codex.benchmark_comparison.v1", "desktop": desktop,
            "path3": swpc,
            "raw_token_difference_desktop_minus_path3":
                {k: desktop[k] - swpc[k] for k in FIELDS} if both else None,
            "like_for_like": False,
            "caveat": "Desktop single turn versus Path 3 codex exec run; model/effort and context not confirmed. Token difference is descriptive, not overhead attribution."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True,
                        help="One explicitly chosen local Codex rollout JSONL; no automatic scanning")
    parser.add_argument("--start", required=True, help="Benchmark UTC start with timezone")
    parser.add_argument("--end", required=True, help="Benchmark UTC end with timezone")
    parser.add_argument("--path3-receipt", type=Path,
                        help="Optional already-downloaded Path 3 JSON receipt")
    parser.add_argument("--output", type=Path,
                        help="Write sanitized comparison JSON (default stdout)")
    args = parser.parse_args()
    try:
        desktop = extract(args.session, clock(args.start), clock(args.end))
        result = compare(desktop, json.loads(args.path3_receipt.read_text())) if args.path3_receipt else desktop
        output = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            if args.output.is_symlink() or args.output.resolve() == args.session.resolve():
                raise ValueError("OUTPUT_PATH_INVALID")
            # Never overwrite existing files or the input rollout.
            with args.output.open("x", encoding="utf-8") as out:
                out.write(output)
        else:
            print(output, end="")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        # Never print raw session content or untrusted parser exception arguments.
        print("BENCHMARK_USAGE_ERROR: " + (str(exc) if str(exc) in {
            "BENCHMARK_WINDOW_INVALID", "SESSION_FILE_INVALID", "OUTPUT_PATH_INVALID",
            "TELEMETRY_EVENT_LIMIT", "Timestamp requires an explicit UTC offset"}
            else "INVALID_OR_INACCESSIBLE_INPUT"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
