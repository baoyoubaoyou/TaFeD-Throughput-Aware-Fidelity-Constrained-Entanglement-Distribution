"""Resume 15/20/25/30-node 100-group benchmark quietly from saved CSV."""

import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import milp_30n4r_10groups_with_baselines as benchmark
from milp_node_points_15_20_25_30_100groups import (
    GROUPS_PER_NODE,
    NODE_POINTS,
    RAW_CSV,
    REQUEST_COUNT,
    SKIPPED_CSV,
    make_config,
    write_outputs,
)


LOG_JSONL = RAW_CSV.with_name(
    "milp_node_points_15_20_25_30_100groups_progress.jsonl"
)


def read_rows():
    if not RAW_CSV.exists():
        return []
    return list(csv.DictReader(RAW_CSV.open(encoding="utf-8-sig")))


def read_skipped():
    if not SKIPPED_CSV.exists():
        return []
    return list(csv.DictReader(SKIPPED_CSV.open(encoding="utf-8-sig")))


def completed_groups(rows, node_count):
    return {
        int(row["group"])
        for row in rows
        if int(row["nodes"]) == node_count and row["algorithm"] == "MILP"
    }


def max_used_seed(rows, skipped, node_count, start_seed):
    seeds = [
        int(row["seed"])
        for row in rows
        if int(row["nodes"]) == node_count
    ]
    seeds.extend(
        int(row["seed"])
        for row in skipped
        if int(row["nodes"]) == node_count
    )
    return max(seeds, default=start_seed - 1)


def append_log(payload):
    with LOG_JSONL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main():
    rows = read_rows()
    skipped = read_skipped()
    for point in NODE_POINTS:
        node_count = point["node_count"]
        done = completed_groups(rows, node_count)
        seed = max_used_seed(rows, skipped, node_count, point["start_seed"]) + 1
        while len(done) < GROUPS_PER_NODE:
            group_index = min(
                group for group in range(1, GROUPS_PER_NODE + 1)
                if group not in done
            )

            def config_for_seed(
                trial_seed,
                node_count=node_count,
                alpha=point["alpha"],
                beta=point["beta"],
            ):
                return make_config(trial_seed, node_count, alpha, beta)

            old_make_config = benchmark.make_config
            benchmark.make_config = config_for_seed
            try:
                current = benchmark.run_group(group_index, seed)
            except RuntimeError as error:
                skipped.append({
                    "nodes": node_count,
                    "group": group_index,
                    "seed": seed,
                    "reason": str(error),
                })
                write_outputs(rows, skipped)
                append_log({
                    "event": "skip",
                    "nodes": node_count,
                    "group": group_index,
                    "seed": seed,
                    "reason": str(error),
                })
                seed += 1
                continue
            finally:
                benchmark.make_config = old_make_config

            rows.extend(current)
            done.add(group_index)
            write_outputs(rows, skipped)
            milp = next(row for row in current if row["algorithm"] == "MILP")
            ours = next(
                row for row in current
                if row["algorithm"] == "Ours_optimized_tree"
            )
            append_log({
                "event": "complete_group",
                "nodes": node_count,
                "group": group_index,
                "seed": seed,
                "completed_for_node": len(done),
                "ours_total_edr": ours["total_edr"],
                "milp_total_edr": milp["total_edr"],
                "gap_percent": (
                    100.0 * (milp["total_edr"] - ours["total_edr"])
                    / milp["total_edr"]
                    if milp["total_edr"] > 0 else 0.0
                ),
                "milp_runtime_seconds": milp["runtime_seconds"],
            })
            seed += 1

    payload = write_outputs(rows, skipped)
    append_log({
        "event": "finished",
        "summary": payload["summary"],
        "ours_vs_milp": payload["ours_vs_milp"],
    })


if __name__ == "__main__":
    main()
