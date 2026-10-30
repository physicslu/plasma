
# PPU Deployment Engine PR2 Gate 1 — Generic Bundle v2 (Host-only)

Status: **Gate 1 Draft**. Based on main cb8fcf63d353320618d2de42af0f7e9ae90ad3b1, containing PR #1219 and #1221. No merge, real installation, service restart, SWPC/Z2/FPGA/DUT operation or rollout is authorized.

## Boundary and architecture

The deployment unit is an immutable **Bundle of components**, not a programming language or an FPGA image. SWPC Engineering CLI and Web Console (Browser -> BFF -> Manager) are distinct clients of the **same existing PPU Bootstrap API**; the Browser must never receive PPU credentials. The PPU owns one DeploymentCoordinator, deployment.lock, deployment.json, transaction evidence, and independent Factory Recovery. No second daemon/installer/lock/journal.

PR1 v1 accepts one kind (python, native-c, fpga-image). PR2 v2 supports **multiple components** and retains PR1 v1 admission unchanged.

## Bundle v2 contract

ZIP: manifest.json and only declared files under payload/components/<component-id>/.

Manifest schema: plasma.ppu.bundle.v2. Fields are exact:

- name, version, source_commit (40 lowercase hexadecimal characters; **self-reported, not proof**)
- purpose: such as programming, diagnostics, experiment, system; **never privilege**
- target: exact platform, board and fpga_part, matched against a private device-owned profile
- components: id, kind, version, requires (other component IDs), files (path, sha256, size, executable)
- optional actions: install, verify, activate, rollback (declarative only)

Component kinds are extensible identifiers, **not an executable allowlist**. Python, Native C and FPGA Image have strict per-kind file shape checks. Arbitrary other types—including programming profiles, IC catalogs, firmware assets, OpenOCD configuration, calibration, AI model, diagnostic data, or future types—may contain ONLY non-executable opaque data/assets files. Ingestion must never automatically execute, program, load, configure or grant authority over these bytes.

Require a valid dependency DAG, exact SHA256 per file and archive, no duplicate IDs/paths/JSON keys, no traversal, symlinks, ZIP special files, undeclared files or incompatible targets. Preserve PR1 v1 input bounds of 32 MiB total uncompressed files and 128 payload files for this Host-only iteration; Bundle v2 caps components at 32. These limits are NOT a final production image-size policy. Valid SHA256 does not establish approved publisher/source provenance.

## Implemented Gate 1 boundary

Existing Bootstrap /v1/uploads and POST /v1/deployments accept kind=bundle for **admission only**: state=admitted; stage=package_admission_only; install_qualified=false; plan.execution_permitted=false. Plans and receipts describe purpose, components, target and hashes; no live installation worker is launched. Existing PS Runtime API behavior is unchanged.

The existing Coordinator internal execute_package_host_only() uses the same lock and journal to simulate Bundle v2 file staging, exact staged-file verification, active-version receipt switch, failure-injected rollback, and recovery_required on uncertain restoration. Only an isolated temporary test directory is writable. It never changes /opt/plasma, systemd, native executable permissions on the device, FPGA Manager, Site power, Factory Recovery or DUT. None of the Bundle's contents is executed.

Host-only tests exercise multi-component positive cases, arbitrary resource kinds, local HTTP loopback admission, missing and cyclic dependencies, changed hashes, unauthorized executable flags, wrong targets, symlink/undeclared member rejection, v1 compatibility, version rollback and uncertain recovery.

## Explicit later gates — NOT authorized now

1. Production TLS, signed/approved publisher provenance, live revocable Master and purpose-based authorization.
2. Trusted per-kind installation/activation policy with bounded on-device ownership and permissions; inventory, migrations and recovery guarantees.
3. SWPC **and** Web Console BFF/Manager end-to-end transport, transaction correlation, receipts, cross-host recovery and idempotency.
4. Site/job quiescence plus special FPGA image/HWH/ABI/Root Guard/Golden safety; no redundant Base FPGA distribution.
5. Separately owner-approved physical SWPC→PPU, FPGA and DUT HIL.

Stop on ambiguous journal/recovery, unknown publisher, incompatible target, invalid dependencies or unqualified hardware. A Host-only PASS is never permission for live deployment.
