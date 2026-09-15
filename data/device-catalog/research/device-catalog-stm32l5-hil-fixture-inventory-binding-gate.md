# STM32L5 HIL fixture inventory binding gate

## Purpose

This transaction binds the merged STM32L5 HIL readiness plan to real physical fixtures. It must not convert catalog evidence, a development-board model name, or a plausible part number into a physical-HIL claim.

## Current physical inventory result

No verified STM32L552/STM32L562 fixture inventory was found in the repository, and no external physical asset evidence was supplied to this transaction.

Therefore the only defensible binding result is:

- verified physical fixtures: **0**
- HIL matrix cells bound: **0 / 20**
- fixture inventory bound: **false**
- HIL execution ready: **false**
- HIL executed: **false**

This is a hard external asset blocker, not a software validation failure.

## Identity boundary

The binding schema accepts only exact commercial ICPNs from the retained ST manufacturer identity set:

- STM32L5 exact commercial ICPNs: **49**
- device lines: STM32L552 / STM32L562
- global Production exact ICPNs: **1,862**

A fixture record must identify the exact commercial ICPN and must have an immutable physical asset record plus security-state provenance. Placeholder, synthetic, guessed, or self-attested fixture records are rejected.

## Security boundary

The binding gate cannot create the state it intends to validate.

- Plasma may not create or change TZEN/RDP state.
- The binding gate may not write option bytes, regress RDP, mass erase, or otherwise mutate security state.
- RDP2 fixtures must already exist as terminal sacrificial assets with provenance.
- No HIL execution is authorized by this gate.

## Required future fixture evidence

Each real fixture must supply at least:

- unique fixture identifier
- physical asset record reference
- exact commercial ICPN
- device line
- fixture class
- pre-provisioned security state
- security-state provenance reference and digest
- custodian/lab identity
- availability status
- inventory verification timestamp

CI can validate the structure and fail-closed semantics of those records, but it cannot prove a claimed physical asset exists. Physical custody/provenance evidence is therefore a separate engineering input.

## Gate result

The schema and 49-part commercial identity boundary are validated, but no real fixtures are bound. Production/runtime/HIL claims remain closed.

## Next gate

**STM32L5 HIL fixture acquisition and provenance gate**

That gate requires actual hardware inventory. Until real L552/L562 fixtures and immutable security-state provenance are supplied, continuing toward HIL execution would be evidence fabrication.
