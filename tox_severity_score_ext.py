import pandas as pd

# Chargement
df = pd.read_csv("data/output/pesticides_tn_enriche.csv")

# Filtrage : Score de dangerosité élevé ET statut européen non approuvé
danger_zone = df[
    (df['tox_severity_score'] >= 8) & 
    (df['eu_status'] != 'Approved')
].drop_duplicates(subset=['clean_name'])

# Tri par score décroissant
top_danger = danger_zone.sort_values(by='tox_severity_score', ascending=False)[
    ['clean_name', 'eu_status', 'tox_severity_score', 'adi_mg_kg_bw']
].head(20)

print("--- TOP 20 DES SUBSTANCES PRIORITAIRES POUR L'ENQUÊTE ---")
print(top_danger)
top_danger.to_csv("data/output/top_20_danger.csv", index=False)