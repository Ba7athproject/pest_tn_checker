# -*- coding: utf-8 -*-
"""
src/eu/eu_matcher.py
Moteur de recherche pour relier une substance tunisienne à la base européenne.
"""
import pandas as pd
from rapidfuzz import process, fuzz
import logging

logger = logging.getLogger("eu_matcher")

class EUMatcher:
    def __init__(self, eu_csv_path: str = "data/reference/eu_active_substances_full.csv"):
        self.eu_csv_path = eu_csv_path
        self.eu_db = self._load_database()
        # Création d'une liste de référence pour la recherche rapide
        self.eu_names = list(self.eu_db.keys()) if self.eu_db else []

    def _load_database(self) -> dict:
        """Charge la base UE et l'indexe par le nom de la substance en minuscules."""
        try:
            df = pd.read_csv(self.eu_csv_path)
            # Dictionnaire : nom_minuscule -> row_dict
            records = {}
            for _, row in df.iterrows():
                name = str(row.get('substance_name', '')).strip()
                if name:
                    records[name.lower()] = row.to_dict()
            logger.info(f"[Matcher UE] Base chargée : {len(records)} substances.")
            return records
        except Exception as e:
            logger.error(f"[Matcher UE] Erreur de chargement : {e}")
            return {}

    def match_substance(self, substance_name: str) -> dict:
        """
        Cherche la meilleure correspondance dans la base UE.
        Retourne le record complet si trouvé (>85% de similarité), sinon None.
        """
        if not substance_name or not self.eu_names:
            return {"match_found": False}

        search_term = substance_name.lower().strip()

        # 1. Test de Correspondance Exacte
        if search_term in self.eu_db:
            record = self.eu_db[search_term]
            return self._format_result(True, search_term, 100.0, record)

        # 2. Test de Correspondance Floue (Fautes d'orthographe ou traduction légère)
        # Ex: "azadirachtine" (FR) -> "azadirachtin" (EN)
        result = process.extractOne(search_term, self.eu_names, scorer=fuzz.WRatio)
        
        if result:
            best_match_name, score, _ = result
            if score >= 85.0: # Seuil de confiance : 85%
                record = self.eu_db[best_match_name]
                return self._format_result(True, best_match_name, score, record)

        # Aucun match satisfaisant trouvé
        return {"match_found": False}

    def _format_result(self, found: bool, matched_name: str, score: float, record: dict) -> dict:
        """Standardise la sortie du matcher."""
        return {
            "match_found": found,
            "matched_eu_name": record.get("substance_name"),
            "match_score_pct": round(score, 2),
            "eu_status": record.get("substance_status", "Unknown"),
            "eu_cas_number": str(record.get("as_cas_number", "")).strip(),
            "eu_category": record.get("substance_category", ""),
            "eu_source_url": record.get("pest_res_linked_legislation_url", "")
        }

# --- TEST ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    matcher = EUMatcher()
    
    test_cases = [
        "azadirachtine", # Typo FR/EN
        "2,4-D",         # Exact
        "Glyphosate",    # Exact
        "ProduitInconnuXYZ" # Faux
    ]
    
    import json
    for test in test_cases:
        print(f"\nRecherche pour : '{test}'")
        res = matcher.match_substance(test)
        print(json.dumps(res, indent=2, ensure_ascii=False))