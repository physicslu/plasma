# Plasma AI Assisted Git Development Workflow

## Purpose

This document defines the standard development lifecycle for Plasma when using AI coding agents.

AI agents must follow this workflow before changing source code, configuration, deployment behavior, hardware behavior, or documentation.

The workflow has **exactly two user approval gate types**:

1. **Gate 1 — Plan Approval**
2. **Gate 2 — Merge Approval**

Everything between those gates is autonomous execution within the approved scope. Mechanical lifecycle transitions such as Draft -> Ready for review are not approval gates.

## Standard Flow

```text
Requirement / read-only inspection
        ↓
Gate 1 — Plan Approval
        ↓
Feature Branch
        ↓
AI Assisted Development
        ↓
Focused Tests
        ↓
Draft PR
        ↓
CI Validation / CI Repair
        ↓
Draft -> Ready for review  ← automatic agent action
        ↓
Final Diff / Mergeability Review
        ↓
Gate 2 — Merge Approval
        ↓
Merge main
        ↓
Approved post-merge Deployment / Runtime / Hardware Acceptance
        ↓
Completion Report
```

Post-merge deployment, runtime acceptance, or hardware validation proceeds automatically when it was explicitly included in the Gate 1 plan. It does **not** create a third approval gate.

If a necessary action materially exceeds the approved plan, the agent must stop and propose a revised plan. Approval of that revised plan is still **Gate 1**, not a new gate type.

## Approval Gate Policy

### Gate 1 — Plan Approval

Before implementation starts, the agent provides a concise plan covering:

- intended scope and non-goals;
- main files/layers likely to change;
- validation approach;
- deployment/runtime/hardware actions, when applicable;
- material architectural, security, destructive-Git, or hardware risk, when applicable.

Explicit approval such as `approve`, `開始`, `可以`, or equivalent authorizes autonomous execution of the stated scope.

After Gate 1, the agent should not repeatedly ask whether it may:

- create or update a branch;
- edit files;
- commit or push;
- create a Draft PR;
- run tests or CI;
- repair deterministic CI failures;
- rerun evidence-supported flaky checks;
- update PR metadata;
- change Draft -> Ready for review;
- perform approved deployment/runtime acceptance;
- perform approved hardware validation.

Those are execution steps, not approval gates.

### Gate 2 — Merge Approval

The agent stops when the PR is genuinely merge-ready and reports:

- what changed;
- what was validated;
- what was not validated;
- branch / PR / CI state;
- known limitations or remaining risks.

Only then does the user approve merge to `main`.

After Merge Approval, the agent merges and verifies the resulting `main` state. If the Gate 1 plan included post-merge deployment or acceptance, the agent continues those steps automatically without asking for another approval.

## Draft -> Ready Policy

`Draft -> Ready for review` is a **mechanical PR lifecycle transition** and must be performed automatically when all merge-ready preconditions that can be checked before human merge approval are satisfied.

The agent must not turn this transition into a third gate.

If a GitHub connector or permission defect prevents the agent from changing Draft -> Ready, that is a **tooling exception**, not an approval gate. The agent may ask the user to perform the mechanical action, but must not describe the click as an additional approval decision.

## Scope Escalation Policy

Exactly two gate types remain in force even for higher-risk work.

The following actions must be explicitly covered by the Gate 1 plan before execution:

- deployment or shared-service restart;
- active systemd, routing, firewall, or runtime configuration changes;
- Z2 / FPGA / real-target operations;
- real IC programming or DUT power/voltage changes;
- destructive or history-rewriting Git operations;
- material architecture or security decisions;
- substantial scope expansion.

If such an action was already stated in the approved Gate 1 plan, proceed autonomously when its turn arrives.

If it was not stated and becomes necessary later, stop, explain the new scope/risk, and request a **revised Gate 1 Plan Approval**. Do not invent a third approval gate.

## Workflow Rules

### 1. Requirement and Plan

Define:

- user requirement;
- expected behavior;
- UI/API/architecture contract where applicable;
- scope boundary;
- non-goals;
- validation and acceptance boundary.

Use read-only inspection to resolve facts before Gate 1. Do not begin implementation before Plan Approval.

### 2. Feature Branch

All feature work normally starts from:

```text
agent/<feature-name>
```

or another purpose-specific branch naming convention already established by the repository.

`main` is the integration/deployment branch, not an AI scratch workspace.

### 3. AI Assisted Development

After Gate 1, AI agents own routine execution within scope:

- implementation;
- refactoring;
- tests;
- documentation;
- branch/commit/PR maintenance;
- CI observation and repair;
- Ready-for-review transition.

Humans retain product authority through Plan Approval and Merge Approval.

### 4. Validation

Validation layers may include:

```text
Unit / Source Test
    ↓
SSR / Rendered HTML
    ↓
Playwright Browser E2E
    ↓
Visual Regression
    ↓
Deployment / Runtime Validation
    ↓
Z2 / FPGA / Real-target Validation when applicable
```

Passing a lower layer does not prove a higher layer.

Validation itself is not an approval gate.

### 5. Pull Request Lifecycle

Create a focused PR and keep it Draft while implementation or CI repair is incomplete.

PR must accurately state:

- change summary;
- validation results;
- known limitations;
- explicit out-of-scope items.

When implementation, relevant validation, CI, diff review, and mergeability are satisfactory, change Draft -> Ready automatically.

### 6. Merge Main

Merge requires:

- implementation complete;
- relevant CI passing;
- review/diff checks complete;
- PR mergeable;
- no evidence claim beyond what was actually tested;
- explicit Gate 2 Merge Approval.

### 7. Post-merge Deployment and Acceptance

When included in the approved Gate 1 plan:

```text
GitHub main
      ↓
Deployment / service reconciliation
      ↓
Runtime acceptance
      ↓
Hardware acceptance when applicable
```

Do not ask for a separate deployment approval after merge merely because deployment is the next lifecycle step.

If deployment or hardware work was not part of the approved plan, request a revised Gate 1 plan before doing it.

### 8. Tooling Exceptions

Missing permissions, connector bugs, unavailable SSH/remote-shell access, or other external blockers may require the user to perform a mechanical step or provide output.

That interaction is not automatically an approval gate. Distinguish clearly between:

- **approval decision** — only Gate 1 or Gate 2;
- **mechanical assistance** — user performs an action because the agent lacks tool access;
- **scope revision** — requires another Gate 1 approval because the plan changed materially.

## AI Agent Requirement

AI agents must:

1. Read `AGENTS.md` before changes.
2. Enforce the exact Two-Gate Model.
3. Preserve architecture and safety contracts.
4. Continue autonomously after Gate 1 within approved scope.
5. Run relevant validation before merge-ready.
6. Change Draft -> Ready automatically when merge-ready.
7. Stop for user approval only at Gate 1 or Gate 2; unexpected scope expansion returns to Gate 1 rather than creating a third gate.
8. Never claim deployment, runtime, FPGA, or hardware success without observed evidence.
