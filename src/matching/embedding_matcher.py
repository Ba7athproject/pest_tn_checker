# -*- coding: utf-8 -*-
"""
src/matching/embedding_matcher.py
Semantic matching layer using local Ollama embeddings and Cosine Similarity,
with support for merging results with fuzzy matcher outputs.
"""
import os
import pickle
import hashlib
import requests
from typing import Dict, List, Tuple, Optional

# Default configuration settings
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_EMBED_MODEL = "nomic-embed-text"

def get_file_md5(filepath: str) -> str:
    """
    Computes MD5 hash of a file for change-detection and validation.
    """
    if not os.path.exists(filepath):
        return ""
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """
    Calculates cosine similarity between two vectors in pure Python.
    """
    dot_product = sum(x * y for x, y in zip(v1, v2))
    norm_v1 = sum(x * x for x in v1) ** 0.5
    norm_v2 = sum(x * x for x in v2) ** 0.5
    if not norm_v1 or not norm_v2:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)

def fetch_embedding_ollama(text: str, ollama_url: str, model: str, is_query: bool = False) -> Optional[List[float]]:
    """
    Fetches the embedding vector from local Ollama.
    Applies the nomic-embed-text prefix guidelines:
    - search_document: for index database building.
    - search_query: for user queries.
    """
    prefix = "search_query: " if is_query else "search_document: "
    prompt = f"{prefix}{text}"
    
    url = f"{ollama_url.rstrip('/')}/api/embeddings"
    payload = {
        "model": model,
        "prompt": prompt
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return response.json().get("embedding")
    except requests.RequestException:
        pass
    return None

def build_index(
    candidates: List[Tuple[str, str, dict]],
    output_path: str,
    source_csv_path: Optional[str] = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_EMBED_MODEL
) -> Optional[dict]:
    """
    Computes embeddings for all candidates and saves them to a pickle file.
    Returns the built index dictionary.
    """
    print(f"[Embedding Matcher] Starting index generation for {len(candidates)} candidates using model '{model}'...")
    
    # Check if Ollama is accessible
    test_vec = fetch_embedding_ollama("test", ollama_url, model, is_query=True)
    if not test_vec:
        print(f"[ERROR] Local Ollama is not running at {ollama_url} or model '{model}' is not pulled.")
        print("[INFO] Run: 'ollama pull nomic-embed-text' to download the model locally.")
        return None

    embeddings_list = []
    source_hash = get_file_md5(source_csv_path) if source_csv_path else ""

    for idx, (norm_name, display_name, rec) in enumerate(candidates, 1):
        if idx % 100 == 0 or idx == 1:
            print(f"[Embedding Matcher] Computing embeddings: {idx}/{len(candidates)}...")
            
        vector = fetch_embedding_ollama(display_name, ollama_url, model, is_query=False)
        if vector:
            embeddings_list.append({
                "normalized_name": norm_name,
                "display_name": display_name,
                "record": rec,
                "embedding": vector
            })
        else:
            # Add placeholders or log failure
            pass

    index = {
        "embeddings": embeddings_list,
        "model": model,
        "source_csv_hash": source_hash
    }

    # Save to disk
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(index, f)
        
    print(f"[Embedding Matcher] Index successfully written to {output_path} ({len(embeddings_list)} vectors).")
    return index

def load_index(index_path: str) -> Optional[dict]:
    """
    Loads a pickled embedding index from disk.
    """
    if not os.path.exists(index_path):
        return None
    try:
        with open(index_path, "rb") as f:
            index = pickle.load(f)
            if isinstance(index, dict) and "embeddings" in index:
                return index
    except Exception as e:
        print(f"[WARN] Failed to load embedding index: {e}")
    return None

def query_index(
    query: str,
    index: dict,
    top_k: int = 5,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_EMBED_MODEL
) -> List[Tuple[str, float, dict]]:
    """
    Retrieves the top-k nearest candidates for the query using cosine similarity.
    Returns a list of tuples: (display_name, similarity_score [0..1.0], record_dict)
    """
    if not index or not index.get("embeddings"):
        return []

    q_vector = fetch_embedding_ollama(query, ollama_url, model, is_query=True)
    if not q_vector:
        return []

    scored_candidates = []
    for item in index["embeddings"]:
        c_vector = item["embedding"]
        score = cosine_similarity(q_vector, c_vector)
        scored_candidates.append((item["display_name"], score, item["record"]))

    # Sort descending by score
    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    return scored_candidates[:top_k]

def merge_candidate_lists(
    fuzzy_candidates: List[Tuple[str, int, dict]],
    semantic_candidates: List[Tuple[str, float, dict]],
    top_k: int = 5
) -> List[Tuple[str, float, dict]]:
    """
    Combines the results from RapidFuzz fuzzy matches (scores 0-100) and
    Semantic matches (cosine similarity 0-1.0).
    Produces a single deduplicated list ranked by a combined score.
    
    Returns a list of tuples: (display_name, combined_score [0..100], record_dict)
    """
    merged: Dict[str, dict] = {}

    # 1. Process fuzzy candidates
    for display_name, score, rec in fuzzy_candidates:
        merged[display_name] = {
            "fuzzy_score": float(score),
            "semantic_score": 0.0,
            "record": rec
        }

    # 2. Process semantic candidates
    for display_name, score, rec in semantic_candidates:
        score_100 = float(score) * 100.0
        if display_name in merged:
            merged[display_name]["semantic_score"] = score_100
        else:
            merged[display_name] = {
                "fuzzy_score": 0.0,
                "semantic_score": score_100,
                "record": rec
            }

    # 3. Compute combined scores and format shortlist
    shortlist = []
    for display_name, data in merged.items():
        f_score = data["fuzzy_score"]
        s_score = data["semantic_score"]
        
        if f_score > 0.0 and s_score > 0.0:
            # Match is supported by both spelling and semantic semantics
            # We calculate a weighted max score plus an intersection boost
            combined = max(f_score, s_score) * 0.7 + min(f_score, s_score) * 0.3 + 5.0
            combined = min(100.0, combined)
        elif f_score > 0.0:
            # Fuzzy spelling-only match
            combined = f_score
        else:
            # Semantic-only match (without exact spelling overlap).
            # Slightly discounted to reduce false positives from synonyms/salts.
            combined = s_score * 0.90
            
        shortlist.append((display_name, round(combined, 1), data["record"]))

    # Sort descending by combined score
    shortlist.sort(key=lambda x: x[1], reverse=True)
    return shortlist[:top_k]
