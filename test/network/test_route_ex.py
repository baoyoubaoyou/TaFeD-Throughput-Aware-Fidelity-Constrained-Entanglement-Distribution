from qns.network.route.dijkstra import DijkstraRouteAlgorithm
from qns.network.route.dijkstra_heap import DijkstraRouteAlgorithmHeap
from qns.network.topology.waxmantopo import WaxmanTopology
from qns.network.topology.treetopo import TreeTopology
import random
import time


def test_speed():
    dijk_default = DijkstraRouteAlgorithm()
    dijk_heap = DijkstraRouteAlgorithmHeap()

    builder = WaxmanTopology(300, 100, 0.5, 0.2)
    topo = builder.build()

    print(f"waxman node num: {len(topo[0])}, edge num: {len(topo[1])}")

    nodes, edges = topo[0], topo[1]

    t0 = time.perf_counter()
    dijk_default.build(nodes, edges)
    t1 = time.perf_counter()
    dijk_heap.build(nodes, edges)
    t2 = time.perf_counter()

    print("\n=== Build Time ===")
    print(f"DijkstraRouteAlgorithm build time: {(t1-t0)*1000:.3f} ms")
    print(f"DijkstraRouteAlgorithmHeap build time: {(t2-t1)*1000:.3f} ms")
    print(f"Heap speedup: {(t1-t0)/(t2-t1):.2f}x")


def test_func():
    dijk_default = DijkstraRouteAlgorithm()
    dijk_heap = DijkstraRouteAlgorithmHeap()

    builder = TreeTopology(300, 3)
    topo = builder.build()

    print(f"tree node num: {len(topo[0])}, edge num: {len(topo[1])}")

    nodes, edges = topo[0], topo[1]

    dijk_default.build(nodes, edges)
    dijk_heap.build(nodes, edges)

    print("\n=== Route Result Comparison ===")
    mismatches = 0
    total_queries = 10000
    random.seed(42)

    for _ in range(total_queries):
        src = random.choice(nodes)
        dest = random.choice(nodes)
        if src == dest:
            continue

        result_default = dijk_default.query(src, dest)
        result_heap = dijk_heap.query(src, dest)

        if len(result_default) != len(result_heap):
            mismatches += 1
            continue

        if len(result_default) == 0:
            continue

        m_default, next_default, path_default = result_default[0]
        m_heap, next_heap, path_heap = result_heap[0]

        if m_default != m_heap:
            mismatches += 1
            continue

        if next_default != next_heap:
            mismatches += 1
            continue

        if path_default != path_heap:
            mismatches += 1
            continue

    print(f"Total queries: {total_queries}")
    print(f"Mismatches: {mismatches}")
    print(f"Result: {'PASS' if mismatches == 0 else 'FAIL'}\n")


test_func()
test_speed()
