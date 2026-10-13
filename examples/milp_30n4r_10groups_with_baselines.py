"""30-node / 4-request strict-aligned benchmark with baselines and MILP."""

import csv
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baselines.legacy_quantum_routing import run_baseline
from baselines.legacy_quantum_routing.runtime import LegacyRuntimeConfig
from examples.milp_strict_aligned_moderate_normal import experiment_config
from experiments.collaborative_routing import (
    CombinatorialThroughputConfig,
    MILPBenchmarkConfig,
    allocate_fixed_swapping_tree_throughput,
    build_scenario,
    optimize_spfd_swapping_trees,
    run_combinatorial_throughput_optimized_stage_one,
    run_spfd_two_stage,
    run_tree_aware_combinatorial_throughput,
    solve_milp_optimal_benchmark,
)


OUTPUT_DIR = Path(__file__).resolve().parent / "results"
RAW_CSV = OUTPUT_DIR / "milp_30n4r_10groups_with_baselines_raw.csv"
SUMMARY_CSV = OUTPUT_DIR / "milp_30n4r_10groups_with_baselines_summary.csv"
JSON_PATH = OUTPUT_DIR / "milp_30n4r_10groups_with_baselines.json"

TARGET_GROUPS = 10
START_SEED = 20260905
BASELINE_RUNTIME = LegacyRuntimeConfig(
    mode="reimplemented",
    max_candidate_paths=3,
    max_reallocation_rounds=30,
)


def make_config(seed: int):
    return experiment_config(
        seed=seed,
        node_count=30,
        request_count=4,
        alpha=0.50,
        beta=0.25,
    )


def jain_from_rates(rates):
    denominator = len(rates) * sum(rate * rate for rate in rates)
    return sum(rates) ** 2 / denominator if denominator else 0.0


def min_satisfaction(throughput_result) -> float:
    return min(
        allocation.demand_satisfaction
        for allocation in throughput_result.request_allocations.values()
    )


def throughput_row(group, seed, algorithm, scenario, throughput, runtime, iterations):
    return {
        "group": group,
        "seed": seed,
        "algorithm": algorithm,
        "nodes": scenario.config.topology.node_count,
        "quantum_links": len(scenario.network.qchannels),
        "requests": scenario.config.requests.count,
        "candidate_paths": scenario.summary()["candidate_paths"],
        "total_demand": sum(
            float(request.attr["demand_intensity"])
            for request in scenario.requests
        ),
        "total_edr": throughput.total_edr,
        "minimum_request_edr": throughput.minimum_request_edr,
        "average_request_edr": throughput.average_request_edr,
        "min_satisfaction": min_satisfaction(throughput),
        "demand_satisfaction_ratio": throughput.demand_satisfaction_ratio,
        "request_acceptance_rate": throughput.request_acceptance_rate,
        "jain_fairness": jain_from_rates([
            item.allocated_rate
            for item in throughput.request_allocations.values()
        ]),
        "average_link_utilization": throughput.average_link_utilization,
        "maximum_link_utilization": throughput.maximum_link_utilization,
        "runtime_seconds": runtime,
        "iterations": iterations,
        "milp_stage_one_status": "",
        "milp_stage_two_status": "",
        "milp_candidate_counts": "",
    }


def legacy_row(group, seed, algorithm, scenario, result):
    demands = [
        float(request.attr["demand_intensity"])
        for request in scenario.requests
    ]
    rates = result.per_request_throughput
    satisfactions = [
        rate / demand if demand > 0.0 else 0.0
        for rate, demand in zip(rates, demands)
    ]
    return {
        "group": group,
        "seed": seed,
        "algorithm": "SFTRAP" if algorithm == "SFTrap" else algorithm,
        "nodes": scenario.config.topology.node_count,
        "quantum_links": len(scenario.network.qchannels),
        "requests": scenario.config.requests.count,
        "candidate_paths": scenario.summary()["candidate_paths"],
        "total_demand": sum(demands),
        "total_edr": result.total_throughput,
        "minimum_request_edr": min(rates, default=0.0),
        "average_request_edr": sum(rates) / len(rates) if rates else 0.0,
        "min_satisfaction": min(satisfactions, default=0.0),
        "demand_satisfaction_ratio": (
            result.total_throughput / sum(demands) if demands else 0.0
        ),
        "request_acceptance_rate": (
            result.accepted_requests / len(rates) if rates else 0.0
        ),
        "jain_fairness": jain_from_rates(rates),
        "average_link_utilization": result.metadata.get(
            "average_link_utilization", 0.0
        ),
        "maximum_link_utilization": result.metadata.get(
            "maximum_link_utilization", 0.0
        ),
        "runtime_seconds": result.runtime_seconds,
        "iterations": result.metadata.get("iterations", 0),
        "milp_stage_one_status": "",
        "milp_stage_two_status": "",
        "milp_candidate_counts": "",
    }


def milp_row(group, seed, scenario, milp, runtime):
    rates = [solution.allocated_rate for solution in milp.request_solutions]
    demands = [
        float(solution.request.attr["demand_intensity"])
        for solution in milp.request_solutions
    ]
    return {
        "group": group,
        "seed": seed,
        "algorithm": "MILP",
        "nodes": scenario.config.topology.node_count,
        "quantum_links": len(scenario.network.qchannels),
        "requests": scenario.config.requests.count,
        "candidate_paths": scenario.summary()["candidate_paths"],
        "total_demand": sum(demands),
        "total_edr": milp.total_edr,
        "minimum_request_edr": min(rates, default=0.0),
        "average_request_edr": (
            sum(rates) / len(rates) if rates else 0.0
        ),
        "min_satisfaction": milp.objective_min_satisfaction,
        "demand_satisfaction_ratio": (
            milp.total_edr / sum(demands) if demands else 0.0
        ),
        "request_acceptance_rate": sum(
            1 for rate, demand in zip(rates, demands)
            if rate >= demand - 1e-9
        ) / len(demands) if demands else 0.0,
        "jain_fairness": jain_from_rates(rates),
        "average_link_utilization": (
            sum(
                milp.link_raw_consumed[channel]
                / milp.link_raw_capacity[channel]
                for channel in milp.link_raw_capacity
                if milp.link_raw_capacity[channel] > 0.0
            ) / len(milp.link_raw_capacity)
            if milp.link_raw_capacity else 0.0
        ),
        "maximum_link_utilization": max(
            (
                milp.link_raw_consumed[channel]
                / milp.link_raw_capacity[channel]
                for channel in milp.link_raw_capacity
                if milp.link_raw_capacity[channel] > 0.0
            ),
            default=0.0,
        ),
        "runtime_seconds": runtime,
        "iterations": 2,
        "milp_stage_one_status": milp.stage_one_status,
        "milp_stage_two_status": milp.stage_two_status,
        "milp_candidate_counts": json.dumps(
            {str(index): len(columns) for index, columns in milp.columns.items()},
            ensure_ascii=False,
        ),
    }


def run_group(group: int, seed: int):
    config = make_config(seed)
    # Build once to verify this seed can generate all required requests.
    build_scenario(config)
    rows = []

    for algorithm in ("QPath", "QLeap", "SFTrap"):
        scenario = build_scenario(config)
        result = run_baseline(scenario, algorithm, BASELINE_RUNTIME)
        rows.append(legacy_row(group, seed, algorithm, scenario, result))

    scenario = build_scenario(config)
    started = perf_counter()
    spfd = run_spfd_two_stage(scenario, mutate_requests=False)
    spfd_base_runtime = perf_counter() - started

    started = perf_counter()
    _, fixed = allocate_fixed_swapping_tree_throughput(
        spfd.quality_result,
        spfd.configuration_result,
        mutate_requests=False,
    )
    fixed_runtime = perf_counter() - started
    rows.append(throughput_row(
        group, seed, "SPFD_no_tree", scenario, fixed,
        spfd_base_runtime + fixed_runtime, 1,
    ))

    started = perf_counter()
    optimized_spfd = optimize_spfd_swapping_trees(spfd, mutate_requests=False)
    spfd_tree_runtime = perf_counter() - started
    rows.append(throughput_row(
        group, seed, "SPFD_optimized_tree", scenario,
        optimized_spfd.selected_record.throughput_result,
        spfd_base_runtime + spfd_tree_runtime,
        optimized_spfd.iterations,
    ))

    scenario = build_scenario(config)
    started = perf_counter()
    joint_no_tree = run_combinatorial_throughput_optimized_stage_one(
        scenario,
        CombinatorialThroughputConfig(
            maximum_iterations=3,
            maximum_block_links=2,
            candidates_per_link=2,
        ),
        mutate_requests=False,
    )
    rows.append(throughput_row(
        group, seed, "Joint_no_tree", scenario,
        joint_no_tree.selected_record.throughput_result,
        perf_counter() - started,
        joint_no_tree.iterations,
    ))

    scenario = build_scenario(config)
    started = perf_counter()
    ours = run_tree_aware_combinatorial_throughput(
        scenario,
        CombinatorialThroughputConfig(
            maximum_iterations=3,
            maximum_block_links=2,
            candidates_per_link=2,
        ),
        mutate_requests=False,
    )
    rows.append(throughput_row(
        group, seed, "Ours_optimized_tree", scenario,
        ours.selected_record.throughput_result,
        perf_counter() - started,
        ours.iterations,
    ))

    scenario = build_scenario(config)
    started = perf_counter()
    milp = solve_milp_optimal_benchmark(
        scenario.requests,
        config,
        MILPBenchmarkConfig(
            path_candidate_indices=None,
            maximum_purification_rounds=2,
            link_option_limit=None,
            time_limit_seconds=120.0,
            verbose=False,
        ),
    )
    rows.append(milp_row(group, seed, scenario, milp, perf_counter() - started))
    return rows


def summarize(rows):
    algorithms = sorted({row["algorithm"] for row in rows})
    output = []
    for algorithm in algorithms:
        group = [row for row in rows if row["algorithm"] == algorithm]
        output.append({
            "algorithm": algorithm,
            "runs": len(group),
            "avg_total_edr": sum(row["total_edr"] for row in group) / len(group),
            "avg_min_satisfaction": (
                sum(row["min_satisfaction"] for row in group) / len(group)
            ),
            "avg_runtime_seconds": (
                sum(row["runtime_seconds"] for row in group) / len(group)
            ),
        })
    return output


def write_outputs(rows):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with RAW_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = summarize(rows)
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)

    JSON_PATH.write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main():
    rows = []
    group = 1
    seed = START_SEED
    while group <= TARGET_GROUPS:
        try:
            current = run_group(group, seed)
        except RuntimeError as error:
            print(f"skip seed={seed}: {error}")
            seed += 1
            continue
        rows.extend(current)
        write_outputs(rows)
        milp = next(row for row in current if row["algorithm"] == "MILP")
        ours = next(row for row in current if row["algorithm"] == "Ours_optimized_tree")
        print(json.dumps({
            "group": group,
            "seed": seed,
            "ours_total_edr": ours["total_edr"],
            "milp_total_edr": milp["total_edr"],
            "gap_percent": (
                100.0 * (milp["total_edr"] - ours["total_edr"]) / milp["total_edr"]
                if milp["total_edr"] > 0 else 0.0
            ),
            "milp_runtime_seconds": milp["runtime_seconds"],
        }, ensure_ascii=False))
        group += 1
        seed += 1

    summary = write_outputs(rows)
    print(json.dumps({
        "summary": summary,
        "raw_csv": str(RAW_CSV),
        "summary_csv": str(SUMMARY_CSV),
        "json": str(JSON_PATH),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
