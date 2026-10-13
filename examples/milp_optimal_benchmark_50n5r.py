"""Run a 50-node, 5-request fixed-path MILP optimal benchmark."""

import json
from dataclasses import replace
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.collaborative_routing import (
    DEFAULT_CONFIG,
    CombinatorialThroughputConfig,
    MILPBenchmarkConfig,
    build_scenario,
    run_tree_aware_combinatorial_throughput,
    solve_milp_optimal_benchmark,
)


def experiment_config(seed=20260820):
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


def request_rows(scenario, milp_result):
    rows = []
    for item in milp_result.request_solutions:
        request = item.request
        column = item.selected_column
        rows.append({
            "request": item.request_index,
            "src": request.src.name,
            "dst": request.dest.name,
            "demand": request.attr["demand_intensity"],
            "required_fidelity": request.attr["required_fidelity"],
            "allocated_rate": item.allocated_rate,
            "satisfaction": item.satisfaction,
            "candidate_columns": len(milp_result.columns[item.request_index]),
            "path_hops": 0 if column is None else len(column.channels),
            "achieved_fidelity": None if column is None else column.achieved_fidelity,
            "tree_signature": None if column is None else column.tree.signature,
        })
    return rows


def main():
    config = experiment_config()
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
    ours_total = ours.selected_record.throughput_result.total_edr
    ours_min_satisfaction = min(
        allocation.demand_satisfaction
        for allocation in ours.selected_record.throughput_result.request_allocations.values()
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

    summary = {
        "scenario": scenario.summary(),
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
        "request_rows": request_rows(scenario, milp),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
