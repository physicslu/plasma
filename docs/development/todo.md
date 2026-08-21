# Plasma Development TODO

This file tracks approved architectural work that is intentionally deferred from the current implementation scope.

## High Priority

### Backend PPU Execution Ownership / Lease

**Status:** TODO  
**Layer:** Backend control-plane invariant  
**Reason:** The Web UI mode-switch guard only prevents accidental operator navigation in one browser. It cannot prevent another browser tab, another PC, Plasma Manager, or a direct REST client from submitting conflicting work to the same PPU.

Required invariant:

```text
one PPU -> at most one active execution owner
```

The backend must own and enforce an execution lease/ownership record for each PPU. Production Mode and Engineering Mode are clients of that invariant, not its source of truth.

Expected behavior:

- Acquire an execution lease before dispatching a PPU Job.
- Keep the lease while any Site Job for that execution owner is submitting, queued, running, or cancelling.
- Reject conflicting execution from another owner/client with an explicit REST error such as `409 PPU_BUSY`.
- Include enough conflict metadata for diagnostics, for example PPU identity and current execution owner.
- Release the lease only after all owned Jobs reach terminal states, including cancellation completion.
- Define stale-owner recovery for browser/network/client loss without terminating valid PPU Jobs incorrectly.
- Enforce the invariant in the Python/backend execution path so direct REST access cannot bypass it.
- Add concurrency tests covering Production vs Engineering, two browser clients, direct REST calls, cancellation races, and stale lease recovery.

Non-goal: do not rely on a disabled P/E navigation control as the concurrency mechanism. That UI guard is UX protection only.
