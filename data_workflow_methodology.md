# Document Méthodologique : Workflow de Réconciliation des Pesticides

Ce document présente en détail le fonctionnement méthodologique et technique du pipeline de réconciliation des données de pesticides tunisiens avec la base de données des substances actives de l'Union Européenne.

---

## Architecture Générale du Workflow

![Architecture Générale du Workflow](data/architecture_generale.png)

<details>
<summary>Source Mermaid de l'Architecture</summary>

```mermaid
graph TD
    A[Base API de l'Union Européenne] -->|01_download_db.py| B[(Référence EU CSV & JSON)]
    C[Fichier Brut Tunisian Products] -->|build_manual_review_queue.py| D[Découpage & Normalisation]
    D --> E{Moteur de Rapprochement}
    E -->|1. Historique / Mappings| F[Auto Mapped]
    E -->|2. Correspondance Exacte| G[Exact Match]
    E -->|3. Score Fuzzy / Sémantique > 95%| H[Auto Accepted]
    E -->|4. Ambigu & LLM / Échec| I[Revue Manuelle Queue]
    I -->|Validation Humaine 'accept'| J[Réinjection & Apprentissage]
    J -->|reinject_decisions.py| K[Mise à jour de manual_mapping.csv]
    J --> L[Classification Réglementaire EU]
    L --> M[Calcul de l'Homologation Produit]
    M --> N[(Dataset Final Conforme)]
```
</details>


---

## Étape 1 : Acquisition de la Référence Européenne (`01_download_db.py`)

* **Objectif** : Télécharger et conserver localement une copie intégrale de la base de données officielle européenne de la DG SANTE.
* **Algorithme et Robustesse** :
  * Le script interroge l'API REST `https://api.datalake.sante.service.ec.europa.eu`.
  * Il gère le **ratelimit** (erreurs `429 Too Many Requests`) en lisant l'en-tête HTTP `Retry-After` renvoyé par le serveur de l'UE pour suspendre proprement les requêtes.
  * Il effectue jusqu'à 5 tentatives de téléchargement avec un **backoff exponentiel** en cas de panne temporaire (erreurs de serveurs `5xx`).
  * **Sortie** : Sauvegarde le NDJSON brut dans `data/reference/eu_active_substances_full.json` (auditabilité) et compile le tableau plat de référence dans `data/reference/eu_active_substances_full.csv`.

---

## Étape 2 : Préparation et Normalisation des Produits (`build_manual_review_queue.py`)

Les substances actives renseignées dans le catalogue tunisien (`data/input/pesticides_tn_checked2.csv`) sont souvent des mélanges, contiennent des impuretés orthographiques, des accents ou des dosages. Le pipeline prépare ces chaînes selon les étapes suivantes :

### A. Découpage des Formules de Mélange (`substance_splitting.py`)
* Le pipeline détecte et sépare les principes actifs multiples séparés par des caractères comme `+`, `;`, `/` ou des conjonctions (`et`, `and`).
* *Exemple* : `"Azadirachtine + Huile de neem"` $\rightarrow$ `["Azadirachtine", "Huile de neem"]`.

### B. Nettoyage Orthographique et Standardisation (`text_normalization.py`)
1. **Retrait des Doses et Unités** : Les indications de dosage et d'unités de mesure sont éliminées via des expressions régulières (ex: `10%`, `50 g/l`, `1x10^10 spores/g`, `WP`, `EC`).
2. **Traduction Chimique** : Les termes en français sont traduits en anglais pour s'aligner sur la base de données européenne (ex: `huile` $\rightarrow$ `oil`, `cuivre` $\rightarrow$ `copper`, `sel` $\rightarrow$ `salt`).
3. **Correction de Variantes** : Les coquilles et variations d'appellation fréquentes sont corrigées (ex: `abamectine` $\rightarrow$ `abamectin`, `lambdacyhalothrine` $\rightarrow$ `lambda-cyhalothrin`).
4. **Simplification** : Les accents sont retirés, le texte est passé en minuscules, et les parenthèses ainsi que les espaces multiples sont normalisés.

---

## Étape 3 : Moteur de Correspondance Multi-Niveaux

Pour chaque substance active extraite de chaque produit commercial, le pipeline applique une cascade de règles, de la plus déterministe à la plus probabiliste :

1. **Vérification de l'Historique de Mapping** : Le script recherche le nom normalisé dans le fichier [manual_mapping.csv](file:///c:/Ba7ath_scripts/pesticides/data/interim/manual_mapping.csv) qui stocke l'historique des validations humaines précédentes. S'il y a correspondance, la substance est validée en tant que `"auto_mapped"`.
2. **Correspondance Exacte** : Le nom normalisé est comparé directement avec la liste des noms normalisés de l'UE. En cas de correspondance parfaite, le statut est `"exact"`.
3. **Seuil de Score Fuzzy & Sémantique** :
   * Le script calcule le score de proximité textuelle (`rapidfuzz`) et, si activé, le score de similarité vectorielle (embeddings locaux Ollama `nomic-embed-text`).
   * Si le score fusionné est supérieur ou égal à **95%**, la correspondance est automatiquement approuvée sous le type `"auto_accept_high_confidence"`.
4. **Arbitrage LLM Local (Optionnel)** : Si le score est intermédiaire (entre 40% et 75%) et que Ollama est actif, un LLM local (`qwen3:14b`) tente de résoudre l'ambiguïté à l'aide d'une invite structurée en JSON (explicitant les synonymes et les sels de la substance). Le LLM a interdiction stricte de proposer un candidat en dehors de la shortlist proposée.
5. **Génération de la file de revue** : Tout produit contenant au moins une substance active non résolue (score < 95%) est dirigé vers la file d'attente manuelle [manual_review_queue.csv](file:///c:/Ba7ath_scripts/pesticides/data/interim/manual_review_queue.csv). Le fichier présente les produits par ligne, avec les 5 meilleurs candidats proposés pour chaque substance active non résolue.

---

## Étape 4 : Revue Manuelle par l'Opérateur

* L'utilisateur ouvre le fichier `data/interim/manual_review_queue.csv` dans son tableur ou éditeur CSV.
* Pour chaque substance active en suspens (repérée par les slots `substance_unit_i` et `substance_normalized_i`), il doit renseigner une décision réglementaire dans la colonne `review_decision_i` :
  * **`accept`** : Valide le rapprochement de la substance. L'opérateur **doit** alors copier/coller le nom officiel de la substance de référence de l'UE dans la colonne `review_match_name_i`. (Des hyperliens vers les fiches de l'UE sont fournis pour faciliter cette vérification).
  * **`reject`** : Marque le rapprochement comme rejeté. La substance n'est pas réinjectée dans le cache historique, son statut final devient `"Rejected"` et le produit associé sera marqué non conforme.
  * **`needs_research`** : Indique que la substance requiert plus de recherches. Son statut final reste `"Needs Research"`.
  * *Vide* / **`review`** / **`review_accept_high_score`** : Conservent la substance dans l'état `"Pending Review"`.
* L'utilisateur enregistre et ferme le fichier CSV.

---

## Étape 5 : Réinjection, Apprentissage et Homologation (`reinject_decisions.py`)

Lorsque l'utilisateur lance le script de réinjection, le pipeline assemble les décisions prises par l'opérateur et compile le catalogue final.

### A. Mécanisme de Réinjection et Apprentissage (Feedback Loop)

![Mécanisme de Réinjection et Apprentissage](data/workflow_reinjection_decisions.png)

<details>
<summary>Source Mermaid du Mécanisme de Réinjection</summary>

```mermaid
graph TD
    A[Lire manual_review_queue.csv] --> B[Identifier les décisions review_decision_i]
    B --> C{Valeur de la décision ?}
    C -->|Autre que 'accept'| D[Pas d'enregistrement dans le mapping historique]
    C -->|'accept' + nom UE renseigné| E[Enregistrer le couple dans le mapping historique]
    
    E --> F[Sauvegarder dans manual_mapping.csv]
    E --> G[Interroger la base de référence de l'UE]
    G --> H[Enrichir le catalogue avec les données réglementaires]
    H --> I[Calculer product_is_approved et le niveau de risque global]
    I --> J[Sauvegarder dans pesticides_tn_clean.csv]
```
</details>


1. **Parcours de la File** : Le script parcourt la file d'attente manuelle et récupère les décisions prises pour chaque slot.
2. **Apprentissage Actif** : Pour chaque décision **`accept`**, il met à jour le dictionnaire de correspondance historique en associant le nom tunisien nettoyé au nom officiel de l'UE.
3. **Persistance du Cache** : Les nouvelles associations sont enregistrées dans le fichier [manual_mapping.csv](file:///c:/Ba7ath_scripts/pesticides/data/interim/manual_mapping.csv). Lors de la prochaine exécution de la file d'attente (`build_manual_review_queue.py`), ces substances seront automatiquement résolues comme `"auto_mapped"` sans action humaine.

### B. Informations Injectées dans les Fichiers de Sortie

Le processus de réinjection enrichit et met à jour deux fichiers clés :

#### 1. Dans le cache historique [manual_mapping.csv](file:///c:/Ba7ath_scripts/pesticides/data/interim/manual_mapping.csv)
Il enregistre la correspondance générique :
* **`source_name`** : Le nom normalisé d'origine tunisienne (ex: `huile de neem`).
* **`eu_name`** : Le nom officiel de la substance active tel qu'il apparaît dans la base de l'UE (ex: `NEEM SEED OIL REFINED`).

#### 2. Dans le catalogue final [pesticides_tn_clean.csv](file:///c:/Ba7ath_scripts/pesticides/data/output/pesticides_tn_clean.csv)
Le script interroge la base européenne de référence [eu_active_substances_full.csv](file:///c:/Ba7ath_scripts/pesticides/data/reference/eu_active_substances_full.csv) pour les correspondances acceptées afin d'injecter dans chaque produit :
* **`eu_substances_final`** : Le(s) nom(s) officiel(s) de(s) substance(s) active(s) associée(s).
* **`eu_statuses_final`** : Le statut réglementaire consolidé de la substance (*Approved*, *Not approved*, *Expired*, *Banned*, etc.).
* **`eu_approval_start` / `eu_approval_end`** : Les dates de début et de fin d'autorisation européenne.
* **`eu_candidate_for_substitution`** : Indicateur booléen signalant si la substance est candidate à la substitution.
* **`eu_is_low_risk`** : Booléen spécifiant si la substance est à faible risque.
* **`eu_is_basic_substance`** : Booléen spécifiant si c'est une substance de base.
* **`eu_regulatory_risk_flag`** : Un niveau de risque global calculé pour le produit commercial (*low*, *medium*, *high*).
* **`product_is_approved`** : L'autorisation finale du produit commercial (*True* si toutes ses substances actives non vides sont approuvées par l'UE, sinon *False*).

### B. Classification Réglementaire Fine (`regulatory_classifier.py`)
Le pipeline enrichit les données avec le contexte réglementaire européen de chaque substance :
* **Calcul des dates** : Analyse et standardisation des dates de début et de fin d'autorisation. Si la date actuelle dépasse la date d'expiration européenne, le statut de la substance est ré-évalué de `"Approved"` à `"Expired"`.
* **Indicateurs de substitution et de risque** :
  * Détection si la substance est qualifiée de "Candidat à la substitution" (`candidate_for_substitution`).
  * Détection si la substance est à "Faible risque" (`low_risk_active_substance`) ou si c'est une "Substance de base" (`basic_substance`).
  * Calcul du niveau de risque global de la substance : `"low"`, `"medium"` ou `"high"` (le risque passe à `"high"` si elle est interdite, en substitution, ou retirée).

### C. Invariant d'Homologation du Produit Commercial
* **Règle d'Invariant** : Un produit commercial complet (qui peut contenir plusieurs substances) n'obtient l'approbation finale (`product_is_approved = True`) **que si toutes ses substances actives non vides** sont individuellement associées à des substances de référence approuvées par l'UE (statut exact `"Approved"`).
* Si une seule substance active du produit est rejetée, expirée, interdite ou non approuvée, le produit entier est marqué `product_is_approved = False`.

#### Focus : Workflow de Matching et Gestion des Substances "Not approved"

Lorsqu'une substance active matche entre la base de données tunisienne et la base européenne, et que son statut dans l'UE est classé sous une catégorie de type **non approuvé** (e.g. `not approved`, `withdrawn`, `expired`, `banned`, `not renewed`), voici le parcours technique et logique appliqué :

![Workflow de Matching et Gestion des Substances "Not approved"](data/workflow_matching_not_approved.png)

<details>
<summary>Source Mermaid du Workflow</summary>

```mermaid
graph TD
    A[Substance Active Tunisienne] -->|Matching réussi| B{Statut de la substance dans l'UE ?}
    B -->|Approved| C[Substance : 'Approved']
    B -->|Not approved / Expired / Banned / Withdrawn / Not renewed| D[Substance : 'Not approved']
    
    D --> E[Substance : Niveau de risque = high]
    D --> F[Produit Commercial : product_is_approved = False]
    D --> G[Produit Commercial : eu_overall_status = CONTAINS_NOT_APPROVED_SUBSTANCE_IN_EU]
    D --> H[Produit Commercial : eu_regulatory_risk_flag = high]
    D --> I[Alerte : Ajout de la substance dans la colonne Substance alerte finale]
```
</details>


1. **Extraction et Classification individuelle (Substance-level)** :
   * La fonction `classify_status_eu` dans [match_engine.py](file:///c:/Ba7ath_scripts/pesticides/utils/match_engine.py) unifie tous les états non-autorisés sous le statut `"Not approved"`.
   * Le script [regulatory_classifier.py](file:///c:/Ba7ath_scripts/pesticides/src/eu/regulatory_classifier.py) attribue le drapeau de risque réglementaire `eu_regulatory_risk_flag = "high"` pour cette substance.

2. **Agrégation et Décision finale (Product-level)** :
   * Dans [reinject_decisions.py](file:///c:/Ba7ath_scripts/pesticides/scripts/reinject_decisions.py), si un produit commercial contient la substance en question, l'invariant d'homologation échoue :
     * **`product_is_approved`** passe à **`False`** (car `all(s == "Approved" for s in resolved_statuses)` renvoie faux).
     * **`eu_overall_status`** prend la valeur **`CONTAINS_NOT_APPROVED_SUBSTANCE_IN_EU`**.
     * **`eu_regulatory_risk_flag`** du produit est marqué à **`high`**.
     * La substance en alerte est répertoriée dans la colonne **`Substance alerte finale`** sous le format `nom_substance (Not approved)`.

### D. Export du Catalogue Final
Toutes les métadonnées consolidées et les statuts détaillés sont enregistrés dans le catalogue final [pesticides_tn_clean.csv](file:///c:/Ba7ath_scripts/pesticides/data/output/pesticides_tn_clean.csv).

