# -*- coding: utf-8 -*-
"""
src/common/config.py
Central configuration and directory path management.
"""
import os

# Base Directories
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(SRC_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")

INPUT_DIR = os.path.join(DATA_DIR, "input")
REFERENCE_DIR = os.path.join(DATA_DIR, "reference")
INTERIM_DIR = os.path.join(DATA_DIR, "interim")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")

# Ensure folders exist
for d in [INPUT_DIR, REFERENCE_DIR, INTERIM_DIR, OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)

# Default File Paths
INPUT_CSV = os.path.join(INPUT_DIR, "pesticides_tn_checked2.csv")
REFERENCE_CSV = os.path.join(REFERENCE_DIR, "eu_active_substances_full.csv")
MAPPING_CSV = os.path.join(INTERIM_DIR, "manual_mapping.csv")
QUEUE_CSV = os.path.join(INTERIM_DIR, "manual_review_queue.csv")
RECOMPOSED_CSV = os.path.join(INTERIM_DIR, "pesticides_tn_eu_2_review.csv")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "pesticides_tn_clean.csv")

# Matching Engine Constants
TOP_K = 5
SCORE_THRESHOLD_ACCEPT = 95
SCORE_THRESHOLD_REVIEW = 75

# LLM Constants (Ollama)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
ENABLE_LLM = False

# URL Template for active substance detail
URL_TEMPLATE_EU = (
    "https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/"
    "active-substances/?event=as.details&as_id={as_id}"
)
