1. ALL_SUBSTANCES_APPROVED_IN_EU
Définition
Toutes les substances actives de ce produit sont approuvées dans l’UE selon la base européenne.

Implication
Statut UE : compatible avec la réglementation européenne sur les substances actives.

Risque : faible du point de vue UE.

Action :

Pas de revue manuelle obligatoire pour le statut UE.

Peut être utilisé comme référence pour des produits “conformes UE”.

Bon à garder en tête si tu veux comparer homologation UE vs homologation tunisienne.

2. CONTAINS_NOT_APPROVED_SUBSTANCE_IN_EU
Définition
Le produit contient au moins une substance qui, dans la base UE, est :

non approuvée,

interdite,

retirée,

expirée,

ou non renouvelée.

Implication
Statut UE : produit non conforme UE au niveau des substances actives.

Risque : élevé si tu envisages l’export vers l’UE, ou si tu veux comparer avec les standards européens.

Action :

Mettre en surveillance prioritaire.

Vérifier si la substance est toujours homologuée en Tunisie.

Si export UE visé : planifier substitution ou reformulation.

Dans un rapport d’analyse, c’est souvent la catégorie “produits à risque UE”.

3. FOUND_UNKNOWN_STATUS
Définition
Une substance a été trouvée dans la base UE, mais son statut n’est ni clairement “approuvé” ni clairement “non approuvé” selon tes règles de classification. Par exemple :

statut manquant,

statut inconnu pour ton script,

valeur non couverte par tes conditions.

Implication
Statut UE : trouvé, mais statut incertain.

Risque : moyen, car il peut y avoir une substance non approuvée cachée.

Action :

Revue manuelle :

vérifier le statut exact dans la page UE de la substance,

mettre à jour la fonction classify_status si c’est un cas fréquent.

Peut être automatisé plus tard si tu écris les statuts manquants.

4. NOT_FOUND_OR_NEEDS_MANUAL_REVIEW
Définition
Aucune correspondance trouvée dans la base européenne pour au moins une substance active. Cela peut venir de :

une orthographe différente,

un nom commercial,

un vieux nom,

un sel, un complexe,

une substance qui n’existe pas dans la base UE (ex: uniquement utilisée en Tunisie),

ou un problème de normalisation.

Implication
Statut UE : inconnu par manque de correspondance.

Risque : inconnu, potentiellement élevé.

Action :

C’est la cible principale de ta revue manuelle.

Tu dois :

chercher le nom correct de la substance,

vérifier si elle existe sous un autre nom dans la base UE,

éventuellement ajouter un synonyme dans ton dictionnaire de mapping.

C’est cette catégorie qui explique le “nombre important de lignes à vérifier manuellement”.

5. API_ERROR
Définition
La requête API vers l’API UE a échoué (500, 502, 503, 504, timeout, etc.), donc le statut n’a pas pu être déterminé pour cette substance dans ce passage.

Implication
Statut UE : inconnu à cause d’un problème technique, pas d’un problème de fond.

Risque : techniquement faible, mais crée des incertitudes artificielles.

Action :

Relancer le script (le retry est déjà implémenté).

En cas de récurrence, vérifier :

connexion,

quota d’appels,

stabilité de l’API.

Si tu as la base locale, tu peux basculer en mode hors ligne pour éviter ce problème.

6. CHECK_INCOMPLETE_API_ERROR
Définition
Au moins une substance du produit a généré une erreur API, donc le jugement global sur le produit est incomplet.

Implication
Statut UE : incomplet.

Action :

Revoir avec la base locale,

ou rejouer le script après correction réseau / API.

7. NO_SUBSTANCE
Définition
La colonne “Substance Active” est vide, ND, ou ne contient aucune substance détectable.

Implication
Statut UE : non applicable.

Action :

Vérifier la qualité du CSV d’entrée,
-éventuellement exclure ces lignes de l’analyse.

8. MANUAL_REVIEW (éventuel)
Dans certains cas, tu peux avoir un statut générique “MANUAL_REVIEW” quand rien ne correspond clairement.

Implication
Statut UE : indéterminé.

Action :

Revue manuelle obligatoire.

Comment ces jugements impactent ta revue manuelle
Concrètement, ton “nombre important de lignes à vérifier manuellement” vient principalement de :

NOT_FOUND_OR_NEEDS_MANUAL_REVIEW : le gros volume,

FOUND_UNKNOWN_STATUS : un volume plus faible mais critique,

API_ERROR / CHECK_INCOMPLETE_API_ERROR : si tu n’utilises pas la base locale.

Les autres statuts sont déjà “clairs” et ne nécessitent pas de revue manuelle UE.
-----------------------------------
-----------------------------------

1. Explication des décisions (review_decision)
Dans manual_review_queue.csv, tu as une colonne review_decision qui indique le statut de chaque substance unitaire. Les valeurs possibles sont :

auto_mapped
La substance a été automatiquement réutilisée à partir d’un mapping déjà validé précédemment (manual_mapping.csv).

Pas de nouvelle recherche nécessaire.

review_match_name contient déjà le nom UE retenu.

auto_accept_high_confidence
Le fuzzy matching a trouvé un candidat UE avec un score très élevé (>= SCORE_THRESHOLD_ACCEPT, par défaut 95).

On considère que c’est une correspondance quasi certaine.

Le nom UE est pré-rempli dans review_match_name.

Tu peux quand même vérifier, mais normalement tu acceptes.

review_accept_high_score
Le score est bon mais pas excellent (entre SCORE_THRESHOLD_REVIEW et SCORE_THRESHOLD_ACCEPT, par exemple 75–94).

Le script propose de l’accepter, mais tu dois confirmer manuellement.

Dans Excel/LibreOffice, tu changes review_decision en accept si tu valides.

review
Score faible ou moyen, ou plusieurs candidats plausibles.

Revue manuelle obligatoire.

Tu regardes les colonnes candidate_1, candidate_2, … avec leurs scores et statuts UE.

Tu décides :

accept : tu valides un candidat (tu remplis review_match_name avec le nom UE choisi),

reject : tu rejettes tous les candidats (la substance n’est pas trouvée / pas pertinente),

needs_research : tu as besoin de chercher ailleurs (internet, base nationale, documentation).

needs_research
Aucune proposition pertinente ou aucune candidate trouvée.

Tu dois faire une recherche externe (base nationale, documentation technique, fabricant, etc.).

Si tu trouves un nom UE, tu le mets dans review_match_name et tu changes review_decision en accept.

Si tu ne trouves rien, tu laisses needs_research ou tu mets reject.

Dans le script de réinjection, on va traiter ces décisions ainsi :

auto_mapped, auto_accept_high_confidence, accept → substance considérée comme matchée, on utilise review_match_name.

reject, needs_research → substance non résolue, on garde un statut spécial dans le dataset clean.
