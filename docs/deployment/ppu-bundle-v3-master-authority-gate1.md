# Bundle v3 — One Master Authority and FPGA Static Qualification for All Executable Assets

**Gate 1 scope:** Host-only implementation; no Z2 update, FPGA load, executable
Package launch, signing-key handling, or automatic activation.

## Decision

An incoming Bundle is a set of inert Assets. B2 must independently establish
that the **exact complete Bundle** was approved by the device owner/Master
before returning canonical Bundle B2 `PASS`. All kinds, including Python,
Native C and FPGA Image, use the **same** authorization.

An exact SHA256 is an *identity*, not a signature. In Development Mode,
the independent authorization method is a **root/service-owned, pre-provisioned
Master grant for that exact Bundle ZIP SHA256**. This is a concrete Master
approval of specific bytes, not cryptographic proof of the claimed
Publisher's identity. A future trusted Publisher signature can substitute
for the grant source without changing the B2/Execution layer boundaries.

The root/service-owned policy is
`/etc/plasma/ppu-bundle-authority.json` (regular file, 0600,
no symlinks, local service owner). It **does not ship in the factory kit**;
an owner must provision it separately. B1 uploads, HTTP headers, Bearer
tokens, Manifest fields and root-installed `ppu-bundle-install-policy.json`
cannot edit or replace it.

## Single B2/B3 authority flow

```text
Console sends complete Bundle v3
    -> B1 commit and checksum
    -> B2 canonical ZIP/Package/Target/DAG verification
    -> B2 compare exact complete ZIP hash against device-owned Master grant
       (source commit, target, purpose, kinds, generation, expiration)
    -> B2 static FPGA qualification of every fpga-image Package
       (Root Manifest parser + factory-shipped trusted Target/ABI contract)
    -> B2 PASS with source_authorized=true; execution_permitted=false
    -> B3 reverify same ZIP, current Master authority and current
       FPGA static qualification (any drift since B2 fails closed)
    -> Install-only immutable Staging
    -> [separate controlled Active Set activation]
    -> [separate explicit Asset execution request]
```

No FPGA-specific allowance, separate Root Approval Database or fixed Package
combination is used. A Bundle with any unapproved kind, expired/revoked
grant, changed digest/target/source, or missing policy fails closed. B3
also refuses if the grant changed after B2.

### Minimal policy structure (illustrative; **not an approved release**)

```json
{
  "schema": "plasma.ppu.bundle-authority.v1",
  "master_generation": 1,
  "authorizations": [{
    "publisher": "open4th-lab",
    "archive_sha256": "<full, previously reviewed SHA256>",
    "source_commit": "<reviewed forty-character Git commit SHA>",
    "target": {
      "platform": "linux-armv7",
      "board": "pynq-z2",
      "fpga_part": "xc7z020clg400-1"
    },
    "purpose": "programming",
    "allowed_kinds": ["python", "native-c", "fpga-image", "programming-profile"],
    "expires_epoch_s": 4102444800
  }]
}
```

The actual Bundle `packages[].kind` set must be contained in
`allowed_kinds`. Actual grant policy must match the exact deployed
Bundle and all of its other Package types. Missing required kinds result
in rejection. No Wildcards; no SHA prefix matching; no Bundle-named hard
coded execution path. Multiple independent grants may coexist.

## FPGA static qualification (B2)

An FPGA Image is an ordinary Asset of the same Bundle. It uses the same B2,
Master grant, B3, Asset Set identity and Active Set as Python and Native C.
There is **no** FPGA-specific approval, installer, deployment API, daemon,
lock or journal. B2 adds only these static checks
(`scripts/ppu_fpga_qualification.py`):

1. **Structure.** An `fpga-image` Package contains exactly one BIN, one HWH
   and one `plasma.fpga.image.v1` Image Manifest under `fpga/`, matching the
   Z2 Root Loader contract. A Vivado `.bit` is not a Z2 loader Asset.
2. **One parser.** The Manifest is parsed by the existing protected Root
   parser `pl/hil/fpga_image_root.py::parse_image_manifest_bytes()`. The
   factory Bootstrap ships that parser (with its `fpga_image_guard` /
   `fpga_image_admission` imports) at `<bootstrap>/pl/hil/`; importing it has
   no firmware, FPGA Manager or MMIO effect.
3. **Pairing.** BIN path equals the Manifest `firmware_name`; BIN SHA256
   equals Manifest `firmware_sha256`; all three files are re-hashed from the
   committed ZIP.
4. **Target.** Manifest board/FPGA part equal the device-trusted
   `/etc/plasma/ppu-package-target.json`, not the Bundle claim.
5. **Independent trusted contract.** Image identity, BIN/HWH/Manifest
   SHA256, ABI, one-based Site identities, Site bitmap and AXI/owner geometry
   must equal an entry in the factory-Bootstrap-shipped
   `ppu-fpga-image-contracts.json` (reviewed in this repository, installed
   `0644` beside the Bootstrap, never writable through B1/B2/HTTP).
6. **Fail closed** on a missing/untrusted contract file, unknown image, any
   SHA/ABI/Identity/Site/geometry/Target mismatch, or a Manifest the Root
   parser rejects.

The shipped contract currently holds one entry,
`swd-independent-abi5-ab79b04e`: build `ab79b04e`, ABI `0x00050001`,
Site 1 Identity `0x00050001` at offset `0x0000`, Site 2 Identity
`0x00050002` at offset `0x1000`, Site bitmap `0b11`, with the BIN/HWH/
Manifest SHA256 values from the **draft** PR #1247 fixtures. This is a static
expectation only: PR #1247 is not assumed merged, deployed or HIL-qualified,
and a statically matching Manifest is **not** evidence of an Identity
readback.

### B2 PASS semantics

B2 `PASS` means: the Bundle source is Master-authorized; every Package passed
its applicable static verification; every FPGA Image (if any) is statically
qualified for the trusted target; the Asset Set may wait for B3 installation
and a later explicit selection. The receipt carries
`source_authorized=true`, `fpga_static_qualification`
(`STATIC_QUALIFIED` or `NOT_APPLICABLE`), `fpga_loaded=false`,
`identity_readback=NOT_RUN` and `plan.execution_permitted=false`; the SWPC
client (`scripts/ppu_deploy_api.py`) rejects a receipt that deviates.

B2 `PASS` does **not** mean that Python/Native C ran, FPGA was loaded, FPGA
Identity was read back, DUT electrical conditions are safe, or a Programming
Job is authorized. B2 never triggers an FPGA load.

## Execution trust is distinct from B2 legality

A B2 PASS grants legal **selection/installation** of Assets within its
approved Set. It does not grant arbitrary code execution. At execution
time the PPU must still verify the single Active Set digest and the
current Master grant; an explicitly selected trusted Executor performs
the operation. Python is not dynamically imported from an upload;
Native C is not launched via arbitrary Bundle-defined shell commands;
FPGA loading continues to use the sole protected Root FPGA Loader with
Runtime/PS–PL ownership and Golden recovery checks. FPGA Identity and IC
qualification are observed only after physical operations.

## Evidence and next work

- Root-policy parsing, exact digest/source/target/kinds/expiry, tamper,
  B2 and B3 grant withdrawal use Host-only tests.
- FPGA static qualification uses Host-only tests with **synthetic** BIN/HWH
  bytes and a test-only contract
  (`software/python/tests/ppu_fpga_qualification_fixture.py`); they are not a
  Vivado build or FPGA acceptance. The shipped ab79b04e contract is checked
  against a byte-exact copy of the PR #1247 draft Manifest only.
- No claim of production Publisher cryptographic authenticity, production
  TLS confidentiality, arbitrary Bundle execution, or live device safety.
- The separate trusted Master provisioning process and real on-device
  integration are **not implemented** here; an unprovisioned device rejects
  canonical Bundle B2 admission.
- Actual FPGA load stays with the existing protected Root FPGA Loader and its
  Controller authorization, Single Active Asset Set check, exclusive FPGA
  ownership/lock, Runtime/Site Job quiescence, current-boot/hardware
  admission, Golden recovery and post-load ABI/Identity readback.
- Plasma Manager and Web still check only the non-executing shape of a B2
  receipt; the PPU enforces FPGA static qualification.
- Next change: one Asset Execution dispatcher used for every executable
  kind, with existing verified runtime/FPGA Executors rather than a second
  FPGA installation path.
