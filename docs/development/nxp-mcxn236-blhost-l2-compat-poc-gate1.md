# NXP MCXN236VKLT — Gate 1 ROM ISP / blhost L2 Compatibility PoC

**Status: CANDIDATE / BLOCKED. This PoC does not qualify L2 or execute anything.**

**Gate 1 base:** \`fd6507cf8202e917f0d2c88f855243aa89667aea\`. Scope is exactly NXP \`MCXN236VKLT\`. No hardware, merge, deployment, runtime integration, privilege modification or Catalog promotion.

## Admission dependency

The production \`get_default_programming_qualification_registry()\` does not include a MCXN 31 exact-ICPN route admission adapter. This PoC does not register as a \`ProgrammingQualificationProvider\`, and it does not change Canonical L0/L1/L2 projections. The preexisting 31-part research/electrical data is not itself L1 route admission. \`canonical_admission_status()\` checks the prerequisite without changing the registry.

## Manufacturer and software sources

| Evidence | Source and version | Verified / not verified |
| --- | --- | --- |
| Exact ordering and Flash | NXP MCXN23x Data Sheet Rev. 3 (2025-01-21), Table 1, p. 4; https://www.nxp.com/docs/en/data-sheet/MCXN23x.pdf | MCXN236VKLT has 1,024 KB main Flash; MCXN235VKLT has only 512 KB. Not interchangeable. |
| Granularity | Same datasheet Table 42, pp. 47–48 | 8 KB sector, 128 B page, 16 B phrase in Flash command specifications. These are not proof of individual bootloader command support. |
| Family ROM ISP | NXP MCXN23x Security Reference Manual Rev. 4 (2025-06-13), NXP SEC processor workflow | Detailed security-state and ROM protocol qualification remains missing. |
| SEC | https://mcuxpresso.nxp.com/secure/26.06/release_notes.html | SEC 26.06 integrates SPSDK **v3.10.0**; project-pinned SEC release-note SHA256: \`5f58034e556df7d3c7a7c99aae8ded8aa9e339e2dcd1e81fd452119c830b0205\`. Not a new independent byte-replay. |
| blhost | https://spsdk.readthedocs.io/en/v3.10.0/apps/blhost.html | Versioned CLI documents \`get-property\`, \`flash-erase-region\`, \`write-memory\`, \`read-memory\`; it warns not all target devices support all commands. |

**Source-custody limitation:** No original NXP PDF byte SHA256 or SPSDK/blhost installed binary hash was measured or pinned by this PoC. Thus PDF replay, reproducible binary identity, and provider version compatibility remain unresolved. Flash start address \`0x00000000\` and a contiguous 1 MB range are **mock-only candidate assumptions**, not proven MCXN236 bank/protected memory maps.

## Conservative Host-only mock contract

\`software/python/plasma_web/nxp_mcxn236_blhost_compat_poc.py\` implements only an immutable mock plan and scripted in-memory mock transport. It imports no physical serial/USB transport or subprocess and is not wired into Job, Provider, or Runtime.

- Mock Probe: require start/size/sector properties, named commands and explicit OPEN security state; properties do not attest exact IC identity.
- Mock Erase: require complete 8 KB sectors; the real \`flash-erase-region\` may affect the entire sector touched.
- Mock Program: require page-aligned start and length in 128 B increments; no implicit last-page padding.
- Mock Read/Verify: compare exact bytes; mismatch blocks.
- Failure: wrong/missing response, timeout, incomplete results, security state mismatch, wrong geometry or forbidden commands fail closed. Replies are single-use; no automatic retry.
- Forbidden: mass erase, unlock, fuses, HSM, provisioning, lifecycle changes, IFR/PFR/CMPA/CFPA operations, unknown reserved memory regions. The protected-region/bank map is not qualified, so **no real operation is permitted**.

The Mock Transport is for deterministic Host-only behavior testing and never proves a physical programming path. Tests run under the existing Python test discovery.

## Gates remaining before any L2

1. MCXN 31 exact ICPNs formally admitted at L1 in canonical registry through their independent reviewed Gate.
2. Reproducible SPSDK 3.10.0 \`blhost\` dependency/source/binary lock, with independent protocol and return-code review.
3. Independent exact silicon identity verification, bank layout, writable application region, and IFR/PFR/CMPA/CFPA exclusion map.
4. Actual target-specific \`get-property\`/ROM command support, security lifecycle constraints, error and recovery semantics.
5. Evidence-backed Probe / Erase / Program / Read / Verify qualification against an identified exact target before any software \`SUPPORTED\` claim.

A successful Gate 2 for this Draft PR would merge **research/mock code only**, never L1/L2 promotion, runtime deployment or hardware operation.
