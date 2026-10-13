"""Node-scaling comparison with/without optimized swapping trees."""

import csv
import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import random
import statistics
from time import perf_counter

from baselines.legacy_quantum_routing import run_baseline
from baselines.legacy_quantum_routing.runtime import LegacyRuntimeConfig
from experiments.collaborative_routing import (
    CombinatorialThroughputConfig,
    DEFAULT_CONFIG,
    allocate_fixed_swapping_tree_throughput,
    build_scenario,
    optimize_spfd_swapping_trees,
    run_combinatorial_throughput_optimized_stage_one,
    run_spfd_two_stage,
    run_tree_aware_combinatorial_throughput,
)
from experiments.collaborative_routing import bottleneck_optimization as bottleneck
from experiments.collaborative_routing import combinatorial_throughput_optimization as combinatorial
from experiments.collaborative_routing import link_configuration
from experiments.collaborative_routing import marginal_throughput_optimization as marginal
from examples.request_scaling_tree_comparison import hop_quotas


NODE_COUNTS = tuple(range(50, 501, 50))
REQUEST_COUNT = 40
SEEDS = tuple(range(20260812, 20260912))
ALGORITHMS = (
    "QPath",
    "QLeap",
    "SFTRAP",
    "SPFD_no_tree",
    "SPFD_optimized_tree",
    "Joint_no_tree",
    "Joint_optimized_tree_fast",
)
RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "node_scaling_with_baselines_100seeds_raw.csv"
SUMMARY = RESULTS / "node_scaling_with_baselines_100seeds_summary.csv"
COMPARISON = RESULTS / "node_scaling_with_baselines_100seeds_comparison.csv"
JSON_OUTPUT = RESULTS / "node_scaling_with_baselines_100seeds.json"
SKIPPED = RESULTS / "node_scaling_with_baselines_100seeds_skipped.csv"
BASELINE_RUNTIME = LegacyRuntimeConfig(
    mode="reimplemented", max_candidate_paths=3, max_reallocation_rounds=30,
)


def experiment_config(node_count, seed):
    # Waxman's expected degree is approximately proportional to alpha * N.
    # Inverse scaling keeps average degree approximately stable, so edge count
    # grows linearly rather than quadratically as the network becomes larger.
    if node_count == 50:
        scaled_alpha = 0.5
    else:
        target_alpha_nodes = 32.0 + 8.0 * (node_count - 100.0) / 400.0
        scaled_alpha = target_alpha_nodes / node_count
    quotas = scaled_hop_quotas(node_count, seed)
    config = replace(
        DEFAULT_CONFIG,
        seed=seed,
        topology=replace(
            DEFAULT_CONFIG.topology,
            node_count=node_count,
            alpha=scaled_alpha,
        ),
        requests=replace(DEFAULT_CONFIG.requests, count=REQUEST_COUNT),
        routing=replace(
            DEFAULT_CONFIG.routing,
            min_hops=min(hop for hop, _ in quotas),
            max_hops=max(hop for hop, _ in quotas),
            shortest_hop_quotas=quotas,
        ),
    )
    config.validate()
    return config


def scaled_hop_quotas(node_count, seed):
    """Shift mass toward longer paths while retaining the six-hop limit."""
    maximum_hops = 5 if node_count == 50 else DEFAULT_CONFIG.routing.max_hops
    shift = max(0.0, (node_count - 100.0) / (NODE_COUNTS[-1] - 100.0))
    integer_shift = int(shift)
    fractional_shift = shift - integer_shift
    hops = [
        min(maximum_hops, hop + integer_shift)
        for hop, count in hop_quotas(REQUEST_COUNT, seed)
        for _ in range(count)
    ]
    rng = random.Random(seed * 1009 + node_count * 9173)
    rng.shuffle(hops)
    shifted = 0
    target_shifts = round(fractional_shift * len(hops))
    for index, hop in enumerate(hops):
        if shifted >= target_shifts:
            break
        if hop < maximum_hops:
            hops[index] += 1
            shifted += 1
    counts = {}
    for hop in hops:
        counts[hop] = counts.get(hop, 0) + 1
    return tuple(sorted(counts.items()))


def jain(throughput):
    rates = [item.allocated_rate for item in throughput.request_allocations.values()]
    denominator = len(rates) * sum(rate * rate for rate in rates)
    return sum(rates) ** 2 / denominator if denominator > 0 else 0.0


def make_row(node_count, seed, algorithm, scenario, throughput, runtime, iterations):
    return {
        "node_count": node_count,
        "request_count": scenario.config.requests.count,
        "seed": seed,
        "algorithm": algorithm,
        "quantum_links": len(scenario.network.qchannels),
        "total_edr": throughput.total_edr,
        "minimum_request_edr": throughput.minimum_request_edr,
        "average_request_edr": throughput.average_request_edr,
        "jain_fairness": jain(throughput),
        "demand_satisfaction_ratio": throughput.demand_satisfaction_ratio,
        "request_acceptance_rate": throughput.request_acceptance_rate,
        "average_link_utilization": throughput.average_link_utilization,
        "maximum_link_utilization": throughput.maximum_link_utilization,
        "runtime_seconds": runtime,
        "iterations": iterations,
    }


def run_legacy_baselines(config):
    scenario = build_scenario(config)
    demands = [float(request.attr["demand_intensity"]) for request in scenario.requests]
    rows = []
    for algorithm in ("QPath", "QLeap", "SFTrap"):
        result = run_baseline(scenario, algorithm, BASELINE_RUNTIME)
        rates = result.per_request_throughput
        denominator = len(rates) * sum(rate * rate for rate in rates)
        rows.append({
            "node_count": config.topology.node_count,
            "request_count": config.requests.count,
            "seed": config.seed,
            "algorithm": "SFTRAP" if algorithm == "SFTrap" else algorithm,
            "quantum_links": len(scenario.network.qchannels),
            "total_edr": result.total_throughput,
            "minimum_request_edr": min(rates, default=0.0),
            "average_request_edr": sum(rates) / len(rates) if rates else 0.0,
            "jain_fairness": sum(rates) ** 2 / denominator if denominator else 0.0,
            "demand_satisfaction_ratio": result.total_throughput / sum(demands) if demands else 0.0,
            "request_acceptance_rate": result.accepted_requests / len(rates) if rates else 0.0,
            "average_link_utilization": result.metadata.get("average_link_utilization", 0.0),
            "maximum_link_utilization": result.metadata.get("maximum_link_utilization", 0.0),
            "runtime_seconds": result.runtime_seconds,
            "iterations": result.metadata.get("iterations", 0),
        })
    return rows


def _legacy_find(point, required_fidelity):
    return next(
        (plan for plan in point.plans if plan.output_fidelity >= required_fidelity),
        None,
    )


def _legacy_batch(channel, requirements, points):
    return [
        link_configuration.evaluate_lookup_configuration(
            channel, requirements, point
        )
        for point in points
    ]


@contextmanager
def legacy_configuration_search():
    old_find = link_configuration.find_minimum_lookup_plan
    modules = (link_configuration, combinatorial, marginal, bottleneck)
    old_batch = {
        module: module.evaluate_lookup_configurations for module in modules
    }
    link_configuration.find_minimum_lookup_plan = _legacy_find
    for module in modules:
        module.evaluate_lookup_configurations = _legacy_batch
    try:
        yield
    finally:
        link_configuration.find_minimum_lookup_plan = old_find
        for module, function in old_batch.items():
            module.evaluate_lookup_configurations = function


def run_spfd_variants(config):
    scenario = build_scenario(config)
    started = perf_counter()
    spfd = run_spfd_two_stage(scenario, mutate_requests=False)
    base_runtime = perf_counter() - started

    fixed_started = perf_counter()
    _, fixed = allocate_fixed_swapping_tree_throughput(
        spfd.quality_result,
        spfd.configuration_result,
        mutate_requests=False,
    )
    fixed_runtime = perf_counter() - fixed_started

    tree_started = perf_counter()
    optimized = optimize_spfd_swapping_trees(spfd, mutate_requests=False)
    tree_runtime = perf_counter() - tree_started
    selected = optimized.selected_record
    return [
        make_row(
            config.topology.node_count, config.seed, "SPFD_no_tree",
            scenario, fixed, base_runtime + fixed_runtime, 1,
        ),
        make_row(
            config.topology.node_count, config.seed, "SPFD_optimized_tree",
            scenario, selected.throughput_result,
            base_runtime + tree_runtime, optimized.iterations,
        ),
    ]


def run_joint_no_tree(config):
    scenario = build_scenario(config)
    started = perf_counter()
    result = run_combinatorial_throughput_optimized_stage_one(
        scenario,
        CombinatorialThroughputConfig(maximum_iterations=10),
        mutate_requests=False,
    )
    runtime = perf_counter() - started
    return make_row(
        config.topology.node_count, config.seed, "Joint_no_tree", scenario,
        result.selected_record.throughput_result, runtime, result.iterations,
    )


def run_joint_tree(config, fast):
    scenario = build_scenario(config)
    started = perf_counter()
    if fast:
        result = run_tree_aware_combinatorial_throughput(
            scenario,
            CombinatorialThroughputConfig(maximum_iterations=10),
            mutate_requests=False,
        )
    else:
        with legacy_configuration_search():
            result = run_tree_aware_combinatorial_throughput(
                scenario,
                CombinatorialThroughputConfig(maximum_iterations=10),
                mutate_requests=False,
            )
    runtime = perf_counter() - started
    return make_row(
        config.topology.node_count, config.seed,
        "Joint_optimized_tree_fast" if fast else "Joint_optimized_tree",
        scenario, result.selected_record.throughput_result,
        runtime, result.iterations,
    )


METRICS = (
    "quantum_links", "total_edr", "minimum_request_edr",
    "average_request_edr", "jain_fairness", "demand_satisfaction_ratio",
    "request_acceptance_rate", "average_link_utilization",
    "maximum_link_utilization", "runtime_seconds", "iterations",
)


def summarize(rows):
    output = []
    for node_count in NODE_COUNTS:
        for algorithm in ALGORITHMS:
            group = [
                row for row in rows
                if row["node_count"] == node_count
                and row["algorithm"] == algorithm
            ]
            item = {
                "node_count": node_count,
                "request_count": REQUEST_COUNT,
                "algorithm": algorithm,
                "repetitions": len(group),
            }
            for metric in METRICS:
                values = [float(row[metric]) for row in group]
                item[f"{metric}_mean"] = statistics.fmean(values)
                item[f"{metric}_std"] = statistics.stdev(values)
            output.append(item)
    return output


def comparisons(rows):
    output = []
    for node_count in NODE_COUNTS:
        means = {}
        for algorithm in ALGORITHMS:
            group = [
                row for row in rows
                if row["node_count"] == node_count
                and row["algorithm"] == algorithm
            ]
            means[algorithm] = {
                metric: statistics.fmean(float(row[metric]) for row in group)
                for metric in METRICS
            }
        for algorithm, baseline in (
            ("Joint_no_tree", "SPFD_no_tree"),
            ("Joint_optimized_tree_fast", "SPFD_optimized_tree"),
            ("SPFD_optimized_tree", "SPFD_no_tree"),
            ("Joint_optimized_tree_fast", "Joint_no_tree"),
        ):
            item = {
                "node_count": node_count,
                "comparison": f"{algorithm}_vs_{baseline}",
            }
            for metric in (
                "total_edr", "minimum_request_edr", "jain_fairness",
                "demand_satisfaction_ratio", "request_acceptance_rate",
                "runtime_seconds",
            ):
                new = means[algorithm][metric]
                old = means[baseline][metric]
                item[f"{metric}_change_percent"] = (
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


def write_skipped(rows):
    fieldnames = ("node_count", "seed", "reason")
    with SKIPPED.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = []
    if RAW.exists():
        with RAW.open(encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                converted = dict(row)
                converted["node_count"] = int(row["node_count"])
                converted["request_count"] = int(row["request_count"])
                converted["seed"] = int(row["seed"])
                for field in METRICS:
                    converted[field] = float(row[field])
                rows.append(converted)
    skipped = []
    if SKIPPED.exists():
        with SKIPPED.open(encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                skipped.append({
                    "node_count": int(row["node_count"]),
                    "seed": int(row["seed"]),
                    "reason": row["reason"],
                })
    completed_scenarios = {
        (row["node_count"], row["seed"])
        for row in rows
        if sum(
            item["node_count"] == row["node_count"]
            and item["seed"] == row["seed"]
            for item in rows
        ) == len(ALGORITHMS)
    }
    skipped_scenarios = {(row["node_count"], row["seed"]) for row in skipped}
    total = len(NODE_COUNTS) * len(SEEDS)
    completed = len(completed_scenarios) + len(skipped_scenarios)
    for node_count in NODE_COUNTS:
        for seed in SEEDS:
            scenario_key = (node_count, seed)
            if scenario_key in completed_scenarios or scenario_key in skipped_scenarios:
                continue
            config = experiment_config(node_count, seed)
            try:
                # Validate that this random topology can instantiate all requests
                # before running each algorithm on its identical reconstruction.
                build_scenario(config)
            except RuntimeError as error:
                if not (
                    str(error).startswith("generated ")
                    or str(error).startswith("Failed to generate a connected topology")
                ):
                    raise
                skipped.append({
                    "node_count": node_count,
                    "seed": seed,
                    "reason": str(error),
                })
                skipped_scenarios.add(scenario_key)
                write_skipped(skipped)
                completed += 1
                print(json.dumps({
                    "completed": completed,
                    "total": total,
                    "node_count": node_count,
                    "seed": seed,
                    "status": "skipped_unusable_topology",
                    "reason": str(error),
                }, ensure_ascii=False), flush=True)
                continue
            current = run_legacy_baselines(config)
            current.extend(run_spfd_variants(config))
            current.append(run_joint_no_tree(config))
            current.append(run_joint_tree(config, fast=True))
            rows.extend(current)
            write_csv(RAW, rows)
            completed += 1
            print(json.dumps({
                "completed": completed,
                "total": total,
                "node_count": node_count,
                "seed": seed,
                "total_edr": {
                    row["algorithm"]: round(row["total_edr"], 3)
                    for row in current
                },
                "runtime_seconds": {
                    row["algorithm"]: round(row["runtime_seconds"], 3)
                    for row in current
                },
            }, ensure_ascii=False), flush=True)

    summary = summarize(rows)
    comparison = comparisons(rows)
    write_csv(SUMMARY, summary)
    write_csv(COMPARISON, comparison)
    JSON_OUTPUT.write_text(json.dumps(
        {"raw": rows, "summary": summary, "comparisons": comparison},
        ensure_ascii=False, indent=2,
    ), encoding="utf-8")
    print(json.dumps({
        "raw": str(RAW), "summary": str(SUMMARY),
        "comparison": str(COMPARISON), "json": str(JSON_OUTPUT),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
