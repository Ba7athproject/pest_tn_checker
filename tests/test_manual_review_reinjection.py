# -*- coding: utf-8 -*-
"""
tests/test_manual_review_reinjection.py
Automated tests for manual review queue parsing, decision reinjection, and product-level approvals.
"""
import sys
import os
import pytest
import pandas as pd
import importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
reinject_module = importlib.import_module("scripts.reinject_decisions")
build_manual_index = reinject_module.build_manual_index
classify_resolution = reinject_module.classify_resolution

def test_classify_resolution():
    # Valid decisions
    assert classify_resolution("accept", "Alpha-Cypermethrin") == ("Alpha-Cypermethrin", "Manual Accept")
    assert classify_resolution("exact", "Abamectin") == ("Abamectin", "Auto Mapped")
    assert classify_resolution("auto_accept_high_confidence", "Deltamethrin") == ("Deltamethrin", "Auto Accepted")
    
    # Negative/unresolved decisions
    assert classify_resolution("reject", "") == ("", "Rejected")
    assert classify_resolution("needs_research", "") == ("", "Needs Research")
    assert classify_resolution("review", "") == ("", "Pending Review")
    assert classify_resolution("", "") == ("", "Pending Review")

def test_build_manual_index_multi_slot():
    # Setup manual review queue simulation
    data = {
        "row_id": [1, 2],
        "Produit Commercial": ["Product A", "Product B"],
        "substance_unit_1": ["alphamethrine", "chlorpyriphos"],
        "substance_normalized_1": ["alphamethrine", "chlorpyriphos"],
        "review_decision_1": ["accept", "reject"],
        "review_match_name_1": ["Alpha-Cypermethrin", ""],
        
        "substance_unit_2": ["huile de neem", ""],
        "substance_normalized_2": ["oil de neem", ""],
        "review_decision_2": ["accept", ""],
        "review_match_name_2": ["Paraffin oil", ""],
    }
    queue_df = pd.DataFrame(data)
    
    manual_index = build_manual_index(queue_df)
    
    # Assert correct collection of slot decisions
    assert "alphamethrine" in manual_index
    assert manual_index["alphamethrine"]["decision"] == "accept"
    assert manual_index["alphamethrine"]["match_name"] == "Alpha-Cypermethrin"
    
    assert "oil de neem" in manual_index
    assert manual_index["oil de neem"]["decision"] == "accept"
    assert manual_index["oil de neem"]["match_name"] == "Paraffin oil"
    
    assert "chlorpyphos" not in manual_index  # Normalized query standard is run

def test_product_level_approval_rules():
    # 1. Mock status mapping
    status_map = {
        "alpha-cypermethrin": "Approved",
        "paraffin oil": "Approved",
        "chlorpyrifos": "Not approved"
    }

    # Helper function replicating reinjection decision loop
    def evaluate_product(sub_units, manual_index):
        resolved_names = []
        resolved_statuses = []
        
        for sub in sub_units:
            norm = sub.lower().strip()  # Simple normalization
            manual = manual_index.get(norm)
            if manual:
                match_name, res_label = classify_resolution(manual["decision"], manual["match_name"])
                if res_label in ("Manual Accept", "Auto Mapped", "Auto Accepted") and match_name:
                    norm_match = match_name.lower().strip()
                    eu_status = status_map.get(norm_match, "Unknown")
                    resolved_names.append(match_name)
                    resolved_statuses.append(eu_status)
                else:
                    resolved_names.append("")
                    resolved_statuses.append("")
            else:
                resolved_names.append("")
                resolved_statuses.append("")

        is_approved = False if not sub_units else (
            len(resolved_statuses) == len(sub_units) and all(s == "Approved" for s in resolved_statuses)
        )
        return is_approved, resolved_statuses

    # CASE A: Multi-slot product review where all slots are approved
    manual_index_success = {
        "alphamethrine": {"decision": "accept", "match_name": "Alpha-Cypermethrin"},
        "oil de neem": {"decision": "accept", "match_name": "Paraffin oil"}
    }
    is_approved_a, statuses_a = evaluate_product(["alphamethrine", "oil de neem"], manual_index_success)
    assert is_approved_a is True
    assert statuses_a == ["Approved", "Approved"]

    # CASE B: Failing case where one slot is unresolved (decision is 'review' or missing)
    manual_index_unresolved = {
        "alphamethrine": {"decision": "accept", "match_name": "Alpha-Cypermethrin"},
        "oil de neem": {"decision": "review", "match_name": ""}
    }
    is_approved_b, statuses_b = evaluate_product(["alphamethrine", "oil de neem"], manual_index_unresolved)
    assert is_approved_b is False
    assert statuses_b == ["Approved", ""]

    # CASE C: Failing case where one slot is rejected
    manual_index_reject = {
        "alphamethrine": {"decision": "accept", "match_name": "Alpha-Cypermethrin"},
        "oil de neem": {"decision": "reject", "match_name": ""}
    }
    is_approved_c, statuses_c = evaluate_product(["alphamethrine", "oil de neem"], manual_index_reject)
    assert is_approved_c is False

    # CASE D: Failing case where one slot matches a substance that is 'Not approved' in EU
    manual_index_not_approved = {
        "alphamethrine": {"decision": "accept", "match_name": "Alpha-Cypermethrin"},
        "chlorpyriphos": {"decision": "accept", "match_name": "Chlorpyrifos"}
    }
    is_approved_d, statuses_d = evaluate_product(["alphamethrine", "chlorpyriphos"], manual_index_not_approved)
    assert is_approved_d is False
    assert statuses_d == ["Approved", "Not approved"]

def test_mapping_persistence_reinjection(tmp_path):
    # Create a temporary queue CSV file
    queue_data = {
        "row_id": [1, 2],
        "Produit Commercial": ["Product A", "Product B"],
        "substance_unit_1": ["alphamethrine", "chlorpyriphos"],
        "substance_normalized_1": ["alphamethrine", "chlorpyriphos"],
        "review_decision_1": ["accept", "review"],
        "review_match_name_1": ["Alpha-Cypermethrin", ""],
        
        "substance_unit_2": ["huile de neem", ""],
        "substance_normalized_2": ["oil de neem", ""],
        "review_decision_2": ["accept", ""],
        "review_match_name_2": ["Paraffin oil", ""],
    }
    queue_df = pd.DataFrame(queue_data)
    queue_file = tmp_path / "queue.csv"
    queue_df.to_csv(queue_file, index=False, encoding="utf-8-sig")
    
    # Create temporary mapping CSV
    mapping_data = [
        {"source_name": "oldsub", "eu_name": "Old EU Name"}
    ]
    mapping_df = pd.DataFrame(mapping_data)
    mapping_file = tmp_path / "mapping.csv"
    mapping_df.to_csv(mapping_file, index=False, encoding="utf-8-sig")
    
    # Create reference CSV
    ref_data = [
        {"substance_name": "Alpha-Cypermethrin", "substance_status": "Approved"},
        {"substance_name": "Paraffin oil", "substance_status": "Approved"},
    ]
    ref_df = pd.DataFrame(ref_data)
    ref_file = tmp_path / "reference.csv"
    ref_df.to_csv(ref_file, index=False, encoding="utf-8-sig")

    # Create input recomposed file
    in_data = {
        "Substance Active": ["Alphaméthrine + huile de neem", "Chlorpyrifos"],
        "resolution_details": ["alphamethrine:Unresolved | oil de neem:Unresolved", "chlorpyrifos:Unresolved"]
    }
    in_df = pd.DataFrame(in_data)
    in_file = tmp_path / "input.csv"
    in_df.to_csv(in_file, index=False, encoding="utf-8-sig")

    out_file = tmp_path / "output.csv"

    # Call main using mock arguments
    import sys
    from unittest.mock import patch
    
    test_args = [
        "reinject_decisions.py",
        "--input", str(in_file),
        "--queue", str(queue_file),
        "--reference", str(ref_file),
        "--mapping", str(mapping_file),
        "--output", str(out_file)
    ]
    
    with patch.object(sys, "argv", test_args):
        build_manual_index = reinject_module.build_manual_index
        reinject_module.main()
        
    # Read the updated mapping
    updated_mapping = pd.read_csv(mapping_file)
    mapping_dict = dict(zip(updated_mapping.source_name, updated_mapping.eu_name))
    
    # Check that new mapping entries were written
    assert "alphamethrine" in mapping_dict
    assert mapping_dict["alphamethrine"] == "Alpha-Cypermethrin"
    assert "oil de neem" in mapping_dict
    assert mapping_dict["oil de neem"] == "Paraffin oil"
    
    # Check that unchanged mappings were preserved
    assert "oldsub" in mapping_dict
    assert mapping_dict["oldsub"] == "Old EU Name"
    
    # Check that non-accepted slots (like chlorpyriphos, decision 'review') were NOT mapped
    assert "chlorpyriphos" not in mapping_dict

