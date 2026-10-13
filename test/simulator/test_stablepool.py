from qns.simulator import Simulator
from qns.simulator.stablepool import StableEventPool
from qns.simulator.event import func_to_event

stable_sim = Simulator(0, 10, pool_cls=StableEventPool)
default_sim = Simulator(0, 10)

stable_result = []
default_result = []

for i in range(0, 100):
    e = func_to_event(stable_sim.time(0), lambda x=i: stable_result.append(x))
    stable_sim.add_event(e)
    e2 = func_to_event(default_sim.time(0), lambda x=i: default_result.append(x))
    default_sim.add_event(e2)

stable_sim.run()
default_sim.run()

print(f"stable_result= {stable_result}")
print(f"default_result= {default_result}")
