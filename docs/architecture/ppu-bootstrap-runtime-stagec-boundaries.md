# PPU Bootstrap / Runtime / Stage C responsibility boundaries

**Status:** Phase 1 documentation of current implementation and its limitations; no deployment or hardware qualification implied.  
**Source baseline:** `main` at `082f018941b508a1310556a2242b112a6ad57dfe` (2026-11-10).  
**Evidence convention:** `CONFIRMED` means the stated *source-code behavior* is directly supported by a path and exact line range. `NOT_VERIFIED` denotes a fact not established by source inspection. A target architecture is labeled `TARGET`, not an installed fact.

This document describes responsibility and packaging boundaries. It does **not** introduce a new service, permission, API, recovery transition, or hardware execution path. See [PPU execution ownership](ppu-execution-ownership.md), [OPF architecture](opf-architecture.md), [unified Bundle-driven execution decision](unified-bundle-driven-programming-decision-2026-11-04.md), and the [Embedded contract](../development/plasma-embedded.md) for the normative policy.

## Ownership and execution

| Component | Responsibility | Current evidence / qualification |
| --- | --- | --- |
| Bootstrap | Factory/enrollment, bounded Bundle v3 deployment transaction, Recovery and Active Asset Set management; **not** the Site Job scheduler | **CONFIRMED** installer is a separate factory/recovery layer and does not install Runtime, load FPGA or change Site power (`scripts/ppu-bootstrap-installer.py:L2-L8`). Transaction and Active Set ownership are the architecture contract; this table does not claim an unobserved Z2 transaction result. |
| Gateway (`plasma-web`) | Console-facing API, status and bounded command ingress; no independent hardware owner | **CONFIRMED** a `gateway` unit entry is generated alongside the `server` entry (`scripts/ppu-z2-installer.py (render_systemd_units)`). The exact Z2 running state is **NOT_VERIFIED**. |
| Runtime (`plasma-server`) | Job admission and lifecycle, PPU execution owner/lease, Site/Session routing and results | **CONFIRMED** `PPUExecutionLease` ties active Jobs to a logical PPU owner (`software/python/plasma_server/site_manager.py:L33-L53`), and SiteManager selects interfaces (`software/python/plasma_server/site_manager.py:L112-L122`). |
| C-3 Site Worker | Local privileged Site admission, PS-local OpenOCD transport, SAFE_OFF verification and Site sealing; accepts Runtime Job sessions across AF_UNIX | **CONFIRMED** Runtime-facing socket client (`software/python/plasma_interfaces/site_worker_c3.py:L1-L17`, `L35-L70`), root requirement for default worker construction (`scripts/ppu_site_worker_service.py:L77-L93`) and rendered root unit (`scripts/ppu_package_units.py:L101-L138`). Hardware-level correctness remains **NOT_VERIFIED** here. |
| Package Actions / control helper | Bounded package execution in a separate non-root identity, with fixed-purpose unit control | **CONFIRMED** unit templates use `plasma-package` and a restricted root control helper (`scripts/ppu_package_units.py:L47-L80`, `L179-L218`). Whether these units are installed or running on any Z2 is **NOT_VERIFIED**. |
| OPF Provider / Profile / Driver | Programming behavior and capability selection behind the Host-owned safety boundary | **TARGET** contract, not an assertion that every third-party Provider is already operational. OPF Core is independent of PPU/Bundle/C-3; a PPU Job uses its verified Active Asset Set and local Host guards ([OPF architecture](opf-architecture.md); [Bundle-driven decision](unified-bundle-driven-programming-decision-2026-11-04.md)). |

The confirmed product OpenOCD path is Runtime `OpenOCDInterface.flash_cycle` → C-3 client → privileged Worker/OpenOCD. The interface requires the C-3 socket and rejects standalone `erase`/`program`/`verify`/`read` operations (`software/python/plasma_interfaces/openocd.py:L19-L34`, `L48-L65`, `L96-L132`). This is **not** a claim that every dynamic, engineering or future `FPGAInterface`/MMIO path has been exhaustively proven unreachable. `FPGAInterface` is currently selectable but its operations raise a not-ready error (`software/python/plasma_server/site_manager.py:L112-L122`; `software/python/plasma_interfaces/fpga.py:L9-L52`).

## Shipping code is not installing a service

- **CONFIRMED:** Bootstrap `REQUIRED_SCRIPTS` includes Stage C scripts as *code only* (`scripts/ppu-bootstrap-installer.py:L24-L55`). The installer separately copies privileged source inputs including `linux_mmio.py` (`scripts/ppu-bootstrap-installer.py:L125-L143`). This does not itself activate a Stage C unit or an FPGA image.
- **CONFIRMED:** `ppu_package_units.py` is a text renderer; its header explicitly says it does not install/enable units and the existing Z2 installer does not reference it (`scripts/ppu_package_units.py:L1-L18`). The file defines the proposed C-3 and package-unit isolation (`L47-L80`, `L101-L138`, `L179-L218`).
- **CONFIRMED:** Runtime package builder copies the `plasma_interfaces` source package into a ZipApp build tree (`scripts/ppu-runtime.py:L30-L38`, `L147-L175`). Inclusion is not evidence of execution or privilege.
- **NOT_VERIFIED:** Which Stage C units are installed, enabled, or resident on an actual Z2. The two main application roles (Gateway and Runtime) must not be equated with the total number of resident systemd processes; Bootstrap and any deployed privileged helpers are separately accounted for.

## Privilege and recovery invariants

1. Runtime Job/Lease ownership and C-3 hardware admission are complementary authorities, not two independent writers for the same Job state (`software/python/plasma_server/site_manager.py:L33-L53`; `software/python/plasma_interfaces/site_worker_c3.py:L1-L17`). Do not infer that all potential alternate interface entry points are closed without a separate reachability audit.
2. Current Worker wiring requires root for its default adapter (`scripts/ppu_site_worker_service.py:L77-L93`), and its rendered unit grants `/dev/mem rw` while constraining its network and filesystem access (`scripts/ppu_package_units.py:L101-L138`). This **does not prove** that Linux/hardware fundamentally requires a permanently root-owned Worker; privilege reduction requires separate design and Z2 evidence.
3. Operator Site Seal Recovery is a root-only CLI, verifies SAFE_OFF and pre/post owner conditions, and archives rather than deletes the sealed marker (`scripts/ppu_site_recovery.py:L92-L125`, `L129-L139`). Recovery does not belong to routine Runtime Job retry.
4. Process exit, timeout, failure, or an unknown transaction outcome never establishes electrical SAFE_OFF or authorizes an automatic replay. The [Embedded contract](../development/plasma-embedded.md) controls actual device recovery; no modification of a pending `recovery_required` state is implied here.
5. Bootstrap retains the sole Bundle deployment transaction and Active Asset Set boundary. Moving scripts among packages must not create a second transaction owner or bypass Package/Site admission. The [Bundle v3 contract](ppu-canonical-bundle-packages.md) remains authoritative.

## Change gates and unresolved evidence

| Candidate | Current status | Required before behavioral change |
| --- | --- | --- |
| Clarify ownership and code-shipping terminology | `CONFIRMED` source facts documented here | Documentation review only |
| Shrink C-3 root privileges or merge Worker into Runtime | `NOT_VERIFIED` hardware/OS replaceability | Separate Gate 1 scope, root/Site/recovery contract review and Z2 acceptance |
| Change Stage C unit installation/enablement | `NOT_VERIFIED` current deployed unit inventory | Separate installer transaction/recovery proof and authorized Z2 Gate |
| Remove interfaces from Runtime ZipApp | `EXPECTED_BY_BUILD_RULE` package inclusion; actual Release member list `NOT_VERIFIED` | Artifact-pinned member inventory, dependency/negative tests and later Gate |

This Phase 1 document is descriptive only. It neither approves Gate 2 merge nor grants deployment, restart, SWPC/Z2 writes, FPGA load, DUT access or recovery actions.
