#    SimQN: a discrete-event simulator for the quantum networks
#    Copyright (C) 2021-2022 Lutong Chen, Jian Li, Kaiping Xue
#    University of Science and Technology of China, USTC.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

from typing import Callable, Dict, List, Tuple, Union
import math

from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.entity.cchannel.cchannel import ClassicChannel
from qns.network.route.route import RouteImpl
import heapq


class heapitem:
    def __init__(self, item: object, key: float) -> None:
        self.item = item
        self.key = key

    def __lt__(self, other) -> bool:
        return self.key < other.key

    def __iter__(self):
        return iter((self.item, self.key))


class DijkstraRouteAlgorithmHeap(RouteImpl):
    """
    This is the dijkstra route algorithm implement
    """

    INF = math.inf

    def __init__(
        self,
        name: str = "dijkstra",
        metric_func: Callable[[Union[QuantumChannel, ClassicChannel]], float] = None,
    ) -> None:
        """
        Args:
            name: the routing algorithm's name
            metric_func: the function that returns the metric for each channel.
                The default is the const function m(l)=1
        """
        self.name = name
        self.route_table = {}

        if metric_func is None:
            self.metric_func = lambda _: 1
        else:
            self.metric_func = metric_func

        self.pathset = {}

    def build(
        self, nodes: List[QNode], channels: List[Union[QuantumChannel, ClassicChannel]]
    ):
        neighbors_table = {node: [] for node in nodes}
        for channel in channels:
            assert len(channel.node_list) == 2
            metric = self.metric_func(channel)

            [node1, node2] = channel.node_list
            neighbors_table[node1].append((node2, metric))
            neighbors_table[node2].append((node1, metric))

        for srcn in nodes:
            nodes_cost = {node: self.INF for node in nodes}
            nodes_cost[srcn] = 0
            prev_node = {node: None for node in nodes}

            heap = []
            heapq.heappush(heap, heapitem(srcn, 0))

            while len(heap) != 0:
                (node, cost) = heapq.heappop(heap)

                if cost > nodes_cost[node]:
                    continue

                for neigh, metric in neighbors_table[node]:
                    neigh_new_cost = cost + metric
                    if neigh_new_cost < nodes_cost[neigh]:
                        nodes_cost[neigh] = neigh_new_cost
                        heapq.heappush(heap, heapitem(neigh, nodes_cost[neigh]))
                        prev_node[neigh] = node

            srcpath = {}
            for dst in nodes:
                if nodes_cost[dst] == self.INF:
                    continue

                if dst in srcpath:
                    continue

                path = []
                curr = dst
                while curr is not None:
                    path.append(curr)
                    curr = prev_node[curr]
                path.reverse()

                while len(path) != 0:
                    if path[-1] in srcpath:
                        break
                    srcpath[path[-1]] = [nodes_cost[path[-1]], path[:]]
                    path.pop()
            self.route_table[srcn] = srcpath

    def query(self, src: QNode, dest: QNode) -> List[Tuple[float, QNode, List[QNode]]]:
        """
        query the metric, nexthop and the path

        Args:
            src: the source node
            dest: the destination node

        Returns:
            A list of route paths. The result should be sortted by the priority.
            The element is a tuple containing: metric, the next-hop and the whole path.
        """
        src_routelist: Dict[QNode, List[float, List[QNode]]] = self.route_table.get(src, None)
        if src_routelist is None:
            return []

        dst_path = src_routelist.get(dest, None)
        if dst_path is None:
            return []

        try:
            metric = dst_path[0]
            path: List[QNode] = dst_path[1][:]
            if len(path) <= 1 or metric == self.INF:
                next_hop = None
                return []
            else:
                next_hop = path[1]
                return [(metric, next_hop, path)]
        except Exception:
            return []
