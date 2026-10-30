"""Host-only local trust policy contract; never an authentication adapter.

Evidence arguments are TEST-SUPPLIED facts. This module does not verify TLS,
signatures, credentials, or durable storage and must not be wired into the
Bootstrap service as an admission callback. Gate 1B must supply those checks.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


class TrustDenied(ValueError):
    """A policy decision cannot authorize deployment."""


@dataclass(frozen=True)
class Principal:
    principal_id: str
    generation: int
    purposes: frozenset[str]
    publishers: frozenset[str]
    targets: frozenset[str]
    expires_at: int


@dataclass(frozen=True)
class Publisher:
    publisher_id: str
    key_id: str
    purposes: frozenset[str]
    sources: frozenset[str]
    targets: frozenset[str]
    expires_at: int


@dataclass(frozen=True)
class TrustState:
    device_id: str
    policy_generation: int
    principals: tuple[Principal, ...]
    publishers: tuple[Publisher, ...]
    revoked_principals: frozenset[str] = frozenset()
    revoked_publisher_keys: frozenset[str] = frozenset()
    consumed_ids: frozenset[str] = frozenset()
    known: bool = True


@dataclass(frozen=True)
class DeploymentIntent:
    device_id: str
    transaction_id: str
    nonce: str
    principal_id: str
    publisher_id: str
    purpose: str
    source: str
    digest: str
    target: str


@dataclass(frozen=True)
class OperatorEvidence:
    """Test fact representing separate client credential verification."""

    verified: bool
    principal_id: str
    generation: int
    bound_transaction_id: str
    bound_nonce: str


@dataclass(frozen=True)
class PublisherEvidence:
    """Test fact representing signature verification over the exact intent."""

    verified: bool
    publisher_id: str
    key_id: str
    bound_source: str
    bound_digest: str
    bound_target: str
    bound_purpose: str


def authorize_host_only(
    state: TrustState,
    intent: DeploymentIntent,
    operator: OperatorEvidence | None,
    publisher_proof: PublisherEvidence | None,
    *,
    now: int,
) -> TrustState:
    """Return the next policy/replay snapshot; caller must commit it before queueing.

    This pure transition is only a Host-only policy model. It does not make an
    authorization decision for a real request without independently verified
    evidence and an atomic durable compare-and-swap implementation.
    """
    if not state.known or state.policy_generation < 1 or not state.device_id:
        raise TrustDenied("unknown trust or revocation state")
    if intent.device_id != state.device_id or not intent.target:
        raise TrustDenied("wrong device or target")
    if not intent.transaction_id or not intent.nonce:
        raise TrustDenied("missing replay identity")
    if intent.transaction_id in state.consumed_ids or intent.nonce in state.consumed_ids:
        raise TrustDenied("replayed transaction or nonce")
    if len(intent.digest) != 64 or any(c not in "0123456789abcdef" for c in intent.digest):
        raise TrustDenied("invalid digest")
    if operator is None or not operator.verified:
        raise TrustDenied("unverified operator")
    if publisher_proof is None or not publisher_proof.verified:
        raise TrustDenied("unverified publisher")
    principals = [p for p in state.principals if p.principal_id == intent.principal_id]
    publishers = [p for p in state.publishers if p.publisher_id == intent.publisher_id]
    if len(principals) != 1 or len(publishers) != 1:
        raise TrustDenied("unknown or ambiguous identity")
    principal, publisher = principals[0], publishers[0]
    if (principal.principal_id in state.revoked_principals
            or publisher.key_id in state.revoked_publisher_keys):
        raise TrustDenied("revoked identity")
    if now >= principal.expires_at or now >= publisher.expires_at:
        raise TrustDenied("expired credential")
    if (operator.principal_id != principal.principal_id
            or operator.generation != principal.generation
            or operator.bound_transaction_id != intent.transaction_id
            or operator.bound_nonce != intent.nonce):
        raise TrustDenied("operator identity or generation mismatch")
    if (publisher_proof.publisher_id != publisher.publisher_id
            or publisher_proof.key_id != publisher.key_id
            or publisher_proof.bound_source != intent.source
            or publisher_proof.bound_digest != intent.digest
            or publisher_proof.bound_target != intent.target
            or publisher_proof.bound_purpose != intent.purpose):
        raise TrustDenied("publisher signature binding mismatch")
    if (intent.purpose not in principal.purposes
            or intent.publisher_id not in principal.publishers
            or intent.target not in principal.targets
            or intent.purpose not in publisher.purposes
            or intent.source not in publisher.sources
            or intent.target not in publisher.targets):
        raise TrustDenied("policy denies deployment")
    return replace(state, consumed_ids=state.consumed_ids | {
        intent.transaction_id, intent.nonce,
    })
