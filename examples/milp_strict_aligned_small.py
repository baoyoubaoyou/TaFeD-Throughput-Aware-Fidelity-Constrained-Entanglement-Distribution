"""Strictly aligned small-scenario comparison: ours vs MILP."""

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


def experiment_config(seed=20260825):
    config = replace(
        DEFAULT_CONFIG,
        seed=seed,
        topology=replace(
            DEFAULT_CONFIG.topology,
            node_count=10,
            alpha=0.75,
            beta=0.55,
        ),
        requests=replace(
            DEFAULT_CONFIG.requests,
            count=2,
            demand_min=45,
            demand_max=70,
            fidelity_min=0.83,
            fidelity_max=0.88,
        ),
        routing=replace(
            DEFAULT_CONFIG.routing,
            k=1,
            min_hops=3,
            max_hops=3,
            shortest_hop_quotas=((3, 2),),
            require_k_paths=True,
        ),
        link_configuration_search=replace(
            DEFAULT_CONFIG.link_configuration_search,
            coarse_step=0.10,
            fine_step=0.10,
            retained_coarse_regions=1,
        ),
        links=replace(
            DEFAULT_CONFIG.links,
            base_generation_capacity=10000.0,
            rate_multiplier_min=0.8,
            rate_multiplier_max=1.2,
        ),
        purification=replace(
            DEFAULT_CONFIG.purification,
            maximum_rounds=2,
        ),
    )
    config.validate()
    return config


def main():
    config = experiment_config()
    scenario_ours = build_scenario(config)
    scenario_milp = build_scenario(config)

    ours_started = perf_counter()
    ours = run_tree_aware_combinatorial_throughput(
        scenario_ours,
        CombinatorialThroughputConfig(
            maximum_iterations=2,
            maximum_block_links=1,
            candidates_per_link=2,
        ),
        mutate_requests=False,
    )
    ours_runtime = perf_counter() - ours_started
    ours_selected = ours.selected_record.throughput_result

    milp_started = perf_counter()
    milp = solve_milp_optimal_benchmark(
        scenario_milp.requests,
        config,
        MILPBenchmarkConfig(
            path_candidate_indices=None,
            maximum_purification_rounds=2,
            link_option_limit=None,
            time_limit_seconds=60.0,
            verbose=True,
        ),
    )
    milp_runtime = perf_counter() - milp_started

    result = {
        "scenario": scenario_ours.summary(),
        "ours_total_edr": ours_selected.total_edr,
        "ours_min_satisfaction": min(
            allocation.demand_satisfaction
            for allocation in ours_selected.request_allocations.values()
        ),
        "ours_runtime_seconds": ours_runtime,
        "milp_total_edr": milp.total_edr,
        "milp_min_satisfaction": milp.objective_min_satisfaction,
        "milp_runtime_seconds": milp_runtime,
        "milp_gurobi_runtime_seconds": milp.runtime_seconds,
        "total_gap_percent_vs_milp": (
            100.0 * (milp.total_edr - ours_selected.total_edr) / milp.total_edr
            if milp.total_edr > 0 else 0.0
        ),
        "min_satisfaction_gap": (
            milp.objective_min_satisfaction
            - min(
                allocation.demand_satisfaction
                for allocation in ours_selected.request_allocations.values()
            )
        ),
        "milp_candidate_counts": {
            str(index): len(columns) for index, columns in milp.columns.items()
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
