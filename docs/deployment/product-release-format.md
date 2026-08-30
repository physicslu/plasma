# Plasma Product Release Format v1

> Status: **Current**. PR #222 established the first machine-verifiable Plasma product release contract. This document does not define or claim host installation, service registration, upgrade activation, Z2 runtime acceptance, FPGA behavior, or real IC programming.

## 1. Purpose

Plasma product deployment must consume immutable release artifacts rather than interpret the source repository on the target machine.

The boundary is:

```text
source repository
    |
    | build/test environment
    v
already-built runtime payload
    |
    v
scripts/product-release.py build
    |
    v
canonical Plasma release artifact
    |
    | later installer phases
    v
Control Station or PPU
```

`product-release.py` is a build/release tool. It is not an installer and does not run npm, pip, source compilation, service mutation, FPGA loading, or IC programming.

## 2. Product version versus component versions

Plasma has one product release identity that is separate from component package versions.

Canonical source metadata is stored in:

```text
release/product.json
```

The first product version is:

```text
product_version = 0.1.0
```

This is intentionally independent from current component package versions:

```text
Web package version     = software/web/package.json
Python package version  = software/python/pyproject.toml
```

The release manifest records both the product version and the relevant source component versions. Therefore:

```text
Product Version != Web package version
Product Version != Python package version
```

A future published release process must ensure one published product version maps to one intended Git commit/release lineage. PR #222 does not publish GitHub Releases or define tag policy.

## 3. Supported v1 release targets

The canonical v1 matrix follows the Product Deployment Foundation.

### Control Station

```text
macos-arm64
macos-x86_64
linux-arm64
linux-x86_64
windows-x86_64
```

### PPU

```text
linux-armv7l
```

Unsupported role/platform/architecture combinations fail closed. In particular, Windows ARM64 is not a supported v1 release target merely because Windows is a supported Control Station operating system.

## 4. Artifact naming and archive format

Canonical names are:

```text
plasma-control-station-<product-version>-macos-arm64.tar.gz
plasma-control-station-<product-version>-macos-x86_64.tar.gz
plasma-control-station-<product-version>-linux-arm64.tar.gz
plasma-control-station-<product-version>-linux-x86_64.tar.gz
plasma-control-station-<product-version>-windows-x86_64.zip
plasma-ppu-<product-version>-linux-armv7l.tar.gz
```

Common Release Format does not mean every operating system must use the same archive container. The common contract is the logical layout, manifest, target identity, integrity model, and verification behavior.

- macOS/Linux/PPU use `tar.gz`.
- Windows uses ZIP.

## 5. Canonical bundle layout

Every archive has exactly one canonical root:

```text
plasma-release/
├── release.json
├── SHA256SUMS
├── runtime/
└── config/
    └── defaults/
```

`runtime/` contains an already-built runtime payload supplied to the release builder. The Common Release Format does not decide how Console/Manager or Gateway/Server are built; those are later runtime-packaging phases.

`config/defaults/` is optional and may contain non-secret product defaults. Persistent site/fleet configuration, credentials, operator state, logs, and secrets are not release payloads.

## 6. `release.json` schema v1

A v1 manifest contains exactly these fields:

```json
{
  "schema_version": 1,
  "product": "plasma",
  "product_version": "0.1.0",
  "git_sha": "<40-character commit SHA>",
  "role": "control-station",
  "platform": "linux",
  "architecture": "x86_64",
  "target": "linux-x86_64",
  "build_timestamp": "2026-08-30T00:00:00Z",
  "archive_format": "tar.gz",
  "contracts": {
    "web_rest_api": "3"
  },
  "components": {
    "python": "0.3.2",
    "web": "0.1.0"
  },
  "layout": {
    "runtime": "runtime",
    "config_defaults": "config/defaults"
  }
}
```

The PPU role carries the contracts currently relevant to that role:

```json
{
  "plasma_protocol": "3.3",
  "web_rest_api": "3"
}
```

No Manager/fleet contract version is invented in v1 because the repository does not yet define a canonical numbered Manager API compatibility contract. A future explicit contract can be added through a release-schema change when the architecture defines it.

## 7. Compatibility metadata

Product version is release identity. Protocol/API versions are interoperability identity.

The current canonical compatibility metadata is:

```text
Web REST API contract = 3
Plasma wire protocol  = 3.3 / PLASMA33
```

A later installer or fleet compatibility checker should compare the contracts required between Control Station and PPU rather than assuming a numerically newer product version is automatically compatible.

## 8. Integrity model

Release v1 intentionally has two SHA-256 layers.

### 8.1 Internal bundle integrity

`SHA256SUMS` contains a SHA-256 entry for every regular file in the bundle except `SHA256SUMS` itself, including `release.json`.

Verification requires the actual file set to match the hashed file set exactly. Missing files, extra files, duplicate entries, or hash mismatches fail closed.

### 8.2 Archive integrity

The complete archive has a detached sidecar:

```text
<artifact>.sha256
```

Example:

```text
plasma-control-station-0.1.0-linux-x86_64.tar.gz
plasma-control-station-0.1.0-linux-x86_64.tar.gz.sha256
```

The detached form is intentional. Putting an archive's own SHA-256 inside `release.json` inside that same archive would create a self-referential hashing cycle.

The future deployment order is therefore:

```text
verify detached archive SHA-256
    ↓
safe extraction
    ↓
verify release.json schema/target/contracts
    ↓
verify SHA256SUMS and exact file set
    ↓
installer-specific checks
```

SHA-256 proves integrity, not publisher authenticity. v1 must not be described as signed software distribution.

Future distribution security may add platform-appropriate authenticity mechanisms, for example macOS code signing/notarization, Windows Authenticode, and signed Linux/release metadata. Those are outside the Release Format v1 integrity scope.

## 9. Extraction safety

The verifier rejects archive structures that are unsafe or outside the v1 contract, including:

- absolute paths;
- `..` path traversal;
- non-canonical backslash archive paths;
- entries outside `plasma-release/`;
- duplicate archive members;
- tar/ZIP symlinks;
- non-regular tar members;
- excessive file count or expanded size beyond verifier safety limits.

Verification occurs in a temporary directory first. `--extract-to` copies the bundle to the requested clean destination only after integrity and manifest validation pass.

## 10. Payload hygiene

The release builder rejects common source-tree/development content such as:

```text
.git/
.hg/
.svn/
node_modules/
.venv/
venv/
__pycache__/
.pytest_cache/
tests/
```

It also rejects common secret/config filenames such as `.env`, `.env.*`, `credentials.json`, `secrets.json`, and common SSH private-key filenames.

This is a defense-in-depth guard, not a complete secret-scanning system. Release construction must still provide a deliberate runtime staging directory rather than point the builder at the repository root.

## 11. CLI

Build an artifact from an already-built payload:

```bash
python3 scripts/product-release.py build \
  --role control-station \
  --platform linux \
  --architecture x86_64 \
  --runtime-dir /path/to/prebuilt-runtime \
  --config-defaults-dir /path/to/defaults \
  --output-dir /path/to/releases
```

In a Git worktree the builder can discover the current full Git SHA. Non-Git build environments must pass `--git-sha` explicitly.

Verify an artifact:

```bash
python3 scripts/product-release.py verify \
  plasma-control-station-0.1.0-linux-x86_64.tar.gz \
  --expect-role control-station \
  --expect-platform linux \
  --expect-architecture x86_64 \
  --expect-version 0.1.0
```

Clean extraction after verification:

```bash
python3 scripts/product-release.py verify \
  plasma-control-station-0.1.0-linux-x86_64.tar.gz \
  --extract-to /tmp/plasma-clean
```

The extracted root becomes:

```text
/tmp/plasma-clean/plasma-release/
```

## 12. CI acceptance

`.github/workflows/product-release.yml` validates the release format independently from deployment.

It covers:

1. release-format unit/regression tests;
2. representative Linux Control Station `tar.gz` build;
3. representative Windows Control Station ZIP build;
4. representative Linux/armv7l PPU build;
5. detached archive SHA-256 verification;
6. manifest and internal `SHA256SUMS` verification;
7. clean-directory verification using a copied standalone verifier script and no source-repository data;
8. clean extraction checks.

A passing workflow supports only these claims:

```text
Plasma Release Format PASS
Release Manifest PASS
Artifact Integrity PASS
Clean Extraction PASS
```

It does not support:

```text
macOS Deployment PASS
Linux Deployment PASS
Windows Deployment PASS
Z2 Deployment PASS
service activation PASS
PS <-> PL PASS
real IC programming PASS
```

## 13. Next phases

With this release contract established, later work can build real role-specific runtime payloads:

```text
Common Release Format
    ↓
Control Station runtime packaging
    ↓
PPU/Z2 runtime packaging
    ↓
platform installers/service adapters
    ↓
upgrade/rollback
    ↓
Control Station -> Manager -> Z2 -> PS Loopback acceptance
```

The installer layer must consume verified release artifacts. It must not reintroduce target-side Git pulls, source builds, npm installation, or repository-relative runtime dependencies.
