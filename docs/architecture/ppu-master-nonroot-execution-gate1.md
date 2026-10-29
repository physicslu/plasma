# PPU Master non-root privileged execution / deployment — Gate 1 Path 1

> **Status:** Owner-approved Gate 1 Path 1, 2026-10-29. **Host-only contract / tests, NOT deployed authority.** Based on `main 68762add6e852854d92a5b4ff4bf87d75dc871a3`, including merged [PR #1205](https://github.com/physicslu/plasma/pull/1205). This Gate 1 does **not** modify Z2 accounts, sudoers, permissions, systemd services, protected Root Entry, FPGA, DUT or SWPC; **no merger or deployment is authorized**.
>
> Prior [PPU privilege roles contract](ppu-privilege-boundary-gate1.md), [Root Guard necessity audit](../development/z2-root-guard-rule-audit-gate1.md), [Z2 installer](../deployment/z2-ps-installer.md), [Bootstrap factory/deployment](../deployment/ppu-bootstrap-factory-and-hil.md), [remote write security](remote-write-security-boundary.md).

## 1. What currently exists, and the actual missing boundary

The current Python product role classification `plasma_core.ppu_privilege_policy` says Monitor can observe, Master may **request** programming/deployment and Engineer alone has a Root-maintenance **role**. It has **no authenticated PPU Master identity/generation** and does not change Linux UID.

Current code and gaps (evidence is source; Host-only is not Z2 hardware proof):

| Existing endpoint / tool | Existing role and authority | Intended reuse / explicitly deferred |
| --- | --- | --- |
| `software/python/plasma_web/secure_gateway.py` + `gateway_security.py` | Opt-in Bearer principal, resource permissions and audit/idempotency; **not** physical single-Master Console Registry | **Reuse** authentication and PPU scope. Require device-derived live Master generation/revocation when Console Registry is separately implemented. Do not accept a role supplied in the request body. |
| `scripts/ppu-bootstrap-service.py` + `ppu-bootstrap-deployment.py` | Bootstrap onboarding uploads and deployment transaction; SHA sidecar, journal, verified release, staged install, health check, rollback | **Reuse** this as the *installer/deployment authority*, not a second deployment daemon or a new write-any-file root API. Existing Bootstrap Bearer token is not Console Master ownership. Factory/bootstrap transport has additional commissioning restrictions. |
| `scripts/ppu-z2-installer-core.py` | Immutable PPU release verifier, packaged file allowlist/digests, atomic installation, systemd activation/rollback, Linux privileges | **Reuse** installer verification rather than promoting a raw SHA match to publisher trust. Runtime authority to install/restart is deliberately **not** granted in this Gate 1. |
| `scripts/plasma_wordport_program.py` and `scripts/bluepill-wordport-session.py` | Z2 WordPort currently requires **EUID 0**; fixed source/BUNDLE module SHA, Root source pin, exact device check and FPGA holder validation | Master must **not** execute a newly updated Python Script as root. Future narrow service must run reviewed/pinned immutable implementation for device-side operations; do not weaken current EUID/root-file owner checks now. |
| `scripts/z2/plasma-path2-root-entry` and `pl/hil/fpga_image_root.py` | Protected Root FPGA lifecycle: fixed `download|test|restore`, signed-off source SHA, trusted import closure, manifest, Boot/Golden/reload lock | **Keep exact allowlist and protected Root code immutability**; allow Master to request *qualified* FPGA Image + Manifest deployment only via future authenticated/narrow privilege path. Never offer arbitrary command/module/file execution. |
| `software/python/plasma_server/site_manager.py` and `linux_mmio.py` | PPU-global Job execution lease plus local MMIO device scope; Site 1 Z2 physical route and future Site 1..8 target | Keep real Site admission, reload exclusion, cleanup and Recovery. A normal Site job must not unnecessarily hold a future all-Site exclusive lock, but Host tests do not qualify hardware parallelism. |

**Critical privilege escalation anti-pattern**: If Master can deploy editable `Script A` and the PPU then executes `Script A` as Root without a separate reviewed immutable trust boundary, **Master becomes effectively Root**. No arbitrary caller-supplied `argv`, shell, Python module, executable path, sudoers edit, or source-pin auto-rewrite is acceptable as the Master programming API.

## 2. Host-only machine-checkable contract

`software/python/plasma_core/ppu_privileged_operation_contract.py` is a **planning-only** API:

- `PrivilegedRequest`: typed `PPUAction`, optional one-based `site_id`, optional staged artifact *relative* name with SHA256. No arbitrary command string, argv, shell, executable path, sudo parameters, or Root identity field.
- `AdmissionFacts`: **test-supplied** role, verified-authentication flag, Master ownership/generation, independent Engineer local maintenance flag, current per-Site/all-Site quiescence, known recovery state, protected-source and qualification evidence.
- `plan_privileged_operation()`: returns a `PrivilegedPlan` containing **only** an existing conceptual route name plus artifact digest/size information. **It does not call the route**, install, connect, run a command or authenticate. An untrusted API client can forge a Python `AdmissionFacts` object; thus **this function is not an authorization security boundary** and must **never** be wired to Root/production hardware on the strength of these values.
- `inspect_staged_artifact()`: Host-only inspection of a caller-independent, **trusted** staging root using `O_NOFOLLOW` on each relative component, regular-file/mode checks, SHA256, before/after stat checks. Its receipt is **not** an immutable file descriptor. A mutable artifact can change **after** inspection; actual privileged deployment must independently verify the exact archive and transaction at time of installation. The staging root may never come directly from a REST caller.

| Action family | Host-only route, **not runnable** | Safety and trust to be enforced in actual PPU |
| --- | --- | --- |
| Master Program/Erase/Verify/IC READ on Site N | Existing Z2 PS WordPort Job | Site-specific ownership, exact ICPN/Provider qualification, protected Root installed code and target electrical checks |
| Master Script/Engine/Profile/Asset/Document deployment | Existing verified PPU **Release/Bootstrap Deployment** | Only contents of a verified immutable release transaction, atomic activation with rollback; Master-controlled scripts must not become Root-trusted runtime code |
| Master FPGA Image deploy/reload | Existing protected FPGA Root lifecycle | Reviewed Image + companion Manifest, current Boot/ABI/Golden, all-Site idle, Root source pinned code, reload exclusion |
| Master Job start/cancel, settings, protected readback export | Existing Job Manager / authenticated Gateway | Exact PPU/Site authorization, safe output scopes, live Master ownership |
| Engineer protected Root/OS/system maintenance | Separate Engineer maintenance | Verified **local** maintenance activation and actual Linux Root UID; not an extra online Master or general Console privilege |
| Monitor | No privileged route | Restricted information-only endpoints; physical IC READ/readback is not monitoring |

The product **Master action capability** and the actual OS privilege boundary are separate requirements. `source_sha256` and packaged SHA are integrity signals, not authenticated publisher provenance. A release change cannot silently alter protected Root source.

## 3. Host-only negative/positive acceptance

Tests: `software/python/tests/test_ppu_privileged_operation_contract_gate1.py`.

- Allow valid *modelled* Master requests to plan an existing Site Job, verified-release deployment, FPGA Root request and Job Manager route; Engineer maintenance role is classified only when separately marked local-authorized.
- Reject Monitor hardware/program/deploy/readback, unauthenticated request, obsolete Master generation, spoofed string role, arbitrary command/argv and Root override.
- Reject malformed Site, busy Site, unsafe/UNKNOWN recovery, unqualified target/FPGA Image, unpinned Root source, FPGA reload while any Site active.
- Check fake staged files: path traversal, absolute paths, symlink file/ancestors, FIFO, group-writable input, wrong SHA, mutated Script. No device files or Root privileges are acquired.
- Static regression assertions require the **unchanged** current Bootstrap Deployment, Installer, protected Root Entry and WordPort guards to remain present.

**Not covered / NOT_RUN:** actual Console Registry ownership generation, physical pairing, Engineer local root login, secure transport/provisioned publisher, executable privileged helper, usable non-root WordPort, O_NOFOLLOW on real Z2 installed filesystem, FPGA image download, concurrent Site lock behavior, real rollback/hardware impact, root credential and OS-level DAC, SWPC or DUT.

## 4. Future integration — explicit separate implementation/qualification

1. Keep existing authentication and Installer; at PPU ingress translate **authenticated** Console identity + active durable Master owner generation into permissions. Revalidate revocation at **dispatch**, not only at UI login. Engineer requires a separate local maintenance authority; do not assume an Engineer role string grants Linux root.
2. Narrow the privileged operation boundary to deterministic **non-shell** operations. For deployment, route a verified, immutable PPU release through the existing Bootstrap journal/installer/rollback; never allow a product API to provide arbitrary sudo commands or direct protected-file paths.
3. For programming, replace the prototype's Root-running mutable WordPort script with a properly protected immutable device-side implementation or a carefully audited least-privilege device helper. Retain current Source Pin/Root Guard until hardware-qualified replacement exists.
4. For FPGA image operations, reuse the existing Root Entry's fixed operations and preserve Boot, Manifest, ABI, all-Site reload exclusion and Golden Recovery. Site 1/2 fence [Draft PR #1189](https://github.com/physicslu/plasma/pull/1189) and uncertainty [Draft PR #1201](https://github.com/physicslu/plasma/pull/1201) remain separately qualified; no automatic merge, software deletion or hardware claim.
5. Test exact role/revocation, open-file/TOCTOU prevention, Linux UID/DAC, root-script trust and per-Site operation on a separately approved system integration/physical HIL plan **before** retiring guards or switching production PPU into the new capability model.

No new standalone privilege daemon, second installer, role registry, release format, per-task workflow, source pin or arbitrary Root API is created by this Gate 1.
