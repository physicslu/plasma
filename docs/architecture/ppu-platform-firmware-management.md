# PPU Platform Firmware Management

Status: implementation contract for Issue #604.

## Purpose

PPU platform lifecycle management is separate from operational Registration and Site programming configuration.

The Console models one PPU as a first-class object with functional surfaces:

```text
PPU
├── Overview
├── Platform
├── Registration
└── Sites
```

## Domain boundaries

### Overview

Read-only operational summary and navigation only. It answers:

- whether the PPU is reachable;
- current platform health;
- installed PPU Platform Firmware identity;
- Bootstrap and Runtime component versions;
- operational Registration state;
- Site ready/busy/fault summary;
- active alerts or update state when known.

Overview does not own mutating actions.

### Platform

Platform owns the PPU appliance lifecycle. Platform maintenance is available for a known/reachable PPU independently of operational Registration.

A Manager registry entry in `pending` lifecycle is sufficient to identify and route to a PPU for Platform maintenance; `commissioned` is the separate operational Registration/admission state for programming management.

Operator-facing Platform scope includes:

- PPU Platform Firmware identity;
- Bootstrap component version;
- Runtime component version;
- platform health and deployment state;
- PPU Platform Firmware update/recovery workflow;
- Bootstrap maintenance authorization used by the update/recovery path.

The Bootstrap pairing token is a Platform maintenance credential. Possessing or verifying it does **not** register the PPU for managed programming operations.

Bootstrap and Runtime remain distinct implementation components and retain their existing deployment/provenance contracts. Product UI must not create a second installer authority.

### Registration

Registration means admission of the PPU into this Console's managed programming fleet. It owns:

- add/remove the known Manager inventory connection;
- pending/commissioned/disabled operational lifecycle;
- validate-and-enable admission;
- selection for managed programming operations;
- operational network commissioning after admission under the existing Manager write gate.

Registration does not own the Bootstrap Platform-maintenance credential and is not a prerequisite for Platform inspection or firmware maintenance.

### Sites

Sites are child resources of a PPU. Site configuration and programming operations require the PPU to be operationally registered/commissioned. Platform maintenance may require trusted idle Site state, but Site configuration is not a prerequisite for Platform inspection or maintenance.

## PPU Platform Firmware product model

To the operator, Bootstrap + Runtime are one PPU Platform Firmware release domain. The Console may display component versions separately for diagnosis, but normal product workflow presents one Platform maintenance surface.

The currently qualified browser update authority deploys the Runtime component through the installed Bootstrap. The UI must state this truthfully: Bootstrap is independently versioned and is not silently rewritten by the Runtime deployment path. A future combined Bootstrap + Runtime package may be admitted only when its Bootstrap update mechanism has its own verified transactional semantics.

The implementation must preserve:

- component provenance;
- exact artifact SHA-256 verification already required by the deployment path;
- target architecture validation;
- lifecycle and trusted-idle gates;
- rollback/recovery behavior;
- separation from FPGA/Programming Logic lifecycle.

Programming Logic (including FPGA bitstreams and Python programming algorithms selected dynamically from ICPN context) is explicitly outside this Platform lifecycle.

## Sequencing

Issue #604 implementation may precede the remaining physical PYNQ-Z2 rollback qualification gates. CI/QEMU success does not qualify physical rollback.

After the productized Platform flow is merge-ready and merged, return to physical Z2 qualification for:

1. controlled activation-failure rollback HIL;
2. reboot-after-rollback HIL.
