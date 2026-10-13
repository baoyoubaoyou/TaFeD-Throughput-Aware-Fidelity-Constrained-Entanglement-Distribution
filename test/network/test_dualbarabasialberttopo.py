from qns.network.network import QuantumNetwork
from qns.network.topology.dualbarabasialberttopo import DualBarabasiAlbertTopology


def test_dualbarabasialbert_topo():
    topo = DualBarabasiAlbertTopology(nodes_number=100, edges_num1=1, edges_num2=3, prob=0.85)
    net = QuantumNetwork(topo)

    print(net.nodes, net.qchannels)

    topo = DualBarabasiAlbertTopology(nodes_number=100, edges_num1=1, edges_num2=3, prob=0.85, link_decoherence=True)
    net = QuantumNetwork(topo)

    print(net.nodes, net.qchannels)
