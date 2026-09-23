# Spatial world and boundary model

**Status: normative methodology.** [Framework](README.md)

This document defines how a study represents the extent of the simulated world, its entity populations,
external influences, spatial boundaries and evaluation eligibility.

A world model is a scientific assumption, not a simulator implementation detail. It affects interference, edge
effects, association alternatives, mobility, routing, resource contention, traffic aggregation, failure
propagation and the transferability of any decision policy.

## Definitions

| Term | Definition |
| --- | --- |
| Region of interest (ROI) | Spatial region whose eligible entities and flows contribute to primary KPIs |
| Evaluation population | Nodes, flows, links or events eligible for primary KPI aggregation |
| Simulation domain | Region in which entities are explicitly instantiated and simulated |
| Guard region | Non-evaluated area around the ROI that contributes interference, load, mobility or topology effects |
| External environment | Influence from beyond the simulation domain, represented explicitly, statistically, analytically or as negligible |
| World mode | The spatial closure and boundary semantics a scenario uses |
| Spatial population process | The rule that places entities: fixed inventory, lattice, map-constrained placement, Poisson point process, cluster process, trace or another declared process |

An executable simulation is always finite in memory and time. An `open_stochastic` model means the underlying
population process is unbounded, while the simulator evaluates a finite window and uses a documented truncation,
guard, replication or residual-interference approximation.

## World modes

| Mode | Meaning | Appropriate use | Main limitation |
| --- | --- | --- | --- |
| `finite_closed` | Only entities inside a bounded domain exist | Isolated laboratory, shielded facility, small private deployment, single cell | May underestimate external interference, arrivals, alternatives and edge load |
| `finite_guarded` | ROI plus explicit non-evaluated guard entities | Most system-level wireless experiments | Guard width must be justified by convergence |
| `wraparound` | Boundary conditions replicate a periodic topology | Homogeneous regular cellular or lattice experiments | Invalid for unique terrain, irregular maps or non-periodic infrastructure |
| `open_stochastic` | Entities arise from an unbounded stochastic process, approximated locally | Density, interference, scalability and generalisation studies | Requires careful truncation or tail modelling |
| `trace_bounded` | A map, inventory or trace defines the world and its boundary | Digital twins, deployment planning, field-calibrated studies, map-derived problem instances | Validity depends on the completeness and calibration of the trace |
| `hybrid_external_field` | Explicit ROI plus a statistical external interference or load field | Large networks whose external topology is unavailable or costly | Does not reproduce specific external topology or control interactions |
| `non_spatial` | Geometry plays no part in the model | Logical topologies and abstract problem instances | No spatial claim is supported |

## Default policy

For system-level wireless studies that make radio or interference claims, `finite_guarded` is the default world
mode unless a scenario gives a stronger deployment-specific justification. Any other mode states why it is fit
for the claim; `finite_closed` in particular states why nothing outside the domain can move the conclusion.

Primary KPIs are aggregated only over the evaluation population. Guard-region entities influence RF, load,
traffic, queues, association, mobility and routing where those subsystems are modelled, but are not included
in primary KPI aggregates.

## World declaration

A scenario declares a `world_model` of at least this shape (values illustrative):

```json
{
  "world_model": {
    "mode": "finite_guarded",
    "coordinate_system": {"reference": "local_cartesian", "unit": "m"},
    "evaluation_window": {"shape": "rectangle", "width_m": 1000, "height_m": 1000, "kpi_population": "roi_only"},
    "simulation_window": {"shape": "rectangle", "width_m": 1800, "height_m": 1800},
    "population_model": {"type": "fixed_topology", "topology_source": "scenario", "spatial_process": null},
    "external_world": {"enabled": true, "representation": "guard_region", "calibration_reference": null},
    "boundary_conditions": {
      "rf": "guarded",
      "mobility": "scenario_defined",
      "traffic": "scenario_defined",
      "routing": "finite_topology",
      "control": "deployment_observable_only"
    },
    "evaluation_eligibility": {
      "nodes": "roi_only",
      "flows": "roi_endpoint_or_declared_flow_set",
      "links": "associated_with_eligible_flows"
    },
    "convergence": {
      "required": true,
      "reference_model": "expanded_domain",
      "target_metrics": ["outage_probability", "latency_p99_ms"],
      "relative_tolerance": 0.02
    }
  }
}
```

## RF boundary semantics

For a receiver $u$, interference conceptually accounts for entities inside the ROI, entities in the guard
region, and residual influence beyond the explicit domain:

$$
I_u = \sum_{x_i \in \mathcal{A}_{\mathrm{ROI}}} P_i g_{iu}
+ \sum_{x_j \in \mathcal{A}_{\mathrm{guard}}} P_j g_{ju}
+ I_{\mathrm{external},u}.
$$

A scenario states how $I_{\mathrm{external},u}$ is represented:

- `none_justified`: only where physical isolation, measured shielding or the claim's scope supports it;
- `guard_truncation`: contributions beyond a converged guard width assumed negligible;
- `stochastic_background`: a sampled external interferer or load field;
- `analytical_tail`: a residual estimate from the declared population and propagation process;
- `map_or_trace`: explicit external infrastructure or measurements;
- `periodic_replication`: wrap-around topology.

## Mobility boundary semantics

A scenario specifies one of:

- `terminate`: the entity or session ends at the boundary;
- `reflect`: the direction of motion is reflected;
- `reroute`: the trajectory is recomputed under a map or network constraint;
- `respawn`: the entity is replaced to preserve population or load;
- `wrap`: the entity re-enters through the opposite boundary;
- `trace_constrained`: the trace determines valid motion;
- `stationary`: mobility does not apply.

The choice must agree with the population and traffic model. `wrap` generally suits only a periodic,
homogeneous world; `trace_constrained` suits roads, factories, substations and map-specific studies.

## Traffic and routing boundary semantics

The world declaration distinguishes:

- whether arrivals come from a finite population or an open, regenerative process;
- whether routes may traverse guard or external nodes;
- whether backhaul or core connectivity terminates at a boundary gateway;
- whether external traffic competes for shared resources;
- whether failures can propagate from external entities into the ROI.

## Edge-effect control

A finite approximation demonstrates that its boundary does not materially bias the primary conclusion. For a
target metric $M$, compare a candidate domain or guard width $w$ with an expanded reference $w + \Delta w$:

$$
\delta_M(w) = \frac{|M(w) - M(w + \Delta w)|}{\max(|M(w + \Delta w)|, \varepsilon)}.
$$

The candidate is accepted only if $\delta_M(w) \le \tau_M$ for every predeclared primary metric, where $\tau_M$
is the scenario's declared tolerance and $\varepsilon$ a small numerical stabiliser.

Where applicable, edge sensitivity is evaluated at least for:

- low-percentile SINR or received power;
- outage probability;
- the throughput or goodput distribution;
- tail latency;
- association, handover or routing decisions;
- the action distribution of any decision policy.

A `finite_closed` world with no external entities by construction replaces this test with its justification
for closure.

## Observability rule

Fields such as `region_class`, `distance_to_roi_boundary_m` or a simulator-only decomposition of external
interference may be recorded for diagnostics. They are not supplied to a decision policy unless the observation
is feasible in the target deployment and declared in the observation contract.

## Required reporting

Every study with a spatial world model reports:

- the world mode and coordinate reference;
- ROI and simulation-domain geometry;
- guard width or open-world truncation radius;
- the population process and its density or inventory source;
- boundary semantics for RF, mobility, traffic, routing and failures;
- the KPI eligibility rule;
- the representation of the external world and its interference;
- convergence or sensitivity evidence;
- random seeds and the spatial realisation policy.
