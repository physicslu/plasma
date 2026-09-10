from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
IC_SUPPORT = ROOT / "data" / "ic-support"
sys.path.insert(0, str(IC_SUPPORT))

from admission.digest import canonical_digest  # noqa: E402
from admission.validate import AdmissionValidationError, validate_admission_package  # noqa: E402


SCHEMA_IDS = {
    "artifact-ref-v1.schema.json": "plasma://ic-support/admission/artifact-ref-v1",
    "manufacturer-evidence-ref-v1.schema.json": "plasma://ic-support/admission/manufacturer-evidence-ref-v1",
    "review-binding-v1.schema.json": "plasma://ic-support/admission/review-binding-v1",
    "post-review-disposition-v1.schema.json": "plasma://ic-support/admission/post-review-disposition-v1",
    "candidate-review-v1.schema.json": "plasma://ic-support/admission/candidate-review-v1",
    "canonical-admission-envelope-v1.schema.json": "plasma://ic-support/admission/canonical-admission-envelope-v1",
    "operation-admission-v1.schema.json": "plasma://ic-support/admission/operation-admission-v1",
    "backend-implementation-binding-v1.schema.json": "plasma://ic-support/admission/backend-implementation-binding-v1",
}
FORBIDDEN = (
    "STM32",
    "STM32F103",
    "STMicroelectronics",
    "NXP",
    "MKL25",
    "KL25",
    "FLASH_CR",
    "KEYR",
    "FTFA",
    "FCCOB",
    "FSEC",
)
LEGACY_SCHEMA_SHA256 = "900cf98da5fbe308dfc69715f667291ab04512a67892c6f0bfff1f5e26c3811b"


def seal(value: dict) -> dict:
    value["artifact_digest"] = canonical_digest(value)
    return value


def ref(value: dict, *, include_schema: bool = True) -> dict:
    result = {key: value[key] for key in ("artifact_id", "artifact_type", "artifact_digest")}
    if include_schema:
        result.update({key: value[key] for key in ("schema_id", "schema_version")})
    return result


def opaque(schema_id: str, artifact_id: str, artifact_type: str, **payload) -> dict:
    return seal(
        {
            "schema_id": schema_id,
            "schema_version": "1.0.0",
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            **payload,
        }
    )


def fixture(vendor: str, icpn: str, payload_schema: str, semantic_payload: dict) -> dict:
    prefix = vendor.casefold()
    source_digest = hashlib.sha256(f"{vendor}-manufacturer-source".encode()).hexdigest()
    artifacts: dict[str, dict] = {}

    source_lock = opaque(
        f"plasma://fixtures/{prefix}/source-lock-v1",
        f"{prefix}-source-lock",
        "source_lock",
        sources=[{"source_id": f"{prefix}-manual", "source_digest": source_digest}],
    )
    fact = opaque(f"plasma://fixtures/{prefix}/fact-v1", f"{prefix}-fact", "manufacturer_fact", statement="fixture statement")
    fact_set = opaque(f"plasma://fixtures/{prefix}/fact-set-v1", f"{prefix}-fact-set", "reviewed_fact_set", facts=[ref(fact)])
    review_report = opaque(f"plasma://fixtures/{prefix}/review-v1", f"{prefix}-review-report", "review_artifact", verdict="fixture-pass")
    artifacts.update({item["artifact_id"]: item for item in (source_lock, fact, fact_set, review_report)})

    review_binding = seal(
        {
            "schema_id": SCHEMA_IDS["review-binding-v1.schema.json"],
            "schema_version": "1.0.0",
            "artifact_id": f"{prefix}-review-binding",
            "artifact_type": "review_binding",
            "reviewed_artifact": ref(fact_set),
            "review_artifact": ref(review_report),
            "review_status": "fixture-reviewed",
        }
    )
    candidate = opaque(f"plasma://fixtures/{prefix}/candidate-v1", f"{prefix}-candidate", "candidate_fact", statement="candidate statement")
    artifacts.update({item["artifact_id"]: item for item in (review_binding, candidate)})
    disposition = seal(
        {
            "schema_id": SCHEMA_IDS["post-review-disposition-v1.schema.json"],
            "schema_version": "1.0.0",
            "artifact_id": f"{prefix}-disposition",
            "artifact_type": "post_review_disposition",
            "review_binding": ref(review_binding),
            "dispositions": [
                {
                    "source_fact": ref(fact),
                    "action": "ACCEPT",
                    "projection_state": "CANONICAL_REQUIRED",
                    "candidate_artifacts": [ref(candidate)],
                }
            ],
        }
    )
    artifacts[disposition["artifact_id"]] = disposition
    evidence = {
        "source_lock_id": source_lock["artifact_id"],
        "source_id": f"{prefix}-manual",
        "source_digest": source_digest,
        "authority": "manufacturer",
        "locator": "fixture locator",
        "section": "fixture section",
    }
    candidate_review = seal(
        {
            "schema_id": SCHEMA_IDS["candidate-review-v1.schema.json"],
            "schema_version": "1.0.0",
            "artifact_id": f"{prefix}-candidate-review",
            "artifact_type": "candidate_manufacturer_review",
            "disposition": ref(disposition),
            "candidate_reviews": [
                {
                    "candidate": ref(candidate),
                    "evidence": [evidence],
                    "review_status": "fixture-pass",
                    "dimensions": {"support": "pass", "scope": "pass"},
                }
            ],
        }
    )
    vendor_payload = opaque(payload_schema, f"{prefix}-vendor-payload", "vendor_canonical_payload", **semantic_payload)
    constraints = opaque(f"plasma://fixtures/{prefix}/constraints-v1", f"{prefix}-constraints", "vendor_backend_constraints", opaque_semantics=semantic_payload)
    implementation_source = opaque(f"plasma://fixtures/{prefix}/implementation-source-v1", f"{prefix}-implementation-source", "implementation_source", files={"driver": hashlib.sha256(prefix.encode()).hexdigest()})
    operation_contract = opaque(f"plasma://fixtures/{prefix}/operation-contract-v1", f"{prefix}-operation-contract", "operation_contract", operation="fixture-operation")
    artifacts.update({item["artifact_id"]: item for item in (candidate_review, vendor_payload, constraints, implementation_source, operation_contract)})

    backend = {
        "schema_id": SCHEMA_IDS["backend-implementation-binding-v1.schema.json"],
        "schema_version": "1.0.0",
        "artifact_id": f"{prefix}-backend",
        "artifact_type": "backend_implementation_binding",
        "backend_id": f"{prefix}-backend",
        "implementation": {"identity": f"{prefix}-tool", "revision": "fixture-revision"},
        "implementation_evidence": [ref(implementation_source)],
        "vendor_constraint_payload": ref(constraints),
    }
    backend["lock_digest"] = canonical_digest(backend, omit=("artifact_digest", "lock_digest"))
    seal(backend)
    artifacts[backend["artifact_id"]] = backend

    envelope = seal(
        {
            "schema_id": SCHEMA_IDS["canonical-admission-envelope-v1.schema.json"],
            "schema_version": "1.0.0",
            "artifact_id": f"{prefix}-envelope",
            "artifact_type": "canonical_admission_envelope",
            "target": {"vendor_id": vendor, "icpn": icpn},
            "vendor_payload": ref(vendor_payload),
            "lineage": {
                "source_lock": ref(source_lock),
                "review_binding": ref(review_binding),
                "disposition": ref(disposition),
                "candidate_review": ref(candidate_review),
            },
            "admission": {"state": "ADMITTED", "unresolved_requirements": []},
        }
    )
    artifacts[envelope["artifact_id"]] = envelope
    operation_admission = seal(
        {
            "schema_id": SCHEMA_IDS["operation-admission-v1.schema.json"],
            "schema_version": "1.0.0",
            "artifact_id": f"{prefix}-operation-admission",
            "artifact_type": "operation_admission",
            "target": {"vendor_id": vendor, "icpn": icpn},
            "operations": [
                {
                    "request_operation": "fixture-operation",
                    "operation_contract_id": operation_contract["artifact_id"],
                    "operation_contract_digest": operation_contract["artifact_digest"],
                    "state": "ADMITTED",
                    "canonical_admission_digest": envelope["artifact_digest"],
                    "backend_id": backend["backend_id"],
                    "backend_lock_digest": backend["lock_digest"],
                    "compiler_id": f"{prefix}-compiler",
                    "canonical_requirements": ["fixture.requirement"],
                    "unresolved_requirements": [],
                    "hardware_runtime_ready": False,
                }
            ],
        }
    )
    artifacts[operation_admission["artifact_id"]] = operation_admission
    return {
        "artifacts": artifacts,
        "compiler_bindings": {backend["backend_id"]: [f"{prefix}-compiler"]},
        "root_envelope_id": envelope["artifact_id"],
        "operation_admission_id": operation_admission["artifact_id"],
    }


class VendorNeutralAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packages = [
            fixture("Acme", "A100-Q", "plasma://fixtures/acme/payload-v3", {"banks": [1, 2], "word_width": 8}),
            fixture("Boreal", "BETA-7", "plasma://fixtures/boreal/device-map-v8", {"zones": {"main": "0x20"}, "write_unit": 16}),
            fixture("Cygnus", "C-42", "plasma://fixtures/cygnus/geometry-v2", {"segments": 3, "token": "opaque"}),
        ]

    def test_same_validator_accepts_three_distinct_payload_schemas(self) -> None:
        results = [validate_admission_package(package) for package in self.packages]
        self.assertEqual([result["status"] for result in results], ["VALID", "VALID", "VALID"])
        schemas = {
            package["artifacts"][package["root_envelope_id"]]["vendor_payload"]["schema_id"]
            for package in self.packages
        }
        self.assertEqual(len(schemas), 3)

    def test_vendor_semantic_fields_are_opaque(self) -> None:
        package = copy.deepcopy(self.packages[0])
        envelope = package["artifacts"][package["root_envelope_id"]]
        payload = package["artifacts"][envelope["vendor_payload"]["artifact_id"]]
        payload["unrecognized_nested_semantics"] = {"anything": [1, "two", {"three": True}]}
        seal(payload)
        envelope["vendor_payload"] = ref(payload)
        seal(envelope)
        operation = package["artifacts"][package["operation_admission_id"]]
        operation["operations"][0]["canonical_admission_digest"] = envelope["artifact_digest"]
        seal(operation)
        self.assertEqual(validate_admission_package(package)["status"], "VALID")

    def test_swapped_vendor_payload_fails(self) -> None:
        package = copy.deepcopy(self.packages[0])
        envelope = package["artifacts"][package["root_envelope_id"]]
        foreign = self.packages[1]["artifacts"][self.packages[1]["artifacts"][self.packages[1]["root_envelope_id"]]["vendor_payload"]["artifact_id"]]
        package["artifacts"][envelope["vendor_payload"]["artifact_id"]] = copy.deepcopy(foreign)
        with self.assertRaisesRegex(AdmissionValidationError, "identity mismatch"):
            validate_admission_package(package)

    def test_stale_payload_review_and_disposition_fail(self) -> None:
        for artifact_id_fragment, mutation in (
            ("vendor-payload", lambda value: value.update({"tampered": True})),
            ("review-binding", lambda value: value.update({"review_status": "changed"})),
            ("candidate-review", lambda value: value["candidate_reviews"][0].update({"review_status": "changed"})),
            ("disposition", lambda value: value["dispositions"][0].update({"projection_state": "KNOWLEDGE_ONLY"})),
        ):
            package = copy.deepcopy(self.packages[0])
            artifact = next(value for key, value in package["artifacts"].items() if artifact_id_fragment in key)
            mutation(artifact)
            with self.assertRaises(AdmissionValidationError):
                validate_admission_package(package)

    def test_missing_candidate_lineage_fails(self) -> None:
        package = copy.deepcopy(self.packages[0])
        review = next(value for key, value in package["artifacts"].items() if key.endswith("candidate-review"))
        review["candidate_reviews"] = []
        seal(review)
        envelope = package["artifacts"][package["root_envelope_id"]]
        envelope["lineage"]["candidate_review"] = ref(review)
        seal(envelope)
        operation = package["artifacts"][package["operation_admission_id"]]
        operation["operations"][0]["canonical_admission_digest"] = envelope["artifact_digest"]
        seal(operation)
        with self.assertRaisesRegex(AdmissionValidationError, "coverage mismatch"):
            validate_admission_package(package)

    def test_operation_contract_backend_and_compiler_swaps_fail(self) -> None:
        operation_cases = []
        contract_swap = copy.deepcopy(self.packages[0])
        foreign_contract = next(value for value in self.packages[1]["artifacts"].values() if value["artifact_type"] == "operation_contract")
        local_contract_id = contract_swap["artifacts"][contract_swap["operation_admission_id"]]["operations"][0]["operation_contract_id"]
        contract_swap["artifacts"][local_contract_id] = copy.deepcopy(foreign_contract)
        operation_cases.append(contract_swap)

        backend_swap = copy.deepcopy(self.packages[0])
        local_backend_id = backend_swap["artifacts"][backend_swap["operation_admission_id"]]["operations"][0]["backend_id"]
        foreign_backend = next(value for value in self.packages[1]["artifacts"].values() if value["artifact_type"] == "backend_implementation_binding")
        backend_swap["artifacts"][local_backend_id] = copy.deepcopy(foreign_backend)
        operation_cases.append(backend_swap)

        compiler_swap = copy.deepcopy(self.packages[0])
        compiler_swap["artifacts"][compiler_swap["operation_admission_id"]]["operations"][0]["compiler_id"] = "foreign-compiler"
        seal(compiler_swap["artifacts"][compiler_swap["operation_admission_id"]])
        operation_cases.append(compiler_swap)

        for package in operation_cases:
            with self.assertRaises(AdmissionValidationError):
                validate_admission_package(package)

    def test_explicit_operation_binding_mismatches_fail_closed(self) -> None:
        cases = []
        for field, value, message in (
            ("operation_contract_digest", "0" * 64, "operation contract digest binding mismatch"),
            ("backend_lock_digest", "0" * 64, "backend-lock mismatch"),
            ("compiler_id", "unregistered-compiler", "compiler mismatch"),
        ):
            package = copy.deepcopy(self.packages[0])
            operation = package["artifacts"][package["operation_admission_id"]]
            operation["operations"][0][field] = value
            seal(operation)
            cases.append((package, message))
        for package, message in cases:
            with self.assertRaisesRegex(AdmissionValidationError, message):
                validate_admission_package(package)

    def test_unknown_field_is_rejected(self) -> None:
        package = copy.deepcopy(self.packages[0])
        envelope = package["artifacts"][package["root_envelope_id"]]
        envelope["unexpected"] = "field"
        seal(envelope)
        with self.assertRaisesRegex(AdmissionValidationError, "fields mismatch"):
            validate_admission_package(package)

    def test_vendor_payload_schema_bindings_are_required(self) -> None:
        envelope_case = copy.deepcopy(self.packages[0])
        envelope = envelope_case["artifacts"][envelope_case["root_envelope_id"]]
        del envelope["vendor_payload"]["schema_id"]
        seal(envelope)

        backend_case = copy.deepcopy(self.packages[0])
        backend = next(value for value in backend_case["artifacts"].values() if value["artifact_type"] == "backend_implementation_binding")
        del backend["vendor_constraint_payload"]["schema_id"]
        backend["lock_digest"] = canonical_digest(backend, omit=("artifact_digest", "lock_digest"))
        seal(backend)

        for package in (envelope_case, backend_case):
            with self.assertRaisesRegex(AdmissionValidationError, "schema binding is required"):
                validate_admission_package(package)

    def test_schema_catalog_and_forbidden_term_scan(self) -> None:
        schema_root = IC_SUPPORT / "schema"
        for filename, schema_id in SCHEMA_IDS.items():
            schema = json.loads((schema_root / filename).read_text(encoding="utf-8"))
            self.assertEqual(schema["$id"], schema_id)
            self.assertFalse(schema.get("additionalProperties", True), filename)
        scanned = [*sorted((IC_SUPPORT / "admission").glob("*.py"))]
        scanned.extend(schema_root / filename for filename in SCHEMA_IDS)
        scanned.append(ROOT / "docs" / "architecture" / "vendor-neutral-ic-admission.md")
        for path in scanned:
            text = path.read_text(encoding="utf-8")
            for term in FORBIDDEN:
                self.assertNotIn(term, text, f"{path}: forbidden term {term}")

    def test_historical_artifacts_are_unchanged(self) -> None:
        base_ref = os.environ.get("ADMISSION_BASE_REF", "origin/main")
        legacy_path = "data/ic-support/schema/post-review-disposition-v0.schema.json"
        head_blob = subprocess.run(
            ["git", "show", f"HEAD:{legacy_path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        base_blob = subprocess.run(
            ["git", "show", f"{base_ref}:{legacy_path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(head_blob, base_blob)
        self.assertEqual(hashlib.sha256(head_blob).hexdigest(), LEGACY_SCHEMA_SHA256)
        changed = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        protected = ("data/ic-support/benchmarks/stm32f103c/", "data/ic-support/benchmarks/nxp-kl25/")
        self.assertFalse([path for path in changed if path.startswith(protected)])


if __name__ == "__main__":
    unittest.main()
