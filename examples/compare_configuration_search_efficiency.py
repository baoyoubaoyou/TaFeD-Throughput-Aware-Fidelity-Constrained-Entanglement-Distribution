"""Paired benchmark for exact 0.001-grid configuration-search acceleration."""

import csv
import json
from contextlib import contextmanager
from pathlib import Path
import statistics
from time import perf_counter

from experiments.collaborative_routing import (
    CombinatorialThroughputConfig,
    build_scenario,
    run_tree_aware_combinatorial_throughput,
)
from experiments.collaborative_routing import bottleneck_optimization as bottleneck
from experiments.collaborative_routing import combinatorial_throughput_optimization as combinatorial
from experiments.collaborative_routing import link_configuration as link_configuration
from experiments.collaborative_routing import marginal_throughput_optimization as marginal
from examples.request_scaling_tree_comparison import SEEDS, experiment_config


REQUEST_COUNT = 20
RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "configuration_search_efficiency_raw.csv"
SUMMARY = RESULTS / "configuration_search_efficiency_summary.csv"
JSON_OUTPUT = RESULTS / "configuration_search_efficiency.json"


def _legacy_find(point, required_fidelity):
    return next(
        (plan for plan in point.plans if plan.output_fidelity >= required_fidelity),
        None,
    )


def _legacy_batch(channel, requirements, points):
    return [
        link_configuration.evaluate_lookup_configuration(
            channel, requirements, point
        )
        for point in points
    ]


@contextmanager
def legacy_configuration_search():
    old_find = link_configuration.find_minimum_lookup_plan
    old_functions = {
        link_configuration: link_configuration.evaluate_lookup_configurations,
        combinatorial: combinatorial.evaluate_lookup_configurations,
        marginal: marginal.evaluate_lookup_configurations,
        bottleneck: bottleneck.evaluate_lookup_configurations,
    }
    link_configuration.find_minimum_lookup_plan = _legacy_find
    for module in old_functions:
        module.evaluate_lookup_configurations = _legacy_batch
    try:
        yield
    finally:
        link_configuration.find_minimum_lookup_plan = old_find
        for module, function in old_functions.items():
            module.evaluate_lookup_configurations = function


def _run(seed, legacy):
    scenario = build_scenario(experiment_config(REQUEST_COUNT, seed))
    started = perf_counter()
    if legacy:
        with legacy_configuration_search():
            result = run_tree_aware_combinatorial_throughput(
                scenario,
                CombinatorialThroughputConfig(maximum_iterations=10),
                mutate_requests=False,
            )
    else:
        result = run_tree_aware_combinatorial_throughput(
            scenario,
            CombinatorialThroughputConfig(maximum_iterations=10),
            mutate_requests=False,
        )
    runtime = perf_counter() - started
    selected = result.selected_record
    request_index = {
        id(request): index for index, request in enumerate(scenario.requests)
    }
    configuration_signature = tuple(sorted(
        (
            channel.name,
            decision.selected.fidelity,
            tuple(
                (
                    request_index[id(item.request)],
                    item.rounds,
                    item.output_fidelity,
                    item.expected_raw_pairs,
                )
                for item in decision.selected.request_decisions
            ),
        )
        for channel, decision in selected.configuration_result.decisions.items()
    ))
    tree_signature = tuple(
        selected.fixed_trees[id(request)].signature
        for request in scenario.requests
    )
    request_rates = tuple(
        selected.throughput_result.request_allocations[id(request)].allocated_rate
        for request in scenario.requests
    )
    return {
        "runtime": runtime,
        "total_edr": selected.throughput_result.total_edr,
        "minimum_edr": selected.throughput_result.minimum_request_edr,
        "request_rates": request_rates,
        "configuration_signature": configuration_signature,
        "tree_signature": tree_signature,
    }


def main():
    rows = []
    for seed in SEEDS:
        before = _run(seed, legacy=True)
        after = _run(seed, legacy=False)
        exactly_equal = all((
            before["total_edr"] == after["total_edr"],
            before["minimum_edr"] == after["minimum_edr"],
            before["request_rates"] == after["request_rates"],
            before["configuration_signature"] == after["configuration_signature"],
            before["tree_signature"] == after["tree_signature"],
        ))
        row = {
            "node_count": 100,
            "request_count": REQUEST_COUNT,
            "seed": seed,
            "before_runtime_seconds": before["runtime"],
            "after_runtime_seconds": after["runtime"],
            "speedup_ratio": before["runtime"] / after["runtime"],
            "runtime_reduction_percent": 100.0 * (
                1.0 - after["runtime"] / before["runtime"]
            ),
            "before_total_edr": before["total_edr"],
            "after_total_edr": after["total_edr"],
            "before_minimum_edr": before["minimum_edr"],
            "after_minimum_edr": after["minimum_edr"],
            "exactly_equal": exactly_equal,
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    summary = {
        "node_count": 100,
        "request_count": REQUEST_COUNT,
        "repetitions": len(rows),
        "all_outputs_exactly_equal": all(row["exactly_equal"] for row in rows),
        "before_runtime_mean": statistics.fmean(
            row["before_runtime_seconds"] for row in rows
        ),
        "after_runtime_mean": statistics.fmean(
            row["after_runtime_seconds"] for row in rows
        ),
    }
    summary["speedup_ratio_from_means"] = (
        summary["before_runtime_mean"] / summary["after_runtime_mean"]
    )
    summary["runtime_reduction_percent_from_means"] = 100.0 * (
        1.0 - summary["after_runtime_mean"] / summary["before_runtime_mean"]
    )
    RESULTS.mkdir(parents=True, exist_ok=True)
    with RAW.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with SUMMARY.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary))
        writer.writeheader()
        writer.writerow(summary)
    JSON_OUTPUT.write_text(
        json.dumps({"raw": rows, "summary": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
