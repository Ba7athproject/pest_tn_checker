# -*- coding: utf-8 -*-
"""
tests/test_match_engine.py
Unit tests for the matching engine.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.match_engine import (
    classify_status_eu,
    score_match,
    find_best_matches,
    find_substance_match,
)

class TestMatchEngine(unittest.TestCase):

    def test_classify_status_eu(self):
        self.assertEqual(classify_status_eu({"substance_status": "Approved"}), "Approved")
        self.assertEqual(classify_status_eu({"approvalStatus": "Not approved"}), "Not approved")
        self.assertEqual(classify_status_eu({"status": "withdrawn"}), "Not approved")
        self.assertEqual(classify_status_eu({"status": "Unknown Status"}), "Unknown")

    def test_score_match(self):
        # Match score between chlorpyriphos and Chlorpyrifos should be high
        self.assertGreaterEqual(score_match("chlorpyriphos", "Chlorpyrifos"), 80)
        # Random match should be low
        self.assertLess(score_match("chlorpyriphos", "Abamectin"), 40)

    def test_find_substance_match(self):
        candidates = [
            ("chlorpyrifos", "Chlorpyrifos", {"substance_status": "Not approved", "substance_id": "548"}),
            ("abamectin", "Abamectin", {"substance_status": "Approved", "substance_id": "123"}),
        ]
        candidate_map = {c[0]: (c[1], c[2]) for c in candidates}
        mapping = {"chorpyriphos": "Chlorpyrifos"}

        # Test historical mapping
        name, status, match_type, score = find_substance_match(
            "chorpyriphos", candidates, candidate_map, mapping
        )
        self.assertEqual(name, "Chlorpyrifos")
        self.assertEqual(status, "Not approved")
        self.assertEqual(match_type, "auto_mapped")

        # Test exact matching
        name, status, match_type, score = find_substance_match(
            "abamectin", candidates, candidate_map, mapping
        )
        self.assertEqual(name, "Abamectin")
        self.assertEqual(status, "Approved")
        self.assertEqual(match_type, "exact")

        # Test fuzzy matching below confidence
        name, status, match_type, score = find_substance_match(
            "abamectinn", candidates, candidate_map, mapping, score_threshold_accept=95
        )
        # abamectine vs Abamectin score is high (95+) due to spell similarity
        self.assertEqual(name, "Abamectin")
        self.assertEqual(status, "Approved")
        self.assertEqual(match_type, "auto_accept_high_confidence")

if __name__ == "__main__":
    unittest.main()
