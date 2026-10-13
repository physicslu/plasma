# Microchip Research v2 — 8 timeout recovery, not Production SKU admission

**Starting base:** merged Research PR #829, commit `7c162f66faece70b0ce330ca78390e3c774738c4`.

The DFP name query first pass covered 3,198 planned search names, but
eight whole batch archives were quarantined due to hard timeout before
the original attestation was written. Their exact names are pinned in
`microchip_mcp_timeout_recovery_v2.py`. They are ALL 8-bit PIC/AVR;
no different manufacturer inventories are touched.

The recovery runs **each individual DFP name in an isolated subprocess**,
with a bounded 85-second query watchdog and three-second serial gap.
Only two batch jobs execute concurrently. Each source proof is
durably fsynced BEFORE any Microchip vendor call; any failed query
retains original response diagnostics and stays unverified. The original
eight quarantined raw archives are never rewritten or post-hoc attested.
Offline `microchip_mcp_evidence_ledger_v1.py` must replay raw response
bytes before a candidate can be included in Research counts.

`NOT_FOUND` does **not** imply device EOL. DFP support names are not
commercial SKU enumeration and measured text-search Active labels are
not authoritative manufacturer life-cycle classification.

**Authorization boundary:** this work does not create or alter Production
ICPN catalogs, flash firmware, OpenOCD mappings or global Active coverage
claims. A separate owner approval will be required for PR merge and for
any later Production data promotion.

