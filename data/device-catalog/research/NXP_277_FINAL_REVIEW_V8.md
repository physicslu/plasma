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
