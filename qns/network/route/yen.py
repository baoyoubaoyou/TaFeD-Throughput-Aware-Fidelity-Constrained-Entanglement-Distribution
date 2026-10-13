"""Yen's K-shortest loopless paths for SimQN networks."""

import heapq
import itertools
import math
from typing import Callable, Dict, List, Optional, Set, Tuple, Union

from qns.entity.cchannel.cchannel import ClassicChannel
from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.route.route import NetworkRouteError, RouteImpl


Channel = Union[QuantumChannel, ClassicChannel]
RouteResult = Tuple[float, QNode, List[QNode]]


class YenKShortestRouteAlgorithm(RouteImpl):
    """Return up to ``k`` shortest loopless paths in priority order.

    ``min_hops`` and ``max_hops`` constrain the number of physical links in
    returned paths. Shorter paths are still enumerated internally so that Yen's
    ordering remains correct, but they are not returned to the caller.
    """

    def __init__(
        self,
        k: int = 3,
        metric_func: Optional[Callable[[Channel], float]] = None,
        min_hops: int = 0,
        max_hops: Optional[int] = None,
        max_candidates: int = 1000,
        name: str = "yen-k-shortest",
    ) -> None:
        super().__init__(name=name)
        if k < 1:
            raise ValueError("k must be at least 1")
        if min_hops < 0:
            raise ValueError("min_hops cannot be negative")
        if max_hops is not None and max_hops < min_hops:
            raise ValueError("max_hops must be greater than or equal to min_hops")
        if max_candidates < k:
            raise ValueError("max_candidates must be at least k")

        self.k = k
        self.metric_func = metric_func or (lambda _: 1.0)
        self.min_hops = min_hops
        self.max_hops = max_hops
        self.max_candidates = max_candidates
        self.nodes: List[QNode] = []
        self.channels: List[Channel] = []
        self._adjacency: Dict[QNode, Dict[QNode, float]] = {}
        self._cache: Dict[Tuple[QNode, QNode], List[RouteResult]] = {}

    @staticmethod
    def _edge_key(node_a: QNode, node_b: QNode) -> frozenset:
        return frozenset((node_a, node_b))

    def build(self, nodes: List[QNode], channels: List[Channel]) -> None:
        self.nodes = list(nodes)
        self.channels = list(channels)
        self._adjacency = {node: {} for node in self.nodes}
        self._cache.clear()

        for channel in self.channels:
            if len(channel.node_list) != 2:
                raise NetworkRouteError("Yen routing requires point-to-point channels")
            node_a, node_b = channel.node_list
            metric = float(self.metric_func(channel))
            if not math.isfinite(metric) or metric < 0:
                raise NetworkRouteError("channel metrics must be finite and non-negative")

            old_metric = self._adjacency[node_a].get(node_b, math.inf)
            if metric < old_metric:
                self._adjacency[node_a][node_b] = metric
                self._adjacency[node_b][node_a] = metric

    def _path_cost(self, path: List[QNode]) -> float:
        return sum(self._adjacency[path[i]][path[i + 1]] for i in range(len(path) - 1))

    def _shortest_path(
        self,
        src: QNode,
        dest: QNode,
        banned_nodes: Optional[Set[QNode]] = None,
        banned_edges: Optional[Set[frozenset]] = None,
    ) -> Optional[Tuple[float, List[QNode]]]:
        banned_nodes = banned_nodes or set()
        banned_edges = banned_edges or set()
        if src in banned_nodes or dest in banned_nodes:
            return None

        counter = itertools.count()
        heap = [(0.0, next(counter), src)]
        distance = {src: 0.0}
        previous: Dict[QNode, QNode] = {}

        while heap:
            cost, _, node = heapq.heappop(heap)
            if cost != distance.get(node):
                continue
            if node == dest:
                path = [dest]
                while path[-1] != src:
                    path.append(previous[path[-1]])
                path.reverse()
                return cost, path

            for neighbor, edge_cost in self._adjacency.get(node, {}).items():
                if neighbor in banned_nodes:
                    continue
                if self._edge_key(node, neighbor) in banned_edges:
                    continue
                new_cost = cost + edge_cost
                if new_cost < distance.get(neighbor, math.inf):
                    distance[neighbor] = new_cost
                    previous[neighbor] = node
                    heapq.heappush(heap, (new_cost, next(counter), neighbor))
        return None

    def _is_eligible(self, path: List[QNode]) -> bool:
        hops = len(path) - 1
        if hops < self.min_hops:
            return False
        return self.max_hops is None or hops <= self.max_hops

    def _calculate_paths(self, src: QNode, dest: QNode) -> List[RouteResult]:
        first = self._shortest_path(src, dest)
        if first is None:
            return []

        accepted: List[Tuple[float, List[QNode]]] = [first]
        accepted_keys = {tuple(first[1])}
        candidate_heap = []
        candidate_keys = set()
        result: List[RouteResult] = []
        counter = itertools.count()
        examined = 0

        if self._is_eligible(first[1]):
            result.append((first[0], first[1][1], first[1][:]))

        while len(result) < self.k and examined < self.max_candidates:
            previous_path = accepted[-1][1]
            for spur_index in range(len(previous_path) - 1):
                root_path = previous_path[:spur_index + 1]
                spur_node = root_path[-1]
                banned_edges: Set[frozenset] = set()

                for _, known_path in accepted:
                    if len(known_path) > spur_index and known_path[:spur_index + 1] == root_path:
                        banned_edges.add(self._edge_key(known_path[spur_index], known_path[spur_index + 1]))

                spur = self._shortest_path(
                    spur_node,
                    dest,
                    banned_nodes=set(root_path[:-1]),
                    banned_edges=banned_edges,
                )
                if spur is None:
                    continue

                total_path = root_path[:-1] + spur[1]
                if self.max_hops is not None and len(total_path) - 1 > self.max_hops:
                    continue
                path_key = tuple(total_path)
                if path_key in accepted_keys or path_key in candidate_keys:
                    continue
                total_cost = self._path_cost(total_path)
                heapq.heappush(candidate_heap, (total_cost, next(counter), total_path))
                candidate_keys.add(path_key)

            if not candidate_heap:
                break

            cost, _, path = heapq.heappop(candidate_heap)
            path_key = tuple(path)
            candidate_keys.discard(path_key)
            accepted.append((cost, path))
            accepted_keys.add(path_key)
            examined += 1
            if self._is_eligible(path):
                result.append((cost, path[1], path[:]))

        return result

    def query(self, src: QNode, dest: QNode) -> List[RouteResult]:
        if src == dest or src not in self._adjacency or dest not in self._adjacency:
            return []
        cache_key = (src, dest)
        if cache_key not in self._cache:
            self._cache[cache_key] = self._calculate_paths(src, dest)
        return [(cost, next_hop, path[:]) for cost, next_hop, path in self._cache[cache_key]]
