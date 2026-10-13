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

import itertools
from qns.entity.node.app import Application
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.entity.qchannel.dqchannel import Link_Decoherence_QuantumChannel
from qns.entity.node.node import QNode
from typing import Dict, List, Optional, Tuple
from qns.network.topology import Topology
from qns.utils.rnd import get_rand, get_weighted_choice
from qns.network.graphalg.alg import is_connected


class DualBarabasiAlbertTopology(Topology):
    """
    DualBarabasiAlbertTopology is a random topology generator based on the Dual Barabasi-Albert model.
    Each new QNode added has either `edges_num1` or `edges_num2` edges to existing QNodes.
    The probability of a new QNode connecting to an existing QNode is proportional to the degree of the existing QNode.
    """
    def __init__(self, nodes_number, edges_num1: int, edges_num2: int,
                 prob: float, nodes_apps: List[Application] = [],
                 qchannel_args: Dict = {}, cchannel_args: Dict = {},
                 memory_args: Optional[List[Dict]] = {}, link_decoherence=False):
        """
        Args:
            nodes_number: the number of Qnodes
            new_nodes_egdes: the number of edges of a new node, must be greater than 0 and less than nodes_number
        """
        super().__init__(nodes_number, nodes_apps, qchannel_args, cchannel_args, memory_args)
        self.edges_num1 = edges_num1
        self.edges_num2 = edges_num2
        self.prob = prob
        self.link_decoherence = link_decoherence

    def build(self) -> Tuple[List[QNode], List[QuantumChannel]]:
        max_attempts = 100
        # 尝试构建最多 100 次
        for _ in range(max_attempts):
            nl, ll = self.creat_topo()
            if is_connected(nl, ll):
                return nl, ll
        raise RuntimeError(f"Failed to generate a connected topology after {max_attempts} attempts.")

    def creat_topo(self) -> Tuple[List[QNode], List[QuantumChannel]]:
        # check config
        if self.edges_num1 < 1 or self.edges_num2 < 1:
            raise ValueError("edges_num1 and edges_num2 must be greater than 0")
        elif self.edges_num1 >= self.nodes_number or self.edges_num2 >= self.nodes_number:
            raise ValueError("edges_num1 and edges_num2 must be less than nodes_number")
        elif self.prob < 0 or self.prob > 1:
            raise ValueError("prob must be in [0, 1]")
        nl: List[QNode] = []
        ll: List[QuantumChannel] = []
        # generate initial QNodes and QuantumChannels
        node_num = max(self.edges_num1, self.edges_num2)
        for i in range(node_num):
            n = QNode(f"n{i+1}")
            nl.append(n)
        initial_edges = list(itertools.combinations(nl, 2))
        for n1, n2 in initial_edges:
            if self.link_decoherence is False:
                qc = QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
            else:
                qc = Link_Decoherence_QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
                qc.create_entanglement_pool()
            ll.append(qc)
            n1.add_qchannel(qc)
            n2.add_qchannel(qc)
        # generate new QNodes following dual Barabasi-Albert model
        for i in range(node_num, self.nodes_number):
            n = QNode(f"n{i+1}")
            p = get_rand()
            # deal with boundary conditions
            if node_num == 1 and i == 1:
                n1 = nl[0]
                nl.append(n1)
                if self.link_decoherence is False:
                    qc = QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
                else:
                    qc = Link_Decoherence_QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
                    qc.create_entanglement_pool()
                ll.append(qc)
                n1.add_qchannel(qc)
                n.add_qchannel(qc)
                continue
            if p < self.prob:
                weighted_choice = [len(n_i.qchannels) for n_i in nl]
                choice_list = get_weighted_choice(nl, weighted_choice, self.edges_num1)
            else:
                weighted_choice = [len(n_i.qchannels) for n_i in nl]
                choice_list = get_weighted_choice(nl, weighted_choice, self.edges_num2)
            for n_i in choice_list:
                if self.link_decoherence is False:
                    qc = QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
                else:
                    qc = Link_Decoherence_QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
                    qc.create_entanglement_pool()
                ll.append(qc)
                n.add_qchannel(qc)
                n_i.add_qchannel(qc)
            nl.append(n)
        # QNode configuration
        self._add_apps(nl)
        self._add_memories(nl)
        return nl, ll
