"""Node-memory-capacity sensitivity experiment on the final 200-node setup."""

import csv
import json
from dataclasses import replace
from pathlib import Path
import statistics

from experiments.collaborative_routing import DEFAULT_CONFIG
from examples.node_scaling_five_algorithms import (
    ALGORITHMS,
    METRICS,
    run_legacy_baselines,
    run_joint_no_tree,
    run_joint_tree,
    run_spfd_variants,
)
from examples.request_scaling_200_nodes_accelerated import experiment_config as base_config


NODE_COUNT = 200
REQUEST_COUNT = 40
MEMORY_CAPACITIES = tuple(round(50 + (200 - 50) * i / 9) for i in range(10))
SEEDS = tuple(range(20260812, 20260912))
RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "memory_capacity_scaling_200_nodes_with_baselines_100seeds_raw.csv"
SUMMARY = RESULTS / "memory_capacity_scaling_200_nodes_with_baselines_100seeds_summary.csv"
COMPARISON = RESULTS / "memory_capacity_scaling_200_nodes_with_baselines_100seeds_comparison.csv"
JSON_OUTPUT = RESULTS / "memory_capacity_scaling_200_nodes_with_baselines_100seeds.json"
REPORT = RESULTS / "memory_capacity_scaling_200_nodes_with_baselines_100seeds_report.md"


def experiment_config(memory_capacity, seed):
    baseline = base_config(REQUEST_COUNT, seed)
    config = replace(
        baseline,
        memory=replace(
            baseline.memory,
            capacity_min=memory_capacity,
            capacity_max=memory_capacity,
        ),
    )
    config.validate()
    return config


def add_memory_capacity(row, memory_capacity):
    output = {"memory_capacity": memory_capacity}
    output.update(row)
    return output


def summarize(rows):
    output = []
    for memory_capacity in MEMORY_CAPACITIES:
        for algorithm in ALGORITHMS:
            group = [
                row for row in rows
                if row["memory_capacity"] == memory_capacity
                and row["algorithm"] == algorithm
            ]
            item = {
                "node_count": NODE_COUNT,
                "request_count": REQUEST_COUNT,
                "memory_capacity": memory_capacity,
                "algorithm": algorithm,
                "repetitions": len(group),
            }
            for metric in METRICS:
                values = [float(row[metric]) for row in group]
                item[f"{metric}_mean"] = statistics.fmean(values)
                item[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
            output.append(item)
    return output


def comparisons(summary):
    pairs = (
        ("Joint_no_tree", "SPFD_no_tree"),
        ("Joint_optimized_tree_fast", "SPFD_optimized_tree"),
        ("Joint_optimized_tree_fast", "SPFD_no_tree"),
        ("SPFD_optimized_tree", "SPFD_no_tree"),
        ("Joint_optimized_tree_fast", "Joint_no_tree"),
    )
    metrics = (
        "total_edr", "minimum_request_edr", "average_request_edr",
        "jain_fairness", "demand_satisfaction_ratio",
        "request_acceptance_rate", "runtime_seconds",
    )
    output = []
    for memory_capacity in MEMORY_CAPACITIES:
        by_algorithm = {
            row["algorithm"]: row
            for row in summary
            if row["memory_capacity"] == memory_capacity
        }
        for algorithm, baseline in pairs:
            item = {
                "memory_capacity": memory_capacity,
                "comparison": f"{algorithm}_vs_{baseline}",
            }
            for metric in metrics:
                new = float(by_algorithm[algorithm][f"{metric}_mean"])
                old = float(by_algorithm[baseline][f"{metric}_mean"])
                item[f"{metric}_change_percent"] = 100.0 * (new / old - 1.0) if old else 0.0
            output.append(item)
    return output


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(summary, comparison):
    lines = [
        "# Node-memory-capacity sensitivity",
        "",
        f"- Nodes: {NODE_COUNT}",
        f"- Requests: {REQUEST_COUNT}",
        f"- Capacities: {MEMORY_CAPACITIES[0]}--{MEMORY_CAPACITIES[-1]} slots, 10 points",
        f"- Seeds: {len(SEEDS)} ({SEEDS[0]}--{SEEDS[-1]})",
        "- Unit memory processing rate: 50 pairs/s/slot",
        "- Node memory bandwidth: capacity x 50 pairs/s",
        "",
        "## Total EDR means",
        "",
        "| Capacity | SPFD no tree | SPFD tree | Joint no tree | Joint tree fast |",
        "|---:|---:|---:|---:|---:|",
    ]
    for capacity in MEMORY_CAPACITIES:
        means = {
            row["algorithm"]: row["total_edr_mean"]
            for row in summary if row["memory_capacity"] == capacity
        }
        lines.append(
            f"| {capacity} | {means['SPFD_no_tree']:.3f} | "
            f"{means['SPFD_optimized_tree']:.3f} | "
            f"{means['Joint_no_tree']:.3f} | "
            f"{means['Joint_optimized_tree_fast']:.3f} |"
        )
    lines.extend(["", "## Joint tree fast vs SPFD no tree", "", "| Capacity | Total EDR change | Minimum EDR change | Fairness change |", "|---:|---:|---:|---:|"])
    for row in comparison:
        if row["comparison"] == "Joint_optimized_tree_fast_vs_SPFD_no_tree":
            lines.append(
                f"| {row['memory_capacity']} | {row['total_edr_change_percent']:.2f}% | "
                f"{row['minimum_request_edr_change_percent']:.2f}% | "
                f"{row['jain_fairness_change_percent']:.2f}% |"
            )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    rows = []
    if RAW.exists():
        with RAW.open(encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                converted = dict(row)
                converted["memory_capacity"] = int(row["memory_capacity"])
                converted["node_count"] = int(row["node_count"])
                converted["request_count"] = int(row["request_count"])
                converted["seed"] = int(row["seed"])
                for field in METRICS:
                    converted[field] = float(row[field])
                rows.append(converted)

    completed = {
        (row["memory_capacity"], row["seed"])
        for row in rows
        if sum(
            item["memory_capacity"] == row["memory_capacity"]
            and item["seed"] == row["seed"]
            for item in rows
        ) == len(ALGORITHMS)
    }
    total = len(MEMORY_CAPACITIES) * len(SEEDS)
    for index, memory_capacity in enumerate(MEMORY_CAPACITIES, start=1):
        for seed in SEEDS:
            if (memory_capacity, seed) in completed:
                continue
            config = experiment_config(memory_capacity, seed)
            current = [
                add_memory_capacity(row, memory_capacity)
                for row in run_legacy_baselines(config) + run_spfd_variants(config)
            ]
            current.append(add_memory_capacity(run_joint_no_tree(config), memory_capacity))
            current.append(add_memory_capacity(run_joint_tree(config, fast=True), memory_capacity))
            rows.extend(current)
            write_csv(RAW, rows)
            print(json.dumps({
                "completed": len(completed) + 1,
                "total": total,
                "memory_capacity": memory_capacity,
                "seed": seed,
                "total_edr": {
                    row["algorithm"]: round(row["total_edr"], 3)
                    for row in current
                },
            }, ensure_ascii=False), flush=True)
            completed.add((memory_capacity, seed))

    summary = summarize(rows)
    comparison = comparisons(summary)
    write_csv(SUMMARY, summary)
    write_csv(COMPARISON, comparison)
    JSON_OUTPUT.write_text(json.dumps({"raw": rows, "summary": summary, "comparisons": comparison}, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(summary, comparison)
    print(json.dumps({"raw": str(RAW), "summary": str(SUMMARY), "comparison": str(COMPARISON), "report": str(REPORT)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
