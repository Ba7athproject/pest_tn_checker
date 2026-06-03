# -*- coding: utf-8 -*-
"""
tests/test_normalize.py
Unit tests for substance name normalization and advanced splitting logic.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.normalize import (
    normalize_text,
    clean_substance_name_for_match,
    split_substances_advanced,
    split_and_extract_substances,
)

class TestNormalize(unittest.TestCase):

    def test_normalize_text(self):
        self.assertEqual(normalize_text("Alphaméthrine"), "alphamethrine")
        self.assertEqual(normalize_text("Azadirachtine (0,03 %)"), "azadirachtine")
        self.assertEqual(normalize_text(None), "")
        self.assertEqual(normalize_text(""), "")

    def test_clean_substance_name(self):
        self.assertEqual(clean_substance_name_for_match("Azadirachtine (0,03 %)"), "azadirachtin")
        self.assertEqual(clean_substance_name_for_match("90,5% huile de neem"), "oil de neem")
        self.assertEqual(clean_substance_name_for_match("hydroxyde de cuivre"), "copper hydroxide")
        self.assertEqual(clean_substance_name_for_match("chlorpyrifos ethyl"), "chlorpyrifos")

    def test_split_substances_advanced(self):
        formula = "Azadirachtine (0,03 %) + 90,5% huile de neem"
        splits = split_substances_advanced(formula)
        self.assertEqual(len(splits), 2)
        self.assertEqual(splits[0], "Azadirachtine (0,03 %)")
        self.assertEqual(splits[1], "90,5% huile de neem")

        formula_and = "Chorpyriphos and Gamma -cyhalothrin"
        splits_and = split_substances_advanced(formula_and)
        self.assertEqual(len(splits_and), 2)
        self.assertEqual(splits_and[0], "Chorpyriphos")
        self.assertEqual(splits_and[1], "Gamma -cyhalothrin")

    def test_split_and_extract_substances(self):
        formula = "Azadirachtine (0,03 %) + 90,5% huile de neem"
        extracted = split_and_extract_substances(formula)
        self.assertEqual(extracted, ["azadirachtin", "oil de neem"])

if __name__ == "__main__":
    unittest.main()
