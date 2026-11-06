# OPF-4A — OpenOCD / ABI v5 Reference Provider (Gate 1)

**Status:** Production REST Runtime source cutover; validation is Host-only, not HIL qualification.
**Scope:** One selected Bundle v3 Active Asset Set, one `flash_cycle` Job, one existing C-3 Site Worker.

> **Gate 1 candidate (Draft only):** Reuses and revises the source patch from Run #42022044418. No HIL qualification, deployment, or Gate 2 approval is implied.

## Execution contract

`ppu_opf_reference_openocd.qualify_reference` first delegates Provider/Profile/Options
admission to `ppu_provider_contract.resolve` (OPF-2) and the existing Active Set
verifier. It permits `fpga` / `flash_cycle` and accepts only an empty Provider
Options object for this Reference implementation. It then checks:

1. A `platform-provider` Package uses the independently installed Engine,
   without shipping its C driver, FPGA Image, OpenOCD Binary or Admission
   Python. Its **only file** is the non-executable Provider Options Schema
   `data/plasma-provider-options.json`; the selected Profile depends on that
   Provider. The retired `data/plasma-platform-engine.json`, including
   Bundle-side `openocd_sha256` / `admission_sha256`, is not accepted:
   there is no optional field or backwards-compatible branch. The Profile's
   `driver_abi` must match the independently installed, root-owned Engine
   verified by `ppu_site_engine.load_engine(require_root=True)`. Bundle
   bytes and provenance never select an Engine or grant permission to run.
   Alternatively, a `native-c` Provider carrying `bin/openocd` must match
   the selected installed executable SHA-256 exactly; the Engine Manager
   verifies both OpenOCD and Admission Python digests independently.
   Generic v3 opaque-resource admission does not grant execution.
2. Selected Profile Package contains `data/plasma-flash-profile.json`, schema
   `plasma.ppu.openocd-flash-profile.v1`, with exactly `icpn`, `target_config`,
   `flash_base`, `flash_size`, and `erase_granularity` plus `schema`.
   The hash-verified selected Active Bundle supplies the Flash Profile for
   C-3 OPF `flash_cycle`; the Runtime checks the requested target, erase
   alignment and image-size bounds using the existing C-3 Worker validator.
   The pinned, verified Profile is bound to the Job Session. Repository exact
   ICPN IC Support, built-in Compiler IDs and static operation-admission
   projections no longer gate this route. Host-only acceptance does NOT prove
   the actual DUT's identity or physical Flash geometry. The provider's live
   `flash probe 0` is necessary but is not a proven independent capacity
   measurement contract; real multi-target HIL must verify that limitation.
3. Capability `driver_abi` must exactly equal the selected engine's actual
   `<adapter_driver>:<driver_abi>`, e.g. `plasma_swd:5`. Independently verified
   device-side observations must also match platform, image identity and driver
   ABI. `fpga_package: null` permits an independently installed FPGA; a declared
   FPGA Package must remain a dependency in this Active Set and match its Image.
   Neither route requests an FPGA reload during programming.

There is **no** baked-in FPGA Image ID, OpenOCD installation path or version,
and no Provider-supplied command-line, Tcl, timeout bypass or Root privilege.
Active Sets containing the retired Engine reference must be replaced through
normal Bundle v3 B1/B2/B3. Do not rewrite Gen7 or add legacy acceptance.
Engine Selection and Worker Session identity checks remain unchanged.

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
binds the installed Engine and Bundle-derived Flash Profile before C-3 admission.
The C-3 OPF flash_cycle does not run the SiteExecutionRouter's static IC Support,
Compiler Registry, or OpenOCDInterface recompilation; non-C-3 plan-based
software-validation paths are unchanged.
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
  unsupported Options/Site, incorrect Job deadline, corrupted installed Engine
  or bundled native-c digest, wrong ABI, incompatible Flash Profile, missing
  C-3 lease, and readback
  mismatch with persistent Site sealing. See
  `software/python/tests/test_opf_4a_openocd_reference.py`.
- Production `plasma-server` Runtime routing changes for C-3 Flash only; no
  Bootstrap/B3 Activation change, no Site 2 HIL or DUT/FPGA/SWPC/Z2 operation. In
  particular, Draft PR #1278's B3 Activation semantics are not modified.
- A `platform-provider` has no Engine Binary or Admission digest claim;
  ABI compatibility and the independently verified installed Engine are
  authoritative. A Provider explicitly bundling `bin/openocd` still binds
  its executable bytes to the selected Engine. No signed Driver Package
  qualification is introduced; native admission remains authoritative.
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
