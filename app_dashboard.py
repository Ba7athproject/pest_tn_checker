# app_dashboard.py
import streamlit as st
import pandas as pd
import plotly.express as px
import os
import sys

# Adjust path to import src module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(layout="wide", page_title="Ba7ath Dashboard Investigation")

# --- CHARTE GRAPHIQUE BA7ATH ---
BA7ATH_COLORS = {
    "Rouge (Extrême)": "#D62828",
    "Orange (Modéré)": "#F77F00",
    "Vert/Jaune (Faible)": "#588157"
}

# --- PALETTE PERSONNALISÉE POUR LE STATUT UE ---
STATUS_COLORS = {
    "Approved": "#007BFF",  # Bleu vif pour le statut Approved
    "Not approved": "#D62828" # Rouge pour Not approved
}

def categoriser_risque(score):
    if score >= 8: return "Rouge (Extrême)"
    if score >= 4: return "Orange (Modéré)"
    return "Vert/Jaune (Faible)"

# --- CHARGEMENT DES DONNÉES ---
@st.cache_data
def load_data():
    df = pd.read_csv("data/output/pesticides_tn_enriche.csv")
    
    # Séparation et explosion de la colonne 'Substance Active'
    df['Substance Active'] = df['Substance Active'].fillna('').astype(str)
    import re
    df['Substance Active'] = df['Substance Active'].apply(
        lambda x: [s.strip() for s in re.split(r'[,/+\+]', x) if s.strip()]
    )
    df = df.explode('Substance Active')
    df = df[df['Substance Active'].str.strip() != '']
    
    # Filtrage des lignes pour associer chaque ligne explodée à sa correspondance correcte
    from src.common.gatekeeper import normalize_text
    
    def is_valid_exploded_row(row):
        sub_norm = normalize_text(row['Substance Active'])
        clean_norm = normalize_text(row['clean_name'])
        if not clean_norm:
            return True
        return sub_norm in clean_norm or clean_norm in sub_norm
        
    df = df[df.apply(is_valid_exploded_row, axis=1)].reset_index(drop=True)
    
    # Normalisation de la colonne 'Société'
    df['Société'] = df['Société'].fillna('').astype(str).str.strip().str.replace(r'\s+', ' ', regex=True).str.upper()
    
    # Ajout de la colonne de risque pour la coloration automatique
    df['niveau_risque'] = df['tox_severity_score'].apply(categoriser_risque)
    # Récupération de l'URL source
    df['Source Scientifique'] = df['eu_source_url'].fillna("")
    return df

df = load_data()

st.title("📊 Dashboard d'Investigation : Projet Ba7ath")
st.markdown("---")

# --- SIDEBAR (NAVIGATION & FILTRES) ---
st.sidebar.header("Navigation")
view = st.sidebar.radio("Sélectionner la vue", ["Vue Macro", "Acteurs & Produits", "Analyse Corrélation"])

st.sidebar.markdown("---")
st.sidebar.header("Paramètres d'Investigation")

# Recherche textuelle globale
search_sub = st.sidebar.text_input("Rechercher un produit ou une substance", "")

if view == "Vue Macro":
    status_filter = st.sidebar.multiselect("Filtrer par Statut UE", df['eu_status'].unique())
    min_score = st.sidebar.slider("Seuil de dangerosité min (Score 0-10)", 0, 10, 0)
    show_intercepted = st.sidebar.checkbox("Inclure les produits interceptés (Biocontrôle/Adjuvants)", value=False)

    # --- APPLICATION DES FILTRES ---
    filtered_df = df.copy()

    # Appliquer la recherche textuelle en priorité
    if search_sub.strip():
        filtered_df = filtered_df[
            filtered_df['Produit Commercial'].str.contains(search_sub, case=False, na=False) | 
            filtered_df['Substance Active'].str.contains(search_sub, case=False, na=False)
        ]

    if status_filter:
        filtered_df = filtered_df[filtered_df['eu_status'].isin(status_filter)]

    filtered_df = filtered_df[filtered_df['tox_severity_score'] >= min_score]

    if not show_intercepted:
        filtered_df = filtered_df[filtered_df['intercepted'] == False]

    # --- VISUALISATION ---
    col1, col2 = st.columns(2)

    with col1:
        # Histogramme avec charte couleur Ba7ath (Score danger)
        fig = px.histogram(
            filtered_df, 
            x="tox_severity_score", 
            color="niveau_risque",
            color_discrete_map=BA7ATH_COLORS,
            title="Distribution des Scores de Dangerosité",
            nbins=11
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Pie Chart avec couleurs forcées (Bleu pour Approved)
        fig_status = px.pie(
            filtered_df, 
            names="eu_status", 
            title="Répartition par statut UE",
            color="eu_status",
            color_discrete_map=STATUS_COLORS
        )
        st.plotly_chart(fig_status, use_container_width=True)
        
    # --- TABLEAU DES RÉSULTATS ---
    st.subheader("Substances détaillées")

    def color_risk(val):
        color = BA7ATH_COLORS.get(val, '')
        if color:
            return f'background-color: {color}; color: white; font-weight: bold;'
        return ''

    st_df = filtered_df[['clean_name', 'eu_status', 'tox_severity_score', 'niveau_risque', 'adi_mg_kg_bw', 'arfd_mg_kg_bw', 'Source Scientifique']]
    styler = st_df.style
    if hasattr(styler, 'map'):
        styler = styler.map(color_risk, subset=['niveau_risque'])
    else:
        styler = styler.applymap(color_risk, subset=['niveau_risque'])

    st.dataframe(
        styler,
        column_config={
            "Source Scientifique": st.column_config.LinkColumn(
                "Source Scientifique",
                help="Lien vers la législation officielle de l'EFSA",
                validate=r"^https?://",
                display_text="🔗 Source EFSA"
            )
        },
        use_container_width=True
    )

    # --- BOUTON EXPORT ---
    csv = filtered_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Exporter les résultats filtrés en CSV",
        csv,
        "ba7ath_investigation_results.csv",
        "text/csv",
        key='download-csv'
    )

elif view == "Acteurs & Produits":
    # Dropna to avoid displaying string nan
    companies_list = sorted([str(x) for x in df['Société'].dropna().unique() if str(x).strip()])
    manufacturers_list = sorted([str(x) for x in df['Fabricant'].dropna().unique() if str(x).strip()])

    selected_companies = st.sidebar.multiselect("Filtrer par Société", companies_list)
    selected_manufacturers = st.sidebar.multiselect("Filtrer par Fabricant", manufacturers_list)

    # --- APPLICATION DES FILTRES ---
    filtered_view_df = df.copy()

    # Appliquer la recherche textuelle en priorité
    if search_sub.strip():
        filtered_view_df = filtered_view_df[
            filtered_view_df['Produit Commercial'].str.contains(search_sub, case=False, na=False) | 
            filtered_view_df['Substance Active'].str.contains(search_sub, case=False, na=False)
        ]

    if selected_companies:
        filtered_view_df = filtered_view_df[filtered_view_df['Société'].astype(str).isin(selected_companies)]
    if selected_manufacturers:
        filtered_view_df = filtered_view_df[filtered_view_df['Fabricant'].astype(str).isin(selected_manufacturers)]

    # --- EN-TÊTE DE SECTION ---
    st.subheader("Analyse par Acteurs & Produits")
    st.markdown("Explorez la conformité des portefeuilles de produits phytosanitaires par importateurs (Sociétés) et producteurs (Fabricants).")

    # --- CONTENEUR D'ONGLETS ---
    tab_graphe, tab_risques, tab_tableau = st.tabs(["📊 Graphe de Conformité", "⚠️ Classement des Risques", "📋 Inventaire détaillé"])

    with tab_graphe:
        # Grouper les données par Société et Statut UE pour compter le nombre de produits
        group_df = filtered_view_df.groupby(['Société', 'eu_status']).size().reset_index(name='Nombre de Produits')
        
        if not group_df.empty:
            fig_conformite = px.bar(
                group_df,
                x="Société",
                y="Nombre de Produits",
                color="eu_status",
                barmode="group",
                color_discrete_map=STATUS_COLORS,
                title="Nombre de Produits par Société et Conformité UE",
                labels={"Nombre de Produits": "Nombre de Produits", "eu_status": "Statut UE"}
            )
            fig_conformite.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_conformite, use_container_width=True)
        else:
            st.info("Aucune donnée correspondante pour afficher le graphique de conformité.")

    with tab_risques:
        # Calculer le 'Taux de Risque' par société :
        # (Nombre de substances 'Not approved' / Nombre total de substances) * 100
        company_stats = []
        for company, group in filtered_view_df.groupby('Société'):
            total_substances = len(group)
            not_approved_substances = len(group[group['eu_status'] == 'Not approved'])
            risk_rate = (not_approved_substances / total_substances) * 100 if total_substances > 0 else 0.0
            company_stats.append({
                'Société': company,
                'Taux de Risque (%)': round(risk_rate, 2),
                'Total Substances': total_substances,
                'Non Approuvées': not_approved_substances
            })
        df_risk_ranking = pd.DataFrame(company_stats)

        if not df_risk_ranking.empty:
            df_risk_ranking = df_risk_ranking.sort_values(by='Taux de Risque (%)', ascending=False)
            
            fig_risk = px.bar(
                df_risk_ranking,
                x="Société",
                y="Taux de Risque (%)",
                title="Classement des Sociétés par Taux de Risque (% de substances non approuvées dans l'UE)",
                labels={"Taux de Risque (%)": "Taux de Risque (%)", "Société": "Société Importatrice"},
                color="Taux de Risque (%)",
                color_continuous_scale="Reds"
            )
            fig_risk.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_risk, use_container_width=True)
        else:
            st.info("Aucune donnée disponible pour calculer les taux de risque par société.")

    with tab_tableau:
        cols_to_show = ['Produit Commercial', 'Société', 'Fabricant', 'Substance Active', 'eu_status', 'tox_severity_score']
        df_table = filtered_view_df[cols_to_show].copy()
        df_table['tox_severity_score'] = pd.to_numeric(df_table['tox_severity_score'], errors='coerce')

        # Regrouper pour n'afficher le produit commercial qu'une seule fois par ligne,
        # tout en listant individuellement les substances (de 1 à 4)
        grouped_rows = []
        for (prod, soc, fab), group in df_table.groupby(['Produit Commercial', 'Société', 'Fabricant'], dropna=False):
            row_data = {
                'Produit Commercial': prod if pd.notna(prod) else "",
                'Société': soc if pd.notna(soc) else "",
                'Fabricant': fab if pd.notna(fab) else ""
            }
            # Initialiser les 4 colonnes de substances
            for i in range(1, 5):
                row_data[f'Substance Active {i}'] = ""
                row_data[f'Statut UE {i}'] = ""
                row_data[f'Score Danger {i}'] = None
                
            for i, (_, sub_row) in enumerate(group.iterrows()):
                if i < 4:
                    row_data[f'Substance Active {i+1}'] = sub_row['Substance Active'] if pd.notna(sub_row['Substance Active']) else ""
                    row_data[f'Statut UE {i+1}'] = sub_row['eu_status'] if pd.notna(sub_row['eu_status']) else ""
                    row_data[f'Score Danger {i+1}'] = sub_row['tox_severity_score']
            grouped_rows.append(row_data)

        df_display = pd.DataFrame(grouped_rows) if grouped_rows else pd.DataFrame()

        # Construire le dictionnaire de configuration de colonnes dynamiquement
        column_config = {
            "Produit Commercial": st.column_config.TextColumn("Produit Commercial"),
            "Société": st.column_config.TextColumn("Société Importatrice"),
            "Fabricant": st.column_config.TextColumn("Fabricant")
        }
        for i in range(1, 5):
            column_config[f"Substance Active {i}"] = st.column_config.TextColumn(f"Substance {i}")
            column_config[f"Statut UE {i}"] = st.column_config.TextColumn(f"Statut UE {i}")
            column_config[f"Score Danger {i}"] = st.column_config.NumberColumn(
                f"Score {i}",
                help=f"Score de dangerosité de la substance {i}",
                format="%.1f"
            )

        st.dataframe(
            df_display,
            column_config=column_config,
            use_container_width=True
        )

    # --- BOUTON EXPORT SELECTION ---
    csv_selection = filtered_view_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Exporter la sélection courante en CSV",
        csv_selection,
        "ba7ath_acteurs_produits_selection.csv",
        "text/csv",
        key='download-selection-csv'
    )

elif view == "Analyse Corrélation":
    st.subheader("Analyse de Corrélation : Limites Toxicologiques vs Score de Dangerosité")
    st.markdown("""
    Cette vue permet d'explorer graphiquement la relation entre les valeurs limites de sécurité sanitaire de l'EFSA (DJA / ADI en mg/kg de poids corporel par jour) et notre score synthétique de dangerosité.
    Une DJA très faible (vers la gauche) signale une substance extrêmement toxique à faible dose.
    """)
    
    # Nettoyage et conversion numérique
    corr_df = df.copy()
    
    # Appliquer la recherche textuelle en priorité
    if search_sub.strip():
        corr_df = corr_df[
            corr_df['Produit Commercial'].str.contains(search_sub, case=False, na=False) | 
            corr_df['Substance Active'].str.contains(search_sub, case=False, na=False)
        ]
    
    def parse_numeric(val):
        if pd.isna(val):
            return None
        import re
        res = re.findall(r"[-+]?\d*\.\d+|\d+", str(val))
        if res:
            return float(res[0])
        return None
        
    corr_df['adi_numeric'] = corr_df['adi_mg_kg_bw'].apply(parse_numeric)
    
    # Filtrer les lignes valides pour l'affichage
    plot_df = corr_df.dropna(subset=['tox_severity_score', 'adi_numeric'])
    plot_df = plot_df[plot_df['adi_numeric'] > 0]  # Éviter log(0)
    
    if not plot_df.empty:
        fig_corr = px.scatter(
            plot_df,
            x="adi_numeric",
            y="tox_severity_score",
            color="eu_status",
            hover_name="clean_name",
            hover_data=["Produit Commercial", "Société", "eu_status"],
            log_x=True,
            color_discrete_map=STATUS_COLORS,
            title="DJA (ADI) en échelle logarithmique vs Score de dangerosité",
            labels={
                "adi_numeric": "DJA (ADI) en mg/kg pc/jour (Échelle Log)",
                "tox_severity_score": "Score de Dangerosité (0-10)",
                "eu_status": "Statut UE"
            }
        )
        fig_corr.update_traces(marker=dict(size=10, opacity=0.7, line=dict(width=1, color='DarkSlateGrey')))
        st.plotly_chart(fig_corr, use_container_width=True)
    else:
        st.info("Données insuffisantes ou non numériques pour générer le graphique de corrélation.")

# --- PIED DE PAGE ---
st.markdown("---")
st.caption("Projet Ba7ath - Outil d'investigation indépendant. Données issues de l'EFSA et de la base UE Pesticides.")