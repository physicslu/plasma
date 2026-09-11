from __future__ import annotations

from dataclasses import replace
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import sys
import unittest

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_interfaces.compiler_registry import (
    DEFAULT_ADMISSION_PROJECTION_RESOURCE,
    CompilerBinding,
    CompilerRegistry,
    OperationAdmission,
    load_operation_admission_projection,
    parse_operation_admission_projection,
)
from plasma_interfaces.kl25_openocd_plan import KL25OpenOCDPlanCompiler
from plasma_interfaces.openocd_plan import OpenOCDPlanCompiler


STM32_COMPILER = "plasma_interfaces.openocd_plan.OpenOCDPlanCompiler"
KL25_COMPILER = "plasma_interfaces.kl25_openocd_plan.KL25OpenOCDPlanCompiler"
STM32_BACKEND = "stm32f103c-openocd-backend-v1"
KL25_BACKEND = "nxp-kl25-openocd-backend-v1"
STM32_LOCK = "041644e5e7203c0d1b679d0799d2136b1ce89c398cb5686395753e73998f4411"
KL25_LOCK = "7628554b4b34a3587688824e95f861bcd95c792699f023e2ae5ad7880196e1c5"


def admission(
    *,
    target: str = "MKL25Z128VLK4",
    state: str = "ADMITTED",
    compiler_id: str = KL25_COMPILER,
    backend_id: str = KL25_BACKEND,
    backend_lock_digest: str = KL25_LOCK,
) -> OperationAdmission:
    return OperationAdmission(
        target_icpn=target,
        request_operation="ERASE",
        state=state,
        operation_admission_id="nxp-kl25-operation-admission-v1",
        operation_admission_digest="47d5738db47816c627c0f2b51983f5f9ecb8c150f9e377c341439d0b4cfcb8c9",
        operation_contract_id="nxp-kl25-operation-contract-erase-sector-v1",
        operation_contract_digest="1c1e86971fe80b49ae34452611f7c5952b2a2efe980ecfb2d6532b7b008766ce",
        canonical_admission_digest="ea3189453da740577580d5f85a3d236b46112f27546fed956edfef762bdddefa",
        backend_id=backend_id,
        backend_lock_digest=backend_lock_digest,
        compiler_id=compiler_id,
        hardware_runtime_ready=False,
    )


def reseal_projection(value: dict) -> None:
    unsigned = {key: item for key, item in value.items() if key != "artifact_digest"}
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    value["artifact_digest"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CompilerRegistryTests(unittest.TestCase):
    def bindings(self) -> tuple[CompilerBinding, ...]:
        return (
            CompilerBinding(STM32_COMPILER, STM32_BACKEND, STM32_LOCK, OpenOCDPlanCompiler()),
            CompilerBinding(KL25_COMPILER, KL25_BACKEND, KL25_LOCK, KL25OpenOCDPlanCompiler()),
        )

    def test_admitted_binding_selects_vendor_compiler(self) -> None:
        registry = CompilerRegistry(self.bindings(), (admission(),))
        selected = registry.select("MKL25Z128VLK4", Operation.ERASE)
        self.assertIsInstance(selected.compiler, KL25OpenOCDPlanCompiler)
        self.assertEqual(selected.admission.operation_contract_id, "nxp-kl25-operation-contract-erase-sector-v1")

    def test_compiler_existence_does_not_admit_an_operation(self) -> None:
        registry = CompilerRegistry(self.bindings())
        with self.assertRaises(PlasmaError) as caught:
            registry.select("MKL25Z128VLK4", Operation.ERASE)
        self.assertEqual(caught.exception.code, ErrorCode.OPERATION_UNSUPPORTED)

    def test_blocked_operation_fails_closed(self) -> None:
        registry = CompilerRegistry(self.bindings(), (replace(admission(), state="BLOCKED"),))
        with self.assertRaises(PlasmaError) as caught:
            registry.select("MKL25Z128VLK4", Operation.ERASE)
        self.assertEqual(caught.exception.code, ErrorCode.OPERATION_UNSUPPORTED)

    def test_compiler_mismatch_fails_closed(self) -> None:
        registry = CompilerRegistry(self.bindings(), (replace(admission(), compiler_id=STM32_COMPILER),))
        with self.assertRaisesRegex(PlasmaError, "registered backend lock"):
            registry.select("MKL25Z128VLK4", Operation.ERASE)

    def test_backend_id_mismatch_fails_closed(self) -> None:
        registry = CompilerRegistry(self.bindings(), (replace(admission(), backend_id=STM32_BACKEND),))
        with self.assertRaisesRegex(PlasmaError, "registered backend lock"):
            registry.select("MKL25Z128VLK4", Operation.ERASE)

    def test_backend_lock_mismatch_fails_closed(self) -> None:
        registry = CompilerRegistry(self.bindings(), (replace(admission(), backend_lock_digest="f" * 64),))
        with self.assertRaisesRegex(PlasmaError, "registered backend lock"):
            registry.select("MKL25Z128VLK4", Operation.ERASE)

    def test_projection_digest_tamper_fails_closed(self) -> None:
        value = json.loads(
            files("plasma_interfaces")
            .joinpath(DEFAULT_ADMISSION_PROJECTION_RESOURCE)
            .read_text(encoding="utf-8")
        )
        value["targets"][0]["operations"][0]["backend_id"] = "forged-backend"
        with self.assertRaisesRegex(PlasmaError, "projection digest mismatch"):
            parse_operation_admission_projection(value)

    def test_resealed_hardware_ready_projection_fails_closed(self) -> None:
        value = json.loads(
            files("plasma_interfaces")
            .joinpath(DEFAULT_ADMISSION_PROJECTION_RESOURCE)
            .read_text(encoding="utf-8")
        )
        value["targets"][0]["operations"][0]["hardware_runtime_ready"] = True
        reseal_projection(value)
        with self.assertRaisesRegex(PlasmaError, "hardware-runtime blocked"):
            parse_operation_admission_projection(value)

    def test_default_stm32_projection_matches_generic_valid_pr_c_packages(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        admission_root = repository_root / "data/ic-support"
        migration_root = admission_root / "benchmarks/stm32f103c"
        sys.path[:0] = [str(admission_root), str(migration_root)]
        try:
            import stm32f103c_vendor_neutral_admission as migration
            from plasma_server.execution_router import _default_compiler_registry

            projected = {
                (row.target_icpn, row.request_operation): row
                for row in load_operation_admission_projection()
            }
            registry = _default_compiler_registry()
            expected_keys: set[tuple[str, str]] = set()

            for target in migration.CONTRACT["targets"]:
                package = migration.build_package(target)
                result = migration.validate_projection(package, target)
                self.assertEqual(result["status"], "VALID")
                artifact = package["artifacts"][package["operation_admission_id"]]
                for row in artifact["operations"]:
                    if row["state"] != "ADMITTED":
                        continue
                    key = (target, row["request_operation"])
                    expected_keys.add(key)
                    projected_row = projected[key]
                    self.assertEqual(projected_row.operation_admission_id, artifact["artifact_id"])
                    self.assertEqual(projected_row.operation_admission_digest, artifact["artifact_digest"])
                    self.assertEqual(projected_row.operation_contract_id, row["operation_contract_id"])
                    self.assertEqual(projected_row.operation_contract_digest, row["operation_contract_digest"])
                    self.assertEqual(projected_row.canonical_admission_digest, row["canonical_admission_digest"])
                    self.assertEqual(projected_row.backend_id, row["backend_id"])
                    self.assertEqual(projected_row.backend_lock_digest, row["backend_lock_digest"])
                    self.assertEqual(projected_row.compiler_id, row["compiler_id"])
                    self.assertFalse(projected_row.hardware_runtime_ready)

                    selected = registry.select(target, Operation[row["request_operation"]])
                    self.assertEqual(selected.admission, projected_row)

            self.assertEqual(set(projected), expected_keys)
        finally:
            del sys.path[:2]


if __name__ == "__main__":
    unittest.main()
