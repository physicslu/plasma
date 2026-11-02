# PPU Single Active Asset Set — P1 Gate 1

> **Term note:** in this document **B1/B2/B3/B4 are Bundle stages** — B1 upload/commit, B2 admission, B3 install/verify, B4 activation (incl. previous-version backup). Not the FPGA/UIO or governance meanings; see [glossary](../glossary.md#b1b2b3).

**State:** Host-only implementation merged in main (PR #1246) / CI evidence only.
**Dependencies:** [PR #1245](https://github.com/physicslu/plasma/pull/1245)
(Generic Bundle B3 Install/Verify), plus the owner-approved architectural
decision in [PR #1244](https://github.com/physicslu/plasma/pull/1244).
This P1 work built on #1245; both are merged.

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

## Activation and authoritative cross-process Job Quiescence

The existing `DeploymentCoordinator` owns `deployment.lock` and
`deployment.json` for B3 and Asset Set activation, with one atomic
`assets/active.json` pointer swap and durable `fsync`. This is a
**separate explicit operation**, never an implicit B3 side effect.

The PPU Runtime already has a private Unix control socket
(`/run/plasma-server/control.sock`) and a `SiteManager` execution
lease/Runtime Quiesce gate. P1 extends **this same existing socket**, not
another daemon or path, with a private
`{"operation":"hold_asset_activation"}` request. Its behavior:

1. Under the **same SiteManager execution lock** used when reserving
   queued/running/cancelling Jobs, reject a held lease while any Site Job
   remains active, including cancelled-but-not-terminal work.
2. Grant a **connection-held exclusive Quiesce** if the Runtime can
   authoritatively prove it has no active Jobs. While the socket stays
   connected, new Jobs are rejected even if submitted immediately
   after a zero-active-Jobs snapshot.
3. The Bootstrap's internal Asset Set helper validates the private Unix
   socket and holds the connection for the **entire** Active pointer
   replacement and directory `fsync`; the Runtime frees its gate on
   socket EOF or abrupt client disconnect. An absent/untrusted Runtime,
   busy Job or concurrent legacy runtime-quiesce request fails closed.
4. Runtime's pre-existing **TTL-based server-restart quiesce** remains
   distinct and unchanged. The Asset Set lease is connection-scoped so
   it cannot expire during an incomplete atomic pointer swap.
5. Internal `activate_staged_asset_set()` defaults to using the trusted
   local socket; Host-only tests can inject a controlled lease. No
   Console request field or untrusted ZIP can supply `idle=true`
   or bypass this authority.

**Evidence limit:** The P1 cross-process contract is Host-only tested.
Runtime admission and activation have not yet been validated on a real
Z2, and other out-of-process FPGA Manager/UIO/kernel owners remain
outside this Job-quiescence guarantee. There is still **no public
Console B4/Activation API** and no real PPU activation permission
claimed here. Source installation, service restarts, physical HIL and
full end-to-end recovery remain separate acceptance work.

A failed update leaves the last verified Active Set unchanged; an
uncertain pointer write enters the existing Coordinator recovery state.
The existing Active content remains immutable while a new Set is staged.

**ACTIVE is not READY**. FPGA Configuration, exact Profile/ICPN and
PS/PL hardware ownership checks remain a distinct P2 task. Even a
successful P1 Asset Set SHA match is not evidence that the FPGA is loaded.

## Non-goals and next evidence

This PR does not add a new server/daemon/installer, multi-version Package
Resolver, FPGA Loader, proprietary staging path, public B4 activation
API, production publisher authentication, real Z2 cross-process/HIL
qualification, Job execution or Z2 HIL results.

Before a real PPU activation can be enabled, integrate and demonstrate
an authoritative cross-process Job ownership/quiescence lease held by
**all programming entrypoints** and the exclusive Configuration/
Activation owner. Demonstrate interruption, restore/recovery, Site
concurrency and hardware isolation under separate authorized scope.
