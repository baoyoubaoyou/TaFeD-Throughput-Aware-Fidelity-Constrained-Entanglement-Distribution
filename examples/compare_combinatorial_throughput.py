"""Full 100-node evaluation of multi-start block throughput search."""

import csv
import json
from pathlib import Path
import statistics
from time import perf_counter

from experiments.collaborative_routing import (
    allocate_fixed_swapping_tree_throughput,
    build_scenario,
    run_combinatorial_throughput_optimized_stage_one,
    run_spfd_two_stage,
)
from examples.request_scaling_tree_comparison import (
    REQUEST_COUNTS,
    SEEDS,
    experiment_config,
)


RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "combinatorial_throughput_raw.csv"
SUMMARY = RESULTS / "combinatorial_throughput_summary.csv"
COMPARISON = RESULTS / "combinatorial_throughput_comparison.csv"
JSON_OUTPUT = RESULTS / "combinatorial_throughput.json"


def jain(throughput):
    rates = [item.allocated_rate for item in throughput.request_allocations.values()]
    denominator = len(rates) * sum(rate * rate for rate in rates)
    return sum(rates) ** 2 / denominator if denominator > 0 else 0.0


def make_row(count, seed, algorithm, throughput, configuration, runtime,
             iterations, initialization="", block_links=0, combinations=0):
    return {
        "node_count": 100,
        "request_count": count,
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
        "initialization": initialization,
        "block_links": block_links,
        "evaluated_candidates": combinations,
        "runtime_seconds": runtime,
    }


def run_one(count, seed):
    experiment = experiment_config(count, seed)
    spfd_started = perf_counter()
    standalone_spfd = run_spfd_two_stage(
        build_scenario(experiment), mutate_requests=False
    )
    _, standalone_spfd_pf = allocate_fixed_swapping_tree_throughput(
        standalone_spfd.quality_result,
        standalone_spfd.configuration_result,
        mutate_requests=False,
    )
    standalone_spfd_runtime = perf_counter() - spfd_started
    result = run_combinatorial_throughput_optimized_stage_one(
        build_scenario(experiment), mutate_requests=False
    )
    joint_record = result.base_stage_one_result.selected_record
    _, joint_pf = allocate_fixed_swapping_tree_throughput(
        joint_record.quality_result,
        joint_record.configuration_result,
        mutate_requests=False,
    )
    selected = result.selected_record
    evaluated = sum(record.evaluated_combinations for record in result.records)
    return [
        make_row(count, seed, "SPFD", standalone_spfd_pf,
                 standalone_spfd.configuration_result,
                 standalone_spfd_runtime, 1),
        make_row(count, seed, "Joint_v1", joint_pf,
                 joint_record.configuration_result,
                 result.joint_initial_runtime_seconds,
                 result.base_stage_one_result.iterations),
        make_row(count, seed, "Joint_combinatorial", selected.throughput_result,
                 selected.configuration_result,
                 result.initial_runtime_seconds + result.search_runtime_seconds,
                 result.iterations, selected.initialization,
                 len(selected.block_channels), evaluated),
    ]


METRICS = (
    "total_edr", "minimum_request_edr", "average_request_edr",
    "jain_fairness", "demand_satisfaction_ratio", "request_acceptance_rate",
    "average_link_utilization", "maximum_link_utilization",
    "average_purification_rounds", "runtime_seconds", "iterations",
    "block_links", "evaluated_candidates",
)


def summarize(rows):
    output = []
    for count in REQUEST_COUNTS:
        for algorithm in ("SPFD", "Joint_v1", "Joint_combinatorial"):
            group = [r for r in rows if r["request_count"] == count and r["algorithm"] == algorithm]
            item = {"request_count": count, "algorithm": algorithm,
                    "repetitions": len(group),
                    "spfd_initializations": sum(r["initialization"] == "SPFD" for r in group)}
            for metric in METRICS:
                values = [float(r[metric]) for r in group]
                item[f"{metric}_mean"] = statistics.fmean(values)
                item[f"{metric}_std"] = statistics.stdev(values)
            output.append(item)
    return output


def compare(rows):
    output = []
    for count in REQUEST_COUNTS:
        means = {}
        for algorithm in ("SPFD", "Joint_v1", "Joint_combinatorial"):
            group = [r for r in rows if r["request_count"] == count and r["algorithm"] == algorithm]
            means[algorithm] = {m: statistics.fmean(float(r[m]) for r in group) for m in METRICS}
        for baseline in ("Joint_v1", "SPFD"):
            item = {"request_count": count,
                    "comparison": f"Joint_combinatorial_vs_{baseline}"}
            for metric in ("total_edr", "minimum_request_edr", "jain_fairness",
                           "demand_satisfaction_ratio", "request_acceptance_rate",
                           "runtime_seconds"):
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
    total = len(REQUEST_COUNTS) * len(SEEDS)
    completed = 0
    for count in REQUEST_COUNTS:
        for seed in SEEDS:
            current = run_one(count, seed)
            rows.extend(current)
            completed += 1
            print(json.dumps({"completed": completed, "total": total,
                              "request_count": count, "seed": seed,
                              "initialization": current[-1]["initialization"],
                              "total_edr": round(current[-1]["total_edr"], 3)},
                             ensure_ascii=False), flush=True)
    summary_rows = summarize(rows)
    comparison_rows = compare(rows)
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
