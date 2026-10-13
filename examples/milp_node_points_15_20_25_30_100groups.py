"""Run 15/20/25/30-node strict-aligned MILP benchmarks, 100 groups each."""

import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import milp_30n4r_10groups_with_baselines as benchmark
from examples.milp_strict_aligned_moderate_normal import experiment_config


OUTPUT_DIR = Path(__file__).resolve().parent / "results"
RAW_CSV = OUTPUT_DIR / "milp_node_points_15_20_25_30_100groups_raw.csv"
SUMMARY_CSV = OUTPUT_DIR / "milp_node_points_15_20_25_30_100groups_summary.csv"
JSON_PATH = OUTPUT_DIR / "milp_node_points_15_20_25_30_100groups.json"
SKIPPED_CSV = OUTPUT_DIR / "milp_node_points_15_20_25_30_100groups_skipped.csv"

NODE_POINTS = (
    {"node_count": 15, "alpha": 0.55, "beta": 0.30, "start_seed": 20261100},
    {"node_count": 20, "alpha": 0.50, "beta": 0.25, "start_seed": 20261200},
    {"node_count": 25, "alpha": 0.50, "beta": 0.25, "start_seed": 20261300},
    {"node_count": 30, "alpha": 0.50, "beta": 0.25, "start_seed": 20261400},
)
REQUEST_COUNT = 4
GROUPS_PER_NODE = 100


def make_config(seed: int, node_count: int, alpha: float, beta: float):
    return experiment_config(
        seed=seed,
        node_count=node_count,
        request_count=REQUEST_COUNT,
        alpha=alpha,
        beta=beta,
    )


def summarize(rows):
    output = []
    node_counts = sorted({int(row["nodes"]) for row in rows})
    algorithms = sorted({row["algorithm"] for row in rows})
    for node_count in node_counts:
        for algorithm in algorithms:
            group = [
                row for row in rows
                if int(row["nodes"]) == node_count
                and row["algorithm"] == algorithm
            ]
            if not group:
                continue
            output.append({
                "nodes": node_count,
                "requests": REQUEST_COUNT,
                "algorithm": algorithm,
                "runs": len(group),
                "avg_quantum_links": (
                    sum(float(row["quantum_links"]) for row in group) / len(group)
                ),
                "avg_total_edr": (
                    sum(float(row["total_edr"]) for row in group) / len(group)
                ),
                "avg_min_satisfaction": (
                    sum(float(row["min_satisfaction"]) for row in group) / len(group)
                ),
                "avg_demand_satisfaction_ratio": (
                    sum(float(row["demand_satisfaction_ratio"]) for row in group)
                    / len(group)
                ),
                "avg_runtime_seconds": (
                    sum(float(row["runtime_seconds"]) for row in group) / len(group)
                ),
            })
    return output


def summarize_ours_vs_milp(rows):
    output = []
    keys = sorted({
        (int(row["nodes"]), int(row["group"]))
        for row in rows
    })
    grouped = {}
    for row in rows:
        grouped.setdefault(
            (int(row["nodes"]), int(row["group"])),
            {},
        )[row["algorithm"]] = row
    for node_count in sorted({key[0] for key in keys}):
        gaps = []
        ratios = []
        for key in keys:
            if key[0] != node_count:
                continue
            pair = grouped[key]
            if "MILP" not in pair or "Ours_optimized_tree" not in pair:
                continue
            milp = float(pair["MILP"]["total_edr"])
            ours = float(pair["Ours_optimized_tree"]["total_edr"])
            if milp <= 0.0:
                continue
            gaps.append(100.0 * (milp - ours) / milp)
            ratios.append(ours / milp)
        if gaps:
            ordered = sorted(gaps)
            output.append({
                "nodes": node_count,
                "ours_vs_milp_runs": len(gaps),
                "avg_gap_percent": sum(gaps) / len(gaps),
                "median_gap_percent": (
                    ordered[len(ordered) // 2]
                    if len(ordered) % 2
                    else 0.5 * (
                        ordered[len(ordered) // 2 - 1]
                        + ordered[len(ordered) // 2]
                    )
                ),
                "min_gap_percent": min(gaps),
                "max_gap_percent": max(gaps),
                "avg_ours_over_milp": sum(ratios) / len(ratios),
            })
    return output


def write_outputs(rows, skipped):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if rows:
        with RAW_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        summary = summarize(rows)
        with SUMMARY_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()))
            writer.writeheader()
            writer.writerows(summary)
    else:
        summary = []

    if skipped:
        with SKIPPED_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(skipped[0].keys()))
            writer.writeheader()
            writer.writerows(skipped)

    payload = {
        "summary": summary,
        "ours_vs_milp": summarize_ours_vs_milp(rows),
        "rows": rows,
        "skipped": skipped,
    }
    JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def main():
    rows = []
    skipped = []
    for point in NODE_POINTS:
        node_count = point["node_count"]
        completed = 0
        seed = point["start_seed"]
        while completed < GROUPS_PER_NODE:
            group_index = completed + 1

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
                seed += 1
                continue
            finally:
                benchmark.make_config = old_make_config

            rows.extend(current)
            completed += 1
            write_outputs(rows, skipped)
            milp = next(row for row in current if row["algorithm"] == "MILP")
            ours = next(
                row for row in current
                if row["algorithm"] == "Ours_optimized_tree"
            )
            print(json.dumps({
                "nodes": node_count,
                "group": group_index,
                "seed": seed,
                "ours_total_edr": ours["total_edr"],
                "milp_total_edr": milp["total_edr"],
                "gap_percent": (
                    100.0 * (milp["total_edr"] - ours["total_edr"])
                    / milp["total_edr"]
                    if milp["total_edr"] > 0 else 0.0
                ),
                "milp_runtime_seconds": milp["runtime_seconds"],
            }, ensure_ascii=False), flush=True)
            seed += 1

    payload = write_outputs(rows, skipped)
    print(json.dumps({
        "summary": payload["summary"],
        "ours_vs_milp": payload["ours_vs_milp"],
        "raw_csv": str(RAW_CSV),
        "summary_csv": str(SUMMARY_CSV),
        "json": str(JSON_PATH),
        "skipped_csv": str(SKIPPED_CSV) if skipped else "",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
