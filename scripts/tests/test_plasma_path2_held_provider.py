#!/usr/bin/env python3
"""Host-only Provider Gate 1: fake FPGA TargetPort, no real device access."""
from __future__ import annotations

from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_path2_held_provider as provider
import plasma_path2_bin_provenance as provenance
import plasma_path2_persistent_lease as lease

SRC = "a" * 40
BIT = "b" * 64
BIN = "c" * 64
BASE = "d" * 64
HWH = "e" * 64
SERVICE = "f" * 64
UIO = "1" * 64
INTENT = "2" * 64
LOAD = "3" * 64
TEST = "4" * 64
RESTORE = "5" * 64


def lease_intent(**changes):
    result = {
        "lease_id": "lease-owned", "target_id": "z2-bench",
        "profile_id": "f1b-site1-v1", "source_sha": SRC,
        "artifact_sha256": BIN, "recovery_sha256": BASE,
        "boot_id": "boot-validated", "owner_id": "trusted-owner",
        "restore_intent_sha256": INTENT, "services_sha256": SERVICE,
        "uio_sha256": UIO, "lease_seconds": 120
    }
    result.update(changes)
    return result


def provenance_data(**changes):
    result = {"source_sha": SRC, "bit_sha256": BIT, "hwh_sha256": HWH,
              "bin_sha256": BIN, "bootgen_evidence_sha256": "6" * 64,
              "build_qualification_sha256": "8" * 64,
              "scope": "BYTE_EQUIVALENCE_ONLY", "physical_load": "NOT_RUN"}
    result.update(changes)
    return result


class SimulatedTarget:
    """Test double, intentionally not a real privileged Configuration Owner."""

    def __init__(self):
        self.clock = 100000
        self.image = BASE
        self.actions = []
        self.safe = True
        self.read_fail = False
        self.load_fail = False
        self.restore_fail = False
        self.boot = "boot-validated"

    def exclusive(self):
        return nullcontext()

    def now(self):
        self.clock += 1
        return self.clock

    def qualification(self, stage):
        self.actions.append("qualify:" + stage)
        return {
            "root_route": self.safe, "target_global_lock": self.safe,
            "target_owner_persistent": self.safe,
            "independent_image_provenance": self.safe,
            "bootgen_execution_verified": self.safe,
            "protected_original_recovery": self.safe,
            "complete_proc_visibility": self.safe,
            "kernel_driver_excluded": self.safe,
            "hardware_owner_excluded": self.safe,
            "axi_idle_isolated": self.safe,
            "worker_reaped": self.safe,
            "restore_route_verified": self.safe,
            "trusted_target_clock": self.safe,
            "target_id": "z2-bench", "boot_id": self.boot,
            "owner_id": "trusted-owner", "restore_intent_sha256": INTENT,
            "bit_sha256": BIT, "bin_sha256": BIN,
            "bootgen_evidence_sha256": "6" * 64,
        }

    def observation(self, at):
        self.actions.append("observe")
        return {"observed_at": at, "target_id": "z2-bench",
                "boot_id": self.boot, "image_sha256": self.image,
                "manager_state": "operating",
                "owner_evidence_sha256": "7" * 64,
                "axi_admission": "SEPARATELY_AUTHORIZED"}

    def image_sha256(self, which):
        return {"recovery": BASE, "candidate": BIN}[which]

    def load_candidate_once(self, bin_sha256):
        self.actions.append("load")
        if self.load_fail:
            raise RuntimeError("test injected load failure")
        assert self.image == BASE and bin_sha256 == BIN
        self.image = BIN
        return {"load_evidence_sha256": LOAD,
                "restore_intent_sha256": INTENT}

    def read_f1b_identity_child(self):
        self.actions.append("test")
        if self.read_fail:
            raise RuntimeError("test injected native SIGBUS")
        return {"observed": lease.TEST_WORDS.copy(), "read32": 3,
                "write32": 0, "native_readonly": True,
                "worker_reaped": True, "timed_out": False,
                "returncode": 0, "evidence_sha256": TEST}

    def restore_original_once(self, recovery_sha256):
        self.actions.append("restore")
        if self.restore_fail:
            raise RuntimeError("test injected restore failure")
        assert recovery_sha256 == BASE and self.image == BIN
        self.image = BASE
        return {"restore_evidence_sha256": RESTORE,
                "services_sha256": SERVICE, "uio_sha256": UIO}


def setup():
    tmp = tempfile.TemporaryDirectory()
    ledger = lease.LeaseLedger(Path(tmp.name) / "z2-bench.json")
    return tmp, ledger, SimulatedTarget()


def download(store, port, intent=None, proof=None):
    return provider.download_held(
        store=store, port=port, intent=intent or lease_intent(),
        provenance=proof or provenance_data())


def test_request():
    return {"lease_id": "lease-owned", "source_sha": SRC,
            "profile_id": "f1b-site1-v1", "target_id": "z2-bench",
            "artifact_sha256": BIN, "load_evidence_sha256": LOAD}


class LifecycleTests(unittest.TestCase):
    def test_distinct_bin_and_bit_and_three_independent_triggers(self):
        tmp, store, port = setup()
        with tmp:
            loaded = download(store, port)
            self.assertEqual(loaded["artifact_sha256"], BIT)
            self.assertEqual(store.snapshot()["artifact_sha256"], BIN)
            self.assertEqual(store.snapshot()["status"], "LOADED_AND_HELD")
            self.assertEqual(port.image, BIN)
            self.assertEqual(port.actions.count("load"), 1)
            read = provider.testing_held(store=store, port=port,
                                         request=test_request(), bit_sha256=BIT)
            self.assertEqual(read["result"], "IDENTITY_PASS")
            self.assertEqual(read["read32_count"], 3)
            self.assertEqual(read["write32_count"], 0)
            self.assertEqual(read["artifact_sha256"], BIT)
            self.assertEqual(port.image, BIN)
            self.assertEqual(port.actions.count("test"), 1)
            result = provider.restore_guarded(store=store, port=port)
            self.assertEqual(result["result"], "RESTORED_VERIFIED")
            self.assertEqual(port.image, BASE)
            self.assertEqual(store.snapshot()["status"], "RESTORED_VERIFIED")
            self.assertEqual(port.actions.count("restore"), 1)

    def test_provenance_mismatch_fails_before_load_or_intent(self):
        for override in ({"bin_sha256": BIT},
                         {"bit_sha256": BIN},
                         {"scope": "HARDWARE_VERIFIED"},
                         {"physical_load": "PASS"},
                         {"source_sha": "8" * 40}):
            with self.subTest(override=override):
                tmp, store, port = setup()
                with tmp, self.assertRaises(provider.ProviderDenied):
                    download(store, port, proof=provenance_data(**override))
                self.assertEqual(port.actions, [])
                self.assertFalse(store.path.exists())

    def test_wrong_target_denied_before_candidate_load(self):
        tmp, store, port = setup()
        with tmp:
            original = port.qualification
            port.qualification = lambda stage: original(stage) | {"target_id": "other-board"}
            with self.assertRaisesRegex(provider.ProviderDenied, "TARGET_OWNER_OR_RECOVERY_CHANGED"):
                download(store, port)
            self.assertNotIn("load", port.actions)

    def test_unproven_axi_does_not_write_image(self):
        tmp, store, port = setup()
        with tmp:
            port.safe = False
            with self.assertRaisesRegex(provider.ProviderDenied,
                                        "TARGET_HARDWARE_ISOLATION_UNPROVEN"):
                download(store, port)
            self.assertFalse(store.path.exists())
            self.assertEqual(port.actions.count("load"), 0)

    def test_preexisting_lease_never_overwritten_or_replayed(self):
        tmp, store, port = setup()
        with tmp:
            download(store, port)
            with self.assertRaisesRegex(provider.ProviderDenied,
                                        "PRIOR_HARDWARE_LEASE_REQUIRES_REVIEW"):
                download(store, port)
            self.assertEqual(port.actions.count("load"), 1)

    def test_load_failure_is_persistent_unknown_without_retry(self):
        tmp, store, port = setup()
        with tmp:
            port.load_fail = True
            with self.assertRaisesRegex(RuntimeError, "load failure"):
                download(store, port)
            self.assertEqual(store.snapshot()["status"],
                             "UNKNOWN_MANUAL_RECOVERY")
            self.assertEqual(store.snapshot()["load_attempts"], 1)
            with self.assertRaises(provider.ProviderDenied):
                download(store, port)
            self.assertEqual(port.actions.count("load"), 1)
            self.assertEqual(port.actions.count("restore"), 0)

    def test_new_boot_and_expired_lease_refuse_independent_testing(self):
        tmp, store, port = setup()
        with tmp:
            download(store, port)
            port.boot = "new-boot"
            with self.assertRaisesRegex(provider.ProviderDenied,
                                        "TARGET_OWNER_OR_RECOVERY_CHANGED"):
                provider.testing_held(store=store, port=port,
                    request=test_request(), bit_sha256=BIT)
            self.assertNotIn("test", port.actions)
            port.boot = "boot-validated"
            port.clock += 150
            with self.assertRaises(lease.LeaseDenied):
                provider.testing_held(store=store, port=port,
                    request=test_request(), bit_sha256=BIT)
            self.assertNotIn("test", port.actions)

    def test_native_sigbus_is_unknown_and_blocks_restore(self):
        tmp, store, port = setup()
        with tmp:
            download(store, port)
            port.read_fail = True
            with self.assertRaisesRegex(RuntimeError, "SIGBUS"):
                provider.testing_held(store=store, port=port,
                    request=test_request(), bit_sha256=BIT)
            self.assertEqual(store.snapshot()["status"],
                             "UNKNOWN_MANUAL_RECOVERY")
            with self.assertRaises(lease.LeaseDenied):
                provider.restore_guarded(store=store, port=port)
            self.assertEqual(port.actions.count("restore"), 0)

    def test_restore_failure_cannot_retry(self):
        tmp, store, port = setup()
        with tmp:
            download(store, port)
            port.restore_fail = True
            with self.assertRaisesRegex(RuntimeError, "restore failure"):
                provider.restore_guarded(store=store, port=port)
            self.assertEqual(store.snapshot()["status"],
                             "UNKNOWN_MANUAL_RECOVERY")
            with self.assertRaises(lease.LeaseDenied):
                provider.restore_guarded(store=store, port=port)
            self.assertEqual(port.actions.count("restore"), 1)

    def test_independent_testing_needs_original_bit_identity(self):
        tmp, store, port = setup()
        with tmp:
            download(store, port)
            with self.assertRaisesRegex(
                    provider.ProviderDenied, "TEST_BIT_BIN_IDENTITY_DENIED"):
                provider.testing_held(store=store, port=port,
                    request=test_request(), bit_sha256="9" * 64)
            self.assertEqual(port.actions.count("test"), 0)

    def test_test_provenance_changed_denied_without_child(self):
        tmp, store, port = setup()
        with tmp:
            download(store, port)
            bad = dict(test_request(), source_sha="9" * 40)
            with self.assertRaises(lease.LeaseDenied):
                provider.testing_held(store=store, port=port,
                                      request=bad, bit_sha256=BIT)
            self.assertNotIn("test", port.actions)

    def test_held_provider_is_not_the_direct_root_dispatch_backend(self):
        code = (ROOT / "scripts/plasma_path2_runtime_integration.py").read_text()
        dispatch = (ROOT / "scripts/plasma_development_dispatch.py").read_text()
        self.assertIn("def direct_root_operation(", code)
        self.assertIn("return integration.direct_root_operation", dispatch)
        prov = (ROOT / "scripts/plasma_path2_held_provider.py").read_text()
        self.assertNotIn("if __name__ == \"__main__\"", prov)
        self.assertNotIn("subprocess", prov)
        self.assertNotIn("paramiko", prov)


class ExistingF1BAdapterIntegrationTests(unittest.TestCase):
    def test_download_rejects_forged_build_qualification_before_hardware(self):
        tmp, store, port = setup()
        with tmp:
            callbacks = provider.bind_injected_stage_callbacks(
                store=store, port=port,
                intent=lease_intent(), provenance=provenance_data())
            tampered = {"stage": "build", "status": "PASS",
                        "artifact_sha256": BIT, "evidence_sha256": "0" * 64}
            with self.assertRaisesRegex(
                    provider.ProviderDenied, "UNTRUSTED_BUILD_TO_DOWNLOAD"):
                callbacks["held_download"]({
                    "stage": "download", "source_sha": SRC,
                    "profile_id": "f1b-site1-v1", "target_id": "z2-bench",
                    "build_receipt": tampered})
            self.assertEqual(port.actions, [])
            self.assertFalse(store.path.exists())

    def test_exact_adapter_abi_with_two_separate_triggers_and_restore(self):
        import plasma_path2_f1b_adapters as f1b_adapter
        import plasma_path2_stage_orchestrator as stages
        tmp, store, port = setup()
        with tmp:
            callbacks = provider.bind_injected_stage_callbacks(
                store=store, port=port,
                intent=lease_intent(), provenance=provenance_data())
            bound = f1b_adapter.bind_f1b_adapters(**callbacks)
            build_receipt = {
                "stage": "build", "status": "PASS",
                "source_sha": SRC, "profile_id": "f1b-site1-v1",
                "artifact_sha256": BIT, "evidence_sha256": "8" * 64}
            first = stages.run({
                "stage": "download", "source_sha": SRC,
                "profile_id": "f1b-site1-v1", "target_id": "z2-bench",
                "artifact_sha256": BIT, "build_receipt": build_receipt},
                adapters=bound)
            self.assertEqual(first["completed"], ["download"])
            self.assertEqual(first["status"], "RECEIPTS_VALIDATED")
            self.assertEqual(port.image, BIN)
            independent = stages.run({
                "stage": "test", "source_sha": SRC,
                "profile_id": "f1b-site1-v1", "target_id": "z2-bench",
                "artifact_sha256": BIT,
                "load_receipt": first["receipts"]["download"]},
                adapters=bound)
            self.assertEqual(independent["completed"], ["test"])
            self.assertEqual(independent["status"], "RECEIPTS_VALIDATED")
            self.assertEqual(port.image, BIN)
            self.assertEqual(port.actions.count("load"), 1)
            self.assertEqual(port.actions.count("test"), 1)
            result = provider.restore_guarded(store=store, port=port)
            self.assertEqual(result["result"], "RESTORED_VERIFIED")


class BitBinProvenanceTests(unittest.TestCase):
    def test_actual_bytes_and_distinct_digests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bit, hwh, bin_file = (root / "a.bit", root / "a.hwh", root / "a.bin")
            payload = bytes.fromhex("11223344aabbccdd")
            bit.write_bytes(b"fake-Xilinx-BIT" + payload)
            hwh.write_bytes(b"fixed HWH bytes")
            bin_data = bytes.fromhex("44332211ddccbbaa00000020")
            bin_file.write_bytes(bin_data)
            bit_sha = hashlib.sha256(bit.read_bytes()).hexdigest()
            hwh_sha = hashlib.sha256(hwh.read_bytes()).hexdigest()
            bin_sha = hashlib.sha256(bin_data).hexdigest()
            build = {"stage": "build", "status": "PASS", "source_sha": SRC,
                     "profile_id": "f1b-site1-v1",
                     "artifact_sha256": bit_sha, "evidence_sha256": "8" * 64}
            bootgen = {"schema": "plasma.path2.bootgen.provenance.v1",
                       "source_sha": SRC, "bit_sha256": bit_sha,
                       "hwh_sha256": hwh_sha, "bin_sha256": bin_sha,
                       "tool_version": "2026.1",
                       "execution_evidence_sha256": "9" * 64,
                       "authentication_status": "EXTERNALLY_VERIFIED"}
            with patch.object(provenance.staging, "bit_payload", return_value=payload):
                actual = provenance.verify_f1b_conversion(
                    bit=bit, hwh=hwh, firmware=bin_file,
                    build_receipt=build, hwh_sha256=hwh_sha,
                    bin_sha256=bin_sha, bootgen_receipt=bootgen)
                self.assertEqual(actual["bit_sha256"], bit_sha)
                self.assertEqual(actual["bin_sha256"], bin_sha)
                self.assertNotEqual(actual["bit_sha256"], actual["bin_sha256"])
                self.assertEqual(actual["scope"], "BYTE_EQUIVALENCE_ONLY")
                for bad in (
                    dict(bootgen, authentication_status="SELF_ATTESTED"),
                    dict(bootgen, source_sha="b" * 40),
                    dict(bootgen, bin_sha256=bit_sha),
                ):
                    with self.assertRaises(provenance.ProvenanceDenied):
                        provenance.verify_f1b_conversion(
                            bit=bit, hwh=hwh, firmware=bin_file,
                            build_receipt=build, hwh_sha256=hwh_sha,
                            bin_sha256=bin_sha, bootgen_receipt=bad)
                original_bit = bit.read_bytes()
                bit.write_bytes(original_bit + b"tampered")
                with self.assertRaises(provenance.ProvenanceDenied):
                    provenance.verify_f1b_conversion(
                        bit=bit, hwh=hwh, firmware=bin_file,
                        build_receipt=build, hwh_sha256=hwh_sha,
                        bin_sha256=bin_sha, bootgen_receipt=bootgen)
                bit.write_bytes(original_bit)
                bin_file.write_bytes(b"tampered")
                with self.assertRaises(provenance.ProvenanceDenied):
                    provenance.verify_f1b_conversion(
                        bit=bit, hwh=hwh, firmware=bin_file,
                        build_receipt=build, hwh_sha256=hwh_sha,
                        bin_sha256=bin_sha, bootgen_receipt=bootgen)


if __name__ == "__main__":
    unittest.main()
