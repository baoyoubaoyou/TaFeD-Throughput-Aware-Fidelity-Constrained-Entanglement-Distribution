"""Link-generation-capacity sensitivity on the final 200-node setup."""

import csv
import json
from dataclasses import replace
from pathlib import Path
import statistics

from examples.node_scaling_five_algorithms import (
    ALGORITHMS, METRICS, run_joint_no_tree, run_joint_tree, run_legacy_baselines, run_spfd_variants,
)
from examples.request_scaling_200_nodes_accelerated import experiment_config as base_config

CAPACITIES = (5_000, 9_000, 13_000, 17_000, 21_000, 25_000, 29_000, 33_000, 37_000, 40_000)
SEEDS = tuple(range(20260812, 20260912))
RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "generation_capacity_scaling_200_nodes_with_baselines_100seeds_raw.csv"
SUMMARY = RESULTS / "generation_capacity_scaling_200_nodes_with_baselines_100seeds_summary.csv"
COMPARISON = RESULTS / "generation_capacity_scaling_200_nodes_with_baselines_100seeds_comparison.csv"
REPORT = RESULTS / "generation_capacity_scaling_200_nodes_with_baselines_100seeds_report.md"


def config_for(value, seed):
    config = base_config(40, seed)
    config = replace(config, links=replace(config.links, base_generation_capacity=value))
    config.validate()
    return config


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows):
    output = []
    for value in CAPACITIES:
        for algorithm in ALGORITHMS:
            group = [r for r in rows if r["base_generation_capacity"] == value and r["algorithm"] == algorithm]
            item = {"base_generation_capacity": value, "algorithm": algorithm, "repetitions": len(group)}
            for metric in METRICS:
                values = [float(r[metric]) for r in group]
                item[f"{metric}_mean"] = statistics.fmean(values)
                item[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
            output.append(item)
    return output


def compare(summary):
    pairs = (("Joint_no_tree", "SPFD_no_tree"), ("Joint_optimized_tree_fast", "SPFD_optimized_tree"), ("Joint_optimized_tree_fast", "SPFD_no_tree"))
    metrics = ("total_edr", "minimum_request_edr", "jain_fairness", "demand_satisfaction_ratio", "request_acceptance_rate")
    output = []
    for value in CAPACITIES:
        table = {r["algorithm"]: r for r in summary if r["base_generation_capacity"] == value}
        for algorithm, baseline in pairs:
            item = {"base_generation_capacity": value, "comparison": f"{algorithm}_vs_{baseline}"}
            for metric in metrics:
                new = float(table[algorithm][f"{metric}_mean"])
                old = float(table[baseline][f"{metric}_mean"])
                item[f"{metric}_change_percent"] = 100 * (new / old - 1) if old else 0.0
            output.append(item)
    return output


def main():
    rows = []
    if RAW.exists():
        with RAW.open(encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            row["base_generation_capacity"] = int(row["base_generation_capacity"])
            row["seed"] = int(row["seed"])
            for metric in METRICS:
                row[metric] = float(row[metric])
    completed = {
        (r["base_generation_capacity"], r["seed"])
        for r in rows
        if sum(
            item["base_generation_capacity"] == r["base_generation_capacity"]
            and item["seed"] == r["seed"]
            for item in rows
        ) == len(ALGORITHMS)
    }
    for value in CAPACITIES:
        for seed in SEEDS:
            if (value, seed) in completed:
                continue
            config = config_for(value, seed)
            current = run_legacy_baselines(config)
            current.extend(run_spfd_variants(config))
            current.append(run_joint_no_tree(config))
            current.append(run_joint_tree(config, fast=True))
            for row in current:
                row["base_generation_capacity"] = value
            rows.extend(current)
            write_csv(RAW, rows)
            print(json.dumps({"capacity": value, "seed": seed, "total_edr": {r["algorithm"]: round(r["total_edr"], 3) for r in current}}, ensure_ascii=False), flush=True)
    summary = summarize(rows)
    comparison = compare(summary)
    write_csv(SUMMARY, summary)
    write_csv(COMPARISON, comparison)
    REPORT.write_text(json.dumps({"summary": summary, "comparison": comparison}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"raw": str(RAW), "summary": str(SUMMARY), "comparison": str(COMPARISON), "report": str(REPORT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
