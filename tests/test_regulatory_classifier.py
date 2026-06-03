# -*- coding: utf-8 -*-
"""
tests/test_regulatory_classifier.py
Unit tests for the EU regulatory classification layer.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.eu.regulatory_classifier import (
    parse_regulatory_date,
    classify_status_determ,
    classify_regulatory_data,
)

class TestRegulatoryClassifier(unittest.TestCase):

    def test_parse_regulatory_date(self):
        # YYYY-MM-DD
        self.assertEqual(parse_regulatory_date("2026-06-03"), "2026-06-03")
        # DD/MM/YYYY
        self.assertEqual(parse_regulatory_date("03/06/2026"), "2026-06-03")
        # Missing/NaN
        self.assertEqual(parse_regulatory_date(""), "")
        self.assertEqual(parse_regulatory_date(None), "")

    def test_classify_status_determ(self):
        self.assertEqual(classify_status_determ("Approved"), "approved")
        self.assertEqual(classify_status_determ("Not approved"), "not_approved")
        self.assertEqual(classify_status_determ("Withdrawn"), "withdrawn")
        self.assertEqual(classify_status_determ("Expired"), "expired")
        self.assertEqual(classify_status_determ("Banned"), "banned")
        self.assertEqual(classify_status_determ("Not renewed"), "not_renewed")
        self.assertEqual(classify_status_determ("Unknown Status"), "unknown")

    def test_classify_regulatory_data_risk_and_flags(self):
        # Low risk Approved -> low risk tier
        record_low = {
            "substance_status": "Approved",
            "approval_date": "01/01/2020",
            "expiry_date": "31/12/2030",
            "low_risk_active_substance": "Yes",
            "basic_substance": "No"
        }
        res_low = classify_regulatory_data(record_low)
        self.assertEqual(res_low["eu_status_current"], "approved")
        self.assertTrue(res_low["eu_is_low_risk"])
        self.assertEqual(res_low["eu_regulatory_risk_flag"], "low")

        # Substitution Candidate -> high risk tier
        record_subst = {
            "substance_status": "Approved",
            "approval_date": "01/01/2020",
            "expiry_date": "31/12/2030",
            "candidate_for_substitution": "Yes",
            "candidate_for_substitution_type": "Toxic"
        }
        res_subst = classify_regulatory_data(record_subst)
        self.assertTrue(res_subst["eu_candidate_for_substitution"])
        self.assertEqual(res_subst["eu_regulatory_risk_flag"], "high")

        # Expired active substance -> high risk tier & historical flag
        record_exp = {
            "substance_status": "Expired",
            "approval_date": "01/01/2010",
            "expiry_date": "31/12/2020"
        }
        res_exp = classify_regulatory_data(record_exp)
        self.assertEqual(res_exp["eu_status_current"], "expired")
        self.assertTrue(res_exp["eu_historical_flag"])
        self.assertEqual(res_exp["eu_regulatory_risk_flag"], "high")

    @patch("src.llm.ollama_client.OllamaClient")
    def test_classify_regulatory_data_llm_fallback(self, mock_client_class):
        mock_client = mock_client_class.return_value
        # Mock LLM response resolving status to "not_approved"
        mock_client.generate_chat.return_value = '{"status_current": "not_approved", "reason": "Banned legislation"}'

        record_ambig = {
            "substance_status": "Complex State",
            "remark": "This substance has been withdrawn due to health hazards",
            "legislations_actives": "Regulation 123/2024"
        }

        res = classify_regulatory_data(record_ambig, ollama_client=mock_client, enable_llm=True)
        self.assertEqual(res["eu_status_current"], "not_approved")
        self.assertEqual(res["eu_regulatory_risk_flag"], "high")

if __name__ == "__main__":
    unittest.main()
