# -*- coding: utf-8 -*-
"""
src/pipeline_orchestrator.py
Script d'assemblage final du pipeline Ba7ath V3.
"""
import pandas as pd
import logging
import os
import sys

# Adjust path to import src module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.gatekeeper import process_product_entry
from src.eu.eu_matcher import EUMatcher
from src.efsa.hazard_enricher import EfsaHazardEnricher

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def run_pipeline(input_path, output_path):
    # 1. Initialisation des moteurs
    matcher = EUMatcher()
    efsa = EfsaHazardEnricher()
    
    # 2. Chargement du registre tunisien
    df = pd.read_csv(input_path)
    final_data = []
    
    logging.info(f"Début du traitement de {len(df)} produits...")
    
    for idx, row in df.iterrows():
        # A. Gatekeeper : Nettoyage et tri
        entries = process_product_entry(row['Substance Active'])
        
        for entry in entries:
            # Création de la ligne enrichie
            enriched_row = row.to_dict()
            enriched_row.update(entry)
            
            # B. Match UE uniquement si non intercepté
            if not entry['intercepted']:
                match = matcher.match_substance(entry['clean_name'])
                if match['match_found']:
                    enriched_row.update(match)
                    
                    # C. Enrichissement EFSA si CAS trouvé
                    if match.get('eu_cas_number'):
                        tox = efsa.get_hazards_by_cas(match['eu_cas_number'])
                        enriched_row.update(tox)
            
            final_data.append(enriched_row)
    
    # 3. Sauvegarde
    result_df = pd.DataFrame(final_data)
    result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    logging.info(f"Pipeline terminé. Résultat sauvegardé dans : {output_path}")

if __name__ == "__main__":
    run_pipeline("data/input/pesticides_tn_checked2.csv", "data/output/pesticides_tn_enriche.csv")