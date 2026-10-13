from qns.simulator.event import Event
from qns.simulator import Simulator, func_to_event
from qns.simulator.stablepool import StableEventPool
from qns.entity.node.node import QNode
from qns.entity.node.app import Application
from qns.utils.log import install
from qns.entity.cchannel.cchannel import ClassicChannel, ClassicPacket
from qns.entity.cchannel.cchannel_ex import ClassicChannelEx


class AppS(Application):
    def __init__(self, dst):
        super().__init__()
        self.dst = dst
        self.i = 0
        self.rate = 1.0

    def start(self):
        self.send()

    def install(self, node, simulator: Simulator):
        return super().install(node, simulator)

    def send(self):
        n: QNode = self.get_node()
        c: ClassicChannelEx = n.get_cchannel(self.dst)

        c.send(ClassicPacket(f"{self.i:02d}"), self.dst)
        self.i += 1

        self._simulator.add_event(
            func_to_event(
                self._simulator.tc + self._simulator.time(sec=1.0 / self.rate),
                self.send,
            )
        )


class AppR(Application):
    def __init__(self):
        super().__init__()
        self.add_handler(self.recv)
        self.recved = []
        self.recved_time = []

    def recv(self, node, event: Event):
        packet: ClassicPacket = event.packet
        # debug(f"{self.get_node().name} recv {packet.msg}")
        self.recved.append(packet.msg)
        self.recved_time.append(self._simulator.tc)


def _run_sim(is_used, tparam):
    sim = Simulator(0, 10, pool_cls=StableEventPool)
    install(sim)

    n1 = QNode("n1")
    n2 = QNode("n2")

    if not is_used:
        c12 = ClassicChannel(
            bandwidth=tparam[0],
            drop_rate=tparam[1],
            delay=tparam[2],
            max_buffer_size=tparam[3],
        )
    else:
        c12 = ClassicChannelEx(
            bandwidth=tparam[0],
            drop_rate=tparam[1],
            delay=tparam[2],
            max_buffer_size=tparam[3],
        )
        c12.reliable = True

    n1.add_cchannel(c12)
    n2.add_cchannel(c12)

    s1 = AppS(n2)
    r1 = AppR()
    n1.add_apps(s1)
    n2.add_apps(r1)

    s2 = AppS(n1)
    r2 = AppR()
    n2.add_apps(s2)
    n1.add_apps(r2)

    n1.install(sim)
    n2.install(sim)

    s1.rate = 1
    s2.rate = 1

    s1.start()
    s2.start()
    sim.run()

    print(f"\nn1->n2: {r1.recved}, time: {r1.recved_time}")
    print(f"n2->n1: {r2.recved}, time: {r2.recved_time}")


def test_bidir_without_ex():
    print("\n--- bidir w/o Ex ---")
    _run_sim(False, (2, 0, 0, 1))


def test_bidir_with_ex():
    print("\n--- bidir w/ Ex ---")
    _run_sim(True, (2, 0, 0, 1))


def test_reliable_without_ex():
    print("\n--- reliable w/o Ex ---")
    _run_sim(False, (0, 0.5, 1, 0))


def test_reliable_with_ex():
    print("\n--- reliable w/ Ex ---")
    _run_sim(True, (0, 0.5, 1, 0))


test_bidir_without_ex()
test_bidir_with_ex()
test_reliable_without_ex()
test_reliable_with_ex()
