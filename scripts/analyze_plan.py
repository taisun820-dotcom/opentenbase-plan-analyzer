#!/usr/bin/env python3
"""Summarize and compare one PostgreSQL-compatible EXPLAIN JSON per input."""

import argparse
import json
import math
import sys
from pathlib import Path


METRICS = {
    "Plan Rows": "estimated_rows",
    "Actual Rows": "actual_rows_per_loop",
    "Actual Loops": "actual_loops",
    "Rows Removed by Filter": "removed_by_filter_per_loop",
    "Rows Removed by Index Recheck": "removed_by_recheck_per_loop",
    "Actual Total Time": "actual_total_ms_per_loop",
    "Shared Hit Blocks": "shared_hit_blocks",
    "Shared Read Blocks": "shared_read_blocks",
    "Temp Read Blocks": "temp_read_blocks",
    "Temp Written Blocks": "temp_written_blocks",
}
DETAILS = {
    "Relation Name": "relation",
    "Index Name": "index",
    "Index Cond": "index_cond",
    "Filter": "filter",
    "Recheck Cond": "recheck_cond",
}
REMOTE_NODES = {"Remote Fast Query Execution", "Remote Query", "Remote Subquery Scan"}


def number_fields(source, fields):
    result = {}
    for key, name in fields.items():
        if key in source:
            value = source[key]
            if type(value) not in (int, float) or value < 0 or (
                isinstance(value, float) and not math.isfinite(value)
            ):
                raise ValueError(f"{key} must be a finite non-negative number")
            result[name] = value
    return result


def walk_plan(plan, path="0"):
    if not isinstance(plan, dict):
        raise ValueError(f"invalid plan node at {path}")
    kind = plan.get("Node Type")
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError(f"missing Node Type at {path}")
    children = plan.get("Plans", [])
    if not isinstance(children, list):
        raise ValueError(f"Plans must be an array at {path}")
    node = {"path": path, "node_type": kind}
    node.update(number_fields(plan, METRICS))
    node.update({name: plan[key] for key, name in DETAILS.items() if isinstance(plan.get(key), str)})
    remote_targets = plan.get("Node/s")
    if isinstance(remote_targets, str):
        node["remote_targets"] = [item.strip() for item in remote_targets.split(",") if item.strip()]
    yield node
    for index, child in enumerate(children):
        yield from walk_plan(child, f"{path}.{index}")


def summarize(explain):
    if isinstance(explain, list) and len(explain) == 1:
        explain = explain[0]
    if not isinstance(explain, dict) or "Plan" not in explain:
        raise ValueError("expected one EXPLAIN JSON object with Plan, optionally in a one-item array")

    nodes = list(walk_plan(explain["Plan"]))
    parents = {node["path"].rpartition(".")[0] for node in nodes[1:]}
    findings = []
    for node in nodes:
        path = node["path"]
        if node["node_type"] in REMOTE_NODES and path not in parents:
            findings.append({"code": "remote_plan_not_expanded", "path": path})
        if node["node_type"] == "Seq Scan" and node.get("actual_loops") != 0:
            findings.append({"code": "sequential_scan", "path": path})

    return {
        "analyzed": "actual_loops" in nodes[0],
        **number_fields(explain, {"Planning Time": "planning_ms", "Execution Time": "execution_ms"}),
        "nodes": nodes,
        "findings": findings,
    }


def load_plans(specs):
    reports = {}
    for spec in specs:
        label, separator, filename = spec.partition("=")
        if not separator or not label.strip() or not filename.strip():
            raise ValueError("expected LABEL=FILE")
        if label in reports:
            raise ValueError(f"duplicate label: {label}")
        try:
            reports[label] = summarize(json.loads(Path(filename).read_text(encoding="utf-8-sig")))
        except (OSError, ValueError, RecursionError) as exc:
            raise ValueError(f"{label}: {exc}") from exc
    return reports


def compare(before, after):
    if before.keys() != after.keys():
        raise ValueError("before and after must have the same labels")
    comparisons = {}
    for label, left in before.items():
        right = after[label]
        left_root, right_root = left["nodes"][0], right["nodes"][0]
        root_fields = METRICS.values()
        deltas = {
            key: right_root[key] - left_root[key]
            for key in root_fields
            if key in left_root and key in right_root
        }
        # A per-loop difference is not meaningful when one root did not execute.
        if left_root.get("actual_loops") == 0 or right_root.get("actual_loops") == 0:
            deltas = {key: value for key, value in deltas.items() if not key.endswith("_per_loop")}
        result = {"before": left, "after": right, "root_delta": deltas}
        if "execution_ms" in left and "execution_ms" in right:
            result["execution_ms_delta"] = right["execution_ms"] - left["execution_ms"]
        comparisons[label] = result
    return comparisons


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="summarize one or more labeled plans")
    analyze.add_argument("--plan", action="append", metavar="LABEL=FILE", required=True)
    compare_command = commands.add_parser("compare", help="compare plans by matching labels")
    for side in ("before", "after"):
        compare_command.add_argument(f"--{side}", action="append", metavar="LABEL=FILE", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "analyze":
            result = {"plans": load_plans(args.plan)}
        else:
            result = {"comparisons": compare(load_plans(args.before), load_plans(args.after))}
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
