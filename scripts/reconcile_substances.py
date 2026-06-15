#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reconcile_substances.py

Ce script réalise la réconciliation d'entités (Entity Resolution) entre les substances actives
présentes dans un fichier CSV d'entrée (pesticides tunisiens) et la nomenclature officielle
de l'Union Européenne (base UE au format JSON).

La similarité entre les substances est calculée par similarité cosinus vectorielle
en utilisant le modèle d'embeddings multilingue 'paraphrase-multilingual-MiniLM-L12-v2'.

Fonctionnalités :
- Chargement sécurisé de la base de référence UE.
- Initialisation robuste du modèle sentence-transformers.
- Vectorisation unique et optimisée de la base de référence et des requêtes uniques.
- Recherche du Top 5 des correspondances pour chaque unité de substance.
- Export des résultats dans data/output/ sans écraser le fichier source.
"""

import os
import sys
import json
import math
import traceback
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer, util

# Configuration des chemins par défaut
DEFAULT_REF_PATH = "data/reference/eu_active_substances_full.json"
DEFAULT_INPUT_PATH = "data/input/pesticides_tn_checker - manual_review_queue.csv"
DEFAULT_OUTPUT_PATH = "data/output/pesticides_tn_checker - manual_review_queue.csv"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

def clean_text(text) -> str:
    """
    Nettoie le texte en le convertissant en minuscules et en supprimant les espaces superflus.
    Gère les valeurs manquantes (NaN, None).
    """
    if text is None or (isinstance(text, float) and math.isnan(text)) or pd.isna(text):
        return ""
    return str(text).strip().lower()

def load_eu_reference(filepath: str) -> list:
    """
    Charge la base de référence UE au format JSON.
    Gère les exceptions de lecture et d'encodage.
    """
    print(f"[*] Chargement de la base de référence UE depuis : {filepath}")
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        
        # Validation basique de la structure du fichier JSON
        if not isinstance(data, list):
            # Certains exports enveloppent les enregistrements sous une clé "value" ou "items"
            if isinstance(data, dict):
                for key in ["items", "results", "data", "value", "content", "records"]:
                    if key in data and isinstance(data[key], list):
                        data = data[key]
                        break
            if not isinstance(data, list):
                raise ValueError("La structure du JSON de référence doit être une liste d'objets.")
                
        print(f"[+] Base UE chargée : {len(data)} substances de référence.")
        return data
    except FileNotFoundError:
        print(f"[!] Erreur : Le fichier de référence UE '{filepath}' est introuvable.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[!] Erreur de décodage JSON dans '{filepath}' : {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[!] Erreur inattendue lors du chargement de la base UE : {e}")
        traceback.print_exc()
        sys.exit(1)

def initialize_model(model_name: str) -> SentenceTransformer:
    """
    Initialise le modèle SentenceTransformer.
    Gère les échecs de chargement du modèle.
    """
    print(f"[*] Initialisation du modèle d'embeddings : {model_name}")
    try:
        # Le chargement du modèle utilise le cache local s'il est déjà téléchargé
        model = SentenceTransformer(model_name)
        # Affichage du périphérique de calcul utilisé (CUDA/GPU ou CPU)
        device = "GPU" if torch.cuda.is_available() else "CPU"
        print(f"[+] Modèle '{model_name}' chargé avec succès sur le périphérique : {device}")
        return model
    except Exception as e:
        print(f"[!] Erreur fatale lors du chargement du modèle sentence-transformers : {e}")
        traceback.print_exc()
        sys.exit(1)

def process_reconciliation(df: pd.DataFrame, eu_data: list, model: SentenceTransformer) -> pd.DataFrame:
    """
    Réalise la réconciliation d'entités en vectorisant de manière unique
    les substances de référence UE et les substances à réconcilier du DataFrame.
    Met à jour les colonnes candidate_x_y, score_x_y, etc., existantes dans le DataFrame.
    """
    print("[*] Début du traitement de réconciliation vectorielle...")
    
    # 1. Extraction et nettoyage des substances UE uniques
    clean_to_raw = {}
    for record in eu_data:
        raw_name = record.get("substance_name")
        if not raw_name:
            continue
        clean_name = clean_text(raw_name)
        if not clean_name:
            continue
            
        # Résolution des doublons : on privilégie les substances actives approuvées si doublon
        if clean_name not in clean_to_raw:
            clean_to_raw[clean_name] = record
        else:
            existing_status = str(clean_to_raw[clean_name].get("substance_status", "")).lower()
            new_status = str(record.get("substance_status", "")).lower()
            if "not approved" in existing_status and "approved" in new_status:
                clean_to_raw[clean_name] = record
                
    unique_eu_names = list(clean_to_raw.keys())
    print(f"[+] Nombre de substances UE uniques à vectoriser : {len(unique_eu_names)}")
    
    # 2. Vectorisation unique de la base de référence UE
    print("[*] Vectorisation de la base UE en cours...")
    try:
        eu_embeddings = model.encode(unique_eu_names, convert_to_tensor=True, show_progress_bar=True)
        print("[+] Vectorisation de la base UE terminée.")
    except Exception as e:
        print(f"[!] Erreur lors de la vectorisation de la base UE : {e}")
        traceback.print_exc()
        sys.exit(1)
        
    # 3. Extraction et nettoyage des requêtes uniques à réconcilier dans le CSV
    # Recherche dynamique des colonnes de type 'substance_unit_x' (ex: substance_unit_1, substance_unit_2...)
    substance_cols = [col for col in df.columns if col.startswith("substance_unit_")]
    print(f"[+] Colonnes de substances identifiées dans le CSV : {substance_cols}")
    
    unique_queries = set()
    for col in substance_cols:
        for val in df[col]:
            cleaned_val = clean_text(val)
            if cleaned_val:
                unique_queries.add(cleaned_val)
                
    unique_queries = sorted(list(unique_queries))
    print(f"[+] Nombre de requêtes uniques identifiées dans le CSV : {len(unique_queries)}")
    
    if not unique_queries:
        print("[!] Aucune substance active à réconcilier n'a été trouvée dans le CSV.")
        return df
        
    # 4. Vectorisation unique des requêtes du CSV
    print("[*] Vectorisation des requêtes du CSV en cours...")
    try:
        query_embeddings = model.encode(unique_queries, convert_to_tensor=True, show_progress_bar=True)
        print("[+] Vectorisation des requêtes terminée.")
    except Exception as e:
        print(f"[!] Erreur lors de la vectorisation des requêtes du CSV : {e}")
        traceback.print_exc()
        sys.exit(1)
        
    # 5. Calcul de la similarité cosinus matricielle
    # similarity_matrix est un tenseur de dimension (nb_requêtes_CSV, nb_substances_UE)
    # contenant les scores de similarité cosinus (compris entre -1.0 et 1.0)
    print("[*] Calcul de la similarité cosinus matricielle...")
    try:
        similarity_matrix = util.cos_sim(query_embeddings, eu_embeddings)
    except Exception as e:
        print(f"[!] Erreur lors du calcul de la similarité cosinus : {e}")
        traceback.print_exc()
        sys.exit(1)
        
    # 6. Extraction du Top 5 des correspondances pour chaque requête unique
    # Nous associons chaque requête unique à sa liste de correspondances optimales
    query_matches = {}
    for i, query in enumerate(unique_queries):
        scores = similarity_matrix[i]
        # Extraction des indices et des scores des 5 meilleures correspondances
        top_k = torch.topk(scores, k=min(5, len(scores)))
        top_scores = top_k.values.cpu().tolist()
        top_indices = top_k.indices.cpu().tolist()
        
        matches = []
        for score, idx in zip(top_scores, top_indices):
            matched_clean_name = unique_eu_names[idx]
            raw_record = clean_to_raw[matched_clean_name]
            
            # Formatage du score de similarité en pourcentage (0.0% à 100.0%)
            percentage_score = round(max(0.0, float(score)) * 100.0, 1)
            
            matches.append({
                "name": raw_record.get("substance_name"),
                "status": raw_record.get("substance_status"),
                "id": raw_record.get("substance_id"),
                "score": percentage_score
            })
        query_matches[query] = matches
        
    # 7. Remplissage des colonnes existantes du DataFrame
    print("[*] Remplissage des colonnes de résultats dans le DataFrame...")
    total_rows = len(df)
    
    # Pour chaque ligne du fichier CSV
    for idx, row in df.iterrows():
        # Journalisation régulière de l'avancement
        if (idx + 1) % 100 == 0 or (idx + 1) == total_rows:
            print(f"[*] Traitement de la ligne {idx + 1}/{total_rows}...")
            
        for col in substance_cols:
            # Récupération du numéro de l'unité (ex: 'substance_unit_1' -> x = 1)
            try:
                x = col.split("_")[-1]
            except Exception:
                continue
                
            val = row[col]
            cleaned_val = clean_text(val)
            
            if not cleaned_val:
                # Si l'unité est vide, on s'assure que les colonnes candidates de cette unité sont vides également
                for y in range(1, 6):
                    for suffix in ["", "_status", "_url"]:
                        col_name = f"candidate_{x}_{y}{suffix}"
                        if col_name in df.columns:
                            df.at[idx, col_name] = None
                    col_score = f"score_{x}_{y}"
                    if col_score in df.columns:
                        df.at[idx, col_score] = None
                continue
                
            # Récupération du Top 5 pré-calculé
            matches = query_matches.get(cleaned_val, [])
            
            # Remplissage des colonnes pour les 5 candidats
            for y_idx, match in enumerate(matches, start=1):
                # Format des colonnes existantes
                col_cand = f"candidate_{x}_{y_idx}"
                col_score = f"score_{x}_{y_idx}"
                col_status = f"candidate_{x}_{y_idx}_status"
                col_url = f"candidate_{x}_{y_idx}_url"
                
                # Construction de l'URL officielle via substance_id
                substance_id = match.get("id")
                url = ""
                if substance_id is not None:
                    url = f"https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/active-substances/?event=as.details&as_id={substance_id}"
                
                # Affectation aux colonnes si elles existent
                if col_cand in df.columns:
                    df.at[idx, col_cand] = match["name"]
                if col_score in df.columns:
                    df.at[idx, col_score] = match["score"]
                if col_status in df.columns:
                    df.at[idx, col_status] = match["status"]
                if col_url in df.columns:
                    df.at[idx, col_url] = url
                    
    print("[+] Traitement de réconciliation terminé avec succès.")
    return df

def export_results(df: pd.DataFrame, output_path: str) -> None:
    """
    Exporte le DataFrame enrichi dans le dossier spécifié.
    Crée le dossier parent s'il n'existe pas.
    Utilise l'encodage utf-8-sig pour assurer la compatibilité d'affichage (notamment avec Excel).
    """
    print(f"[*] Exportation des résultats vers : {output_path}")
    try:
        # Création du dossier de sortie s'il n'existe pas
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"[+] Fichier exporté avec succès ({len(df)} lignes).")
    except Exception as e:
        print(f"[!] Erreur lors de l'exportation du fichier : {e}")
        traceback.print_exc()
        sys.exit(1)

def main():
    print("======================================================================")
    print("SCRIPT D'ENTITY RESOLUTION DES SUBSTANCES ACTIVES (COSINE SIMILARITY)")
    print("======================================================================")
    
    # 1. Chargement de la base de référence UE
    eu_data = load_eu_reference(DEFAULT_REF_PATH)
    
    # 2. Initialisation du modèle d'embeddings
    model = initialize_model(MODEL_NAME)
    
    # 3. Chargement du fichier CSV tunisien à traiter
    print(f"[*] Chargement du fichier à traiter : {DEFAULT_INPUT_PATH}")
    try:
        # Utilisation de utf-8-sig au cas où le fichier source contiendrait un BOM UTF-8
        df = pd.read_csv(DEFAULT_INPUT_PATH, encoding="utf-8-sig")
        print(f"[+] Fichier CSV chargé avec succès : {len(df)} lignes.")
    except FileNotFoundError:
        print(f"[!] Erreur : Le fichier CSV '{DEFAULT_INPUT_PATH}' est introuvable.")
        sys.exit(1)
    except Exception as e:
        print(f"[!] Erreur lors de la lecture du fichier CSV '{DEFAULT_INPUT_PATH}' : {e}")
        traceback.print_exc()
        sys.exit(1)
        
    # 4. Traitement de la réconciliation d'entités
    df_reconciled = process_reconciliation(df, eu_data, model)
    
    # 5. Export des résultats enrichis dans le dossier de sortie
    export_results(df_reconciled, DEFAULT_OUTPUT_PATH)
    print("[*] Fin de l'exécution du script.")

if __name__ == "__main__":
    main()
