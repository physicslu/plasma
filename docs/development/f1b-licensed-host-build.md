# F1-B licensed runner integration (candidate, not activated)

Vivado startup on Path 3 Run 39620483855 failed with exit 42; category-only
FlexNet diagnostics reported Invalid host. A matching interface in sysfs does
not establish visibility to FlexNet in the sandbox's network namespace.
Network-interface enumeration was denied. There is no same-run unsandboxed
baseline, so namespace causality and host license usability remain unproven.

The candidate change uses the existing engineering dispatcher, existing
`f1b-path3-codex-vivado-build` task and existing Python Build Engine. It adds
no workflow, runner, service, IPC endpoint, arbitrary command transport or
sandbox escape. The trusted dispatcher takes a metadata/category-only runner
baseline before Codex; Codex can compare it with its sandbox observation.
After Codex exits successfully, the trusted dispatcher authenticates every
tracked PL file against the owner-reviewed pinned Git object, ignoring Git
replace refs and comparing bytes rather than trusting the index. Symlinked
inputs and modified PL inputs fail. The executable board helper must also
match trusted main. Candidate build-driver edits are never imported by this
new host route. The existing engine runs twice with separate build/evidence
directories and retains actual child exits, raw logs, verified BIT/HWH hashes
and reports. Failure stops the second build. Vivado startup PASS alone is
never synthesis, implementation or artifact PASS.

This deliberately supports reviewed fixed sources. Codex can diagnose and
propose RTL/Tcl fixes in its sandbox, but host execution of those edits needs
an independently reviewed new pinned SHA. It does not turn a candidate patch
or self-reported source digest into host command authority. Normal source
iteration reuses the same dispatcher/task/engine.

## Activation and pre-merge acceptance

The current job runs trusted-main dispatcher bytes checked out before Codex
started. This patch is only in candidate; it cannot replace that executing
code, access the runner namespace, or create a permitted host executor.
Therefore the new Path 3 mechanism cannot be accepted live pre-merge with the
currently installed dispatcher. This is an executable routing blocker, not a
request for another Gate 1. Do not run candidate dispatcher code outside the
sandbox to work around it, and do not merge on a claim of Build PASS.

An existing pre-merge real-build route is available for a separately reviewed
owner PR: Issue #981 owner command

```text
/plasma-dispatch run fixed-site1-vivado-host-build --pr <PR> --sha <40-hex-reviewed-HEAD> 981
```

Repeat the identical command in a second created comment for a fresh run.
The existing Path 2 dispatcher verifies live same-repository owner PR metadata,
exact HEAD, trusted main and registry binding, then uses its existing reviewed
candidate Build Engine admission. Because that older route imports the pinned
candidate engine, its Python code MUST be independently reviewed and expressly
authorized; do not treat a candidate hash as review or silently run it. This
can validate host licensing and the F1-B project before merge, but it does not
validate the new Path 3 runner/sandbox orchestration. No comments/jobs were
submitted by this job. No concrete PR number or reviewed candidate SHA exists
for these uncommitted edits.

To accept the new Path 3 mechanism itself, a reviewed trusted dispatcher update
must first be activated through normal repository review. Then use the existing
owner command (with a separate reviewed source PR):

```text
/plasma-dispatch run f1b-path3-codex-vivado-build --pr <PR> --sha <40-hex-reviewed-HEAD> 981
```

Inspect same-run `runner-license-diagnostic.json`, sandbox diagnostics,
`host-input-authentication.json`, `licensed-host-builds.json`, each
`host-build-{1,2}/plasma-fpga-build-diagnostics.json`, actual Vivado child exits,
raw logs, timing/DRC reports, and BIT/HWH bytes/hashes. Confirm distinct output
directories. Never substitute GitHub job success or host-only unit tests for
these observations. No Z2 or other physical target operation is included.
