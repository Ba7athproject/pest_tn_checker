# -*- coding: utf-8 -*-
"""
src/common/substance_splitting.py
Advanced formula splitting rules for active substance mixtures.
"""
import re
from typing import Any, List
from src.common.text_normalization import normalize_text, clean_substance_name_for_match, is_trivial_token

def split_substances_advanced(raw_value: Any) -> List[str]:
    """
    Splits active substances separated by '+', ';', 'et' / 'and', or similar delimiters.
    E.g. "Azadirachtine (0,03 %) + 90,5% huile de neem" -> ["Azadirachtine (0,03 %)", "90,5% huile de neem"]
    """
    s = str(raw_value or "").strip()
    if not s:
        return []

    # Strip Famille chimique metadata
    s = re.sub(r"\bfamille\s+chimique\b.*$", "", s, flags=re.IGNORECASE)

    s = s.replace("＋", "+")
    s = re.sub(r"\s*\+\s*", " § ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*;\s*", " § ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+et\s+", " § ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+and\s+", " § ", s, flags=re.IGNORECASE)

    parts = [p.strip() for p in s.split("§") if p.strip()]
    return parts

def split_and_extract_substances(raw_value: Any) -> List[str]:
    """
    Splits a complex formula, cleans each substance unitaire,
    removes trivial terms, and returns a list of unique normalized values.
    """
    parts = split_substances_advanced(raw_value)
    results = []

    for part in parts:
        extracted = clean_substance_name_for_match(part)
        if is_trivial_token(extracted):
            continue
        results.append(extracted)

    cleaned_results = []
    for s in results:
        tokens = s.split()
        if len(tokens) >= 2:
            half = len(tokens) // 2
            if tokens[:half] == tokens[half:]:
                s = " ".join(tokens[:half])
        cleaned_results.append(s)

    # Deduplicate keeping order
    deduped = []
    seen = set()
    for item in cleaned_results:
        norm = normalize_text(item)
        if norm not in seen:
            seen.add(norm)
            deduped.append(item)

    return deduped
