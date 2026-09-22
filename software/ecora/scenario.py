"""Building the world a scenario declares, and refusing a world that is not it.

Until now the frozen ScenarioSpec described one world and the harness built another. The
topology and the disturbance list were opaque objects that nothing read, while the sites,
legs, periods and deadlines that actually ran were Python constants. The scenario hash was
bound into the provenance of every claim, so each claim cited a description rather than the
conditions it was produced under. That is a provenance defect, not a tidiness one: a reader
who fetched the scenario by its hash would have been told something false.

Two functions close it, and they are deliberately a pair.

`build_world` is the only supported way to obtain a model for a run: the scenario is the
source, the model is derived, and a scenario change needs no code change.

`verify_world` is the check for a model that arrived some other way. It compares what the
model holds against what the scenario declares and refuses the run on any disagreement,
so a hand-built world cannot quietly run under a scenario hash it does not match.

The world is finite and so is what a scenario may declare. Both legs the model reasons
about must be present, one flow per service class, and every disturbance must name a site
and a leg that exist. A scenario that declares something the model cannot build is
rejected when it is read, not discovered part-way through a run.
"""

import json
from pathlib import Path

from .contracts import Record, digest, require, validate
from .model import PACING_BPS, SERVICES, FiniteModel, Link

REQUIRED_LEGS = ("lte", "alternative")
SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"


def _link(entry):
    return Link(entry["leg_id"], entry["capacity_bps"], entry["delay_s"],
                entry["queue_limit_bytes"])


def _flows(scenario):
    flows = {}
    for flow in scenario["flows"]:
        require(flow["service"] not in flows,
                f"one flow per service class; {flow['service']} is declared twice")
        flows[flow["service"]] = flow
    require(set(flows) == set(SERVICES),
            f"a runnable scenario declares a flow for each of {', '.join(SERVICES)}")
    return flows


def build_world(scenario):
    """The FiniteModel that this scenario declares, with nothing supplied from code."""
    data = scenario.data if isinstance(scenario, Record) else scenario
    validate("ScenarioSpec", data)
    topology, flows = data["topology"], _flows(data)
    legs = {entry["leg_id"]: _link(entry) for entry in topology["legs"]}
    require(set(legs) >= set(REQUIRED_LEGS),
            f"the world reasons over {' and '.join(REQUIRED_LEGS)}; both must be declared")
    require(topology["initial_pacing"] in PACING_BPS,
            f"unknown pacing profile: {topology['initial_pacing']}")
    return FiniteModel(
        sites=list(topology["sites"]), links=legs, egress=_link(topology["egress"]),
        scada_period_s=flows["scada"]["generation"]["period_s"],
        ami_period_s=flows["ami"]["generation"]["period_s"],
        scada_bytes=flows["scada"]["payload_bytes"], ami_bytes=flows["ami"]["payload_bytes"],
        scada_deadline_s=flows["scada"]["deadline_s"], ami_deadline_s=flows["ami"]["deadline_s"],
        initial_path=topology["initial_path"], initial_pacing=topology["initial_pacing"],
        disturbances=[dict(d) for d in data["disturbances"]])


# The one requirement the assembled result stage can evaluate today. Measurements are
# keyed by metric alone and the study freezes a single cohort, so a second requirement
# naming the same metric would be scored against the first one's population.
DEFAULT_REQUIREMENTS = [
    {"requirement_id": "req:ami-delivery", "target": "site-1", "service": "ami",
     "metric": "within_age_delivery", "unit": "ratio", "comparator": "ge",
     "threshold": 0.95, "window_s": 10, "denominator": "generated readings",
     "missingness_limit": 0.05}]


def _entry(link):
    return {"leg_id": link.link_id, "capacity_bps": link.capacity_bps,
            "delay_s": link.delay_s, "queue_limit_bytes": link.queue_limit_bytes}


def describe_world(model, *, scenario_id="scenario:derived", revision="1",
                   requirements=None, required_capability_ids=(), parameter_set_hash=None,
                   initial_state=None, disturbances=None):
    """The scenario a model already is, so a derived world is still described accurately.

    A run assembled from a hand-built model still freezes a scenario hash into every claim
    it produces. Deriving that scenario from the model keeps the description true where the
    model did not come from a file, which is the other half of closing the same defect.
    """
    site = model.sites[0]
    flows = []
    for service in SERVICES:
        deadline = model.deadlines[service]
        flows.append({"flow_id": f"flow:{service}", "source": site, "destination": "central-1",
                      "service": service, "generation": {"period_s": model.periods[service]},
                      "payload_bytes": model.sizes[service], "deadline_s": deadline,
                      "max_deferral_s": 0 if service == "scada" else min(2.0, deadline / 2)})
    return Record("ScenarioSpec", {
        "scenario_id": scenario_id, "revision": revision, "synthetic": True,
        "topology": {"sites": list(model.sites),
                     "legs": [_entry(link) for _, link in sorted(model.links.items())],
                     "egress": _entry(model.egress),
                     "initial_path": model.path[site], "initial_pacing": model.pacing[site]},
        "flows": flows,
        "requirements": list(requirements if requirements is not None else DEFAULT_REQUIREMENTS),
        "initial_state": dict(initial_state or {}),
        "disturbances": [dict(d) for d in (model.disturbances if disturbances is None
                                           else disturbances)],
        "parameter_set_hash": parameter_set_hash or digest({"parameter_set": "v1-nominal-uncalibrated"}),
        "required_capability_ids": sorted(required_capability_ids)})


def _declared(scenario):
    """The model-visible facts a scenario declares, in the shape a model reports them."""
    topology, flows = scenario["topology"], _flows(scenario)
    return {"sites": tuple(topology["sites"]),
            "legs": {entry["leg_id"]: _link(entry) for entry in topology["legs"]},
            "egress": _link(topology["egress"]),
            "periods": {s: flows[s]["generation"]["period_s"] for s in SERVICES},
            "sizes": {s: flows[s]["payload_bytes"] for s in SERVICES},
            "deadlines": {s: flows[s]["deadline_s"] for s in SERVICES}}


def verify_world(model, scenario):
    """Refuse a model that does not hold what its scenario declares."""
    data = scenario.data if isinstance(scenario, Record) else scenario
    declared = _declared(data)
    actual = {"sites": model.sites, "legs": model.links, "egress": model.egress,
              "periods": dict(model.periods), "sizes": dict(model.sizes),
              "deadlines": dict(model.deadlines)}
    for field, expected in declared.items():
        require(actual[field] == expected,
                f"the model does not match scenario {data['scenario_id']}: "
                f"{field} is {actual[field]!r}, the scenario declares {expected!r}")
    return model


def load(path):
    """Read a scenario file into a validated, content-addressed record."""
    return Record("ScenarioSpec", json.loads(Path(path).read_text(encoding="utf-8")))


def catalogue(directory):
    """Every scenario file in a directory, by identifier, in a stable order."""
    found = {}
    for path in sorted(Path(directory).glob("*.json")):
        scenario = load(path)
        identity = scenario.data["scenario_id"]
        require(identity not in found, f"two files declare {identity}")
        found[identity] = scenario
    return found
