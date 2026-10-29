# PLASMA Console Controller / PPU Security Simplification

> **Status (2026-10-29): Owner-confirmed product direction and documentation baseline; implementation migration NOT_DONE.**
> This is a forward-looking product architecture decision, **not** a claim that the current Z2, Secure Gateway, Root Guard, FPGA or 8-Site system already enforces it. No service, Linux account, FPGA, Root image, DUT or deployment is changed by this document.
> Related current-state contracts: [configuration architecture](configuration-architecture.md), [remote-write security](remote-write-security-boundary.md), [PPU execution ownership](ppu-execution-ownership.md), [control-plane routing](control-plane-routing-architecture.md), [Zynq isolation review](zynq-fpga-manager-isolation-ownership-review.md).

## 1. Product premise and distinct responsibilities

PLASMA is an autonomous physical IC programmer: a Console Controller uses high-level commands/status over Ethernet; the PPU has embedded Linux on PS, a PS-local programming runtime/OpenOCD and a PL FPGA implementing the target-side interface. The product target is eight independent Programming Sites; the existing Z2 hardware route is a one-Site prototype, while the independent two-Site proposal in Draft PR #1189 has only Host-only qualification. **Eight-Site production hardware is not qualified.**

The simplest useful product model has three user-facing capabilities, but **only two normal Console roles**:

| Product mode | Authority | Linux/OS boundary |
| --- | --- | --- |
| **Monitor** | Read information: status, progress, non-sensitive logs/results. No new Job, IC/target read operation, write, configuration, firmware/download, maintenance or secret/readback extraction. | Guest-equivalent constrained identity, not necessarily a real Linux login. |
| **Master** | Sole active Console that may issue all authorized *programming-related* jobs, IC operations, programming engines/scripts/profiles/documentation deployments and qualified FPGA image deployment. | **Not a Linux root account**. Uses a narrow reviewed privileged bridge for root-required operations, not an arbitrary root shell. |
| **Engineer** (maintenance mode) | System maintenance, recovery, Linux users/permissions, protected Root/Bridge replacement and underlying OS/hardware repair, in addition to Master capabilities while maintenance is authorized. | Real Linux **root (UID 0)** maintenance authority, entered through separately authenticated, locally confirmed maintenance; not a routinely connected third master or seventh Console. |

Master's programming deployment rights do not imply arbitrary rewriting of protected Root executables or the OS. Any protected Root/FPGA Manager update follows its separately authorized integrity/rollback process. A Root maintenance session is powerful and **not** made unconditionally safe by application-level locks or Root Guard.

A single-PUU Standalone path must work without Plasma Manager, Cloudflare Access, Internet or a remote licensing/login service. Existing Managed Mode remains available for multi-PPU routing, but is not a standalone device prerequisite.

## 2. Console Controller — decisions, existing evidence, reduction

**Product rules (approved design; runtime enforcement still pending):**

1. Exactly **one registered active Master** per PPU; no other Console may mutate the device while this Master is active.
2. **Five simultaneously connected Monitor Consoles by default**, from PPU-owned configuration, not constants in the UI or server. The default total is six independently authenticated Console **identities**, computed as 1 + 5; browser tabs, sockets and reconnections are not new devices.
3. A person physically possessing the PPU can locally confirm re-registration of another Console as Master. The new registration **atomically replaces** the old Master without old-Master or Internet approval. A remote LAN request alone must not silently steal ownership. The exact physical confirmation mechanism on production hardware is not yet qualified.
4. On successful replacement, the old Master immediately loses **all further mutation rights**, including on an already-open connection and with previously issued credentials. It may be treated as Monitor **only if capacity permits**; otherwise disconnect/deny it as a Monitor. Never evict unrelated occupied Monitor seats solely to keep the old Master.
5. The PPU retains its Master designation across Console disconnect and PPU restart. Already accepted Jobs continue on the PPU independent of Console connectivity and are not automatically interrupted by Master replacement.
6. All mutations, including direct REST/API, Manager-relayed, CLI and privileged deployment paths, must enforce device-side ownership. UI button disabling is not security.
7. Registered Console identity, current Master, generation/revocation and live connection occupancy are distinct data. Private credentials and durable ownership must remain PPU-side protected; do not put private keys or live sessions in YAML. A durable SQLite state is a reuse candidate, **not yet wired** to Console registration.

**Current code vs actions:**

| Existing mechanism | Current verified behavior | Direction / removal boundary |
| --- | --- | --- |
| `gateway_security.py` Principal/roles: `viewer/operator/engineer/admin/service` | Static security principals and permission sets; `viewer` already lacks executable IC READ/Program/Erase permission. | **Retire five-way role selection from product UI only after replacement.** Product presentation becomes Monitor/Master and a separate Engineer mode. Retain backend permission granularity for sensitive endpoints/internal service use. |
| Manual Bearer token entry and static SHA256 principal digests | Opt-in Secure Gateway authenticates tokens, but no physical Master re-registration/revocation workflow. | **Retire manual daily token UX after device registration**; reuse authentication plumbing with revocable Console identity and generation. |
| Browser page-instance `execution_owner_id` | Logical Job concurrency label, not a security principal. | **Do not use as Console identity**; keep existing Job concurrency compatibility until authenticated device identity is bound at PPU ingress. |
| Manager registry, managed routing and Bootstrap token pairing | Useful for optional managed fleet/platform routing; Bootstrap pairing is *not* physical Console registration. | **Remove Manager from required single-device user path**, not from repository or genuine optional managed deployments. Never reuse Manager Bootstrap pairing as Console ownership. |
| Secure Gateway opt-in deployment | Backend permission, scope, idempotency and audit logic exist; plain canonical Gateway remains default in documented deployments. | **Retire unprotected write ingress in product deployment only after** every reachable write/privileged path uses the trusted PPU ownership decision. Keep development rollback during migration. |
| Console seat/count policy | Canonical `main` config has no enforcement. Independent candidate branch `agent/ppu-console-capacity-config-gate1-20261029` adds YAML parsing/defaults and Host-only tests only. | Implement **actual connected-identity seat admission**, atomic replacement and restart semantics before marking this feature implemented. |

The future PPU YAML policy shape is:

```yaml
ppu:
  console:
    max_master_consoles: 1
    max_readonly_consoles: 5
```

`max_total_consoles` is derived, never separately configured. The single-master count remains fixed by product policy; only Monitor capacity is configurable. This example is **not yet effective on main or deployed Z2**.

## 3. PPU (Z2 PS/PL) — existing guards, simplification candidates, exclusions

**Separate three independent questions:**
- **Console Authorization:** *who* may submit a command? One registered Master; Monitors can observe.
- **Job/Hardware Ownership:** *which Job/Site/process* currently owns execution? Site/PPU locks and Job lifecycle; this is not the Console role.
- **Hardware/Programming Qualification:** *is this specific operation safe/valid now?* Image/ABI, real device ownership, Site readiness, power/wiring, IC Provider/Exact ICPN qualification, recovery state.

| Existing mechanism | Observed source state | Product direction / what NOT to remove |
| --- | --- | --- |
| Privileged Root Image/Manifest Guard | `pl/hil/fpga_image_root.py` and `fpga_image_guard.py` require privileged protected execution, pinned code provenance, Image/Golden digest, Boot/FPGA Manager/IO facts and the historic `supervisor.lock`. | **Keep core image/hardware safety.** Narrow normal programming preflight to relevant observable hazards. Do not turn this into another Console role service. |
| Full `/proc` census | On main, `live_program_session_report()` avoids whole-system PID enumeration for normal programming; FPGA Manager download/test/restore retain the stricter `live_report()`. The 2026-10-28 device mismatch is documented; installed Z2 versions were not re-verified in this documentation task. | **Do not reintroduce the global PID census into normal programming.** Keep stricter maintenance checks until source/real hardware review proves a narrower safe alternative. |
| Source SHA / Root source pin | Protects **Root executable bytes** and compatible Bridge source, not an arbitrary static per-image admission token. Deployment code does check exact reviewed installation for some hardware paths. | **Do not delete integrity checks merely to ease deployment.** Allow Master to update qualified programming assets using a safe publisher/installation process; updating protected Root code remains Engineer-controlled and requires reviewed re-pin/rollback. |
| `fuser` / advisory `flock` | Device-scope observations and cooperative process locks detect some conflicts. They do **not** prove no privileged bypass, race-free ownership or hardware isolation. | **Minimize redundant preflight while retaining real ownership.** Do not claim `flock` can constrain a non-cooperating root process. |
| PPU FPGA Reload Fence | Existing single-owner MMIO and protected Root supervisor locks are real; proposed shared PPU Reload Fence + independent Site-exclusive locks are **Draft PR #1189 Host-only**, not deployed. | **Keep one logically consistent Reload/Configuration exclusion.** No image reload while any active Site/unsafe in-flight work exists; do not serialize all future eight Site flash jobs under a single EX lock. |
| PPU Execution Lease in `site_manager.py` | Current PPU-global Job ownership prevents different logical owners from overlapping; existing Batch/page owner labels are not authenticated Console ownership. | **Reuse and simplify** only after proving per-Site fairness/independence, proper authorization at ingress and concurrency invariants. Do not confuse global execution lease with persistent Console Master ownership. |
| Site Crash Recovery / persistent UNCERTAIN | Draft PR #1201 provides Host-only journal/gate evidence; trusted live Root recovery authority and real FIFO integration remain incomplete. | **Remove independent “Recovery Authority service” as a required product component**; integrate necessary recovery decision into Job Manager/PPU. **Retain** pre-write durable intent and stop-on-unknown for hazardous/in-flight operations; never blindly retry OTP/security/protection operations. |
| Root-required current WordPort CLI | `scripts/plasma_wordport_program.py` currently checks `os.geteuid() == 0` and specific source/installation/target guards. | Master still must complete allowed programming work through a narrow audited privileged service; **do not grant it general root shell**, and do not claim that wiring already exists. |
| Engineering/Root maintenance | Actual Linux root can perform privileged repairs and can bypass user-space advisory coordination if it chooses. | Engineer is an exceptional locally authorized **maintenance mode**, not automatically another normal Console seat or a permanent programming identity. |

**Scope boundary:** `Root Guard` does not decide *who is Master*. It validates protected hardware/image preconditions for authorized operations; `PPU Reload Fence` prevents incompatible operations from overlapping. A product authorization policy must not be implemented a second time with independent role state inside these guards.

## 4. Who is allowed to define a “safety rule”?

| Decision | Authority / evidence | Enforcement |
| --- | --- | --- |
| Product roles, Master replacement, default limits, Engineer capability | **Product Owner** | PPU Console Registry / authorization policy |
| Exact ICPN, Provider, Flash geometry, operation-specific interlocks | Reviewed original-manufacturer evidence, device-specific software and Host/HIL qualification following ADR-0002 | ProgrammingQualification / Job admission |
| Image/ABI, electrical/ownership/reload/recovery preconditions | Reviewed platform design and **actual** PS/PL/electrical evidence, not just source SHA or Host tests | Protected PPU runtime/Root hardware safety |
| Implementation and refactoring proposal | Developers and automated coding tools can propose and test; they **cannot invent a permanent product rule** | Change review and normal Gate 1/Gate 2 process |

A blocking check must document: the failure it prevents, the observable evidence, whether it is mandatory during normal programming or only during maintenance, its false-positive/operational cost, and its corresponding regression test. Classify as **necessary hardware safety**, **deployment integrity**, **historical/development restriction**, or **duplicate check** before removing or narrowing it. Normal development should not be blocked merely because a broad inventory scan is incomplete when specific hardware ownership and safety can be reliably established; unknown real in-flight state, dangerous electrical conditions or unqualified restoration still stop unsafe operations.

## 5. Migration / deletion sequence (design only; no deletion authorized)

| Order | Console Controller | PPU |
| --- | --- | --- |
| P0 | Implement authenticated single Master, physical-confirmed atomic takeover and configured Monitor count. Replace the product multi-role UI after equivalent coverage. | Require PPU-side Master decision for all mutation ingress; close plain/unprotected product write paths once safe replacement is validated. |
| P1 | Auto-register/auto-authenticate; stop treating browser-page owner or Manager Bootstrap pairing as Console authority. Keep optional Managed Mode. | Audit Root Guard rules; separate ordinary programming checks from Root maintenance checks. Preserve versioned Root protected update/rollback. |
| P2 | Remove unused product-only role UX and duplicated owner controls **after tests**. | Collapse unnecessary *services* for Site Lease/Recovery into existing PPU Job Manager, without deleting the underlying lock/UNCERTAIN behavior or interrupt isolation. |

### Minimum acceptance requirements before retiring existing guards

1. Monitor read access and information-only response; deny any Program/Erase/Verify/IC Read, asset write, settings change, protected readback/secrets or deployment.
2. Exactly one Master; a sixth Monitor (after five active Monitors) is denied without consuming a new seat for additional tabs/sockets of an existing Console identity.
3. Physically confirmed B takeover atomically revokes A for all subsequent writes, including stale HTTP sessions/tokens/queued *new* commands; B can submit work. Already admitted in-flight work is not aborted merely due to ownership change.
4. A retains Monitor access only if a Monitor seat is actually available. Local PPU restart preserves the new Master and no old credentials regain mutation rights.
5. Real direct REST, optional Manager-relayed calls, CLI, deployment/privileged bridge and engineering interfaces cannot bypass Master authorization; Engineer mode needs independent authenticated/local maintenance control.
6. Authorized Master can deploy programming Engine/Scripts/Profiles/Documents and qualified FPGA images without gaining a general root shell; protected Root and Linux administration remain Engineer-controlled.
7. No FPGA reload while Site hardware work is active, no same-Site concurrent MMIO, no automatic replay of uncertain destructive work, and no unnecessary global serialization of independent future Site Jobs.
8. All relevant negative/positive tests pass on exact source; Z2/HIL claims require separate real evidence. Existing legacy endpoints remain closed or are explicitly designated internal privileged service endpoints.

## 6. Grounded implementation status at decision date

- `main` SHA: `11a67ed526bbc999e6ffbb1abfdb6e57abf34e61`.
- Existing Secure Gateway has static principals/roles, permission scopes, explicit API authorization and a durable idempotency/audit ledger; its product default deployment is **not** yet unified enforced Console identity. See [remote-write security](remote-write-security-boundary.md).
- Console limits `1+5` are config-parser/validation only on separate branch `agent/ppu-console-capacity-config-gate1-20261029`; they do not enforce live Console admission.
- Independent two-Site SWD and PPU shared/exclusive fence: [Draft PR #1189](https://github.com/physicslu/plasma/pull/1189), **not merged or hardware qualified**.
- Site UNCERTAIN crash recovery: [Draft PR #1201](https://github.com/physicslu/plasma/pull/1201), **not merged or hardware qualified**.
- Root Guard Program Session vs FPGA reconfiguration observation split has source in `main`; actual installed protected Root/Bridge compatibility on Z2 remains a separate deployment/HIL fact.
- **NOT_DONE in this documentation update:** physical registration, Master/Monitor/Engineer runtime enforcement, Console count enforcement, protected privilege redesign, Source Pin changes, lock/recovery changes, any SWPC/Z2/DUT operation or merge.

**This document records the intended product architecture and retirement criteria; it is not permission to remove operational safety guards before their substitutes are proven.**
