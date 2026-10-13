"""Compare three algorithms before and after optimal swapping-tree search."""

import csv
import json
from pathlib import Path
import statistics
from time import perf_counter

from experiments.collaborative_routing import (
    allocate_fixed_swapping_tree_throughput,
    build_scenario,
    optimize_spfd_swapping_trees,
    optimize_stage_one_swapping_trees,
    optimize_swapping_trees_and_throughput,
    run_combinatorial_throughput_optimized_stage_one,
    run_spfd_two_stage,
)
from examples.request_scaling_tree_comparison import (
    REQUEST_COUNTS,
    SEEDS,
    experiment_config,
)


RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "three_algorithms_with_trees_raw.csv"
SUMMARY = RESULTS / "three_algorithms_with_trees_summary.csv"
GAIN = RESULTS / "three_algorithms_tree_gain.csv"
COMPARISON = RESULTS / "three_algorithms_optimized_comparison.csv"
JSON_OUTPUT = RESULTS / "three_algorithms_with_trees.json"


def jain(throughput):
    rates = [item.allocated_rate for item in throughput.request_allocations.values()]
    denominator = len(rates) * sum(rate * rate for rate in rates)
    return sum(rates) ** 2 / denominator if denominator > 0 else 0.0


def tree_raw_cost(trees):
    costs = [sum(tree.raw_costs.values()) for tree in trees.values()]
    return statistics.fmean(costs) if costs else 0.0


def make_row(count, seed, algorithm, mode, throughput, trees,
             algorithm_runtime, tree_runtime, tree_iterations):
    return {
        "node_count": 100,
        "request_count": count,
        "seed": seed,
        "algorithm": algorithm,
        "tree_mode": mode,
        "total_edr": throughput.total_edr,
        "minimum_request_edr": throughput.minimum_request_edr,
        "average_request_edr": throughput.average_request_edr,
        "jain_fairness": jain(throughput),
        "demand_satisfaction_ratio": throughput.demand_satisfaction_ratio,
        "request_acceptance_rate": throughput.request_acceptance_rate,
        "average_link_utilization": throughput.average_link_utilization,
        "maximum_link_utilization": throughput.maximum_link_utilization,
        "average_tree_raw_cost": tree_raw_cost(trees),
        "pf_iterations": throughput.iterations,
        "tree_iterations": tree_iterations,
        "algorithm_runtime_seconds": algorithm_runtime,
        "tree_runtime_seconds": tree_runtime,
        "total_runtime_seconds": algorithm_runtime + tree_runtime,
    }


def append_pair(rows, count, seed, algorithm, quality, configuration,
                fixed_trees, fixed_pf, optimized, algorithm_runtime,
                fixed_runtime, optimized_runtime):
    rows.append(make_row(
        count, seed, algorithm, "fixed_sequential", fixed_pf, fixed_trees,
        algorithm_runtime, fixed_runtime, 0,
    ))
    selected = optimized.selected_record
    rows.append(make_row(
        count, seed, algorithm, "optimized_DP",
        selected.throughput_result, selected.trees,
        algorithm_runtime, optimized_runtime, optimized.iterations,
    ))


def run_one(count, seed):
    config = experiment_config(count, seed)
    rows = []

    spfd_started = perf_counter()
    spfd = run_spfd_two_stage(build_scenario(config), mutate_requests=False)
    spfd_runtime = perf_counter() - spfd_started
    started = perf_counter()
    spfd_fixed_trees, spfd_fixed = allocate_fixed_swapping_tree_throughput(
        spfd.quality_result, spfd.configuration_result, mutate_requests=False
    )
    spfd_fixed_runtime = perf_counter() - started
    started = perf_counter()
    spfd_optimized = optimize_spfd_swapping_trees(
        spfd, mutate_requests=False
    )
    spfd_tree_runtime = perf_counter() - started
    append_pair(
        rows, count, seed, "SPFD", spfd.quality_result,
        spfd.configuration_result, spfd_fixed_trees, spfd_fixed,
        spfd_optimized, spfd_runtime, spfd_fixed_runtime, spfd_tree_runtime,
    )

    combined = run_combinatorial_throughput_optimized_stage_one(
        build_scenario(config), mutate_requests=False
    )
    joint = combined.base_stage_one_result
    joint_record = joint.selected_record
    started = perf_counter()
    joint_fixed_trees, joint_fixed = allocate_fixed_swapping_tree_throughput(
        joint_record.quality_result,
        joint_record.configuration_result,
        mutate_requests=False,
    )
    joint_fixed_runtime = perf_counter() - started
    started = perf_counter()
    joint_optimized = optimize_stage_one_swapping_trees(
        joint, mutate_requests=False
    )
    joint_tree_runtime = perf_counter() - started
    append_pair(
        rows, count, seed, "Joint_v1", joint_record.quality_result,
        joint_record.configuration_result, joint_fixed_trees, joint_fixed,
        joint_optimized, combined.joint_initial_runtime_seconds,
        joint_fixed_runtime, joint_tree_runtime,
    )

    selected = combined.selected_record
    started = perf_counter()
    combined_fixed_trees, combined_fixed = allocate_fixed_swapping_tree_throughput(
        selected.quality_result,
        selected.configuration_result,
        mutate_requests=False,
    )
    combined_fixed_runtime = perf_counter() - started
    started = perf_counter()
    combined_optimized = optimize_swapping_trees_and_throughput(
        selected.quality_result,
        selected.configuration_result,
        mutate_requests=False,
    )
    combined_tree_runtime = perf_counter() - started
    append_pair(
        rows, count, seed, "Joint_combinatorial", selected.quality_result,
        selected.configuration_result, combined_fixed_trees, combined_fixed,
        combined_optimized,
        combined.initial_runtime_seconds + combined.search_runtime_seconds,
        combined_fixed_runtime, combined_tree_runtime,
    )
    return rows


METRICS = (
    "total_edr", "minimum_request_edr", "average_request_edr",
    "jain_fairness", "demand_satisfaction_ratio", "request_acceptance_rate",
    "average_link_utilization", "maximum_link_utilization",
    "average_tree_raw_cost", "tree_runtime_seconds", "total_runtime_seconds",
)


def summarize(rows):
    output = []
    for count in REQUEST_COUNTS:
        for algorithm in ("SPFD", "Joint_v1", "Joint_combinatorial"):
            for mode in ("fixed_sequential", "optimized_DP"):
                group = [r for r in rows if r["request_count"] == count
                         and r["algorithm"] == algorithm and r["tree_mode"] == mode]
                item = {"request_count": count, "algorithm": algorithm,
                        "tree_mode": mode, "repetitions": len(group)}
                for metric in METRICS:
                    values = [float(r[metric]) for r in group]
                    item[f"{metric}_mean"] = statistics.fmean(values)
                    item[f"{metric}_std"] = statistics.stdev(values)
                output.append(item)
    return output


def gains(rows):
    output = []
    for count in REQUEST_COUNTS:
        for algorithm in ("SPFD", "Joint_v1", "Joint_combinatorial"):
            fixed = [r for r in rows if r["request_count"] == count
                     and r["algorithm"] == algorithm and r["tree_mode"] == "fixed_sequential"]
            optimized = [r for r in rows if r["request_count"] == count
                         and r["algorithm"] == algorithm and r["tree_mode"] == "optimized_DP"]
            item = {"request_count": count, "algorithm": algorithm,
                    "repetitions": len(fixed)}
            for metric in ("total_edr", "minimum_request_edr", "jain_fairness",
                           "demand_satisfaction_ratio", "request_acceptance_rate",
                           "average_tree_raw_cost"):
                before = statistics.fmean(float(r[metric]) for r in fixed)
                after = statistics.fmean(float(r[metric]) for r in optimized)
                item[f"fixed_{metric}_mean"] = before
                item[f"optimized_{metric}_mean"] = after
                item[f"{metric}_change_percent"] = 100.0 * (after / before - 1.0) if before else 0.0
            output.append(item)
    return output


def optimized_comparisons(rows):
    output = []
    for count in REQUEST_COUNTS:
        means = {}
        for algorithm in ("SPFD", "Joint_v1", "Joint_combinatorial"):
            group = [r for r in rows if r["request_count"] == count
                     and r["algorithm"] == algorithm and r["tree_mode"] == "optimized_DP"]
            means[algorithm] = {m: statistics.fmean(float(r[m]) for r in group) for m in METRICS}
        for baseline in ("Joint_v1", "SPFD"):
            item = {"request_count": count,
                    "comparison": f"Joint_combinatorial_vs_{baseline}"}
            for metric in ("total_edr", "minimum_request_edr", "jain_fairness",
                           "demand_satisfaction_ratio", "request_acceptance_rate",
                           "total_runtime_seconds"):
                new = means["Joint_combinatorial"][metric]
                old = means[baseline][metric]
                item[f"{metric}_change_percent"] = 100.0 * (new / old - 1.0) if old else 0.0
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
    for count in REQUEST_COUNTS:
        for seed in SEEDS:
            current = run_one(count, seed)
            rows.extend(current)
            completed += 1
            best = next(r for r in current if r["algorithm"] == "Joint_combinatorial"
                        and r["tree_mode"] == "optimized_DP")
            print(json.dumps({"completed": completed, "total": total,
                              "request_count": count, "seed": seed,
                              "optimized_total_edr": round(best["total_edr"], 3)},
                             ensure_ascii=False), flush=True)
    summary_rows = summarize(rows)
    gain_rows = gains(rows)
    comparison_rows = optimized_comparisons(rows)
    write_csv(RAW, rows)
    write_csv(SUMMARY, summary_rows)
    write_csv(GAIN, gain_rows)
    write_csv(COMPARISON, comparison_rows)
    JSON_OUTPUT.write_text(json.dumps({"summary": summary_rows, "tree_gains": gain_rows,
                                       "optimized_comparisons": comparison_rows},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"raw": str(RAW), "summary": str(SUMMARY),
                      "gain": str(GAIN), "comparison": str(COMPARISON),
                      "json": str(JSON_OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
