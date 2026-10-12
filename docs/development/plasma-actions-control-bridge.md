# PLASMA GitHub Actions Control Bridge

The PLASMA Actions control bridge provides a narrow, auditable control path for
ChatGPT to request selected GitHub Actions operations that are not exposed by
the normal GitHub connector.

## Security boundary

The bridge is intentionally fail-closed:

- repository: `physicslu/plasma`;
- dedicated control channel: Issue #814;
- allowed actor: `physicslu`;
- dispatch ref: `main`;
- only workflows listed in `.github/plasma-actions-control.json` may be
  dispatched, cancelled, or re-run through the bridge;
- the control job receives `actions: write` and `contents: read` only;
- no arbitrary shell, arbitrary GitHub API endpoint, secrets administration,
  branch administration, force push, or runner administration is exposed;
- all commands remain visible in the GitHub Issue and Actions audit trail.

The workflow also contains static checks for Issue #814 and actor
`physicslu`, while the checked-in configuration repeats those checks as
defense in depth.

## Commands

Commands are accepted only as exact three-token comments on Issue #814.

Dispatch an allowlisted workflow on `main`:

```text
/plasma-actions dispatch z2like-demo-browser-live-acceptance.yml
```

Cancel an allowlisted workflow run on `main`:

```text
/plasma-actions cancel 38191574110
```

Re-run an allowlisted workflow run on `main`:

```text
/plasma-actions rerun 38191574110
```

For `cancel` and `rerun`, the bridge first fetches the workflow run and
verifies both its workflow filename and branch before performing the action.
A run ID by itself is not sufficient authorization.

## Allowlist changes

The allowlist is version-controlled in:

```text
.github/plasma-actions-control.json
```

Adding a workflow therefore requires the normal PLASMA branch/PR/CI/merge
process. The bridge cannot expand its own allowlist at command-execution time.

## Validation

Run:

```bash
python3 scripts/plasma-actions-control-bridge-contract.py
```

The contract test checks the fixed issue, actor, branch, workflow filenames,
required permissions and pinned GitHub Script action, and rejects selected
unsafe workflow patterns.
