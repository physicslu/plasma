#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import stm32f103c_vendor_neutral_admission as adapter


class STM32F103CVendorNeutralAdmissionTests(unittest.TestCase):
    def _package(self, target: str = "STM32F103C8T6") -> dict:
        package = adapter.build_package(target)
        self.assertEqual(adapter.validate_admission_package(package)["status"], "VALID")
        return package

    @staticmethod
    def _payload(package: dict) -> dict:
        envelope = package["artifacts"][package["root_envelope_id"]]
        return package["artifacts"][envelope["vendor_payload"]["artifact_id"]]

    @staticmethod
    def _rows(package: dict) -> dict[str, dict]:
        artifact = package["artifacts"][package["operation_admission_id"]]
        return {row["request_operation"]: row for row in artifact["operations"]}

    @staticmethod
    def _reseal_payload_chain(package: dict) -> None:
        artifacts = package["artifacts"]
        envelope = artifacts[package["root_envelope_id"]]
        payload = artifacts[envelope["vendor_payload"]["artifact_id"]]
        adapter.seal(payload)
        envelope["vendor_payload"] = adapter.ref(payload)
        adapter.seal(envelope)
        operations = artifacts[package["operation_admission_id"]]
        for row in operations["operations"]:
            row["canonical_admission_digest"] = envelope["artifact_digest"]
            for requirement in row["canonical_requirements"]:
                requirement["artifact"] = adapter.ref(payload)
        adapter.seal(operations)

    @staticmethod
    def _reseal_backend_chain(package: dict) -> None:
        artifacts = package["artifacts"]
        rows = STM32F103CVendorNeutralAdmissionTests._rows(package)
        backend = artifacts[rows["READ"]["backend_id"]]
        backend["lock_digest"] = adapter.canonical_digest(
            backend, omit=("artifact_digest", "lock_digest")
        )
        adapter.seal(backend)
        operations = artifacts[package["operation_admission_id"]]
        for row in operations["operations"]:
            row["backend_lock_digest"] = backend["lock_digest"]
        adapter.seal(operations)

    @staticmethod
    def _reseal_operation_contract(package: dict, operation: str) -> None:
        artifacts = package["artifacts"]
        rows = STM32F103CVendorNeutralAdmissionTests._rows(package)
        row = rows[operation]
        contract = artifacts[row["operation_contract_id"]]
        adapter.seal(contract)
        row["operation_contract_digest"] = contract["artifact_digest"]
        adapter.seal(artifacts[package["operation_admission_id"]])

    def _assert_semantic_fail(self, package: dict, target: str) -> None:
        self.assertEqual(adapter.validate_admission_package(package)["status"], "VALID")
        with self.assertRaises(adapter.MigrationError):
            adapter.validate_projection(package, target)

    def test_frozen_inputs_validate(self) -> None:
        validated = adapter.validate_frozen_inputs()
        self.assertEqual(set(validated["geometries"]), set(adapter.CONTRACT["targets"]))

    def test_both_exact_targets_are_generic_valid(self) -> None:
        for target in sorted(adapter.CONTRACT["targets"]):
            with self.subTest(target=target):
                package = adapter.build_package(target)
                result = adapter.validate_projection(package, target)
                self.assertEqual(result["status"], "VALID")
                self.assertEqual(result["candidate_count"], 9)
                self.assertEqual(result["operation_count"], 10)
                self.assertEqual(result["admitted_operation_count"], 4)

    def test_sidecar_is_deterministic_and_non_production(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"
            manifest_a = adapter.build_sidecar(first)
            manifest_b = adapter.build_sidecar(second)
            self.assertEqual(manifest_a, manifest_b)
            qualification = json.loads((first / "qualification.json").read_text(encoding="utf-8"))
            self.assertFalse(qualification["hardware_runtime_ready"])
            self.assertFalse(qualification["model_invocation"])
            self.assertFalse(qualification["icpn_rediscovery"])
            self.assertFalse(qualification["production_admission"])

    def test_c8_flash_size_mutation_fails_closed_after_reseal(self) -> None:
        package = self._package()
        self._payload(package)["memory"]["main_flash_size_bytes"] = 131072
        self._reseal_payload_chain(package)
        self._assert_semantic_fail(package, "STM32F103C8T6")

    def test_cb_flash_size_mutation_fails_closed_after_reseal(self) -> None:
        package = self._package("STM32F103CBT6")
        self._payload(package)["memory"]["main_flash_size_bytes"] = 65536
        self._reseal_payload_chain(package)
        self._assert_semantic_fail(package, "STM32F103CBT6")

    def test_page_size_mutation_fails_closed_after_reseal(self) -> None:
        package = self._package()
        self._payload(package)["memory"]["page_size_bytes"] = 2048
        self._reseal_payload_chain(package)
        self._assert_semantic_fail(package, "STM32F103C8T6")

    def test_program_unit_mutation_fails_closed_after_reseal(self) -> None:
        package = self._package()
        payload = self._payload(package)
        payload["memory"]["program_granularity_bytes"] = 4
        payload["programming"]["program_granularity_bytes"] = 4
        self._reseal_payload_chain(package)
        self._assert_semantic_fail(package, "STM32F103C8T6")

    def test_unlock_key_mutation_fails_closed_after_reseal(self) -> None:
        package = self._package()
        payload = self._payload(package)
        payload["programming"]["unlock_keys"] = [
            "0x00000000",
            payload["programming"]["unlock_keys"][1],
        ]
        self._reseal_payload_chain(package)
        self._assert_semantic_fail(package, "STM32F103C8T6")

    def test_target_applicability_mutation_fails_closed_after_reseal(self) -> None:
        package = self._package()
        self._payload(package)["target"]["base_device"] = "STM32F103CB"
        self._reseal_payload_chain(package)
        self._assert_semantic_fail(package, "STM32F103C8T6")

    def test_erase_scope_mutation_fails_closed_after_reseal(self) -> None:
        package = self._package()
        rows = self._rows(package)
        contract = package["artifacts"][rows["ERASE"]["operation_contract_id"]]
        contract["scope"] = "single_page"
        self._reseal_operation_contract(package, "ERASE")
        self._assert_semantic_fail(package, "STM32F103C8T6")

    def test_backend_revision_mutation_fails_closed_after_reseal(self) -> None:
        package = self._package()
        rows = self._rows(package)
        backend = package["artifacts"][rows["READ"]["backend_id"]]
        backend["implementation"]["revision"] = "0" * 40
        self._reseal_backend_chain(package)
        self._assert_semantic_fail(package, "STM32F103C8T6")

    def test_compiler_binding_mutation_fails_closed_after_reseal(self) -> None:
        package = self._package()
        rows = self._rows(package)
        backend_id = rows["READ"]["backend_id"]
        fake = "plasma_interfaces.fake.Compiler"
        package["compiler_bindings"][backend_id] = [fake]
        operations = package["artifacts"][package["operation_admission_id"]]
        for row in operations["operations"]:
            row["compiler_id"] = fake
        adapter.seal(operations)
        self._assert_semantic_fail(package, "STM32F103C8T6")

    def test_destructive_operation_promotion_fails_closed_after_reseal(self) -> None:
        package = self._package()
        rows = self._rows(package)
        row = rows["RDP_DISABLE"]
        payload = self._payload(package)
        row["state"] = "ADMITTED"
        row["unresolved_requirements"] = []
        row["canonical_requirements"] = [
            {"artifact": adapter.ref(payload), "pointer": "/safety/destructive_security_operations_admitted"}
        ]
        contract = package["artifacts"][row["operation_contract_id"]]
        contract["state"] = "ADMITTED"
        adapter.seal(contract)
        row["operation_contract_digest"] = contract["artifact_digest"]
        adapter.seal(package["artifacts"][package["operation_admission_id"]])
        self._assert_semantic_fail(package, "STM32F103C8T6")

    def test_hardware_runtime_ready_true_fails_closed_after_reseal(self) -> None:
        package = self._package()
        operations = package["artifacts"][package["operation_admission_id"]]
        operations["operations"][0]["hardware_runtime_ready"] = True
        adapter.seal(operations)
        self._assert_semantic_fail(package, "STM32F103C8T6")


if __name__ == "__main__":
    unittest.main()
