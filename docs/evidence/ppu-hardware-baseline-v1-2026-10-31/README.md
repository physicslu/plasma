# PLASMA Z2 Physical Package Baseline v1 — Path 2 Evidence

Status: **Physical B1 Receive PASS; B2-v1 Integrity/Admission PASS; B2-v2 Bundle NOT_QUALIFIED.** B3/B4, FPGA and DUT NOT_RUN.

## First real positive acceptance — directly through existing engineering-mode SSH to Bootstrap API

- [GitHub workflow Run #41154668038](https://github.com/physicslu/plasma/actions/runs/41154668038), `development-execute` on `SWPC-plasma-codex`.
- Exact first successful source SHA: `acc3e87fa6188fd82a29d761f716be5e04593974`.
- Work Order SHA256: `0f8800d49184ab29f570e80dfe0c7153b17b7a8813ed8052a8c8a2d64b5b54b4`.
- Real process: **Exit 0**, stdout SHA256 `6a7bca66b89e67af7edd406ec6752c7df69de5f715e7db3333f56ac424633c70`, no stderr.
- Evidence artifact: `plasma-development-cli-41154668038` (raw process receipt and sanitized JSON output).
- Physical device ID: `ppu-device-7ed4b30913a9bf6101da5a7a`; Bootstrap version `0.1.0`, API version `1`, Runtime `runtime_active`.
- Engineering transport: existing SWPC worker enrolled SSH account / pinned known_hosts, existing protected Z2 sudo control-token read **into process memory only**, followed by private-LAN HTTP Bootstrap `:18081`. No Manager registry or paired Manager required. No credential value included in any evidence or Work Order. This commissioning transport is **NOT qualified for production TLS**.

| Real Z2 tier | Result | Source-of-truth evidence |
|---|---|---|
| B1 Receive/Commit | **PASS** | Real Z2 accepted 701 bytes, archive SHA256 `eaa03e92721482c3dc8be2b7b3dc9055e287d6a442e788c4108fab5f307b2b3b`, Upload ID `d6bf049f696d4ab9a248a84694bc1c22` |
| B1 negative SHA | **PASS** | Deliberate wrong chunk SHA256 was rejected as `CHUNK_SHA256_MISMATCH`, verified specific response, then correct chunks committed |
| B2-v1 Integrity/Admission | **PASS** | Transaction ID `94ea95005714452bb1021b358f08684c`, `stage=package_admission_only`, `execution_permitted=false`, `install_qualified=false` |
| B2-v1 negative file SHA / target | **PASS** | Actual Z2 rejected `PACKAGE_FILE_SHA256_MISMATCH` and `PACKAGE_MANIFEST_CONTENT_DENIED` |
| B2-v2 Bundle Admission | **NOT_QUALIFIED** | Installed Z2 rejected Bundle v2 Admission; original Run classified `DeploymentAPIError`; the installed verifier's exact source SHA is NOT_ATTESTED, so do not assume a specific incompatibility cause |
| B3 Install / B4 Activate/Rollback | **NOT_RUN** | No install or activation API was called |
| FPGA / DUT | **NOT_RUN** | No PL load, probe or IC programming |

**Conclusion:** B1 Receive and B2-v1 Admission are valid independently reusable **physical** Baseline tiers. B2-v2 requires separate on-device verification/qualification; it cannot invalidate B1 or B2-v1.

## Historical diagnostics prior to successful direct API execution

| Step | Real Run | Observed result |
|---|---|---|
| Z2 read-only identity/version | [41098395015](https://github.com/physicslu/plasma/actions/runs/41098395015) | PASS; Z2 device ID and Bootstrap `0.1.0` |
| Initial standalone CLI token-file requirement | [41099568098](https://github.com/physicslu/plasma/actions/runs/41099568098) | `PRIVATE_TOKEN_FILE_NOT_PROVISIONED`; B1/B2 NOT_RUN |
| Control Manager paired probe | [41150496276](https://github.com/physicslu/plasma/actions/runs/41150496276) | `MANAGER_PHYSICAL_TARGET_NOT_ENROLLED`; B1/B2 NOT_RUN |
| Manager registry inventory | [41150656253](https://github.com/physicslu/plasma/actions/runs/41150656253) | :18180 unavailable; :18280 has no real Z2 alias |
| Owner-approved Manager registry enrollment | [41151768961](https://github.com/physicslu/plasma/actions/runs/41151768961) | `ENROLL_REGISTRY_NOT_MUTABLE`, no POST mutation; B1/B2 NOT_RUN |
| SWPC Manager fixed-path/runtime inspection | [41154085590](https://github.com/physicslu/plasma/actions/runs/41154085590) | Read-only; no Manager or credential change |
| First direct SSH+API attempt | [41154527571](https://github.com/physicslu/plasma/actions/runs/41154527571) | Existing Status API has no `ok` field; fixed host acceptance parser |

The earlier Manager limitations remain relevant to **Control Station managed deployment** but are **not dependencies for the engineering-mode direct SWPC→Z2 Bootstrap acceptance**. No Manager config, persistent Registry, pairing credential, or PPU service was changed.

## Qualification and reproducibility rules

1. Always run from open owner PR exact candidate HEAD under existing Issue #981 trusted `main` Dispatcher, `path2-cli` / `operator-cli` / `guarded-hardware` on `SWPC-plasma-codex`.
2. The CLI must verify exact pinned physical device ID before the first write; SSH uses enrolled Z2 login and pinned host key, root-protected existing token is only held in transient memory and never written, logged or printed.
3. Positive receive is proven by real committed bytes, archive SHA, Z2 Upload ID. Negative SHA/target cases must be **rejected by the Z2 verifier**, not by a busy Manager or missing pairing.
4. B2-v1 and B2-v2 are independent; retain explicit NOT_QUALIFIED on missing physical Bundle v2 evidence. `exit 0` is not a blanket PASS for all tiers.
5. Receipts must preserve true GitHub Run, Job, source SHA, stdout SHA256 and Work Order SHA256. Do not substitute host-only CI or simulator results.
6. Never infer installed Z2 Bundle verifier source SHA or Publisher/Master install authority; never install/activate/rollback, reconfigure FPGA, use DUT or modify Factory Recovery as part of B1/B2.
