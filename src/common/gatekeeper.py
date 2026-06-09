# -*- coding: utf-8 -*-
"""
src/common/gatekeeper.py
Le filtre d'entrée du pipeline Ba7ath.
Sépare les mélanges, nettoie le texte et intercepte les produits de biocontrôle/adjuvants.
"""
import re
import math
import unicodedata
from typing import Any, List, Dict

# --- 1. FONCTIONS DE NORMALISATION DE BASE ---

def normalize_text(value: Any) -> str:
    """Nettoie le texte : minuscules, sans accents, espaces propres."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("’", "'").replace("`", "'").replace("´", "'")
    s = re.sub(r"\([^)]*\)", " ", s) # Enlève ce qu'il y a entre parenthèses
    s = re.sub(r"\s+", " ", s).strip()
    return s

def clean_substance_name(value: Any) -> str:
    """Enlève les unités de mesure et les mots parasites courants, SANS détruire la chimie."""
    s = normalize_text(value)
    
    # 1. Suppression des catégories fonctionnelles
    s = re.sub(r"\b(insecticide|fongicide|herbicide|acaricide|rodenticide|nematicide)\b", " ", s, flags=re.IGNORECASE)
    
    # 2. Suppression INTELLIGENTE des dosages (Chiffre + Unité uniquement)
    # Ex: détruit "42.5 ml" ou "90.5%" mais laisse "2,4-D" tranquille
    s = re.sub(r"\b\d+([.,]\d+)?\s*(%|sachet|piege|ec|sc|wp|sl|dg|gr|fs|ks|mg|ml|l|kg|g)\b", " ", s, flags=re.IGNORECASE)
    
    # 3. Nettoyage final
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"[^a-z0-9+\-, ]+", " ", s) # On autorise la virgule pour les molécules
    s = re.sub(r"\s+", " ", s).strip()
    
    # 4. Standardisation absolue pour le 2,4-D (très courant et problématique)
    if "2,4-d" in s or "2, 4-d" in s or "2 4-d" in s:
        s = "2,4-D"
        
    return s

    
# --- 2. FONCTIONS DE SÉPARATION DES MÉLANGES ---

def split_substances(raw_value: Any) -> List[str]:
    """Sépare les formules complexes (avec +, ;, et)."""
    s = str(raw_value or "").strip()
    if not s:
        return []

    s = re.sub(r"\bfamille\s+chimique\b.*$", "", s, flags=re.IGNORECASE)
    s = s.replace("＋", "+")
    s = re.sub(r"\s*\+\s*", " § ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*;\s*", " § ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+et\s+", " § ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+and\s+", " § ", s, flags=re.IGNORECASE)

    parts = [p.strip() for p in s.split("§") if p.strip()]
    return parts

# --- 3. LE GATEKEEPER : INTERCEPTION DES EXCEPTIONS ---

def apply_gatekeeper_rules(substance_brute: str) -> Dict[str, Any]:
    """
    Analyse une substance séparée et décide si elle doit aller vers la base UE,
    ou si elle est interceptée (Biocontrôle, Adjuvant).
    """
    nom_propre = clean_substance_name(substance_brute)
    nom_lower = nom_propre.lower()

    # Règle par défaut (à envoyer au moteur de recherche UE)
    resultat = {
        "raw_name": substance_brute,
        "clean_name": nom_propre,
        "intercepted": False,
        "category": "Substance Chimique (À vérifier)",
        "ba7ath_status": "En attente UE",
        "risk_flag": "Inconnu"
    }

    # 1. Pièges et Kaïromones (Ex: Acétate d'éthyle)
    if "keromone" in nom_lower or "kairomone" in nom_lower or "acetate d ethyle" in nom_lower:
        resultat.update({
            "intercepted": True,
            "clean_name": "Acétate d'éthyle (Kaïromone)",
            "category": "Biocontrôle - Piège olfactif",
            "ba7ath_status": "Hors champ UE (Substance de base)",
            "risk_flag": "🟢 Nul (Dispositif fermé)"
        })
        return resultat

    # 2. Phéromones locales (Ex: Pyrale des dattes)
    if "dodecatrienyl" in nom_lower or "pyrale" in nom_lower:
        resultat.update({
            "intercepted": True,
            "clean_name": "(Z,E)-7,9,11-Dodecatrienyl formate",
            "category": "Biocontrôle - Confusion sexuelle",
            "ba7ath_status": "Approuvé localement (Hors UE)",
            "risk_flag": "🟢 Zéro Résidu"
        })
        return resultat

    # 3. Super-mouillants siliconés
    if "trisiloxane" in nom_lower or "polyether" in nom_lower:
        resultat.update({
            "intercepted": True,
            "clean_name": "Tensioactif Organosiliconé",
            "category": "Adjuvant de cuve",
            "ba7ath_status": "Additif légal (Hors Annexe I)",
            "risk_flag": "🟡 Multiplicateur de toxicité"
        })
        return resultat

    # 4. Détergents (SLES)
    if "lauryl" in nom_lower or "sles" in nom_lower:
        resultat.update({
            "intercepted": True,
            "clean_name": "Sodium lauryl ether sulfate (SLES)",
            "category": "Adjuvant - Agent mouillant",
            "ba7ath_status": "Additif légal (Hors Annexe I)",
            "risk_flag": "🟡 Ecotoxique aquatique (Base ECHA)"
        })
        return resultat

    return resultat

def process_product_entry(raw_product_string: str) -> List[Dict[str, Any]]:
    """
    La fonction principale appelée par le pipeline.
    Prend le string brut du registre, le sépare, et applique le gatekeeper sur chaque partie.
    """
    parts = split_substances(raw_product_string)
    processed_parts = []
    
    for part in parts:
        if part:
            processed = apply_gatekeeper_rules(part)
            processed_parts.append(processed)
            
    return processed_parts

# --- TEST ---
if __name__ == "__main__":
    test_products = [
        "Keromone 42.5 ml acetate d'ethyle",
        "Azadirachtine (0,03 %) + 90,5% huile de neem",
        "Polyethermodifiedtrisiloxane + polyether",
        "2,4-D",
        "Sodium lauryl ether sulfate (SLES)"
    ]
    
    import json
    for prod in test_products:
        print(f"\n--- Produit Brut : {prod} ---")
        result = process_product_entry(prod)
        print(json.dumps(result, indent=2, ensure_ascii=False))