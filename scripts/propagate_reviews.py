import pandas as pd
import os

# --- CONFIGURATION ---
INPUT_FILE = "data/input/pesticides_tn_checker - manual_review_queue.csv"
OUTPUT_FILE = "data/output/pesticides_tn_checker_propagated.csv"

def build_truth_dictionary(df):
    """
    Parcourt le DataFrame pour extraire toutes les décisions 'accept' validées manuellement.
    Retourne un dictionnaire : { 'Nom_Substance_Originale' : {'match_name': '...', 'notes': '...'} }
    """
    print("[*] Étape 1 : Construction du dictionnaire de vérité...")
    truth_dict = {}
    
    # On boucle sur les 4 colonnes d'unités de substances
    for i in range(1, 5):
        unit_col = f'substance_unit_{i}'
        decision_col = f'review_decision_{i}'
        match_col = f'review_match_name_{i}'
        notes_col = f'review_notes_{i}'
        
        # Sécurité : vérifier si les colonnes existent
        if unit_col not in df.columns:
            continue
            
        # On ne garde que les lignes où la décision est explicitement 'accept'
        accepted_rows = df[df[decision_col] == 'accept']
        
        for _, row in accepted_rows.iterrows():
            substance = row[unit_col]
            if pd.notna(substance) and str(substance).strip() != "":
                clean_substance = str(substance).strip()
                
                # Sauvegarde des paramètres validés par le journaliste
                truth_dict[clean_substance] = {
                    'match_name': row[match_col] if pd.notna(row[match_col]) else "",
                    'notes': row[notes_col] if pd.notna(row[notes_col]) else ""
                }
                
    print(f"[+] Dictionnaire construit : {len(truth_dict)} substances uniques validées.")
    return truth_dict

def propagate_decisions(df, truth_dict):
    """
    Applique le dictionnaire de vérité au reste du dataset.
    """
    print("[*] Étape 2 : Propagation des décisions sur l'ensemble du dataset...")
    df_updated = df.copy()
    count_updates = 0
    
    for index, row in df_updated.iterrows():
        for i in range(1, 5):
            unit_col = f'substance_unit_{i}'
            decision_col = f'review_decision_{i}'
            match_col = f'review_match_name_{i}'
            notes_col = f'review_notes_{i}'
            
            if unit_col not in df_updated.columns:
                continue
                
            substance = row[unit_col]
            current_decision = row[decision_col]
            
            if pd.notna(substance) and str(substance).strip() != "":
                clean_substance = str(substance).strip()
                
                # Si la substance est connue dans notre dictionnaire
                if clean_substance in truth_dict:
                    # Si elle n'a pas déjà été marquée 'accept' manuellement sur cette ligne spécifique
                    if current_decision != 'accept':
                        
                        # 1. Mise à jour de la décision
                        df_updated.at[index, decision_col] = 'accept'
                        
                        # 2. Mise à jour du nom validé UE
                        df_updated.at[index, match_col] = truth_dict[clean_substance]['match_name']
                        
                        # 3. Mise à jour des notes avec balise de traçabilité
                        original_notes = truth_dict[clean_substance]['notes']
                        # On évite d'ajouter la balise si elle y est déjà (cas de passages multiples)
                        if "[Auto-propagé]" not in original_notes:
                            new_notes = f"{original_notes} [Auto-propagé]".strip()
                        else:
                            new_notes = original_notes
                            
                        df_updated.at[index, notes_col] = new_notes
                        count_updates += 1
                        
    print(f"[+] Propagation terminée : {count_updates} cases mises à jour automatiquement.")
    return df_updated

def export_results(df, output_path):
    """
    Sauvegarde sécurisée du fichier résultant.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    try:
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"[+] Fichier exporté avec succès : {output_path}")
    except Exception as e:
        print(f"[-] Erreur critique lors de l'export : {e}")

def main():
    print("=== DÉMARRAGE DE LA PROPAGATION DES VALIDATIONS ===")
    
    # 1. Vérification du fichier source
    if not os.path.exists(INPUT_FILE):
        print(f"[-] Erreur : Fichier introuvable ({INPUT_FILE})")
        # Si le fichier n'est pas dans le dossier, on tente de le lire dans le répertoire courant
        fallback_file = "pesticides_tn_checker - manual_review_queue.csv"
        if os.path.exists(fallback_file):
            print(f"[*] Fichier trouvé dans le répertoire courant, utilisation de {fallback_file}")
            df = pd.read_csv(fallback_file)
        else:
            return
    else:
        df = pd.read_csv(INPUT_FILE)
        
    # 2. Exécution du workflow
    truth_dict = build_truth_dictionary(df)
    
    if len(truth_dict) > 0:
        df_propagated = propagate_decisions(df, truth_dict)
        # 3. Export
        export_results(df_propagated, OUTPUT_FILE)
    else:
        print("[!] Aucune ligne 'accept' trouvée dans le fichier. Rien à propager.")

if __name__ == "__main__":
    main()