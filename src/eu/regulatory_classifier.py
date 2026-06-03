# -*- coding: utf-8 -*-
"""
src/eu/regulatory_classifier.py
Deterministic and LLM-assisted classification of EU active substance regulatory metrics.
"""
import re
import json
import datetime
from typing import Dict, Any, Tuple, Optional

# Expected taxonomy constraints
ALLOWED_STATUSES = ["approved", "not_approved", "withdrawn", "expired", "banned", "not_renewed", "unknown"]
ALLOWED_RISK_FLAGS = ["low", "medium", "high"]

def parse_regulatory_date(value: Any) -> str:
    """
    Parses date strings safely from various potential formats (DD/MM/YYYY, YYYY-MM-DD)
    into ISO standard format YYYY-MM-DD.
    """
    if not value or (isinstance(value, float) and str(value) == "nan"):
        return ""
        
    s = str(value).strip()
    
    # Check if already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
        
    # Check DD/MM/YYYY
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        
    # Attempt standard datetime parsing
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            dt = datetime.datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
            
    return s

def classify_status_determ(status_str: str) -> str:
    """
    Checks status string against regex patterns to classify as approved, banned, withdrawn, etc.
    """
    s = str(status_str or "").strip().lower()
    if not s:
        return "unknown"
        
    if any(x in s for x in ["not approved", "non approuve", "not-approved"]):
        return "not_approved"
    if any(x in s for x in ["approved", "approuve", "autorise", "authorised", "active"]):
        return "approved"
    if any(x in s for x in ["withdrawn", "retire"]):
        return "withdrawn"
    if any(x in s for x in ["expired", "expire"]):
        return "expired"
    if any(x in s for x in ["banned", "interdit"]):
        return "banned"
    if any(x in s for x in ["not renewed", "non renouvele"]):
        return "not_renewed"
        
    return "unknown"

def query_llm_for_status(
    status_str: str,
    remark: str,
    legislations: str,
    ollama_client: Any,
    model: str = "qwen3:14b"
) -> str:
    """
    Queries local Ollama to resolve status when deterministic checks fall to 'unknown'.
    """
    if not ollama_client:
        return "unknown"
        
    prompt = f"""We are parsing pesticide active substance database statuses.
The substance status field has an ambiguous or unknown value: "{status_str}"

Here is additional context:
Remark: {remark}
Legislations: {legislations}

Please classify the current regulatory status into exactly one of these categories:
approved, not_approved, withdrawn, expired, banned, not_renewed, unknown.

Response MUST be a single raw JSON matching the schema below:
{{
  "status_current": "one of the categories above",
  "reason": "short explanation of your choice in French"
}}
"""
    try:
        raw_res = ollama_client.generate_chat(prompt)
        if raw_res:
            # Clean and parse JSON
            from src.llm.ollama_client import clean_json_response
            cleaned = clean_json_response(raw_res)
            data = json.loads(cleaned)
            status = str(data.get("status_current", "")).strip().lower()
            if status in ALLOWED_STATUSES:
                return status
    except Exception:
        pass
        
    return "unknown"

def classify_regulatory_data(
    record: Dict[str, Any],
    ollama_client: Optional[Any] = None,
    enable_llm: bool = False
) -> Dict[str, Any]:
    """
    Translates raw EU database fields into normalized regulatory states and risk flags.
    Preserves all raw input fields.
    """
    # 1. Date extraction
    app_start = parse_regulatory_date(record.get("approval_date") or record.get("approvalDate") or "")
    app_end = parse_regulatory_date(record.get("expiry_date") or record.get("expiryDate") or "")
    
    # 2. Boolean flags extraction
    subst_val = str(record.get("candidate_for_substitution") or record.get("candidateForSubstitution") or "").lower().strip()
    is_subst = subst_val in ("yes", "true", "1", "y")
    
    low_risk_val = str(record.get("low_risk_active_substance") or record.get("lowRiskActiveSubstance") or "").lower().strip()
    is_low_risk = low_risk_val in ("yes", "true", "1", "y")
    
    basic_val = str(record.get("basic_substance") or record.get("basicSubstance") or "").lower().strip()
    is_basic = basic_val in ("yes", "true", "1", "y")
    
    subst_reason = str(record.get("candidate_for_substitution_type") or record.get("candidateForSubstitutionType") or "").strip()

    # 3. Status extraction (deterministic first)
    raw_status = record.get("substance_status") or record.get("approvalStatus") or record.get("status") or ""
    status_current = classify_status_determ(raw_status)
    
    # 4. LLM arbitration fallback
    if status_current == "unknown" and enable_llm and ollama_client:
        remark = str(record.get("remark") or "").strip()
        legislations = str(record.get("legislations_actives") or record.get("legislations_old") or "").strip()
        status_current = query_llm_for_status(raw_status, remark, legislations, ollama_client)

    # 5. historical check
    is_historical = False
    if status_current in ("withdrawn", "expired", "banned", "not_renewed"):
        is_historical = True
    else:
        # Check if expired date is in the past
        if app_end:
            try:
                end_dt = datetime.datetime.strptime(app_end, "%Y-%m-%d").date()
                if end_dt < datetime.date.today():
                    is_historical = True
                    if status_current == "approved":
                        # If expired but status was approved, it is technically expired/historical
                        status_current = "expired"
            except ValueError:
                pass

    # 6. Risk Tiering calculation
    if is_subst or status_current in ("not_approved", "withdrawn", "expired", "banned", "not_renewed"):
        risk_flag = "high"
    elif is_low_risk and status_current == "approved":
        risk_flag = "low"
    else:
        risk_flag = "medium"

    # Preserving the raw source fields and constructing final clean output dictionary
    out_dict = {
        # Raw fields preserved
        "substance_status": record.get("substance_status") or "",
        "approval_date": record.get("approval_date") or "",
        "expiry_date": record.get("expiry_date") or "",
        "candidate_for_substitution": record.get("candidate_for_substitution") or "",
        "candidate_for_substitution_type": record.get("candidate_for_substitution_type") or "",
        "remark": record.get("remark") or "",
        "legislations_old": record.get("legislations_old") or "",
        "legislations_actives": record.get("legislations_actives") or "",
        "low_risk_active_substance": record.get("low_risk_active_substance") or "",
        "basic_substance": record.get("basic_substance") or "",
        
        # Normalized output fields
        "eu_status_current": status_current,
        "eu_historical_flag": is_historical,
        "eu_candidate_for_substitution": is_subst,
        "eu_substitution_reason": subst_reason,
        "eu_is_low_risk": is_low_risk,
        "eu_is_basic_substance": is_basic,
        "eu_approval_start": app_start,
        "eu_approval_end": app_end,
        "eu_regulatory_risk_flag": risk_flag
    }
    
    return out_dict
