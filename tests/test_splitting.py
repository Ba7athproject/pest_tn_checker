# -*- coding: utf-8 -*-
"""
tests/test_splitting.py
Automated tests for chemical formula splitting logic.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common.substance_splitting import split_substances_advanced, split_and_extract_substances

def test_split_substances_advanced():
    # Split on "+"
    assert split_substances_advanced("Abamectine + Cypermethrine") == ["Abamectine", "Cypermethrine"]
    
    # Split on ";"
    assert split_substances_advanced("Chlorpyrifos; Deltamethrine") == ["Chlorpyrifos", "Deltamethrine"]
    
    # Split on French "et" and English "and"
    assert split_substances_advanced("cuivre et soufre") == ["cuivre", "soufre"]
    assert split_substances_advanced("Lambda-cyhalothrin and Thiamethoxam") == ["Lambda-cyhalothrin", "Thiamethoxam"]
    
    # Strip Famille chimique metadata
    assert split_substances_advanced("Abamectine famille chimique Avermectine") == ["Abamectine"]

def test_split_and_extract_substances():
    # Complex mixtures with units, concentrations, spelling corrections, and deduplication
    res = split_and_extract_substances("Azadirachtine (0,03 %) + 90,5% huile de neem")
    assert res == ["azadirachtin", "oil de neem"]

    # OCR duplicate repeating phrases
    res_repeats = split_and_extract_substances("Bacillus thuringiensis Bacillus thuringiensis")
    assert res_repeats == ["bacillus thuringiensis"]

    # Filter out trivial/meaningless tokens
    res_trivial = split_and_extract_substances("Abamectine + 5% + / + Cypermethrine")
    assert res_trivial == ["abamectin", "cypermethrin"]

    # Empty inputs
    assert split_and_extract_substances("") == []
    assert split_and_extract_substances(None) == []
