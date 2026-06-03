# -*- coding: utf-8 -*-
"""
tests/test_llm_prompt_format.py
Automated tests for LLM prompt construction and candidate record formatting.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.llm.prompts import (
    format_candidates,
    build_disambiguation_prompt,
    SYSTEM_PROMPT,
    ALLOWED_RELATIONS,
    ALLOWED_REGULATORY_STATES,
)

def test_system_prompt_content():
    # System prompt should specify allowed values and parsing rules
    assert "exact_equivalent" in SYSTEM_PROMPT
    assert "spelling_variant" in SYSTEM_PROMPT
    assert "salt_or_derivative" in SYSTEM_PROMPT
    assert "chemical_synonym" in SYSTEM_PROMPT
    assert "unrelated" in SYSTEM_PROMPT
    assert "JSON" in SYSTEM_PROMPT

def test_format_candidates():
    candidates = [
        {
            "display_name": "Alpha-Cypermethrin",
            "status": "Approved",
            "cas_number": "67375-30-8",
            "formula": "C22H19Cl2NO3"
        },
        {
            "display_name": "Cypermethrin",
            "status": "Approved",
            "cas_number": "52315-07-8",
            "formula": "C22H19Cl2NO3"
        }
    ]
    
    formatted = format_candidates(candidates)
    
    # Assert candidate details are present in the output
    assert "Candidate #1:" in formatted
    assert "Name: Alpha-Cypermethrin" in formatted
    assert "EU Status: Approved" in formatted
    assert "CAS No: 67375-30-8" in formatted
    assert "Formula: C22H19Cl2NO3" in formatted
    
    assert "Candidate #2:" in formatted
    assert "Name: Cypermethrin" in formatted
    assert "CAS No: 52315-07-8" in formatted

def test_build_disambiguation_prompt():
    source = "Alphaméthrine"
    normalized_source = "alphamethrine"
    candidates = [
        {
            "display_name": "Alpha-Cypermethrin",
            "status": "Approved",
            "cas_number": "67375-30-8",
            "formula": "C22H19Cl2NO3"
        }
    ]
    
    prompt = build_disambiguation_prompt(source, normalized_source, candidates)
    
    # Assert query and candidates are written into the prompt
    assert 'Source substance to match: "Alphaméthrine"' in prompt
    assert 'Normalized source substance: "alphamethrine"' in prompt
    assert "Alpha-Cypermethrin" in prompt
    assert "same_entity" in prompt
    assert "selected_candidate" in prompt
    assert "relation_type" in prompt
    assert "regulatory_state" in prompt
