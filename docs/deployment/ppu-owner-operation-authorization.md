# PLASMA Owner Operation Authorization — user-programmable Bundles

Status: Gate 1 Stage A / Host-only. Z2 deployment, FPGA load and DUT
**NOT_RUN**. Replaces the retired Bundle Authority v2 per-Bundle SHA256
allowlist (`/etc/plasma/ppu-bundle-authority.json`,
`plasma.ppu.bundle-authority.v2`, `LOCAL_APPROVED`).

## Product decision

PLASMA is an owner-operated, **user-programmable** IC programmer. A user who
is authorized to operate the device may upload, admit, install and request
execution of **their own** Bundle v3 Packages (FPGA, Python, Native C,
Programming Profile, …) through Console → Manager → PPU.

- No Bundle SHA256 needs to be pre-written into a device allowlist.
- Normal operation needs no SSH, sudo or Linux configuration edits.
- **Operator authorization ≠ Package safety.** Being allowed to *ask* never
  waives Bundle v3 format, SHA256 integrity, Target, Package DAG, Active Asset
  Set, FPGA qualification, Owner Lock, Journal, Recovery or Linux privileges.

## One authorization per explicit operation

Schema `plasma.ppu.owner-operation-authorization.v1`
(verifier: `scripts/ppu_owner_authorization.py`; Manager issuer:
`software/python/plasma_manager/owner_authorization.py`; SWPC CLI issuer:
`scripts/ppu_deploy_api.py`, which reuses the verifier module).

```json
{
  "schema": "plasma.ppu.owner-operation-authorization.v1",
  "action": "bundle.admit | bundle.install | bundle.activate | bundle.activate-fpga-load | asset.execute",
  "device_id": "ppu-device-<hex>",
  "subject_sha256": "<exact Bundle archive == Asset Set SHA256>",
  "transaction_id": "<B1 upload_id | current B2 transaction_id | Runtime job_id>",
  "package_identity_sha256": null,
  "mac": "<HMAC-SHA256>"
}
```

`mac = HMAC-SHA256(K, canonical-JSON(claims))`, with
`K = HMAC-SHA256(paired Bootstrap credential, "plasma.ppu.owner-operation-authorization.v1/key")`.

| Stage | Action | `transaction_id` | PPU derives itself |
| --- | --- | --- | --- |
| B2 Admission | `bundle.admit` | B1 `upload_id` | device ID, committed upload SHA256 |
| B3 `stage_only` Install/Verify | `bundle.install` | **current** B2 `transaction_id` | device ID, re-hashed archive, current journal |
| B3 `activate`, no FPGA load | `bundle.activate` | current B2 `transaction_id` | same, explicit mode |
| B3 `activate` + FPGA load | `bundle.activate-fpga-load` | current B2 `transaction_id` | same, explicit mode and `fpga_load:true` |
| Runtime Dispatch | `asset.execute` (+ `package_identity_sha256`) | Runtime `job_id` (== Job lease) | Active Set SHA256, Package identity |

Each stage verifies its **own** fresh authorization against facts the PPU
derived (device identity from `/etc/machine-id`, the bytes it hashed, its own
current journal/Active Set). A B2 receipt is never install authority, a B3
receipt is never execute authority, and a stage-only authorization cannot be
widened into activation or FPGA load.

What the MAC is and is not: it adds **no** strength over the Bearer
credential itself. It binds the user's explicit choice to one exact
operation so a receipt or earlier authorization cannot be replayed for a
different action, Bundle, device or transaction, and rotating the pairing
credential invalidates every outstanding authorization. It is not a
publisher signature; publisher authenticity and transport confidentiality
remain `not_qualified`.

Freshness without trusting the SWPC clock: B3 must name the PPU's
**current** B2 transaction (a new B2 or any B3 supersedes it) and start within
`B2_ADMISSION_TTL_S = 3600` s of admission by the PPU's own clock.

No new database: nothing about authorizations is persisted except the
verified summary (no MAC/secret) inside the existing B2/B3 deployment
records. No Publisher, Git Commit Pin, per-Bundle admin approval or parallel
authorization store exists. User Bundle v3 `source_commit` is optional,
untrusted provenance: omission is valid through B1/B2/B3, and a claimed
commit grants no qualification. User ZIPs need not originate in GitHub and
need no publisher signature or CI whitelist. Engineering Runtime Release,
factory/CI identity and trusted Dispatcher Work Order pins remain mandatory
under their independent contracts.

## Console → Manager → PPU

- Console B2 body: `{kind:"bundle", upload_id, archive_sha256}` — the SHA256 of
  the file the user selected.
- Console B3 body: `{kind:"bundle", upload_id, archive_sha256,
  admission_transaction_id, mode, fpga_load}`; `mode` is exactly `activate` or
  `stage_only`, and `stage_only` requires `fpga_load:false`.
- Manager (paired, device-bound credential) issues the authorization and
  forwards `{kind, upload_id, mode, fpga_load, authorization}`. Callers can
  never supply their own `authorization` field through the Manager.
- PPU Bootstrap: 401 without the Bearer credential; 409 for any denied
  binding. B1 upload and B2 admission never install or execute; FPGA load
  and Python/Native C execution each still require their own explicit request.

## Unchanged safety boundaries

Factory `ppu-bundle-install-policy.json` (Bundle-independent capability,
actions `install`/`verify` only), trusted Target profile, FPGA Image static
qualification contracts, Root Entry/Root FPGA Guard, Owner Lock, Journal,
Recovery, Active Asset Set and Identity readback are unchanged. Python/Native
C production executors remain `NOT_WIRED` (see Stage C plan); the Runtime
dispatch seam already requires the `asset.execute` authorization and a
matching Job lease.

## Migration

- Z2 still runs the #1252/#1266 Bootstrap until an approved deployment. The
  old `/etc/plasma/ppu-bundle-authority.json` is simply unused by the new
  code; removal belongs to that deployment, not this PR.
- Old B2 records (`source_authorized`, `plan.authorization`) are not accepted
  by B3: re-run B2 after upgrade.
- HIL tools must send owner authorizations (`BootstrapAPIClient` does this).

Do not claim Z2 privilege, FPGA load, Golden recovery or DUT qualification
from Host-only tests.
