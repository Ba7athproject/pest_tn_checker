# -*- coding: utf-8 -*-
"""
scripts/reinject_decisions.py
CLI script to reinject manual review decisions and compile the final clean product-level dataset.
Integrates the EU regulatory classifier to output detailed risk flags, approvals, and metrics.
"""
import os
import sys
import re
import argparse
import pandas as pd
from typing import Dict, Tuple, List, Optional, Any

# Adjust path to import src module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common import config
from src.common.logging_utils import setup_logging
from src.common.io_utils import read_csv, write_csv, load_mapping
from src.common.substance_splitting import split_and_extract_substances
from src.common.text_normalization import clean_substance_name_for_match
from src.eu.regulatory_classifier import classify_regulatory_data

logger = setup_logging("reinject")

def load_eu_substance_records(reference_path: str) -> Dict[str, dict]:
    """
    Loads EU active substances database and builds a mapping: normalized_name -> raw_record_dict.
    """
    if not os.path.exists(reference_path):
        logger.warning(f"Reference database not found at {reference_path}. Manual matches will default to blank regulatory fields.")
        return {}
    
    try:
        df = pd.read_csv(reference_path)
        records_map = {}
        for _, row in df.iterrows():
            name = row.get("substance_name") or row.get("name") or row.get("activeSubstance")
            if name:
                norm = clean_substance_name_for_match(name)
                records_map[norm] = row.to_dict()
        return records_map
    except Exception as e:
        logger.warning(f"Failed to load EU reference records mapping ({e}).")
        return {}

def build_manual_index(queue_df: pd.DataFrame) -> Dict[str, dict]:
    """
    Scans the manual review queue across all substance slots and collects decisions.
    """
    idx = {}
    if queue_df.empty:
        return idx

    # Find split slots dynamically
    split_indices = []
    for col in queue_df.columns:
        m = re.match(r"^substance_normalized_(\d+)$", col)
        if m:
            split_indices.append(int(m.group(1)))

    if not split_indices:
        # Fallback to single slot structure if applicable
        for _, row in queue_df.iterrows():
            norm = clean_substance_name_for_match(row.get("substance_normalized", "") or row.get("substance_unit", ""))
            if norm:
                idx[norm] = {
                    "decision": str(row.get("review_decision", "")).strip(),
                    "match_name": str(row.get("review_match_name", "")).strip(),
                    "notes": str(row.get("review_notes", "")).strip(),
                }
        return idx

    # Read each slot for every product row
    for _, row in queue_df.iterrows():
        for i in split_indices:
            norm_col = f"substance_normalized_{i}"
            unit_col = f"substance_unit_{i}"
            dec_col = f"review_decision_{i}"
            match_col = f"review_match_name_{i}"
            notes_col = f"review_notes_{i}"

            val_norm = row.get(norm_col)
            val_unit = row.get(unit_col)

            norm = clean_substance_name_for_match(val_norm or val_unit)
            if not norm:
                continue

            decision = str(row.get(dec_col, "")).strip()
            match_name = str(row.get(match_col, "")).strip()
            notes = str(row.get(notes_col, "")).strip()

            is_new = norm not in idx
            is_unresolved_in_idx = not is_new and idx[norm]["decision"] in ("", "review", "review_accept_high_score")
            has_resolved_decision = decision not in ("", "review", "review_accept_high_score")

            if is_new or (is_unresolved_in_idx and has_resolved_decision) or (not is_new and not idx[norm]["decision"]):
                idx[norm] = {
                    "decision": decision,
                    "match_name": match_name,
                    "notes": notes,
                }
    return idx

def classify_resolution(decision: str, match_name: str) -> Tuple[str, str]:
    """
    Classifies a decision value into resolution status.
    """
    d = (decision or "").strip().lower()
    if d == "accept" and match_name:
        return match_name, "Manual Accept"
    if d == "reject":
        return "", "Rejected"
    if d == "needs_research":
        return "", "Needs Research"
    if d in ("auto_mapped", "exact") and match_name:
        return match_name, "Auto Mapped"
    if d == "auto_accept_high_confidence" and match_name:
        return match_name, "Auto Accepted"
    return "", "Pending Review"

def main():
    parser = argparse.ArgumentParser(description="Reinject manual decisions and produce the clean dataset.")
    parser.add_argument("--input", default=config.RECOMPOSED_CSV, help="Path to recomposed intermediate CSV")
    parser.add_argument("--queue", default=config.QUEUE_CSV, help="Path to manual review queue CSV")
    parser.add_argument("--reference", default=config.REFERENCE_CSV, help="Path to reference EU CSV")
    parser.add_argument("--mapping", default=config.MAPPING_CSV, help="Path to mapping history CSV")
    parser.add_argument("--output", default=config.OUTPUT_CSV, help="Path to output clean CSV")
    args = parser.parse_args()

    # Fallbacks if files are not in config locations
    if not os.path.exists(args.input):
        fallback = os.path.join(config.BASE_DIR, "pesticides_tn_eu_2_review.csv")
        if os.path.exists(fallback):
            args.input = fallback
        else:
            logger.error(f"Input recomposed CSV not found: {args.input}")
            sys.exit(1)

    if not os.path.exists(args.queue):
        fallback = os.path.join(config.BASE_DIR, "manual_review_queue.csv")
        if os.path.exists(fallback):
            args.queue = fallback
        else:
            logger.error(f"Manual review queue CSV not found: {args.queue}")
            sys.exit(1)

    logger.info(f"Loading recomposed dataset: {args.input}")
    df = read_csv(args.input)

    logger.info(f"Loading manual review queue: {args.queue}")
    queue_df = read_csv(args.queue)

    logger.info(f"Loading EU database status mapping from: {args.reference}")
    eu_records = load_eu_substance_records(args.reference)

    mapping = load_mapping(args.mapping)
    logger.info(f"Loaded {len(mapping)} manual mappings.")

    manual_index = build_manual_index(queue_df)
    logger.info(f"Parsed {len(manual_index)} substance decisions from review queue.")

    # Update mapping cache with manual review accepted choices
    updated_mappings_count = 0
    for norm, details in manual_index.items():
        dec = details.get("decision", "").strip().lower()
        match_name = details.get("match_name", "").strip()
        if dec == "accept" and match_name:
            if mapping.get(norm) != match_name:
                mapping[norm] = match_name
                updated_mappings_count += 1
                logger.info(f"[Mapping Cache] Added mapping: '{norm}' -> '{match_name}'")

    final_eu_substances = []
    final_eu_statuses = []
    final_resolution_details = []
    final_alerts = []
    
    # Aggregated regulatory status lists
    product_approval = []
    prod_risk_flags = []
    prod_is_subst = []
    prod_is_low_risk = []
    prod_is_basic = []

    substance_col = "Substance Active"
    if substance_col not in df.columns:
        for col in df.columns:
            if "substance" in col.lower():
                substance_col = col
                break

    for _, row in df.iterrows():
        raw_val = str(row.get(substance_col, "")).strip()
        original_details = str(row.get("resolution_details", "") or "")

        sub_units = split_and_extract_substances(raw_val)

        resolved_names = []
        resolved_statuses = []
        resolved_details = []
        alerts = []
        
        # Product flags trackers
        risk_tier = "low"
        has_substitution = False
        all_low_risk = True if sub_units else False
        all_basic = True if sub_units else False

        # Parse existing non-unresolved pairings from build queue run
        existing_pairs = {}
        if original_details:
            for chunk in original_details.split("|"):
                chunk = chunk.strip()
                if ":" in chunk:
                    left, right = chunk.split(":", 1)
                    existing_pairs[clean_substance_name_for_match(left)] = right.strip()

        for sub in sub_units:
            norm = clean_substance_name_for_match(sub)
            eu_name = ""
            eu_status = "Unknown"
            resolution_label = "Pending Review"

            # Check if this substance unit was already resolved auto-accept or exact
            if norm in existing_pairs and "Unresolved" not in existing_pairs[norm]:
                detail = existing_pairs[norm]
                m = re.match(r"(.+)\((Approved|Not approved|Unknown)\)$", detail)
                if m:
                    eu_name = m.group(1).strip()
                    eu_status = m.group(2).strip()
                    resolution_label = "Auto Mapped"

            # Query manual queue decisions if not already resolved
            if not eu_name:
                manual = manual_index.get(norm)
                if manual:
                    match_name, res_label = classify_resolution(manual["decision"], manual["match_name"])
                    if res_label in ("Manual Accept", "Auto Mapped", "Auto Accepted") and match_name:
                        eu_name = match_name
                        resolution_label = res_label
                    else:
                        resolution_label = res_label
                else:
                    resolution_label = "Pending Review"

            # 4. Evaluate detailed regulatory metrics
            if resolution_label in ("Manual Accept", "Auto Mapped", "Auto Accepted") and eu_name:
                norm_match = clean_substance_name_for_match(eu_name)
                raw_rec = eu_records.get(norm_match)
                
                if raw_rec:
                    # Classify raw EU metrics using regulatory classifier
                    metrics = classify_regulatory_data(raw_rec)
                    raw_status = metrics["eu_status_current"] or "unknown"
                    eu_status = raw_status.replace("_", " ").capitalize()
                        
                    # Aggregate metrics
                    sub_risk = metrics["eu_regulatory_risk_flag"]
                    if sub_risk == "high":
                        risk_tier = "high"
                    elif sub_risk == "medium" and risk_tier == "low":
                        risk_tier = "medium"
                        
                    if metrics["eu_candidate_for_substitution"]:
                        has_substitution = True
                    if not metrics["eu_is_low_risk"]:
                        all_low_risk = False
                    if not metrics["eu_is_basic_substance"]:
                        all_basic = False
                else:
                    # Match name is not in reference DB
                    eu_status = "Unknown"
                    risk_tier = "high"
                    all_low_risk = False
                    all_basic = False
                
                resolved_names.append(eu_name)
                resolved_statuses.append(eu_status)
                resolved_details.append(f"{sub}:{eu_name}({eu_status})")
                if eu_status != "Approved":
                    alerts.append(f"{eu_name} ({eu_status})")

            elif resolution_label == "Rejected":
                resolved_names.append("")
                resolved_statuses.append("")
                resolved_details.append(f"{sub}:Rejected")
                alerts.append(f"{sub} (Rejected)")
                risk_tier = "high"
                all_low_risk = False
                all_basic = False
            elif resolution_label == "Needs Research":
                resolved_names.append("")
                resolved_statuses.append("")
                resolved_details.append(f"{sub}:Needs Research")
                alerts.append(f"{sub} (Needs Research)")
                risk_tier = "high"
                all_low_risk = False
                all_basic = False
            else:
                resolved_names.append("")
                resolved_statuses.append("")
                resolved_details.append(f"{sub}:Pending Review")
                alerts.append(f"{sub} (Pending Review)")
                risk_tier = "high"
                all_low_risk = False
                all_basic = False

        # Compile final fields
        eu_subs_str = " | ".join([x for x in resolved_names if x])
        eu_stats_str = " | ".join([x for x in resolved_statuses if x])
        
        final_eu_substances.append(eu_subs_str)
        final_eu_statuses.append(eu_stats_str)
        final_resolution_details.append(" | ".join(resolved_details))
        final_alerts.append(" | ".join(alerts))

        # Product-level approval rule: Product is approved only if it has at least one active substance
        # and EVERY active substance has status 'Approved'
        if not sub_units:
            is_approved = False
        else:
            is_approved = len(resolved_statuses) == len(sub_units) and all(s == "Approved" for s in resolved_statuses)
        
        product_approval.append(is_approved)
        prod_risk_flags.append(risk_tier)
        prod_is_subst.append(has_substitution)
        prod_is_low_risk.append(all_low_risk)
        prod_is_basic.append(all_basic)

    # Save to dataframe
    df["eu_substances_final"] = final_eu_substances
    df["eu_statuses_final"] = final_eu_statuses
    df["resolution_details_final"] = final_resolution_details
    df["Substance alerte finale"] = final_alerts
    df["product_is_approved"] = product_approval
    df["eu_regulatory_risk_flag"] = prod_risk_flags
    df["eu_candidate_for_substitution"] = prod_is_subst
    df["eu_is_low_risk"] = prod_is_low_risk
    df["eu_is_basic_substance"] = prod_is_basic

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    write_csv(df, args.output)
    logger.info(f"Clean reconciled dataset written to: {args.output}")
    logger.info(f"Total products: {len(df)}")
    logger.info(f"Approved products: {sum(1 for x in product_approval if x)}")

    # Save updated mapping cache
    mapping_list = [{"source_name": k, "eu_name": v} for k, v in mapping.items()]
    if mapping_list:
        write_csv(pd.DataFrame(mapping_list), args.mapping)
        logger.info(f"Updated manual mappings saved to: {args.mapping} ({updated_mappings_count} new mappings added)")

if __name__ == "__main__":
    main()
