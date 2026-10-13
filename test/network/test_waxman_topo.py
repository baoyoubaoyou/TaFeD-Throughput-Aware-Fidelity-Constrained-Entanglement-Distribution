from qns.network.network import QuantumNetwork
from qns.network.topology.waxmantopo import WaxmanTopology


def test_waxman_topo():
    topo = WaxmanTopology(nodes_number=10, size=1000, alpha=0.5, beta=0.5)
    net = QuantumNetwork(topo)

    print(net.nodes, net.qchannels)

    topo = WaxmanTopology(nodes_number=10, size=1000, alpha=0.5, beta=0.5, link_decoherence=True)
    net = QuantumNetwork(topo)

    print(net.nodes, net.qchannels)

    print(net.qchannels[-1].entanglement_pool)
