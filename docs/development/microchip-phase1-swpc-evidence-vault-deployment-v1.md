# Microchip Phase 1 — SWPC Evidence Vault controlled deployment v1

**Repository scope:** Research evidence only. The existing portable ZIP/Local Vault capabilities were merged in PR #878. This increment adds an **explicit SHA-256-pinned operator handoff for SWPC**, not an unattended deployment.

## Known source receipt available for operator recovery

The completed GitHub Actions run **38535507957** produced the [Microchip manufacturer original-byte portable bundle](https://github.com/physicslu/plasma/actions/runs/38535507957/artifacts/11879822665), with an expiry of **2027-01-12 08:29:49 UTC**. The ZIP bundle byte digest independently recorded in that run is:

~~~text
964561207e565757a2c270a438c366d6cf690c4fb0a7ba3405b257e8ad0cca16
~~~

The nested portable bundle has original MicrochipDirect chart HTML, two full MCP original-response pagination streams (E5/D5 + PIC32MX), original evidence manifests, source-derived query plan and 341-P0 Research report. This is **not** a Microchip-wide ICPN archive. It does **not** include all earlier SAMD21 research bytes. 90-day expiry is a deadline for this particular artifact, not a permanent-retention policy.

**Operational prerequisite:** the human operator must first confirm the exact intended SWPC host and account, real mounted disks, availability of GitHub CLI, GitHub authentication, Git checkout at a reviewed commit and access to the existing artifact. The connected GitHub API used for authoring this change cannot inspect the private SWPC shell, mounted volumes, runtime or self-hosted runner status. No remote filesystem has been touched during authoring.

## 1. Determine an appropriate SWPC storage topology (read-only)

Before running any command, explicitly set PLASMA_REPO in your interactive shell to the verified absolute path of the reviewed checkout. The commands below use that role-based variable, not a hardcoded host-specific location.



On the authorized SWPC shell, inspect first. Do not assume that /storage has its own physical disk just because it has a different pathname:

~~~bash
hostname
id
pwd
lsblk -f
findmnt -T $PLASMA_REPO
df -hT /storage $PLASMA_REPO
gh auth status
~~~

The operator must set PLASMA_REPO to the actual, verified local checkout path. **No public documentation or repository workflow assumes its private pathname.** If /storage shares the system drive or is an ephemeral/network mount, record the real topology and its risk. A distinct local disk is still **not an offsite copy, WORM, or enforceable retention**.

## 2. Acquire the exact original bytes (operator action)

Do not hardcode tokens, secrets or GitHub credentials in a script or PR. Use the locally authenticated GitHub CLI, and fetch the named Artifact into a **fresh**, outside-repository staging directory:

~~~bash
cd $PLASMA_REPO
git status --short
git rev-parse HEAD
gh auth status

install -d -m 0700 /storage/plasma-evidence-staging
install -d -m 0700 /storage/plasma-evidence-staging/run-38535507957

gh run download 38535507957 \
  --repo physicslu/plasma \
  --name microchip-phase1-portable-bundle-live-and-receipts-v1 \
  --dir /storage/plasma-evidence-staging/run-38535507957
~~~

**Do not proceed with an incomplete or expired artifact.** Before using the script, check that the download produced portable-original-evidence.zip, portable-original-evidence.sha256, pack-receipt.json and cold-replay-receipt.json.

## 3. Pre-provision a protected local target

The operator must choose and provision the actual filesystems. The following commands are **illustrative**, never automatically run by CI, and might need administrator filesystem permissions:

~~~bash
install -d -m 0700 /storage/plasma-evidence-vault
install -d -m 0700 /storage/plasma-evidence-restore
install -d -m 0700 /storage/plasma-evidence-receipts
findmnt -T /storage/plasma-evidence-vault
findmnt -T /storage/plasma-evidence-restore
~~~

The evidence ZIP and vault **must** be outside the Git checkout. The vault key is exclusive and cannot be overwritten. A previously incomplete key must be quarantined for manual investigation; never silently delete it.

## 4. First run a read-only preflight

~~~bash
python3 scripts/microchip-phase1-swpc-vault-handoff-v1.py \
  --artifact-dir /storage/plasma-evidence-staging/run-38535507957 \
  --vault-root /storage/plasma-evidence-vault \
  --restore-dir /storage/plasma-evidence-restore \
  --evidence-key microchip-p0-20261014-e5-pic32 \
  --expected-sha256 964561207e565757a2c270a438c366d6cf690c4fb0a7ba3405b257e8ad0cca16 \
  --receipt /storage/plasma-evidence-receipts/preflight.json
~~~

This stage does not create the vault key or copy any evidence into the vault. It validates the exact externally pinned ZIP hash, original SHA sidecar and two pack/cold-replay receipts; reruns the original chart and both 20/60-page manufacturer MCP evidence validators offline; checks available filesystem space; and observes kernel device IDs/mount metadata. Device-ID inequality is a **filesystem observation**, not a guarantee of independent physical hardware.

## 5. Explicit deposit, audit and restore

Only after PRE-FLIGHT PASS and human review of the mounted drive, append **--apply** with a **new receipt path**:

~~~bash
python3 scripts/microchip-phase1-swpc-vault-handoff-v1.py \
  --artifact-dir /storage/plasma-evidence-staging/run-38535507957 \
  --vault-root /storage/plasma-evidence-vault \
  --restore-dir /storage/plasma-evidence-restore \
  --evidence-key microchip-p0-20261014-e5-pic32 \
  --expected-sha256 964561207e565757a2c270a438c366d6cf690c4fb0a7ba3405b257e8ad0cca16 \
  --apply \
  --receipt /storage/plasma-evidence-receipts/local-deposit-and-restore.json
~~~

Success requires a ZIP with the exact pinned SHA-256, an on-disk vault deposit, independent vault audit, a separate restored ZIP file and **offline cold replay from that restore**. The local receipt retains flags:
- local_deposit = PASS
- stored_bundle_audit = PASS
- local_restore_and_offline_cold_replay = PASS
- durable_storage_verified = false
- independent_offsite_copy_verified = false
- immutable_retention_verified = false
- production_write_authorized = false

**Important:** Filesystem operators/root can still delete or replace this evidence along with its receipt. It is **not** a security-grade signed provenance chain. No action writes to the Production Catalog, PPU, PL, device sockets or target ICs.

## 6. Independent long-term archive (not automated)

Before claiming durable custody, copy the validated bytes **to a separately administered, access-restricted storage destination**, configure an enforceable retention/deletion policy if available, and perform a fresh restore from that destination using separately held hashes. Record the operator, archive version/key, UTC restore timestamp, SHA-256, tool/repository commit, access boundary, periodic audit schedule and disaster recovery plan. A secondary directory on the same SWPC machine is not enough.

Also migrate earlier manufacturer original-byte artifacts, particularly PR #871 SAMD21, before their expiry. This implementation deliberately does **not** automatically ingest them or mark them durable.

## CI status contract

Repository CI runs synthetic negative/preflight/apply tests and a **separate real Microchip original-source E5/D5/PIC32MX ZIP through an ephemeral Ubuntu runner vault**. The GitHub Runner test proves the program can perform deposit/audit/restore with actual manufacturer original bytes, but says nothing about SWPC being provisioned, mounted, backed up or accessible right now.

**Merge acceptance:** check all updated tests and source CI, confirm only Research/scripts/docs/workflow files changed, then obtain owner approval. **SWPC deployment is a separate operator acceptance gate.**
