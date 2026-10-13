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
from qns.utils.rnd import get_rand
from qns.network.graphalg.alg import is_connected


class ErdosRenyiTopology(Topology):
    """
    ErdosRenyiTopology includes `nodes_number` Qnodes.
    The topology is randomly generated following the Erdos-Renyi model(G(n,p) Model).
    Each pair of Qnodes has a probability `generate_prob` to be connected by a QuantumChannel.
    """
    def __init__(self, nodes_number, generate_prob: float,
                 nodes_apps: List[Application] = [],
                 qchannel_args: Dict = {}, cchannel_args: Dict = {},
                 memory_args: Optional[List[Dict]] = {}, link_decoherence=False):
        """
        Args:
            nodes_number: the number of Qnodes
            generate_prob: the probability of QuantumChannel generation between two Qnodes
        """
        super().__init__(nodes_number, nodes_apps, qchannel_args, cchannel_args, memory_args)
        self.generate_prob = generate_prob
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
        nl: List[QNode] = []
        ll: List[QuantumChannel] = []
        # generate Qnodes
        for i in range(self.nodes_number):
            n = QNode(f"n{i+1}")
            nl.append(n)
        # generate QuantumChannels
        edges = list(itertools.combinations(nl, 2))
        for n1, n2 in edges:
            if get_rand() < self.generate_prob:
                if self.link_decoherence is False:
                    qc = QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
                else:
                    qc = Link_Decoherence_QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
                    qc.create_entanglement_pool()
                ll.append(qc)
                n1.add_qchannel(qc)
                n2.add_qchannel(qc)
        # QNode configuration
        self._add_apps(nl)
        self._add_memories(nl)
        return nl, ll
