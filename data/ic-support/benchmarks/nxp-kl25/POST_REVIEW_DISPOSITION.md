# NXP KL25 post-review disposition

Status: **Gate 1 implementation; Gate 2 approval pending**

This directory keeps the deterministic software that turns the rejected Gate 5.8 review into a new, separately reviewed release candidate. Gate 5.8 remains immutable and rejected. Its 140 retained facts, fact digests, retained-run identity, review-view digest, verdict digest, and final qualification digest are required inputs.

The transition has three independent admission boundaries:

```text
manufacturer-reviewed knowledge
  -> canonical field admission
  -> operation/profile admission
  -> Software Executor candidate
```

`ACCEPT` retains a Gate 5.8 fact that passed all five review dimensions. A transformed fact (`REPLACE_WITH_MANUFACTURER_FACT`, `SPLIT`, `NARROW`, or `CITATION_SUPPLEMENT_FOR_CANONICAL`) is not admitted from deterministic transformation alone. Every transformed candidate has its own statement digest, locked manufacturer evidence, and explicit five-dimension review verdict.

Projection states are explicit:

- `KNOWLEDGE_ONLY`
- `CANONICAL_REQUIRED`
- `EXECUTION_PROFILE_REQUIRED`
- `BLOCKED`

The exact target is `MKL25Z128VLK4`, bound to the locked NXP KL25 datasheet Rev. 5 ordering row as well as the locked NXP KL25 reference manual Rev. 3. Silicon facts and OpenOCD backend behavior remain separate. The backend lock pins the exact upstream commit and source-file SHA-256 values used for the software compiler contract.

The frozen Software Executor candidate operations are `READ`, `VERIFY`, `PROGRAM`, and `ERASE_SECTOR`. Programming never requests implicit erase, rejects the Flash Configuration Field, and honors the backend's four-byte start alignment while allowing its documented padded tail behavior. Sector erase requires one exact aligned 1 KiB sector and rejects the sector containing the Flash Configuration Field.

The following remain blocked: Erase All Blocks, MDM-AP mass erase, backdoor-key workflows, security-state changes, Flash Configuration Field programming, erasing its sector, unprotect operations, and implicit destructive flows. The production device catalog, production routing allowlist, real OpenOCD runtime, physical hardware, HIL, and Production admission are unchanged.

`build_post_review_release.py` writes only into a new empty directory. It re-runs the Gate 5.8 qualification against the retained run before producing the disposition, explicit candidate review, canonical specification, candidate profiles, operation matrix, qualification result, backend lock copy, and a content-addressed release manifest. The caller finalizes that directory under an immutable release identifier only after all files and digests have been validated.
