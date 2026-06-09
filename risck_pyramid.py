import pandas as pd

# Load the enriched dataset
df = pd.read_csv("data/output/pesticides_tn_enriche.csv")
def categoriser_risque(score):
    if score >= 8: return "Rouge (Extrême)"
    if score >= 4: return "Orange (Modéré)"
    return "Vert/Jaune (Faible)"

df['niveau_risque'] = df['tox_severity_score'].apply(categoriser_risque)
distribution = df['niveau_risque'].value_counts()

print("\n--- DISTRIBUTION DES RISQUES DANS LE REGISTRE ---")
print(distribution)