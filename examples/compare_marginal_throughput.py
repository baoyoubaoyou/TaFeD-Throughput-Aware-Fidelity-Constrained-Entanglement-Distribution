"""Compare SPFD, Joint v1, and marginal-price Joint without tree DP."""

import csv
import json
from pathlib import Path
import statistics
from time import perf_counter

from experiments.collaborative_routing import (
    allocate_fixed_swapping_tree_throughput,
    build_scenario,
    run_marginal_throughput_optimized_stage_one,
    run_spfd_two_stage,
)
from examples.request_scaling_tree_comparison import (
    REQUEST_COUNTS,
    SEEDS,
    experiment_config,
)


RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "marginal_throughput_raw.csv"
SUMMARY = RESULTS / "marginal_throughput_summary.csv"
COMPARISON = RESULTS / "marginal_throughput_comparison.csv"
JSON_OUTPUT = RESULTS / "marginal_throughput.json"


def jain(throughput):
    rates = [item.allocated_rate for item in throughput.request_allocations.values()]
    denominator = len(rates) * sum(rate * rate for rate in rates)
    return sum(rates) ** 2 / denominator if denominator > 0 else 0.0


def row(request_count, seed, algorithm, throughput, configuration, runtime,
        iterations, searched_links):
    return {
        "node_count": 100,
        "request_count": request_count,
        "seed": seed,
        "algorithm": algorithm,
        "tree_mode": "fixed_sequential",
        "total_edr": throughput.total_edr,
        "minimum_request_edr": throughput.minimum_request_edr,
        "average_request_edr": throughput.average_request_edr,
        "jain_fairness": jain(throughput),
        "demand_satisfaction_ratio": throughput.demand_satisfaction_ratio,
        "request_acceptance_rate": throughput.request_acceptance_rate,
        "average_link_utilization": throughput.average_link_utilization,
        "maximum_link_utilization": throughput.maximum_link_utilization,
        "average_purification_rounds": configuration.average_purification_rounds,
        "active_links": configuration.active_links,
        "infeasible_links": configuration.infeasible_links,
        "iterations": iterations,
        "positive_marginal_links": searched_links,
        "runtime_seconds": runtime,
    }


def run_one(request_count, seed):
    config = experiment_config(request_count, seed)
    started = perf_counter()
    spfd = run_spfd_two_stage(build_scenario(config), mutate_requests=False)
    _, spfd_pf = allocate_fixed_swapping_tree_throughput(
        spfd.quality_result, spfd.configuration_result, mutate_requests=False
    )
    spfd_runtime = perf_counter() - started

    marginal = run_marginal_throughput_optimized_stage_one(
        build_scenario(config), mutate_requests=False
    )
    base = marginal.records[0]
    selected = marginal.selected_record
    return [
        row(request_count, seed, "SPFD", spfd_pf, spfd.configuration_result,
            spfd_runtime, 1, 0),
        row(request_count, seed, "Joint_v1", base.throughput_result,
            base.configuration_result, marginal.base_runtime_seconds,
            marginal.base_stage_one_result.iterations, 0),
        row(request_count, seed, "Joint_marginal_total", selected.throughput_result,
            selected.configuration_result,
            marginal.base_runtime_seconds + marginal.refinement_runtime_seconds,
            marginal.refinement_iterations, len(selected.searched_channels)),
    ]


METRICS = (
    "total_edr", "minimum_request_edr", "average_request_edr",
    "jain_fairness", "demand_satisfaction_ratio", "request_acceptance_rate",
    "average_link_utilization", "maximum_link_utilization",
    "average_purification_rounds", "runtime_seconds", "iterations",
    "positive_marginal_links",
)


def summaries(rows):
    output = []
    for count in REQUEST_COUNTS:
        for algorithm in ("SPFD", "Joint_v1", "Joint_marginal_total"):
            group = [r for r in rows if r["request_count"] == count and r["algorithm"] == algorithm]
            item = {"request_count": count, "algorithm": algorithm, "repetitions": len(group)}
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
        for algorithm in ("SPFD", "Joint_v1", "Joint_marginal_total"):
            group = [r for r in rows if r["request_count"] == count and r["algorithm"] == algorithm]
            means[algorithm] = {m: statistics.fmean(float(r[m]) for r in group) for m in METRICS}
        for baseline in ("Joint_v1", "SPFD"):
            item = {"request_count": count, "comparison": f"Joint_marginal_total_vs_{baseline}"}
            for metric in ("total_edr", "minimum_request_edr", "jain_fairness",
                           "demand_satisfaction_ratio", "request_acceptance_rate", "runtime_seconds"):
                old = means[baseline][metric]
                new = means["Joint_marginal_total"][metric]
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
            print(json.dumps({"completed": completed, "total": total,
                              "request_count": count, "seed": seed,
                              "new_total_edr": round(current[-1]["total_edr"], 3)},
                             ensure_ascii=False), flush=True)
    summary_rows = summaries(rows)
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
