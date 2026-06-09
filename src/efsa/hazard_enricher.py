# -*- coding: utf-8 -*-
"""
src/efsa/hazard_enricher.py
Module d'enrichissement toxico lisant DIRECTEMENT le fichier Excel OpenFoodTox.
Gère les jointures complexes IUCLID (Tox -> SUB -> REF_SUB)
"""
import os
import pandas as pd
import logging
import re
from typing import Dict, Any

logger = logging.getLogger("efsa_enricher")

class EfsaHazardEnricher:
    
    def __init__(self, excel_path: str = "data/reference/OFT3.0 export repository.xlsx"):
        self.excel_path = excel_path
        self.efsa_db = self._build_relational_database()

    def _clean_cas(self, cas: Any) -> str:
        if pd.isna(cas) or not isinstance(cas, str):
            return ""
        return re.sub(r'[^0-9-]', '', str(cas))

    def _build_relational_database(self) -> Dict[str, dict]:
        if not os.path.exists(self.excel_path):
            logger.warning(f"[EFSA] Fichier Excel introuvable : {self.excel_path}")
            return {}

        try:
            logger.info("[EFSA] Lecture des onglets Excel en cours (Patientez une dizaine de secondes)...")
            
            # 1. L'Annuaire des CAS (REF_SUB)
            df_ref = pd.read_excel(self.excel_path, sheet_name='REF_SUB')
            df_ref['Clean_CAS'] = df_ref['Inventory.CASNumber'].apply(self._clean_cas)
            df_ref = df_ref[df_ref['Clean_CAS'] != ""]
            
            # 2. Le Pont Administratif (SUB) -> Fait le lien entre le dossier et le CAS
            df_sub = pd.read_excel(self.excel_path, sheet_name='SUB')
            # Dictionnaire : Document UUID (Dossier) -> ReferenceSubstance UUID (Le CAS)
            sub_to_ref_map = dict(zip(df_sub['Document UUID'], df_sub['ReferenceSubstance.ReferenceSubstance']))
            
            # 3. Les Données de Toxicité (FLEX_SUM.ToxRefValues)
            df_tox = pd.read_excel(self.excel_path, sheet_name='FLEX_SUM.ToxRefValues')
            
            # Indexation de la toxicité par l'UUID du CAS (REF_SUB)
            tox_dict = {}
            for _, row in df_tox.iterrows():
                # Le parent ici est le SUB_UUID
                sub_uuid = str(row.get('Parent UUID', '')).strip()
                
                # On traverse le pont pour trouver le REF_SUB_UUID
                ref_uuid = sub_to_ref_map.get(sub_uuid)
                
                if ref_uuid:
                    adi_val = row.get('HumanHealthHazardCharacteristics.AcceptableDailyIntake.Adi.lowerValue')
                    arfd_val = row.get('HumanHealthHazardCharacteristics.AcuteReferenceDose.Arfd.lowerValue')
                    
                    if ref_uuid not in tox_dict:
                        tox_dict[ref_uuid] = {"adi": None, "arfd": None}
                    
                    # On garde la valeur si elle existe
                    if pd.notna(adi_val):
                        tox_dict[ref_uuid]["adi"] = adi_val
                    if pd.notna(arfd_val):
                        tox_dict[ref_uuid]["arfd"] = arfd_val

            # 4. Construction de la base finale consolidée
            records = {}
            for _, row in df_ref.iterrows():
                cas = row['Clean_CAS']
                ref_uuid = str(row.get('Document UUID', '')).strip()
                
                tox_data = tox_dict.get(ref_uuid, {"adi": "Inconnu", "arfd": "Inconnu"})
                
                # Gestion des valeurs propres pour l'affichage
                adi = tox_data["adi"] if tox_data["adi"] is not None else "Inconnu"
                arfd = tox_data["arfd"] if tox_data["arfd"] is not None else "Inconnu"
                
                records[cas] = {
                    "efsa_found": True,
                    "substance_name_efsa": row.get('ReferenceSubstanceName', 'Inconnu'),
                    "adi_mg_kg_bw": adi,
                    "arfd_mg_kg_bw": arfd
                }
                
            logger.info(f"[EFSA] Succès ! Ponts relationnels établis pour {len(records)} substances.")
            return records

        except Exception as e:
            logger.error(f"[EFSA] Erreur fatale : {e}")
            return {}

    def get_hazards_by_cas(self, cas_number: str) -> Dict[str, Any]:
        clean_cas = self._clean_cas(cas_number)
        
        default_response = {
            "efsa_found": False,
            "substance_name_efsa": "Non trouvée",
            "adi_mg_kg_bw": "Inconnu",
            "arfd_mg_kg_bw": "Inconnu",
            "tox_severity_score": 0
        }
        
        if not clean_cas or clean_cas not in self.efsa_db:
            return default_response

        data = self.efsa_db[clean_cas].copy()
        
        score = 0
        try:
            if float(data["adi_mg_kg_bw"]) < 0.01: score += 5
            elif float(data["adi_mg_kg_bw"]) < 0.1: score += 3
        except: pass
            
        try:
            if float(data["arfd_mg_kg_bw"]) < 0.01: score += 5
            elif float(data["arfd_mg_kg_bw"]) < 0.1: score += 3
        except: pass

        data["tox_severity_score"] = min(10, score)
        return data

# =====================================================================
# BLOC DE TEST
# =====================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    print("\n--- DÉMARRAGE DU TEST DU MOTEUR EFSA ---")
    
    enricher = EfsaHazardEnricher(excel_path="data/reference/OFT3.0 export repository.xlsx")
    
    cas_test = "2921-88-2" # Chlorpyrifos
    print(f"\nRecherche des données toxicologiques pour le CAS : {cas_test}")
    
    resultat = enricher.get_hazards_by_cas(cas_test)
    
    import json
    print(json.dumps(resultat, indent=4, ensure_ascii=False))