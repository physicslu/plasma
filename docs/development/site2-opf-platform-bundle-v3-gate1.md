# Site 2 OPF platform-provider Bundle v3 source alignment — Gate 1

Status: **Draft / Host-only**. Does not grant Gate 2, merge, deployment,
FPGA load, C-3 session, or DUT operation.

## Observed evidence

On Z2, Active Asset Set generation 7 (archive SHA-256
`4efe0fea45cd71e48f4de53318f4a4fb863c2332bab8a04affbcdd26fce52a8d`)
contained a `platform-provider` Package named
`openocd-platform-reference` with BOTH
`data/plasma-provider-options.json` and the retired
`data/plasma-platform-engine.json`. The existing
`ppu_provider_contract.resolve()` rejects the extra file with
`PROVIDER_ENTRYPOINT_MISSING` before opening a C-3 Flash session.
The Site 2 Job ended `E4005 / OPERATION_UNSUPPORTED`; readback was **NOT_RUN**.

The current main source contains the OPF-4A exact-file-set contract and a
negative regression test for the retired reference. Generic Bundle v3 B2/B3
admission deliberately admits opaque non-executable resource files. That
generic validation does **not** authorize OPF Job execution. In particular,
do not weaken Provider resolution to accept the old file and do not edit an
already-staged/active Asset Set in place.

**Provenance gap:** no tracked main-branch source for the Z2 Gen7 producer
(`openocd-platform-reference` ID) was found by GitHub default-branch code
search. Gen7 may have been created by an external/local engineering producer,
but its origin is **NOT_VERIFIED**. This Gate 1 does **not** assert that the
unknown original producer has been patched. It adds a constrained, audited
replacement producer for future profile-only Bundle v3 artifacts.

## One engine-selection authority

- The Bundle's `programming-profile` carries the target capabilities,
  Flash geometry, compatible `driver_abi` and Provider reference.
- The Bundle's `platform-provider` carries **only**
  `data/plasma-provider-options.json`. It has no executable, engine path,
  Engine binary SHA, Admission SHA or FPGA reload request.
- Root-owned `/etc/plasma/site-worker-engine.json` remains the sole
  Engine Selection authority. `ppu_site_engine.load_engine(require_root=True)`
  verifies its selected installed Engine independently.
- The installed FPGA can be referenced through
  `fpga_package: null` only with current trusted Worker/PL Identity, ABI,
  Site ownership and Root admission. The builder does not verify hardware.

## Canonical offline builder

`scripts/opf_platform_bundle_v3_build.py` generates a deterministic
**two-Package, profile-only** Bundle v3 for the current OPF-4A route:

1. `platform-provider`, exactly one Options Schema JSON, no code.
2. `programming-profile`, exactly `plasma-provider.json` and
   `plasma-flash-profile.json`, dependent on that Provider.

Its source directory must contain **exactly** these three files:

```text
source/
  plasma-provider-options.json
  plasma-provider.json
  plasma-flash-profile.json
```

`--target-json` is a separate file with the canonical
`platform`, `board`, `fpga_part` identity of the destination PPU.
The caller supplies Package IDs, Bundle name, and version; no OpenOCD path,
Image ID, particular Site, or MCU model is hardcoded by the builder.

Example (source files must first be constructed/reviewed from independent
source data; do not copy the retired Engine reference into this directory):

```bash
python3 scripts/opf_platform_bundle_v3_build.py \
  --source /path/to/reviewed/source \
  --target-json /path/to/ppu-target.json \
  --provider-id openocd-platform-reference \
  --profile-id stm32f103c8t6-site2 \
  --name site2-opf-profile-only --version 1.0.0 \
  --output /path/to/new-profile-only-v3.zip
```

This prints the new archive SHA256 and `GENERIC_HOST_ONLY_PASS`. It does
not install, activate, or run the ZIP. It fails closed on unexpected source
files, including `plasma-platform-engine.json`, rejects malformed
descriptor/Flash geometry/Options data, and refuses to overwrite an existing
archive. Complete ZIP SHA256 changes even if the same target, Provider ID
and firmware are retained. Do not reuse the Gen7 archive SHA or receipts.

## Host-only regression evidence

```bash
python3 -m pytest -q software/python/tests/test_opf_platform_bundle_v3_build.py
python3 -m pytest -q software/python/tests/test_opf_4a_openocd_reference.py
```

The new tests cover deterministic output; exact Provider/Programming Profile
files; generic Bundle v3 verification; test-only B3 staging/Active selection;
OPF Provider resolution using synthetic trusted observations; retired file,
mismatched Provider, unqualified FPGA dependency, bad ABI and geometry, duplicate
JSON keys, and overwrite refusal. A synthetic `IMAGE` observation in tests
is **not** HIL qualification.

## Gate 2 / hardware boundary

Before approving a merge, check the Draft PR's exact HEAD and relevant hosted
CI. Verify which engineering source actually produced Gen7; update that source
to use this builder (or an equivalent exact-file-set contract), or explicitly
record that provenance remains unknown. Neither the new builder nor CI proves
a DUT Flash PASS.

A subsequent separately authorized deployment must use normal Bundle v3
B1/B2/B3 with the **new ZIP SHA** and trusted owner authorization. Preserve
the immutable Gen7 Set as evidence. Do not edit `active.json` or staged
`manifest.json` directly. Only after exact installed-version and live
FPGA/ABI/Worker checks may a new Site 2 `flash_cycle` be attempted.
