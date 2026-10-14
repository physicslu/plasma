# NXP 277 One-Gate Complete Batch v8

One Draft PR, one owner merge gate after completed end-to-end source and CI review.
Original manufacturer Active discovery remains bounded to 501 exact SKUs (not an
NXP-wide coverage estimate). Existing Production = 4,853 exact, NXP = 224.

The full batch replays **all 277** original /part/ page observations from the
8 verified SHA-locked HTML shards in #846 (Actions run 38366666349) and creates
an auditable per-SKU positive or negative verdict. Source blocked is not EOL.

The three LPC5502JHI48/LPC5504JHI48/LPC5506JHI48 have four basic
HTML metadata fields but lack on-page RAM. NXP's official Datasheet
LPC55S0x/LPC550x, Rev 1.4 (14 Apr 2023), Table 2 physical PDF page 6,
documents exact ordering type number / Flash / RAM (64/48, 128/80, 256/96 KB).
CI downloads original PDF bytes, records SHA256, validates exact rows,
then preserves original PDF and review CSV as artifacts.

NO production manifest write, hardware operation, OpenOCD route, job admission
or programming claims before independent CI and owner approval.
Sources in temporary CI artifacts need durable archiving if retained longer than
30 days; SHA alone does not preserve original bytes.

## Verified batch status (CI on 2026-10-13)

- Official 277 original-source HTML re-replay **PASS**. 207 blocked/schema,
  67 incomplete four-field observations, 3 original HTML four-basic fields
  with SRAM missing. **277/277 reviewed; 0 new Production admissions.**
- HTTP 404 from all three official NXP PDF CDN host variants on the Linux
  GitHub Runner: NXP Japan, NXP China and NXP global. Exact LPC5502/04/06
  RAM values are confirmed by visible NXP Rev 1.4 Table 2, but the
  unavailability of the **original PDF bytes** prohibits a new canonical
  claim that the PDF binary SHA was verified.
- A reproducible 277-row disposition ledger is generated; its committed
  copy must compare byte-identically to a subsequent independent CI run.
  Runtime, Production and programming claims remain unchanged. No hidden
  catch or fallback may silently publish the three candidate identities.
- CI artifact original HTML and PDF acquisition failure receipts retain
  their temporary lifecycle. Future durable archival of the original NXP
  binary must precede any gated LPC3 Production publication.

## Superseded research priority under ADR-0002 (2026-10-14)

The 277-v8 raw manufacturer source review and each negative/partial decision are retained as research evidence; however, the earlier next-step emphasis on acquiring the three LPC550x PDF originals is now P2 (archive only), not an active blocking dependency for software-first research. Under Accepted ADR-0002 and Issue #851, only devices with pinned OpenOCD Target/Flash Driver/operations evidence receive P0 or bounded P1 deep research. See `NXP_ADR0002_OPENOCD_TRIAGE_V9.md` and the 501-row source-locked v9 classification. No PDF URL failure is proof of chip EOL or lack of future backend support. Software/public visibility remains unqualified pending exact ICPN review under Issue #849; PPU/Socket HIL is independent.
