"""Host-only contract tests for archival F1-B owner-one-shot. No Z2/hardware."""
from __future__ import annotations

import pytest

from pl.hil import f1b_owner_once as owner


FACTS = {
    'uio': 'uio1', 'driver': 'uio_pdrv_genirq',
    'maps': [[0x40000000, 0x10000]],
    'runtime': 'suspended', 'irq_counts': [0, 0],
}


def test_exact_owner_snapshot_requires_explicit_ack():
    owner.accept_exact(FACTS, owner.ACK)
    with pytest.raises(RuntimeError, match="risk acknowledgment"):
        owner.accept_exact(FACTS, None)
    with pytest.raises(RuntimeError, match="risk acknowledgment"):
        owner.accept_exact(FACTS, "ANY_OTHER_ACK")


@pytest.mark.parametrize("field,wrong", [
    ("uio", "uio0"),
    ("driver", "another_driver"),
    ("maps", [[0x40000000, 0x20000]]),
    ("runtime", "active"),
    ("irq_counts", [1, 0]),
])
def test_changed_snapshot_denied(field, wrong):
    fact = dict(FACTS, **{field: wrong})
    with pytest.raises(RuntimeError, match="owner exception"):
        owner.accept_exact(fact, owner.ACK)


def test_historical_only_no_generic_auto_transition():
    assert owner.ACK == "F1B_ONE_SHOT_BOUND_PASSIVE_UIO"
    assert owner.CANDIDATE.name == "plasma-f1b-owner-20261020-once.bin"
    assert owner.RECOVERY.name == "base.bin"
