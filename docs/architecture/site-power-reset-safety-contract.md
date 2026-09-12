# Site Power / Reset Safety Contract

## Purpose

A Plasma Programming Site must never allow an already-programmed target IC to execute uncontrolled firmware merely because target power was enabled in the socket.

This contract is independent from the UI and from the selected programming backend. OpenOCD remains responsible for programming/debug transport; Plasma owns Site safety and job lifecycle.

## Safety invariants

For every Site:

1. Target power is OFF by default.
2. Site reset is asserted before target power is enabled.
3. Power-good must be established before reset ownership can be transferred to the programmer.
4. Reset ownership may only be transferred to a programmer path that guarantees connect-under-reset semantics.
5. On success, failure, timeout, or cancellation, the Site must reclaim/assert reset before target power is removed.
6. On cancellation while a programmer operation is active, Plasma must reclaim/assert reset before cancelling the programmer task/process.
7. No other Site is affected by this sequence.

Canonical sequence:

```text
SAFE / POWER OFF
  -> Site assert reset
  -> Target power ON
  -> Wait power-good
  -> Transfer reset control to programmer
  -> Programmer operation
  -> Site reclaim/assert reset
  -> Target power OFF
  -> SAFE
```

Cancellation sequence:

```text
Programmer operation active
  -> cancellation requested
  -> Site reclaim/assert reset
  -> cancel programmer task/process
  -> Target power OFF
  -> SAFE
```

## Reset ownership handoff

`transfer_reset_control_to_programmer()` is an ownership handoff, not a request to let the target execute.

For an OpenOCD runtime, the eventual real implementation must prove that the SWD/SRST path can acquire the target under reset before the Site releases its own reset hold. The exact PS/PL/SRST ownership handshake is still a hardware-runtime qualification item.

A one-shot OpenOCD subprocess alone does not prove that this ownership handoff is electrically safe. Therefore this contract does **not** make the current OpenOCD route hardware-runtime-ready.

## Current software status

`SiteSafetyControl` and `SiteSafetySequencer` define and CI-test the software ordering contract only.

The current OpenOCD production route remains fail-closed:

```text
hardware_runtime_ready = false
```

No real DUT power, NRST/SRST, PL signal, or physical OpenOCD execution is enabled by this change.

## Future hardware mapping

Each Site is expected to provide independent equivalents of:

```text
TARGET_PWR_EN
TARGET_RESET_N / SRST
TARGET_PWR_GOOD
```

Recommended later additions include target voltage sense, current sense/current limit, and controlled discharge.

The real implementation must define fail-safe behavior for PS restart, PL reset, OpenOCD crash, job cancellation, communication loss, and emergency shutdown.

## OpenOCD service exposure

When a real OpenOCD runtime is eventually enabled, production configuration should keep unnecessary interactive/debug services disabled by default. GDB and Telnet are not required for normal offline programming; any automation interface must be explicitly scoped and locally restricted.
