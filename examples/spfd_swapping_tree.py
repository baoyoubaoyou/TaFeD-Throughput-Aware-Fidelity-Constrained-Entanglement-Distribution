"""Run SPFD, optimal swapping trees, and PF resource allocation."""

from pprint import pprint

from experiments.collaborative_routing import (
    allocate_spfd_end_to_end_throughput,
    build_scenario,
    optimize_spfd_swapping_trees,
    run_spfd_two_stage,
)


def main():
    scenario = build_scenario()
    spfd = run_spfd_two_stage(scenario)
    sequential_swapping = allocate_spfd_end_to_end_throughput(
        spfd,
        mutate_requests=False,
    )
    optimized = optimize_spfd_swapping_trees(spfd)
    selected = optimized.selected_record.throughput_result
    pprint({
        "tree_iterations": optimized.iterations,
        "tree_converged": optimized.converged,
        "tree_stop_reason": optimized.stop_reason,
        "sequential_total_edr": sequential_swapping.total_edr,
        "optimized_tree_total_edr": selected.total_edr,
        "sequential_minimum_edr": sequential_swapping.minimum_request_edr,
        "optimized_tree_minimum_edr": selected.minimum_request_edr,
        "optimized_demand_satisfaction": selected.demand_satisfaction_ratio,
        "optimized_average_link_utilization": selected.average_link_utilization,
    })


if __name__ == "__main__":
    main()
