# -*- coding: utf-8 -*-
"""
tests/test_reinject.py
Unit tests for reinjection logic and product-level approval state.
"""
import sys
import os
import unittest
import pandas as pd

import importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
reinject_module = importlib.import_module("scripts.reinject_decisions")
build_manual_index = reinject_module.build_manual_index
classify_resolution = reinject_module.classify_resolution

class TestReinject(unittest.TestCase):

    def test_classify_resolution(self):
        self.assertEqual(classify_resolution("accept", "Alpha-Cypermethrin"), ("Alpha-Cypermethrin", "Manual Accept"))
        self.assertEqual(classify_resolution("reject", ""), ("", "Rejected"))
        self.assertEqual(classify_resolution("needs_research", ""), ("", "Needs Research"))
        self.assertEqual(classify_resolution("exact", "Abamectin"), ("Abamectin", "Auto Mapped"))
        self.assertEqual(classify_resolution("review", ""), ("", "Pending Review"))

    def test_build_manual_index_single_slot(self):
        # Test old or simple single slot fallback
        data = {
            "substance_unit": ["alphamethrine", "oil de neem"],
            "substance_normalized": ["alphamethrine", "oil de neem"],
            "review_decision": ["accept", "reject"],
            "review_match_name": ["Alpha-Cypermethrin", ""],
            "review_notes": ["Note 1", "Note 2"]
        }
        df = pd.DataFrame(data)
        idx = build_manual_index(df)
        self.assertEqual(len(idx), 2)
        self.assertEqual(idx["alphamethrine"]["decision"], "accept")
        self.assertEqual(idx["alphamethrine"]["match_name"], "Alpha-Cypermethrin")
        self.assertEqual(idx["oil de neem"]["decision"], "reject")

    def test_build_manual_index_multi_slot(self):
        # Test multi-slot columns
        data = {
            "substance_unit_1": ["alphamethrine"],
            "substance_normalized_1": ["alphamethrine"],
            "review_decision_1": ["accept"],
            "review_match_name_1": ["Alpha-Cypermethrin"],
            "review_notes_1": ["Note 1"],
            
            "substance_unit_2": ["oil de neem"],
            "substance_normalized_2": ["oil de neem"],
            "review_decision_2": ["reject"],
            "review_match_name_2": [""],
            "review_notes_2": ["Note 2"]
        }
        df = pd.DataFrame(data)
        idx = build_manual_index(df)
        self.assertEqual(len(idx), 2)
        self.assertEqual(idx["alphamethrine"]["decision"], "accept")
        self.assertEqual(idx["alphamethrine"]["match_name"], "Alpha-Cypermethrin")
        self.assertEqual(idx["oil de neem"]["decision"], "reject")

if __name__ == "__main__":
    unittest.main()
