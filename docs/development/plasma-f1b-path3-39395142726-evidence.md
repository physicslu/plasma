# F1-B real Z2 development evidence — Run #39395142726

**Acceptance class:** \`PASS_DEVELOPMENT_IDENTITY_LOAD_RESTORE\`, **not** production/AXI-isolation qualification.

## Immutable provenance

- GitHub Run: https://github.com/physicslu/plasma/actions/runs/39395142726
- Artifact: https://github.com/physicslu/plasma/actions/runs/39395142726/artifacts/12251322848
- PR #1074 owner-authorized baseline: \`38461a153afef7e09c360019acf8070eeb6dbe31\`
- Artifact receipt engineering report SHA256: \`85e8ab98283a935fe72aa125afb4c273c2bee198e2b2dc3347f310b19d335a9d\`
- Exact **repaired executed** source \`pl/hil/f1b_owner_once.py\` SHA256: \`5c3d8b6e834ba33f429163bae8da265b030b8d57eed2fb2fea74186e822cc841\` (9152 bytes); artifact reviewed source archive before repair SHA256 \`d9e4d637e421dc0a6de1419d6ef1232f959962f40924094a48dbfff8b273d01d\`.
- BIT 4,045,769 bytes SHA256 \`fdbde5c66999a9dab37339587d304b9c16e71a06f1890b24893c8391859cf075\`
- HWH 138,977 bytes SHA256 \`bf3690d69fefc8da3fc62964209776466894cd4353aec0a475b373257899ca76\`
- F1-B BIN 4,045,568 bytes SHA256 \`c351f668094a2b841426c64681d44c76cb8c14b61766d90a0e10adcf3a22a3c3\`
- Original \`base.bin\` SHA256 \`c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c\`

## Raw observed outcomes (not simulated)

| Stage | Actual machine evidence | Status |
|---|---|---|
| Secure owner-enrolled SSH / sudo | Successful protected login and root uid 0, exit 0; no credential disclosure | PASS |
| Exact owner snapshot | 88 processes checked, no retained MMIO FD/VMA; \`uio_pdrv_genirq\` bound to \`uio1\`, 0x40000000 / 64 KiB | OBSERVED |
| Durable recovery intent | \`intent.json\` = RESTORE_REQUIRED before manager write; one-shot claim | PASS |
| F1-B candidate load | \`candidate-loaded.json\`: \`[82936.566766] fpga_manager fpga0: writing plasma-f1b-owner-20261020-once.bin\` | 1 candidate write |
| 3 native readonly Identity reads | \`identity.json\`: offsets 0→1297304656, 4→65536, 16384→1 = 0x4D534C50 / 0x00010000 / 1 | **3/3 PASS** |
| Original restore | \`restored.json\`: \`[82939.089659] fpga_manager fpga0: writing base.bin\`, \`operating\`, same boot, owners and 5 services | **1 restore PASS** |
| Counter summary | \`result.json\`: candidate_write_attempts=1, restore_write_attempts=1, overall=PASS_DEVELOPMENT_IDENTITY_LOAD_RESTORE | PASS |
| AXI isolation / broader platform/DUT programming | No independent proof | **UNPROVEN / NOT_RUN** |
| Restored-image Identity | No MMIO read after restore | NOT_RUN |

## Evidence location and limits

Reference archived JSON in the original Artifact nested \`_temp/plasma-path3-new-files.tar.gz\` under \`.plasma-path3-evidence/target-evidence/\`: \`original.json\`, \`ownership-before.json\`, \`intent.json\`, \`candidate-write-attempt.json\`, \`candidate-loaded.json\`, \`identity.json\`, \`ownership-before-restore.json\`, \`restore-write-attempt.json\`, \`restored.json\`, \`result.json\`. The repository retains the small key JSON observations in \`docs/development/evidence/f1b-path3-39395142726/\`, with the authoritative original in GitHub Actions.

The original Artifact also contains \`gate-tests.txt\`, \`source-sha256.json\`, \`runtime-check.txt\`, \`reviewed-source.tar\` and \`execute_owner_once.py\`. The latter is an archived historical host helper **not shipped or authorized as a generic Path 2 executor**. No password, private login record, known-host key, unredacted SSH transcript or token is committed to this PR.

See [Codex as-run procedure and Path 2 handoff](./plasma-f1b-path3-39395142726-codex-steps.md) for actual command/exits, incident correction and explicit per-stage triggers. The one-time owner risk acknowledgment does not transfer to Path 2 or production. Neither driver binding nor IRQ counts prove AXI bus isolation.

**Gate 1 scope:** preserve code/evidence and run GitHub-hosted Host-only CI only. No Z2 operations, deployment, merge, Vivado rebuild or second FPGA write.
