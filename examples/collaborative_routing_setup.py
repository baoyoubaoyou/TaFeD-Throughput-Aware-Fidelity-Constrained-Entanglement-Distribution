"""Build and inspect the baseline collaborative-routing scenario."""

from pprint import pprint

from experiments.collaborative_routing import allocate_scenario_qualities, build_scenario


def main() -> None:
    scenario = build_scenario()
    quality_result = allocate_scenario_qualities(scenario)
    pprint(scenario.summary())
    pprint({
        "quality_accepted_requests": quality_result.accepted_requests,
        "quality_acceptance_rate": quality_result.acceptance_rate,
    })

    first_request = scenario.requests[0]
    pprint({
        "source": first_request.src.name,
        "destination": first_request.dest.name,
        "demand_intensity": first_request.attr["demand_intensity"],
        "required_fidelity": first_request.attr["required_fidelity"],
        "candidate_paths": first_request.attr["candidate_path_names"],
        "selected_path_index": first_request.attr["selected_route_index"],
        "selected_path": [node.name for node in first_request.attr["selected_path"]],
        "link_fidelity_requirements": first_request.attr["link_fidelity_requirements"],
        "achieved_fidelity": first_request.attr["achieved_fidelity"],
    })


if __name__ == "__main__":
    main()
