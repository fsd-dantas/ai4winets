# Network, protocol, traffic and service model

**Status: normative methodology.** [Framework](README.md)

This document defines the protocol, topology, queueing, transport, traffic, application and mobility
abstractions a study declares when it makes end-to-end service, resilience, routing, orchestration or QoS
claims.

## End-to-end delay

End-to-end delay is not an unexplained constant when the study concerns latency, reliability or control
responsiveness. The model identifies its applicable components:

$$
D_{\mathrm{E2E}} = D_{\mathrm{tx}} + D_{\mathrm{prop}} + D_{\mathrm{proc}} + D_{\mathrm{queue}}
+ D_{\mathrm{retx}} + D_{\mathrm{route/control}}.
$$

A component omitted from a latency claim is declared `assumed_negligible`, with its justification.

## PHY/MAC and radio resource management

Declare, when relevant:

- waveform, channel bandwidth, resource grid, numerology, duplexing and overhead;
- modulation and coding set and the MCS-selection policy;
- BLER/BER mapping and CQI quality and delay;
- HARQ and ARQ configuration;
- scheduler type: round robin, proportional fair, max-C/I, deadline-aware, QoS-aware, slice-aware, heuristic or
  learned;
- queue disciplines: FIFO, priority, per-flow, per-class, DRR, AQM;
- buffer capacities and drop behaviour;
- admission control and bearer or QoS-flow treatment;
- random access and contention;
- CSMA/CA behaviour where applicable;
- sleep, DRX and wake-up behaviour where energy or latency is material.

## Topology and forwarding

A scenario identifies the topology and abstractions of:

- access, aggregation, backhaul, fronthaul, core, edge, cloud and external gateways;
- link capacity, propagation delay, serialisation delay, loss and queueing;
- tunnels, encapsulation, MTU and protocol overhead where material;
- the routing and control plane: static, distributed, SDN, multipath, fast reroute or abstracted;
- controller, discovery and convergence delay;
- service function chaining, slicing, and function placement and migration if used;
- failure domains and shared-risk groups.

A logical topology with no physical layer, such as a coordination graph with reliable messaging, is declared as
such, with the transport assumptions it makes: loss, ordering, delay and whether it shares resources with the
data it coordinates.

## Transport

State the transport and congestion-control model for each traffic class:

- UDP, a TCP variant, QUIC, SCTP or an application-specific transport;
- congestion control, loss recovery, pacing, ECN and retransmission timers;
- connection establishment and session behaviour;
- rate adaptation and application-layer retransmission.

Application-level reliability is not inferred from a UDP-only model unless the application has an explicit
reliability mechanism.

## Traffic and application classes

Each traffic class defines:

```json
{
  "traffic_class": {
    "id": "string",
    "direction": "uplink_downlink_bidirectional",
    "packet_size_model": "constant_distribution_trace",
    "arrival_model": "periodic_poisson_mmpp_self_similar_trace",
    "offered_load": "declared",
    "burst_correlation": "independent_or_declared_event_model",
    "transport": "UDP_TCP_QUIC_other",
    "priority": "declared",
    "deadline_ms": null,
    "reliability_target": null,
    "freshness_target": null,
    "flow_lifetime": "declared",
    "source_destination_model": "declared"
  }
}
```

For utility and industrial communications, distinguish rather than aggregate where relevant:

- protective relaying and teleprotection;
- SCADA and supervisory traffic;
- synchrophasor (PMU) streams;
- distribution automation;
- advanced metering infrastructure;
- DER and EV coordination;
- video and situational awareness;
- firmware updates and maintenance traffic.

## Event correlation

The model states whether traffic, failures, mobility and control events are independent. Where an event can
trigger simultaneous demand or failures, the correlation is represented. Examples:

- a physical fault triggering many protection and control messages;
- a cell-site outage causing handover and load redistribution;
- a weather event causing correlated link degradation and power failures;
- a cyber event generating synchronised control-plane load.

## Mobility and temporal evolution

Choose a mobility model consistent with the deployment:

- stationary fixed nodes;
- a map- or road-constrained trace;
- an industrial worker or equipment trace;
- a vehicular, rail or UAV trajectory;
- group mobility;
- random waypoint or Gauss-Markov, only with an explicit justification;
- regenerative or open-boundary mobility, as defined in the [spatial world model](spatial-world-model.md);
- a declared sequence of static snapshots, where the model re-solves between moves rather than simulating
  motion.

Declare speed, acceleration, pauses, route constraints, device orientation, population arrival and departure,
the channel-update interval, and time-of-day or load evolution when relevant.

## KPI contract

Each experiment distinguishes:

- offered load from carried or delivered load;
- packet loss from deadline miss;
- mean from percentile latency;
- application goodput from PHY throughput;
- availability from outage probability from recovery time;
- per-flow, per-user, per-slice and aggregate KPI populations.

Primary metrics state their aggregation population and time window. Where reliability is central, report tail
behaviour and confidence intervals, not only means.

## Scenario declaration

```json
{
  "network_service_model": {
    "topology": {"access": "declared", "backhaul": "declared", "edge_cloud": "declared", "routing": "declared"},
    "queues": {"discipline": "priority_or_declared", "buffer_size_packets": null, "aqm": "none_or_declared"},
    "traffic_classes": ["reference-to-defined-classes"],
    "service_constraints": {"latency": "declared", "reliability": "declared", "freshness": "declared"},
    "mobility": {"model": "stationary_or_declared", "boundary_semantics": "from_world_model"}
  }
}
```
