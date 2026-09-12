# STM32L0 L0.2 retained manufacturer evidence

This directory retains the successful official-ST L0.2 acquisition from workflow run `34686132303`, artifact `10296507776`.

- 99 deterministic Base Devices across 16 STM32L0 subfamilies
- 360 unique Active exact ICPNs
- 10 exact non-Active Part Numbers excluded by Marketing Status
- 0 lifecycle-only Base Devices
- 0 source-unavailable targets
- 0 manual review / acquisition failures
- 99/99 OpenOCD routing observations unique; routing does not gate commercial identity
- L0.1 representative continuity passed

`live-summary.json` embeds the complete 99 evidence records. The original artifact also contained one JSON leaf per Base Device. To avoid duplicating the same evidence twice in Git, `leaf-digests.json` retains the SHA-256 of every original leaf, and the retained-evidence validator reconstructs each leaf byte-for-byte from the embedded summary before checking those digests.

This evidence is research-only. It does not authorize canonical admission, Production publication, programming algorithm equivalence, Flash/security semantics, electrical/socket qualification, HIL, or runtime programming support.
