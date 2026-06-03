# -*- coding: utf-8 -*-
"""
utils/match_engine.py
Matching engine logic for deterministic and fuzzy lookups of active substances.
"""
from typing import Dict, List, Optional, Tuple
from rapidfuzz import fuzz, process
from utils.normalize import clean_substance_name_for_match, normalize_text, is_trivial_token
from src.eu.regulatory_classifier import classify_status_determ

def classify_status_eu(record: dict) -> str:
    """
    Classifies the raw EU status field into 'Approved', 'Not approved', or 'Unknown'.
    """
    status_value = (
        record.get("substance_status")
        or record.get("approvalStatus")
        or record.get("status")
        or ""
    )
    res = classify_status_determ(status_value)
    if res == "approved":
        return "Approved"
    elif res == "unknown":
        return "Unknown"
    else:
        # not_approved, withdrawn, expired, banned, not_renewed
        return "Not approved"

def score_match(query: str, candidate: str) -> int:
    """
    Calculates WRatio score between query and candidate.
    """
    a = clean_substance_name_for_match(query)
    b = clean_substance_name_for_match(candidate)
    if not a or not b:
        return 0
    return int(round(fuzz.WRatio(a, b)))

def find_best_matches(
    query: str,
    candidates: List[Tuple[str, str, dict]],
    top_k: int = 5,
) -> List[Tuple[str, int, dict]]:
    """
    Given a query, find the best fuzzy matches from a list of candidates:
    candidates is a list of tuples: (normalized_name, display_name, record_dict).
    """
    query_norm = clean_substance_name_for_match(query)
    if not query_norm:
        return []

    cand_norms = [cand[0] for cand in candidates]
    results = process.extract(query_norm, cand_norms, scorer=fuzz.WRatio, limit=top_k * 3)

    out = []
    seen = set()
    for cand_norm, score, idx in results:
        norm_name, cand_display, rec = candidates[idx]
        key = normalize_text(cand_display)
        if key in seen:
            continue
        seen.add(key)
        out.append((cand_display, int(round(score)), rec))
        if len(out) >= top_k:
            break

    return out

def find_substance_match(
    sub_unit: str,
    candidates: List[Tuple[str, str, dict]],
    candidate_map: Dict[str, Tuple[str, dict]],
    mapping: Dict[str, str],
    score_threshold_accept: int = 95
) -> Tuple[Optional[str], Optional[str], str, int]:
    """
    Attempts to match sub_unit against:
    1. Historical manual mappings
    2. Exact matches in candidate_map
    3. Fuzzy matches above score_threshold_accept
    
    Returns a tuple: (eu_name, status, match_type, score)
    """
    norm_name = clean_substance_name_for_match(sub_unit)
    if not norm_name:
        return None, None, "empty", 0

    # 1. Check historical mapping
    if norm_name in mapping:
        eu_name = mapping[norm_name]
        eu_name_norm = clean_substance_name_for_match(eu_name)
        if eu_name_norm in candidate_map:
            display_name, rec = candidate_map[eu_name_norm]
            status = classify_status_eu(rec)
            return display_name, status, "auto_mapped", 100
        else:
            return eu_name, "Unknown", "auto_mapped_not_in_db", 100

    # 2. Check exact match in EU DB
    if norm_name in candidate_map:
        display_name, rec = candidate_map[norm_name]
        status = classify_status_eu(rec)
        return display_name, status, "exact", 100

    # 3. Check fuzzy match in EU DB
    matches = find_best_matches(sub_unit, candidates, top_k=5)
    if matches:
        cand_display, score, rec = matches[0]
        if score >= score_threshold_accept:
            status = classify_status_eu(rec)
            return cand_display, status, "auto_accept_high_confidence", score
        else:
            return None, None, "unresolved", score

    return None, None, "none", 0
