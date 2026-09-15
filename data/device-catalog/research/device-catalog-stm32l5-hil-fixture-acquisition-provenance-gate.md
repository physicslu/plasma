# STM32L5 HIL fixture acquisition and provenance gate

## Purpose

This research-only gate closes the software-only portion of STM32L5 HIL preparation. It defines the evidence required before any physical STM32L552/STM32L562 device can be accepted as a HIL fixture.

It does **not** acquire hardware, create security states, authorize debug/flash operations, or admit STM32L5 into Production.

## Current verified state

- Retained STM32L5 commercial ICPNs: **49**.
- Verified acquired physical fixtures: **0**.
- Verified security-state provenance slots: **0**.
- Full HIL matrix: **20 test cells**.
- Fail-closed reference allocation: **14 state-specific fixture slots** = 2 device lines × 7 security states.
- HIL execution ready: **false**.
- Production/runtime programming authorization: **false**.

## What counts as acquisition evidence

A procurement plan, distributor listing, development-board model, photograph without immutable asset identity, or self-attestation is insufficient.

A future fixture record must bind at minimum:

1. immutable fixture identifier;
2. physical asset record;
3. acquisition/transfer record;
4. retained exact commercial ICPN;
5. device line;
6. physical marking evidence;
7. custodian/lab and custody record;
8. received timestamp and supplier/source;
9. availability state;
10. pre-provisioned security state and fixture class;
11. security-state provenance and evidence digest;
12. security-state verification timestamp.

## Security-state allocation

The reference allocation uses one pre-provisioned fixture slot per `(device line, security state)` pair. Secure/non-secure execution-context cells may reuse the same state-specific fixture only when TZEN/RDP state is unchanged and the execution context is separately evidenced.

RDP2 fixtures must already be RDP2 before entering Plasma HIL and must be terminal sacrificial assets. Plasma may not create RDP2, regress RDP, write option bytes, or mutate security state in this gate.

## Gate result

The schema, identity boundary, provenance requirements, and reference allocation are complete. No physical acquisition has been evidenced, so the gate remains blocked on an external dependency.

**Blocker:** external STM32L552/STM32L562 hardware acquisition plus immutable asset/custody/security-state provenance.

## Exact ICPN count

**1,862** — Production catalog unchanged.

## Next action

`external_stm32l5_fixture_acquisition_and_provenance_submission`

There is intentionally **no next software-only research gate**. Further HIL progression requires real physical evidence.
