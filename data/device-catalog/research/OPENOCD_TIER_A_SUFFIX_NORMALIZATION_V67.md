# OpenOCD Tier A Catalog-Suffix Normalization Probe v6.7

This research-only probe asks one narrow question about the **69** v6.5 identifier-blocked identities:

> If the exact commercial ICPN ends with the Catalog's already-authoritative `option_suffix`, does removing exactly that suffix expose one unique existing OpenOCD route identifier?

The probe does **not** claim that OpenOCD itself understands or ignores the suffix. It only measures whether a deterministic normalization rule is technically possible.

Rules:

- only the Catalog's existing `option_suffix` field may be removed;
- empty suffixes are not normalized;
- the remaining core is matched with the same v6.5 family policy and target config;
- zero or multiple matches stay blocked;
- no Production mapping is changed.

A unique result is only a candidate for a future explicit normalization policy.
