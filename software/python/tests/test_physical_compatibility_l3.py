"""L3 host-only regression: independent PPU/Site and Socket routes.

Synthetic records exercise schema/derivation only; they are not physical HIL.
The production default is separately authenticated against preserved receipts.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from plasma_web.device_catalog import DeviceCatalog, DeviceCatalogIntegrityError, DeviceCatalogRecord
from plasma_web.physical_compatibility import (
    PhysicalCompatibilityRegistry,
    get_default_physical_compatibility_registry,
)
from plasma_web.programming_qualification import ProgrammingQualificationRegistry


class _FakeProvider:
    reviewed_exact_keys = (("ExampleVendor", "EXAMPLE123"),)

    def __init__(self, state: str = "SUPPORTED") -> None:
        self.state = state

    def lookup(self, manufacturer: str, icpn: str):
        return {"software_state": self.state} if (manufacturer, icpn) in self.reviewed_exact_keys else None

    def describe(self, manufacturer: str, icpn: str):
        return {
            "software_state": self.state,
            "reviewed": True,
            "provider": {"provider_id": "fake", "version": "1"},
            "operations": {},
            "programming": None,
        }


def _fake_catalog() -> DeviceCatalog:
    return DeviceCatalog((DeviceCatalogRecord(
        vendor="ExampleVendor", family="Example", subfamily=None, plasma_series="Example",
        identifier="EXAMPLE123", identifier_kind="manufacturer_part_number",
        cpu_architectures=(), target_config="target/fake.cfg", openocd_distribution="fake",
        mapping_status="mapped", validation_status="unknown", catalog_origin="test",
        production_admitted=True, package="LQFP", pin_count="48",
    ),))


def _synthetic(kind: str) -> dict:
    # The only physical receipt used by the released L3 record is real; these
    # modified identities are never loaded into the production registry.
    real = get_default_physical_compatibility_registry().verified_for(
        "STMicroelectronics", "STM32F103C8T6"
    )[0]
    record = deepcopy(real)
    record["configuration_id"] = f"synthetic-{kind.lower()}-v1"
    record["identity"]["manufacturer"] = "ExampleVendor"
    record["identity"]["icpn"] = "EXAMPLE123"
    record["engine"]["provider_id"] = "fake"
    record["engine"]["provider_version"] = "1"
    record["verification_type"] = kind
    if kind == "SOCKET_ADAPTER":
        record["connection_mode"] = "SOCKET_ADAPTER"
        record["socket"] = {"model": "synthetic-test-fixture", "revision": "test-v1"}
    return record


@pytest.mark.parametrize("kinds,ppu,socket", [
    (("PPU_SITE",), True, False),
    (("SOCKET_ADAPTER",), False, True),
    (("PPU_SITE", "SOCKET_ADAPTER"), True, True),
])
def test_l3_routes_independently_promote_exact_icpn_once(kinds, ppu, socket):
    physical = PhysicalCompatibilityRegistry([_synthetic(kind) for kind in kinds])
    registry = ProgrammingQualificationRegistry(
        _fake_catalog(), (_FakeProvider(),), physical_compatibility=physical,
    )
    record = registry.describe("ExampleVendor", "EXAMPLE123")
    assert record["state"] == "SUPPORTED"
    assert record["catalog_level"] == 3
    assert record["catalog_level_state"] == "PLASMA_VERIFIED"
    assert record["ppu_ready"] is ppu
    assert record["socket_ready"] is socket
    assert len(record["verified_configurations"]) == len(kinds)
    assert registry.summary["catalog_level_counts"]["3"] == 1
    assert registry.summary["catalog_level_counts"]["2"] == 0
    assert record["execution_authorized"] is False


def test_l3_cannot_promote_without_supported_l2_or_admitted_identity():
    physical = PhysicalCompatibilityRegistry([_synthetic("PPU_SITE")])
    with pytest.raises(DeviceCatalogIntegrityError, match="requires SUPPORTED L2 provider"):
        ProgrammingQualificationRegistry(
            _fake_catalog(), (_FakeProvider("BLOCKED"),), physical_compatibility=physical,
        )
    with pytest.raises(DeviceCatalogIntegrityError, match="lacks admitted exact ICPN"):
        ProgrammingQualificationRegistry(
            DeviceCatalog(()), (), physical_compatibility=physical,
        )


def test_direct_wire_never_claims_unbuilt_socket():
    record = _synthetic("PPU_SITE")
    record["socket"] = {"model": "unbuilt", "revision": "v0"}
    with pytest.raises(DeviceCatalogIntegrityError, match="must not claim a Socket"):
        PhysicalCompatibilityRegistry([record])


def test_independent_voltage_current_measurement_and_harness_revision_are_optional():
    record = deepcopy(get_default_physical_compatibility_registry().verified_for(
        "STMicroelectronics", "STM32F103C8T6"
    )[0])
    record.pop("electrical_measurement")
    record.pop("physical_wiring_revision")
    physical = PhysicalCompatibilityRegistry(
        [record], root=Path(__file__).resolve().parents[3],
    )
    assert physical.verified_for("STMicroelectronics", "STM32F103C8T6")[0]["result"] == "PASSED"

    synthetic = _synthetic("PPU_SITE")
    synthetic.pop("electrical_measurement")
    synthetic.pop("physical_wiring_revision")
    registry = ProgrammingQualificationRegistry(
        _fake_catalog(), (_FakeProvider(),),
        physical_compatibility=PhysicalCompatibilityRegistry([synthetic]),
    )
    assert registry.describe("ExampleVendor", "EXAMPLE123")["catalog_level"] == 3


def test_socket_fixture_requires_model_and_revision():
    record = _synthetic("SOCKET_ADAPTER")
    record["socket"]["revision"] = ""
    with pytest.raises(DeviceCatalogIntegrityError, match="versioned fixture"):
        PhysicalCompatibilityRegistry([record])


def test_direct_wire_physical_receipt_cannot_be_relabelled_socket_ready():
    record = deepcopy(get_default_physical_compatibility_registry().verified_for(
        "STMicroelectronics", "STM32F103C8T6"
    )[0])
    record["verification_type"] = "SOCKET_ADAPTER"
    record["connection_mode"] = "SOCKET_ADAPTER"
    record["socket"] = {"model": "hypothetical-unbuilt-socket", "revision": "test-v1"}
    with pytest.raises(DeviceCatalogIntegrityError, match="Socket fixture identity"):
        PhysicalCompatibilityRegistry([record], root=Path(__file__).resolve().parents[3])


def test_default_l3_receipts_are_hashed_and_replay_checked():
    physical = get_default_physical_compatibility_registry()
    records = physical.verified_for("STMicroelectronics", "STM32F103C8T6")
    assert len(records) == 1
    record = records[0]
    assert record["verification_type"] == "PPU_SITE"
    assert record["connection_mode"] == "DIRECT_WIRE"
    assert record["socket"] is None
    assert record["ppu_site"]["site_id"] == 2
    assert record["electrical_measurement"] == "NOT_TESTED"
    assert record["physical_wiring_revision"] == "NOT_RECORDED"
    assert len(record["evidence"]) == 2

    repo = Path(__file__).resolve().parents[3]
    damaged = deepcopy(record)
    damaged["evidence"][0]["sha256"] = "0" * 64
    with pytest.raises(DeviceCatalogIntegrityError, match="receipt identity, readback"):
        PhysicalCompatibilityRegistry([damaged], root=repo)

    wrong_device = deepcopy(record)
    wrong_device["ppu_site"]["device_id"] = "ppu-device-incorrect"
    with pytest.raises(DeviceCatalogIntegrityError, match="PPU Bootstrap identity/runtime"):
        PhysicalCompatibilityRegistry([wrong_device], root=repo)


def test_l3_rejects_readback_or_safe_off_spoof_even_with_matching_digest(tmp_path):
    repo = Path(__file__).resolve().parents[3]
    record = deepcopy(get_default_physical_compatibility_registry().verified_for(
        "STMicroelectronics", "STM32F103C8T6"
    )[0])
    source = repo / record["evidence"][0]["path"]
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["job"]["result"]["details"]["flash_cycle"]["safe_off"] = False
    destination = tmp_path / "docs" / "evidence" / "modified.json"
    destination.parent.mkdir(parents=True)
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    destination.write_bytes(raw)
    for prefix in ("manager_journal", "bootstrap_status"):
        rel = record["provenance"][prefix]
        copy_to = tmp_path / rel
        copy_to.parent.mkdir(parents=True, exist_ok=True)
        copy_to.write_bytes((repo / rel).read_bytes())
    record["evidence"] = [{"path": "docs/evidence/modified.json", "sha256": hashlib.sha256(raw).hexdigest()}]
    with pytest.raises(DeviceCatalogIntegrityError, match="receipt identity, readback"):
        PhysicalCompatibilityRegistry([record], root=tmp_path)
