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

from typing import List, Union

from qns.simulator.ts import Time
from qns.entity.node.node import QNode
from qns.models.delay.delay import DelayModel
from qns.simulator.simulator import Simulator
from qns.utils.rnd import get_rand
import qns.utils.log as log
from qns.entity.cchannel.cchannel import ClassicPacket, ClassicChannel, RecvClassicPacket, NextHopNotConnectionException


class ClassicChannelEx(ClassicChannel):
    class param:
        def __init__(self) -> None:
            self._next_send_time: Time = Time(0)
            self._last_recv_time: Time = Time(0)

    def __init__(
        self,
        name: str = None,
        node_list: List[QNode] = [],
        bandwidth: int = 0,
        delay: Union[float, DelayModel] = 0,
        length: Union[float, None] = 0,
        drop_rate: float = 0,
        max_buffer_size: int = 0,
    ):
        super().__init__(
            name, node_list, bandwidth, delay, length, drop_rate, max_buffer_size
        )
        self.reliable = True

    def install(self, simulator: Simulator) -> None:
        assert len(self.node_list) == 2
        self.bidir_param = {
            self.node_list[0]: self.param(),
            self.node_list[1]: self.param(),
        }
        self.first_run = False
        return super().install(simulator)

    def send(self, packet: ClassicPacket, next_hop: QNode):

        if next_hop not in self.node_list:
            raise NextHopNotConnectionException

        param = self.bidir_param[next_hop]

        if self.bandwidth != 0:
            if param._next_send_time <= self._simulator.current_time:
                send_time = self._simulator.current_time
            else:
                send_time = param._next_send_time

            if (
                self.max_buffer_size != 0
                and send_time
                > self._simulator.current_time
                + self._simulator.time(sec=self.max_buffer_size / self.bandwidth)
            ):
                # buffer is overflow
                log.debug(f"cchannel {self}: drop packet {packet} due to overflow")
                return

            param._next_send_time = send_time + self._simulator.time(
                sec=len(packet) / self.bandwidth
            )
        else:
            send_time = self._simulator.current_time

        # random drop
        if self.reliable:
            while get_rand() < self.drop_rate:
                # 每丢包重发一次增加一个1-rtt
                send_time += self._simulator.time(sec=self.delay_model.calculate())
                send_time += self._simulator.time(sec=self.delay_model.calculate())
        else:
            if get_rand() < self.drop_rate:
                log.debug(f"cchannel {self}: drop packet {packet} due to drop rate")
                return

        #  add delay
        recv_time = send_time + self._simulator.time(sec=self.delay_model.calculate())

        if self.reliable:
            if recv_time < param._last_recv_time:
                recv_time = param._last_recv_time

            param._last_recv_time = recv_time

        send_event = RecvClassicPacket(
            recv_time, name=None, by=self, cchannel=self, packet=packet, dest=next_hop
        )
        self._simulator.add_event(send_event)
