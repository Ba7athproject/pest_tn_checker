# -*- coding: utf-8 -*-
"""
src/llm/prompts.py
System and user prompt templates for local LLM active substance arbitration.
"""
from typing import Any, List, Dict

# Allowed constraint categories
ALLOWED_RELATIONS = ["exact_equivalent", "spelling_variant", "salt_or_derivative", "chemical_synonym", "unrelated"]
ALLOWED_REGULATORY_STATES = ["approved", "not_approved", "withdrawn", "expired", "banned", "not_renewed", "unknown"]

SYSTEM_PROMPT = """You are a senior pesticide chemistry data engineer.
We are reconciling Tunisian active substance names with the EU active substances database.
Analyze the source substance name and compare it against the provided candidate list.

Rules:
1. Identify if the source substance matches any candidate.
2. Select a candidate ONLY if it is chemically identical, a direct spelling variant, a synonym, or a salt/derivative of that candidate.
3. If no candidate represents the source substance, set same_entity to false and selected_candidate to null.
4. relation_type must be strictly one of: exact_equivalent, spelling_variant, salt_or_derivative, chemical_synonym, unrelated.
5. regulatory_state must be strictly one of: approved, not_approved, withdrawn, expired, banned, not_renewed, unknown.
6. The response must be a single raw JSON object matching the requested schema. No markdown formatting or extra text outside JSON.
"""

def format_candidates(candidates: List[Dict[str, Any]]) -> str:
    """
    Formats the candidate database records into a clean string for the LLM.
    """
    formatted_parts = []
    for idx, cand in enumerate(candidates, 1):
        name = cand.get("display_name") or cand.get("substance_name") or cand.get("name") or "Unknown"
        status = cand.get("status") or cand.get("substance_status") or "Unknown"
        cas = cand.get("cas_number") or cand.get("casNumber") or "N/A"
        formula = cand.get("formula") or cand.get("chemicalFormula") or "N/A"
        
        part = (
            f"Candidate #{idx}:\n"
            f"  Name: {name}\n"
            f"  EU Status: {status}\n"
            f"  CAS No: {cas}\n"
            f"  Formula: {formula}\n"
        )
        formatted_parts.append(part)
    return "\n".join(formatted_parts)

def build_disambiguation_prompt(source: str, normalized_source: str, candidates: List[Dict[str, Any]]) -> str:
    """
    Constructs the prompt for substance disambiguation.
    """
    candidates_str = format_candidates(candidates)
    
    prompt = f"""Source substance to match: "{source}"
Normalized source substance: "{normalized_source}"

Candidates from EU Database:
{candidates_str}

Please decide if the source substance is a match to any candidate.
Provide your response strictly in the following JSON format:
{{
  "same_entity": true or false,
  "selected_candidate": "Write the exact name of the selected candidate from the list, or null if same_entity is false",
  "relation_type": "one of: exact_equivalent, spelling_variant, salt_or_derivative, chemical_synonym, unrelated",
  "regulatory_state": "one of: approved, not_approved, withdrawn, expired, banned, not_renewed, unknown",
  "confidence": 0.0 to 1.0,
  "requires_human_review": true or false,
  "reason": "Provide a concise explanation of your logic in French"
}}
"""
    return prompt
