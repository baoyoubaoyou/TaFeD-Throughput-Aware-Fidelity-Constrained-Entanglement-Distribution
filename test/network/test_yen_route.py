from qns.entity.node.node import QNode
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.network.route.yen import YenKShortestRouteAlgorithm


def _connect(node_a, node_b, name):
    channel = QuantumChannel(name=name)
    node_a.add_qchannel(channel)
    node_b.add_qchannel(channel)
    return channel


def test_yen_returns_three_loopless_paths_with_hop_filter():
    nodes = {name: QNode(name) for name in "ABCDEFG"}
    edges = [
        _connect(nodes["A"], nodes["B"], "ab"),
        _connect(nodes["B"], nodes["G"], "bg"),
        _connect(nodes["A"], nodes["C"], "ac"),
        _connect(nodes["C"], nodes["D"], "cd"),
        _connect(nodes["D"], nodes["G"], "dg"),
        _connect(nodes["A"], nodes["E"], "ae"),
        _connect(nodes["E"], nodes["F"], "ef"),
        _connect(nodes["F"], nodes["G"], "fg"),
        _connect(nodes["C"], nodes["F"], "cf"),
    ]

    route = YenKShortestRouteAlgorithm(k=3, min_hops=3, max_hops=4)
    route.build(list(nodes.values()), edges)
    results = route.query(nodes["A"], nodes["G"])

    assert len(results) == 3
    assert [result[0] for result in results] == sorted(result[0] for result in results)
    for _, next_hop, path in results:
        assert 3 <= len(path) - 1 <= 4
        assert len(path) == len(set(path))
        assert next_hop == path[1]


def test_yen_honors_custom_channel_metric():
    a, b, c, d = [QNode(name) for name in "ABCD"]
    edges = [
        _connect(a, b, "ab"),
        _connect(b, d, "bd"),
        _connect(a, c, "ac"),
        _connect(c, d, "cd"),
    ]
    weights = {"ab": 5, "bd": 5, "ac": 1, "cd": 1}
    route = YenKShortestRouteAlgorithm(k=2, metric_func=lambda channel: weights[channel.name])
    route.build([a, b, c, d], edges)

    results = route.query(a, d)
    assert [node.name for node in results[0][2]] == ["A", "C", "D"]
    assert results[0][0] == 2
