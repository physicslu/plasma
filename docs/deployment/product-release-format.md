# Plasma Product Release Format v1

> Status: **Current**. The manifest schema remains v1. Current deployment identity policy is **Release Identity v2**: every deployable artifact is named by product version plus a 12-character source Git SHA prefix, while the manifest retains the full 40-character Git SHA and detached SHA-256 integrity evidence.

## 1. Purpose

Plasma product deployment must consume immutable release artifacts rather than interpret the source repository on the target machine.

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

## 2. Version, release identity, and digest

Canonical product metadata lives in `release/product.json`. The current product version is:

```text
product_version = 0.1.1
```

Product version is independent from Web/Python component package versions.

Release Identity v2 separates three concerns:

```text
product_version = 0.1.1
full git_sha    = abcdef1234567890...40 hex characters...
release_id      = 0.1.1-abcdef123456
artifact_sha256 = <64 hex characters>
```

Their meanings are deliberately different:

- `product_version` is the SemVer product version used for product evolution and platform package-version semantics.
- `release_id` is the immutable deployment/build identity: `<product-version>-<first-12-git-sha>`.
- `artifact_sha256` identifies the exact artifact bytes and proves transport/integrity equality.

A different source Git SHA MUST NOT reuse the same deployable artifact filename or immutable release directory even when `product_version` is unchanged. Rebuilding the same source may retain the same `release_id`, but the detached artifact digest remains the exact-byte identity.

The full Git SHA remains authoritative provenance. The 12-character prefix is a human-operational identity used in filenames and install paths; it does not replace the full SHA in `release.json`.

## 3. Supported v1 release targets

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

Unsupported role/platform/architecture combinations fail closed.

## 4. Artifact naming and archive format

Canonical Common Release Format names are now:

```text
plasma-control-station-<release-id>-macos-arm64.tar.gz
plasma-control-station-<release-id>-macos-x86_64.tar.gz
plasma-control-station-<release-id>-linux-arm64.tar.gz
plasma-control-station-<release-id>-linux-x86_64.tar.gz
plasma-control-station-<release-id>-windows-x86_64.zip
plasma-ppu-<release-id>-linux-armv7l.tar.gz
```

Example:

```text
plasma-ppu-0.1.1-abcdef123456-linux-armv7l.tar.gz
```

Common Release Format does not mean every operating system uses the same archive container:

- macOS/Linux/PPU use `tar.gz`;
- Windows uses ZIP.

Platform installers inherit the same release identity. Examples:

```text
plasma-control-station-0.1.1-abcdef123456-macos-arm64.pkg
plasma-control-station-0.1.1-abcdef123456-windows-x86_64.msi
```

## 5. Canonical bundle layout

Every archive has one canonical root:

```text
plasma-release/
├── release.json
├── SHA256SUMS
├── runtime/
└── config/
    └── defaults/
```

`runtime/` is already-built product runtime content. `config/defaults/` is optional and must not contain persistent operator state, credentials, logs, or secrets.

## 6. `release.json` schema v1

Release Identity v2 does **not** change the release manifest schema. A representative v1 manifest is:

```json
{
  "schema_version": 1,
  "product": "plasma",
  "product_version": "0.1.1",
  "git_sha": "abcdef1234567890abcdef1234567890abcdef12",
  "role": "control-station",
  "platform": "linux",
  "architecture": "x86_64",
  "target": "linux-x86_64",
  "build_timestamp": "2026-09-06T00:00:00Z",
  "archive_format": "tar.gz",
  "contracts": {
    "web_rest_api": "3"
  },
  "components": {
    "python": "<component-version>",
    "web": "<component-version>"
  },
  "layout": {
    "runtime": "runtime",
    "config_defaults": "config/defaults"
  }
}
```

The PPU role carries:

```json
{
  "plasma_protocol": "3.3",
  "web_rest_api": "3"
}
```

## 7. Compatibility metadata

Product/release identity and protocol compatibility are separate dimensions.

```text
Web REST API contract = 3
Plasma wire protocol  = 3.3 / PLASMA33
```

A numerically newer product version is not automatically protocol-compatible. Installers and Managers must compare the relevant contracts rather than infer compatibility from SemVer alone.

## 8. Integrity model

Release v1 has two SHA-256 layers.

### Internal bundle integrity

`SHA256SUMS` hashes every regular bundle file except itself. Verification requires the exact file set and exact hashes.

### Archive integrity

The complete artifact has a detached sidecar:

```text
<artifact>.sha256
```

Example:

```text
plasma-control-station-0.1.1-abcdef123456-linux-x86_64.tar.gz
plasma-control-station-0.1.1-abcdef123456-linux-x86_64.tar.gz.sha256
```

Verification order is:

```text
verify detached artifact SHA-256
    ↓
safe extraction
    ↓
verify release.json full source identity / target / contracts
    ↓
verify SHA256SUMS + exact file set
    ↓
installer-specific checks
```

SHA-256 proves integrity, not publisher authenticity. Signing/notarization/Authenticode remain separate controls.

## 9. Extraction safety

The verifier rejects absolute paths, traversal, non-canonical archive paths, entries outside `plasma-release/`, duplicates, symlinks, non-regular tar entries, case-insensitive portability collisions, and safety-limit breaches.

## 10. Payload hygiene

The builder rejects common source/development material such as `.git`, `node_modules`, virtual environments, caches, tests, and common secret filenames. This is defense in depth; the input must still be a deliberate runtime staging tree.

## 11. CLI

Build:

```bash
python3 scripts/product-release.py build \
  --role control-station \
  --platform linux \
  --architecture x86_64 \
  --runtime-dir /path/to/prebuilt-runtime \
  --config-defaults-dir /path/to/defaults \
  --output-dir /path/to/releases \
  --git-sha "$(git rev-parse HEAD)"
```

For source SHA `abcdef123456...`, product version `0.1.1` produces a filename containing:

```text
0.1.1-abcdef123456
```

Verify:

```bash
python3 scripts/product-release.py verify \
  plasma-control-station-0.1.1-abcdef123456-linux-x86_64.tar.gz \
  --expect-role control-station \
  --expect-platform linux \
  --expect-architecture x86_64 \
  --expect-version 0.1.1
```

## 12. CI acceptance

`.github/workflows/product-release.yml` validates representative Linux Control Station, Windows Control Station, and Linux/armv7l PPU artifacts, detached hashes, manifest/internal integrity, clean verification, and clean extraction.

Regression coverage explicitly verifies that two different Git SHAs under the same product version produce different artifact filenames.

A passing workflow supports only release-format/integrity claims. It does not prove host deployment, service activation, Z2 HIL, PS↔PL, or real IC programming.

## 13. Operational rule

The deployment rule is now fail-closed:

> Every deployable Plasma artifact and immutable installed release must be traceable as `product_version + full source Git SHA + artifact digest`. Human-facing artifact names and immutable release directories use `product_version + 12-character Git SHA prefix`; manifests retain the full SHA.

This rule exists because version-only names such as `plasma-control-station-0.1.0-macos-arm64.pkg` allowed different source commits to look identical during field qualification. Version-only deployment identity is no longer acceptable.
