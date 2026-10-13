# Legacy multi-request baselines

This directory contains an isolated copy of the published comparison source
and adapters for the current SimQN experiments.

`original/` is a source snapshot from the supplied attachment. It is not
edited by the experiment framework. `bounded/` is a minimal execution copy of
QPath/QLeap with candidate and reallocation limits; it leaves routing and
priority rules unchanged. The adapters pass one complete request batch to the
multi-request entry points (`MQpath.alg4` and `MQleap.alg3`) and return a
common result object.

The current physical model remains authoritative for topology, link capacity,
node memory, fidelity demands and random seeds. QPath/QLeap retain their
legacy path and multi-request priority decisions, then their selected paths
are reevaluated using the shared Werner purification, swapping and PF rate
model. This separates an algorithm's routing logic from incompatible legacy
capacity units.

`sftrap_compatible.py` is an explicit compatibility extension because the
supplied SFTRAP source supports only one global threshold. It retains the
K-shortest path pool and adaptive congestion cancellation while computing
purification separately for each request-path-link using that request's
fidelity target. Results must be labelled `SFTrap-compatible`, not claimed as
an unmodified execution of the original single-threshold implementation.
