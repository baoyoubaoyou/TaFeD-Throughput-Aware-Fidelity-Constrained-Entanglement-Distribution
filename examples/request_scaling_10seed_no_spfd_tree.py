"""Ten-seed request-scaling comparison without SPFD's optimized-tree variant."""

import csv
import statistics
from pathlib import Path
from time import perf_counter

from baselines.legacy_quantum_routing import run_baseline
from baselines.legacy_quantum_routing.runtime import LegacyRuntimeConfig
from examples.request_scaling_tree_comparison import REQUEST_COUNTS, experiment_config
from experiments.collaborative_routing import (
    CombinatorialThroughputConfig,
    allocate_fixed_swapping_tree_throughput,
    build_scenario,
    run_combinatorial_throughput_optimized_stage_one,
    run_spfd_two_stage,
    run_tree_aware_combinatorial_throughput,
)

# These ten seeds all satisfy the current 3--6-hop request-generation
# constraints for request counts 10, 20, 30, and 40.
SEEDS = tuple(range(20260812, 20260820)) + (20260822, 20260823)
ALGORITHMS = (
    "QPath", "QLeap", "SFTRAP", "SPFD_no_tree",
    "Ours_no_tree", "Ours_optimized_tree",
)
RUNTIME = LegacyRuntimeConfig(mode="reimplemented", max_candidate_paths=3, max_reallocation_rounds=30)
RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "request_scaling_10seed_no_spfd_tree_raw.csv"
SUMMARY = RESULTS / "request_scaling_10seed_no_spfd_tree_summary.csv"
REPORT = RESULTS / "request_scaling_10seed_no_spfd_tree_report.md"
FIELDS = ("node_count", "request_count", "seed", "algorithm", "total_edr",
          "average_request_edr", "jain_fairness", "demand_satisfaction_ratio",
          "runtime_seconds", "iterations")


def _jain(values):
    denominator = len(values) * sum(value * value for value in values)
    return sum(values) ** 2 / denominator if denominator else 0.0


def _row(config, algorithm, rates, runtime, iterations=0, demand_ratio=0.0):
    return {
        "node_count": config.topology.node_count,
        "request_count": config.requests.count,
        "seed": config.seed,
        "algorithm": algorithm,
        "total_edr": sum(rates),
        "average_request_edr": statistics.fmean(rates) if rates else 0.0,
        "jain_fairness": _jain(rates),
        "demand_satisfaction_ratio": demand_ratio,
        "runtime_seconds": runtime,
        "iterations": iterations,
    }


def _formal_row(config, algorithm, throughput, runtime, iterations):
    rates = [item.allocated_rate for item in throughput.request_allocations.values()]
    return _row(config, algorithm, rates, runtime, iterations, throughput.demand_satisfaction_ratio)


def _run_current(config):
    rows = []
    scenario = build_scenario(config)
    started = perf_counter()
    spfd = run_spfd_two_stage(scenario, mutate_requests=False)
    base_runtime = perf_counter() - started
    started = perf_counter()
    _, fixed = allocate_fixed_swapping_tree_throughput(
        spfd.quality_result, spfd.configuration_result, mutate_requests=False)
    rows.append(_formal_row(config, "SPFD_no_tree", fixed, base_runtime + perf_counter() - started, 1))

    scenario = build_scenario(config)
    started = perf_counter()
    joint = run_combinatorial_throughput_optimized_stage_one(
        scenario, CombinatorialThroughputConfig(maximum_iterations=10), mutate_requests=False)
    rows.append(_formal_row(config, "Ours_no_tree", joint.selected_record.throughput_result,
                            perf_counter() - started, joint.iterations))

    scenario = build_scenario(config)
    started = perf_counter()
    joint_tree = run_tree_aware_combinatorial_throughput(
        scenario, CombinatorialThroughputConfig(maximum_iterations=10), mutate_requests=False)
    rows.append(_formal_row(config, "Ours_optimized_tree", joint_tree.selected_record.throughput_result,
                            perf_counter() - started, joint_tree.iterations))
    return rows


def _run_legacy(config):
    scenario = build_scenario(config)
    rows = []
    demands = [float(request.attr["demand_intensity"]) for request in scenario.requests]
    total_demand = sum(demands)
    for algorithm in ("QPath", "QLeap", "SFTrap"):
        result = run_baseline(scenario, algorithm, RUNTIME)
        rates = result.per_request_throughput
        rows.append(_row(config, "SFTRAP" if algorithm == "SFTrap" else algorithm,
                         rates, result.runtime_seconds,
                         result.metadata.get("iterations", 0),
                         sum(rates) / total_demand if total_demand else 0.0))
    return rows


def main():
    rows = []
    for request_count in REQUEST_COUNTS:
        for seed in SEEDS:
            config = experiment_config(request_count, seed)
            rows.extend(_run_legacy(config) + _run_current(config))
            print(request_count, seed, {row["algorithm"]: round(row["total_edr"], 3)
                                        for row in rows[-len(ALGORITHMS):]}, flush=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    with RAW.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    summary = []
    for request_count in REQUEST_COUNTS:
        for algorithm in ALGORITHMS:
            group = [row for row in rows if row["request_count"] == request_count and row["algorithm"] == algorithm]
            item = {"request_count": request_count, "algorithm": algorithm, "repetitions": len(group)}
            for metric in FIELDS[4:]:
                values = [float(row[metric]) for row in group]
                item[f"{metric}_mean"] = statistics.fmean(values) if values else 0.0
                item[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
            summary.append(item)
    with SUMMARY.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    report = ["# Request scaling comparison (10 seeds, no SPFD optimized tree)", "",
              "| Requests | Algorithm | Total EDR mean | Jain mean | Runtime mean (s) |",
              "|---:|---|---:|---:|---:|"]
    for item in summary:
        report.append(f"| {item['request_count']} | {item['algorithm']} | "
                      f"{float(item['total_edr_mean']):.3f} | "
                      f"{float(item['jain_fairness_mean']):.3f} | "
                      f"{float(item['runtime_seconds_mean']):.3f} |")
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"raw={RAW}\nsummary={SUMMARY}\nreport={REPORT}")


if __name__ == "__main__":
    main()
