"""Calibrating the finite world's reading of the LTE leg from the simulator.

A scenario's LTE leg carries, under `logical`, how the finite world reads it: a capacity and
a table from extra path loss and cell load to rate. Until measured, those were nominal.
This module measures them in ns-3 and writes them back, so the finite world's
interpretation is a measurement of the leg the simulator runs rather than an estimate of it.

The measurement is saturation goodput: offered load well above the leg's ceiling, and the
application bytes received inside a window after attach. It is taken with the simulator's
own LTE construction (`ecora-calibrate` includes it), over a grid of losses and competing
UEs, and under several random runs so that any variance shows. The unloaded cell is also
measured downlink, for the record.

What saturation goodput is, and is not, matters here. It is the share a site gets when it
wants more than it can have. A site carrying a light load is served sooner than that share
suggests, because proportional fairness favours a low-rate user; so the table predicts the
leg's behaviour once demand reaches the share, which is when degradation happens, and
overstates the harm below it.

Two choices are recorded rather than made silently:

- **The finite world reads one rate for both directions, and it is the uplink's.** Every
  obligation's payload travels up: AMI readings, and SCADA responses. The downlink carries
  only the small request and was measured to hold on to higher loss, so using the uplink
  figure is exact for what limits a transaction and conservative for the request.
- **The table is a step function over measured points.** The finite world takes the rate
  of the largest measured loss not above the impairment, so between two points it is
  optimistic by at most the difference between them. Nothing is interpolated.
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .contracts import MAX_COMPETING_UES, Record, canonical, digest, require

DATASET = Path(__file__).resolve().parents[2] / "data" / "simulator" / "lte-rate-calibration.json"
VERSION = "lte-rate-calibration-v1"
# The unloaded cell, finely around the uplink cliff and past the downlink one.
GRID = [0, 10, 20, 24, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 49, 49.5, 49.75, 50,
        52, 54, 56, 60]
# Loaded cells: the loss levels where a load changes what a site can get.
LOADED_GRID = [0, 20, 30, 36, 40, 44, 46, 47, 48, 49, 49.75]
COMPETITORS = [1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, MAX_COMPETING_UES]
DIRECTIONS = ("up", "down")
RUNS = (1, 2, 3)
WORKERS = 8


def calibrate_command():
    """How to start the calibration program on this host."""
    explicit = os.environ.get("ECORA_CALIBRATE")
    if explicit:
        return explicit.split()
    if sys.platform == "win32":
        return ["wsl.exe", "-e", "bash", "-c",
                'exec "${ECORA_NS3_ROOT:-$HOME/ecora-ns3}/out/ecora-calibrate" "$@"', "calibrate"]
    root = Path(os.environ.get("ECORA_NS3_ROOT", "~/ecora-ns3")).expanduser()
    return [str(root / "out" / "ecora-calibrate")]


def measure_point(scenario, loss_db, direction, run, competitors=0, command=None):
    """One saturation measurement, as the calibration program reports it."""
    command = (command or calibrate_command()) + [
        "--scenario=-", f"--loss={loss_db}", f"--direction={direction}", f"--run={run}",
        f"--competitors={competitors}"]
    completed = subprocess.run(command, input=json.dumps(scenario).encode(),
                               capture_output=True, timeout=600)
    require(completed.returncode == 0,
            f"calibration failed at {loss_db} dB, {competitors} competitors, {direction}: "
            f"{completed.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return json.loads(completed.stdout.decode("utf-8").strip().splitlines()[-1])


def plan(grid=GRID, loaded_grid=LOADED_GRID, competitors=COMPETITORS, directions=DIRECTIONS,
         runs=RUNS):
    """Every point to measure: the unloaded cell both ways, each load level uplink."""
    points = [(loss, direction, run, 0) for direction in directions for loss in grid
              for run in runs]
    points += [(loss, "up", run, level) for level in competitors for loss in loaded_grid
               for run in runs]
    return points


def measure(scenario, points=None, command=None, workers=WORKERS):
    """Measure every planned point. Each is its own process, so order cannot matter."""
    points = plan() if points is None else points
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda p: measure_point(scenario, p[0], p[1], p[2], p[3], command),
                             points))


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def spread(points):
    """Per direction, load and loss: the median over runs and the range around it."""
    grouped = {}
    for point in points:
        key = (point["direction"], point.get("competitors", 0), point["loss_db"])
        grouped.setdefault(key, []).append(point["goodput_bps"])
    return {key: {"median": _median(rates), "min": min(rates), "max": max(rates), "runs": len(rates)}
            for key, rates in grouped.items()}


def derive_table(points):
    """The finite world's capacity and rate table, from the uplink points.

    The statistic is the median over runs. The LTE error model draws each transport
    block's fate, so near a cliff runs differ, and past it one run can decode a stray
    datagram; a median of three is not moved by one. Away from the cliffs every run agreed
    exactly. The range is kept in the dataset so the choice can be seen.

    Each load level is its own loss table: its entry at zero loss, then an entry wherever
    the rate changes. A rate that rises with loss, or with load at the same loss, is
    refused as noise the grid did not resolve.
    """
    uplink = {}
    for (direction, level, loss), summary in spread(points).items():
        if direction == "up":
            uplink.setdefault(level, {})[loss] = summary["median"]
    require(0 in uplink and 0 in uplink[0], "the grid covers the unloaded, unimpaired cell")
    capacity = uplink[0][0]
    require(capacity > 0, "the leg delivers nothing at zero loss")
    table = []
    for level in sorted(uplink):
        losses = sorted(uplink[level])
        require(losses[0] == 0, f"the grid at {level} competitors starts at zero loss")
        current = None
        for loss in losses:
            rate = uplink[level][loss]
            require(current is None or rate <= current,
                    f"the median rate rises with loss at {loss} dB, {level} competitors")
            if current is None or rate != current:
                table.append({"extra_loss_db": loss, "competing_ues": level, "capacity_bps": rate})
                current = rate
        require(current == 0, f"the grid at {level} competitors reaches the leg's cliff")
    levels = sorted(uplink)
    for lower, higher in zip(levels, levels[1:]):
        for loss in set(uplink[lower]) & set(uplink[higher]):
            require(uplink[higher][loss] <= uplink[lower][loss],
                    f"the median rate rises with load at {loss} dB, {higher} competitors")
    return {"direction": "up", "capacity_bps": capacity, "rate_table": table}


def lte_leg(scenario):
    data = scenario.data if isinstance(scenario, Record) else scenario
    return next(leg for leg in data["topology"]["legs"] if leg["kind"] == "lte")


def dataset(scenario, points, build_id, model_hash, calibrate_source_sha256):
    """The calibration as a record: what was measured, with what, and what it implies."""
    data = scenario.data if isinstance(scenario, Record) else scenario
    leg = lte_leg(data)
    ids = {point.pop("build_id") for point in points}
    require(ids == {build_id}, "the points were measured with a build other than the manifest's")
    body = {"calibration_version": VERSION,
            "measured_leg": {"radio": leg["radio"], "queue_limit_bytes": leg["queue_limit_bytes"]},
            "scenario_id": data["scenario_id"], "scenario_revision": data["revision"],
            "simulator_build_id": build_id, "model_hash": model_hash,
            "calibrate_source_sha256": calibrate_source_sha256,
            "method": {"measure": "saturation goodput of application payload",
                       "window_s": points[0]["window_s"], "payload_bytes": points[0]["payload_bytes"],
                       "offered_bps": {d: next(p["offered_bps"] for p in points if p["direction"] == d)
                                       for d in sorted({p["direction"] for p in points})},
                       "runs": sorted({p["rng_run"] for p in points}),
                       "grid_db": sorted({p["loss_db"] for p in points}),
                       "competitors": sorted({p.get("competitors", 0) for p in points}),
                       "competitor_offered_bps": 20e6,
                       "statistic": "median over runs, uplink; range recorded per point",
                       "caveat": "saturation share; a light load is served sooner than this"},
            "points": sorted(points, key=lambda p: (p["direction"], p.get("competitors", 0),
                                                    p["loss_db"], p["rng_run"])),
            "spread": [{"direction": d, "competitors": c, "loss_db": l, **summary}
                       for (d, c, l), summary in sorted(spread(points).items())],
            "table": derive_table(points)}
    return {**body, "dataset_hash": digest(body)}


def verify(calibration):
    body = {k: v for k, v in calibration.items() if k != "dataset_hash"}
    require(calibration["dataset_hash"] == digest(body), "the calibration dataset was altered")
    require(calibration["table"] == derive_table(calibration["points"]),
            "the table does not follow from the points")
    return calibration


def apply(scenario, calibration):
    """The scenario with its LTE interpretation replaced by the measured one.

    Refused if the scenario's LTE leg is not the leg that was measured: a table measured on
    one radio configuration says nothing about another.
    """
    data = json.loads(canonical(scenario.data if isinstance(scenario, Record) else scenario))
    leg = lte_leg(data)
    require({"radio": leg["radio"], "queue_limit_bytes": leg["queue_limit_bytes"]}
            == calibration["measured_leg"],
            f"{data['scenario_id']} declares an LTE leg other than the one measured")
    table = calibration["table"]
    leg["logical"] = {key: value for key, value in leg["logical"].items() if key != "loss_rates"}
    leg["logical"].update(capacity_bps=table["capacity_bps"], rate_table=table["rate_table"],
                          calibration=calibration["dataset_hash"])
    return data


def load(path=DATASET):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(calibration, path=DATASET):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(calibration, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")
    return path
