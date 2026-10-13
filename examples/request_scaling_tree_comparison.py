"""Compare Joint and SPFD with fixed versus optimized swapping trees."""

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
    optimize_spfd_swapping_trees,
    optimize_stage_one_swapping_trees,
    run_spfd_two_stage,
    run_stage_one,
)


REQUEST_COUNTS = (10, 20, 30, 40)
SEEDS = (20260812, 20260813, 20260814, 20260815, 20260816)
OUTPUT_DIRECTORY = Path(__file__).resolve().parents[1] / "results"
RAW_OUTPUT = OUTPUT_DIRECTORY / "request_scaling_tree_comparison_raw.csv"
SUMMARY_OUTPUT = OUTPUT_DIRECTORY / "request_scaling_tree_comparison_summary.csv"
GAIN_OUTPUT = OUTPUT_DIRECTORY / "request_scaling_tree_gain_summary.csv"
JSON_OUTPUT = OUTPUT_DIRECTORY / "request_scaling_tree_comparison.json"


def hop_quotas(request_count, seed):
    """Random 3--6-hop mix, guaranteeing long-path coverage in every run."""
    rng = random.Random(seed * 1009 + request_count)
    counts = {3: 1, 4: 1, 5: 1, 6: 1}
    for hop_count in rng.choices(
        population=(3, 4, 5, 6),
        weights=(0.30, 0.30, 0.25, 0.15),
        k=request_count - 4,
    ):
        counts[hop_count] += 1
    return tuple((hop, counts[hop]) for hop in (3, 4, 5, 6))


def experiment_config(request_count, seed):
    config = replace(
        DEFAULT_CONFIG,
        seed=seed,
        requests=replace(DEFAULT_CONFIG.requests, count=request_count),
        routing=replace(
            DEFAULT_CONFIG.routing,
            shortest_hop_quotas=hop_quotas(request_count, seed),
        ),
    )
    config.validate()
    return config


def jain(values):
    values = list(values)
    denominator = len(values) * sum(value * value for value in values)
    return sum(values) ** 2 / denominator if denominator > 0 else 0.0


def endpoint_memory(channel):
    capacities = [
        sum(int(memory.capacity) for memory in node.memories)
        for node in channel.node_list
    ]
    return min(capacities) if capacities else 0


def configuration_metrics(configuration):
    evaluations = [
        decision.selected
        for decision in configuration.decisions.values()
        if decision.selected is not None
    ]
    link_rates = [evaluation.effective_rate for evaluation in evaluations]
    purification = [
        item.rounds
        for evaluation in evaluations
        for item in evaluation.request_decisions
    ]
    memory_ratios = [
        item.memory_slots_per_endpoint / endpoint_memory(evaluation.channel)
        for evaluation in evaluations
        for item in evaluation.request_decisions
        if endpoint_memory(evaluation.channel) > 0
    ]
    return {
        "active_links": len(configuration.decisions),
        "infeasible_links": configuration.infeasible_links,
        "total_link_effective_rate": sum(link_rates),
        "minimum_link_effective_rate": min(link_rates, default=0.0),
        "average_link_effective_rate": statistics.fmean(link_rates) if link_rates else 0.0,
        "link_rate_jain_fairness": jain(link_rates),
        "average_purification_rounds": statistics.fmean(purification) if purification else 0.0,
        "average_memory_slot_ratio": statistics.fmean(memory_ratios) if memory_ratios else 0.0,
        "maximum_memory_slot_ratio": max(memory_ratios, default=0.0),
    }


def throughput_metrics(throughput, trees):
    rates = [
        allocation.allocated_rate
        for allocation in throughput.request_allocations.values()
    ]
    raw_costs = [sum(tree.raw_costs.values()) for tree in trees.values()]
    return {
        "total_edr": throughput.total_edr,
        "minimum_request_edr": throughput.minimum_request_edr,
        "average_request_edr": throughput.average_request_edr,
        "median_request_edr": statistics.median(rates) if rates else 0.0,
        "request_edr_jain_fairness": jain(rates),
        "demand_satisfaction_ratio": throughput.demand_satisfaction_ratio,
        "fully_satisfied_requests": throughput.fully_satisfied_requests,
        "request_acceptance_rate": throughput.request_acceptance_rate,
        "average_link_utilization": throughput.average_link_utilization,
        "maximum_link_utilization": throughput.maximum_link_utilization,
        "total_raw_capacity": sum(
            link.raw_capacity for link in throughput.link_allocations.values()
        ),
        "total_raw_consumed": sum(
            link.raw_consumed for link in throughput.link_allocations.values()
        ),
        "average_tree_raw_cost": statistics.fmean(raw_costs) if raw_costs else 0.0,
        "pf_iterations": throughput.iterations,
    }


def result_rows(
    request_count,
    seed,
    family,
    quality,
    configuration,
    fixed_trees,
    fixed_throughput,
    optimized,
    base_runtime,
    fixed_runtime,
    optimized_runtime,
    algorithm_iterations,
):
    common = {
        "node_count": 100,
        "request_count": request_count,
        "seed": seed,
        "algorithm_family": family,
        "hop_quotas": json.dumps(hop_quotas(request_count, seed)),
        "mean_path_hops": statistics.fmean(
            plan.selected_plan.hop_count
            for plan in quality.request_plans
            if plan.selected_plan is not None
        ),
        "algorithm_iterations": algorithm_iterations,
        "base_algorithm_runtime_seconds": base_runtime,
        **configuration_metrics(configuration),
    }
    selected = optimized.selected_record
    return [
        {
            **common,
            "tree_mode": "fixed_sequential",
            "tree_iterations": 0,
            "tree_runtime_seconds": fixed_runtime,
            "total_runtime_seconds": base_runtime + fixed_runtime,
            **throughput_metrics(fixed_throughput, fixed_trees),
        },
        {
            **common,
            "tree_mode": "optimized_DP",
            "tree_iterations": optimized.iterations,
            "tree_runtime_seconds": optimized_runtime,
            "total_runtime_seconds": base_runtime + optimized_runtime,
            **throughput_metrics(selected.throughput_result, selected.trees),
        },
    ]


def run_family(request_count, seed, family):
    config = experiment_config(request_count, seed)
    scenario = build_scenario(config)
    started = perf_counter()
    if family == "Joint":
        result = run_stage_one(scenario)
        base_runtime = perf_counter() - started
        selected = result.selected_record
        quality = selected.quality_result
        configuration = selected.configuration_result
        algorithm_iterations = result.iterations
        started = perf_counter()
        optimized = optimize_stage_one_swapping_trees(
            result, mutate_requests=False
        )
    else:
        result = run_spfd_two_stage(scenario, mutate_requests=False)
        base_runtime = perf_counter() - started
        quality = result.quality_result
        configuration = result.configuration_result
        algorithm_iterations = 1
        started = perf_counter()
        optimized = optimize_spfd_swapping_trees(
            result, mutate_requests=False
        )
    optimized_runtime = perf_counter() - started
    started = perf_counter()
    fixed_trees, fixed_throughput = allocate_fixed_swapping_tree_throughput(
        quality, configuration, mutate_requests=False
    )
    fixed_runtime = perf_counter() - started
    return result_rows(
        request_count, seed, family, quality, configuration,
        fixed_trees, fixed_throughput, optimized, base_runtime,
        fixed_runtime, optimized_runtime, algorithm_iterations,
    )


METRICS = (
    "total_edr",
    "minimum_request_edr",
    "average_request_edr",
    "median_request_edr",
    "request_edr_jain_fairness",
    "demand_satisfaction_ratio",
    "request_acceptance_rate",
    "average_link_utilization",
    "maximum_link_utilization",
    "total_raw_consumed",
    "average_tree_raw_cost",
    "average_purification_rounds",
    "average_memory_slot_ratio",
    "total_link_effective_rate",
    "minimum_link_effective_rate",
    "total_runtime_seconds",
    "base_algorithm_runtime_seconds",
    "tree_runtime_seconds",
)


def summarize(rows):
    summaries = []
    for request_count in REQUEST_COUNTS:
        for family in ("Joint", "SPFD"):
            for tree_mode in ("fixed_sequential", "optimized_DP"):
                group = [
                    row for row in rows
                    if row["request_count"] == request_count
                    and row["algorithm_family"] == family
                    and row["tree_mode"] == tree_mode
                ]
                summary = {
                    "node_count": 100,
                    "request_count": request_count,
                    "algorithm_family": family,
                    "tree_mode": tree_mode,
                    "repetitions": len(group),
                }
                for metric in METRICS:
                    values = [float(row[metric]) for row in group]
                    summary[f"{metric}_mean"] = statistics.fmean(values)
                    summary[f"{metric}_std"] = statistics.stdev(values)
                summaries.append(summary)
    return summaries


def tree_gains(rows):
    gains = []
    for request_count in REQUEST_COUNTS:
        for family in ("Joint", "SPFD"):
            group = [
                row for row in rows
                if row["request_count"] == request_count
                and row["algorithm_family"] == family
            ]
            fixed = [row for row in group if row["tree_mode"] == "fixed_sequential"]
            optimized = [row for row in group if row["tree_mode"] == "optimized_DP"]
            item = {
                "request_count": request_count,
                "algorithm_family": family,
                "repetitions": len(fixed),
            }
            for metric in (
                "total_edr", "minimum_request_edr", "request_edr_jain_fairness",
                "demand_satisfaction_ratio", "request_acceptance_rate",
                "average_tree_raw_cost",
            ):
                fixed_mean = statistics.fmean(row[metric] for row in fixed)
                optimized_mean = statistics.fmean(row[metric] for row in optimized)
                item[f"fixed_{metric}_mean"] = fixed_mean
                item[f"optimized_{metric}_mean"] = optimized_mean
                item[f"{metric}_change_percent"] = (
                    100.0 * (optimized_mean / fixed_mean - 1.0)
                    if fixed_mean else 0.0
                )
            gains.append(item)
    return gains


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
            rows.extend(run_family(request_count, seed, "SPFD"))
            rows.extend(run_family(request_count, seed, "Joint"))
            completed += 1
            print(json.dumps({
                "completed_pairs": completed,
                "total_pairs": total,
                "request_count": request_count,
                "seed": seed,
            }, ensure_ascii=False), flush=True)

    summaries = summarize(rows)
    gains = tree_gains(rows)
    write_csv(RAW_OUTPUT, rows)
    write_csv(SUMMARY_OUTPUT, summaries)
    write_csv(GAIN_OUTPUT, gains)
    JSON_OUTPUT.write_text(
        json.dumps({"summary": summaries, "tree_gains": gains},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "raw_output": str(RAW_OUTPUT),
        "summary_output": str(SUMMARY_OUTPUT),
        "gain_output": str(GAIN_OUTPUT),
        "json_output": str(JSON_OUTPUT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
