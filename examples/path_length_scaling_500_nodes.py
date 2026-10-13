"""Fixed-path-length sensitivity for swapping-tree performance."""

import csv
import json
from dataclasses import replace
from pathlib import Path
import random
import statistics

from experiments.collaborative_routing import DEFAULT_CONFIG
from experiments.collaborative_routing.scenario import (
    Scenario,
    _candidate_route_names,
    _configure_links,
    _configure_nodes,
)
import examples.node_scaling_five_algorithms as node_scaling_helpers
from examples.node_scaling_five_algorithms import (
    ALGORITHMS, METRICS, run_joint_no_tree, run_joint_tree, run_legacy_baselines, run_spfd_variants,
)
from qns.network.network import QuantumNetwork
from qns.network.route.yen import YenKShortestRouteAlgorithm
from qns.network.topology.topo import ClassicTopology
from qns.network.topology.waxmantopo import WaxmanTopology
from qns.utils.rnd import get_rand, get_randint, set_seed

NODE_COUNT = 500
REQUEST_COUNT = 10
HOP_COUNTS = tuple(range(2, 9))
SEEDS = tuple(range(20260812, 20260912))
RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "path_length_scaling_500_nodes_with_baselines_100seeds_raw.csv"
SUMMARY = RESULTS / "path_length_scaling_500_nodes_with_baselines_100seeds_summary.csv"
COMPARISON = RESULTS / "path_length_scaling_500_nodes_with_baselines_100seeds_comparison.csv"
REPORT = RESULTS / "path_length_scaling_500_nodes_with_baselines_100seeds_report.md"
EXPERIMENT_ALGORITHMS = (
    "SPFD_no_tree",
    "SPFD_optimized_tree",
    "Joint_no_tree",
    "Joint_optimized_tree_fast",
)


def config_for(hops, seed):
    target_alpha_nodes = 32.0 + 8.0 * (NODE_COUNT - 100.0) / 400.0
    config = replace(
        DEFAULT_CONFIG,
        seed=seed,
        topology=replace(
            DEFAULT_CONFIG.topology,
            node_count=NODE_COUNT,
            alpha=max(0.12, target_alpha_nodes / NODE_COUNT),
        ),
        requests=replace(DEFAULT_CONFIG.requests, count=REQUEST_COUNT),
        routing=replace(
            DEFAULT_CONFIG.routing,
            # Select requests by their shortest-path hop count while allowing
            # Yen's K=3 query to retain longer alternate candidates.
            min_hops=2,
            max_hops=8,
            shortest_hop_quotas=((hops, REQUEST_COUNT),),
            require_k_paths=False,
        ),
    )
    config.validate()
    return config


def _adjacency(network):
    graph = {node: [] for node in network.nodes}
    for channel in network.qchannels:
        if len(channel.node_list) != 2:
            continue
        node_a, node_b = channel.node_list
        graph[node_a].append(node_b)
        graph[node_b].append(node_a)
    return graph


def _fixed_length_paths(network, hops, count, seed):
    graph = _adjacency(network)
    rng = random.Random(seed * 1009 + hops * 9173)
    nodes = list(network.nodes)
    node_index = {node: index for index, node in enumerate(nodes)}
    paths = []
    used_pairs = set()
    max_attempts = max(100_000, count * 20_000)

    for _ in range(max_attempts):
        path = [rng.choice(nodes)]
        visited = {path[0]}
        for _ in range(hops):
            candidates = [node for node in graph[path[-1]] if node not in visited]
            if not candidates:
                break
            next_node = rng.choice(candidates)
            path.append(next_node)
            visited.add(next_node)
        if len(path) != hops + 1:
            continue
        pair_key = tuple(sorted((node_index[path[0]], node_index[path[-1]])))
        if pair_key in used_pairs:
            continue
        used_pairs.add(pair_key)
        paths.append(path)
        if len(paths) >= count:
            return paths

    raise RuntimeError(
        f"generated {len(paths)} of {count} fixed {hops}-hop paths after "
        f"{max_attempts} attempts"
    )


def build_fixed_path_scenario(config=DEFAULT_CONFIG):
    config.validate()
    set_seed(config.seed)
    route = YenKShortestRouteAlgorithm(
        k=config.routing.k,
        min_hops=config.routing.min_hops,
        max_hops=config.routing.max_hops,
        max_candidates=config.routing.max_candidates,
    )
    topology = WaxmanTopology(
        nodes_number=config.topology.node_count,
        size=config.topology.size_m,
        alpha=config.topology.alpha,
        beta=config.topology.beta,
        memory_args=None,
    )
    network = QuantumNetwork(
        topo=topology,
        route=route,
        classic_topo=ClassicTopology.Follow,
        name="collaborative-routing-fixed-path-length",
    )
    _configure_links(network, config)
    _configure_nodes(network, config)
    network.build_route()

    hops = int(config.routing.shortest_hop_quotas[0][0])
    paths = _fixed_length_paths(network, hops, config.requests.count, config.seed)
    requests = []
    for path in paths:
        candidate_routes = [(float(hops), path[1], path[:])]
        attr = {
            "demand_intensity": int(get_randint(
                config.requests.demand_min,
                config.requests.demand_max,
            )),
            "required_fidelity": get_rand(
                config.requests.fidelity_min,
                config.requests.fidelity_max,
            ),
            "edr_upper_bound": config.requests.edr_upper_bound,
            "shortest_path_hops": hops,
            "fixed_candidate_path_hops": hops,
            "path_generation_mode": "fixed_candidate_path",
            "candidate_routes": candidate_routes,
            "candidate_path_names": _candidate_route_names(candidate_routes),
        }
        network.add_request(src=path[0], dest=path[-1], attr=attr)
        requests.append(network.requests[-1])

    return Scenario(network=network, route=route, requests=requests, config=config)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows):
    output = []
    for hops in HOP_COUNTS:
        for algorithm in EXPERIMENT_ALGORITHMS:
            group = [r for r in rows if r["hop_count"] == hops and r["algorithm"] == algorithm]
            item = {"node_count": NODE_COUNT, "request_count": REQUEST_COUNT, "hop_count": hops, "algorithm": algorithm, "repetitions": len(group)}
            for metric in METRICS:
                values = [float(r[metric]) for r in group]
                item[f"{metric}_mean"] = statistics.fmean(values)
                item[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
            output.append(item)
    return output


def compare(summary):
    pairs = (("Joint_no_tree", "SPFD_no_tree"), ("Joint_optimized_tree_fast", "SPFD_optimized_tree"), ("Joint_optimized_tree_fast", "SPFD_no_tree"), ("Joint_optimized_tree_fast", "Joint_no_tree"))
    metrics = ("total_edr", "minimum_request_edr", "jain_fairness", "demand_satisfaction_ratio", "request_acceptance_rate")
    output = []
    for hops in HOP_COUNTS:
        table = {r["algorithm"]: r for r in summary if r["hop_count"] == hops}
        for algorithm, baseline in pairs:
            item = {"hop_count": hops, "comparison": f"{algorithm}_vs_{baseline}"}
            for metric in metrics:
                new = float(table[algorithm][f"{metric}_mean"])
                old = float(table[baseline][f"{metric}_mean"])
                item[f"{metric}_change_percent"] = 100 * (new / old - 1) if old else 0.0
            output.append(item)
    return output


def main():
    node_scaling_helpers.build_scenario = build_fixed_path_scenario
    rows = []
    if RAW.exists():
        with RAW.open(encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            row["hop_count"] = int(row["hop_count"])
            row["seed"] = int(row["seed"])
            for metric in METRICS:
                row[metric] = float(row[metric])
    completed = {(r["hop_count"], r["seed"]) for r in rows}
    for hops in HOP_COUNTS:
        for seed in SEEDS:
            if (hops, seed) in completed:
                continue
            config = config_for(hops, seed)
            current = []
            current.extend(run_spfd_variants(config))
            current.append(run_joint_no_tree(config))
            current.append(run_joint_tree(config, fast=True))
            for row in current:
                row["hop_count"] = hops
            rows.extend(current)
            write_csv(RAW, rows)
            print(json.dumps({"hop_count": hops, "seed": seed, "total_edr": {r["algorithm"]: round(r["total_edr"], 3) for r in current}}, ensure_ascii=False), flush=True)
    summary = summarize(rows)
    comparison = compare(summary)
    write_csv(SUMMARY, summary)
    write_csv(COMPARISON, comparison)
    REPORT.write_text(json.dumps({"summary": summary, "comparison": comparison}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"raw": str(RAW), "summary": str(SUMMARY), "comparison": str(COMPARISON), "report": str(REPORT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
