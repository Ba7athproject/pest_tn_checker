import pandas as pd
import re

# Chargement du dataset contenant les listes concaténées
df = pd.read_csv('pesticides_tn_checked2.csv')

def extract_reference_list(df):
    reference_data = []

    # On parcourt le fichier ligne par ligne
    for _, row in df.iterrows():
        # On divise les chaînes par espaces multiples (en ignorant les espaces isolés)
        # Note: Si tes séparateurs sont différents (ex: virgule), ajuste le split
        produits = re.split(r'\s{2,}', str(row['Produit Commercial']))
        societes = re.split(r'\s{2,}', str(row['Société']))
        fabricants = re.split(r'\s{2,}', str(row['Fabricant']))

        # On crée une entrée pour chaque correspondance trouvée
        # On prend la longueur minimale pour éviter les débordements
        min_len = min(len(produits), len(societes), len(fabricants))
        
        for i in range(min_len):
            reference_data.append({
                'Produit_Commercial': produits[i].strip(),
                'Société': societes[i].strip(),
                'Fabricant': fabricants[i].strip()
            })

    # Création du DataFrame de référence
    ref_df = pd.DataFrame(reference_data)
    
    # Suppression des doublons stricts pour avoir une liste unique
    ref_df = ref_df.drop_duplicates().sort_values(by=['Société', 'Produit_Commercial'])
    
    return ref_df

# Exécution
print("[+] Extraction des correspondances...")
ref_df = extract_reference_list(df)

# Exportation du fichier de référence pour vérification manuelle
ref_df.to_csv('reference_correspondances_propre.csv', index=False, encoding='utf-8-sig')
print(f"[+] Dictionnaire généré : reference_correspondances_propre.csv ({len(ref_df)} entrées)")