# -*- coding: utf-8 -*-
"""
tests/test_fuzzy_matching.py
Automated tests for exact, fuzzy, and historical mapping search algorithms.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.match_engine import (
    classify_status_eu,
    score_match,
    find_best_matches,
    find_substance_match,
)

# Reference data for test case
TEST_CANDIDATES = [
    ("chlorpyrifos", "Chlorpyrifos", {"substance_status": "Not approved", "substance_id": "548"}),
    ("abamectin", "Abamectin", {"substance_status": "Approved", "substance_id": "123"}),
    ("alpha-cypermethrin", "Alpha-Cypermethrin", {"substance_status": "Approved", "substance_id": "325"}),
]

TEST_CANDIDATE_MAP = {c[0]: (c[1], c[2]) for c in TEST_CANDIDATES}
TEST_MAPPING = {"chorpyriphos": "Chlorpyrifos"}

def test_classify_status_eu():
    assert classify_status_eu({"substance_status": "Approved"}) == "Approved"
    assert classify_status_eu({"approvalStatus": "Not renewed"}) == "Not approved"
    assert classify_status_eu({"status": "expired"}) == "Not approved"
    assert classify_status_eu({"status": "Unknown Status"}) == "Unknown"

def test_score_match():
    # Spell similarity scores
    assert score_match("abamectine", "Abamectin") >= 90
    assert score_match("alpha-cyperméthrine", "Alpha-Cypermethrin") >= 90
    assert score_match("abamectin", "Chlorpyrifos") < 40

def test_find_best_matches():
    res = find_best_matches("abamectine", TEST_CANDIDATES, top_k=2)
    assert len(res) >= 1
    assert res[0][0] == "Abamectin"
    assert res[0][1] >= 90

def test_find_substance_match_deterministic():
    # 1. Historical manual mapping lookup
    name, status, match_type, score = find_substance_match(
        "chorpyriphos", TEST_CANDIDATES, TEST_CANDIDATE_MAP, TEST_MAPPING
    )
    assert name == "Chlorpyrifos"
    assert status == "Not approved"
    assert match_type == "auto_mapped"

    # 2. Exact match lookup
    name, status, match_type, score = find_substance_match(
        "abamectin", TEST_CANDIDATES, TEST_CANDIDATE_MAP, TEST_MAPPING
    )
    assert name == "Abamectin"
    assert status == "Approved"
    assert match_type == "exact"

def test_find_substance_match_fuzzy_thresholds():
    # Fuzzy match above default score_threshold_accept (95)
    name, status, match_type, score = find_substance_match(
        "abamectin", TEST_CANDIDATES, TEST_CANDIDATE_MAP, TEST_MAPPING, score_threshold_accept=90
    )
    assert name == "Abamectin"
    assert match_type == "exact"  # exact match takes precedence

    # High similarity fuzzy match (e.g. spelling error)
    name, status, match_type, score = find_substance_match(
        "abamectinn", TEST_CANDIDATES, TEST_CANDIDATE_MAP, TEST_MAPPING, score_threshold_accept=90
    )
    assert name == "Abamectin"
    assert match_type == "auto_accept_high_confidence"

    # Low similarity unresolved case
    name, status, match_type, score = find_substance_match(
        "randomsubstance", TEST_CANDIDATES, TEST_CANDIDATE_MAP, TEST_MAPPING, score_threshold_accept=95
    )
    assert name is None
    assert match_type == "unresolved"
