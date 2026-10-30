# PPU Local Trust Root — Security Architecture Contract (Gate 1A)

**Status:** Owner-approved architecture, 2026-10-30. Contract and Host-only model only; no production credentials, TLS service or generic admission. Baseline main `a22c9cb04a9ea1361a39d2504fc83f510898390e`, PR #1214 `3d6e52c92916b7f0e6b27246550ae2a154365f87`, Draft PR #1215 `bd580d858b9fbb9c1513b1b67563439aedef470f`.

## Trust and responsibility boundaries

| Owner | Required contract |
| --- | --- |
| Factory | Under a protected physical process, assign a unique immutable PPU device ID, create initial device key and trust anchors, record provenance and recovery inventory. Private keys never enter Git, packages, API receipts or client logs. |
| PPU HTTPS endpoint | Present a certificate whose device identity matches the selected PPU; validate client credential and local revocation state before accepting a deployment intent. TLS failure or untrusted/expired server identity is a client hard failure. No HTTP downgrade. |
| Local principal store | Maintain Master principal ID, monotonic generation, credential validity, role/purpose/target/publisher scope and revocation. The PPU derives identity from verified credentials, not JSON claims, client name or Engineering Mode. Commissioning Bearer is not a deployment credential. |
| Publisher trust store | Verify a versioned detached signature over a canonical package envelope containing package bytes digest, source identity, purpose, target profile, publisher/key ID and format version. Verify the public key chain and revocation independently of the operator. SHA256 alone authenticates no publisher. |
| DeploymentCoordinator | Reuse the one Bootstrap API, lock and journal. Admission must atomically reserve durable transaction ID and nonce under current policy before queueing. Activation separately requires the scheduler fence and hardware quiescence. |
| Recovery authority | Factory/Engineer protected local procedure with physical ownership, separate credential and audit; never a normal Deployment API route. |

The device must operate offline after factory provisioning. No central availability assumption may weaken revocation or policy checks. A locally unknown, corrupt or stale trust snapshot denies new deployment. The PPU may continue already safe programming according to its independent runtime policy; uncertain deployment recovery keeps activation blocked.

## Two independent trust chains

1. **Operator chain:** authenticate client principal with a PPU-trusted credential, bind it to the request transaction ID and nonce, check expiry/revocation and exact current Master generation, then check permission for the purpose, publisher and target. An operator may not self-declare a role or substitute a commissioning token.
2. **Publisher chain:** verify a trusted publisher key and signature over the exact immutable envelope; check key validity/revocation, declared source commit/repository provenance, package digest, purpose and target. A valid operator cannot authorize unsigned bytes; a signed package cannot authorize an unprivileged operator.

The package SHA256 and per-file hashes remain integrity checks. Source claims are authenticated only when covered by the publisher signature and matched to an independently trusted publisher/source policy. Target compatibility comes from PPU-owned target identity, never solely the ZIP manifest or client request. Signature algorithm, canonical encoding, certificate profile and key storage backend require Gate 1B implementation review; Gate 1A does not invent a production credential format.

## Atomicity, replay and crash handling

The PPU stores a monotonic policy generation, principal generations, key revocations, used transaction IDs/nonces and deployment journal in protected local persistent storage. A single serialized transaction validates the current policy and atomically records the `(transaction_id, nonce, package_digest, policy_generation, principal_generation)` reservation before a job can be queued. Duplicate ID or nonce, even with altered bytes, is denied. A retry may query an existing receipt by transaction ID after authenticated identity/ownership checking; it cannot silently create another deployment. Nonces must be unpredictable and bounded; the production retention/garbage-collection rule must preserve replay safety across reboot, rollback and clock changes.

Policy update and rotation are atomic generation changes: validate new trust material, commit it durably, then expose it. Old credentials are rejected immediately after the committed generation changes; revocation cannot be rolled back by a software deployment. On write failure, conflicting workers, lost lock, ambiguous fsync/rename outcome, corrupt store, time uncertainty or restart before authoritative readback, enter `UNKNOWN`/`RECOVERY_REQUIRED` and deny new admission. Recovery reads a verified durable snapshot and journal before deciding whether the request was committed, queued or activated. A cached success result is not authority.

## Threat model and required denials

| Threat / fault | Required behavior |
| --- | --- |
| Forged SWPC/Engineering flag, unauthenticated client, stolen/expired/revoked credential or stale Master generation | Deny before queue; no privilege from client claims. |
| Signed package from wrong publisher/source, altered bytes or wrong target/purpose | Deny even if operator is valid. |
| Valid package but unprivileged operator | Deny even if publisher signature is valid. |
| TLS interception, wrong PPU certificate or compromised client trust anchor | Client rejects connection; PPU never treats HTTP/Bearer as production admission. |
| Replayed transaction/nonce, concurrent duplicate requests, stale policy cache | Serialize against durable current state; deny duplicate or unknown result. |
| Store corruption, failed write, power loss, rollback, missing revocation read | Fail closed; protected local recovery and audit before new admission. |
| General client attempts trust reset or arbitrary Root command | No such API; protected Factory Recovery only. |

Credential rotation and factory recovery need audited procedures, protected storage ownership, key custody, clock policy and an explicit operator break-glass decision. Those are Gate 1B design inputs, not present capabilities. Hardware tamper resistance is not claimed by a local software store; physical compromise is outside this Host-only contract and needs separate product threat assessment.

## Existing boundary and Gate 1B minimum WBS

1. Define and review factory device identity, client/publisher credential formats, signature canonicalization, trust storage ownership, secure time and protected recovery runbook; provision no real keys in Gate 1A.
2. Add HTTPS server identity and client authentication to the existing Bootstrap service, with no insecure fallback; validate the local principal/Master generation/revocation and independent publisher chain before generic enqueue.
3. Add one durable serialized policy/replay reservation and crash reconciliation to the existing Bootstrap/DeploymentCoordinator journal path; prove multi-process and reboot failure injection.
4. Connect the existing SiteManager scheduler to the one Coordinator via a persistent admission fence and real eight-Site/hardware quiescence authority, then bounded generic activation/rollback through the existing installer and Root Guard.
5. Run GitHub-hosted positive/negative API, TLS, replay and failure tests, then separately authorized PPU/HIL and recovery qualification. Keep Draft PR #1215's deployment-client architecture separate; resolve `docs/README.md` on merge and do not change programming Web/BFF ownership implicitly.

## Gate 1A evidence and Gate 2 matrix

| Capability | Status | Evidence / remaining acceptance |
| --- | --- | --- |
| Local trust-root architecture, two chains, offline and recovery boundary | **PASS — contract** | This document and [ADR-0004](../adr/0004-ppu-local-trust-root-deployment-security.md). |
| Fail-closed policy transition and replay model | **PASS — Host-only model** | `plasma_core/ppu_local_trust_contract.py` and `test_ppu_local_trust_contract.py`; inputs are synthetic preverified facts, no production signature or durable store. |
| Production TLS, credentials, publisher verification, durable revocation/replay | **BLOCKED** | Gate 1B WBS 1–3; current `scripts/ppu-bootstrap-service.py` is commissioning HTTP and denies generic. |
| Production scheduler fence, generic activation, FPGA/HIL recovery | **BLOCKED** | Gate 1B WBS 4–5 and separate hardware Gate; mocks/Host-only tests do not qualify physical state. |
| PR #1214 Host-only Gate 2 readiness | **BLOCKED** | Preserve Draft until independent production integration and review. |

Gate 1A tests validate policy *decisions*, not credential cryptography, TLS, disk atomicity, PPU runtime or hardware. The current Bootstrap generic request path must remain fail-closed.
