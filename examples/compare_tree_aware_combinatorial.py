"""Evaluate tree-aware block search against optimized-tree baselines."""

import csv
import json
from pathlib import Path
import statistics

from experiments.collaborative_routing import (
    CombinatorialThroughputConfig,
    build_scenario,
    run_tree_aware_combinatorial_throughput,
)
from examples.request_scaling_tree_comparison import (
    REQUEST_COUNTS,
    SEEDS,
    experiment_config,
)


RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "tree_aware_combinatorial_raw.csv"
SUMMARY = RESULTS / "tree_aware_combinatorial_summary.csv"
COMPARISON = RESULTS / "tree_aware_combinatorial_comparison.csv"
JSON_OUTPUT = RESULTS / "tree_aware_combinatorial.json"


def jain(throughput):
    rates = [item.allocated_rate for item in throughput.request_allocations.values()]
    denominator = len(rates) * sum(rate * rate for rate in rates)
    return sum(rates) ** 2 / denominator if denominator > 0 else 0.0


def make_row(count, seed, algorithm, throughput, runtime, iterations,
             initialization="", evaluated=0):
    return {
        "node_count": 100,
        "request_count": count,
        "seed": seed,
        "algorithm": algorithm,
        "tree_mode": "optimized_DP",
        "total_edr": throughput.total_edr,
        "minimum_request_edr": throughput.minimum_request_edr,
        "average_request_edr": throughput.average_request_edr,
        "jain_fairness": jain(throughput),
        "demand_satisfaction_ratio": throughput.demand_satisfaction_ratio,
        "request_acceptance_rate": throughput.request_acceptance_rate,
        "average_link_utilization": throughput.average_link_utilization,
        "maximum_link_utilization": throughput.maximum_link_utilization,
        "iterations": iterations,
        "initialization": initialization,
        "evaluated_candidates": evaluated,
        "runtime_seconds": runtime,
    }


def run_one(count, seed):
    result = run_tree_aware_combinatorial_throughput(
        build_scenario(experiment_config(count, seed)),
        CombinatorialThroughputConfig(maximum_iterations=10),
        mutate_requests=False,
    )
    joint_record = next(
        record for record in result.records
        if record.iteration == 0
    )
    selected = result.selected_record
    # Both initial EDRs already include each baseline's optimal tree.
    common = {
        "joint": result.joint_initial_total_edr,
        "spfd": result.spfd_initial_total_edr,
    }
    # Load the exact baseline metrics from the previously verified paired run.
    previous_rows = list(csv.DictReader(
        (RESULTS / "three_algorithms_with_trees_raw.csv").open(
            encoding="utf-8-sig"
        )
    ))
    def prior(algorithm):
        row = next(
            item for item in previous_rows
            if int(item["request_count"]) == count
            and int(item["seed"]) == seed
            and item["algorithm"] == algorithm
            and item["tree_mode"] == "optimized_DP"
        )
        return row
    rows = []
    for label, prior_name in (("SPFD", "SPFD"), ("Joint_v1", "Joint_v1"),
                              ("Joint_fixed_combinatorial", "Joint_combinatorial")):
        old = prior(prior_name)
        rows.append({
            "node_count": 100, "request_count": count, "seed": seed,
            "algorithm": label, "tree_mode": "optimized_DP",
            "total_edr": float(old["total_edr"]),
            "minimum_request_edr": float(old["minimum_request_edr"]),
            "average_request_edr": float(old["average_request_edr"]),
            "jain_fairness": float(old["jain_fairness"]),
            "demand_satisfaction_ratio": float(old["demand_satisfaction_ratio"]),
            "request_acceptance_rate": float(old["request_acceptance_rate"]),
            "average_link_utilization": float(old["average_link_utilization"]),
            "maximum_link_utilization": float(old["maximum_link_utilization"]),
            "iterations": int(old["tree_iterations"]),
            "initialization": "", "evaluated_candidates": 0,
            "runtime_seconds": float(old["total_runtime_seconds"]),
        })
    rows.append(make_row(
        count, seed, "Joint_tree_aware_combinatorial",
        selected.throughput_result,
        result.initial_runtime_seconds + result.search_runtime_seconds,
        result.iterations,
        selected.initialization,
        sum(record.evaluated_combinations for record in result.records),
    ))
    return rows


METRICS = (
    "total_edr", "minimum_request_edr", "average_request_edr",
    "jain_fairness", "demand_satisfaction_ratio", "request_acceptance_rate",
    "average_link_utilization", "maximum_link_utilization", "runtime_seconds",
    "iterations", "evaluated_candidates",
)
ALGORITHMS = (
    "SPFD", "Joint_v1", "Joint_fixed_combinatorial",
    "Joint_tree_aware_combinatorial",
)


def summarize(rows):
    output = []
    for count in REQUEST_COUNTS:
        for algorithm in ALGORITHMS:
            group = [r for r in rows if r["request_count"] == count
                     and r["algorithm"] == algorithm]
            item = {"request_count": count, "algorithm": algorithm,
                    "repetitions": len(group)}
            for metric in METRICS:
                values = [float(r[metric]) for r in group]
                item[f"{metric}_mean"] = statistics.fmean(values)
                item[f"{metric}_std"] = statistics.stdev(values)
            output.append(item)
    return output


def comparisons(rows):
    output = []
    for count in REQUEST_COUNTS:
        means = {}
        for algorithm in ALGORITHMS:
            group = [r for r in rows if r["request_count"] == count
                     and r["algorithm"] == algorithm]
            means[algorithm] = {m: statistics.fmean(float(r[m]) for r in group)
                                for m in METRICS}
        for baseline in ALGORITHMS[:-1]:
            item = {"request_count": count,
                    "comparison": f"tree_aware_vs_{baseline}"}
            for metric in ("total_edr", "minimum_request_edr", "jain_fairness",
                           "demand_satisfaction_ratio", "request_acceptance_rate",
                           "runtime_seconds"):
                new = means[ALGORITHMS[-1]][metric]
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
    total = len(REQUEST_COUNTS) * len(SEEDS)
    completed = 0
    for count in REQUEST_COUNTS:
        for seed in SEEDS:
            current = run_one(count, seed)
            rows.extend(current)
            completed += 1
            new = current[-1]
            print(json.dumps({"completed": completed, "total": total,
                              "request_count": count, "seed": seed,
                              "initialization": new["initialization"],
                              "total_edr": round(new["total_edr"], 3)},
                             ensure_ascii=False), flush=True)
    summary_rows = summarize(rows)
    comparison_rows = comparisons(rows)
    write_csv(RAW, rows)
    write_csv(SUMMARY, summary_rows)
    write_csv(COMPARISON, comparison_rows)
    JSON_OUTPUT.write_text(json.dumps({"summary": summary_rows,
                                       "comparisons": comparison_rows},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"raw": str(RAW), "summary": str(SUMMARY),
                      "comparison": str(COMPARISON), "json": str(JSON_OUTPUT)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
