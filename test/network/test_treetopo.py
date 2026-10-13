from qns.network.network import QuantumNetwork
from qns.network.topology.treetopo import TreeTopology


def test_tree_topo():
    topo = TreeTopology(nodes_number=15, children_number=3)
    net = QuantumNetwork(topo)

    print(net.nodes, net.qchannels)

    topo = TreeTopology(nodes_number=15, children_number=3, link_decoherence=True)
    net = QuantumNetwork(topo)

    print(net.nodes, net.qchannels)
