#!/usr/bin/env python3
"""One-shot, host-only restore of F103 L2 source changes. Temporary; delete after use."""
import base64
import hashlib
import lzma
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
ENCODED = ROOT / "scripts/ci/.f103_l2_recovery_temp.b64"
MODULE = ROOT / "software/python/plasma_web/stm32f103_low_density_candidate.py"
PATCH_SHA = "a23aa5a1739079fdb00ef027b971658c8e91e2755e129894bd84751d18ddc09f"
MODULE_SHA = "71c29ea38aabeb33932dfda40c90a81f51625d671c9145642998297a823cff5b"
OLD = {
".github/workflows/openocd-software-qualification.yml":"f56749381",
"data/ic-support/evidence/sources.json":"0b45e1500",
"data/ic-support/profiles/memory-geometry/stm32f103c4-16k-v0.json":"49e0a2743",
"data/ic-support/profiles/memory-geometry/stm32f103c6-32k-v0.json":"78a487ec7",
"data/ic-support/profiles/memory-geometry/stm32f103r4-16k-v0.json":"e06527289",
"data/ic-support/profiles/memory-geometry/stm32f103r6-32k-v0.json":"23271c290",
"data/ic-support/profiles/programming/stm32f1-low-density-flash-v0.json":"15aac779b",
"release/openocd-qualification/openocd-0.12.0-stm32f103-low-density-12-v1.json":"99440443c",
"release/openocd-qualification/openocd-0.12.0-stm32f103-v10.json":"cf1169dba",
"release/openocd-qualification/stm32f103-low-density-ds5936-source-lock-v1.json":"66c440a9b",
"release/openocd-qualification/stm32f103-low-density-exact-12-applicability-v1.json":"9c7adbb25",
"scripts/ci/stm32f103_low_density_candidate.py":"cf468599f",
"software/python/plasma_web/openocd_software_qualification.py":"6912bf123",
"software/python/tests/test_catalog_promotion_framework.py":"bee329ffd",
"software/python/tests/test_openocd_software_qualification_v1.py":"676791a33",
"software/python/tests/test_programming_qualification.py":"5611531d4",
"software/python/tests/test_stm32f103_low_density_v10_candidate.py":"b0e4c0d2a",
}
def run(*args, input=None):
    return subprocess.run(args, cwd=ROOT, input=input, capture_output=True, check=True)

def main():
    assert not run("git", "status", "--porcelain").stdout.strip(), "DIRTY_WORKTREE"
    branch = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    assert branch.returncode != 0 or branch.stdout.strip() == "feat/stm32f103-low-density-12-provider-v10", "WRONG_BRANCH"
    assert not MODULE.exists(), "MODULE_ALREADY_EXISTS"
    data = base64.b64decode(ENCODED.read_text().splitlines()[-1], validate=True)
    raw = lzma.decompress(data)
    length = int.from_bytes(raw[:4], "big")
    patch, module = raw[4:4+length], raw[4+length:]
    assert hashlib.sha256(patch).hexdigest() == PATCH_SHA, "PATCH_SHA_MISMATCH"
    assert hashlib.sha256(module).hexdigest() == MODULE_SHA, "MODULE_SHA_MISMATCH"
    assert len(OLD) == 17
    for p, digest in OLD.items():
        actual = run("git", "hash-object", p).stdout.decode().strip()
        assert actual.startswith(digest), "OLD_BLOB_MISMATCH:"+p
    run("git", "apply", "--check", "--whitespace=error", "-", input=patch)
    compile(module, str(MODULE), "exec")
    print("RESTORE_PRECHECK_PASS 17 old Git blobs; patch and module SHA256; git apply --check", flush=True)
    run("git", "apply", "--whitespace=error", "-", input=patch)
    MODULE.write_bytes(module)
    run("git", "diff", "--check")
    print("RESTORED_PASS: 17 changed files + one new Python module", flush=True)
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "software/python")
    tests = [
        ["-m","py_compile","software/python/plasma_web/openocd_software_qualification.py",
         "software/python/plasma_web/programming_qualification.py",
         "software/python/plasma_web/stm32f103_low_density_candidate.py"],
        ["software/python/tests/test_openocd_software_qualification_v1.py"],
        ["software/python/tests/test_programming_qualification.py"],
        ["software/python/tests/test_stm32f103_low_density_v10_candidate.py"],
        ["software/python/tests/test_catalog_promotion_framework.py"],
    ]
    for x in tests:
        r=subprocess.run([sys.executable,*x],cwd=ROOT,env=env,check=False)
        if r.returncode: raise RuntimeError("HOST_ONLY_TEST_FAILED: "+" ".join(x))
    # Remove one-time payload/helper so no temporary recovery file remains in final PR.
    ENCODED.unlink()
    Path(__file__).unlink()
    print("HOST_ONLY_PASS, TEMP_RECOVERY_FILES_REMOVED",flush=True)

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print("RECOVERY_BLOCKED:",type(e).__name__,str(e),file=sys.stderr)
        raise
