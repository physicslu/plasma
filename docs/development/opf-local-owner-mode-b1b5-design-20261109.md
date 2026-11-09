# OPF Local Owner Mode — B1–B5 proposed design and refreshed Gap Audit

> **Status: PROPOSED — pending explicit owner confirmation.** B1–B5 below are the owner's *proposed* direction (2026-11-09). This document is **not** a Gate 1 authorization for P2A-0, P2A-2, P2B, P1, P3 or P4, and nothing here is implemented except where stated as merged on main.
> Normative policy: [ADR-0008](../adr/0008-local-owner-mode.md). Prior audit: [Gate 1 ledger](opf-local-owner-mode-gate1-20261109.md) (§5 = first latest-main refresh). Deployment of the merged P2A-1: [synchronized deployment runbook](../deployment/ppu-lom-p2a1-synchronized-deployment-runbook.md) (**not authorized**).
> Source: `main` `3c2145f3d` (#1371 + #1372 merged). Read-only audit; no SWPC/Z2/FPGA/DUT access.

## 1. State refresh since the §5 audit

| Item | State on `main` 3c2145f3d | Deployed? |
| --- | --- | --- |
| ADR-0008 policy, Gate 1 ledger, Claude handoff | Merged (#1371, `4fd802ac8`) | n/a (docs) |
| **G2** Bearer credential in clear / anonymous device identity | **Fixed in code** by LOM-P2A-1 (#1372): per-request HMAC under a single-use PPU nonce, PPU response MAC, Bearer retired. Hosted CI and post-merge main CI PASS | **No.** Z2 Bootstrap and SWPC Manager still run Bearer. |
| G1 physical presence | Unchanged: no primitive exists | — |
| G3 single credential = owner-HMAC root | Unchanged (by design until P2A-2) | — |
| G4 Manager-local `OUTCOME_UNKNOWN` latch | Unchanged | — |
| G5 Manager loopback not enforced | Unchanged | — |
| G6 duplicated `commissioned` gate | Unchanged | — |
| G7 Render cookie profile | Unchanged | — |
| G8 overlapping drafts | Audited in §4; none closed | — |

New observations in this refresh:

- **G9 — Bootstrap version is not identifiable on the device.** `/v1/status` reports `bootstrap.version = "0.1.0"` with no source SHA (evidence `docs/evidence/console-bundle-programming-hil-2026-11-09/bootstrap-status-after.json`). Rollback and audit therefore depend on a **file-level SHA256 inventory** of `/opt/plasma/bootstrap`, captured before any refresh (runbook step P3). After P2A-1 is deployed, `security.request_authentication` is the observable protocol marker. A later small PR should add the factory bundle identity to status (proposal, not authorized).
- **G10 — `--refresh-only` replaces every Bootstrap script**, not only the authentication files. The deployed Z2 Bootstrap predates several merged changes, so a refresh carries all Bootstrap-layer changes between that unknown version and `3c2145f3d`. The runbook requires a pre-refresh per-file diff reviewed by the owner (runbook step P3/P4).
- **G11 — Path 2 CLI work orders are protocol-coupled.** `plasma_program.py` / `ppu_path2_hardware_baseline.py` run from the dispatcher `--source-sha`. After deployment, any work order pinned to a SHA before `3c2145f3d` fails with 401 (no side effect); during a rollback the converse holds.
- **G12 — Console pairing UI still shows a manual token.** P2A-1 does not change that UX; "no manual credential" may be claimed only after P2A-2 and P1.

## 2. Proposed B1–B5 (pending owner confirmation)

### B1 — Physical presence: SD one-shot enrollment (primary), local serial (development alternative)

Principle: **only a physically bounded, PPU-local action can create or replace the controller trust relationship.** No LAN request, however authenticated by reachability, may trigger unauthenticated takeover.

**Primary — SD boot-partition one-shot enrollment ticket.**

1. Owner powers the PPU off, removes the SD card, and on any computer writes `plasma-enroll.json` to the FAT boot partition (contents: schema, a random 256-bit *enrollment ticket*, a creation note; **no** credential, no device secret). The Control Station may generate the ticket and file for the user to copy; the ticket is not a manufacturer artifact.
2. On the next boot, a PPU-local early unit (root, before network services accept mutations) reads the file **once**, moves it into root-owned state as `pending-enrollment` with a monotonic deadline (proposal: 15 min) and **securely deletes it from the boot partition**. A file appearing on the boot partition at runtime is ignored: only boot-time consumption counts (root can write `/boot`, so runtime writes prove nothing).
3. The Control Station proves possession of the ticket in a bounded enrollment exchange (`plasma.ppu.local-enrollment.v1`, P2A-0 to freeze): PPU nonce → HMAC(ticket, nonce‖device_id‖controller public identity) → PPU generates the new per-PPU credential (B2) and returns it **wrapped** to the ticket-derived key. The ticket is single-use; failure or expiry discards it.
4. The bound ticket never enables reset, rollback, deployment, FPGA load or Site activity. It only authorizes the credential transition in B3.

**Development alternative — local serial CLI.** `ppu-bootstrap-service.py enroll --local-console` (proposal) prints a one-time ticket on the serial console for the same exchange. It counts as physical presence **only** when the UART is attached to a non-networked host. The current Z2 UART is cabled to the SWPC; in that topology serial enrollment is an *engineering* path equivalent to SWPC access, and must be labelled so in evidence.

**Rejected:** PL buttons/switches (readable only through the loaded, possibly user-authored PL image — B5); any HTTP "claim/reset/reclaim" endpoint without a ticket; MAC/IP/subnet adjacency.

**Open questions for P2A-0:** exact boot unit ordering on PYNQ images; FAT write-safety for the delete; ticket format; whether the Control Station or the user generates the ticket; behavior when SD is cloned (see B2).

### B2 — Identity: per-PPU high-entropy key is the authentication root

- The credential generated at enrollment (≥256-bit, `secrets.token_*`, root-owned `0600`, never printed) is the **only secret**. It keys P2A-1 request/response MACs and the Owner Operation Authorization (existing `KEY_CONTEXT` derivation).
- `machine-id`-derived `device_id` and, where available, PL DNA are **binding/consistency attributes**, never secrets: recorded at enrollment, checked on every challenge (P2A-1 already binds `device_id` in the MAC), and surfaced as `WRONG_DEVICE` on mismatch. PL DNA is read only under a known Golden/qualified image; absence is allowed and reported, not faked.
- SD cloning copies the key: this is accepted as "physical possession" for the prototype and documented; a hardware-rooted key store is a separate future decision.
- Rotation = new enrollment (B3); no silent rotation over the LAN.

### B3 — Single active controller with atomic physical-presence reclaim

- **One active controller per PPU** in the first version. The PPU stores `{controller_id, credential, generation}`; the generation is monotonic and durable.
- **Reclaim** (new computer, lost credential, broken PC) uses the B1 ticket. Transition is **atomic**: write new credential+generation to a temp file, fsync, rename; old credential invalid from that instant, including on open connections. Crash before rename = old controller remains; after rename = new one; never both, never neither.
- **Blocked while unsafe:** if any Site Job is active, a B3/deployment is `queued/running`, any `OUTCOME_UNKNOWN`/`recovery_required` is unresolved, or a Site is SEALED, reclaim reports the blocker and does not rotate. (Proposal for owner: allow reclaim while SEALED/UNKNOWN but require the new controller to reconcile before any write — choose one in P2A-0.)
- **Never erased by reclaim:** `/var/lib/plasma-bootstrap/deployment*.json`, upload records, Active Set pointer and generation, Site seals, Worker journals, PPU-side programming outcomes. The new Manager must import PPU-side unresolved state before showing `READY` (G4 → P2B).
- Read-only Monitor consoles (from #1204) are compatible as a later extension; not in the first version.

### B4 — Render `fixed-lifecycle` profile kept as an isolated demo/test profile

- Retain `PLASMA_MANAGER_REGISTRY_POLICY=fixed-lifecycle`, the maintenance cookie and the HTTPS-origin check **only** for `render-control-station-start.sh` / `render.yaml`.
- Local Owner Mode code paths (local-control-station, desktop packages, P1 `Connect PPU`) **must not import, require or branch on** that profile. P1 acceptance adds a contract test that the local profile works with the policy unset and that removing the Render profile would not break Local Owner flows.

### B5 — Arbitrary custom FPGA images remain hardware NO_GO

- Owner Bundles/Providers need no manufacturer allowlist (ADR-0008 §8), but **activation/load of an arbitrary user FPGA image stays NO_GO** until a hardware fail-safe that is independent of the untrusted PL bitstream (output/power isolation that the PL cannot override) exists **and is measured on hardware**.
- Until then: qualified images only (existing Root Image Identity/ABI/static qualification); `fpga_load:true` for an unqualified image is refused with an explicit reason; metadata, SHA256 or self-declared ABI never upgrade an image to safe.

## 3. Revised small-PR plan (each still needs its own Gate 1)

| PR | Depends on | Scope (proposed) | Exit |
| --- | --- | --- | --- |
| P2A-1 deploy | Owner deployment approval | [Runbook](../deployment/ppu-lom-p2a1-synchronized-deployment-runbook.md) only | Hardware acceptance A1–A9 |
| P2A-0 | B1–B3 confirmed | Freeze `plasma.ppu.local-enrollment.v1`, state machine, ticket format, reclaim blocking rule; docs + contract tests | Reviewed protocol; no code path |
| P2A-2 | P2A-0 | Boot-time SD ticket consumer, serial dev CLI, enrollment exchange, atomic credential/generation store, Manager enrollment client | Host-only: replay/expiry/wrong device/runtime-written ticket ignored/crash-atomic/blocked-while-unsafe/journals preserved |
| P2B | P2A-2 | Connect orchestration, derived readiness (replaces 9 `commissioned` gates), PPU-side UNKNOWN import, Manager loopback guard | No READY with unresolved PPU state; non-loopback Manager refuses start |
| P1 | P2B, B4 | `Connect PPU`, remove token box and Validate & Enable for local profile | Local profile has no cookie/token dependency |
| P3 | P1, #1278 disposition, B5 | Unified maintenance, auto exact-action proofs, unqualified FPGA refusal | B5 negatives |
| P4 | all | Retirement + real-PPU acceptance plan | Separate hardware Gate |

## 4. Overlapping Draft PR audit (no PR closed; owner decides)

| PR | State | Overlap with ADR-0008 / B1–B5 | Conflicts | Recommendation (owner decides) |
| --- | --- | --- | --- | --- |
| **#1204** Console Controller / PPU security simplification (2026-10-29, docs, `CONFLICTING`) | Master + 5 Monitor + Engineer; physically confirmed atomic Master takeover; generation/revocation; "never reuse Manager Bootstrap pairing as Console ownership"; remove Manager from the required single-device path | Strongly aligned with B3 (single active controller, physical takeover, generation, old controller loses rights immediately) | Treats Bootstrap pairing and Console ownership as **separate** authorities; ADR-0008 makes the enrolled controller credential the local-control root. Monitor capacity, Engineer root mode and Manager-optional topology are beyond the first LOM version | **Supersede the takeover/Master parts by P2A-0**; keep Monitor/Engineer as a future extension. Either rebase into a short "future roles" note referencing ADR-0008 or close as superseded **after owner review** |
| **#1215** Dual deployment clients (2026-10-30, docs, `CONFLICTING`) | One PPU API for SWPC CLI and User PC Console; no SWPC production dependency; no SSH product deployment; eight-Site admission fence | Aligned: single PPU-owned deployment engine, User PC Console = Local Owner default, PPU-side authentication (P2A-1 now exists) | Requires **HTTPS** (P2A-1 is HMAC over HTTP; TLS NOT_QUALIFIED) and "trusted publisher/provenance" — conflicts with ADR-0008 §8 (no manufacturer allowlist; user-selected trust) | **Rebase and amend**: replace its auth section with ADR-0008 + P2A-1, state TLS as future, drop publisher allowlist wording; keep eight-Site fence invariant. Otherwise close as superseded |
| **#1260** HTTP API only in production; engineering SSH fallback (2026-11-02, docs + `AGENTS.md`, `MERGEABLE`) | Production deploys only via Bootstrap HTTP API; engineering SSH/SCP fallback only before write and with evidence | Compatible. The P2A-1 Bootstrap refresh itself is an SSH engineering action (the API cannot replace its own service) and fits this fallback rule | Touches `AGENTS.md`; "authenticated Bootstrap HTTP API" wording predates P2A-1 | **Keep**; refresh wording to "mutual-authenticated Bootstrap API (P2A-1)" and link the runbook before any Gate 2 |
| **#1278** Retire B4; B3 auto-Active; default authorized FPGA load (2026-11-03, docs, `CONFLICTING`) | Install Bundle → Run Job → Get Result; B3 `activate` atomically selects Active; FPGA load by default with explicit field + authorization | Non-FPGA auto-Active is effectively live (Console sends `mode:"activate"`, `fpga_load:false`; Active Set gen 13 evidence). Aligns with ADR-0008 D8 (explicit intent) | "Default authorized FPGA load" must be limited to **qualified** images under B5; custom images stay NO_GO | **Rebase and amend** with a B5 clause; then Gate 2 independently. Not a blocker for P2A-x |

## 5. Acceptance boundary

Host-only tests prove protocol contracts only. Physical-presence enrollment, reclaim and every hardware step are **NOT_RUN** until separately approved. TLS confidentiality remains NOT_QUALIFIED. Manual credential entry remains until P2A-2 + P1 land.
