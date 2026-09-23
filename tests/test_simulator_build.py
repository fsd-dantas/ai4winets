import copy
import re
import unittest
from pathlib import Path

from ecora import ns3build
from ecora.contracts import ContractError

ROOT = Path(__file__).resolve().parents[1]
DECLARED = ns3build.declaration()


def dump(groups=None):
    """A minimal registry dump covering the declared groups."""
    groups = DECLARED["manifest_groups"] if groups is None else groups
    return {"types": [{"name": f"ns3::{group}Thing", "group": group, "parent": "ns3::Object",
                       "attributes": [{"name": "Value", "value": "1", "type": "ns3::UintegerValue",
                                       "flags": "gsc", "support": "supported"}]}
                      for group in groups],
            "globals": [{"name": "RngSeed", "value": "1"}]}


def facts(**changes):
    base = {"release": DECLARED["release"], "archive_sha256": DECLARED["sha256"],
            "build_profile": DECLARED["build_profile"], "native_optimizations": "OFF"}
    return {**base, **changes}


class DeclarationTests(unittest.TestCase):
    """The pin is declared once and agrees with the parameter register."""

    def test_the_register_names_the_release_the_build_pins(self):
        register = (ROOT / "docs" / "ECoRA" / "experiments.md").read_text(encoding="utf-8")
        pinned = re.findall(r"ns3_release=([0-9.]+)", register)
        self.assertEqual(pinned, [DECLARED["release"]])
        scope = (ROOT / "docs" / "ECoRA" / "v1-scope.md").read_text(encoding="utf-8")
        self.assertIn(f"Select ns-3 release {DECLARED['release']}", scope)

    def test_the_archive_is_pinned_by_checksum_and_named_by_release(self):
        self.assertRegex(DECLARED["sha256"], r"^[0-9a-f]{64}$")
        self.assertIn(DECLARED["release"], DECLARED["archive"])
        self.assertTrue(DECLARED["url"].endswith("/" + DECLARED["archive"]))
        self.assertEqual(DECLARED["cmake_defines"]["NS3_NATIVE_OPTIMIZATIONS"], "OFF")

    def test_every_declared_program_has_a_source(self):
        source = ROOT / "software" / "simulator" / "src"
        for program in DECLARED["programs"]:
            with self.subTest(program=program):
                # One file, or a directory ns-3 builds into one executable.
                self.assertTrue((source / f"{program}.cc").is_file()
                                or any((source / program).glob("*.cc")))
        for dependency in DECLARED["dependencies"]:
            self.assertRegex(dependency["sha256"], r"^[0-9a-f]{64}$")
            self.assertIn(dependency["program"], DECLARED["programs"])


class AssemblyTests(unittest.TestCase):
    """A manifest is refused rather than assembled from a build it does not describe."""

    def test_a_faithful_build_assembles_and_verifies(self):
        manifest = ns3build.assemble(dump(), facts())
        ns3build.verify(manifest)
        self.assertEqual(manifest["registry"]["types"], len(DECLARED["manifest_groups"]))

    def test_it_refuses_a_build_that_differs_from_the_declaration(self):
        for change, expected in (({"release": "3.45"}, "pins"),
                                 ({"archive_sha256": "0" * 64}, "archive"),
                                 ({"build_profile": "debug"}, "profile"),
                                 ({"native_optimizations": "ON"}, "CPU")):
            with self.subTest(change=change), self.assertRaises(ContractError) as caught:
                ns3build.assemble(dump(), facts(**change))
            self.assertIn(expected, str(caught.exception))

    def test_it_refuses_a_simulator_built_from_other_sources(self):
        dump_sha = "d" * 64
        honest = facts(attribute_dump_sha256=dump_sha,
                       simulator_source_sha256=ns3build.simulator_source_sha256())
        honest["simulator_build_id"] = ns3build.build_id(
            DECLARED["sha256"], dump_sha, honest["simulator_source_sha256"])
        ns3build.assemble(dump(), honest, dump_sha256=dump_sha)
        for change, expected in (({"simulator_source_sha256": "e" * 64}, "sources"),
                                 ({"simulator_build_id": "f" * 64}, "identity"),
                                 ({"attribute_dump_sha256": "0" * 64}, "dump")):
            with self.subTest(change=change), self.assertRaises(ContractError) as caught:
                ns3build.assemble(dump(), {**honest, **change}, dump_sha256=dump_sha)
            self.assertIn(expected, str(caught.exception))

    def test_it_refuses_a_dump_missing_a_declared_group(self):
        with self.assertRaises(ContractError) as caught:
            ns3build.assemble(dump(DECLARED["manifest_groups"][1:]), facts())
        self.assertIn(DECLARED["manifest_groups"][0], str(caught.exception))

    def test_the_model_hash_ignores_the_host_and_the_build_hash_does_not(self):
        one = ns3build.assemble(dump(), facts(platform="host-a"))
        two = ns3build.assemble(dump(), facts(platform="host-b"))
        self.assertEqual(one["model_hash"], two["model_hash"])
        self.assertNotEqual(one["build_hash"], two["build_hash"])

    def test_any_changed_default_changes_the_model_hash(self):
        """Including one in a group the readable section leaves out."""
        changed = dump(DECLARED["manifest_groups"] + ["Wifi"])
        base = ns3build.assemble(changed, facts())
        edited = copy.deepcopy(changed)
        edited["types"][-1]["attributes"][0]["value"] = "2"
        self.assertNotIn("ns3::WifiThing", base["attributes"])
        self.assertNotEqual(ns3build.assemble(edited, facts())["model_hash"], base["model_hash"])

    def test_a_tampered_manifest_fails_verification(self):
        manifest = ns3build.assemble(dump(), facts())
        manifest["globals"]["RngSeed"] = "2"
        with self.assertRaises(ContractError):
            ns3build.verify(manifest)


@unittest.skipUnless(ns3build.MANIFEST.is_file(), "no committed ns-3 manifest")
class CommittedManifestTests(unittest.TestCase):
    """The manifest in the repository describes the current declaration and sources."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = ns3build.verify(ns3build.load())

    def test_it_describes_the_pinned_release_built_as_declared(self):
        build = self.manifest["build"]
        self.assertEqual(self.manifest["release"], DECLARED["release"])
        self.assertEqual(build["archive_sha256"], DECLARED["sha256"])
        self.assertEqual(build["cmake_build_type"].lower(), "release")
        self.assertEqual((build["native_optimizations"], build["asserts"], build["logs"]),
                         ("OFF", "ON", "OFF"))
        self.assertEqual(sorted(build["enabled_modules"]), sorted(DECLARED["modules"]))
        # Configure resolves dependencies; every declared module is among what it enabled.
        self.assertLessEqual(set(DECLARED["modules"]), set(build["resolved_modules"]))

    def test_it_exports_the_settings_v1_scope_requires(self):
        """RLC and HARQ settings inherited from the release, and the selected components."""
        attributes = self.manifest["attributes"]
        for type_name in ("ns3::LteHelper", "ns3::LteEnbRrc", "ns3::LteRlcUm", "ns3::LteRlcAm",
                          "ns3::LteEnbPhy", "ns3::LteUePhy", "ns3::PfFfMacScheduler",
                          "ns3::PointToPointEpcHelper", "ns3::PointToPointNetDevice",
                          "ns3::RateErrorModel", "ns3::FriisSpectrumPropagationLossModel"):
            with self.subTest(type_name=type_name):
                self.assertIn(type_name, attributes)
        self.assertIn("HarqEnabled", attributes["ns3::PfFfMacScheduler"])
        self.assertEqual(attributes["ns3::LteHelper"]["Scheduler"], "ns3::PfFfMacScheduler")
        self.assertIn("MaxTxBufferSize", attributes["ns3::LteRlcUm"])
        self.assertIn("RngSeed", self.manifest["globals"])
        # Selected with nothing to configure: listed, and visibly empty.
        self.assertEqual(attributes["ns3::FriisSpectrumPropagationLossModel"], {})
        for type_name in ("ns3::LteEnbNetDevice", "ns3::LteUeNetDevice", "ns3::UeManager"):
            with self.subTest(ungrouped=type_name):
                self.assertIn(type_name, attributes)

    def test_the_simulator_identity_follows_from_its_inputs(self):
        """The id compiled into the simulator is recomputable from the repository."""
        build = self.manifest["build"]
        self.assertEqual(build["simulator_source_sha256"], ns3build.simulator_source_sha256())
        self.assertEqual(self.manifest["simulator_build_id"],
                         ns3build.build_id(build["archive_sha256"],
                                           build["attribute_dump_sha256"],
                                           build["simulator_source_sha256"]))
        self.assertIn("ecora-sim/ecora-sim.cc", self.manifest["sources"])

    def test_no_exported_value_is_a_process_address(self):
        """An address differs per process, so a manifest holding one could never reproduce."""
        for type_name, values in self.manifest["attributes"].items():
            for name, value in values.items():
                self.assertNotRegex(value, r"0x[0-9a-f]{6,}", f"{type_name}::{name}")


if __name__ == "__main__":
    unittest.main()
