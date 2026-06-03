# -*- coding: utf-8 -*-
"""
tests/test_normalization.py
Automated tests for text normalization and substance name cleaning.
"""
import sys
import os
import pytest
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common.text_normalization import normalize_text, clean_substance_name_for_match, is_trivial_token

def test_normalize_text():
    # Lowercase and accent/diacritic removal
    assert normalize_text("Alphaméthrine") == "alphamethrine"
    assert normalize_text("Piége de phéromone") == "piege de pheromone"
    assert normalize_text("À base de Cuivre") == "a base de cuivre"
    
    # Parentheses content stripping
    assert normalize_text("Azadirachtine (0,03 %)") == "azadirachtine"
    
    # NaN and None handling
    assert normalize_text(None) == ""
    assert normalize_text(float('nan')) == ""

def test_clean_substance_name_french_english_variants():
    # Translation and cleaning
    assert clean_substance_name_for_match("cuivre") == "copper"
    assert clean_substance_name_for_match("soufre") == "sulphur"
    assert clean_substance_name_for_match("acide") == "acid"
    assert clean_substance_name_for_match("huile de neem") == "oil de neem"
    
    # Spelling spelling correction
    assert clean_substance_name_for_match("Alphaméthrine") == "alphamethrine"
    assert clean_substance_name_for_match("deltamethrine") == "deltamethrin"
    assert clean_substance_name_for_match("abamectine") == "abamectin"

def test_clean_substance_name_copper_compounds():
    # Copper compounds collapsing (order-independent in the regex pattern)
    assert clean_substance_name_for_match("hydroxyde de cuivre") == "copper hydroxide"
    assert clean_substance_name_for_match("oxychlorure de cuivre") == "copper oxychloride"
    assert clean_substance_name_for_match("sulfate de cuivre") == "copper sulfate"
    assert clean_substance_name_for_match("oxyde de cuivre") == "copper oxide"

def test_clean_substance_name_bacillus_and_ocr_noise():
    # Bacillus strains and deduplication of OCR repetition
    assert clean_substance_name_for_match("Bacillus thuringiensis Bacillus thuringiensis") == "bacillus thuringiensis"
    assert clean_substance_name_for_match("Bacillus thuringiensis sp. kurstaki") == "bacillus thuringiensis subsp kurstaki"
    
    # Spore count, percentage, dose, and units stripping
    assert clean_substance_name_for_match("Bacillus thuringiensis (1x10^10 spores/g)") == "bacillus thuringiensis"
    assert clean_substance_name_for_match("Abamectine 1.8% EC") == "abamectin"
    assert clean_substance_name_for_match("Chlorpyrifos-ethyl 480 g/l") == "chlorpyrifos"
    assert clean_substance_name_for_match("Lambda-cyhalothrine 50 g/l") == "lambda-cyhalothrin"

def test_clean_substance_name_salts():
    assert clean_substance_name_for_match("sel de sodium") == "salt sodium"
    assert clean_substance_name_for_match("sel d'ammonium") == "salt ammonium"

def test_is_trivial_token():
    assert is_trivial_token("") is True
    assert is_trivial_token("g") is True
    assert is_trivial_token("%") is True
    assert is_trivial_token("12.5") is True
    assert is_trivial_token("chlorpyrifos") is False
