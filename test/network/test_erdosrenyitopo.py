from qns.network.network import QuantumNetwork
from qns.network.topology.erdosrenyitopo import ErdosRenyiTopology


def test_erdosrenyi_topo():
    topo = ErdosRenyiTopology(nodes_number=20, generate_prob=0.2)
    net = QuantumNetwork(topo)

    print(net.nodes, net.qchannels)

    topo = ErdosRenyiTopology(nodes_number=20, generate_prob=0.2, link_decoherence=True)
    net = QuantumNetwork(topo)

    print(net.nodes, net.qchannels)
