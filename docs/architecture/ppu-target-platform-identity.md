# ADR — PPU Target Platform Identity (proposal)

> **Term note:** in this document **B1/B2/B3/B4 are Bundle stages** — B1 upload/commit, B2 admission, B3 install/verify, B4 activation (incl. previous-version backup). Not the FPGA/UIO or governance meanings; see [glossary](../glossary.md#b1b2b3).

Status: Proposed (merged as a proposal in PR #1225); not approved for production deployment.

## Observed evidence

On PYNQ Z2, the root-owned, mode 0600 trusted target profile at `/etc/plasma/ppu-package-target.json` contains `platform: linux-armv7`, `board: pynq-z2`, `fpga_part: xc7z020clg400-1`. The currently installed runtime status advertises `target: linux-armv7l`. The Path 2 B1 upload passed, but B2 `POST /v1/deployments` returned HTTP 409. The actual server rejection message was not captured; platform mismatch is a hypothesis, **not a confirmed root cause**.

## Proposed contract

- Treat `linux-armv7` as the canonical PPU **package admission** platform identifier for this Z2 target, subject to verification of all existing producers and consumers before finalizing.
- Treat `armv7l` from Linux `uname -m` as a detected machine string, not an interchangeable canonical package target. The suffix `l` denotes little-endian in that Linux machine designation. Record endianness separately when required by binary compatibility checks.
- The Bundle v3 manifest `target` must exactly match the trusted device-local profile for `platform`, `board` and `fpga_part`; do not silently normalize or accept aliases at the admission boundary.
- A runtime status field is observational metadata; it does not authorize a Bundle target. Any runtime metadata migration must be reviewed separately for its consumers and compatibility impact.
- Preserve the root-owned target profile, Factory Recovery, and existing Bootstrap HTTP `/v1` endpoints. HTTP API version 1 and deployment-state schema_version 1 are independent of Bundle schema v1/v2 retirement.

## Gate 1 acceptance criteria

1. Audit Git history and all target producers/consumers before adopting the proposed canonical identifier as final.
2. Host-only tests: matching canonical target passes; mismatched platform, board or FPGA part fail closed; no legacy Bundle v1/v2 accepted.
3. Capture sanitized B2 HTTP 409 rejection reason and make the overall hardware acceptance exit nonzero unless B1 and B2 both pass.
4. Re-run Path 2 B1/B2 using a SHA-pinned reviewed PR HEAD only after code and CI are ready. Do not run B3/B4, FPGA or DUT operations.
