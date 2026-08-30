#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from device_catalog_admission_framework import write_canonical_dataset  # noqa: E402
from device_catalog_pipeline_framework import (  # noqa: E402
    AdmissionInputs,
    PipelineError,
    build_pipeline_plan,
    pipeline_plan_is_clean,
)


FIELDS = ["manufacturer", "base_device", "icpn", "source_reference"]


def row_builder(candidate: dict[str, object], fields: list[str]) -> dict[str, str]:
    row = {
        "manufacturer": str(candidate["manufacturer"]),
        "base_device": str(candidate["base_device"]),
        "icpn": str(candidate["icpn"]),
        "source_reference": str(candidate["authoritative_evidence"]["source_url"]),
    }
    if set(row) != set(fields):
        raise AssertionError("fixture fields changed")
    return row


class PipelineFrameworkTests(unittest.TestCase):
    def _canonical(self, root: Path) -> Path:
        path = root / "canonical.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
        return path

    def _inputs(self) -> AdmissionInputs:
        candidates = []
        for base, icpn in (("EXM32A1", "EXM32A1T6"), ("EXM32B2", "EXM32B2U7")):
            candidates.append(
                {
                    "manufacturer": "ExampleSemiconductor",
                    "base_device": base,
                    "icpn": icpn,
                    "authoritative_evidence": {
                        "evidence_id": "example-evidence-1",
                        "source_url": f"https://example.invalid/{base}",
                    },
                    "base_mapping": {
                        "status": "unique",
                        "target_configs": [f"target/{base.lower()}.cfg"],
                    },
                }
            )
        return AdmissionInputs(
            evidence_id="example-evidence-1",
            candidate_inputs=candidates,
            source_provenance={
                "repository": "physicslu/plasma",
                "executed_git_sha": "b" * 40,
            },
            input_bindings={"adapter": "synthetic-example-v1"},
            expected_candidate_count=2,
        )

    def test_pipeline_has_no_stm32_or_transport_assumption(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            canonical = self._canonical(Path(temp))
            plan = build_pipeline_plan(
                canonical_path=canonical,
                row_builder=row_builder,
                admission_inputs=self._inputs(),
            )
            self.assertTrue(pipeline_plan_is_clean(plan))
            self.assertEqual(plan["candidate_count"], 2)
            self.assertEqual(plan["decision_counts"]["admit"], 2)
            self.assertEqual(plan["pipeline_expected_candidate_count"], 2)
            self.assertEqual(plan["candidates"][0]["manufacturer"], "ExampleSemiconductor")

    def test_writer_remains_owned_by_generic_admission_framework(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            canonical = self._canonical(Path(temp))
            plan = build_pipeline_plan(
                canonical_path=canonical,
                row_builder=row_builder,
                admission_inputs=self._inputs(),
            )
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 0)
            self.assertEqual(first["rows_after"], 2)
            self.assertEqual(second["status"], "no_op")

    def test_adapter_candidate_count_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            canonical = self._canonical(Path(temp))
            inputs = self._inputs()
            bad = AdmissionInputs(
                evidence_id=inputs.evidence_id,
                candidate_inputs=inputs.candidate_inputs,
                source_provenance=inputs.source_provenance,
                input_bindings=inputs.input_bindings,
                expected_candidate_count=3,
            )
            with self.assertRaisesRegex(PipelineError, "candidate count"):
                build_pipeline_plan(
                    canonical_path=canonical,
                    row_builder=row_builder,
                    admission_inputs=bad,
                )


if __name__ == "__main__":
    unittest.main()
