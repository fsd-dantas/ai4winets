# Abstraction catalog

**Status: reference checklist.** [Framework](README.md)

A quick checklist of model families that may be relevant to a wireless-network or distributed-control
simulation study. It does not require every abstraction in every study. It requires an explicit selection, a
justification of scope and evidence proportional to the claim.

## System and scientific scope

- Research question, hypothesis and causal claim
- Target deployment, population and validity domain
- System boundary and exogenous inputs
- Temporal horizon and control timescale
- Primary and secondary metrics and decision criteria
- Included, abstracted, negligible and out-of-scope mechanisms

## Spatial world and environment

- Finite closed domain
- Finite ROI with a guard region
- Periodic or wrap-around topology
- Open stochastic population process with finite truncation
- Trace- or map-bounded deployment
- Explicit region plus an external stochastic field
- Non-spatial logical topology
- Fixed topology, grid, lattice, Poisson, cluster, Cox or hard-core point process
- Elevation, land use, clutter, buildings, walls, foliage, roads, tunnels
- LOS/NLOS/O2I state and spatial consistency
- Evaluation region and KPI eligibility
- Mobility, traffic, routing and failure boundary conditions

## Antennas, RF and propagation

- Transmit power, conducted power, EIRP, regulatory constraints
- Carrier frequency, bandwidth, duplexing, numerology, aggregation
- Antenna height, gain, pattern, tilt, polarisation, sidelobes
- Array geometry, beamforming, beam training, misalignment
- MIMO rank, spatial correlation, CSI acquisition, delay and ageing
- Free-space (Friis) baseline
- Log-distance, dual-slope and multi-slope path loss
- Two-ray ground reflection
- Terrain, clutter and empirical models
- Geometry-based stochastic channel model
- Ray tracing, radio map or measurement-calibrated model
- Shadowing standard deviation and spatial and cross-link correlation
- Rayleigh, Rician and Nakagami fading; delay spread, Doppler, angular spread
- Thermal noise, noise figure, implementation loss, sensitivity
- Co-channel, adjacent-channel, cross-tier, cross-RAT and external interference
- Interference surrogates: conflict graphs, adjacency, protection distances
- Link adaptation, CQI, MCS, BLER mapping, HARQ, ARQ

## MAC, network and transport

- Scheduler and resource-allocation policy
- Queue discipline, buffer capacity, AQM, packet priority
- Random access, contention, CSMA/CA, grant-based and grant-free access
- Admission control, bearers and QoS flows, slicing
- Access, aggregation, backhaul, fronthaul, core, edge and cloud topology
- Capacity, propagation, serialisation, processing and queueing delay
- Routing, SDN control, multipath, fast reroute, convergence
- Encapsulation, MTU, tunnels, protocol overhead
- UDP, TCP, QUIC, SCTP and congestion control
- Control-plane traffic, telemetry and management overhead
- Logical coordination transport: loss, ordering, delay, shared or separate path

## Traffic, applications and mobility

- Periodic, Poisson, MMPP, self-similar, trace-driven and on/off traffic
- Packet-size and inter-arrival distributions
- Flow duration, session establishment, uplink/downlink asymmetry
- Deadline, reliability, freshness and age-of-information targets
- Priorities and pre-emption
- Correlated event bursts and failure-induced demand
- Utility classes: protection, SCADA, PMU, automation, AMI, DER/EV, video, updates
- Stationary, road-constrained, worker or equipment, vehicular, rail, UAV and group mobility
- Sequences of static snapshots re-solved between moves
- Time-of-day load and channel and failure evolution

## Decision, control and orchestration

- MDP, POMDP, Dec-POMDP, game, DCOP, planning or rule-system formulation
- Agent granularity and centralised or decentralised information
- Centralised training with decentralised execution, and its deployment gap
- Observation delay, noise, missingness and quantisation
- Discrete, continuous or hybrid actions and their constraints
- Decision interval, reasoning or inference latency, actuation latency
- Objective design, normalisation, multi-objective weights, hard constraints
- Safety shields, projection, constrained optimisation, risk sensitivity
- Separation of tuning and evaluation; generalisation
- Static, heuristic, exact, optimisation and learned baselines
- Tuning budget, seed stability, ablations, policy or rule-base size
- Compute capacity, edge queueing, placement, migration, scaling, failover

## Energy, security, resilience and cyber-physical systems

- Radio state machine; amplifier, circuit, baseband and compute energy
- Battery, ageing, harvesting, wake-up, network lifetime
- Node, link, site, backhaul, controller, edge, cloud and power failures
- Correlated and common-mode disasters and shared-risk groups
- Jamming, spoofing, replay, Sybil, false-data injection, denial of service
- Authentication, cryptographic overhead, detection and mitigation delay
- Adversarial or poisoned observations and Byzantine agents
- Power flow, DER, EV, storage, load, protection, state estimation
- Communication-to-grid and grid-to-communication dependencies
- Co-simulation time synchronisation and causality

## Experiment credibility

- Analytical sanity checks
- Unit, integration, regression and reachability tests
- Calibration and parameter provenance
- Independent validation against standards, traces, testbeds or measurements
- Seed strategy and independent replications, or declared determinism
- Confidence intervals, percentiles, warm-up and stopping criteria
- Sensitivity and robustness studies and conclusion-reversal regions
- Fair comparison budget and information parity
- Release of source code, configurations, environment, raw data, analysis and provenance
