# OPF-4A — OpenOCD / ABI v5 Reference Provider (Gate 1)

**Status:** Production REST Runtime source cutover; validation is Host-only, not HIL qualification.
**Scope:** One selected Bundle v3 Active Asset Set, one `flash_cycle` Job, one existing C-3 Site Worker.

> **Gate 1 candidate (Draft only):** Reuses and revises the source patch from Run #42022044418. No HIL qualification, deployment, or Gate 2 approval is implied.

## Execution contract

`ppu_opf_reference_openocd.qualify_reference` first delegates Provider/Profile/Options
admission to `ppu_provider_contract.resolve` (OPF-2) and the existing Active Set
verifier. It permits `fpga` / `flash_cycle` and accepts only an empty Provider
Options object for this Reference implementation. It then checks:

1. A `platform-provider` metadata Package references the independently installed
   universal Engine without shipping its C driver or FPGA Image. Its only Engine
   reference is non-executable `data/plasma-platform-engine.json`, with exactly
   `schema: "plasma.ppu.platform-openocd-reference.v1"`, `openocd_sha256`,
   `admission_sha256`, and `driver_abi`. All values must equal the Engine checked
   by `ppu_site_engine.load_engine(require_root=True)`. No command or path is
   accepted. Its Options Schema is `data/plasma-provider-options.json`; the
   Profile requires this Provider in the same verified Active Set. Generic v3
   opaque-resource admission remains unchanged and confers no execution grant.
   Alternatively, an explicitly selected `native-c` Provider contains `bin/openocd`
   whose SHA-256 is **exactly** the installed, independently verified OpenOCD
   selected by the root-owned `site-worker-engine.json` record. The existing
   Engine verifier separately validates the installed admission-helper SHA-256;
   native-c Bundle v3 does not admit arbitrary `libexec/` files.
2. Selected Profile Package contains `data/plasma-flash-profile.json`, schema
   `plasma.ppu.openocd-flash-profile.v1`, with exactly `icpn`, `target_config`,
   `flash_base`, `flash_size`, and `erase_granularity` fields plus `schema`.
   These verified values must match the trusted Runtime's existing exact-ICPN
   `C3FlashProfile`; a Bundle cannot override the admitted geometry silently.
3. Capability `driver_abi` must exactly equal the selected engine's actual
   `<adapter_driver>:<driver_abi>`, e.g. `plasma_swd:5`. Independently verified
   device-side observations must also match platform, image identity and driver
   ABI. `fpga_package: null` permits an independently installed FPGA; a declared
   FPGA Package must remain a dependency in this Active Set and match its Image.
   Neither route requests an FPGA reload during programming.

There is **no** baked-in FPGA Image ID, OpenOCD installation path or version,
and no Provider-supplied command-line, Tcl, timeout bypass or Root privilege.

`execute_reference_flash` passes the qualifying OPF-3B route into the existing
`ppu_opf_site_session.open_provider_job_session`. It then invokes the same
`plasma_interfaces.site_worker_c3.run_flash_cycle` implementation already used
by the current REST Runtime, with an optional qualified Session opener. The
remaining sequence is unchanged: stage Job image, C-3 `bind_image`, C-3 `run`,
full readback SHA/length evidence, C-3 `close_session`, cleanup. C-3 alone
owns Site ownership, Job lease verification, operation timeout, SAFE_OFF and
persistent seals; the existing Runtime alone owns Job retry policy. This PR
introduces **none** of those controls.

## Production Runtime binding

`PackageActionRuntime` wires configured C-3 OpenOCD interfaces to the reference
executor using its configured product root. SiteWorker supplies the admitted
Job's pinned Active Asset Set and original monotonic deadline on every attempt.
The executor verifies the Set, resolves its Profile and declared Provider, and
binds the installed Engine and exact-ICPN Runtime profile before C-3 admission.
An unwired or invalid OPF route fails closed without direct-C3 fallback.

The authenticated Worker supplies its installed adapter's platform, loaded image
identity and supported Sites. The Runtime verifies current boot and valid Image
observation before deriving hardware admission inputs; Bundle target fields are
only requirements, never observations. Exactly one hash-verified Programming
Profile is required even when the Bundle contains no FPGA Image. FPGA handoff
resolution is used only for FPGA-bearing Bundles.
OPF checks loaded-image matching and pins that observation to the opened Session.
Historical manifest SHA and test-count qualification are not per-Job gates.
Root/native admission retains same-boot and live PL checks,
the reload fence and Site lock. Existing C-3 identity-change checks, lease checks,
seals and SAFE_OFF remain authoritative throughout execution. A qualified,
unchanged session does not require requalification for an ordinary Job.

## Verification and retained boundaries

- Host-only tests build and B3-install a real Bundle v3 ZIP, publish its
  verified Active Set in an isolated test directory, then traverse the real
  C-3 Unix protocol into the existing ABI-v5 OpenOCD Adapter. The **process
  edge only** is simulated; this is not a Mock Provider.
- Negative cases include wrong Active Set, stale/unknown FPGA observation,
  unsupported Options/Site, incorrect Job deadline, wrong OpenOCD digest,
  wrong ABI, incompatible Flash Profile, missing C-3 lease, and readback
  mismatch with persistent Site sealing. See
  `software/python/tests/test_opf_4a_openocd_reference.py`.
- Production `plasma-server` Runtime routing changes for C-3 Flash only; no
  Bootstrap/B3 Activation change, no Site 2 HIL or DUT/FPGA/SWPC/Z2 operation. In
  particular, Draft PR #1278's B3 Activation semantics are not modified.
- The Provider's reference metadata (or explicitly bundled `bin/openocd`) is
  bound to the selected Engine. This is not a distinct signed Driver Package
  qualification; installed Engine ownership/SHA verification and live native
  admission remain authoritative.
- The Worker pins its actual Adapter on startup. The selected Engine record
  is now bound in the existing authenticated C-3 `open_job_session` exchange:
  the root-owned Worker snapshots the SHA-256 of its verified Engine Selection
  record at startup, rejects an OPF-4A Job whose expected digest differs, and
  echoes that digest plus its Worker epoch in the accepted Session receipt.
  Missing/unverified Worker binding or a missing/mismatching receipt fails closed
  before Flash. Changing Selection without Worker restart cannot silently
  change the running Adapter. This is Host-only contract evidence, not a Z2 HIL
  observation or hardware execution authorization.
- The trusted Runtime must obtain `hardware` independently on-device. Test
  observations are synthetic inputs, **not** proof of real Image/ABI/PL
  compatibility. The full authorization/ownership/Timeout chain still needs
  live Site 2 HIL before declaring physical Flash PASS.

## Next Gate

Gate 2 can review this narrow Host-only PR after required hosted CI PASS.
This source cutover requires exact-HEAD Gate 2 review and CI. Hardware acceptance
remains NOT_RUN until separately authorized Site 2 HIL.
