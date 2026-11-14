# OPF user Bundle v3 source-independent admission — host evidence

Work Order SHA256: `2f3ed29d734b06cb27a8bcfe27db1db865917d61fba99d4f4a3cac1e9f1ecd1f`.
Verified against the dispatched canonical JSON. Exact pinned source/base HEAD:
`d17810e8100954fb7f92ab905338354e94c533ae`. This is a worktree patch against that source,
not a published commit or merge-ready PR. No floating main update was used.

Path: **3**, `workspace-write`, executor `SWPC-plasma-codex`, GitHub
engineering run `42142814250`, job `development-codex`. That run identifies
this engineering execution; it is not CI acceptance of this uncommitted patch.
No new GitHub CI run/job or PR ID exists.

## Result and scope

Implemented the canonical v3 user policy across verifier, B2/B3 Coordinator,
Bootstrap dispatch, installed-device CLI, installer receipt reuse, staged Set
verification, local producer, diagnostic client, tests and current docs.
`source_commit` is optional SHA40-shaped, untrusted provenance; omission yields
`null` in emitted receipts. B3 also accepts an omitted provenance field in B2.
There is no GitHub lookup, publisher signature or CI whitelist prerequisite.
Expected-source arguments were removed across canonical v3 APIs and callers;
no compatibility source-pin path was added.

The existing authenticated paired owner MAC remains bound to device, exact
ZIP SHA256, current transaction and action. Schema, Package DAG, exact ZIP/file
SHA256, target, separate FPGA static qualification, reload/ownership and
SAFE_OFF/resource/permission guards remain. Non-FPGA `activate` with
`fpga_load:false` succeeds under a held Runtime lease; FPGA activation requires
explicit load plus separate load authorization. Installation never executes
uploaded code or starts a DUT operation. Runtime Release, factory/CI identity
and trusted Dispatcher source pins are unchanged. The later OPF P0 Step 2 migration removes the factory FPGA Image ID contract;
Root hardware and operation guards still apply.

## Observed validation

- **PASS**, exit **0**, **71 tests** (15 new user Bundle tests, 3 existing
  journal tests, 53 existing simulated Root safety tests):
  `python3 -m unittest software.python.tests.test_ppu_user_bundle_v3 software.python.tests.test_ppu_bundle_v3_b3_b4_journal_gate1 scripts.tests.test_fpga_image_root -v`.
- **PASS**, exit **0**: AST parsing of all 19 changed Python files and repository
  call-site audit for removed canonical source-pin parameters. The sole
  remaining test call supplies the retired parameter to prove rejection.
- **PASS**, exit **0**: `git diff --check`.
- **NOT_RUN**, broader pytest regressions: `python3 -m pytest --version`
  exited **1** (`No module named pytest`). No packages were installed.
- **NOT_RUN**, existing Site safety suite: attempted
  `PYTHONPATH=software/python python3 -m unittest software.python.tests.test_site_safety -v`
  exited **1** during import (`StrEnum` unavailable in Python 3.10).
  The project Python runtime requires >=3.11. The new dependency-free tests
  independently exercise busy Runtime, Site ownership/seal and injected
  SAFE_OFF-failure denials using synthetic adapters only.
- **NOT_RUN**, GitHub CI: the Bootstrap workflow now includes the new test
  file in push/PR path filters and its regression command, but this patch
  has not been published or dispatched. Full pytest and Python >=3.11 Site
  safety acceptance remain pending in a suitable environment.
- **NOT_RUN**, Draft PR publication: the Work Order expressly prohibits
  credential use. No authenticated Git push, GitHub API write or CI dispatch
  was attempted. Deliver the patch/evidence through the trusted publisher;
  then run relevant CI and create the Draft PR before Gate 2 readiness.
- **NOT_RUN**, all new live SWPC/Z2 deployment, package installation on a live
  host, SSH, FPGA load/Identity readback, DUT operations and recovery.
  Existing physical evidence is unchanged and historical only.

Host tests use temporary product/state roots, synthetic test credentials,
reviewed local fixture bytes and injected Runtime/Root adapters. The actual
engine subprocess test uses `stage_only` and temporary roots. No uploaded
Python/native payload is executed by these new tests. PASS here qualifies
host contract behavior only, not physical PPU/ABI/Site readiness.

## Exact changed files

- `.github/workflows/ppu-bootstrap.yml`
- `docs/architecture/ppu-canonical-bundle-packages.md`
- `docs/deployment/ppu-bundle-v3-generic-assets-gate1.md`
- `docs/deployment/ppu-owner-operation-authorization.md`
- `docs/development/opf-user-bundle-source-agnostic-host-20261106.md`
- `examples/ppu-bundle-v3-smoke/README.md`
- `scripts/ppu-bootstrap-deployment.py`
- `scripts/ppu-bootstrap-service.py`
- `scripts/ppu-bundle-v3-smoke.py`
- `scripts/ppu-z2-installer.py`
- `scripts/ppu_asset_set.py`
- `scripts/ppu_deploy_api.py`
- `scripts/ppu_path2_hardware_baseline.py`
- `scripts/ppu_unified_deployment.py`
- `software/python/tests/test_ppu_asset_execution_gate1.py`
- `software/python/tests/test_ppu_b3_fpga_load_gate1.py`
- `software/python/tests/test_ppu_b3_z2_install_gate1.py`
- `software/python/tests/test_ppu_bundle_v3_packages_contract.py`
- `software/python/tests/test_ppu_bundle_v3_single_engine_gate1.py`
- `software/python/tests/test_ppu_bundle_v3_smoke_execution_gate1.py`
- `software/python/tests/test_ppu_fpga_static_qualification_gate1.py`
- `software/python/tests/test_ppu_generic_package_host_only_gate1.py`
- `software/python/tests/test_ppu_pr3_host_only_unified_deployment.py`
- `software/python/tests/test_ppu_stage_c1_execution_scope.py`
- `software/python/tests/test_ppu_user_bundle_v3.py`

## Handoff

The delivered binary-capable Git patch contains every file above, including
new files. The accompanying JSON records its SHA256 and the test log hash.
No merge, deployment or hardware operation was performed. Gate 1 host
implementation is delivered; environment/publication blockers prevent full
acceptance. **Next Gate is Gate 2 only after a specific PR is merge-ready and
separately owner-approved.**
