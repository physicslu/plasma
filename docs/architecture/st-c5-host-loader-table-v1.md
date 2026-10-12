# STM32C5 source-only Host Loader Selection Guard v1

**No Z2, FPGA, SWD, OpenOCD, actual device readback, loader execution, vendor binary distribution, production mapping or flash operations.**

## Why

ST's pinned \`stm32c5x.cfg\` has two scalar \`set\` declarations subsequently used as Tcl arrays. Prior v1.1 static research demonstrated the two in-memory \`array set\` fixes but left the vendor \`dev_id_loader\` table empty. This package does **not** patch, distribute, install or source the vendor target configuration. It adds a host-only synthetic lookup fixture demonstrating corrected Tcl array indexing of the three **source identities**. The fixture is not a runnable target script and never calls \`stldr set_loader\`.

The production Catalog already has all 172 C5 commercial exact MPNs, and all remain backend \`no_mapping\`. Of those, **139** match an official DFP exact Dvariant and **33** only match a Base Device; the latter are *blocked from this exact-variant source match*, not misrepresented as missing Production identity/Flash metadata.

## Host guard

\`C5HostLoaderGuard\` consumes the existing immutable Production Catalog + \`BackendCandidateRegistry\`, pinned official ST OpenOCD commit and DFP commit. It validates three independently SHA-locked loader source paths, device group (0x44F, 0x44E, 0x45A), DFP algorithm RAM declaration, default 32 KiB ST workarea and official exact Flash metadata. Caller-supplied **synthetic** IDCODE + Flash-size inputs can yield \`synthetic_source_match_only\` for the 139 exact DFP variants. Every Base-only record, unknown IC, wrong family/device ID, invalid read, invalid geometry, vendor maximum fallback, override, tampered source fingerprint or unauthorized field is blocked.

The 139 matches are **not** runtime candidates to execute: loader files are not staged; actual physical ID, SRAM ABI, loader availability, license, security state, erase/program/verify and runtime readiness remain unverified. The output includes no commands, transport, installed binary or target CFG. \`synthetic_source_match_only\` is an offline research result, never programming authorization.

## Tests

\`\`\`bash
python -m pip install -e software/python
python scripts/ci/device-catalog-production-invariants.py
python -m unittest discover -s software/python/tests -p 'test_c5_host_loader_guard_v1.py' -v
tclsh software/python/tests/fixtures/c5_stldr_array_lookup_v1.tcl
\`\`\`

The dedicated workflow installs Tcl and checks negative cases. No dynamic manufacturer download or loader binary is included. Existing PPU and Production backend routing remain unchanged.

## What remains

A separately approved non-deployed test must verify source-pinned ST driver registration and real loader ABI/RAM behavior. Actual target readback and flash programming require physical evidence, independent security/electrical qualification and formal per-exact-ICPN admission. The global ST baseline stays 4,164 mapped / 465 no_mapping.
