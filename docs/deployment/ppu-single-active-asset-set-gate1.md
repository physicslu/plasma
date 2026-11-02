# PPU Single Active Asset Set — P1 Gate 1

**State:** Draft implementation, Host-only / CI evidence only.
**Dependencies:** [PR #1245](https://github.com/physicslu/plasma/pull/1245)
(Generic Bundle B3 Install/Verify), plus the owner-approved architectural
decision in [PR #1244](https://github.com/physicslu/plasma/pull/1244).
This P1 PR is stacked on #1245, **not** yet merged into main.

## One Asset Set identity

For the current PPU Bundle v3 implementation, the **complete Bundle ZIP
SHA256** is the canonical Asset Set identity. This binds the exact ZIP
bytes, Manifest, Package versions and file hashes. It is distinct from
the target Firmware SHA, Normalized Image SHA, FPGA BIN SHA and any
individual Package SHA. It is a *content identity*, not a publisher
signature, Master approval or device authorization.

- B3 stores a complete verified Set under
  \`/opt/plasma/assets/staged/<bundle-archive-sha256>/\`.
- Only one active identity is published in
  \`/opt/plasma/assets/active.json\` (root-owned file, atomic replace).
- The Active record binds one immutable staged Set. There may be multiple
  **Staged** Sets but only one **Active** Set. Staging is not Activation.
- \`GET /v1/assets\` gives an independently verified \`EMPTY\` or \`ACTIVE\`
  identity and a **READY=false** result. Corrupt active content causes
  failure/unknown, never a false SHA match.
- Console \`reconcile_bundle_assets(full_bundle_bytes)\` fetches the
  PPU Active identity: if the digest matches it returns \`ALREADY_ACTIVE\`
  without upload; otherwise uploads the **whole Bundle** through B1,
  obtains B2, and explicitly requests B3 Install-only. It returns
  \`B3_INSTALL_QUEUED\`, **not** \`ACTIVE\` or \`READY\`.
- B3 still verifies every Package and installs without changing the
  Active pointer, rebooting a service, running a Python Parser, loading
  an FPGA or touching a DUT.

## Activation and Job quiescence — intentionally fail closed on Z2

The *existing* DeploymentCoordinator \`deployment.lock\` and
\`deployment.json\` Journal serialize and record a P1 activation
transaction. \`activate_staged_asset_set()\` independently verifies
the entire installed Asset Set before switching, and makes the pointer
visible through a single atomic \`os.replace()\` plus fsync.

**A held trusted exclusive Runtime/Job quiescence lease is mandatory.**
It must prevent new Jobs from being admitted and ensure all queued,
running and cancelling Site Jobs and relevant PS/PL hardware users have
released ownership **for the entire activation**. A Console-provided
\`idle=true\`, a status snapshot or a public token is NOT proof.

The current SiteManager's execution lease and RuntimeQuiesceGate are
process-local and are **not yet a verified cross-process Bootstrap guard**.
Therefore real PPU/HTTP activation is **NOT QUALIFIED / NOT EXPOSED**.
The Coordinator method requires an injected **trusted context manager**
and denies without one. Host-only tests inject a controlled lease to
verify the state transition and busy/failure logic. This does **not**
qualify loading an FPGA or changing resources while real Jobs exist.

The last verified Active Set is not deleted or overwritten when B3
stages a new Set; failed validation or quiescence refuses the new Set.
Uncertain outcomes after an attempted pointer write require recovery
through the same existing Coordinator journal rather than blind retry.

**ACTIVE is not READY**. A separate Controller-directed FPGA
Configuration and full Programming Profile/ICPN/hardware qualification
remain P2. The Active SHA must never be treated as proof that the
selected FPGA Image is physically loaded or that a DUT is programmable.

## Non-goals and next evidence

This PR does not add a new server/daemon/installer, multi-version Package
Resolver, FPGA Loader, proprietary staging path, public B4 activation
API, production publisher authentication, live PPU cross-process
quiescence, Job execution or Z2 HIL results.

Before a real PPU activation can be enabled, integrate and demonstrate
an authoritative cross-process Job ownership/quiescence lease held by
**all programming entrypoints** and the exclusive Configuration/
Activation owner. Demonstrate interruption, restore/recovery, Site
concurrency and hardware isolation under separate authorized scope.
