import heapq
from collections import deque
from typing import Dict

from qns.simulator.ts import Time
from qns.simulator.event import Event
from qns.simulator.pool import DefaultEventPool


class HashedBucketEventPool(DefaultEventPool):
    """
    An event pool using a 'hash bucket (timestamp -> deque)' + 'active timestamp heap'.
    """
    def __init__(self, ts: Time, te: Time):
        super().__init__(ts, te)
        self.slot_buckets: Dict[int, deque] = {}
        self.active_slots = []

    def add_event(self, event: Event) -> bool:
        if event.t < self.tc or event.t > self.te:
            return False

        slot = event.t.time_slot
        bucket = self.slot_buckets.get(slot)
        if bucket is None:
            bucket = deque()
            self.slot_buckets[slot] = bucket
            heapq.heappush(self.active_slots, slot)

        bucket.append(event)
        return True

    def next_event(self) -> Event:
        while self.active_slots:
            slot = self.active_slots[0]
            bucket = self.slot_buckets.get(slot)

            if not bucket:
                # 该时间戳桶已被清空，弹出并继续
                heapq.heappop(self.active_slots)
                continue

            event = bucket.popleft()
            if not bucket:
                heapq.heappop(self.active_slots)
                del self.slot_buckets[slot]

            self.tc = event.t
            return event

        self.tc = self.te
        return None
