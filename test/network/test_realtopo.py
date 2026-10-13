from qns.network.network import QuantumNetwork
from qns.network.topology.realtopo import AboveNetTopology, AGISTopology, GMLTopology


def test_real_topo():
    topo1 = AboveNetTopology()
    net1 = QuantumNetwork(topo1)
    print(net1.nodes, net1.qchannels)

    topo2 = AGISTopology()
    net2 = QuantumNetwork(topo2)
    print(net2.nodes, net2.qchannels)

    topo3 = GMLTopology(file_path="AboveNet.gml")
    net3 = QuantumNetwork(topo3)
    print(net3.nodes, net3.qchannels)

    print(net3.shortest_path(net3.nodes[0], net3.nodes[-1]))
    print(net3.create_neighbors_tables())
    net3.draw("test_network.html")

    topo1 = AboveNetTopology(link_decoherence=True)
    net1 = QuantumNetwork(topo1)
    print(net1.nodes, net1.qchannels)

    topo2 = AGISTopology(link_decoherence=True)
    net2 = QuantumNetwork(topo2)
    print(net2.nodes, net2.qchannels)

    topo3 = GMLTopology(file_path="AboveNet.gml", link_decoherence=True)
    net3 = QuantumNetwork(topo3)
    print(net3.nodes, net3.qchannels)

    print(net3.shortest_path(net3.nodes[0], net3.nodes[-1]))
    print(net3.create_neighbors_tables())
    net3.draw("test_network.html")
