"""Host-only positive and adversarial F1-B HIL-B1 admission contracts."""
import unittest
from pl.hil.fixed_b1_contract import (
    B1Blocked, FPGA_BASE, FPGA_END, IDENTITY_OFFSETS, admit_ownership,
    one_shot, overlaps_64k, read_identity, verify_pins,
    F1_BIT_SHA256, F1_HWH_SHA256, BASE_BIN_SHA256, BASE_HWH_SHA256,
    CANDIDATE_BIN_SHA256,
)


class B1OfflineContracts(unittest.TestCase):
    def pins(self):
        return dict(bit_sha256=F1_BIT_SHA256, hwh_sha256=F1_HWH_SHA256,
                    recovery_bin_sha256=BASE_BIN_SHA256,
                    recovery_hwh_sha256=BASE_HWH_SHA256,
                    candidate_bin_sha256=CANDIDATE_BIN_SHA256)

    def test_exact_build_and_recovery_pins(self):
        verify_pins(self.pins())
        for field in self.pins():
            bad = self.pins()
            bad[field] = "WRONG"
            with self.subTest(field=field), self.assertRaises(B1Blocked):
                verify_pins(bad)
        with self.assertRaisesRegex(B1Blocked, "BIN_UNPINNED"):
            verify_pins({k: v for k, v in self.pins().items()
                         if k != "candidate_bin_sha256"})
        with self.assertRaisesRegex(B1Blocked, "BIN_NOT_PINNED"):
            verify_pins(self.pins() | {"candidate_bin_sha256": "a" * 64})

    def test_full_64k_conflicts_and_bound_fabric(self):
        self.assertEqual(FPGA_END - FPGA_BASE, 65536)
        self.assertTrue(overlaps_64k(0x4000F000, 4096))
        self.assertTrue(overlaps_64k(0x3FFFF000, 4096 * 2))
        self.assertFalse(overlaps_64k(0x40010000, 4096))
        good = dict(uio_maps=[], platform_maps=[], unknown_owners=False,
                    open_pl_consumers=False, retained_mmio_maps=False)
        admit_ownership(**good)
        for key in ("unknown_owners", "open_pl_consumers", "retained_mmio_maps"):
            bad = good | {key: True}
            with self.subTest(key=key), self.assertRaises(B1Blocked):
                admit_ownership(**bad)
        fabric = {"base": FPGA_BASE, "size": 0x10000, "driver_bound": True}
        for kind in ("uio_maps", "platform_maps"):
            with self.subTest(kind=kind), self.assertRaisesRegex(
                    B1Blocked, "BOUND_DRIVER_CONFLICT"):
                admit_ownership(**(good | {kind: [fabric]}))
        with self.assertRaisesRegex(B1Blocked, "BOUND_DRIVER_CONFLICT"):
            admit_ownership(**(good | {"uio_maps": [{
                "base": 0x4000F000, "size": 0x1000, "driver_bound": True}]}))
        admit_ownership(**(good | {"uio_maps": [{
            "base": 0x40010000, "size": 0x1000, "driver_bound": True}]}))
        for start, size in ((-1, 1), (FPGA_BASE, 0), (FPGA_BASE, -1)):
            with self.subTest(start=start), self.assertRaises(B1Blocked):
                overlaps_64k(start, size)

    def identity(self):
        return {0x000: 0x4D534C50, 0x004: 0x10000, 0x028: 1,
                0x030: 1, 0x044: 1, 0x048: 4096}

    def test_only_allowlisted_global_identity_reads(self):
        requested = []
        words = self.identity()
        def read(addr):
            requested.append(addr)
            return words[addr - FPGA_BASE]
        result = read_identity(read)
        self.assertEqual(result["site_present"], 1)
        self.assertEqual(requested, [FPGA_BASE + x for x in IDENTITY_OFFSETS])
        for field in self.identity():
            bad = self.identity()
            bad[field] = 0
            with self.subTest(offset=field), self.assertRaises(B1Blocked):
                read_identity(lambda addr: bad[addr - FPGA_BASE])

    def test_oneshot_pass_injected_without_hardware(self):
        called = []
        def cb(name):
            return lambda: called.append(name)
        out = one_shot(preflight=cb("preflight"),
                       load_candidate=cb("load"),
                       identity_child=lambda: {
                           "magic": 0x4D534C50, "abi": 0x00010000,
                           "capabilities": 1, "site_present": 1,
                           "map_revision": 1, "site_stride": 4096,
                       },
                       child_stopped_and_unmapped=lambda: True,
                       restore_original=cb("restore"),
                       verify_restoration=cb("verify"))
        self.assertEqual(out["overall"], "PASS_INTERNAL_IDENTITY_ONLY")
        self.assertEqual(called, ["preflight", "load", "restore", "verify"])

    def test_oneshot_rejects_missing_or_fake_identity_and_restores(self):
        for fake in ({}, {"magic": 0x4D534C50}, None):
            restored = []
            outcome = one_shot(
                preflight=lambda: None, load_candidate=lambda: None,
                identity_child=lambda: fake,
                child_stopped_and_unmapped=lambda: True,
                restore_original=lambda: restored.append("restore"),
                verify_restoration=lambda: restored.append("verify"))
            self.assertEqual(outcome["overall"], "FAIL_OR_BLOCKED")
            self.assertEqual(outcome["identity"], "NOT_RUN")
            self.assertEqual(restored, ["restore", "verify"])

    def test_preflight_block_does_not_load_or_restore(self):
        called = []
        def stop():
            raise B1Blocked("NO_GO")
        out = one_shot(preflight=stop,
                       load_candidate=lambda: called.append("load"),
                       identity_child=lambda: {},
                       child_stopped_and_unmapped=lambda: True,
                       restore_original=lambda: called.append("restore"),
                       verify_restoration=lambda: None)
        self.assertEqual(out["overall"], "BLOCKED_PREFLIGHT")
        self.assertEqual(called, [])

    def test_partial_load_always_attempts_safe_restore(self):
        called = []
        def fail():
            called.append("load")
            raise B1Blocked("partially programmed")
        out = one_shot(preflight=lambda: None,
                       load_candidate=fail,
                       identity_child=lambda: {},
                       child_stopped_and_unmapped=lambda: True,
                       restore_original=lambda: called.append("restore"),
                       verify_restoration=lambda: called.append("verify"))
        self.assertEqual(out["overall"], "FAIL_OR_BLOCKED")
        self.assertEqual(called, ["load", "restore", "verify"])

    def test_retained_mapping_forbids_reload_and_false_pass(self):
        called = []
        out = one_shot(preflight=lambda: None,
                       load_candidate=lambda: None,
                       identity_child=lambda: (_ for _ in ()).throw(B1Blocked("SIGBUS")),
                       child_stopped_and_unmapped=lambda: False,
                       restore_original=lambda: called.append("DANGEROUS"),
                       verify_restoration=lambda: called.append("DANGEROUS"))
        self.assertEqual(out["overall"], "FAIL_OR_UNKNOWN")
        self.assertEqual(out["restore"], "BLOCKED_UNSAFE")
        self.assertEqual(called, [])

    def test_restoration_failure_cannot_pass(self):
        def fail():
            raise B1Blocked("restore unavailable")
        out = one_shot(preflight=lambda: None,
                       load_candidate=lambda: None,
                       identity_child=lambda: {
                           "magic": 0x4D534C50, "abi": 0x00010000,
                           "capabilities": 1, "site_present": 1,
                           "map_revision": 1, "site_stride": 4096,
                       },
                       child_stopped_and_unmapped=lambda: True,
                       restore_original=fail,
                       verify_restoration=lambda: None)
        self.assertEqual(out["overall"], "FAIL_OR_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
