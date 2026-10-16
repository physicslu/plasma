"""Cross-Manufacturer Catalog promotion coverage and blocker framework.

This module is an observer over the canonical ProgrammingQualificationRegistry.
It never promotes an ICPN, changes Product visibility, or grants execution.
Its purpose is to make L0/L1/L2/L3 coverage and the next blocked promotion edge
measurable with one vendor-neutral vocabulary.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from functools import cached_property, lru_cache
from typing import Any

from .device_catalog import (
    DeviceCatalog,
    DeviceCatalogIntegrityError,
    DeviceCatalogRecord,
    get_default_device_catalog,
)
from .programming_qualification import (
    ProgrammingQualificationRegistry,
    get_default_programming_qualification_registry,
)


EDGE_L0_TO_L1 = "L0_TO_L1"
EDGE_L1_TO_L2 = "L1_TO_L2"
EDGE_L2_TO_L3 = "L2_TO_L3"

NO_PROGRAMMING_ROUTE_EVIDENCE = "NO_PROGRAMMING_ROUTE_EVIDENCE"
MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED = "MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED"
BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED = "BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED"
PROVIDER_QUALIFICATION_INCOMPLETE = "PROVIDER_QUALIFICATION_INCOMPLETE"
PROVIDER_QUALIFICATION_BLOCKED = "PROVIDER_QUALIFICATION_BLOCKED"
PROVIDER_DECLARED_UNSUPPORTED = "PROVIDER_DECLARED_UNSUPPORTED"
PLASMA_VERIFIED_CONFIGURATION_MISSING = "PLASMA_VERIFIED_CONFIGURATION_MISSING"

BLOCKER_TAXONOMY = {
    NO_PROGRAMMING_ROUTE_EVIDENCE: (
        "Exact manufacturer identity exists, but no canonical source-backed "
        "programming route has been admitted."
    ),
    MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED: (
        "A canonical mapped target route exists, but no reviewed Programming "
        "Provider has qualified this exact ICPN."
    ),
    BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED: (
        "A source-backed backend candidate route exists, but it remains "
        "research-only and is not Programming Provider qualified."
    ),
    PROVIDER_QUALIFICATION_INCOMPLETE: (
        "A reviewed Programming Provider record exists, but qualification is "
        "still UNKNOWN or CANDIDATE rather than SUPPORTED."
    ),
    PROVIDER_QUALIFICATION_BLOCKED: (
        "A reviewed Programming Provider record exists and explicitly reports "
        "a BLOCKED software qualification state."
    ),
    PROVIDER_DECLARED_UNSUPPORTED: (
        "A reviewed Programming Provider record explicitly reports UNSUPPORTED."
    ),
    PLASMA_VERIFIED_CONFIGURATION_MISSING: (
        "Software programming is qualified, but no versioned PLASMA "
        "PPU/Site/Socket/Adapter/FPGA/PS/Provider configuration HIL PASS has "
        "promoted the ICPN to Level 3."
    ),
}

_BLOCKER_BY_REVIEWED_STATE = {
    "UNKNOWN": PROVIDER_QUALIFICATION_INCOMPLETE,
    "CANDIDATE": PROVIDER_QUALIFICATION_INCOMPLETE,
    "BLOCKED": PROVIDER_QUALIFICATION_BLOCKED,
    "UNSUPPORTED": PROVIDER_DECLARED_UNSUPPORTED,
}


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise DeviceCatalogIntegrityError(f"Catalog promotion framework: {reason}")


class CatalogPromotionFramework:
    """Read-only cross-Manufacturer projection over canonical qualification."""

    def __init__(
        self,
        catalog: DeviceCatalog,
        qualification: ProgrammingQualificationRegistry,
    ) -> None:
        self._catalog = catalog
        self._qualification = qualification

    def observe(self, record: DeviceCatalogRecord) -> dict[str, Any]:
        _require(
            record.identity_state == "IDENTIFIED" and record.icpn is not None,
            f"promotion observation requires one IDENTIFIED exact ICPN: {record.identifier}",
        )
        qualification = self._qualification.describe(record.vendor, record.identifier)
        level = qualification.get("catalog_level")
        _require(
            isinstance(level, int) and level in {0, 1, 2, 3},
            f"invalid Catalog Level for {record.vendor}/{record.identifier}: {level!r}",
        )

        selector_visible = bool(qualification.get("selector_visible", False))
        job_selectable = bool(qualification.get("job_selectable", False))
        _require(
            selector_visible == (level >= 1),
            f"selector visibility drift for {record.vendor}/{record.identifier}",
        )
        _require(
            job_selectable == (level >= 2),
            f"Job Picker eligibility drift for {record.vendor}/{record.identifier}",
        )
        _require(
            qualification.get("execution_authorized") is False,
            f"Catalog projection must not authorize execution: {record.vendor}/{record.identifier}",
        )

        promotion_edge: str | None
        blocker: str | None
        if level == 0:
            promotion_edge = EDGE_L0_TO_L1
            blocker = NO_PROGRAMMING_ROUTE_EVIDENCE
        elif level == 1:
            promotion_edge = EDGE_L1_TO_L2
            if qualification.get("reviewed"):
                state = qualification.get("state")
                _require(
                    state != "SUPPORTED",
                    f"SUPPORTED qualification cannot remain Level 1: {record.vendor}/{record.identifier}",
                )
                blocker = _BLOCKER_BY_REVIEWED_STATE.get(str(state))
                _require(
                    blocker is not None,
                    f"unclassified reviewed provider state for {record.vendor}/{record.identifier}: {state!r}",
                )
            elif qualification.get("route_evidence") == "backend_candidate_registry":
                blocker = BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED
            elif record.mapping_status == "mapped" and bool(record.target_config):
                blocker = MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED
            else:
                raise DeviceCatalogIntegrityError(
                    "Catalog promotion framework: Level 1 route evidence is not "
                    f"classifiable for {record.vendor}/{record.identifier}"
                )
        elif level == 2:
            _require(
                qualification.get("state") == "SUPPORTED",
                f"Level 2 requires SUPPORTED qualification: {record.vendor}/{record.identifier}",
            )
            promotion_edge = EDGE_L2_TO_L3
            blocker = PLASMA_VERIFIED_CONFIGURATION_MISSING
        else:
            promotion_edge = None
            blocker = None

        return {
            "manufacturer": record.vendor,
            "icpn": record.identifier,
            "catalog_level": level,
            "catalog_level_state": qualification.get("catalog_level_state"),
            "programming_state": qualification.get("state"),
            "reviewed": bool(qualification.get("reviewed", False)),
            "selector_visible": selector_visible,
            "job_selectable": job_selectable,
            "promotion_edge": promotion_edge,
            "promotion_blocker": blocker,
        }

    @cached_property
    def report(self) -> dict[str, Any]:
        by_manufacturer: dict[str, dict[str, Any]] = {}
        total_levels: Counter[int] = Counter()
        total_blockers: dict[str, Counter[str]] = {
            EDGE_L0_TO_L1: Counter(),
            EDGE_L1_TO_L2: Counter(),
            EDGE_L2_TO_L3: Counter(),
        }
        total_selector_visible = 0
        total_job_selectable = 0
        observed = 0

        for record in self._catalog.records:
            if record.identity_state != "IDENTIFIED" or record.icpn is None:
                continue
            observation = self.observe(record)
            observed += 1
            level = int(observation["catalog_level"])
            total_levels[level] += 1
            total_selector_visible += int(bool(observation["selector_visible"]))
            total_job_selectable += int(bool(observation["job_selectable"]))

            manufacturer = record.vendor
            row = by_manufacturer.setdefault(
                manufacturer,
                {
                    "manufacturer": manufacturer,
                    "catalog_level_counts": Counter(),
                    "promotion_blocker_counts": {
                        EDGE_L0_TO_L1: Counter(),
                        EDGE_L1_TO_L2: Counter(),
                        EDGE_L2_TO_L3: Counter(),
                    },
                    "selector_visible_exact_icpns": 0,
                    "job_selectable_exact_icpns": 0,
                    "discovered_exact_icpns": 0,
                },
            )
            row["discovered_exact_icpns"] += 1
            row["catalog_level_counts"][level] += 1
            row["selector_visible_exact_icpns"] += int(bool(observation["selector_visible"]))
            row["job_selectable_exact_icpns"] += int(bool(observation["job_selectable"]))

            edge = observation["promotion_edge"]
            blocker = observation["promotion_blocker"]
            if edge is not None:
                _require(
                    isinstance(blocker, str) and blocker in BLOCKER_TAXONOMY,
                    f"unknown blocker for {record.vendor}/{record.identifier}",
                )
                row["promotion_blocker_counts"][edge][blocker] += 1
                total_blockers[edge][blocker] += 1

        _require(observed == self._catalog.size, "Production Catalog contains non-exact/non-identified rows")
        _require(
            sum(total_levels.values()) == observed,
            "Catalog Level totals do not reconcile with exact identity count",
        )
        _require(
            total_selector_visible == total_levels[1] + total_levels[2] + total_levels[3],
            "selector-visible total does not reconcile with L1-L3",
        )
        _require(
            total_job_selectable == total_levels[2] + total_levels[3],
            "Job Picker total does not reconcile with L2-L3",
        )

        def level_payload(counter: Counter[int]) -> dict[str, int]:
            return {str(level): int(counter[level]) for level in range(4)}

        def blocker_payload(rows: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
            return {
                edge: dict(sorted(counter.items()))
                for edge, counter in rows.items()
            }

        manufacturers = []
        for manufacturer in sorted(by_manufacturer, key=str.casefold):
            row = by_manufacturer[manufacturer]
            manufacturers.append(
                {
                    "manufacturer": manufacturer,
                    "discovered_exact_icpns": int(row["discovered_exact_icpns"]),
                    "catalog_level_counts": level_payload(row["catalog_level_counts"]),
                    "selector_visible_exact_icpns": int(row["selector_visible_exact_icpns"]),
                    "job_selectable_exact_icpns": int(row["job_selectable_exact_icpns"]),
                    "promotion_blocker_counts": blocker_payload(
                        row["promotion_blocker_counts"]
                    ),
                }
            )

        return {
            "schema_version": "1.0.0",
            "framework": "ADR-0002-cross-manufacturer-promotion",
            "authority": "ProgrammingQualificationRegistry",
            "catalog_id": self._catalog.catalog_id,
            "catalog_version": self._catalog.catalog_version,
            "catalog_revision_sha256": self._catalog.revision_sha256,
            "manufacturer_count": len(manufacturers),
            "discovered_exact_icpns": observed,
            "catalog_level_counts": level_payload(total_levels),
            "selector_visible_exact_icpns": total_selector_visible,
            "job_selectable_exact_icpns": total_job_selectable,
            "promotion_blocker_counts": blocker_payload(total_blockers),
            "blocker_taxonomy": dict(sorted(BLOCKER_TAXONOMY.items())),
            "manufacturers": manufacturers,
            "execution_authorized_by_framework": False,
        }


@lru_cache(maxsize=1)
def get_default_catalog_promotion_framework() -> CatalogPromotionFramework:
    return CatalogPromotionFramework(
        get_default_device_catalog(),
        get_default_programming_qualification_registry(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report ADR-0002 cross-Manufacturer Catalog promotion coverage"
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact deterministic JSON",
    )
    args = parser.parse_args(argv)
    report = get_default_catalog_promotion_framework().report
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            indent=None if args.compact else 2,
            separators=(",", ":") if args.compact else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
