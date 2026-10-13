"""Run five comparison groups between ours and the MILP benchmark."""

import csv
import json
from dataclasses import replace
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.collaborative_routing import (
    CombinatorialThroughputConfig,
    DEFAULT_CONFIG,
    MILPBenchmarkConfig,
    build_scenario,
    run_tree_aware_combinatorial_throughput,
    solve_milp_optimal_benchmark,
)


SEEDS = (20260820, 20260821, 20260822, 20260823, 20260824)
OUTPUT_DIR = ROOT / "results"
RAW_OUTPUT = OUTPUT_DIR / "milp_50n5r_five_groups_raw.csv"
SUMMARY_OUTPUT = OUTPUT_DIR / "milp_50n5r_five_groups_summary.csv"
JSON_OUTPUT = OUTPUT_DIR / "milp_50n5r_five_groups.json"


def experiment_config(seed):
    config = replace(
        DEFAULT_CONFIG,
        seed=seed,
        topology=replace(
            DEFAULT_CONFIG.topology,
            node_count=50,
            alpha=0.5,
            beta=0.2,
        ),
        requests=replace(
            DEFAULT_CONFIG.requests,
            count=5,
            demand_min=50,
            demand_max=100,
            fidelity_min=0.80,
            fidelity_max=0.93,
        ),
        routing=replace(
            DEFAULT_CONFIG.routing,
            k=1,
            min_hops=3,
            max_hops=5,
            shortest_hop_quotas=((3, 2), (4, 2), (5, 1)),
            require_k_paths=True,
        ),
        purification=replace(
            DEFAULT_CONFIG.purification,
            maximum_rounds=4,
        ),
    )
    config.validate()
    return config


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows):
    summary = []
    for metric in (
        "ours_total_edr",
        "ours_min_satisfaction",
        "ours_runtime_seconds",
        "milp_total_edr",
        "milp_min_satisfaction",
        "milp_runtime_seconds",
        "milp_gurobi_runtime_seconds",
        "total_gap_percent_vs_milp",
        "min_satisfaction_gap",
    ):
        values = [float(row[metric]) for row in rows]
        summary.append({
            "metric": metric,
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        })
    return summary


def request_summary(request_solutions):
    return [
        {
            "request": item.request_index,
            "allocated_rate": item.allocated_rate,
            "satisfaction": item.satisfaction,
            "selected_column": None if item.selected_column is None else item.selected_column.column_index,
            "candidate_columns": item.request.attr.get("candidate_columns", None),
        }
        for item in request_solutions
    ]


def run_group(seed):
    config = experiment_config(seed)
    scenario = build_scenario(config)

    ours_started = perf_counter()
    ours = run_tree_aware_combinatorial_throughput(
        scenario,
        CombinatorialThroughputConfig(
            maximum_iterations=3,
            maximum_block_links=3,
            candidates_per_link=2,
        ),
        mutate_requests=False,
    )
    ours_runtime = perf_counter() - ours_started
    ours_selected = ours.selected_record
    ours_total = ours_selected.throughput_result.total_edr
    ours_min_satisfaction = min(
        allocation.demand_satisfaction
        for allocation in ours_selected.throughput_result.request_allocations.values()
    )

    milp_started = perf_counter()
    milp = solve_milp_optimal_benchmark(
        scenario.requests,
        config,
        MILPBenchmarkConfig(
            maximum_purification_rounds=4,
            link_option_limit=8,
            time_limit_seconds=600.0,
            verbose=True,
        ),
    )
    milp_runtime = perf_counter() - milp_started

    row = {
        "seed": seed,
        "nodes": len(scenario.network.nodes),
        "requests": len(scenario.requests),
        "ours_total_edr": ours_total,
        "ours_min_satisfaction": ours_min_satisfaction,
        "ours_runtime_seconds": ours_runtime,
        "milp_total_edr": milp.total_edr,
        "milp_min_satisfaction": milp.objective_min_satisfaction,
        "milp_runtime_seconds": milp_runtime,
        "milp_gurobi_runtime_seconds": milp.runtime_seconds,
        "total_gap_percent_vs_milp": (
            100.0 * (milp.total_edr - ours_total) / milp.total_edr
            if milp.total_edr > 0 else 0.0
        ),
        "min_satisfaction_gap": milp.objective_min_satisfaction - ours_min_satisfaction,
        "ours_tree_iterations": ours.iterations,
        "ours_tree_converged": ours.converged,
        "ours_tree_stop_reason": ours.stop_reason,
        "ours_selected_total_edr": ours_selected.throughput_result.total_edr,
        "milp_candidate_counts": json.dumps(
            {str(key): len(value) for key, value in milp.columns.items()},
            ensure_ascii=False,
        ),
        "request_details": json.dumps(request_summary(milp.request_solutions), ensure_ascii=False),
    }
    return row


def main():
    rows = []
    total = len(SEEDS)
    for index, seed in enumerate(SEEDS, start=1):
        row = run_group(seed)
        rows.append(row)
        print(json.dumps({
            "completed": index,
            "total": total,
            "seed": seed,
            "ours_total_edr": row["ours_total_edr"],
            "milp_total_edr": row["milp_total_edr"],
        }, ensure_ascii=False), flush=True)

    summary = summarize(rows)
    write_csv(RAW_OUTPUT, rows)
    write_csv(SUMMARY_OUTPUT, summary)
    JSON_OUTPUT.write_text(
        json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "raw_output": str(RAW_OUTPUT),
        "summary_output": str(SUMMARY_OUTPUT),
        "json_output": str(JSON_OUTPUT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
