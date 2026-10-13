from qns.entity.node.app import Application
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.entity.qchannel.dqchannel import Link_Decoherence_QuantumChannel
from qns.entity.node.node import QNode
from typing import Dict, List, Optional, Tuple
from qns.network.topology import Topology
import os
import re


class AboveNetTopology(Topology):
    """
    AboveNet Topology class for quantum networks.
    """
    def __init__(self, nodes_number=10, nodes_apps: List[Application] = [], qchannel_args: Dict = {}, cchannel_args: Dict = {},
                 memory_args: Optional[List[Dict]] = {}, link_decoherence=False):
        super().__init__(nodes_number, nodes_apps, qchannel_args, cchannel_args, memory_args)
        self.link_decoherence = link_decoherence

    def build(self) -> Tuple[List[QNode], List[QuantumChannel]]:
        """Build the random topology.
        Returns:
            List[Node]: List of nodes in the topology.
            List[Channel]: List of quantum channels in the topology.
        """
        nl = []
        ll = []
        edges = [(0, 2), (0, 4), (0, 5), (0, 7), (1, 8), (1, 22), (1, 5), (1, 4), (1, 6), (2, 10), (2, 3), (3, 10),
                 (5, 12), (5, 8), (6, 7), (8, 9), (9, 12), (10, 20), (10, 13), (10, 14), (11, 13), (11, 22), (11, 21),
                 (13, 14), (15, 16), (15, 22), (16, 18), (16, 18), (17, 18), (18, 19), (18, 21), (19, 20)]
        for i in range(23):
            node = QNode(name=f"n{i+1}")
            nl.append(node)
        for edge in edges:
            n1 = nl[edge[0]]
            n2 = nl[edge[1]]
            if self.link_decoherence is False:
                channel = QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
            else:
                channel = Link_Decoherence_QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
                channel.create_entanglement_pool()
            ll.append(channel)
            n1.add_qchannel(channel)
            n2.add_qchannel(channel)
        self._add_apps(nl)
        self._add_memories(nl)
        return nl, ll


class AGISTopology(Topology):
    """
    AGIST Topology class for quantum networks.
    """
    def __init__(self, nodes_number=10, nodes_apps: List[Application] = [], qchannel_args: Dict = {}, cchannel_args: Dict = {},
                 memory_args: Optional[List[Dict]] = {}, link_decoherence=False):
        super().__init__(nodes_number, nodes_apps, qchannel_args, cchannel_args, memory_args)
        self.link_decoherence = link_decoherence

    def build(self) -> Tuple[List[QNode], List[QuantumChannel]]:
        nl = []
        ll = []
        edges = [(0, 3), (1, 6), (2, 3), (2, 23), (3, 6), (3, 15), (4, 6), (5, 9), (5, 6), (6, 7), (7, 19), (8, 9),
                 (9, 10), (9, 12), (9, 19), (9, 24), (10, 11), (10, 12), (10, 13), (10, 14), (14, 17), (15, 16), (15, 23),
                 (17, 18), (17, 19), (19, 20), (19, 21), (21, 22), (22, 23), (23, 24)]
        for i in range(25):
            node = QNode(name=f"n{i+1}")
            nl.append(node)
        for edge in edges:
            n1 = nl[edge[0]]
            n2 = nl[edge[1]]
            if self.link_decoherence is False:
                channel = QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
            else:
                channel = Link_Decoherence_QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
                channel.create_entanglement_pool()
            ll.append(channel)
            n1.add_qchannel(channel)
            n2.add_qchannel(channel)
        self._add_apps(nl)
        self._add_memories(nl)
        return nl, ll


class GMLTopology(Topology):
    """
    Build topology based on gml download from The Internet Topology Zoo.
    """
    def __init__(self,
                 file_path: str,
                 nodes_apps: List = [],
                 qchannel_args: Dict = {},
                 cchannel_args: Dict = {},
                 memory_args: Optional[List[Dict]] = {},
                 link_decoherence=False):

        self.file_path = file_path
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"GML file not found: {self.file_path}")

        self.gml_nodes = []
        self.gml_edges = []

        self._parse_gml_manually()

        nodes_number = len(self.gml_nodes)

        super().__init__(nodes_number, nodes_apps, qchannel_args, cchannel_args, memory_args)
        self.link_decoherence = link_decoherence

    def _parse_gml_manually(self):

        with open(self.file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        node_blocks = re.findall(r'node\s*\[(.*?)\]', content, re.DOTALL)
        for block in node_blocks:
            id_match = re.search(r'\bid\s+(\d+)', block)
            if id_match:
                node_id = int(id_match.group(1))
                self.gml_nodes.append(node_id)

        edge_blocks = re.findall(r'edge\s*\[(.*?)\]', content, re.DOTALL)
        for block in edge_blocks:
            src_match = re.search(r'source\s+(\d+)', block)
            tgt_match = re.search(r'target\s+(\d+)', block)

            if src_match and tgt_match:
                src = int(src_match.group(1))
                tgt = int(tgt_match.group(1))
                self.gml_edges.append((src, tgt))

    def build(self) -> Tuple[List[QNode], List[QuantumChannel]]:
        nl = []
        ll = []

        id_to_qnode = {}

        for node_id in self.gml_nodes:
            node = QNode(f"n{node_id}")
            nl.append(node)
            id_to_qnode[node_id] = node

        for src_id, tgt_id in self.gml_edges:
            if src_id in id_to_qnode and tgt_id in id_to_qnode:
                n1 = id_to_qnode[src_id]
                n2 = id_to_qnode[tgt_id]
                if self.link_decoherence is False:
                    channel = QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
                else:
                    channel = Link_Decoherence_QuantumChannel(name=f"l{n1}-{n2}", **self.qchannel_args)
                    channel.create_entanglement_pool()
                ll.append(channel)

                n1.add_qchannel(channel)
                n2.add_qchannel(channel)
        self._add_apps(nl)
        self._add_memories(nl)
        return nl, ll
