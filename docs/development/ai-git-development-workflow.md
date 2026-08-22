# Plasma AI Assisted Git Development Workflow

## Purpose

This document defines the standard development lifecycle for Plasma when using AI coding agents.

AI agents must follow this workflow before changing source code, configuration, deployment behavior, or documentation.

## Standard Flow

```text
Requirement Confirmation
        ↓
Architecture Design
        ↓
Feature Branch
        ↓
AI Assisted Development
        ↓
Unit Test
        ↓
CI Validation
        ↓
PR Review
        ↓
Merge main
        ↓
Render Deploy
        ↓
Acceptance Test
```

## Workflow Rules

### 1. Requirement Confirmation

Define:

- User requirement
- Expected behavior
- UI/API contract
- Scope boundary
- Non-goals

Do not implement from ambiguous requests.

### 2. Architecture Design

Before coding, define:

- Component hierarchy
- Data model
- API contract
- Runtime ownership
- Test strategy

Example:

```text
PE Dashboard
├── FPS Selector
├── Programming Image Section
├── Batch Action Section
├── Batch Policy Section
└── Active FPS Summary
```

### 3. Feature Branch

All feature work starts from:

```text
agent/<feature-name>
```

`main` is the integration branch, not an AI workspace.

### 4. AI Assisted Development

AI agents assist with:

- Implementation
- Refactoring
- Tests
- Documentation

Humans own:

- Architecture decisions
- Requirement validation
- Acceptance criteria
- Merge approval

### 5. Unit Test and CI

Validation layers:

```text
Unit Test
    ↓
SSR / Rendered HTML
    ↓
Playwright Browser E2E
    ↓
Visual Regression
    ↓
Deployment Validation
```

Passing a lower layer does not prove higher-level correctness.

### 6. PR Review

Create PR only when ready for review.

PR must include:

- Change summary
- Test results
- UI screenshots when applicable
- Known limitations

### 7. Merge Main

Merge requires:

- CI passing
- Review completed
- Explicit approval

### 8. Render Deploy

After merge:

```text
GitHub main
      ↓
Render Deploy
      ↓
Runtime Validation
```

Render validates cloud software delivery, not hardware operation.

### 9. Acceptance Test

Acceptance depends on scope:

Software:

- UI behavior
- API behavior
- Runtime behavior

Hardware:

- SWPC deployment
- Z2 validation
- FPGA/PL behavior
- Real IC programming

## AI Agent Requirement

AI agents must:

1. Read `AGENTS.md` before changes.
2. Follow this workflow.
3. Preserve architecture contracts.
4. Run relevant validation before review.
5. Stop at protected approval gates.
