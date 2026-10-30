"""Host-only policy transitions with synthetic, preverified evidence."""
from dataclasses import replace

import pytest

from plasma_core.ppu_local_trust_contract import (
    DeploymentIntent, OperatorEvidence, Principal, Publisher,
    PublisherEvidence, TrustDenied, TrustState, authorize_host_only,
)


def case():
    digest = "a" * 64
    state = TrustState(
        device_id="ppu-1", policy_generation=3,
        principals=(Principal("master-1", 7, frozenset({"deploy"}),
                              frozenset({"pub-1"}), frozenset({"z2"}), 200),),
        publishers=(Publisher("pub-1", "key-2", frozenset({"deploy"}),
                              frozenset({"source-1"}), frozenset({"z2"}), 200),),
    )
    intent = DeploymentIntent("ppu-1", "tx-1", "nonce-1", "master-1", "pub-1",
                              "deploy", "source-1", digest, "z2")
    operator = OperatorEvidence(True, "master-1", 7, "tx-1", "nonce-1")
    publisher = PublisherEvidence(True, "pub-1", "key-2", "source-1", digest,
                                  "z2", "deploy")
    return state, intent, operator, publisher


def decide(state, intent, operator, publisher):
    return authorize_host_only(state, intent, operator, publisher, now=100)


def test_success_consumes_both_replay_identifiers_before_queue():
    state, intent, operator, publisher = case()
    next_state = decide(state, intent, operator, publisher)
    assert next_state.consumed_ids == frozenset({"tx-1", "nonce-1"})
    assert state.consumed_ids == frozenset()
    with pytest.raises(TrustDenied, match="replayed"):
        decide(next_state, intent, operator, publisher)
    with pytest.raises(TrustDenied, match="replayed"):
        decide(next_state, replace(intent, transaction_id="tx-2"),
               replace(operator, bound_transaction_id="tx-2"), publisher)


@pytest.mark.parametrize("change,reason", [
    ({"operator": None}, "unverified operator"),
    ({"operator": "unverified"}, "unverified operator"),
    ({"publisher": None}, "unverified publisher"),
    ({"publisher": "unverified"}, "unverified publisher"),
    ({"state": "unknown"}, "unknown trust"),
    ({"state": "revoked_principal"}, "revoked"),
    ({"state": "revoked_publisher"}, "revoked"),
    ({"state": "expired_principal"}, "expired"),
    ({"state": "expired_publisher"}, "expired"),
    ({"operator": "old_generation"}, "generation mismatch"),
    ({"operator": "wrong_principal"}, "identity"),
    ({"publisher": "old_key"}, "signature binding"),
    ({"intent": "wrong_device"}, "wrong device"),
    ({"intent": "wrong_target"}, "signature binding"),
    ({"intent": "wrong_source"}, "signature binding"),
    ({"intent": "wrong_digest"}, "signature binding"),
    ({"intent": "bad_digest"}, "invalid digest"),
    ({"intent": "wrong_purpose"}, "signature binding"),
    ({"intent": "missing_nonce"}, "missing replay"),
    ({"state": "corrupt_generation"}, "unknown trust"),
    ({"state": "publisher_scope"}, "policy denies"),
    ({"state": "principal_scope"}, "policy denies"),
])
def test_denials(change, reason):
    state, intent, operator, publisher = case()
    if change.get("operator") is None and "operator" in change:
        operator = None
    elif change.get("operator") == "unverified":
        operator = replace(operator, verified=False)
    elif change.get("operator") == "old_generation":
        operator = replace(operator, generation=6)
    elif change.get("operator") == "wrong_principal":
        operator = replace(operator, principal_id="forged")
    if change.get("publisher") is None and "publisher" in change:
        publisher = None
    elif change.get("publisher") == "unverified":
        publisher = replace(publisher, verified=False)
    elif change.get("publisher") == "old_key":
        publisher = replace(publisher, key_id="key-1")
    if change.get("intent") == "wrong_device":
        intent = replace(intent, device_id="ppu-2")
    elif change.get("intent") == "wrong_target":
        intent = replace(intent, target="other")
    elif change.get("intent") == "wrong_source":
        intent = replace(intent, source="untrusted")
    elif change.get("intent") == "wrong_digest":
        intent = replace(intent, digest="b" * 64)
    elif change.get("intent") == "bad_digest":
        intent = replace(intent, digest="not-a-sha")
    elif change.get("intent") == "wrong_purpose":
        intent = replace(intent, purpose="maintenance")
    elif change.get("intent") == "missing_nonce":
        intent = replace(intent, nonce="")
    if change.get("state") == "unknown":
        state = replace(state, known=False)
    elif change.get("state") == "revoked_principal":
        state = replace(state, revoked_principals=frozenset({"master-1"}))
    elif change.get("state") == "revoked_publisher":
        state = replace(state, revoked_publisher_keys=frozenset({"key-2"}))
    elif change.get("state") == "expired_principal":
        state = replace(state, principals=(replace(state.principals[0], expires_at=100),))
    elif change.get("state") == "expired_publisher":
        state = replace(state, publishers=(replace(state.publishers[0], expires_at=100),))
    elif change.get("state") == "corrupt_generation":
        state = replace(state, policy_generation=0)
    elif change.get("state") == "publisher_scope":
        state = replace(state, publishers=(replace(state.publishers[0], sources=frozenset()),))
    elif change.get("state") == "principal_scope":
        state = replace(state, principals=(replace(state.principals[0], purposes=frozenset()),))
    with pytest.raises(TrustDenied, match=reason):
        decide(state, intent, operator, publisher)


def test_rotation_and_revocation_invalidate_old_evidence():
    state, intent, operator, publisher = case()
    rotated = replace(state,
                      principals=(replace(state.principals[0], generation=8),),
                      publishers=(replace(state.publishers[0], key_id="key-3"),),
                      revoked_publisher_keys=frozenset({"key-2"}),
                      policy_generation=4)
    with pytest.raises(TrustDenied):
        decide(rotated, intent, operator, publisher)
    fresh = replace(publisher, key_id="key-3")
    assert decide(rotated, intent, replace(operator, generation=8), fresh).policy_generation == 4


def test_either_trust_chain_cannot_substitute_for_the_other():
    state, intent, operator, publisher = case()
    with pytest.raises(TrustDenied, match="unverified publisher"):
        decide(state, intent, operator, None)
    with pytest.raises(TrustDenied, match="unverified operator"):
        decide(state, intent, None, publisher)
    signed_unapproved = replace(intent, publisher_id="pub-2")
    matching_signature_fact = replace(publisher, publisher_id="pub-2")
    with pytest.raises(TrustDenied, match="unknown or ambiguous identity"):
        decide(state, signed_unapproved, operator, matching_signature_fact)


def test_unknown_commit_outcome_must_not_be_retried_or_queued():
    state, intent, operator, publisher = case()
    proposed = decide(state, intent, operator, publisher)
    assert proposed.consumed_ids
    # After a crash with no authoritative readback, policy state is UNKNOWN.
    with pytest.raises(TrustDenied, match="unknown trust"):
        decide(replace(state, known=False), intent, operator, publisher)
