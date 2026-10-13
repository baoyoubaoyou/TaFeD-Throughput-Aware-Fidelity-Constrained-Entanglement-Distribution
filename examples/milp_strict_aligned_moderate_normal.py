"""Moderate-size strictly aligned normal-scenario comparison: ours vs MILP.

The scenarios are intentionally less synthetic than the congested unit test:
normal link generation capacity, 20--30 nodes, and 3--4 fixed-path requests.
The fidelity grid is still coarsened to keep the MILP finite and exactly
aligned with the heuristic's lookup grid.
"""

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


OUTPUT_DIR = Path(__file__).resolve().parent / "results"
JSON_PATH = OUTPUT_DIR / "milp_strict_aligned_moderate_normal.json"
CSV_PATH = OUTPUT_DIR / "milp_strict_aligned_moderate_normal.csv"


CASES = [
    {"case": "20n3r", "seed": 20260901, "nodes": 20, "requests": 3},
    {"case": "20n4r", "seed": 20260902, "nodes": 20, "requests": 4},
    {"case": "25n3r", "seed": 20260903, "nodes": 25, "requests": 3},
    {"case": "25n4r", "seed": 20260904, "nodes": 25, "requests": 4},
    {
        "case": "30n4r",
        "seed": 20260905,
        "nodes": 30,
        "requests": 4,
        "alpha": 0.50,
        "beta": 0.25,
    },
]


def hop_quotas(request_count: int):
    if request_count == 3:
        return ((3, 2), (4, 1))
    if request_count == 4:
        return ((3, 2), (4, 2))
    raise ValueError("this script supports 3 or 4 requests")


def experiment_config(
    seed: int,
    node_count: int,
    request_count: int,
    alpha: float = 0.70,
    beta: float = 0.45,
):
    config = replace(
        DEFAULT_CONFIG,
        seed=seed,
        topology=replace(
            DEFAULT_CONFIG.topology,
            node_count=node_count,
            alpha=alpha,
            beta=beta,
        ),
        requests=replace(
            DEFAULT_CONFIG.requests,
            count=request_count,
            demand_min=50,
            demand_max=100,
            fidelity_min=0.80,
            fidelity_max=0.93,
        ),
        routing=replace(
            DEFAULT_CONFIG.routing,
            k=1,
            min_hops=3,
            max_hops=4,
            shortest_hop_quotas=hop_quotas(request_count),
            require_k_paths=True,
        ),
        link_configuration_search=replace(
            DEFAULT_CONFIG.link_configuration_search,
            coarse_step=0.10,
            fine_step=0.10,
            retained_coarse_regions=1,
        ),
        purification=replace(
            DEFAULT_CONFIG.purification,
            maximum_rounds=2,
        ),
        links=replace(
            DEFAULT_CONFIG.links,
            base_generation_capacity=DEFAULT_CONFIG.links.base_generation_capacity,
            rate_multiplier_min=DEFAULT_CONFIG.links.rate_multiplier_min,
            rate_multiplier_max=DEFAULT_CONFIG.links.rate_multiplier_max,
        ),
    )
    config.validate()
    return config


def min_satisfaction(throughput_result) -> float:
    return min(
        allocation.demand_satisfaction
        for allocation in throughput_result.request_allocations.values()
    )


def run_case(case: dict) -> dict:
    config = experiment_config(
        seed=case["seed"],
        node_count=case["nodes"],
        request_count=case["requests"],
        alpha=case.get("alpha", 0.70),
        beta=case.get("beta", 0.45),
    )
    scenario_ours = build_scenario(config)
    scenario_milp = build_scenario(config)
    summary = scenario_ours.summary()
    request_demands = [
        float(request.attr["demand_intensity"])
        for request in scenario_ours.requests
    ]

    ours_started = perf_counter()
    ours = run_tree_aware_combinatorial_throughput(
        scenario_ours,
        CombinatorialThroughputConfig(
            maximum_iterations=3,
            maximum_block_links=2,
            candidates_per_link=2,
        ),
        mutate_requests=False,
    )
    ours_runtime = perf_counter() - ours_started
    ours_selected = ours.selected_record.throughput_result
    ours_min_sat = min_satisfaction(ours_selected)

    milp_started = perf_counter()
    milp = solve_milp_optimal_benchmark(
        scenario_milp.requests,
        config,
        MILPBenchmarkConfig(
            path_candidate_indices=None,
            maximum_purification_rounds=2,
            link_option_limit=None,
            time_limit_seconds=120.0,
            verbose=False,
        ),
    )
    milp_runtime = perf_counter() - milp_started

    total_gap = (
        100.0 * (milp.total_edr - ours_selected.total_edr) / milp.total_edr
        if milp.total_edr > 0.0
        else 0.0
    )
    return {
        "case": case["case"],
        "seed": case["seed"],
        "nodes": summary["nodes"],
        "quantum_links": summary["quantum_links"],
        "requests": summary["requests"],
        "candidate_paths": summary["candidate_paths"],
        "minimum_path_hops": summary["minimum_path_hops"],
        "maximum_path_hops": summary["maximum_path_hops"],
        "request_demands": request_demands,
        "total_demand": sum(request_demands),
        "ours_total_edr": ours_selected.total_edr,
        "ours_min_satisfaction": ours_min_sat,
        "ours_runtime_seconds": ours_runtime,
        "milp_total_edr": milp.total_edr,
        "milp_min_satisfaction": milp.objective_min_satisfaction,
        "milp_runtime_seconds": milp_runtime,
        "milp_gurobi_runtime_seconds": milp.runtime_seconds,
        "total_gap_percent_vs_milp": total_gap,
        "min_satisfaction_gap": milp.objective_min_satisfaction - ours_min_sat,
        "milp_candidate_counts": {
            str(index): len(columns) for index, columns in milp.columns.items()
        },
        "stage_one_status": milp.stage_one_status,
        "stage_two_status": milp.stage_two_status,
    }


def main() -> None:
    rows = []
    for case in CASES:
        row = None
        for attempt in range(20):
            trial = dict(case)
            trial["seed"] = case["seed"] + attempt
            try:
                row = run_case(trial)
                break
            except RuntimeError as error:
                print(f"skip case={case['case']} seed={trial['seed']}: {error}")
        if row is None:
            raise RuntimeError(f"failed to generate and solve case={case['case']}")
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    gaps = [row["total_gap_percent_vs_milp"] for row in rows]
    min_gaps = [row["min_satisfaction_gap"] for row in rows]
    summary = {
        "cases": len(rows),
        "average_total_gap_percent_vs_milp": sum(gaps) / len(gaps),
        "maximum_total_gap_percent_vs_milp": max(gaps),
        "minimum_total_gap_percent_vs_milp": min(gaps),
        "average_min_satisfaction_gap": sum(min_gaps) / len(min_gaps),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    flat_rows = []
    for row in rows:
        flat = dict(row)
        flat["request_demands"] = json.dumps(row["request_demands"], ensure_ascii=False)
        flat["milp_candidate_counts"] = json.dumps(
            row["milp_candidate_counts"],
            ensure_ascii=False,
        )
        flat_rows.append(flat)

    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0].keys()))
        writer.writeheader()
        writer.writerows(flat_rows)

    print(json.dumps(
        {"summary": summary, "json": str(JSON_PATH), "csv": str(CSV_PATH)},
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
