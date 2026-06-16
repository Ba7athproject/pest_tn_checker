import pandas as pd
import unicodedata
import os

def normaliser_texte(texte):
    """
    Standardise une chaîne de caractères pour l'analyse de données (OSINT).
    - Convertit en minuscules.
    - Supprime les espaces superflus aux extrémités.
    - Retire tous les accents (é, è, à, ç, etc.) pour éviter les doublons artificiels.
    """
    if pd.isna(texte):
        return texte
        
    try:
        # 1. Mise en minuscules et nettoyage des espaces périphériques
        texte = str(texte).strip().lower()
        
        # 2. Normalisation Unicode (NFD sépare la lettre de son accent)
        texte_normalise = unicodedata.normalize('NFD', texte)
        
        # 3. Filtrage : on ne garde que les caractères qui ne sont pas des marques diacritiques (accents)
        texte_sans_accent = ''.join(c for c in texte_normalise if unicodedata.category(c) != 'Mn')
        
        return texte_sans_accent
    
    except Exception as e:
        print(f"[!] Erreur de nettoyage sur la valeur '{texte}': {e}")
        return texte

def charger_donnees(chemin_fichier, separateur=';'):
    """
    Charge un fichier CSV de manière sécurisée avec gestion des erreurs.
    """
    try:
        if not os.path.exists(chemin_fichier):
            print(f"[!] Erreur : Le fichier {chemin_fichier} est introuvable.")
            return None
            
        df = pd.read_csv(chemin_fichier, sep=separateur, encoding='utf-8')
        print(f"[+] Fichier chargé avec succès : {chemin_fichier} ({len(df)} lignes)")
        return df
    except Exception as e:
        print(f"[!] Erreur lors du chargement de {chemin_fichier} : {e}")
        return None

def auditer_bases(df_script, df_notebook, colonnes_fusion):
    """
    Réalise une jointure externe (Outer Join) pour réconcilier les deux bases de données.
    Identifie les valeurs exclusives à chaque méthode d'extraction.
    """
    try:
        # Nettoyage systématique des colonnes de fusion pour garantir un alignement parfait
        for col in colonnes_fusion:
            if col in df_script.columns:
                df_script[col] = df_script[col].apply(normaliser_texte)
            if col in df_notebook.columns:
                df_notebook[col] = df_notebook[col].apply(normaliser_texte)

        # Jointure complète (Outer Join)
        comparaison = df_script.merge(
            df_notebook, 
            on=colonnes_fusion, 
            how='outer', 
            suffixes=('_cr', '_nlm'),
            indicator=True
        )
        
        return comparaison
    except Exception as e:
        print(f"[!] Erreur lors de la réconciliation des bases : {e}")
        return None

def main():
    """
    Fonction principale orchestrant le pipeline de réconciliation des données des pesticides.
    """
    print("=== Démarrage du pipeline de réconciliation ===")
    
    # Définition des chemins relatifs
    chemin_cr = os.path.join('data', 'input', 'pesticides_tn_cr.csv')
    chemin_nlm = os.path.join('data', 'input', 'pesticides_tn_nlm.csv')
    chemin_sortie = os.path.join('data', 'output', 'audit_pesticides_reconcilies.csv')
    
    # Création du dossier de sortie s'il n'existe pas
    os.makedirs(os.path.dirname(chemin_sortie), exist_ok=True)
    
    # 1. Chargement des datasets
    df_script = charger_donnees(chemin_cr, separateur=';')
    df_notebook = charger_donnees(chemin_nlm, separateur=';')
    
    if df_script is None or df_notebook is None:
        print("[-] Pipeline interrompu en raison d'un fichier manquant. Vérifiez les chemins.")
        return

    # 2. Définition des colonnes servant de clés uniques pour la fusion
    colonnes_cles = ['Substance(s) active(s)', 'P.Comm']
    
    # Vérification de la présence des colonnes clés
    for col in colonnes_cles:
        if col not in df_script.columns or col not in df_notebook.columns:
            print(f"[!] Erreur critique : La colonne '{col}' est absente d'un des fichiers.")
            return

    # 3. Exécution de l'audit et de la réconciliation
    print("[*] Nettoyage typographique et fusion des bases en cours...")
    comparaison = auditer_bases(df_script, df_notebook, colonnes_cles)
    
    if comparaison is not None:
        # 4. Analyse des résultats
        exclusif_cr = comparaison[comparaison['_merge'] == 'left_only']
        exclusif_nlm = comparaison[comparaison['_merge'] == 'right_only']
        commun = comparaison[comparaison['_merge'] == 'both']
        
        print("\n=== Rapport d'Audit ===")
        print(f"- Lignes communes aux deux extractions : {len(commun)}")
        print(f"- Lignes trouvées uniquement par Command-R : {len(exclusif_cr)}")
        print(f"- Lignes trouvées uniquement par NotebookLM : {len(exclusif_nlm)}")
        
        # 5. Exportation du rapport d'audit pour pointage
        try:
            # Encodage utf-8-sig recommandé pour une ouverture propre sous Excel
            comparaison.to_csv(chemin_sortie, sep=';', index=False, encoding='utf-8-sig')
            print(f"\n[+] Audit terminé. Rapport détaillé sauvegardé sous : {chemin_sortie}")
        except Exception as e:
            print(f"[!] Erreur lors de la sauvegarde du fichier d'audit : {e}")

if __name__ == "__main__":
    main()