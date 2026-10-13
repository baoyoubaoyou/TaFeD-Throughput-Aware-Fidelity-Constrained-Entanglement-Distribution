"""Compare SPFD and the joint algorithm under one identical random seed."""

from pprint import pprint
from time import perf_counter

from experiments.collaborative_routing import (
    build_scenario,
    run_spfd_two_stage,
    run_stage_one,
)


def main() -> None:
    spfd_scenario = build_scenario()
    started = perf_counter()
    spfd = run_spfd_two_stage(spfd_scenario)
    spfd_runtime = perf_counter() - started

    joint_scenario = build_scenario()
    started = perf_counter()
    joint = run_stage_one(joint_scenario)
    joint_runtime = perf_counter() - started
    joint_configuration = joint.selected_record.configuration_result
    joint_rates = [
        decision.selected.effective_rate
        for decision in joint_configuration.decisions.values()
        if decision.selected is not None
    ]

    spfd_routes = [
        request.attr["selected_route_index"] for request in spfd_scenario.requests
    ]
    joint_routes = [
        request.attr["selected_route_index"] for request in joint_scenario.requests
    ]
    if spfd_routes != joint_routes:
        raise RuntimeError("paired algorithms did not use identical fixed paths")

    pprint({
        "same_fixed_paths": True,
        "spfd": {
            "active_links": spfd.active_links,
            "infeasible_links": spfd.infeasible_links,
            "total_link_rate": spfd.total_link_rate,
            "minimum_link_rate": spfd.minimum_link_rate,
            "average_link_rate": spfd.average_link_rate,
            "link_rate_fairness": spfd.link_rate_fairness,
            "runtime_seconds": spfd_runtime,
        },
        "joint_algorithm": {
            "active_links": joint_configuration.active_links,
            "infeasible_links": joint_configuration.infeasible_links,
            "total_link_rate": joint_configuration.total_effective_rate,
            "minimum_link_rate": min(joint_rates, default=0.0),
            "average_link_rate": (
                sum(joint_rates) / len(joint_rates) if joint_rates else 0.0
            ),
            "runtime_seconds": joint_runtime,
        },
    })


if __name__ == "__main__":
    main()
