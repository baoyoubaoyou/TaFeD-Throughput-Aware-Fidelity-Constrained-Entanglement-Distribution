"""Run five strictly aligned small-scenario comparisons: ours vs MILP."""

import csv
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.collaborative_routing import (
    CombinatorialThroughputConfig,
    MILPBenchmarkConfig,
    build_scenario,
    run_tree_aware_combinatorial_throughput,
    solve_milp_optimal_benchmark,
)

from milp_strict_aligned_small import experiment_config


OUTPUT_DIR = Path(__file__).resolve().parent / "results"
JSON_PATH = OUTPUT_DIR / "milp_strict_aligned_small_five_groups.json"
CSV_PATH = OUTPUT_DIR / "milp_strict_aligned_small_five_groups.csv"


def run_one(seed: int, group_index: int) -> dict:
    config = experiment_config(seed=seed)
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
    ours_min_satisfaction = min(
        allocation.demand_satisfaction
        for allocation in ours_selected.request_allocations.values()
    )

    milp_started = perf_counter()
    milp = solve_milp_optimal_benchmark(
        scenario_milp.requests,
        config,
        MILPBenchmarkConfig(
            path_candidate_indices=None,
            maximum_purification_rounds=2,
            link_option_limit=None,
            time_limit_seconds=60.0,
            verbose=False,
        ),
    )
    milp_runtime = perf_counter() - milp_started

    total_gap = (
        100.0 * (milp.total_edr - ours_selected.total_edr) / milp.total_edr
        if milp.total_edr > 0
        else 0.0
    )
    min_gap = milp.objective_min_satisfaction - ours_min_satisfaction
    candidate_counts = {
        str(index): len(columns) for index, columns in milp.columns.items()
    }
    request_demands = [
        float(request.attr["demand_intensity"])
        for request in scenario_ours.requests
    ]

    return {
        "group": group_index,
        "seed": seed,
        "nodes": scenario_ours.summary()["nodes"],
        "quantum_links": scenario_ours.summary()["quantum_links"],
        "requests": scenario_ours.summary()["requests"],
        "candidate_paths": scenario_ours.summary()["candidate_paths"],
        "minimum_path_hops": scenario_ours.summary()["minimum_path_hops"],
        "maximum_path_hops": scenario_ours.summary()["maximum_path_hops"],
        "request_demands": request_demands,
        "total_demand": sum(request_demands),
        "ours_total_edr": ours_selected.total_edr,
        "ours_min_satisfaction": ours_min_satisfaction,
        "ours_runtime_seconds": ours_runtime,
        "milp_total_edr": milp.total_edr,
        "milp_min_satisfaction": milp.objective_min_satisfaction,
        "milp_runtime_seconds": milp_runtime,
        "milp_gurobi_runtime_seconds": milp.runtime_seconds,
        "total_gap_percent_vs_milp": total_gap,
        "min_satisfaction_gap": min_gap,
        "milp_candidate_counts": candidate_counts,
        "stage_one_status": milp.stage_one_status,
        "stage_two_status": milp.stage_two_status,
    }


def main() -> None:
    rows = []
    seed = 20260825
    while len(rows) < 5:
        group_index = len(rows) + 1
        try:
            row = run_one(seed, group_index)
        except RuntimeError as error:
            print(f"skip seed={seed}: {error}")
            seed += 1
            continue
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
        seed += 1

    totals = [row["total_gap_percent_vs_milp"] for row in rows]
    min_gaps = [row["min_satisfaction_gap"] for row in rows]
    summary = {
        "groups": len(rows),
        "average_total_gap_percent_vs_milp": sum(totals) / len(totals),
        "maximum_total_gap_percent_vs_milp": max(totals),
        "minimum_total_gap_percent_vs_milp": min(totals),
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
        flat["milp_candidate_counts"] = json.dumps(
            row["milp_candidate_counts"],
            ensure_ascii=False,
        )
        flat_rows.append(flat)
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0].keys()))
        writer.writeheader()
        writer.writerows(flat_rows)

    print(json.dumps({"summary": summary, "json": str(JSON_PATH), "csv": str(CSV_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
