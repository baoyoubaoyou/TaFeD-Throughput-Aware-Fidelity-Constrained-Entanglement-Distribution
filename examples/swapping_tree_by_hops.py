"""Measure optimal swapping-tree gains separately for each path length."""

import csv
from dataclasses import replace
import json
from pathlib import Path
import random
import statistics

from experiments.collaborative_routing import (
    DEFAULT_CONFIG,
    allocate_fixed_swapping_tree_throughput,
    build_scenario,
    optimize_spfd_swapping_trees,
    optimize_stage_one_swapping_trees,
    run_spfd_two_stage,
    run_stage_one,
)


SEEDS = (20260812, 20260813, 20260814, 20260815, 20260816)
REQUEST_COUNT = 20
OUTPUT_DIRECTORY = Path(__file__).resolve().parents[1] / "results"
RAW_OUTPUT = OUTPUT_DIRECTORY / "swapping_tree_by_hops_raw.csv"
SUMMARY_OUTPUT = OUTPUT_DIRECTORY / "swapping_tree_by_hops_summary.csv"


def hop_quotas(seed):
    rng = random.Random(seed * 1009 + REQUEST_COUNT)
    counts = {3: 1, 4: 1, 5: 1, 6: 1}
    for hop_count in rng.choices(
        population=(3, 4, 5, 6),
        weights=(0.30, 0.30, 0.25, 0.15),
        k=REQUEST_COUNT - 4,
    ):
        counts[hop_count] += 1
    return tuple((hop, counts[hop]) for hop in (3, 4, 5, 6))


def config_for_seed(seed):
    return replace(
        DEFAULT_CONFIG,
        seed=seed,
        requests=replace(DEFAULT_CONFIG.requests, count=REQUEST_COUNT),
        routing=replace(
            DEFAULT_CONFIG.routing,
            shortest_hop_quotas=hop_quotas(seed),
        ),
    )


def collect_rows(seed, algorithm, quality, configuration, optimized):
    fixed_trees, fixed = allocate_fixed_swapping_tree_throughput(
        quality,
        configuration,
    )
    selected = optimized.selected_record
    rows = []
    for request_plan in quality.request_plans:
        plan = request_plan.selected_plan
        if plan is None:
            continue
        key = id(request_plan.request)
        fixed_rate = fixed.request_allocations[key].allocated_rate
        optimized_rate = selected.throughput_result.request_allocations[key].allocated_rate
        fixed_cost = sum(fixed_trees[key].raw_costs.values())
        optimized_cost = sum(selected.trees[key].raw_costs.values())
        rows.append({
            "seed": seed,
            "algorithm": algorithm,
            "hop_count": plan.hop_count,
            "fixed_tree_edr": fixed_rate,
            "optimized_tree_edr": optimized_rate,
            "edr_change": optimized_rate - fixed_rate,
            "edr_gain_percent": (
                100.0 * (optimized_rate - fixed_rate) / fixed_rate
                if fixed_rate > 0 else 0.0
            ),
            "fixed_tree_raw_cost": fixed_cost,
            "optimized_tree_raw_cost": optimized_cost,
            "raw_cost_reduction_percent": (
                100.0 * (fixed_cost - optimized_cost) / fixed_cost
                if fixed_cost > 0 else 0.0
            ),
        })
    return rows


def summarize(rows):
    summaries = []
    for algorithm in ("SPFD", "Joint"):
        for hop_count in (3, 4, 5, 6):
            group = [
                row for row in rows
                if row["algorithm"] == algorithm
                and row["hop_count"] == hop_count
            ]
            summaries.append({
                "algorithm": algorithm,
                "hop_count": hop_count,
                "request_samples": len(group),
                "fixed_tree_edr_mean": statistics.mean(
                    row["fixed_tree_edr"] for row in group
                ),
                "optimized_tree_edr_mean": statistics.mean(
                    row["optimized_tree_edr"] for row in group
                ),
                "edr_gain_percent_from_group_means": 100.0 * (
                    statistics.mean(row["optimized_tree_edr"] for row in group)
                    / statistics.mean(row["fixed_tree_edr"] for row in group) - 1.0
                ),
                "mean_per_request_edr_gain_percent": statistics.mean(
                    row["edr_gain_percent"] for row in group
                ),
                "mean_raw_cost_reduction_percent": statistics.mean(
                    row["raw_cost_reduction_percent"] for row in group
                ),
            })
    return summaries


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = []
    for index, seed in enumerate(SEEDS, start=1):
        config = config_for_seed(seed)

        spfd_scenario = build_scenario(config)
        spfd = run_spfd_two_stage(spfd_scenario)
        spfd_optimized = optimize_spfd_swapping_trees(
            spfd,
            mutate_requests=False,
        )
        rows.extend(collect_rows(
            seed,
            "SPFD",
            spfd.quality_result,
            spfd.configuration_result,
            spfd_optimized,
        ))

        joint_scenario = build_scenario(config)
        joint = run_stage_one(joint_scenario)
        joint_optimized = optimize_stage_one_swapping_trees(
            joint,
            mutate_requests=False,
        )
        selected = joint.selected_record
        rows.extend(collect_rows(
            seed,
            "Joint",
            selected.quality_result,
            selected.configuration_result,
            joint_optimized,
        ))
        print(json.dumps({
            "completed": index,
            "seed": seed,
            "hop_quotas": hop_quotas(seed),
        }, ensure_ascii=False), flush=True)

    summaries = summarize(rows)
    write_csv(RAW_OUTPUT, rows)
    write_csv(SUMMARY_OUTPUT, summaries)
    print(json.dumps({
        "raw_output": str(RAW_OUTPUT),
        "summary_output": str(SUMMARY_OUTPUT),
        "summaries": summaries,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
