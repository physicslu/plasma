# Plasma Batch Domain Model Architecture

## 1. Purpose

This document defines the domain model boundary for Plasma batch programming operations.

The goal is to provide a common language and architecture contract between:

- Web Console
- REST API
- Batch Controller
- Scheduler
- Channel Manager
- Programmer Hardware Layer
- FPGA / PL execution layer

This document is an architecture reference. It does not define implementation details.

---

## 2. Core Design Principles

### Batch is not execution

A Batch represents a user requested operation group. It is an aggregate container.

Actual execution happens at the Site execution boundary.

```
Batch
 |
 +-- Site Execution 1
 +-- Site Execution 2
 +-- Site Execution 3
```

Each Site can independently become:

- RUNNING
- PASS
- FAIL
- CANCELLED

A failed Site must not block other Sites.

---

## 3. Domain Hierarchy

```
Factory
 |
Facility
 |
Programmer (PPU)
 |
Site
 |
Batch
 |
Site Execution
 |
Operation
 |
Programming Image
```

---

## 4. Domain Entities

## Factory

Top-level manufacturing environment.

Future expansion point for multiple production locations.

---

## Facility

A physical production area containing programmers.

Example:

```
Facility A
 |
 +-- PPU-001
 +-- PPU-002
```

---

## Programmer (PPU)

Represents one physical programmer device.

Responsibilities:

- Hardware identity
- Capability information
- Number of Sites
- Connection status

Example:

```
PPU-001
 |
 +-- Site 1
 +-- Site 2
 +-- Site 3
 +-- Site 4
```

---

## Site

The smallest execution resource.

A Site is the scheduling boundary.

Responsibilities:

- Execute programming operation
- Maintain runtime state
- Report result independently

---

## Programming Image

The data source used for programming.

Terminology:

- Programming Image (formal)
- Image (short name)
- Shared Image (multiple Sites use the same Image)

Attributes:

- filename
- size
- checksum
- storage reference

Example:

```
Shared Image
 |
 +-- Site 1 execution
 +-- Site 2 execution
 +-- Site 3 execution
```

---

## Batch

A user-level operation request.

Responsibilities:

- Group Site executions
- Apply Batch Policy
- Provide overall progress summary

A Batch does not directly control hardware execution.

---

## Site Execution

The real execution unit.

Responsibilities:

- Bind Site + Operation + Image
- Maintain progress
- Report result
- Handle cancellation

---

## Operation

Defines the requested programming action.

Current operations:

```
ERASE
PROGRAM
VERIFY
READ
```

Future extensions:

```
BLANK_CHECK
SECURE
OTP
LOCK
```

---

## 5. Batch Policy

Batch Policy controls execution behavior.

Examples:

- Retry count
- Failure threshold
- Stop conditions

Policy affects scheduling decisions but does not change Site execution semantics.

---

## 6. Scheduler Relationship

Correct model:

```
Batch
 |
 Scheduler
 |
 +-- Site Worker
 +-- Site Worker
 +-- Site Worker
 |
 Hardware Interface
```

Incorrect model:

```
Batch
 |
 Execute all Sites sequentially
```

---

## 7. Production / Engineering Mode Relationship

Production Mode and Engineering Mode share the same domain model.

Only runtime policy and available controls differ.

```
             Domain Model
                  |
       +----------+----------+
       |                     |
 Production Mode     Engineering Mode
```

---

## 8. Naming Rules

Use:

- Image
- Programming Image
- Shared Image
- Batch
- Site Execution

Avoid ambiguous names:

- firmware_file
- program_file
- binary_file
- BatchJob

unless a future architecture decision introduces them explicitly.

---

## 9. Future Migration Direction

Future implementation work should evaluate:

1. Existing Python models against this domain model
2. API contract alignment
3. Scheduler ownership boundaries
4. Persistence requirements
5. Multi-programmer deployment support

This document is the architecture baseline before code migration.
