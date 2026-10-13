"""Evaluate the three necessary bottleneck-aware optimizations without tree DP."""

import csv
from dataclasses import replace
import json
from pathlib import Path
import random
import statistics
from time import perf_counter

from experiments.collaborative_routing import (
    DEFAULT_CONFIG,
    allocate_fixed_swapping_tree_throughput,
    build_scenario,
    run_bottleneck_optimized_stage_one,
    run_spfd_two_stage,
)


REQUEST_COUNTS = (10, 20, 30, 40)
SEEDS = (20260812, 20260813, 20260814, 20260815, 20260816)
RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW_OUTPUT = RESULTS / "bottleneck_optimization_raw.csv"
SUMMARY_OUTPUT = RESULTS / "bottleneck_optimization_summary.csv"
COMPARISON_OUTPUT = RESULTS / "bottleneck_optimization_comparison.csv"
JSON_OUTPUT = RESULTS / "bottleneck_optimization.json"


def hop_quotas(request_count, seed):
    rng = random.Random(seed * 1009 + request_count)
    counts = {3: 1, 4: 1, 5: 1, 6: 1}
    for hop in rng.choices(
        (3, 4, 5, 6), weights=(0.30, 0.30, 0.25, 0.15),
        k=request_count - 4,
    ):
        counts[hop] += 1
    return tuple((hop, counts[hop]) for hop in (3, 4, 5, 6))


def config_for(request_count, seed):
    return replace(
        DEFAULT_CONFIG,
        seed=seed,
        requests=replace(DEFAULT_CONFIG.requests, count=request_count),
        routing=replace(
            DEFAULT_CONFIG.routing,
            shortest_hop_quotas=hop_quotas(request_count, seed),
        ),
    )


def jain(values):
    values = list(values)
    denominator = len(values) * sum(value * value for value in values)
    return sum(values) ** 2 / denominator if denominator > 0 else 0.0


def metrics(request_count, seed, algorithm, throughput, configuration, runtime,
            iterations, bottleneck_links=0):
    rates = [item.allocated_rate for item in throughput.request_allocations.values()]
    return {
        "node_count": 100,
        "request_count": request_count,
        "seed": seed,
        "algorithm": algorithm,
        "tree_mode": "fixed_sequential",
        "total_edr": throughput.total_edr,
        "minimum_request_edr": throughput.minimum_request_edr,
        "average_request_edr": throughput.average_request_edr,
        "request_edr_jain_fairness": jain(rates),
        "demand_satisfaction_ratio": throughput.demand_satisfaction_ratio,
        "request_acceptance_rate": throughput.request_acceptance_rate,
        "average_link_utilization": throughput.average_link_utilization,
        "maximum_link_utilization": throughput.maximum_link_utilization,
        "average_purification_rounds": configuration.average_purification_rounds,
        "active_links": configuration.active_links,
        "infeasible_links": configuration.infeasible_links,
        "algorithm_iterations": iterations,
        "searched_bottleneck_links": bottleneck_links,
        "runtime_seconds": runtime,
        "hop_quotas": json.dumps(hop_quotas(request_count, seed)),
    }


def run_scenario(request_count, seed):
    config = config_for(request_count, seed)
    started = perf_counter()
    spfd = run_spfd_two_stage(build_scenario(config), mutate_requests=False)
    spfd_trees, spfd_throughput = allocate_fixed_swapping_tree_throughput(
        spfd.quality_result, spfd.configuration_result, mutate_requests=False
    )
    spfd_runtime = perf_counter() - started

    optimized = run_bottleneck_optimized_stage_one(
        build_scenario(config), mutate_requests=False
    )
    base = optimized.records[0]
    selected = optimized.selected_record
    return [
        metrics(
            request_count, seed, "SPFD", spfd_throughput,
            spfd.configuration_result, spfd_runtime, 1,
        ),
        metrics(
            request_count, seed, "Joint_v1", base.throughput_result,
            base.configuration_result, optimized.base_runtime_seconds,
            optimized.base_stage_one_result.iterations,
        ),
        metrics(
            request_count, seed, "Joint_bottleneck", selected.throughput_result,
            selected.configuration_result,
            optimized.base_runtime_seconds + optimized.refinement_runtime_seconds,
            optimized.refinement_iterations,
            len(selected.bottleneck_channels),
        ),
    ]


METRICS = (
    "total_edr", "minimum_request_edr", "average_request_edr",
    "request_edr_jain_fairness", "demand_satisfaction_ratio",
    "request_acceptance_rate", "average_link_utilization",
    "maximum_link_utilization", "average_purification_rounds",
    "runtime_seconds", "algorithm_iterations", "searched_bottleneck_links",
)


def summarize(rows):
    output = []
    for request_count in REQUEST_COUNTS:
        for algorithm in ("SPFD", "Joint_v1", "Joint_bottleneck"):
            group = [
                row for row in rows
                if row["request_count"] == request_count
                and row["algorithm"] == algorithm
            ]
            item = {
                "request_count": request_count,
                "algorithm": algorithm,
                "repetitions": len(group),
                "infeasible_runs": sum(row["infeasible_links"] > 0 for row in group),
            }
            for name in METRICS:
                values = [float(row[name]) for row in group]
                item[f"{name}_mean"] = statistics.fmean(values)
                item[f"{name}_std"] = statistics.stdev(values)
            output.append(item)
    return output


def comparisons(rows):
    output = []
    for request_count in REQUEST_COUNTS:
        means = {}
        for algorithm in ("SPFD", "Joint_v1", "Joint_bottleneck"):
            group = [
                row for row in rows
                if row["request_count"] == request_count
                and row["algorithm"] == algorithm
            ]
            means[algorithm] = {
                name: statistics.fmean(float(row[name]) for row in group)
                for name in METRICS
            }
        for baseline in ("Joint_v1", "SPFD"):
            item = {
                "request_count": request_count,
                "comparison": f"Joint_bottleneck_vs_{baseline}",
            }
            for name in (
                "total_edr", "minimum_request_edr",
                "request_edr_jain_fairness", "demand_satisfaction_ratio",
                "request_acceptance_rate", "runtime_seconds",
            ):
                old = means[baseline][name]
                new = means["Joint_bottleneck"][name]
                item[f"{name}_change_percent"] = (
                    100.0 * (new / old - 1.0) if old else 0.0
                )
            output.append(item)
    return output


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = []
    completed = 0
    total = len(REQUEST_COUNTS) * len(SEEDS)
    for request_count in REQUEST_COUNTS:
        for seed in SEEDS:
            scenario_rows = run_scenario(request_count, seed)
            rows.extend(scenario_rows)
            completed += 1
            new = scenario_rows[-1]
            print(json.dumps({
                "completed": completed,
                "total": total,
                "request_count": request_count,
                "seed": seed,
                "new_minimum_edr": round(new["minimum_request_edr"], 4),
                "new_total_edr": round(new["total_edr"], 4),
            }, ensure_ascii=False), flush=True)
    summaries = summarize(rows)
    comparison_rows = comparisons(rows)
    write_csv(RAW_OUTPUT, rows)
    write_csv(SUMMARY_OUTPUT, summaries)
    write_csv(COMPARISON_OUTPUT, comparison_rows)
    JSON_OUTPUT.write_text(
        json.dumps({"summary": summaries, "comparisons": comparison_rows},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "raw": str(RAW_OUTPUT),
        "summary": str(SUMMARY_OUTPUT),
        "comparisons": str(COMPARISON_OUTPUT),
        "json": str(JSON_OUTPUT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
