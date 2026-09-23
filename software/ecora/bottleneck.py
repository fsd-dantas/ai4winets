"""The shared-bottleneck pilot: where SCADA and AMI contend, and how much it costs.

v1-scope puts both services' site-to-central traffic through one finite egress queue and
asks that the contention there be demonstrated and measured independently, with capacity
labels resting on an uncontrolled pilot and deadline-aware service evidence rather than
on offered bitrate. This module is that pilot.

The design isolates contention from overload. The workload is fixed: the nominal scenario
with AMI every 100 ms, so the two classes offer comparable load. The egress capacity is
swept, and every capacity is run twice, once with AMI released at the normal pacing
profile and once throttled to the minimum. Where SCADA meets its deadlines with AMI
throttled and misses them with AMI at normal, the difference is AMI's share of the one
queue both cross: that is the shared bottleneck, and the pacing lever is what relieves it.
Where SCADA misses with AMI throttled too, the egress is too narrow for SCADA alone, which
is overload rather than contention.

Both worlds run the same grid and report the same instrumentation: per class at the
egress, arrivals, departures, drops and queueing delay; and the queue's occupancy over
time. Nothing is controlled during a run: no controller, no action, only the world.
"""

import copy
import json
from pathlib import Path

from .contracts import Record, digest, require
from .scenario import SCENARIOS, build_world, load

DATASET = Path(__file__).resolve().parents[2] / "data" / "simulator" / "bottleneck-pilot.json"
VERSION = "bottleneck-pilot-v1"
CAPACITIES = [48000, 56000, 64000, 72000, 80000, 96000, 128000, 256000]
PACINGS = ("normal", "minimum")
AMI_PERIOD_S = 0.1
HORIZON_S = 8.0
# Cohorts start after the LTE attach and end one period of settling before the stop.
WINDOW = {"start_s": 1.5, "end_s": 7.0}
SERVICE_TARGET = 0.99


def variant(base, capacity_bps, pacing, ami_period_s=AMI_PERIOD_S):
    """The nominal scenario with the egress, pacing and AMI period the pilot varies."""
    data = copy.deepcopy(base.data if isinstance(base, Record) else base)
    data["scenario_id"] = f"scenario:pilot-bottleneck-{capacity_bps}-{pacing}"
    data["topology"]["egress"]["capacity_bps"] = capacity_bps
    data["topology"]["initial_pacing"] = pacing
    for flow in data["flows"]:
        if flow["service"] == "ami":
            flow["generation"]["period_s"] = ami_period_s
    data["initial_state"] = {"note": "Bottleneck pilot variant of the nominal scenario; "
                                     "not a member of any scenario set."}
    return Record("ScenarioSpec", data)


def _specs():
    return [{"cohort_id": f"cohort:{service}:pilot", "service": service,
             "deadline_s": 0, "generation_window": dict(WINDOW)} for service in ("scada", "ami")]


def _outcome(cohorts, queues):
    services = {}
    for cohort in cohorts:
        generated = cohort["generated"]
        services[cohort["service"]] = {
            "generated": generated, "on_time": cohort["delivered_on_time"],
            "late": cohort["delivered_late"], "lost": cohort["lost"],
            "pending": cohort["pending"],
            "on_time_ratio": cohort["delivered_on_time"] / generated if generated else None}
    return {"services": services, "egress": {name[7:]: queue for name, queue in queues.items()
                                             if name.startswith("egress/")},
            "legs": {name: queue for name, queue in queues.items()
                     if not name.startswith("egress/")}}


def run_finite(scenario, horizon=HORIZON_S):
    model = build_world(scenario).advance_to(horizon)
    return _outcome(model.cohorts(_specs()), model.queues())


def run_simulated(scenario, horizon=HORIZON_S, command=None):
    from .simulator import Ns3World, verify_simulated
    with Ns3World.start(scenario, command) as world:
        verify_simulated(world.resolved, scenario)
        world.advance_to(horizon)
        return _outcome(world.cohorts(_specs()), world.queues())


def labels(cells):
    """What the grid establishes, per world, from the SCADA outcome alone.

    `attainable` is the smallest capacity at which SCADA meets its target under each
    pacing profile. `contended` lists the capacities where it meets it only with AMI
    throttled: the band where the bottleneck is shared rather than simply too narrow.
    """
    met = {}
    for cell in cells:
        ratio = cell["outcome"]["services"]["scada"]["on_time_ratio"]
        met[(cell["capacity_bps"], cell["pacing"])] = ratio is not None and ratio >= SERVICE_TARGET
    capacities = sorted({capacity for capacity, _ in met})
    attainable = {pacing: next((c for c in capacities if met[(c, pacing)]), None)
                  for pacing in {pacing for _, pacing in met}}
    contended = [c for c in capacities if met.get((c, "minimum")) and not met.get((c, "normal"))]
    return {"service_target": SERVICE_TARGET, "attainable_capacity_bps": attainable,
            "contended_capacities_bps": contended}


def pilot(base=None, worlds=("finite", "simulated"), capacities=CAPACITIES, pacings=PACINGS):
    """Run the grid in each world and assemble the dataset."""
    base = base or load(SCENARIOS / "s0-nominal.json")
    runners = {"finite": run_finite, "simulated": run_simulated}
    results = {}
    for world in worlds:
        cells = []
        for capacity in capacities:
            for pacing in pacings:
                cells.append({"capacity_bps": capacity, "pacing": pacing,
                              "outcome": runners[world](variant(base, capacity, pacing))})
        results[world] = {"cells": cells, "labels": labels(cells)}
    return results


def dataset(base, results, build_id=None, model_hash=None):
    data = base.data if isinstance(base, Record) else base
    body = {"pilot_version": VERSION, "base_scenario_id": data["scenario_id"],
            "base_scenario_revision": data["revision"],
            "base_scenario_hash": base.content_hash if isinstance(base, Record) else digest(data),
            "simulator_build_id": build_id, "model_hash": model_hash,
            "design": {"varied": "egress capacity and AMI pacing profile",
                       "fixed": f"nominal scenario, AMI every {AMI_PERIOD_S} s, no controller",
                       "capacities_bps": sorted({c["capacity_bps"] for w in results.values()
                                                 for c in w["cells"]}),
                       "pacings": list(PACINGS), "horizon_s": HORIZON_S, "window": WINDOW,
                       "queueing_delay": "arrival to start of transmission",
                       "occupancy_difference": "ns-3 excludes the datagram on the wire; "
                                               "the finite world includes it"},
            "results": results}
    return {**body, "dataset_hash": digest(body)}


def write(built, path=DATASET):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(built, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                    newline="\n")
    return path


def load_dataset(path=DATASET):
    built = json.loads(Path(path).read_text(encoding="utf-8"))
    require(built["dataset_hash"] == digest({k: v for k, v in built.items()
                                             if k != "dataset_hash"}),
            "the pilot dataset was altered")
    return built
