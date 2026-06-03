# -*- coding: utf-8 -*-
"""
utils/llm_helper.py
Local Ollama integration helper to assist resolving ambiguous active substances.
"""
import json
from typing import Any, List, Optional, Tuple
import requests

def build_ollama_prompt(substance: str, candidates: List[Tuple[str, int, dict]]) -> str:
    """
    Constructs the prompt for the local LLM.
    """
    candidates_list = []
    for idx, (display, score, rec) in enumerate(candidates, 1):
        status = rec.get("substance_status") or rec.get("approvalStatus") or "Unknown"
        candidates_list.append(f"{idx}. Name: {display} (Fuzzy score: {score}%, EU status: {status})")

    candidates_str = "\n".join(candidates_list)

    prompt = f"""You are a pesticide active substance chemistry expert.
We are reconciling Tunisian active substance names with the EU active substances database.
Your task is to recommend the best match from the list of candidates below for the query substance.

Query Substance to map: "{substance}"

Candidate Matches in EU Database:
{candidates_str}

Please analyze the spelling, structure, salts, and synonyms. Determine which candidate is chemically identical or represents the correct parent substance (e.g. if the query is a synonym, trademark name, spelling mistake, or salt of the candidate).

Response MUST be a single raw JSON object matching the schema below. Do not include any explanation outside the JSON.
{{
  "suggested_match": "The exact name of the best candidate from the list, or null if none of them is chemically identical/correct",
  "reasoning": "A short sentence in French explaining your reasoning for this choice"
}}
"""
    return prompt

def query_ollama_match(
    substance: str,
    candidates: List[Tuple[str, int, dict]],
    ollama_url: str = "http://localhost:11434",
    model: str = "llama3"
) -> Optional[dict]:
    """
    Queries local Ollama using /api/generate with JSON format constraint.
    Catches connection errors and handles them gracefully.
    """
    if not candidates:
        return None

    prompt = build_ollama_prompt(substance, candidates)
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0
        }
    }

    url = f"{ollama_url.rstrip('/')}/api/generate"
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            result = response.json()
            response_text = result.get("response", "").strip()
            # Parse the response text as JSON
            data = json.loads(response_text)
            return {
                "suggested_match": data.get("suggested_match"),
                "reasoning": data.get("reasoning")
            }
    except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
        # Graceful failure
        print(f"[Ollama Helper] Warning: Local LLM call failed or returned invalid JSON ({e})")
    return None
