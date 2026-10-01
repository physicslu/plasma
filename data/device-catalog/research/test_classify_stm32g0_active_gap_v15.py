import unittest
import classify_stm32g0_active_gap_v15 as triage

class STM32G0GapTriageV15(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = triage.classify()

    def test_layer1_exact_gap_is_frozen(self):
        layer = self.result["layer1_catalog"]
        self.assertEqual(layer["official_active_exact_total"], 406)
        self.assertEqual(layer["production_exact_current"], 47)
        self.assertEqual(layer["active_exact_gap"], 359)
        self.assertEqual(layer["catalog_identity_candidate_count"], 359)

    def test_backend_state_does_not_gate_identity(self):
        self.assertTrue(
            self.result["layer1_catalog"]["identity_is_not_rejected_by_backend_state"])
        self.assertFalse(
            self.result["layer2_route_observation"]["route_state_gates_layer1_identity"])

    def test_historical_scope_explains_gap(self):
        scope = self.result["historical_scope"]
        self.assertEqual(scope["published_base_device_count"], 12)
        self.assertEqual(
            sum(scope["exact_gap_scope_counts"].values()), 359)

    def test_no_publication_or_physical_claim(self):
        claims = self.result["claims"]
        self.assertFalse(claims["production_write_authorized"])
        self.assertFalse(claims["metadata_complete_for_all_gap_identities"])
        self.assertFalse(claims["backend_support_claimed_for_all_gap_identities"])
        self.assertFalse(claims["physical_validation_claimed"])

if __name__ == "__main__":
    unittest.main()
