# PLASMA Z2 Hardware Package Baseline v1 — Gate 1 Path 2 Evidence

Status: **B1 NOT_RUN / B2-v1 NOT_RUN / B2-v2 NOT_RUN**. This is not
hardware Receive/Admission qualification. Read-only physical preflight and
SWPC Manager inventory were successfully executed; **no package was uploaded**.

## Source and trust boundary

- Main ancestor: \`c58621afe896e6a6f57fe712c27ffcbc06a6f0e8\`.
- Candidate: [Draft PR #1224](https://github.com/physicslu/plasma/pull/1224), exact SHA must be re-pinned on every subsequent run.
- Existing Issue #981 trusted owner Work Order / Path 2 \`operator-cli\`,
  \`guarded-hardware\`, runner \`SWPC-plasma-codex\`, Verification \`exit-code\`.
- Real physical Z2 Bootstrap: \`192.168.2.99:18081\`, observed identity
  \`ppu-device-7ed4b30913a9bf6101da5a7a\`, Bootstrap version \`0.1.0\`,
  API \`1\`, Runtime \`runtime_active\`. Installed source commit of the
  Bundle verifier is **NOT_ATTESTED**.
- No Z2 Installer, FPGA/PL, DUT, factory service, SWPC settings or control-token
  file was changed by this Gate 1.

## Independent physical Path 2 results

| Stage | Workflow / Evidence | Pin and Result |
|---|---|---|
| Physical Z2 read-only HTTP probe | [Run 41098395015](https://github.com/physicslu/plasma/actions/runs/41098395015) | Original candidate \`8a64808830106c0d56a73d65f9c5f23ce57e5716\`; authorized Path 2 exit 0; device ID, Bootstrap version, Runtime status observed. B1/B2 NOT_RUN |
| Original direct Bootstrap B1/B2 attempt | [Run 41099568098](https://github.com/physicslu/plasma/actions/runs/41099568098) | No Token file provisioned to Runner; Exit 69; B1/B2 NOT_RUN. Motivated reuse of existing Manager pairings |
| Manager-paired read-only probe (port 18280) | [Run 41150496276](https://github.com/physicslu/plasma/actions/runs/41150496276) | Candidate \`b21cedfb511729b09c19a67d77fc900539c882a4\`; Exit 69 \`MANAGER_PHYSICAL_TARGET_NOT_ENROLLED\`; no mutation |
| Manager Registry inventory | [Run 41150656253](https://github.com/physicslu/plasma/actions/runs/41150656253) | Candidate \`857975fe993f20e08495f6ea9606c686a55e1888\`; exact trusted Runner exit 0; local Manager :18180 NOT_AVAILABLE, :18280 NO_PHYSICAL_TARGET; B1/B2 NOT_RUN |

Registry-inventory output (from actual Path 2 process receipt):

\`\`\`json
{
  "phase": "READ_ONLY_MANAGER_REGISTRY_INVENTORY",
  "managers": [
    {"port": 18180, "status": "NOT_AVAILABLE"},
    {"port": 18280, "status": "NO_PHYSICAL_TARGET",
     "real_z2_aliases": []}
  ],
  "b1": "NOT_RUN",
  "b2_v1": "NOT_RUN",
  "b2_v2": "NOT_RUN",
  "install": "NOT_RUN",
  "fpga": "NOT_RUN",
  "dut": "NOT_RUN"
}
\`\`\`

Actual process receipt \`stdout_sha256\`:
\`85aad67e9ed31c9b63370ae4885502eb02d76325d63d51040021dc5bec89d9d4\`;
\`work_order_sha256\`:
\`b15f8b58f462beea897e19bb96907c9a98ed5d97325cc7fe958cbd208827bf1c\`.
The matching workflow's downloadable \`plasma-development-cli-41150656253\`
artifact is the authoritative raw stdout/process/receipt evidence.

## Classification and next admissible step

- **Physical connection:** Proven with the initial read-only direct Z2 probe.
- **SWPC Manager availability:** :18280 reachable, but its Registry has no
  \`http://192.168.2.99:18080\` alias; :18180 unavailable. Therefore the
  Runner does not have an authenticated Manager route to the physical Z2.
- **Do not reinterpret Run exit 0 from inventory as a B1 PASS.** No upload,
  server-side hash/commit or Admission transaction occurred in those runs.
- The product Manager's existing Bootstrap Credential Store must be enrolled
  for the **real physical Z2** with matching device ID and its configured
  Gateway endpoint. Registration/pairing must be performed only in an
  explicitly authorized, controlled Platform maintenance workflow.
  **This Gate 1 does not authorize changing SWPC system configuration**;
  no guessed Token, no direct HTTP mutation fallback, no QEMU substitution.
- When owner confirms the real Manager enrollment, rerun the exact-HEAD
  read-only Manager pairing preflight and then B1/B2. Keep B1 independent of
  B2. Never claim Production TLS, Publisher/Master authority, Installer or
  FPGA/DUT qualification from B1/B2.
