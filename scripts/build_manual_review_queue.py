# -*- coding: utf-8 -*-
"""
scripts/build_manual_review_queue.py
Orchestrates active substance splitting, fuzzy/semantic matching, and local LLM disambiguation
to generate a product-level multi-slot manual review queue.
"""
import os
import sys
import argparse
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any

# Adjust path to import src module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common import config
from src.common.logging_utils import setup_logging
from src.common.io_utils import read_csv, write_csv, load_mapping, load_eu_database
from src.common.text_normalization import normalize_text, clean_substance_name_for_match
from src.common.substance_splitting import split_and_extract_substances
from utils.match_engine import find_substance_match, find_best_matches, classify_status_eu

# Try to import optional matching/LLM modules
try:
    from src.matching import embedding_matcher
    EMBEDDINGS_SUPPORTED = True
except ImportError:
    EMBEDDINGS_SUPPORTED = False

try:
    from src.llm.ollama_client import OllamaClient
    from src.llm.llm_disambiguator import disambiguate_substance
    LLM_SUPPORTED = True
except ImportError:
    LLM_SUPPORTED = False

logger = setup_logging("queue_builder")

def build_candidates_list(eu_db: List[dict]) -> List[Tuple[str, str, dict]]:
    candidates = []
    for rec in eu_db:
        name = rec.get("substance_name") or rec.get("name") or rec.get("activeSubstance")
        if not name:
            continue
        display_name = str(name).strip()
        norm_name = clean_substance_name_for_match(display_name)
        if not norm_name:
            continue
        candidates.append((norm_name, display_name, rec))
    return candidates

def main():
    parser = argparse.ArgumentParser(description="Build product-level multi-slot manual review queue.")
    parser.add_argument("--input", default=config.INPUT_CSV, help="Path to input products CSV")
    parser.add_argument("--reference", default=config.REFERENCE_CSV, help="Path to reference EU CSV")
    parser.add_argument("--mapping", default=config.MAPPING_CSV, help="Path to mapping history CSV")
    parser.add_argument("--queue", default=config.QUEUE_CSV, help="Path to output review queue CSV")
    parser.add_argument("--recomposed", default=config.RECOMPOSED_CSV, help="Path to output recomposed product CSV")
    parser.add_argument("--enable-embeddings", action="store_true", help="Enable local nomic-embed-text matching")
    parser.add_argument("--embeddings-index", default=os.path.join(config.REFERENCE_DIR, "eu_active_substances_embeddings.pkl"), help="Path to saved embeddings index")
    parser.add_argument("--enable-llm", action="store_true", default=config.ENABLE_LLM, help="Enable Ollama LLM disambiguation")
    parser.add_argument("--ollama-url", default=config.OLLAMA_URL, help="Ollama API base URL")
    parser.add_argument("--ollama-model", default=config.OLLAMA_MODEL, help="Ollama model to query for arbitration")
    args = parser.parse_args()

    logger.info(f"Starting manual review queue builder pipeline.")
    
    if not os.path.exists(args.input):
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)
        
    df = read_csv(args.input)
    logger.info(f"Loaded {len(df)} rows from raw products input.")

    # Determine substance active column
    substance_col = "Substance Active"
    if substance_col not in df.columns:
        for col in df.columns:
            if "substance" in col.lower():
                substance_col = col
                break
        if substance_col not in df.columns:
            logger.error(f"Could not locate substance column. Available: {list(df.columns)}")
            sys.exit(1)

    logger.info(f"Using active substance column: '{substance_col}'")

    eu_db = load_eu_database(args.reference)
    logger.info(f"Loaded {len(eu_db)} reference items from EU active substances database.")

    candidates = build_candidates_list(eu_db)
    candidate_map = {c[0]: (c[1], c[2]) for c in candidates}

    mapping = load_mapping(args.mapping)
    logger.info(f"Loaded {len(mapping)} manual mappings.")

    # Embedding index setup
    embed_index = None
    if args.enable_embeddings and EMBEDDINGS_SUPPORTED:
        embed_index = embedding_matcher.load_index(args.embeddings_index)
        # Check index consistency with source CSV
        curr_hash = embedding_matcher.get_file_md5(args.reference)
        if not embed_index or embed_index.get("source_csv_hash") != curr_hash:
            logger.info("Embeddings index not found or reference DB changed. Rebuilding index...")
            embed_index = embedding_matcher.build_index(
                candidates, args.embeddings_index, source_csv_path=args.reference,
                ollama_url=args.ollama_url, model="nomic-embed-text"
            )
        if embed_index:
            logger.info("Embeddings matching engine successfully loaded.")
        else:
            logger.warn("Embeddings index building failed. Falling back to fuzzy-only matching.")

    # Initialize LLM Client if enabled
    llm_client = None
    if args.enable_llm and LLM_SUPPORTED:
        llm_client = OllamaClient(
            base_url=args.ollama_url,
            primary_model=args.ollama_model,
            fallback_model="llama3"
        )
        logger.info(f"LLM Client initialized with primary model: '{args.ollama_model}'.")

    # Determine max splits in dataset
    max_splits = 0
    row_splits = []
    for idx, row in df.iterrows():
        raw_val = str(row.get(substance_col, "")).strip()
        extracted = split_and_extract_substances(raw_val)
        row_splits.append(extracted)
        if len(extracted) > max_splits:
            max_splits = len(extracted)

    logger.info(f"Maximum active substances found in a product mixture: {max_splits}")

    # Build queue rows and product annotations
    queue_rows = []
    eu_substances_col = []
    eu_statuses_col = []
    resolution_details_col = []
    substance_alerte_col = []

    split_substance_active_cols = [[] for _ in range(max_splits)]
    split_eu_substance_cols = [[] for _ in range(max_splits)]
    split_eu_status_cols = [[] for _ in range(max_splits)]

    for idx, row in df.iterrows():
        raw_val = str(row.get(substance_col, "")).strip()
        extracted = row_splits[idx]

        row_eu_substances = []
        row_eu_statuses = []
        row_resolution_details = []
        row_alerts = []
        needs_review_queue = False
        row_queue_details = []

        if not extracted:
            row_eu_substances.append("")
            row_eu_statuses.append("")
            row_resolution_details.append("NO_SUBSTANCE")
            overall_status = "NO_SUBSTANCE"
            for i in range(max_splits):
                split_substance_active_cols[i].append("")
                split_eu_substance_cols[i].append("")
                split_eu_status_cols[i].append("")
                row_queue_details.append(None)
        else:
            for i in range(max_splits):
                if i < len(extracted):
                    sub_unit = extracted[i]
                    norm_sub = normalize_text(sub_unit)

                    if not norm_sub:
                        split_substance_active_cols[i].append("")
                        split_eu_substance_cols[i].append("")
                        split_eu_status_cols[i].append("")
                        row_queue_details.append(None)
                        continue

                    # 1. Deterministic match (exact & history mapping)
                    eu_name, status, match_type, score = find_substance_match(
                        sub_unit, candidates, candidate_map, mapping, config.SCORE_THRESHOLD_ACCEPT
                    )

                    # Persistence hook
                    if match_type == "auto_accept_high_confidence" and norm_sub not in mapping:
                        mapping[norm_sub] = eu_name

                    if match_type in ("unresolved", "none"):
                        # Get fuzzy matches
                        fuzzy_matches = find_best_matches(sub_unit, candidates, config.TOP_K)
                        merged_candidates = []
                        top_score = fuzzy_matches[0][1] if fuzzy_matches else 0

                        # Get semantic matches if enabled
                        if embed_index and EMBEDDINGS_SUPPORTED:
                            sem_matches = embedding_matcher.query_index(
                                sub_unit, embed_index, config.TOP_K, args.ollama_url, "nomic-embed-text"
                            )
                            # Merge and compute combined scores
                            merged_candidates = embedding_matcher.merge_candidate_lists(fuzzy_matches, sem_matches, config.TOP_K)
                            top_score = merged_candidates[0][1] if merged_candidates else 0
                        else:
                            # Fallback score formatting
                            merged_candidates = [(cand, float(scr), rec) for cand, scr, rec in fuzzy_matches]

                        row_eu_substances.append("")
                        row_eu_statuses.append("")
                        row_resolution_details.append(f"{sub_unit}:Unresolved(score={top_score})")
                        row_alerts.append(f"{sub_unit} (Not Found)")
                        needs_review_queue = True

                        row_queue_details.append({
                            "sub_unit": sub_unit,
                            "norm_sub": norm_sub,
                            "match_type": "unresolved",
                            "eu_name": None,
                            "score": top_score,
                            "candidates_list": merged_candidates
                        })
                    else:
                        row_eu_substances.append(eu_name)
                        row_eu_statuses.append(status)
                        row_resolution_details.append(f"{sub_unit}:{eu_name}({status})")
                        if status != "Approved":
                            row_alerts.append(f"{eu_name} ({status})")

                        row_queue_details.append({
                            "sub_unit": sub_unit,
                            "norm_sub": norm_sub,
                            "match_type": match_type,
                            "eu_name": eu_name,
                            "score": score,
                            "candidates_list": []
                        })

                    split_substance_active_cols[i].append(sub_unit)
                    split_eu_substance_cols[i].append(eu_name if eu_name else "")
                    split_eu_status_cols[i].append(status if status else "")
                else:
                    split_substance_active_cols[i].append("")
                    split_eu_substance_cols[i].append("")
                    split_eu_status_cols[i].append("")
                    row_queue_details.append(None)

            # Determine product overall status
            non_empty_statuses = [x for x in row_eu_statuses if x]
            has_unresolved = any(d and d["match_type"] == "unresolved" for d in row_queue_details)
            
            if has_unresolved:
                overall_status = "NOT_FOUND_OR_NEEDS_MANUAL_REVIEW"
            elif any(s != "Approved" for s in non_empty_statuses):
                overall_status = "CONTAINS_NOT_APPROVED_SUBSTANCE_IN_EU"
            else:
                overall_status = "ALL_SUBSTANCES_APPROVED_IN_EU"

        eu_substances_col.append(" | ".join(row_eu_substances))
        eu_statuses_col.append(" | ".join(row_eu_statuses))
        resolution_details_col.append(" | ".join(row_resolution_details))
        substance_alerte_col.append(" | ".join(row_alerts))

        # 5. Populate Review Queue Row
        if needs_review_queue:
            out_row = {
                "row_id": idx,
                "Produit Commercial": row.get("Produit Commercial", ""),
                "Substance Active": raw_val,
                "eu_overall_status": overall_status,
                "eu_status_details": " | ".join(row_resolution_details),
            }

            # Initialize slots
            for i in range(max_splits):
                out_row[f"substance_unit_{i+1}"] = ""
                out_row[f"substance_normalized_{i+1}"] = ""
                for k in range(1, config.TOP_K + 1):
                    out_row[f"candidate_{i+1}_{k}"] = ""
                    out_row[f"score_{i+1}_{k}"] = ""
                    out_row[f"candidate_{i+1}_{k}_status"] = ""
                    out_row[f"candidate_{i+1}_{k}_url"] = ""
                out_row[f"review_decision_{i+1}"] = ""
                out_row[f"review_match_name_{i+1}"] = ""
                out_row[f"review_notes_{i+1}"] = ""

            # Populate slots
            for i in range(len(extracted)):
                details = row_queue_details[i]
                if not details:
                    continue

                sub_unit = details["sub_unit"]
                norm_sub = details["norm_sub"]
                match_type = details["match_type"]
                eu_name = details["eu_name"]

                out_row[f"substance_unit_{i+1}"] = sub_unit
                out_row[f"substance_normalized_{i+1}"] = norm_sub

                if match_type == "unresolved":
                    cand_list = details["candidates_list"]
                    for k, (cand_display, m_score, rec) in enumerate(cand_list, 1):
                        as_id = str(rec.get("substance_id") or rec.get("id") or "").strip()
                        c_status = str(rec.get("substance_status") or rec.get("approvalStatus") or "").strip()
                        url = config.URL_TEMPLATE_EU.format(as_id=as_id) if as_id else ""
                        out_row[f"candidate_{i+1}_{k}"] = cand_display
                        out_row[f"score_{i+1}_{k}"] = m_score
                        out_row[f"candidate_{i+1}_{k}_status"] = c_status
                        out_row[f"candidate_{i+1}_{k}_url"] = url

                    top_score = details["score"]
                    review_decision = "review"
                    review_notes = ""
                    suggested_match_name = ""

                    # Optional LLM Arbitration
                    if args.enable_llm and LLM_SUPPORTED and 40 <= top_score < config.SCORE_THRESHOLD_REVIEW:
                        logger.info(f"Requesting LLM arbitration for ambiguous case: '{sub_unit}'")
                        cand_dicts = [item[2] for item in cand_list]
                        # Populate display name in candidate dicts for LLM compat
                        for cd, cl_item in zip(cand_dicts, cand_list):
                            cd["display_name"] = cl_item[0]
                        
                        llm_res = disambiguate_substance(sub_unit, norm_sub, cand_dicts, llm_client)
                        if llm_res and llm_res.get("same_entity") and llm_res.get("selected_candidate"):
                            suggested_match_name = llm_res["selected_candidate"]
                            review_notes = f"[LLM Suggestion] {llm_res.get('reason', '')}"
                            if llm_res.get("requires_human_review"):
                                review_decision = "review"
                            else:
                                review_decision = "review_accept_high_score"

                    elif top_score >= config.SCORE_THRESHOLD_REVIEW:
                        review_decision = "review_accept_high_score"

                    out_row[f"review_decision_{i+1}"] = review_decision
                    out_row[f"review_match_name_{i+1}"] = suggested_match_name
                    out_row[f"review_notes_{i+1}"] = review_notes
                else:
                    out_row[f"review_decision_{i+1}"] = match_type
                    out_row[f"review_match_name_{i+1}"] = eu_name if eu_name else ""

            queue_rows.append(out_row)

    # Save outputs
    df["eu_overall_status"] = [
        "NOT_FOUND_OR_NEEDS_MANUAL_REVIEW" if "Unresolved" in r else
        "CONTAINS_NOT_APPROVED_SUBSTANCE_IN_EU" if any(s and s != "Approved" for s in st.split(" | ")) else
        "ALL_SUBSTANCES_APPROVED_IN_EU" if st else "NO_SUBSTANCE"
        for r, st in zip(resolution_details_col, eu_statuses_col)
    ]
    df["eu_status_details"] = resolution_details_col
    df["eu_substances"] = eu_substances_col
    df["eu_statuses"] = eu_statuses_col
    df["resolution_details"] = resolution_details_col
    df["Substance alerte"] = substance_alerte_col

    for i in range(max_splits):
        df[f"substance_active_{i+1}"] = split_substance_active_cols[i]
        df[f"eu_substance_{i+1}"] = split_eu_substance_cols[i]
        df[f"eu_status_{i+1}"] = split_eu_status_cols[i]

    write_csv(df, args.recomposed)
    logger.info(f"Recomposed products catalog successfully saved to: {args.recomposed}")

    if queue_rows:
        queue_df = pd.DataFrame(queue_rows)
        write_csv(queue_df, args.queue)
        logger.info(f"Manual review queue successfully saved to: {args.queue} ({len(queue_df)} products)")
    else:
        write_csv(pd.DataFrame(), args.queue)
        logger.info("All substances resolved. Saved empty review queue.")

    # Save mapping dict
    mapping_list = [{"source_name": k, "eu_name": v} for k, v in mapping.items()]
    if mapping_list:
        write_csv(pd.DataFrame(mapping_list), args.mapping)
        logger.info(f"Updated manual mappings saved to: {args.mapping}")

if __name__ == "__main__":
    main()
