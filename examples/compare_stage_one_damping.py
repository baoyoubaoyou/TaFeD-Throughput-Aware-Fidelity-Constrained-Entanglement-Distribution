"""Compare the preserved fixed-damping baseline with adaptive damping."""

from collections import Counter
from dataclasses import replace
import json
import statistics

from experiments.collaborative_routing import (
    DEFAULT_CONFIG,
    adaptive_damping_config,
    build_scenario,
    fixed_damping_config,
    run_stage_one,
)


SEEDS = (20260812, 20260813, 20260814, 20260815, 20260816)


def run_variant(name, make_config):
    rows = []
    for seed in SEEDS:
        config = make_config(replace(DEFAULT_CONFIG, seed=seed))
        result = run_stage_one(build_scenario(config))
        selected = result.selected_record
        rows.append({
            "variant": name,
            "seed": seed,
            "accepted_requests": selected.quality_result.accepted_requests,
            "iterations": result.iterations,
            "converged": result.converged,
            "selected_iteration": selected.iteration,
            "minimum_request_capacity": round(selected.minimum_request_capacity, 6),
            "total_request_capacity": round(selected.total_request_capacity, 3),
            "total_link_effective_rate": round(selected.objective, 3),
            "average_purification_rounds": round(
                selected.configuration_result.average_purification_rounds,
                3,
            ),
            "relaxation_counts": dict(Counter(
                record.selected_relaxation for record in result.records[1:]
            )),
        })
    return rows


def aggregate(name, rows):
    return {
        "variant": name,
        "converged_runs": sum(row["converged"] for row in rows),
        "mean_minimum_request_capacity": round(statistics.mean(
            row["minimum_request_capacity"] for row in rows
        ), 6),
        "mean_total_request_capacity": round(statistics.mean(
            row["total_request_capacity"] for row in rows
        ), 3),
        "mean_total_link_effective_rate": round(statistics.mean(
            row["total_link_effective_rate"] for row in rows
        ), 3),
        "mean_purification_rounds": round(statistics.mean(
            row["average_purification_rounds"] for row in rows
        ), 3),
    }


def main():
    fixed_rows = run_variant("fixed_0.2", fixed_damping_config)
    adaptive_rows = run_variant("adaptive", adaptive_damping_config)
    for row in fixed_rows + adaptive_rows:
        print(json.dumps(row, ensure_ascii=False))
    print(json.dumps(aggregate("fixed_0.2", fixed_rows), ensure_ascii=False))
    print(json.dumps(aggregate("adaptive", adaptive_rows), ensure_ascii=False))


if __name__ == "__main__":
    main()
