# Bundle v3 — One Master Authority for All Executable Assets

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
    -> B2 PASS with source_authorized=true; execution_permitted=false
    -> B3 reverify same ZIP and current independent Master authority
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
- No claim of production Publisher cryptographic authenticity, production
  TLS confidentiality, arbitrary Bundle execution, or live device safety.
- The separate trusted Master provisioning process and real on-device
  integration are **not implemented** here; an unprovisioned device rejects
  canonical Bundle B2 admission.
- Next change: one Asset Execution dispatcher used for every executable
  kind, with existing verified runtime/FPGA Executors rather than a second
  FPGA installation path.
