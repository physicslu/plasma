#!/usr/bin/env python3
"""Host-only guards for the independent ARMv7 cross-build A/B experiment."""
from pathlib import Path
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[3]
UPSTREAM = "5088db4c9154ca833c6d558381074b33672e127a"
BASELINE = REPO / "scripts/ci/build-openocd5088-armv7.sh"
CROSS = REPO / "scripts/ci/build-openocd5088-armv7-cross.sh"
VERIFY = REPO / "scripts/ci/verify-openocd5088-armv7.sh"
WORKFLOW = REPO / ".github/workflows/swd-openocd5088-armv7-cross-poc.yml"
REQUIRED = REPO / ".github/workflows/swd-openocd5088-armv7-candidate.yml"


class CrossBuildGate1Contracts(unittest.TestCase):
    def test_same_upstream_and_plasma_injector(self):
        native = BASELINE.read_text()
        cross = CROSS.read_text()
        for text in (native, cross):
            self.assertIn(UPSTREAM, text)
            self.assertIn("inject-plasma-openocd5088-native.py", text)
            self.assertIn("--disable-internal-libjaylink", text)
            self.assertIn("--enable-internal-jimtcl", text)
            self.assertIn("make -j2", text)

    def test_cross_uses_native_host_and_armhf_target_packages(self):
        cross = CROSS.read_text()
        for needle in (
            "--platform linux/amd64", "ubuntu:22.04", "dpkg --add-architecture armhf",
            "gcc-arm-linux-gnueabihf", "libusb-1.0-0-dev:armhf",
            "--host=arm-linux-gnueabihf", "PKG_CONFIG_LIBDIR=",
            "arm-linux-gnueabihf-readelf", "--volume \"$GITHUB_WORKSPACE:/plasma:ro\"",
        ):
            self.assertIn(needle, cross)
        self.assertNotIn("--privileged", cross)
        self.assertNotIn("/dev/mem", cross)

    def test_workflow_is_non_required_hosted_only_and_a_b_verifies(self):
        wf = WORKFLOW.read_text()
        required = REQUIRED.read_text()
        self.assertIn("  armv7-source-locked-candidate:", required)
        self.assertNotIn("armv7-cross-cold-experiment", required)
        for needle in (
            "  armv7-cross-cold-experiment:", "runs-on: ubuntu-24.04",
            "build-openocd5088-armv7.sh", "build-openocd5088-armv7-cross.sh",
            "verify-openocd5088-armv7.sh", "persist-credentials: false",
            "GITHUB_STEP_SUMMARY", "if: always()", "pull_request:",
        ):
            self.assertIn(needle, wf)
        self.assertEqual(wf.count("bash scripts/ci/verify-openocd5088-armv7.sh"), 2)
        for prohibited in ("runs-on: self-hosted", "actions/cache/", "upload-artifact",
                           "workflow_dispatch", "docker/login-action", "ssh ", "sudo "):
            self.assertNotIn(prohibited, wf)

    def test_scripts_have_valid_shell_syntax(self):
        for script in (BASELINE, CROSS, VERIFY):
            with self.subTest(script=script.name):
                subprocess.run(["bash", "-n", str(script)], check=True)


if __name__ == "__main__":
    unittest.main()
