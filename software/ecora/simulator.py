"""The simulator adapter: the ns-3 world, driven across a process boundary.

system/simulator-adapter.md settles the boundary: the simulator is a separate process,
one request and one response per call, framed as a four-byte big-endian length followed by
JSON. This module is the Python side of it.

Four of the protocol's rules are enforced here rather than trusted to the other side:

- **Every response is attributable.** It carries the simulator's build identity, and a
  response whose identity differs from the committed manifest's is refused. A result from
  a build other than the one the manifest describes cannot enter a run.
- **Every response answers its request.** A response to another request, or of another
  kind, is refused rather than matched up afterwards.
- **A refusal is a result.** The simulator's refusal is raised with its code and reason,
  never replaced by a value the adapter made up.
- **A crash is not an answer.** A process that exits or closes its output mid-exchange
  raises, so the run can be quarantined rather than continued on a guess.

Acceptance 1 of the adapter contract, that one scenario builds both worlds and each reports
holding what it declares, is `verify_simulated`: the same check `verify_world` makes of the
finite model, made against what the simulator's `configure` reports it built.
"""

import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from .contracts import ContractError, Record, canonical, require
from .model import PACING_BPS

COMMAND_ENV = "ECORA_SIMULATOR"
ROOT_ENV = "ECORA_NS3_ROOT"


class SimulatorRefusal(ContractError):
    """The simulator declined a request and said why."""

    def __init__(self, code, detail):
        super().__init__(f"simulator refused ({code}): {detail}")
        self.code = code
        self.detail = detail


class SimulatorCrashed(ContractError):
    """The simulator stopped answering. The run cannot continue on what it last said."""


def default_command():
    """How to start the simulator on this host, or None if there is no way to.

    `ECORA_SIMULATOR` names a command explicitly. Otherwise the build's default location is
    used: directly on Linux, and through WSL on Windows, where the build lives.
    """
    explicit = os.environ.get(COMMAND_ENV)
    if explicit:
        return explicit.split()
    if sys.platform == "win32":
        if not shutil.which("wsl.exe"):
            return None
        return ["wsl.exe", "-e", "bash", "-c",
                'exec "${ECORA_NS3_ROOT:-$HOME/ecora-ns3}/out/ecora-sim"']
    binary = Path(os.environ.get(ROOT_ENV, "~/ecora-ns3")).expanduser() / "out" / "ecora-sim"
    return [str(binary)] if binary.exists() else None


class SimulatorClient:
    """One conversation with one simulator process."""

    def __init__(self, reader, writer, expected_build_id, process=None):
        require(expected_build_id, "a simulator is only trusted against a declared build")
        self._reader = reader
        self._writer = writer
        self._process = process
        self.expected_build_id = expected_build_id
        self._next = 0
        self.exchanges = 0

    @classmethod
    def spawn(cls, command=None, expected_build_id=None):
        """Start the simulator and hold it to the committed manifest's build identity."""
        from . import ns3build
        command = command or default_command()
        require(command, "no simulator is available on this host")
        if expected_build_id is None:
            expected_build_id = ns3build.load()["simulator_build_id"]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        return cls(process.stdout, process.stdin, expected_build_id, process)

    def _read_exactly(self, size):
        data = b""
        while len(data) < size:
            chunk = self._reader.read(size - len(data))
            if not chunk:
                raise SimulatorCrashed(self._crash_detail())
            data += chunk
        return data

    def _crash_detail(self):
        detail = "the simulator closed its output mid-exchange"
        if self._process is not None:
            self._process.wait(timeout=5)
            error = self._process.stderr.read().decode("utf-8", "replace").strip()
            detail += f" (exit {self._process.returncode})"
            if error:
                detail += f": {error.splitlines()[0]}"
        return detail

    def request(self, kind, **body):
        """Send one request and return its result, or raise the simulator's refusal."""
        self._next += 1
        message = {"request_id": self._next, "kind": kind, **body}
        # The same canonical encoding the records use, so the adapter adds no second one.
        payload = canonical(message)
        try:
            self._writer.write(struct.pack(">I", len(payload)) + payload)
            self._writer.flush()
        except (BrokenPipeError, OSError) as exc:
            raise SimulatorCrashed(f"the simulator stopped accepting requests: {exc}") from exc
        size = struct.unpack(">I", self._read_exactly(4))[0]
        response = json.loads(self._read_exactly(size).decode("utf-8"))
        self.exchanges += 1
        require(response.get("build_id") == self.expected_build_id,
                f"response from build {str(response.get('build_id'))[:12]}, "
                f"the manifest describes {self.expected_build_id[:12]}")
        require(response.get("request_id") == self._next and response.get("kind") == kind,
                "the simulator answered a different request")
        if response["status"] != "ok":
            reason = response.get("reason") or {}
            raise SimulatorRefusal(reason.get("code", "unstated"), reason.get("detail", ""))
        return response["result"]

    def close(self):
        if self._process is None:
            return
        try:
            if self._process.poll() is None:
                self.request("shutdown")
        except ContractError:
            pass
        finally:
            for stream in (self._writer, self._reader, self._process.stderr):
                try:
                    stream.close()
                except OSError:
                    pass
            if self._process.poll() is None:
                self._process.kill()
            self._process.wait(timeout=10)
            self._process = None


class Ns3World:
    """The simulated world behind the six-call interface, as far as it is implemented.

    `advance_to` and `cohorts` are answered by the simulator. `observations`, `apply` and
    `truth` are forwarded and currently refused by it, with its reason; they are not
    filled in here, because a world that approximated them would be claiming evidence it
    does not produce.
    """

    def __init__(self, client, scenario, rng_run=1):
        self.client = client
        data = scenario.data if isinstance(scenario, Record) else scenario
        self.scenario = data
        self.resolved = client.request("configure", scenario=data, rng_run=rng_run)
        self.now = 0.0

    @classmethod
    def start(cls, scenario, command=None, rng_run=1):
        return cls(SimulatorClient.spawn(command), scenario, rng_run)

    def advance_to(self, time_s):
        require(time_s >= self.now, "the model clock cannot move backwards")
        self.now = self.client.request("advance", time_s=time_s)["time_s"]
        return self

    def cohorts(self, cohort_specs):
        return self.client.request("cohorts", cohort_specs=list(cohort_specs))["cohorts"]

    def accounting(self, cohort_specs=()):
        return self.client.request("cohorts", cohort_specs=list(cohort_specs))["accounting"]

    def observations(self, *, capability_ids, window_s=1.0):
        return self.client.request("observe", window_s=window_s,
                                   capability_ids=sorted(set(capability_ids.values())))

    def apply(self, command):
        data = command.data if isinstance(command, Record) else command
        return self.client.request("apply", command=data)

    def truth(self):
        return self.client.request("truth")

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _leg(scenario, leg_id):
    return next(leg for leg in scenario["topology"]["legs"] if leg["leg_id"] == leg_id)


def _flow(scenario, service):
    return next(flow for flow in scenario["flows"] if flow["service"] == service)


def declared(scenario):
    """What a simulator built from this scenario must report holding, in its own terms."""
    data = scenario.data if isinstance(scenario, Record) else scenario
    lte, alternative = _leg(data, "lte"), _leg(data, "alternative")
    egress, radio = data["topology"]["egress"], lte["radio"]
    scada, ami = _flow(data, "scada"), _flow(data, "ami")
    return {
        "lte": {"dl_bandwidth_rb": radio["dl_bandwidth_rb"],
                "ul_bandwidth_rb": radio["ul_bandwidth_rb"],
                "dl_earfcn": radio["dl_earfcn"], "ul_earfcn": radio["ul_earfcn"],
                "enb_tx_dbm": radio["enb_tx_dbm"],
                "enb_noise_figure_db": radio["enb_noise_figure_db"],
                "rlc_um_max_tx_buffer_bytes": lte["queue_limit_bytes"],
                "rlc_mapping": "RlcUmAlways", "scheduler": "ns3::PfFfMacScheduler",
                "downlink_loss_models": ["ns3::FriisSpectrumPropagationLossModel",
                                         "ns3::MatrixPropagationLossModel"],
                "uplink_loss_models": ["ns3::FriisSpectrumPropagationLossModel",
                                       "ns3::MatrixPropagationLossModel"],
                "logical": "not_applicable"},
        "sites": {site: {"position_m": [float(x) for x in radio["site_positions_m"][site]],
                         "ue_tx_dbm": radio["ue_tx_dbm"],
                         "ue_noise_figure_db": radio["ue_noise_figure_db"],
                         "alternative": {"capacity_bps": alternative["capacity_bps"],
                                         "delay_s": alternative["delay_s"],
                                         "queue_limit": f"{alternative['queue_limit_bytes']}B"},
                         "initial_path": data["topology"]["initial_path"],
                         "initial_pacing": data["topology"]["initial_pacing"]}
                  for site in data["topology"]["sites"]},
        "egress": {"capacity_bps": egress["capacity_bps"], "delay_s": egress["delay_s"],
                   "queue_limit": f"{egress['queue_limit_bytes']}B", "queue_discipline": "none"},
        "flows": {"scada": {"pattern": "request_response",
                            "request_bytes": scada["payload_bytes"],
                            "response_bytes": scada["response_bytes"],
                            "processing_delay_s": scada["processing_delay_s"],
                            "period_s": scada["generation"]["period_s"],
                            "deadline_s": scada["deadline_s"]},
                  "ami": {"pattern": "periodic", "payload_bytes": ami["payload_bytes"],
                          "period_s": ami["generation"]["period_s"],
                          "deadline_s": ami["deadline_s"]}},
        "pacing_bps": {name: float(rate) for name, rate in PACING_BPS.items()},
        "disturbances_scheduled": len(data["disturbances"]),
        # Competitors are built for the largest load any disturbance declares.
        "competitors_built": max((d["competing_ues"] for d in data["disturbances"]
                                  if d["kind"] == "cell_load"), default=0),
    }


def _reported(resolved):
    """The same facts, as the simulator's configure response reports them."""
    lte = {key: resolved["lte"][key] for key in (
        "dl_bandwidth_rb", "ul_bandwidth_rb", "dl_earfcn", "ul_earfcn", "enb_tx_dbm",
        "enb_noise_figure_db", "rlc_um_max_tx_buffer_bytes", "rlc_mapping", "scheduler",
        "downlink_loss_models", "uplink_loss_models", "logical")}
    sites = {site["site"]: {"position_m": site["position_m"], "ue_tx_dbm": site["ue_tx_dbm"],
                            "ue_noise_figure_db": site["ue_noise_figure_db"],
                            "alternative": {key: site["alternative"][key]
                                            for key in ("capacity_bps", "delay_s", "queue_limit")},
                            "initial_path": site["initial_path"],
                            "initial_pacing": site["initial_pacing"]}
             for site in resolved["sites"]}
    return {"lte": lte, "sites": sites, "egress": resolved["egress"],
            "flows": resolved["flows"], "pacing_bps": resolved["pacing_bps"],
            "disturbances_scheduled": resolved["disturbances_scheduled"],
            "competitors_built": resolved["cell_load"]["competitors_built"]}


def verify_simulated(resolved, scenario):
    """Refuse a simulated world that does not report holding what its scenario declares.

    Compared field by field and section by section, so a refusal names what disagrees.
    The finite world's logical reading of the LTE leg is expected to be reported as not
    applicable: a simulator that used it would be running the finite world's assumption.
    """
    data = scenario.data if isinstance(scenario, Record) else scenario
    expected, actual = declared(data), _reported(resolved)
    for section in expected:
        require(actual[section] == expected[section],
                f"the simulator does not hold scenario {data['scenario_id']}: {section} is "
                f"{actual[section]!r}, the scenario declares {expected[section]!r}")
    return resolved
