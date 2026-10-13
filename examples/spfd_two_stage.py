"""Run the two-stage SPFD baseline on the configured SimQN scenario."""

from pprint import pprint

from experiments.collaborative_routing import (
    allocate_spfd_end_to_end_throughput,
    build_scenario,
    run_spfd_two_stage,
)


def main() -> None:
    scenario = build_scenario()
    result = run_spfd_two_stage(scenario)
    throughput = allocate_spfd_end_to_end_throughput(result)
    pprint({
        "accepted_paths": result.quality_result.accepted_requests,
        "active_links": result.active_links,
        "infeasible_links": result.infeasible_links,
        "total_link_rate": result.total_link_rate,
        "minimum_link_rate": result.minimum_link_rate,
        "average_link_rate": result.average_link_rate,
        "link_rate_fairness": result.link_rate_fairness,
        "spfd_selection_objective": result.total_greedy_served_rate,
        "total_end_to_end_edr": throughput.total_edr,
        "minimum_request_edr": throughput.minimum_request_edr,
        "average_request_edr": throughput.average_request_edr,
        "demand_satisfaction_ratio": throughput.demand_satisfaction_ratio,
        "fully_satisfied_requests": throughput.fully_satisfied_requests,
        "average_link_utilization": throughput.average_link_utilization,
    })


if __name__ == "__main__":
    main()
