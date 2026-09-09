#!/usr/bin/env python3
from __future__ import annotations
import copy, json, tempfile
from pathlib import Path
from st_product_page_acquisition import AcquisitionError
from stm32g0_foundation import DEFAULT_CATALOG, deterministic_initial_targets, read_catalog
from stm32g0_phase4_8b_discovery import (
    CANONICAL_PAGE_404, DiscoveryTarget, discovery_is_clean, read_manifest, run_discovery,
)

def fake_builder(*, base_device: str, **_: object) -> dict[str, object]:
    return {"exact_icpns":[base_device+"T6"],"excluded_non_active_part_numbers":[]}

def fake_fetcher(url: str, timeout: float):
    return b"x", url, None, None

def main() -> int:
    rows=read_catalog(DEFAULT_CATALOG)
    pilot, targets=read_manifest(Path(__file__).with_name("stm32g0-phase4.8b-discovery-manifest.json"), rows)
    assert [(t.subfamily,t.base_device) for t in targets] == deterministic_initial_targets(rows)
    summary=run_discovery(pilot_id=pilot,targets=targets,catalog_rows=rows,fetcher=fake_fetcher,evidence_builder=fake_builder)
    assert discovery_is_clean(summary)
    assert summary["attempted"] == 12 and summary["active_candidate_targets"] == 12
    assert summary["claims"]["cmsis_alias_is_commercial_identity"] is False

    def lifecycle_builder(*, base_device: str, **_: object):
        return {"exact_icpns":[],"excluded_non_active_part_numbers":[{"icpn":base_device+"T6","marketing_status":"NRND"}]}
    one=[targets[0]]
    s=run_discovery(pilot_id=pilot,targets=one,catalog_rows=rows,fetcher=fake_fetcher,evidence_builder=lifecycle_builder)
    assert s["lifecycle_excluded_targets"] == 1 and s["acquisition_failure"] == 0

    def fail404(url: str, timeout: float): raise AcquisitionError(CANONICAL_PAGE_404)
    s=run_discovery(pilot_id=pilot,targets=one,catalog_rows=rows,fetcher=fail404,evidence_builder=fake_builder)
    assert s["source_unavailable_exclusions"] == 1 and s["identity_manual_intervention_required"] == 0

    def foreign_builder(*, base_device: str, **_: object):
        return {"exact_icpns":["STM32F103C8T6"],"excluded_non_active_part_numbers":[]}
    s=run_discovery(pilot_id=pilot,targets=one,catalog_rows=rows,fetcher=fake_fetcher,evidence_builder=foreign_builder)
    assert s["acquisition_failure"] == 1 and s["identity_manual_intervention_required"] == 1
    print("STM32G0 Phase 4.8B discovery tests: PASS")
    return 0

if __name__ == "__main__": raise SystemExit(main())
