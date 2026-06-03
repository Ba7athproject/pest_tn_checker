# -*- coding: utf-8 -*-
"""
src/common/io_utils.py
Centralized utilities for reading and writing CSV files within the pipeline.
"""
import os
from typing import Dict, List
import pandas as pd
from src.common.text_normalization import clean_substance_name_for_match

def read_csv(filepath: str, encoding: str = "utf-8-sig") -> pd.DataFrame:
    """
    Reads a CSV file into a pandas DataFrame using the specified encoding.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV file not found: {filepath}")
    return pd.read_csv(filepath, encoding=encoding)

def write_csv(df: pd.DataFrame, filepath: str, encoding: str = "utf-8-sig") -> None:
    """
    Writes a pandas DataFrame to a CSV file at the specified path, ensuring parent folders exist.
    """
    parent_dir = os.path.dirname(filepath)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    df.to_csv(filepath, index=False, encoding=encoding)

def load_mapping(mapping_path: str) -> Dict[str, str]:
    """
    Loads manual mappings history mapping from source_name to eu_name.
    """
    if not os.path.exists(mapping_path):
        return {}
    try:
        df = read_csv(mapping_path)
        mapping = {}
        for _, row in df.iterrows():
            src = clean_substance_name_for_match(row.get("source_name", ""))
            eu = str(row.get("eu_name", "")).strip()
            if src and eu:
                mapping[src] = eu
        return mapping
    except Exception as e:
        # Graceful fallback
        print(f"[WARN] Failed to load mapping history from {mapping_path} ({e}). Starting fresh.")
        return {}

def load_eu_database(db_path: str) -> List[dict]:
    """
    Loads EU Active substances database as list of dictionaries.
    """
    df = read_csv(db_path)
    return df.to_dict(orient="records")
