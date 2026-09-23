# Control, compute, energy, security and cyber-physical model

**Status: normative methodology.** [Framework](README.md)

This document defines how a study represents decision-making, multi-agent coordination, observability,
computation, energy, failures, security and cyber-physical dependencies. It applies to every kind of decision
method: rule-based and expert systems, symbolic planning, optimisation, distributed constraint algorithms,
game-theoretic methods and learned policies.

## Decision formulation

A controlled scenario defines its decision process. In the general sequential form, agent $i$ acts in

$$
\mathcal{M}_i = (\mathcal{S}_i, \mathcal{O}_i, \mathcal{A}_i, P, R_i, \gamma),
$$

where $\mathcal{S}_i$ is state, $\mathcal{O}_i$ observation, $\mathcal{A}_i$ action, $P$ the transition
process, $R_i$ the objective or reward and $\gamma$ the discount factor.

The study states which formalism it uses: MDP, POMDP, Dec-POMDP, constrained MDP, game, distributed constraint
optimisation, classical planning problem, rule system over declared evidence, or another. A method that does
not optimise a reward still declares its state, observations, actions, decision instants and objective or goal
conditions, because those are what a baseline must share.

## Decision-policy declaration

```json
{
  "control_model": {
    "enabled": true,
    "method_family": "rule_based_planning_optimisation_distributed_constraint_learned_or_declared",
    "agent_granularity": "base_station_relay_gateway_region_controller_or_declared",
    "decision_formalism": "declared",
    "information_structure": "centralised_decentralised_CTDE_or_declared",
    "observations": {
      "features": ["declared"],
      "sampling_interval_ms": 100,
      "measurement_delay_ms": 20,
      "noise_missingness_quantization": "declared",
      "deployment_feasible_only": true
    },
    "actions": {
      "variables": ["association_power_routing_scheduling_channel_or_declared"],
      "space": "discrete_continuous_hybrid",
      "actuation_delay_ms": 20,
      "constraints": "declared"
    },
    "objective": {
      "terms": ["declared"],
      "normalization": "declared",
      "weights": "declared",
      "constraint_treatment": "declared"
    },
    "algorithm": {
      "name": "declared",
      "parameters_reference": "declared",
      "training_steps": "learned methods only",
      "seed_policy": "declared"
    },
    "baselines": ["static", "heuristic", "exact_or_oracle_reference_if_tractable"],
    "generalization_axes": ["topology", "load", "channel", "failure", "mobility"]
  }
}
```

Values are illustrative.

## Validity rules for every decision method

- An agent does not observe simulator-only information unavailable in deployment, unless the study explicitly
  evaluates privileged information and declares the deployment gap.
- Every method is compared with meaningful baselines under comparable action constraints and information
  availability.
- Objective components, weights, normalisation and constraint treatment are reported.
- Decision interval, telemetry delay, actuation delay and computation time are represented or justified as
  negligible.
- A method whose tuning (rule thresholds, heuristics, search budgets, hyperparameters) was chosen by looking at
  results is evaluated on configurations and seeds not used for that tuning.

## Additional rules for learned policies

- Training and evaluation use separate seeds and, where generalisation is claimed, separate topology, channel,
  traffic and failure realisations.
- Training stability is reported across independent initialisation and training seeds.
- Algorithm and implementation version, hyperparameters and tuning budget, training steps, hardware and
  wall-clock cost, learning curves with uncertainty, and ablations are reported.

## Constrained and safe control

When actions can violate service, power, spectrum, safety or operational constraints, declare the enforcement
mechanism:

- hard feasibility projection;
- action masking;
- a rule-based safety shield;
- constrained optimisation or a Lagrangian method;
- chance constraints or a risk-sensitive objective;
- post-decision validation and rollback;
- hard constraints represented as forbidden values rather than finite penalties.

A penalty term alone is not assumed to guarantee hard operational safety.

## Compute and orchestration

Where control, inference, digital-twin processing, edge computing, virtualised functions or orchestration delay
can affect conclusions, model:

- CPU, GPU or NPU capacity;
- task size and arrival process;
- queueing and scheduling at edge and cloud nodes;
- inference or reasoning latency and model-update cadence;
- telemetry volume, compression, transport and storage;
- start-up, migration, placement, scaling and failure recovery of functions;
- controller overload, failover and control-plane network dependency.

Where computation is measured in a machine-independent unit instead (inference passes, search expansions, table
entries, messages), say so and do not convert it into time without a calibration.

## Energy

Where energy, battery life, UAV operation, device longevity or sustainability is a claim, declare:

- the radio state machine: sleep, idle or listen, receive, transmit and transitions;
- the transmit-power and power-amplifier efficiency model;
- circuit, baseband and compute power;
- battery capacity and discharge, with ageing and temperature where material;
- energy harvesting and storage policy where applicable;
- the energy accounting boundary;
- the definition of network lifetime.

Energy is not reduced to $E = P_{\mathrm{tx}}\,t$ unless receive, idle, retransmission, transition and compute
energy are demonstrably irrelevant to the claim.

## Security and resilience

A resilience or security scenario states its failure or attack process, correlation structure, detection,
mitigation and recovery behaviour, and success criterion. Model classes include:

- node, radio, link, backhaul, site, controller, edge, cloud and power-supply failures;
- common-mode disasters and shared-risk groups;
- jamming: barrage, reactive, selective, protocol-aware;
- spoofing, replay, Sybil, false-data injection and route manipulation;
- denial of service, control-plane overload and controller compromise;
- poisoned telemetry, adversarial observations, malicious or Byzantine agents, objective manipulation;
- authentication, key management, detection and mitigation delay.

Independent Bernoulli failures are not the only model for a claim about cascading, geographically correlated,
cyber-physical or disaster resilience. Scheduled, declared disturbances are a legitimate model for controlled
comparisons, and are declared as such rather than as a failure process.

## Cyber-physical coupling

When network behaviour affects a physical process, the feedback loop is modelled explicitly:

```text
physical state -> traffic and control demand -> network state -> delay, loss, availability
  -> control action -> physical state
```

For power-system studies, declare as applicable:

- the power-flow abstraction: DC, AC, linearised distribution or unbalanced three-phase;
- DER, storage, EV, renewable and load profiles;
- protection logic and fault-clearing times;
- state-estimation measurement timing and quality;
- voltage, frequency, demand-response and FLISR loops;
- communication power dependence, backup power, restoration order and outage propagation;
- the co-simulation synchronisation policy and time-step or event semantics.

Use co-simulation only where the feedback loop is necessary to the hypothesis. Otherwise declare an exogenous
physical-event abstraction.
