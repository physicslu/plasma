# STM32F4 Phase 4.1 R/T Batch3 status

State: browser-readiness fix validation triggered.

The first discovery attempt stopped before any ST acquisition because seven total targets exceeded the existing `MAX_PILOT_TARGETS = 6` guard. No production dataset was modified and no discovery artifact was admitted.

Batch3 is corrected to four policy-ready admission Base Devices plus one admitted Active lifecycle control. STM32F446RC and STM32F446RE are deferred together to Batch4.

The corrected bounded discovery then reached official ST acquisition but remained dirty after one whole-batch retry: attempt 1 had a missing `Marketing Status` readiness marker for STM32F411RE, while attempt 2 timed out waiting for `Quality and Reliability` on STM32F411RC. Because the failed target changed between attempts and the other four targets succeeded each time, the transaction remains fail-closed while the shared browser readiness contract is strengthened.

Browser-readiness fix commit: `53681a72d66b729536f18bf714474951a0e4daac`. Canonical dataset admission remains disabled until retained official-ST evidence and a clean deterministic admission proposal exist.
