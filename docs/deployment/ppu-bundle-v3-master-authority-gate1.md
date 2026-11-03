# PLASMA Bundle v3 — single-machine local approval (PR #1252)

Status: Gate 1 / Host-only; Z2 deployment **NOT_RUN**.

## One authority, one exact checksum

Only one device-managed source of Bundle permission exists:
`/etc/plasma/ppu-bundle-authority.json` (0600, trusted service UID).
It is independent of uploaded files and the network caller. Canonical v2:

```json
{
  "schema": "plasma.ppu.bundle-authority.v2",
  "generation": 1,
  "approved_bundle_sha256": ["<exact-64-hex-archive-digest>"]
}
```

An empty list revokes all grants. Increment `generation` on each operator
change; the exact policy hash is also recorded in authorization receipts.
No publisher claim, Git Commit Pin, expiry, Package Kind allowlist or
duplicate Target check is stored in the policy. **This is not a digital
signature and SHA256 alone does not authorize anything.**

B2, B3 and Runtime Package Action all reread this single policy on use.
A previously approved B2 receipt cannot override an updated/revoked local
policy. Source Commit may appear in canonical Bundle v3 as build metadata,
not as a permission to execute. Device-level target and package checks
remain in the canonical verifier; FPGA-specific BIN/HWH/Manifest, Target,
ABI, Site capabilities, Identity and AXI contract are separate and required.

`LOCAL_APPROVED` means only that this exact already-verified archive is
permitted to proceed to the **next** gate. Runtime Job/Owner Lock, Linux
process privileges, exact Active Set, Root FPGA Guard, identity readback,
journal and recovery remain mandatory. Python/Native C production executors
remain `NOT_WIRED`.

## Gate 1 migration

Previously installed v1 Master grant files are **not** auto-accepted by
this schema and must be replaced through an approved local operator
provisioning step. Z2 file contents, existing services and hardware have
not been modified. The credential-bearing network/Manager API is not a
policy writer. Fail closed when the v2 file is absent, untrusted or malformed.

Do not claim Z2 privilege, FPGA load, Golden recovery or DUT qualification
from Host-only tests.
