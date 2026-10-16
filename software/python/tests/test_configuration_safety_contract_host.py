"""Only synthetic Phase 2A.2 data is exercised: never touch devices or Z2."""
from dataclasses import replace
import pytest

from plasma_interfaces.configuration_safety_contract import (
    ConfigurationPin, OwnershipEvidence, IsolationEvidence, RetirementEvidence,
    VerificationEvidence, ContractRejected, validate_synthetic_transition,
)


@pytest.fixture
def evidence():
    p = ConfigurationPin("boot-a", "a" * 40, "dt-a", "b" * 64, "c" * 64, 3, "epoch-a")
    return (
        p,
        OwnershipEvidence(p, True, True, True, True, True, True, True),
        IsolationEvidence(p, True, True, True, True),
        RetirementEvidence(p, True, True, True),
        VerificationEvidence(p, True, True, True, True),
    )


def test_synthetic_success_has_no_hardware_capability(evidence):
    receipt = validate_synthetic_transition(*evidence)
    assert receipt.next_generation == 4
    assert receipt.host_only is True
    assert receipt.grants_hardware_authority is False


@pytest.mark.parametrize("index,field", [
    (1, "admission_sealed"), (1, "no_site_leases"),
    (1, "all_processes_enumerated"), (1, "no_retained_vmas"),
    (1, "no_kernel_consumers"), (1, "no_dma_masters"),
    (1, "no_external_mmio_owners"), (2, "safe_io_verified"),
    (2, "axi_transactions_drained"), (2, "axi_isolation_verified"),
    (2, "external_recovery_available"), (3, "old_mapping_retired"),
    (3, "no_live_handles"), (3, "no_outstanding_site_io"),
    (4, "exact_candidate_verified"), (4, "resources_verified"),
    (4, "independent_health_verified"), (4, "recovery_receipt_verified"),
])
@pytest.mark.parametrize("value", [False, None, 1])
def test_every_missing_unknown_or_nonboolean_gate_rejected(evidence, index, field, value):
    items = list(evidence)
    items[index] = replace(items[index], **{field: value})
    with pytest.raises(ContractRejected):
        validate_synthetic_transition(*items)


@pytest.mark.parametrize("index", [1, 2, 3, 4])
def test_stale_pin_rejected_at_every_gate(evidence, index):
    items = list(evidence)
    items[index] = replace(items[index], pin=replace(evidence[0], owner_epoch="other-owner"))
    with pytest.raises(ContractRejected, match="pin mismatch"):
        validate_synthetic_transition(*items)


@pytest.mark.parametrize("index", [1, 2, 3, 4])
def test_unknown_evidence_kind_rejected(evidence, index):
    items = list(evidence)
    items[index] = replace(items[index], kind="LIVE")
    with pytest.raises(ContractRejected):
        validate_synthetic_transition(*items)


def test_bad_pin_identity_or_generation_rejected():
    with pytest.raises(ContractRejected):
        ConfigurationPin("boot", "a" * 40, "dt", "b" * 64, "c" * 64, 0, "epoch")
    with pytest.raises(ContractRejected):
        ConfigurationPin("boot", "a" * 40, "dt", "b" * 64, "c" * 64, True, "epoch")
    with pytest.raises(ContractRejected):
        ConfigurationPin("boot", "a" * 40, "dt", "b" * 64, "c" * 64, 1, " ")


def test_no_physical_io_api_exposed():
    import plasma_interfaces.configuration_safety_contract as contract
    for name in ("load_bitstream", "open_uio", "rebind_driver", "write_mmio",
                 "authorize_hardware", "recover_device"):
        assert not hasattr(contract, name)


@pytest.mark.parametrize("field,invalid", [
    ("source_sha", "not-a-sha"), ("source_sha", "A" * 40),
    ("source_sha", "a" * 39), ("source_sha", "g" * 40),
    ("old_image_sha256", "b" * 63), ("old_image_sha256", "B" * 64),
    ("candidate_sha256", "c" * 65), ("candidate_sha256", "g" * 64),
])
def test_synthetic_digest_must_have_canonical_hex_shape(evidence, field, invalid):
    with pytest.raises(ContractRejected):
        replace(evidence[0], **{field: invalid})


@pytest.mark.parametrize("field", [
    "boot_id", "source_sha", "resource_id", "old_image_sha256",
    "candidate_sha256", "mapping_generation", "owner_epoch",
])
def test_each_evidence_pin_field_must_match(evidence, field):
    original = evidence[0]
    other = {
        "boot_id": "other-boot",
        "source_sha": "d" * 40,
        "resource_id": "other-resource",
        "old_image_sha256": "d" * 64,
        "candidate_sha256": "e" * 64,
        "mapping_generation": 4,
        "owner_epoch": "other-epoch",
    }[field]
    altered = replace(evidence[2], pin=replace(original, **{field: other}))
    with pytest.raises(ContractRejected, match="pin mismatch"):
        validate_synthetic_transition(original, evidence[1], altered,
                                      evidence[3], evidence[4])
