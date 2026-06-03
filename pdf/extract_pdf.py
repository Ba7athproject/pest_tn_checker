import pdfplumber
import pandas as pd
import re
import os

# 1. Mapping pour normaliser les variations de noms de colonnes dans les PDF
COLUMN_MAPPING = {
    'SUBSTANCE ACTIVE': 'Substance Active',
    'MATIERE ACTIVE': 'Substance Active',
    'SUBTANCE ACTIVE': 'Substance Active', # Faute de frappe fréquente dans les docs du Ministère
    'CONC.': 'Concentration',
    'CONC': 'Concentration',
    'T.F.': 'Formulation',
    'T.F': 'Formulation',
    'P.COMM': 'Produit Commercial',
    'P.COMMERCIAL': 'Produit Commercial',
    'N°.H.': 'Numéro Homologation',
    'N.H.': 'Numéro Homologation',
    'N°.H': 'Numéro Homologation',
    'SOCIETE': 'Société',
    'FABRICANT': 'Fabricant'
}

# 2. Structure exacte demandée + Année pour le suivi historique
TARGET_COLUMNS = [
    "Catégorie", "Substance Active", "Concentration", "Formulation", 
    "Produit Commercial", "Numéro Homologation", "Société", "Fabricant", "Année"
]

def detect_category(text, current_category):
    """
    Détecte la catégorie de pesticides en lisant les titres de section dans le texte de la page.
    Cela permet de peupler la colonne 'Catégorie' qui n'existe pas dans les tableaux.
    """
    if not text:
        return current_category
    
    text_upper = text.upper()
    categories = ["INSECTICIDES", "FONGICIDES", "HERBICIDES", "NÉMATICIDES", "NEMATICIDES", "RATICIDES"]
    
    found_cat = current_category
    for cat in categories:
        # Recherche du mot clé isolé
        if re.search(r'\b' + cat + r'\b', text_upper):
            # Normalisation au singulier
            found_cat = cat.replace('S', '') if cat.endswith('S') else cat
            if found_cat == "NEMATICIDE": found_cat = "NÉMATICIDE"
            
    return found_cat

def merge_split_columns(table):
    """
    Fusionne les colonnes adjacentes qui ont été séparées à tort par pdfplumber (souvent dues à des décalages de grilles).
    L'algorithme fusionne la colonne i avec i+1 si elles sont complémentaires (l'une est vide quand l'autre a du texte).
    """
    if not table or len(table) == 0:
        return table
    num_cols = len(table[0])
    cleaned_table = []
    for row in table:
        cleaned_row = []
        for cell in row:
            if cell is None:
                val = ""
            else:
                val = str(cell).strip().replace('\n', ' ')
                if val.lower() == "nan":
                    val = ""
            cleaned_row.append(val)
        cleaned_table.append(cleaned_row)
        
    cols_to_drop = set()
    i = 0
    while i < num_cols - 1:
        complementary = True
        for row in cleaned_table:
            val_i = row[i]
            val_next = row[i+1]
            if val_i != "" and val_next != "" and val_i != val_next:
                complementary = False
                break
        if complementary:
            for row in cleaned_table:
                if row[i+1] == "":
                    row[i+1] = row[i]
            cols_to_drop.add(i)
            i += 1
        else:
            i += 1
            
    new_table = []
    for row in cleaned_table:
        new_row = [row[j] for j in range(num_cols) if j not in cols_to_drop]
        new_table.append(new_row)
    return new_table

def extract_pesticides_from_pdf(pdf_path, year):
    """
    Parcourt un PDF page par page, suit la catégorie active, nettoie les tableaux,
    gère les lignes continuations sans en-tête et aligne les colonnes de manière robuste.
    """
    all_dfs = []
    current_category = "Non Spécifiée"
    active_headers = None
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Extraction du texte pour le suivi de la catégorie
                text = page.extract_text()
                current_category = detect_category(text, current_category)
                
                # Extraction des tableaux de la page
                tables = page.extract_tables()
                for table in tables:
                    # 1. Fusionner les colonnes fractionnées
                    cleaned_table = merge_split_columns(table)
                    if not cleaned_table or len(cleaned_table) < 2 or len(cleaned_table[0]) < 3:
                        continue
                    
                    # 2. Vérifier si la première ligne est un en-tête
                    first_row_upper = [
                        str(col).upper().strip().replace('\n', ' ').replace('\ufffd', '°') 
                        for col in cleaned_table[0]
                    ]
                    
                    keywords = ['SUBSTANCE', 'MATIERE', 'CONC', 'T.F', 'P.COMM', 'HOMOLOGU', 'SOCIETE', 'FABRICANT', 'UTILISATION']
                    match_count = sum(1 for kw in keywords if any(kw in col for col in first_row_upper))
                    is_header = match_count >= 2
                    
                    if is_header:
                        # On met à jour l'en-tête actif avec la première ligne nettoyée
                        active_headers = first_row_upper
                        data_rows = cleaned_table[1:]
                    else:
                        # Si ce n'est pas un en-tête, c'est une continuation
                        # On vérifie que la taille correspond à l'en-tête actif
                        if active_headers and len(cleaned_table[0]) == len(active_headers):
                            data_rows = cleaned_table
                        else:
                            # Si le nombre de colonnes ne correspond pas mais qu'on a déjà des headers,
                            # on ignore cette table pour éviter des décalages imprévus (ex: tableaux de notes)
                            continue
                    
                    if data_rows:
                        # Créer le DataFrame
                        df = pd.DataFrame(data_rows, columns=active_headers)
                        
                        # Renommer les colonnes
                        df = df.rename(columns=lambda x: COLUMN_MAPPING.get(x, x))
                        
                        # Supprimer les colonnes doublonnées s'il y en a
                        df = df.loc[:, ~df.columns.duplicated(keep='first')]
                        
                        # Ajouter les colonnes manquantes
                        for col in TARGET_COLUMNS:
                            if col not in df.columns:
                                df[col] = ''
                        
                        # Injecter la Catégorie et l'Année
                        df['Catégorie'] = current_category
                        df['Année'] = year
                        
                        # Réorganisation stricte
                        df = df[TARGET_COLUMNS]
                        
                        # Nettoyer les sauts de ligne internes et espaces blancs
                        df = df.astype(str).apply(lambda col: col.str.replace('\n', ' ').str.strip())
                        
                        # Éliminer les lignes qui répètent les en-têtes ou qui sont vides
                        df = df[df['Substance Active'].str.upper() != 'SUBSTANCE ACTIVE']
                        df = df[df['Substance Active'].str.upper() != 'MATIERE ACTIVE']
                        df = df[df['Substance Active'].str.upper() != 'SUBTANCE ACTIVE']
                        
                        # Garder la ligne si elle contient au moins une donnée significative
                        # (évite de garder des lignes de remarques vides ou des annexes)
                        mask_valid = (
                            (df['Substance Active'] != '') & (df['Substance Active'] != 'None') |
                            (df['Produit Commercial'] != '') & (df['Produit Commercial'] != 'None') |
                            (df['Numéro Homologation'] != '') & (df['Numéro Homologation'] != 'None')
                        )
                        df = df[mask_valid]
                        
                        if not df.empty:
                            all_dfs.append(df)
                            
        print(f"[+] Succès : {pdf_path} ({len(all_dfs)} tableaux consolidés)")
        
    except Exception as e:
        print(f"[-] Erreur critique sur {pdf_path}: {e}")
        
    if all_dfs:
        df_concat = pd.concat(all_dfs, ignore_index=True)
        return df_concat
    return pd.DataFrame(columns=TARGET_COLUMNS)

def main():
    # Mapping exact des fichiers fournis vers leurs années respectives
    files_to_process = {
        "liste-des-pesticides-homologues-en-tunisie_13-02-2020.pdf": 2020,
        "liste-des-pesticides-homologues-27-dec-2022-.pdf": 2022,
        "liste-des-produits-pesticides-homologues_ver.finale-19-avril-2023.pdf": 2023,
        "liste-des-produits-homologues-22-mai-2024.pdf": 2024,
        "liste-des-produits-pesticides-homologues-16-juillet-2025-vf-1.pdf": 2025
    }
    
    master_df = pd.DataFrame(columns=TARGET_COLUMNS)
    
    print("Démarrage de l'extraction OSINT (Pesticides) - Phase de parsing...")
    for filename, year in files_to_process.items():
        # Corriger le chemin pour chercher dans le sous-dossier pdf/ ou dossier courant
        filepath = os.path.join("pdf", filename) if not os.path.exists(filename) else filename
        if os.path.exists(filepath):
            print(f"-> Traitement de l'archive {year}...")
            df_year = extract_pesticides_from_pdf(filepath, year)
            
            # Forward-fill les colonnes Substance, Concentration, Formulation et Catégorie
            # pour propager l'info sur les lignes de produits commerciaux dérivés
            if not df_year.empty:
                cols_to_ffill = ['Substance Active', 'Concentration', 'Formulation', 'Catégorie']
                for col in cols_to_ffill:
                    df_year[col] = df_year[col].replace('', None).replace('None', None).ffill()
            
            master_df = pd.concat([master_df, df_year], ignore_index=True)
        else:
            print(f"[!] Fichier introuvable dans le répertoire courant ou dans pdf/ : {filename}")
            
    if not master_df.empty:
        # Nettoyage final : on retire les doublons stricts pour une même année
        master_df.drop_duplicates(inplace=True)
        
        # Export avec encodage utf-8-sig pour que les accents s'affichent correctement sur Excel/Google Sheets
        output_file = "Dataset_Pesticides_Tunisie_2020_2025_Structure.csv"
        master_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n[+] Terminé. Fichier généré : {output_file}")
        print(f"[i] {len(master_df)} lignes prêtes pour l'analyse datajournalistique.")
    else:
        print("\n[!] Échec : Aucun dataset n'a pu être consolidé. Vérifie les chemins d'accès.")

if __name__ == "__main__":
    main()