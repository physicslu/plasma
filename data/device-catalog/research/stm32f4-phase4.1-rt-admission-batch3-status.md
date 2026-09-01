# STM32F4 Phase 4.1 R/T Batch3 status

State: bounded discovery retry triggered.

The first discovery attempt stopped before any ST acquisition because seven total targets exceeded the existing `MAX_PILOT_TARGETS = 6` guard. No production dataset was modified and no discovery artifact was admitted.

Batch3 is corrected to four policy-ready admission Base Devices plus one admitted Active lifecycle control. STM32F446RC and STM32F446RE are deferred together to Batch4. Canonical dataset admission remains disabled until retained official-ST evidence and a clean deterministic admission proposal exist.

Correction commit: `ee5739fb46d24c13667375df8fbe372703cdd78d`.
