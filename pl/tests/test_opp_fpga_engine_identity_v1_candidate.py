"""Host-only checks for OPP FPGA Engine Identity candidate; no hardware access."""
import json
import re
import unittest
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[1] / "verification" / "opp_fpga_engine_identity_v1_candidate.json"


def admit(manifest, actual):
    required = {
        "engine_id", "image_id", "image_name", "build_id", "engine_abi",
        "target_fpga_part", "artifact_sha256", "capabilities",
        "site_count", "board_compatibility",
    }
    if not required.issubset(manifest):
        return "ENGINE_IDENTITY_UNAVAILABLE"
    if not re.fullmatch(r"plasma-[a-z0-9]+-[a-z0-9]+-v\d+\.\d+\.\d+", manifest["image_name"]):
        return "INVALID_IMAGE_NAME"
    if any(token in manifest["image_name"].split("-") for token in ("z2", "pynq")):
        return "INVALID_IMAGE_NAME"
    if not re.fullmatch(r"[0-9a-f]{32}", manifest["build_id"]):
        return "INVALID_BUILD_ID"
    if not re.fullmatch(r"[0-9a-f]{64}", manifest["artifact_sha256"]):
        return "INVALID_ARTIFACT_SHA"
    if manifest["target_fpga_part"] != actual.get("fpga_part"):
        return "FPGA_DEVICE_MISMATCH"
    if actual.get("board") not in manifest["board_compatibility"]:
        return "HW_PLATFORM_MISMATCH"
    if manifest["artifact_sha256"] != actual.get("artifact_sha256"):
        return "IMAGE_BUILD_MISMATCH"
    if manifest["build_id"] != actual.get("build_id"):
        return "IMAGE_BUILD_MISMATCH"
    if manifest["engine_abi"] != actual.get("engine_abi"):
        return "ENGINE_ABI_MISMATCH"
    if not set(actual.get("required_capabilities", [])).issubset(set(manifest["capabilities"])):
        return "CAPABILITY_UNAVAILABLE"
    if manifest["site_count"] < actual.get("required_sites", 0):
        return "CAPABILITY_UNAVAILABLE"
    return "PASS_HOST_ONLY"


class TestCandidate(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "engine_id": "plasma.swd.independent",
            "image_id": "plasma.swd.independent",
            "image_name": "plasma-xc7z020-swd-v1.0.0",
            "build_id": "1" * 32,
            "engine_abi": 5,
            "target_fpga_part": "xc7z020clg400-1",
            "artifact_sha256": "a" * 64,
            "capabilities": ["swd"],
            "site_count": 2,
            "board_compatibility": ["engine-board-r1"],
        }
        self.actual = {
            "fpga_part": "xc7z020clg400-1",
            "board": "engine-board-r1",
            "artifact_sha256": "a" * 64,
            "build_id": "1" * 32,
            "engine_abi": 5,
            "required_capabilities": ["swd"],
            "required_sites": 2,
        }

    def test_contract_preserves_existing_offsets(self):
        data = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertFalse(data["ownership"]["opf_core_required"])
        self.assertIsNone(data["mmio_candidate"]["scratch_offset"])
        self.assertEqual(data["mmio_candidate"]["existing_offsets"]["SITE_PRESENT_BITMAP"], 48)
        self.assertEqual(data["mmio_candidate"]["existing_offsets"]["BUILD_ID_W0"], 24)

    def test_reference_positive(self):
        self.assertEqual(admit(self.manifest, self.actual), "PASS_HOST_ONLY")

    def test_other_fpga_vendor(self):
        self.manifest["image_name"] = "plasma-10cl025-swd-v1.0.0"
        self.manifest["target_fpga_part"] = self.actual["fpga_part"] = "10cl025yu256c8g"
        self.assertEqual(admit(self.manifest, self.actual), "PASS_HOST_ONLY")

    def test_wrong_device(self):
        self.actual["fpga_part"] = "xc7z010clg400-1"
        self.assertEqual(admit(self.manifest, self.actual), "FPGA_DEVICE_MISMATCH")

    def test_wrong_board(self):
        self.actual["board"] = "other-pinout"
        self.assertEqual(admit(self.manifest, self.actual), "HW_PLATFORM_MISMATCH")

    def test_wrong_digest(self):
        self.actual["artifact_sha256"] = "b" * 64
        self.assertEqual(admit(self.manifest, self.actual), "IMAGE_BUILD_MISMATCH")

    def test_wrong_build(self):
        self.actual["build_id"] = "2" * 32
        self.assertEqual(admit(self.manifest, self.actual), "IMAGE_BUILD_MISMATCH")

    def test_wrong_abi(self):
        self.actual["engine_abi"] = 6
        self.assertEqual(admit(self.manifest, self.actual), "ENGINE_ABI_MISMATCH")

    def test_missing_identity(self):
        del self.manifest["build_id"]
        self.assertEqual(admit(self.manifest, self.actual), "ENGINE_IDENTITY_UNAVAILABLE")

    def test_missing_capability(self):
        self.actual["required_capabilities"] = ["jtag"]
        self.assertEqual(admit(self.manifest, self.actual), "CAPABILITY_UNAVAILABLE")

    def test_board_named_image_rejected(self):
        self.manifest["image_name"] = "plasma-z2-swd-v1.0.0"
        self.assertEqual(admit(self.manifest, self.actual), "INVALID_IMAGE_NAME")


if __name__ == "__main__":
    unittest.main()
