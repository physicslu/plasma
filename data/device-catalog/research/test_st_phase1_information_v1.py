from __future__ import annotations

import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "st_phase1_information_v1.py"
SPEC = importlib.util.spec_from_file_location("st_phase1_information_v1", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def exact(records, icpn):
    return next(row for row in records if row["icpn"] == icpn)


def test_st_phase1_baseline_reconciles_full_production_and_field_denominators():
    records, summary = MODULE.build()

    assert len(records) == 4629
    assert summary["exact_icpn_count"] == 4629
    assert summary["existing_source_backed_basic_bindings"] == 1622
    assert summary["legacy_m1_blocked_exact_icpns"] == 3007

    for field in MODULE.FIELDS:
        states = summary["field_coverage"][field]
        assert set(states) == set(MODULE.STATES)
        assert sum(states.values()) == 4629

    # Existing M1 evidence becomes field-level evidence, not a package gate.
    assert summary["field_coverage"]["ram"]["VERIFIED"] == 1622
    assert summary["field_coverage"]["working_vdd"]["VERIFIED"] == 1622
    assert summary["field_coverage"]["ram"]["UNKNOWN"] == 3007
    assert summary["field_coverage"]["working_vdd"]["UNKNOWN"] == 3007

    # Exact Production identity fields remain independently useful for all ST rows.
    for field in ("manufacturer", "icpn", "base_device", "package", "pin_count", "flash", "temperature"):
        assert summary["field_coverage"][field]["VERIFIED"] == 4629


def test_st_phase1_preserves_known_fields_when_other_fields_are_unknown():
    records, _summary = MODULE.build()

    f407 = exact(records, "STM32F407VGT6")
    assert f407["fields"]["flash"]["value"] == "1024 KiB"
    assert f407["fields"]["flash"]["state"] == "VERIFIED"
    assert f407["fields"]["ram"]["state"] == "UNKNOWN"
    assert f407["fields"]["working_vdd"]["state"] == "UNKNOWN"
    assert f407["legacy_m1_context"]["disposition"] == "blocked_evidence_gap"

    # H5's conditional temperature text was a legacy M1 model blocker. Phase 1 preserves
    # the original manufacturer wording instead of flattening or discarding the field.
    h5 = exact(records, "STM32H503CBT7")
    assert h5["fields"]["temperature"]["state"] == "VERIFIED"
    assert "up to 125 at low dissipation" in h5["fields"]["temperature"]["value"]
    assert h5["fields"]["ram"]["state"] == "UNKNOWN"


def test_st_phase1_projects_existing_source_backed_ram_vdd_without_programming_claims():
    records, _summary = MODULE.build()

    f103 = exact(records, "STM32F103C8T6")
    assert f103["fields"]["ram"]["value"] == "20 KiB"
    assert f103["fields"]["ram"]["state"] == "VERIFIED"
    assert f103["fields"]["working_vdd"]["value"] == {"min": 2, "max": 3.6}
    assert f103["fields"]["working_vdd"]["state"] == "VERIFIED"

    for row in records:
        assert row["phase"] == "IC_INFORMATION"
        assert row["non_claims"]["production_admission_changed"] is False
        assert row["non_claims"]["openocd_software_supported"] is False
        assert row["non_claims"]["programming_profile_authority"] is False
        assert row["non_claims"]["external_vpp_evaluated"] is False
        assert row["non_claims"]["hardware_runtime_ready"] is False
        assert row["non_claims"]["physical_programming_qualified"] is False
        assert "vpp" not in row["fields"]
