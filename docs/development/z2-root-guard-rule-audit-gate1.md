# Z2 Root Guard rule necessity audit — Gate 1 (read-only evidence)

> **Status:** 2026-10-29, Gate 1 Path 1 **Host-only source audit**. This is a recommendation ledger, not a deletion list, source modification, installed-Z2 observation, permission change or hardware clearance.
> Source baseline: `main 11a67ed526bbc999e6ffbb1abfdb6e57abf34e61`. Related [PPU product privilege contract](../architecture/ppu-privilege-boundary-gate1.md). Root Guard Program Session split is already merged on main via PR #1202. The Z2 installed Root/Bridge versions, if different, remain unverified.

## 1. Responsibilities and audit rule

**Console permission** (who may request) belongs to authenticated PPU Gateway / future Master Registry, **not** Root Image Guard. **OS privilege** (whether the caller or privileged service has required Linux access) is enforced by Linux DAC/sudo/service isolation and verified by trusted local entry. **FPGA/DUT safety** belongs to Guard / Job Manager / physical hardware admission, not to user role names. The `engineer` role requires genuine independently authorized Root maintenance, not a trusted spelling in an API request.

Each blocking rule must have a defined hazard, a trustworthy observation, an operating phase, a source location, and evidence before removal. Classification:
- **KEEP**: currently justifies a real safety/integrity bound.
- **KEEP_PHASED**: valid for FPGA maintenance or protected operations, not a mandatory ordinary Program preflight.
- **REVIEW_DUPLICATION**: may be consolidated only after equivalent real ownership/safety coverage is proven.
- **NOT_YET_ACTIVE**: draft architecture/Host-only capability, cannot be claimed as deployed.
- **REVIEW_DEPLOYMENT**: preserve integrity but evolve a safe Master-led deployment transaction; do not remove code pin without substitution.

## 2. Real code-level rule inventory

| ID | Source / exact check | Purpose / observed evidence | Phase | Decision |
| --- | --- | --- | --- | --- |
| RG-01 | `scripts/z2/plasma-path2-root-entry`: root UID + fixed `download|test|restore` allowlist | Reject unprivileged or arbitrary Root-command/module invocation; not Console authorization | Protected FPGA lifecycle | **KEEP** |
| RG-02 | `plasma-path2-root-entry`: fixed protected root tree owner/mode/no symlinks and pinned commit/SHA256 | Prevent unreviewed executable/plugin/bytecode injection into privileged Root operation | Protected Root code | **KEEP**; **REVIEW_DEPLOYMENT** for signed/reviewed update transaction |
| RG-03 | `fpga_image_root.trusted_local()`: exact ARMv7 Python runtime + Root-owned executable paths | Ensure supported native Runtime and prevent modified Root imports | Protected Root | **KEEP** until a new exact ARMv7 qualified runtime is demonstrated |
| RG-04 | `fpga_image_root.read_image_manifest()` / `fpga_image_guard.sha_file()`: board/SOC, BIN/Golden SHA, Manifest, ABI/register words | Reject wrong/unverified Image/FPGA ABI and lost Recovery artifact | Image install/load/restore and Program session | **KEEP** (Manifest hash alone does not prove publisher trust) |
| RG-05 | `fpga_image_root.read_state()`, `_confirm_current()`, `write_state()`: boot, checkpoint, manifest, `DOWNLOAD_IN_FLIGHT`/`TEST_IN_FLIGHT`/`UNKNOWN` states | Prevent stale-image operations and blind retry after uncertain PL transition | FPGA lifecycle | **KEEP** |
| RG-06 | `fpga_image_guard.RootZ2TargetPort.exclusive()`: protected `/run/plasma-z2-swd05/supervisor.lock` | Serialize cooperative protected FPGA lifecycle and check lock inode/owner/mode | Protected FPGA operations | **KEEP**, evaluate future co-existence with same PPU Reload Fence |
| RG-07 | `fpga_image_admission.check_exact()`: current Boot, Manager `operating`, load provenance, exact bound UIO map/Driver and IRQ topology | Detect stale/wrong platform mapping and unexpected FPGA-state change | Program and FPGA maintenance | **KEEP** where applicable to exact hardware; specialize per hardware ABI |
| RG-08 | `fpga_image_admission.check_exact(...runtime_program_session=True)`: `proc_complete=None`, `NOT_RUN_PROGRAM_SESSION` | Explicitly **does not** claim complete PID/FD census; safeguards against mislabeling a skipped scan as PASS | Ordinary programming | **KEEP** (existing simplification from PR #1202) |
| RG-09 | `fpga_image_admission.check_exact(...runtime_program_session=False)`: `proc_complete=True`, `proc_conflicts=[]`; `fpga_image_guard.scan_proc_consumers()` | Stronger pre-reload/process-VMA observation; can fail if global scan incomplete, but reload is riskier than runtime traffic | FPGA Manager download/test/restore | **KEEP_PHASED**; do not add back to ordinary Program |
| RG-10 | `scripts/plasma_wordport_program.py`: `geteuid()==0`, pinned install path, native library/Bridge SHA and Root source pin | Current specific Z2 WordPort execution expects Root and reviewed binaries | Z2 prototype programming | **REVIEW_DEPLOYMENT**: Master needs narrowly scoped privileged service, not root shell; don't weaken before wiring |
| RG-11 | `scripts/plasma_wordport_program.py`: `fuser -s /dev/mem` and `/dev/uio1` plus existing OpenOCD/session scan; Bridge repeats scope check under lock | Detect another process holding the same device before MMIO; `fuser` is observation, not atomic owner lock | One-Site Z2 Program | **REVIEW_DUPLICATION** only if a trusted single-owner service/lock covers both races |
| RG-12 | `software/python/plasma_interfaces/linux_mmio.py`: `/run/lock/plasma-mmio.lock` `flock(EX)`; explicitly claimed Site apertures and register allowlists | Prevent cooperative MMIO collision, unaligned/unapproved register accesses | Current MMIO | **KEEP** ownership/allowlist; refactor global-lock granularity only with qualified independent Sites |
| RG-13 | `software/python/plasma_server/site_manager.py`: PPUExecutionLease, Job state/queue, runtime quiesce | Prevent conflicting logical Jobs and reject runtime activation while busy | PPU job runtime | **KEEP**; do not equate job-owner label with registered Console Master |
| RG-14 | `scripts/bluepill-wordport-session.py` checkpoint preflight: exact `IMAGE`, Boot, SHA, ABI and tested image | Reject stale/recovery/untested FPGA Image for SWD session | Normal Program | **KEEP**; source/Bridge mismatch must return real NOT_RUN, not synthetic PASS |
| RG-15 | Draft PR #1189: PPU Reload Fence SH for active Site; EX for FPGA Load/Restore; per-Site EX | Avoid reconfiguration during transactions **without** globally serializing independent Site jobs | Future multi-Site | **NOT_YET_ACTIVE** on main; Host-only proposal, not Z2-qualified |
| RG-16 | Draft PR #1201: durable UNCERTAIN in-flight programming journal | Prevent re-issuing destructive writes after interruption/unknown outcome | Future recovery | **NOT_YET_ACTIVE** on main; integrate into existing Job Manager only after evidence |
| RG-17 | `fpga_image_guard.manager_write()`: only manifest-bound known filename; FPGA Manager `operating` + current-boot provenance | Prevent arbitrary firmware path and detect unsuccessful loads | FPGA maintenance | **KEEP** |
| RG-18 | Physical voltage, SWD pins, isolation, AXI quiescence and recovery | Cannot be established from `sha256sum`, `fuser`, a successful Host-only test or a UI authorization token | Physical programming/reload | **KEEP as real acceptance**; gaps remain for production eight Site and reload qualification |

## 3. Where duplication really exists

| Overlapping mechanisms | What they *actually* cover | Correct consolidation target | Do not do |
| --- | --- | --- | --- |
| Console roles / Static `Principal` / Root UID | Different questions: authenticated requester vs privileged OS execution | One trusted PPU ingress; narrow privileged Bridge | Delete Root UID checks because Master UI says `root` |
| `fuser` + `/proc` process scan + `flock` | Detection vs process inventory vs cooperative exclusion | Ordinary Program: scoped ownership/lock; Maintenance: strict quiescence and process visibility | Use `fuser` as a race-free lock, skip unknown active MMIO owner |
| `supervisor.lock` + `plasma-mmio.lock` + proposed PPU Fence | Different historic lock namespaces, not necessarily the same inode or acquisition protocol | Single coordinated reload exclusion + per-Site ownership after independent proof | Delete both locks, or keep 1 full-job PPU EX lock for eight independent Sites |
| PPU ExecutionLease + Site MMIO lease | Job-level scheduling vs hardware access lease | Reuse current Job Manager for authority and Site-exclusive driver locks | Assume a Browser page/batch label proves Console ownership |
| Root SHA vs Image BIN SHA | Protected **executable source** vs deployed **bitstream data** | Maintain separate versioned protected update and Image/Manifest validation | Require a new Root commit per Image or remove protected-source integrity |

## 4. Priorities, evidence gates and explicit non-goals

- **P0 — no code removal:** Define Master/Monitor/Engineer action matrix (Host-only), map each privileged request to existing Root/WordPort/FPGA endpoints, preserve the exact current Root Entry. A principal with `operator` or `admin` today is **not automatically** the product Master.
- **P1 — source/authorization integration later:** Build narrow trusted service for authorized Master programming and installation; prevent non-Master API/CLI bypass; separate platform Root Engineer maintenance from ordinary programming; then qualify the protected source update/rollback path.
- **P2 — real resource-owner simplification later:** Once trusted Owner/Reload admission is wired, review RG-06/11/12/13 for redundant locking/false positives in isolated real one-Site and two-Site fault injection, preserving no-reload-during-program and no-same-Site-double-write.
- **P3 — expansion after physical evidence:** Merge/qualify #1189/#1201 separately and prove eight-Site isolation and recovery. No suggestion to remove retry/UNCERTAIN protection for OTP, protection registers or irreversible operations.

**No automatic deletion authorization:** The terms **REVIEW_DUPLICATION** and **REVIEW_DEPLOYMENT** are candidates for an independently reviewed source change only after an equivalent mechanism passes Host tests and applicable Z2 HIL. Prototype convenience alone does not justify silent FPGA, OS or electrical bypass.

## 5. Negative acceptance contracts

Host-only tests on this Gate 1 assert: bad roles/actions fail closed; Monitor cannot program/modify/export target data; Master cannot replace Root or manage Linux; Engineer capability is classified without simulated root grant; Root Entry rejects unknown operations; non-root protected Root calls refuse before hardware; Program Session explicitly marks whole-system scan NOT_RUN while maintenance retains its scan. These tests do **not** assert deployed Z2 permissions, real FPGA reload mutual exclusion, GPIO/AXI behavior or safe in-flight power recovery.

**Residual fact:** Root can bypass cooperative `flock`. Full safety against arbitrary privileged processes is not established by these rules; maintenance procedures must quiesce affected hardware explicitly.
