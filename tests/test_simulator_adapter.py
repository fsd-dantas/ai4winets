import copy
import json
import struct
import unittest

from ecora import ns3build
from ecora.contracts import ContractError
from ecora.scenario import SCENARIOS, build_world, load, verify_world
from ecora.simulator import (Ns3World, SimulatorClient, SimulatorCrashed, SimulatorRefusal,
                             default_command, declared, verify_simulated)

BUILD = "b" * 64


class Stub:
    """An in-memory simulator: answers each framed request with whatever `answer` returns."""

    def __init__(self, answer):
        self.answer = answer
        self.outbox = b""
        self.requests = []

    def write(self, data):
        length = struct.unpack(">I", data[:4])[0]
        request = json.loads(data[4:4 + length])
        self.requests.append(request)
        response = self.answer(request)
        if response is not None:
            body = json.dumps(response).encode()
            self.outbox += struct.pack(">I", len(body)) + body

    def flush(self):
        pass

    def read(self, size):
        chunk, self.outbox = self.outbox[:size], self.outbox[size:]
        return chunk


def honest(result=None):
    return lambda request: {"request_id": request["request_id"], "kind": request["kind"],
                            "build_id": BUILD, "status": "ok", "result": result or {}}


def client(answer):
    stub = Stub(answer)
    return SimulatorClient(stub, stub, BUILD), stub


class ProtocolTests(unittest.TestCase):
    """The adapter enforces the protocol's rules rather than trusting the other side."""

    def test_a_request_is_framed_canonically_and_answered(self):
        adapter, stub = client(honest({"time_s": 1.0}))
        self.assertEqual(adapter.request("advance", time_s=1.0), {"time_s": 1.0})
        self.assertEqual(stub.requests, [{"kind": "advance", "request_id": 1, "time_s": 1.0}])

    def test_a_response_from_another_build_is_refused(self):
        adapter, _ = client(lambda r: {**honest()(r), "build_id": "c" * 64})
        with self.assertRaises(ContractError) as caught:
            adapter.request("advance", time_s=1.0)
        self.assertIn("the manifest describes", str(caught.exception))

    def test_a_response_to_another_request_is_refused(self):
        for change in ({"request_id": 99}, {"kind": "cohorts"}):
            with self.subTest(change=change):
                adapter, _ = client(lambda r, change=change: {**honest()(r), **change})
                with self.assertRaises(ContractError) as caught:
                    adapter.request("advance", time_s=1.0)
                self.assertIn("different request", str(caught.exception))

    def test_a_refusal_is_raised_with_its_reason_and_not_replaced(self):
        adapter, _ = client(lambda r: {**honest()(r), "status": "refused",
                                       "reason": {"code": "clock_backwards", "detail": "no"}})
        with self.assertRaises(SimulatorRefusal) as caught:
            adapter.request("advance", time_s=0.0)
        self.assertEqual(caught.exception.code, "clock_backwards")

    def test_silence_is_a_crash_and_not_an_answer(self):
        adapter, _ = client(lambda r: None)
        with self.assertRaises(SimulatorCrashed):
            adapter.request("advance", time_s=1.0)

    def test_an_adapter_needs_a_build_to_hold_the_simulator_to(self):
        stub = Stub(honest())
        with self.assertRaises(ContractError):
            SimulatorClient(stub, stub, "")


def reported(scenario):
    """What an honest simulator would report for this scenario, in its own shape."""
    expected = declared(scenario)
    return {"lte": expected["lte"],
            "sites": [{"site": name, **site} for name, site in expected["sites"].items()],
            "egress": expected["egress"], "flows": expected["flows"],
            "pacing_bps": expected["pacing_bps"],
            "disturbances_scheduled": expected["disturbances_scheduled"],
            "cell_load": {"competitors_built": expected["competitors_built"]}}


class VerificationTests(unittest.TestCase):
    """Acceptance 1 as a check: the simulated world is refused where it differs."""

    def setUp(self):
        self.scenario = load(SCENARIOS / "s1-degraded-primary.json")

    def test_a_faithful_report_passes(self):
        verify_simulated(reported(self.scenario), self.scenario)

    def test_a_disagreement_is_refused_and_named(self):
        cases = (
            (lambda r: r["lte"].update(dl_earfcn=200), "lte"),
            (lambda r: r["lte"].update(logical="used"), "lte"),
            (lambda r: r["lte"].update(rlc_mapping="RlcSmAlways"), "lte"),
            (lambda r: r["sites"][0]["alternative"].update(capacity_bps=1), "sites"),
            (lambda r: r["egress"].update(queue_discipline="ns3::FqCoDelQueueDisc"), "egress"),
            (lambda r: r["flows"]["scada"].update(pattern="periodic"), "flows"),
            (lambda r: r["pacing_bps"].update(normal=1.0), "pacing_bps"),
            (lambda r: r.update(disturbances_scheduled=0), "disturbances_scheduled"),
            (lambda r: r["cell_load"].update(competitors_built=0), "competitors_built"))
        for edit, section in cases:
            with self.subTest(section=section):
                report = copy.deepcopy(reported(self.scenario))
                edit(report)
                with self.assertRaises(ContractError) as caught:
                    verify_simulated(report, self.scenario)
                self.assertIn(f": {section} is", str(caught.exception))


def _available():
    if not ns3build.MANIFEST.is_file() or default_command() is None:
        return False
    try:
        adapter = SimulatorClient.spawn()
    except (ContractError, OSError):
        return False
    try:
        adapter.request("cohorts", cohort_specs=[])
    except SimulatorRefusal:
        return True  # it answered, with the refusal an unconfigured world gives
    except ContractError:
        return False
    finally:
        adapter.close()
    return True


AVAILABLE = _available()
SPECS = [{"cohort_id": f"cohort:{service}", "service": service, "deadline_s": 0,
          "generation_window": {"start_s": 0.0, "end_s": 3.0}} for service in ("scada", "ami")]


@unittest.skipUnless(AVAILABLE, "no ns-3 simulator build is available on this host")
class SimulatorTests(unittest.TestCase):
    """Against the real build: acceptance 1, the ledger, and the refusals."""

    def test_every_scenario_builds_both_worlds_and_each_holds_it(self):
        for path in sorted(SCENARIOS.glob("s*.json")):
            scenario = load(path)
            with self.subTest(scenario=path.stem), Ns3World.start(scenario) as world:
                verify_world(build_world(scenario), scenario)
                verify_simulated(world.resolved, scenario)

    def test_the_ledger_accounts_for_every_obligation(self):
        with Ns3World.start(load(SCENARIOS / "s2-silent-primary.json")) as world:
            world.advance_to(4.0)
            for cohort in world.cohorts(SPECS):
                with self.subTest(service=cohort["service"]):
                    self.assertGreater(cohort["generated"], 0)
                    self.assertEqual(cohort["generated"],
                                     cohort["delivered_on_time"] + cohort["delivered_late"]
                                     + cohort["lost"] + cohort["pending"])

    def test_the_same_seed_gives_the_same_world(self):
        def run():
            with Ns3World.start(load(SCENARIOS / "s1-degraded-primary.json")) as world:
                world.advance_to(3.0)
                return world.cohorts(SPECS)
        self.assertEqual(run(), run())

    def test_the_clock_is_monotonic_and_unbuilt_calls_are_refused(self):
        with Ns3World.start(load(SCENARIOS / "s0-nominal.json")) as world:
            world.advance_to(1.0)
            with self.assertRaises(SimulatorRefusal) as caught:
                world.client.request("advance", time_s=0.5)
            self.assertEqual(caught.exception.code, "clock_backwards")
            # Truth and fork are not served yet; both are refused, never approximated.
            for call in (world.truth, lambda: world.client.request("fork", epoch=1)):
                with self.assertRaises(SimulatorRefusal) as caught:
                    call()
                self.assertEqual(caught.exception.code, "unsupported_request")
            # A refusal leaves the world where it was, and the next request is answered.
            self.assertEqual(world.advance_to(2.0).now, 2.0)

    def test_a_world_is_configured_once(self):
        with Ns3World.start(load(SCENARIOS / "s0-nominal.json")) as world:
            with self.assertRaises(SimulatorRefusal) as caught:
                world.client.request("configure", scenario=world.scenario)
            self.assertEqual(caught.exception.code, "already_configured")


if __name__ == "__main__":
    unittest.main()
