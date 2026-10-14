import unittest
from nxp_adr0002_core_qual_v10 import build,summary,verify,REQUIRED_RULE_HEADINGS

class NxpADR0002ThreeImplementationRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all=build()
        cls.ids={r["icpn"]:r for r in cls.all}

    def test_core_transport_target_driver_exact_are_distinct_dimensions(self):
        k=self.ids["MKL25Z128VFM4"]
        l=self.ids["LPC844M201JBD48E"]
        self.assertEqual(k["core_model"],l["core_model"])
        self.assertNotEqual(k["flash_bank_driver"],l["flash_bank_driver"])
        self.assertNotEqual(k["target_config"],l["target_config"])
        self.assertEqual(l["debug_transport"],"SWD")
        self.assertEqual(k["debug_transport"],"UNKNOWN")
        self.assertNotEqual(k["software_support_qualification"],"SUPPORTED")
        self.assertEqual(l["exact_icpn_applicability"],"UNVERIFIED")

    def test_core_swd_cfg_alone_never_grants_exact_supported(self):
        for r in self.all:
            self.assertNotEqual(r["software_support_qualification"],"SUPPORTED")
            self.assertEqual(r["public_catalog_visibility_authorized"],"false")
            self.assertEqual(r["operation_read_verify_qualification"],"UNKNOWN")
            self.assertEqual(r["exact_icpn_to_silicon_revision"],"UNKNOWN")
            self.assertEqual(r["physical_validation"],"NO_CONFIGURATION_HIL_EVIDENCE_IN_THIS_RESEARCH")
        self.assertEqual(self.ids["LPC802M001JDH16FP"]["research_priority"],"P1")
        self.assertEqual(self.ids["K32L2B11VFT0AR"]["target_config"],"")

    def test_core_unknown_not_arm_and_jtag_boundary_scan_not_programming_transport(self):
        p2=[r for r in self.all if r["research_priority"]=="P2"]
        self.assertEqual(len(p2),436)
        self.assertTrue(all(r["core_architecture"]=="UNKNOWN" and r["debug_transport"]=="UNKNOWN" for r in p2))
        self.assertNotIn("JTAG",{r["debug_transport"] for r in self.all})

    def test_core_aware_denominators(self):
        s=summary(self.all)
        self.assertEqual(s["source_backed_target_driver_research_profiles"],3)
        self.assertEqual(s["core_unknown_exact"],436)
        self.assertEqual(s["transport_unknown_exact"],468)
        self.assertIsNone(s["actual_user_facing_catalog_visible_exact"])
        self.assertIsNone(s["physical_hil_tested_configuration_count"])
        self.assertEqual(s["verified_exact_supported_by_this_new_research"],0)
        self.assertEqual(sum(x["exact_icpn_count"] for x in s["by_manufacturer_core_transport_provider_driver"]),501)

    def test_pinned_byte_replay(self):
        verify()

if __name__=="__main__":
    unittest.main()
