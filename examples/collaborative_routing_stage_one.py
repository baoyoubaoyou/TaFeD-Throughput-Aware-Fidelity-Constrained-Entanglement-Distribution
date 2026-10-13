"""Run the joint stage-I algorithm over reproducible random seeds."""

from dataclasses import replace
import json
import statistics

from experiments.collaborative_routing import DEFAULT_CONFIG, build_scenario, run_stage_one


DEFAULT_SEEDS = (20260812, 20260813, 20260814, 20260815, 20260816)


def summarize_seed(seed: int) -> dict:
    scenario = build_scenario(replace(DEFAULT_CONFIG, seed=seed))
    result = run_stage_one(scenario)
    final = result.final_record
    selected_record = result.selected_record
    selected = [
        decision.selected
        for decision in selected_record.configuration_result.decisions.values()
        if decision.selected is not None
    ]
    request_decisions = [
        item
        for evaluation in selected
        for item in evaluation.request_decisions
    ]
    fidelities = [evaluation.fidelity for evaluation in selected]
    return {
        "seed": seed,
        "accepted_requests": final.quality_result.accepted_requests,
        "active_links": final.configuration_result.active_links,
        "infeasible_links": final.configuration_result.infeasible_links,
        "iterations": result.iterations,
        "converged": result.converged,
        "stop_reason": result.stop_reason,
        "selected_iteration": selected_record.iteration,
        "selected_effective_rate": round(selected_record.objective, 3),
        "effective_rate_sequence": [
            round(record.objective, 3) for record in result.records
        ],
        "relative_change_sequence": [
            None if record.relative_change is None else round(record.relative_change, 4)
            for record in result.records
        ],
        "purification_round_sequence": [
            round(record.configuration_result.average_purification_rounds, 3)
            for record in result.records
        ],
        "selected_base_fidelity": {
            "minimum": round(min(fidelities), 3),
            "mean": round(statistics.mean(fidelities), 3),
            "maximum": round(max(fidelities), 3),
        },
        "selected_purification_rounds": {
            "minimum": min(item.rounds for item in request_decisions),
            "mean": round(statistics.mean(item.rounds for item in request_decisions), 3),
            "maximum": max(item.rounds for item in request_decisions),
        },
    }


def main() -> None:
    rows = [summarize_seed(seed) for seed in DEFAULT_SEEDS]
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))
    print(json.dumps({
        "seed_count": len(rows),
        "converged_runs": sum(row["converged"] for row in rows),
        "all_requests_accepted_runs": sum(
            row["accepted_requests"] == DEFAULT_CONFIG.requests.count for row in rows
        ),
        "mean_selected_effective_rate": round(statistics.mean(
            row["selected_effective_rate"] for row in rows
        ), 3),
        "mean_selected_purification_rounds": round(statistics.mean(
            row["selected_purification_rounds"]["mean"] for row in rows
        ), 3),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
