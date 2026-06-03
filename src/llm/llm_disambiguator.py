# -*- coding: utf-8 -*-
"""
src/llm/llm_disambiguator.py
Arbitration orchestrator enforcing constraints and validation rules on local LLM outputs.
"""
import json
from typing import List, Dict, Any, Tuple
from src.llm.prompts import build_disambiguation_prompt, ALLOWED_RELATIONS, ALLOWED_REGULATORY_STATES
from src.llm.ollama_client import OllamaClient, clean_json_response

def validate_and_clean_disambiguation_result(
    result_dict: Dict[str, Any],
    candidates: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Enforces rules on the LLM output:
    - Ensures same_entity is boolean.
    - Ensures relation_type is in ALLOWED_RELATIONS.
    - Ensures regulatory_state is in ALLOWED_REGULATORY_STATES.
    - Ensures selected_candidate matches one of the input candidates.
      If the LLM invented a candidate name, sets selected_candidate to None and flags for human review.
    """
    cleaned = {
        "same_entity": False,
        "selected_candidate": None,
        "relation_type": "unrelated",
        "regulatory_state": "unknown",
        "confidence": 0.0,
        "requires_human_review": False,
        "reason": "Default validation fallback"
    }

    if not isinstance(result_dict, dict):
        cleaned["requires_human_review"] = True
        return cleaned

    # Check same_entity
    same_entity = result_dict.get("same_entity")
    if isinstance(same_entity, str):
        same_entity = same_entity.lower().strip() == "true"
    cleaned["same_entity"] = bool(same_entity)

    # Check confidence
    try:
        conf = float(result_dict.get("confidence", 0.0))
        cleaned["confidence"] = min(1.0, max(0.0, conf))
    except (ValueError, TypeError):
        cleaned["confidence"] = 0.0

    # Parse and validate relation_type
    rel = str(result_dict.get("relation_type", "")).strip().lower()
    if rel in ALLOWED_RELATIONS:
        cleaned["relation_type"] = rel
    else:
        cleaned["relation_type"] = "unrelated"
        cleaned["requires_human_review"] = True

    # Parse and validate regulatory_state
    reg = str(result_dict.get("regulatory_state", "")).strip().lower()
    if reg in ALLOWED_REGULATORY_STATES:
        cleaned["regulatory_state"] = reg
    else:
        cleaned["regulatory_state"] = "unknown"
        cleaned["requires_human_review"] = True

    # Validate selected_candidate strictly
    candidate_names = []
    for cand in candidates:
        name = cand.get("display_name") or cand.get("substance_name") or cand.get("name")
        if name:
            candidate_names.append(str(name).strip())

    selected = result_dict.get("selected_candidate")
    if selected and isinstance(selected, str):
        selected_strip = selected.strip()
        # Find exact case-insensitive match in candidates list
        matched_name = None
        for cand_name in candidate_names:
            if cand_name.lower() == selected_strip.lower():
                matched_name = cand_name
                break
        
        if matched_name:
            cleaned["selected_candidate"] = matched_name
        else:
            # LLM invented a candidate name!
            cleaned["selected_candidate"] = None
            cleaned["same_entity"] = False
            cleaned["requires_human_review"] = True
            cleaned["reason"] = f"[Constraint Viol] LLM invented candidate '{selected_strip}' not in shortlist."
            return cleaned
    else:
        cleaned["selected_candidate"] = None
        cleaned["same_entity"] = False

    # Check human review flag from LLM
    llm_review = result_dict.get("requires_human_review")
    if isinstance(llm_review, str):
        llm_review = llm_review.lower().strip() == "true"
    if llm_review:
        cleaned["requires_human_review"] = True

    cleaned["reason"] = str(result_dict.get("reason", "")).strip()
    return cleaned

def disambiguate_substance(
    source: str,
    normalized_source: str,
    candidates: List[Dict[str, Any]],
    client: OllamaClient
) -> Dict[str, Any]:
    """
    Executes LLM disambiguation call using the provided OllamaClient.
    Returns a validated, clean result dictionary.
    """
    if not candidates:
        return {
            "same_entity": False,
            "selected_candidate": None,
            "relation_type": "unrelated",
            "regulatory_state": "unknown",
            "confidence": 0.0,
            "requires_human_review": True,
            "reason": "No candidates provided for matching."
        }

    prompt = build_disambiguation_prompt(source, normalized_source, candidates)
    raw_response = client.generate_chat(prompt)

    if not raw_response:
        return {
            "same_entity": False,
            "selected_candidate": None,
            "relation_type": "unrelated",
            "regulatory_state": "unknown",
            "confidence": 0.0,
            "requires_human_review": True,
            "reason": "Local LLM did not return a response."
        }

    # Clean and parse response
    cleaned_json = clean_json_response(raw_response)
    try:
        data = json.loads(cleaned_json)
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "same_entity": False,
            "selected_candidate": None,
            "relation_type": "unrelated",
            "regulatory_state": "unknown",
            "confidence": 0.0,
            "requires_human_review": True,
            "reason": f"Failed to parse LLM response as JSON. Raw: {raw_response[:200]}"
        }

    # Validate constraints
    return validate_and_clean_disambiguation_result(data, candidates)
