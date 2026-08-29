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

from st_product_page_acquisition import AcquisitionError  # noqa: E402
from stm32f1_acquisition_pilot import (  # noqa: E402
    PilotTarget,
    catalog_mapping,
    pilot_is_clean,
    read_catalog,
    read_manifest,
    run_pilot,
)


def html_for(*icpns: str) -> bytes:
    rows = "".join(f"<tr><td>{icpn}</td></tr>" for icpn in icpns)
    return (
        "<html><body><h2>Quality and Reliability</h2>"
        f"<table><thead><tr><th>Part Number</th></tr></thead><tbody>{rows}</tbody></table>"
        "<h2>Sample &amp; Buy</h2></body></html>"
    ).encode("utf-8")


class PilotTests(unittest.TestCase):
    def test_checked_in_manifest_is_bounded_and_valid(self) -> None:
        pilot_id, targets = read_manifest(HERE / "stm32f1-acquisition-pilot-manifest.json")
        self.assertEqual(pilot_id, "stm32f1-phase2.5-controlled-batch-2026-08-29")
        self.assertEqual(len(targets), 6)
        self.assertEqual(len({target.base_device for target in targets}), 6)
        self.assertEqual(len({target.source_url for target in targets}), 6)

    def test_checked_in_manifest_maps_uniquely_to_stm32f1_openocd_capability(self) -> None:
        _, targets = read_manifest(HERE / "stm32f1-acquisition-pilot-manifest.json")
        catalog_rows = read_catalog(HERE / "openocd-parts-canonical.csv")
        for target in targets:
            with self.subTest(base_device=target.base_device):
                mapping = catalog_mapping(target.base_device, catalog_rows)
                self.assertEqual(mapping["status"], "unique")
                self.assertEqual(mapping["identifier_kind"], "cmsis_device_name")
                self.assertEqual(mapping["target_configs"], ["tcl/target/stm32f1x.cfg"])

    def test_manifest_rejects_duplicate_base_device(self) -> None:
        payload = {
            "schema_version": 1,
            "pilot_id": "test",
            "targets": [
                {
                    "base_device": "STM32F100C8",
                    "source_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32f100c8.html",
                    "selection_reason": "first",
                },
                {
                    "base_device": "STM32F100C8",
                    "source_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32f100c8.html",
                    "selection_reason": "duplicate",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(AcquisitionError, "duplicate pilot base_device"):
                read_manifest(path)

    def test_catalog_mapping_classifies_unique_ambiguous_and_unmapped(self) -> None:
        rows = [
            {
                "part_number": "STM32F100C8",
                "identifier_kind": "cmsis_device_name",
                "target_config": "a.cfg",
            },
            {
                "part_number": "STM32F101C8",
                "identifier_kind": "cmsis_device_name",
                "target_config": "a.cfg",
            },
            {
                "part_number": "STM32F101C8",
                "identifier_kind": "ordering_pattern",
                "target_config": "b.cfg",
            },
        ]
        self.assertEqual(catalog_mapping("STM32F100C8", rows)["status"], "unique")
        self.assertEqual(catalog_mapping("STM32F101C8", rows)["status"], "ambiguous")
        self.assertEqual(catalog_mapping("STM32F102C8", rows)["status"], "unmapped")

    def test_run_pilot_aggregates_success_failure_mapping_and_candidates(self) -> None:
        targets = [
            PilotTarget(
                "STM32F100C8",
                "https://www.st.com/en/microcontrollers-microprocessors/stm32f100c8.html",
                "success",
            ),
            PilotTarget(
                "STM32F102C8",
                "https://www.st.com/en/microcontrollers-microprocessors/stm32f102c8.html",
                "failure",
            ),
        ]
        catalog_rows = [
            {
                "part_number": "STM32F100C8",
                "identifier_kind": "cmsis_device_name",
                "target_config": "tcl/target/stm32f1x.cfg",
            }
        ]

        def fake_fetcher(url: str, timeout_seconds: float):
            self.assertEqual(timeout_seconds, 5.0)
            if url.endswith("stm32f102c8.html"):
                raise AcquisitionError("synthetic layout failure")
            return (
                html_for("STM32F100C8T6B", "STM32F100C8T6BTR"),
                url,
                '"etag"',
                "Sat, 29 Aug 2026 00:00:00 GMT",
            )

        summary = run_pilot(
            pilot_id="test",
            targets=targets,
            catalog_rows=catalog_rows,
            fetcher=fake_fetcher,
            timeout_seconds=5.0,
            retrieved_at_factory=lambda: "2026-08-29T00:00:00Z",
        )
        self.assertEqual(summary["attempted"], 2)
        self.assertEqual(summary["acquisition_success"], 1)
        self.assertEqual(summary["acquisition_failure"], 1)
        self.assertEqual(summary["exact_icpn_candidates"], 2)
        self.assertEqual(
            summary["canonical_mapping"],
            {"unique": 1, "ambiguous": 0, "unmapped": 1},
        )
        self.assertEqual(summary["openocd_cfg_mapping"], {"mapped": 1, "total": 2})
        self.assertEqual(summary["manual_intervention_required"], 1)
        self.assertFalse(pilot_is_clean(summary))
        self.assertEqual(summary["results"][0]["acquisition_status"], "success")
        self.assertEqual(summary["results"][1]["acquisition_status"], "failure")

    def test_successful_acquisition_with_ambiguous_mapping_is_not_clean(self) -> None:
        target = PilotTarget(
            "STM32F101C8",
            "https://www.st.com/en/microcontrollers-microprocessors/stm32f101c8.html",
            "ambiguous mapping",
        )
        catalog_rows = [
            {
                "part_number": "STM32F101C8",
                "identifier_kind": "cmsis_device_name",
                "target_config": "tcl/target/stm32f1x.cfg",
            },
            {
                "part_number": "STM32F101C8",
                "identifier_kind": "ordering_pattern",
                "target_config": "tcl/target/stm32f1x.cfg",
            },
        ]

        def fake_fetcher(url: str, timeout_seconds: float):
            del timeout_seconds
            return html_for("STM32F101C8T6"), url, None, None

        summary = run_pilot(
            pilot_id="test",
            targets=[target],
            catalog_rows=catalog_rows,
            fetcher=fake_fetcher,
            retrieved_at_factory=lambda: "2026-08-29T00:00:00Z",
        )
        self.assertEqual(summary["acquisition_failure"], 0)
        self.assertEqual(summary["canonical_mapping"]["ambiguous"], 1)
        self.assertEqual(summary["manual_intervention_required"], 1)
        self.assertFalse(pilot_is_clean(summary))


if __name__ == "__main__":
    unittest.main()
