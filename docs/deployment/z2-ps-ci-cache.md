# Z2 PS ARMv7 Python CI Cache

> Status: CI performance layer only. The cache is disposable and is not a Plasma release or deployment source of truth.

## Purpose

The Z2 PS release workflow builds CPython for Ubuntu 22.04 ARMv7 under QEMU. That build dominates workflow time. A verified cache may reuse the resulting Plasma Python artifact when the build identity is unchanged.

## Cache identity

The cache key binds at least:

```text
cache schema
GitHub runner OS
ARMv7
Ubuntu 22.04 userspace
Python version
Python source SHA-256
workflow/build-recipe hash
z2-python-runtime.py hash
```

No broad restore key is used. A recipe or source change therefore produces a cache miss rather than silently reusing a stale binary.

## Trust boundary

Pull-request workflows may restore a cache created by the trusted default branch, but they do not publish executable cache entries. Cache save is limited to `main` push or an explicit manual run on `main`.

A cache hit skips only the expensive CPython build. It does not skip qualification checks. Every run still:

1. verifies the artifact and detached SHA-256 sidecar without executing ARM code on the x86 host;
2. installs the artifact into a fresh Ubuntu 22.04 ARMv7 userspace;
3. executes the Plasma Python runtime and imports `ssl`, `sqlite3`, and `urllib.request`;
4. publishes a normal per-run GitHub Actions artifact;
5. uses that per-run artifact to assemble and verify the Z2 PS release candidate kit.

## Release boundary

```text
GitHub Actions cache = performance optimization, disposable
GitHub Actions run artifact = current-run qualified input
Canonical PPU release / Z2 kit = deployment candidate
```

Cache loss or eviction must only make CI slower. It must not make the workflow unable to rebuild or verify the release candidate.
