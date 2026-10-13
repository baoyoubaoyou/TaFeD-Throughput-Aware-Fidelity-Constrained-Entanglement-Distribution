"""Build a reproducible SimQN scenario from the paper's baseline settings."""

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Tuple

from qns.entity.memory.memory import QuantumMemory
from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.network import QuantumNetwork
from qns.network.requests import Request
from qns.network.route.yen import YenKShortestRouteAlgorithm
from qns.network.topology.topo import ClassicTopology
from qns.network.topology.waxmantopo import WaxmanTopology
from qns.utils.rnd import get_rand, get_randint, set_seed

from experiments.collaborative_routing.config import DEFAULT_CONFIG, ExperimentConfig


@dataclass
class Scenario:
    network: QuantumNetwork
    route: YenKShortestRouteAlgorithm
    requests: List[Request]
    config: ExperimentConfig

    def summary(self) -> Dict:
        degrees = [len(node.qchannels) for node in self.network.nodes]
        hop_counts = [
            len(candidate[2]) - 1
            for request in self.requests
            for candidate in request.attr["candidate_routes"]
        ]
        shortest_hop_distribution = {}
        for request in self.requests:
            hops = request.attr["shortest_path_hops"]
            shortest_hop_distribution[hops] = shortest_hop_distribution.get(hops, 0) + 1
        return {
            "nodes": len(self.network.nodes),
            "quantum_links": len(self.network.qchannels),
            "average_degree": sum(degrees) / len(degrees),
            "requests": len(self.requests),
            "candidate_paths": sum(len(r.attr["candidate_routes"]) for r in self.requests),
            "minimum_path_hops": min(hop_counts),
            "maximum_path_hops": max(hop_counts),
            "shortest_hop_distribution": shortest_hop_distribution,
            "metrics": list(self.config.metrics),
        }


def _configure_links(network: QuantumNetwork, config: ExperimentConfig) -> None:
    """Attach a formula-derived heterogeneous fidelity-rate table to each channel."""
    for channel in network.qchannels:
        rate_multiplier = get_rand(
            config.links.rate_multiplier_min,
            config.links.rate_multiplier_max,
        )
        fidelity_scale = get_rand(
            config.links.fidelity_scale_min,
            config.links.fidelity_scale_max,
        )
        table = []
        fidelity_span = config.links.maximum_fidelity - config.links.minimum_fidelity
        for index, base_fidelity in enumerate(config.links.fidelity_points):
            # Warp the normalized quality interval while keeping both physical
            # endpoints fixed. Direct multiplication could make fidelity > 1.
            normalized = (base_fidelity - config.links.minimum_fidelity) / fidelity_span
            fidelity = config.links.minimum_fidelity + fidelity_span * normalized ** fidelity_scale
            table.append({
                "id": f"C{index + 1}",
                "fidelity": fidelity,
                "raw_rate": config.links.raw_rate(fidelity) * rate_multiplier,
            })

        channel.fidelity_rate_table = table
        channel.rate_multiplier = rate_multiplier
        channel.generation_capacity = config.links.base_generation_capacity * rate_multiplier
        channel.fidelity_scale = fidelity_scale
        set_link_working_point(channel, 0)


def set_link_working_point(channel: QuantumChannel, profile_index: int) -> None:
    """Activate one point from a channel's fidelity-rate configuration table."""
    table = getattr(channel, "fidelity_rate_table", None)
    if table is None:
        raise ValueError("channel does not have a fidelity-rate table")
    if profile_index < 0 or profile_index >= len(table):
        raise IndexError("link profile index out of range")

    point = table[profile_index]
    channel.active_profile_index = profile_index
    channel.fidelity = point["fidelity"]
    channel.raw_entanglement_rate = point["raw_rate"]
    channel.bandwidth = point["raw_rate"]


def _configure_nodes(network: QuantumNetwork, config: ExperimentConfig) -> None:
    for node in network.nodes:
        capacity = int(get_randint(config.memory.capacity_min, config.memory.capacity_max))
        memory = QuantumMemory(
            name=f"m-{node.name}",
            node=node,
            capacity=capacity,
            decoherence_rate=config.memory.decoherence_rate,
            delay=config.memory.read_write_delay,
        )
        node.add_memory(memory)
        node.memory_capacity = capacity
        node.swap_success_probability = get_rand(
            config.swapping.success_probability_min,
            config.swapping.success_probability_max,
        )
        node.swap_quality_factor = config.swapping.quality_factor

    # Treat memory bandwidth as a node-level shared resource.  The simple
    # equal-share policy keeps the experiment focused on routing rather than
    # on a separate memory-scheduling algorithm.
    for node in network.nodes:
        node.memory_bandwidth = node.memory_capacity * config.memory.rate_per_slot
        degree = len(node.qchannels)
        node.memory_bandwidth_per_link = (
            node.memory_bandwidth / degree if degree > 0 else 0.0
        )
    for channel in network.qchannels:
        endpoint_shares = [
            float(getattr(node, "memory_bandwidth_per_link", 0.0))
            for node in channel.node_list
        ]
        channel.memory_bandwidth = min(endpoint_shares, default=0.0)
        channel.memory_capacity = min(
            (int(getattr(node, "memory_capacity", 0)) for node in channel.node_list),
            default=0,
        )


def _candidate_route_names(routes: List[Tuple[float, QNode, List[QNode]]]) -> List[List[str]]:
    return [[node.name for node in route[2]] for route in routes]


def _shortest_hop_count(src: QNode, dest: QNode) -> int:
    """Return the unfiltered minimum hop count between two network nodes."""
    queue = deque([(src, 0)])
    visited = {src}
    while queue:
        node, hops = queue.popleft()
        if node == dest:
            return hops
        for channel in node.qchannels:
            if len(channel.node_list) != 2:
                continue
            neighbor = channel.node_list[0] if channel.node_list[1] == node else channel.node_list[1]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, hops + 1))
    return -1


def _generate_requests(
    network: QuantumNetwork,
    route: YenKShortestRouteAlgorithm,
    config: ExperimentConfig,
) -> List[Request]:
    requests = []
    used_pairs = set()
    attempts = 0
    max_attempts = max(10_000, config.requests.count * 1000)

    target_hops = [
        hop
        for hop, count in sorted(config.routing.shortest_hop_quotas, reverse=True)
        for _ in range(count)
    ]

    while len(requests) < config.requests.count and attempts < max_attempts:
        attempts += 1
        required_shortest_hops = target_hops[len(requests)]
        src_index = int(get_randint(0, len(network.nodes) - 1))
        dst_index = int(get_randint(0, len(network.nodes) - 1))
        if src_index == dst_index:
            continue
        pair_key = tuple(sorted((src_index, dst_index)))
        if pair_key in used_pairs:
            continue

        src = network.nodes[src_index]
        dest = network.nodes[dst_index]
        shortest_path_hops = _shortest_hop_count(src, dest)
        if shortest_path_hops != required_shortest_hops:
            continue
        candidate_routes = route.query(src, dest)
        required_count = config.routing.k if config.routing.require_k_paths else 1
        if len(candidate_routes) < required_count:
            continue

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
            "shortest_path_hops": shortest_path_hops,
            "candidate_routes": candidate_routes,
            "candidate_path_names": _candidate_route_names(candidate_routes),
        }
        network.add_request(src=src, dest=dest, attr=attr)
        requests.append(network.requests[-1])
        used_pairs.add(pair_key)

    if len(requests) != config.requests.count:
        raise RuntimeError(
            f"generated {len(requests)} of {config.requests.count} requests after "
            f"{max_attempts} attempts; relax hop or K-path constraints"
        )
    return requests


def build_scenario(config: ExperimentConfig = DEFAULT_CONFIG) -> Scenario:
    """Build, parameterize, and route the baseline 100-node experiment."""
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
        name="collaborative-routing-baseline",
    )
    _configure_links(network, config)
    _configure_nodes(network, config)
    network.build_route()
    requests = _generate_requests(network, route, config)
    return Scenario(network=network, route=route, requests=requests, config=config)
