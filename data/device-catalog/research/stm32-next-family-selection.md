# STM32 next-family research selection

Status: **research-selection gate only**.

The retained manufacturer identity/lifecycle probe leaves STM32U0 and STM32C0 as the two active candidates and deprioritizes STM32L1 for next-family research because three of four L1 representative targets are lifecycle-only (NRND). L1 is not rejected for future support.

Official ST datasheet review covers nine representative U0/C0 targets through eight datasheet authorities. Every representative has a complete Ordering Information schema for device family, product type, subfamily, pin count, flash size, package, temperature range, and packing/options. STM32C071 additionally confirms that `N` is a real product-version semantic. STM32C091 and STM32C092 legitimately share DS14720.

The required manufacturer evidence quality is therefore equivalent for U0 and C0. The frozen cross-family prioritization shortlist is `STM32U0 -> STM32C0 -> STM32L1`, so the deterministic tie-break selects **STM32U0** as the next family for research.

This selection authorizes research only. It does **not** authorize canonical admission, Production publication, programming-policy equivalence, flash-geometry assumptions, option/security semantics, HIL qualification, or runtime programming support.

GitHub-hosted runner failures while transporting ST PDF bytes are treated as method limitations and are not used as family quality signals. Visual screenshot availability is audit support, not a selection gate.
