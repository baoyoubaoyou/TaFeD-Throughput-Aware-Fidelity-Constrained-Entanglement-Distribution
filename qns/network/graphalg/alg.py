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

from typing import Callable, List
import math
from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.graphalg.draw import draw


def create_neighbors_tables(nl: List[QNode], ll):
    """
    This is the algorithm create the neighbor nodes of the network.
    Args:
        nl: list of Qnode.
        ll: list of QuantumChannel.
    Return:
        neighbors_table: a dict of neighbors node for Qnode in nl.
    """
    neighbors_table = {node: [] for node in nl}
    for channel in ll:
        assert len(channel.node_list) == 2

        if channel.bandwidth <= 0:
            continue

        [node1, node2] = channel.node_list
        neighbors_table[node1].append(node2)
        neighbors_table[node2].append(node1)
    return neighbors_table


def is_connected(nl, ll):
    """
    This is the algorithm check whether the network is connected(BFS).
    Args:
        nl: list of Qnode.
        ll: list of QuantumChannel.
    Return:
        whether the network is connected.
    """
    if len(nl) == 0:
        return True

    neighbors_table = create_neighbors_tables(nl, ll)

    visited = {node: False for node in nl}
    stack = [nl[0]]
    while len(stack) != 0:
        node = stack.pop()
        if visited[node] is True:
            continue

        for neighbor in neighbors_table[node]:
            if not visited[neighbor]:
                stack.append(neighbor)

        visited[node] = True

    for node in nl:
        if visited[node] is False:
            return False
    return True


def min_hop_metric_funcation(channel: QuantumChannel):
    return 1


def dijkstra(src: QNode, dest: QNode, nl: List[QNode], ll: List[QuantumChannel],
             metric_function: Callable = min_hop_metric_funcation):
    """
    dijkstra algorithm.
    Args:
        src: source Qnode.
        dest: destination Qnode.
        nl: list of Qnodes.
        ll: list of QuantumChannel.
        metric_function: function to calculate the weight of each channel.
    Return:
        pathset: shortest path set and cost on path.
    """
    # create neighbors table and weight table
    if metric_function is None:
        metric_function = min_hop_metric_funcation
    else:
        metric_function = metric_function

    neighbors_tables = create_neighbors_tables(nl, ll)
    weight = {}
    for channel in ll:
        assert len(channel.node_list) == 2
        [node1, node2] = channel.node_list
        weight[(node1, node2)] = metric_function(channel)
        weight[(node2, node1)] = metric_function(channel)

    # initialize distances and previous nodes
    distances = {node: math.inf for node in nl}
    previous = {node: None for node in nl}
    distances[src] = 0

    # priority queue
    priority_queue = [(0, src)]
    visited = {node: False for node in nl}
    while priority_queue:
        priority_queue.sort(key=lambda x: x[0])
        current_distance, current_node = priority_queue.pop()

        # if already visited, skip
        if visited[current_node]:
            continue
        visited[current_node] = True

        # if reached destination, break
        if dest is not None and current_node == dest:
            break

        # explore neighbors
        for neighbor in neighbors_tables[current_node]:
            if visited[neighbor]:
                continue

            new_distance = current_distance + weight[(current_node, neighbor)]

            # update distance if new distance is shorter
            if new_distance < distances[neighbor]:
                distances[neighbor] = new_distance
                previous[neighbor] = current_node
                priority_queue.append((new_distance, neighbor))

    # if destination is unreachable
    # if distances[dest] == math.inf:
    if previous[dest] == dest:
        return []

    # 重建路径
    path = []
    current = dest
    while current is not None:
        path.append(current)
        current = previous[current]
    path.reverse()

    return path


def networkdraw(nl, ll, filename):
    '''
    Network visualization Algorithm.
    Args:
        nl: list of Qnodes.
        ll: list of QuantumChannel.
        filename: path of the output file
    Return:
        Interactive HTML file
    '''
    draw(nl, ll, filename)
