# PPU Unified Deployment PR3 — Path 1 Host-only integration

Status: Gate 1 Candidate; **no device installation, hardware access or rollout**.
Base: main fe3f8896804bad7155cbefd4d3e47baefcc6fc12 (PR #1219, #1221, #1222 merged).

## One Engine, one ingress, two control-plane entry points

- SWPC CLI -> existing Bootstrap /v1/uploads -> /v1/deployments.
- Web Console -> existing same-origin BFF -> Plasma Manager -> existing PPU
  Bootstrap /v1/uploads -> /v1/deployments.
- The Browser never has the PPU Bearer token. Manager already owns device
  pairing, idle-state gate, launch serialization and transport policy. Bundle
  requests are exactly kind=bundle + committed upload_id, without caller claims
  of publisher, Master, target, install permission, script path or root.
- The PPU Bootstrap network API **admits only**, emitting admitted Receipt,
  install_qualified=false and execution_permitted=false. The Manager and
  browser API reject an upstream response pretending that Bundle was installed
  or activated. No new endpoints, SSH writer, installer daemon or second
  Lock/Journal are added.

## Version, dependency, inventory, authorization — host-only contract

Existing plasma.ppu.bundle.v2 specifies component IDs, exact versions,
dependencies and verified files. This PR introduces a deterministic topological
resolver and component content identities from the full descriptor (kind,
version, requires and SHA256/size/executable metadata).

- Every dependency is in the Bundle and pinned to the included component's
  version (the present **closed-bundle** model). Missing/cyclic dependencies
  remain denied. Dynamic installed-component external dependency resolution
  is NOT qualified by this iteration.
- An independently verified, device-owned inventory may allow exact
  content+version+board reuse; otherwise stage. An inventory record claiming
  trust without correct exact fields is rejected. The inventory fixture is
  not constructed from the package or browser.
- The trust-policy simulator requires independently injected exact publisher,
  source_commit, archive SHA256, target, purpose, active Master generation,
  allowed component kinds and expiry. No field in an uploaded ZIP becomes
  authorization. Policy simulation is not a cryptographic publisher signature.
- Actual host-only package Install -> Verify -> Activate -> Rollback is
  exercised by **DeploymentCoordinator.execute_package_host_only** and its
  existing deployment.lock and deployment.json, within a temporary local
  directory. The PR3 wrapper checks policy and resolver before delegating to
  the existing method, and does not own additional lock/state.
- Failure after activation restores the prior active receipt. If restoration
  is unprovable, the existing Journal records recovery_required and blocks
  new writes. This is an isolated transaction simulation, not a service restart
  or an assertion that physical FPGA changes can roll back.
- PR1 legacy package admission and the PS Runtime's existing qualified
  deployment path remain unchanged.

## End-to-end Host-only acceptance

Positive: multi-type Bundle, exact DAG, deterministic order, trusted inventory
reuse, canonical source/target/purpose policy, Manager pairing-bound Bundle
admission, Browser BFF allowlist and bounded chunks, shared receipt and
Host-only activation/rollback.

Negative: missing/revoked/expired Master policy, hash/source/target/purpose
mismatch, unauthorized kinds, untrusted cache or spoofed installed state,
caller-provided authority, malicious upstream receipt, unknown rollback,
ZIP traversal/symlink/tamper, and existing PR1/PR2 regression.

GitHub-hosted Python/PL, Bootstrap, Manager, Web lint/build/tests, Contracts and
applicable QEMU tests are required before Gate 2 readiness. SWPC, Z2, FPGA and
DUT must all remain NOT_RUN.

## Remaining *production* blockers — do not claim real deployment complete

1. A device-verifiable publisher signature and revocable Master authority,
   sealed provenance, authenticated TLS and authorization at dispatch, not
   an operator-supplied JSON policy fixture.
2. Qualified least-privilege installer for executable/data components,
   safe default paths/permissions, service health/readiness, atomic version
   inventory, power-loss recovery and real reconciled API/Coordinator Receipt.
3. Board-specific FPGA image+companion Manifest/HWH, Root Guard/Golden
   lifecycle and cross-Site quiescence; FPGA file admission is not loading.
4. Real SWPC/Web Console -> PPU integration and qualified physical HIL,
   including actual hardware owner, jobs, interlocks and rollback evidence.
5. Retire legacy SSH engineering installation only after explicit proven parity.

**GO for Gate 2 means merge only this bounded Host-only PR3 basis.** It is not
approval for real device installation or activation. No post-merge deployment
is included in this Gate 1.
