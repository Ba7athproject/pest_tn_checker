# -*- coding: utf-8 -*-
"""
Script de consolidation, découpage de mélanges et d'Entity Resolution pour les pesticides.
Ce script :
1. Nettoie et harmonise les noms d'entreprises (Sociétés et Fabricants).
2. Découpe les mélanges de substances actives (séparées par '+') en colonnes individuelles.
3. Gère les valeurs manquantes et assure la compatibilité avec le reste de la pipeline du projet.

Auteur : Développeur Python Senior (Datajournalisme & OSINT)
Date : Juin 2026
"""

import os
import sys
import re
import unicodedata
import pandas as pd

def nettoyer_statut_juridique(nom) -> str:
    """
    Fonction OSINT pour standardiser et canoniser les noms d'entreprises.
    Supprime les accents, la ponctuation, les espaces superflus et les suffixes
    juridiques ou géographiques pour faciliter la réconciliation.
    
    Args:
        nom (any): Nom de l'entreprise à nettoyer (peut être NaN, float ou str).
        
    Returns:
        str: Le nom canonisé de l'entreprise en majuscules, ou "NON SPECIFIE".
    """
    if pd.isna(nom):
        return "NON SPECIFIE"
        
    try:
        # 1. Normalisation de base : suppression des espaces aux extrémités et mise en minuscules
        nom_str = str(nom).strip().lower()
        
        # Détection et normalisation immédiate de toutes les variantes de "Non spécifié"
        nom_sans_accent_base = ''.join(
            c for c in unicodedata.normalize('NFD', nom_str) 
            if unicodedata.category(c) != 'Mn'
        )
        if nom_sans_accent_base in [
            'non specifie', 'non specifiee', 'non specifiees', 'non specifies', 
            'none', 'null', 'nan', '', 'non_specifie', 'non-specifie'
        ]:
            return "NON SPECIFIE"
            
        # 2. Suppression des accents (diacritiques)
        nom_str = ''.join(c for c in unicodedata.normalize('NFD', nom_str) if unicodedata.category(c) != 'Mn')
        
        # 3. Remplacement de la ponctuation et des caractères spéciaux par des espaces
        nom_str = re.sub(r'[^\w\s]', ' ', nom_str)
        
        # 4. Suppression des termes juridiques, corporatifs et géographiques isolés
        # Utilisation de \b pour s'assurer de ne cibler que des mots entiers (ex: évite de couper "franc" dans "france")
        termes_a_purger = (
            r'\b(sarl|sas|ltd|spa|co|llc|inc|gmbh|france|tunisia|tunisie|limited|'
            r'company|crop|protection|agrochemical|agrochemicals|chemicals|'
            r'chemical|sciences|science|agriculture|agricole)\b'
        )
        nom_str = re.sub(termes_a_purger, '', nom_str)
        
        # 5. Nettoyage final des espaces multiples et retour en majuscules
        nom_final = re.sub(r'\s+', ' ', nom_str).strip()
        
        if not nom_final:
            return "NON SPECIFIE"
            
        return nom_final.upper()
        
    except Exception as e:
        print(f"[!] Erreur lors de la canonisation de '{nom}': {e}")
        return str(nom).upper()


def extraire_substances_actives(df: pd.DataFrame, col_source: str = "Substance(s) active(s)", max_subs: int = 4) -> pd.DataFrame:
    """
    Extrait et découpe les substances actives à partir d'une colonne de mélange (séparées par '+').
    Crée et remplit les colonnes 'substance_active_1' à 'substance_active_4'.
    Proactivement, remplit également 'substance_unit_1' à 'substance_unit_4' pour assurer
    la compatibilité avec les scripts suivants du projet (qui attendent 'substance_unit_X').
    
    Args:
        df (pd.DataFrame): Le DataFrame contenant le catalogue de pesticides.
        col_source (str): Nom de la colonne source contenant la formule (ex: 'Substance(s) active(s)').
        max_subs (int): Nombre maximal de substances à extraire (4 par défaut).
        
    Returns:
        pd.DataFrame: Le DataFrame enrichi des colonnes de substances découpées.
    """
    print(f"[*] Extraction et découpage des substances actives à partir de '{col_source}'...")
    
    # Initialisation des colonnes de sortie
    for i in range(1, max_subs + 1):
        df[f'substance_active_{i}'] = ""
        df[f'substance_unit_{i}'] = ""  # Doublon pour compatibilité avec reconcile_substances.py
        
    for idx, row in df.iterrows():
        raw_val = row.get(col_source)
        
        # Gestion des cas où la substance est vide, nulle ou marquée comme non spécifiée
        if pd.isna(raw_val) or not str(raw_val).strip():
            df.at[idx, 'substance_active_1'] = "NON SPECIFIE"
            df.at[idx, 'substance_unit_1'] = "NON SPECIFIE"
            continue
            
        raw_str = str(raw_val).strip()
        
        # Vérification si la valeur brute est une variation de "Non spécifié"
        norm_test = ''.join(c for c in unicodedata.normalize('NFD', raw_str.lower()) if unicodedata.category(c) != 'Mn')
        if norm_test in ['non specifie', 'non specifiee', 'none', 'null', 'nan']:
            df.at[idx, 'substance_active_1'] = "NON SPECIFIE"
            df.at[idx, 'substance_unit_1'] = "NON SPECIFIE"
            continue
            
        # Découpage déterministe par le signe '+'
        # Suppression des espaces blancs superflus autour de chaque élément extrait
        parts = [p.strip() for p in raw_str.split("+")]
        parts = [p for p in parts if p]  # Élimine les parties vides accidentelles
        
        # Attribution aux colonnes cibles (dans la limite de max_subs)
        for i in range(min(max_subs, len(parts))):
            col_idx = i + 1
            val_sub = parts[i]
            
            df.at[idx, f'substance_active_{col_idx}'] = val_sub
            df.at[idx, f'substance_unit_{col_idx}'] = val_sub
            
    return df


def main():
    print("=== Démarrage de l'Entity Resolution (Résolution d'Entités) ===")
    
    # 1. Définition et résolution dynamique des chemins pour éviter les erreurs d'exécution
    # selon le répertoire d'invocation (ex: depuis la racine ou depuis le sous-dossier 'utils')
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # Résolution des fichiers relative au projet racine
    fichier_entree = os.path.join(project_root, 'data', 'input', 'N_pesticide - NBLM.csv')
    fichier_sortie = os.path.join(project_root, 'data', 'output', 'Pesticides_TN_Consolides.csv')
    fichier_dictionnaire = os.path.join(project_root, 'data', 'output', 'Audit_Fusions_Entreprises.csv')
    
    print(f"[*] Chemin d'entrée résolu : {fichier_entree}")
    
    # Création du répertoire de sortie si inexistant
    os.makedirs(os.path.dirname(fichier_sortie), exist_ok=True)
    
    # 2. Chargement sécurisé des données avec tolérance aux encodages
    df = None
    encodings_to_try = ['utf-8-sig', 'utf-8', 'cp1252', 'latin1']
    
    for encoding in encodings_to_try:
        try:
            df = pd.read_csv(fichier_entree, sep=',', encoding=encoding)
            print(f"[+] Base chargée avec succès avec l'encodage : {encoding} ({len(df)} lignes).")
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"[!] Erreur inattendue de lecture avec l'encodage {encoding} : {e}")
            
    if df is None:
        print(f"[!] Erreur critique : Impossible de lire le fichier '{fichier_entree}'.")
        print("    Vérifiez que le fichier existe et que son encodage est valide (UTF-8, Latin-1, CP1252).")
        sys.exit(1)

    # Vérification de la présence des colonnes indispensables
    colonnes_requises = ['Substance(s) active(s)', 'Société', 'Fabricant']
    for col in colonnes_requises:
        if col not in df.columns:
            print(f"[!] Erreur : La colonne obligatoire '{col}' est absente du fichier CSV d'entrée.")
            print(f"    Colonnes disponibles : {df.columns.tolist()}")
            sys.exit(1)

    # 3. Découpage et extraction des substances actives individuelles
    df = extraire_substances_actives(df, col_source='Substance(s) active(s)', max_subs=4)

    # 4. Application de la canonisation et de l'Entity Resolution des entreprises
    print("[*] Consolidation des noms de Sociétés locales et Fabricants...")
    df['Société_Canonique'] = df['Société'].apply(nettoyer_statut_juridique)
    df['Fabricant_Canonique'] = df['Fabricant'].apply(nettoyer_statut_juridique)
    
    # 5. Création du dictionnaire de transparence pour audit OSINT (suivi des fusions d'entités)
    # Regroupement des variations orthographiques sous leur forme canonique unique
    audit_fabricants = df.groupby('Fabricant_Canonique')['Fabricant'].unique().reset_index()
    audit_fabricants.rename(columns={'Fabricant': 'Variations_Originales'}, inplace=True)
    audit_fabricants['Variations_Originales'] = audit_fabricants['Variations_Originales'].apply(
        lambda val_list: ' | '.join([str(v) for v in val_list if pd.notna(v)])
    )
    
    # 6. Calcul et affichage des parts de marché (Top 10 des Fabricants consolidés)
    top_fabricants = df['Fabricant_Canonique'].value_counts().head(10)
    print("\n=== TOP 10 DES FABRICANTS (Après consolidation) ===")
    print(top_fabricants)
    print("===================================================\n")
    
    # 7. Sauvegarde sécurisée des résultats consolidés
    try:
        # Fichier principal enrichi des colonnes canoniques et substances découpées
        df.to_csv(fichier_sortie, sep=';', index=False, encoding='utf-8-sig')
        # Dictionnaire d'audit pour le suivi journalistique des fusions d'entreprises
        audit_fabricants.to_csv(fichier_dictionnaire, sep=';', index=False, encoding='utf-8-sig')
        
        print(f"[+] Pipeline d'Entity Resolution finalisé et assaini.")
        print(f"    -> Base consolidée : {fichier_sortie}")
        print(f"    -> Journal des fusions : {fichier_dictionnaire}")
    except Exception as e:
        print(f"[!] Erreur lors de l'enregistrement des fichiers de sortie : {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()