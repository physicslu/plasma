# STM32G0 Official Ordering Authority Replay v1.7

Research-only. No Production write.

The previous v1.6 audit showed that the old bounded metadata policy could directly decode only 2 of the 359 current Active G0 Catalog gaps because its allowlists were intentionally narrow.

This gate replaces the loose global-code question with **per-subfamily ST Ordering Information authority**.

The authority table covers all 12 STM32G0 subfamilies and records, per subfamily:

- pin-count code;
- Flash-size code;
- package code;
- temperature code;
- whether the documented ordering scheme permits the N product-version suffix.

Representative official current ST evidence confirms the expanded code surface. STM32G031 defines J/Y/F/G/K/C pin codes and LQFP/UFQFPN/WLCSP/TSSOP/SO8N package codes; STM32G071 defines E/G/K/C/R and UFBGA/LQFP/UFQFPN/WLCSP, including the N product-version option; STM32G0B1/G0C1 define K/C/N/M/R/V and the same high-density package set with N-version semantics.

The replay must decode **all 359 current Active exact gaps using only the rule belonging to that exact subfamily**. It is not allowed to borrow a code from another G0 subfamily.

Expected result:

- Active exact gap input: 359
- metadata-decodable exact identities: **359**
- unique gap Base Devices: **88**
- Production write: false
- backend route required for metadata decode: false

This does not publish Catalog rows. It establishes that the Layer-1 identities now have a manufacturer-backed metadata decode candidate, so the next gate can prepare an explicit Catalog admission proposal.
