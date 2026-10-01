# STM32G0 Metadata Policy Gap v1.6

Research only. This follows the merged v1.5 finding that **357 of 359** Active G0 Catalog gaps belong to **87 Base Devices outside the original bounded discovery scope**.

Current G0 metadata policy can fully decode only **2/359** gap identities. The blockers overlap:

| Policy dimension | Gap exact rows blocked |
| --- | ---: |
| Base-device allowlist | **357** |
| Pin-count code map | **284** |
| Package code map | **67** |
| N-version scope | **40** |
| Flash-size code map | **0** |
| Temperature code map | **0** |
| Option-suffix vocabulary | **0** |

Observed new code surface:
- pin codes: C, E, F, G, J, K, M, N, R, V, Y
- package codes: I, M, P, T, U, Y
- flash codes: 4, 6, 8, B, C, E
- temperature codes: 3, 6, 7
- option suffixes: blank, TR, N, NTR

All 12 STM32G0 subfamilies already have a bound official ST ordering-information authority in the existing policy. That does **not** mean the new pin/package/N semantics are automatically authorized; those tables must be revalidated against the observed code surface before policy expansion.

The important conclusion is architectural: Layer-1 Catalog identity is already established by the official Active exact MPN evidence. Metadata completeness and Layer-2 route state are follow-up dimensions, not reasons to deny device existence.

No Production write is authorized.
