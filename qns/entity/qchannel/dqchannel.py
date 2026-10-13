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

from typing import List, Optional, Union
import numpy as np
from qns.entity.node.node import QNode
from qns.models.delay.delay import DelayModel
from qns.utils.rnd import get_rand
from qns.entity.qchannel.qchannel import QuantumChannel


def calculate_fidelity(init_fidelity: float, storage_time: float, storage_tau: float = 1.0) -> float:
    if init_fidelity <= 0.25:
        raise ValueError("init_fidelity must be greater than 0.25.")
    if storage_tau <= 0.0:
        raise ValueError("storage_tau must be positive.")
    return float(0.25 + (float(init_fidelity) - 0.25) * np.exp(-float(storage_time) / float(storage_tau)))


class Link_Decoherence_QuantumChannel(QuantumChannel):
    '''
    Link_Decoherence_QuantumChannel is the channel in which the fidelity of entangled pairs decoherence
    within the quantum memory.
    '''
    def __init__(self, name: str = None, node_list: List[QNode] = [], init_fidelity: float = 0.8,
                 bandwidth: int = 1, delay: Union[float, DelayModel] = 0, drop_rate: float = 0,
                 max_buffer_size: int = 0, length: float = 0, decoherence_rate: Optional[float] = 0,
                 transfer_error_model_args: dict = {}, max_storage_time=0.4, min_storage_time=0.0):

        """
        Args:
            init_fidelity: fidelity of steady-state entanglement established by two-atom excitation.
            max_storage_time: maximum storage time of entanglement within the quantum memory.
            min_storage_time: minimum storage time of entanglement within the quantum memory.
        """

        super().__init__(name=name, node_list=node_list, bandwidth=bandwidth, delay=delay,
                         drop_rate=drop_rate, max_buffer_size=max_buffer_size, length=length,
                         decoherence_rate=decoherence_rate, transfer_error_model_args=transfer_error_model_args)

        self.init_fidelity = init_fidelity
        self.max_storage_time = max_storage_time
        self.min_storage_time = min_storage_time
        self.entanglement_pool = []

    def create_entanglement_pool(self):
        """
        Creat entangled pairs.
        """
        self.entanglement_pool = []

        if self.bandwidth <= 0:
            self.entanglement_pool = []
            return None

        effective_storage_time = np.log(4*self.init_fidelity - 1)
        self.max_storage_time = min(self.max_storage_time, effective_storage_time)

        if self.min_storage_time > self.max_storage_time:
            self.entanglement_pool = []
            return None
        if np.isclose(self.min_storage_time, self.max_storage_time):
            storage_time = self.min_storage_time
            fidelity = calculate_fidelity(self.init_fidelity, storage_time)
            self.entanglement_pool = [(fidelity, storage_time)] * self.bandwidth
            return None

        for i in range(self.bandwidth):
            storage_time = get_rand(self.min_storage_time, self.max_storage_time)
            fidelity = calculate_fidelity(self.init_fidelity, storage_time)
            self.entanglement_pool.append((fidelity, storage_time))

    def find_fidlity_index(self, fidelity):
        """
        Find the entanglement pair whose fidelity is equal to the specified fidelity.

        Args:
            fidelity: the specified fidelity.
        """
        for i in range(len(self.entanglement_pool)):
            if np.isclose(self.entanglement_pool[i][0], fidelity):
                return i
        return None

    def find_max_min_fidelity(self):
        """
        Find the entanglement pairs with maximum and minimum fidelity.
        """
        max_fidelity = 0.0
        min_fidelity = 1.0
        max_index = min_index = None
        for i in range(len(self.entanglement_pool)):
            if self.entanglement_pool[i][0] > max_fidelity:
                max_fidelity = self.entanglement_pool[i][0]
                max_index = i
            if self.entanglement_pool[i][0] < min_fidelity:
                min_fidelity = self.entanglement_pool[i][0]
                min_index = i
        return max_index, min_index

    def remove_entanglement_by_fidelity(self, fidelity):
        """
        Remove the entanglement pair whose fidelity is equal to the specified fidelity.
        """
        index = self.find_fidlity_index(fidelity)
        if index is None:
            raise ValueError("can not remove fidelity with index None")
        self.entanglement_pool.pop(index)
        # self.bandwidth = self.bandwidth - 1

    def remove_entanglement_by_index(self, index):
        """
        Remove the entanglement pair whose fidelity is equal to the specified index.
        """
        if index is None:
            raise ValueError("can not remove fidelity with index None")
        self.entanglement_pool.pop(index)
        # self.bandwidth = self.bandwidth - 1
