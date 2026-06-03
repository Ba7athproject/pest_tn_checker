# -*- coding: utf-8 -*-
"""
tests/test_llm_disambiguator.py
Unit tests for the LLM active substance arbitration layer.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.llm.ollama_client import clean_json_response
from src.llm.llm_disambiguator import validate_and_clean_disambiguation_result, disambiguate_substance

class TestLLMDisambiguator(unittest.TestCase):

    def test_clean_json_response(self):
        # Markdown wrapper
        raw_markdown = "```json\n{\n  \"same_entity\": true\n}\n```"
        self.assertEqual(clean_json_response(raw_markdown), "{\n  \"same_entity\": true\n}")

        # Text explanation outside braces
        raw_text = "Here is the response:\n{\n  \"same_entity\": false\n}\nHope this helps!"
        self.assertEqual(clean_json_response(raw_text), "{\n  \"same_entity\": false\n}")

    def test_validate_and_clean_disambiguation_result_valid(self):
        candidates = [
            {"display_name": "Copper hydroxide", "status": "Approved"},
            {"display_name": "Copper oxychloride", "status": "Approved"}
        ]
        
        valid_response = {
            "same_entity": True,
            "selected_candidate": "Copper hydroxide",
            "relation_type": "chemical_synonym",
            "regulatory_state": "approved",
            "confidence": 0.95,
            "requires_human_review": False,
            "reason": "Test reason"
        }
        
        cleaned = validate_and_clean_disambiguation_result(valid_response, candidates)
        self.assertTrue(cleaned["same_entity"])
        self.assertEqual(cleaned["selected_candidate"], "Copper hydroxide")
        self.assertEqual(cleaned["relation_type"], "chemical_synonym")
        self.assertFalse(cleaned["requires_human_review"])

    def test_validate_and_clean_disambiguation_result_invented(self):
        candidates = [
            {"display_name": "Copper hydroxide", "status": "Approved"}
        ]
        
        # LLM invented "Copper sulfate" which is not in shortlist
        invented_response = {
            "same_entity": True,
            "selected_candidate": "Copper sulfate",
            "relation_type": "chemical_synonym",
            "regulatory_state": "approved",
            "confidence": 0.90,
            "requires_human_review": False,
            "reason": "Synonym match"
        }
        
        cleaned = validate_and_clean_disambiguation_result(invented_response, candidates)
        # Should override to safe values due to violation
        self.assertFalse(cleaned["same_entity"])
        self.assertIsNone(cleaned["selected_candidate"])
        self.assertTrue(cleaned["requires_human_review"])
        self.assertTrue("[Constraint Viol]" in cleaned["reason"])

    @patch("src.llm.ollama_client.OllamaClient")
    def test_disambiguate_substance_success(self, mock_client_class):
        mock_client = mock_client_class.return_value
        # Mock successful Ollama JSON string response
        mock_client.generate_chat.return_value = """{
            "same_entity": true,
            "selected_candidate": "Copper hydroxide",
            "relation_type": "chemical_synonym",
            "regulatory_state": "approved",
            "confidence": 0.95,
            "requires_human_review": false,
            "reason": "Synonym match"
        }"""
        
        candidates = [
            {"display_name": "Copper hydroxide", "status": "Approved"}
        ]
        
        res = disambiguate_substance("hydroxyde de cuivre", "copper hydroxide", candidates, mock_client)
        self.assertTrue(res["same_entity"])
        self.assertEqual(res["selected_candidate"], "Copper hydroxide")
        self.assertEqual(res["relation_type"], "chemical_synonym")

    @patch("src.llm.ollama_client.OllamaClient")
    def test_disambiguate_substance_invalid_json_fallback(self, mock_client_class):
        mock_client = mock_client_class.return_value
        # Mock unparseable response
        mock_client.generate_chat.return_value = "This is not JSON at all!"
        
        candidates = [
            {"display_name": "Copper hydroxide", "status": "Approved"}
        ]
        
        res = disambiguate_substance("hydroxyde de cuivre", "copper hydroxide", candidates, mock_client)
        self.assertFalse(res["same_entity"])
        self.assertIsNone(res["selected_candidate"])
        self.assertTrue(res["requires_human_review"])
        self.assertIn("Failed to parse LLM response", res["reason"])

    @patch("src.llm.ollama_client.OllamaClient")
    def test_disambiguate_substance_timeout_fallback(self, mock_client_class):
        mock_client = mock_client_class.return_value
        # Mock connection failure (Ollama client returns None)
        mock_client.generate_chat.return_value = None
        
        candidates = [
            {"display_name": "Copper hydroxide", "status": "Approved"}
        ]
        
        res = disambiguate_substance("hydroxyde de cuivre", "copper hydroxide", candidates, mock_client)
        self.assertFalse(res["same_entity"])
        self.assertIsNone(res["selected_candidate"])
        self.assertTrue(res["requires_human_review"])
        self.assertIn("Local LLM did not return a response", res["reason"])

if __name__ == "__main__":
    unittest.main()
