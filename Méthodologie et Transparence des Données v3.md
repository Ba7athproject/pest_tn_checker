Méthodologie et Transparence des Données
Cette enquête repose sur une méthodologie de datajournalisme rigoureuse visant à croiser le registre national des pesticides avec les données toxicologiques et réglementaires européennes les plus récentes (données arrêtées en juin 2026).

1. Le Pipeline Ba7ath V3
L'analyse a été effectuée via un pipeline automatisé conçu pour éliminer les biais de saisie et les erreurs d'interprétation humaine :

Gatekeeper (Filtre) : Un moteur de nettoyage textuel a été utilisé pour isoler les substances actives chimiques des adjuvants, phéromones et produits de biocontrôle, garantissant que seuls les pesticides à risque potentiel soient soumis aux tests européens.

Matcher (Réconciliation) : Chaque substance active a été comparée à la base de données officielle de l'Union Européenne (EU Pesticide Database) via des algorithmes de recherche floue (fuzzy matching), permettant de lier les noms commerciaux tunisiens aux nomenclatures internationales (N° CAS).

Analyse Toxicologique (EFSA) : Les substances identifiées ont été croisées avec la base OpenFoodTox 3.0 de l'EFSA. Cette base contient les études toxicologiques brutes.

2. Algorithme de Dangerosité
Nous avons développé un Score de Dangerosité (0 à 10) pour qualifier le risque :

Le score est calculé en fonction de la Dose Journalière Admissible (ADI) et de la Dose de Référence Aiguë (ARfD).

Une molécule recevant un score de 10 présente une toxicité aiguë ou chronique extrêmement élevée (seuil très bas de dose admissible).

3. Sources de données
L'intégralité des données source provient d'institutions publiques garantissant leur fiabilité :

Données locales : Registre officiel des produits phytosanitaires (Autorité nationale).

Données réglementaires UE : EU Pesticide Database (Commission européenne).

Données toxicologiques : OpenFoodTox 3.0 (Agence européenne de sécurité des aliments - EFSA).

4. Limites de l'étude
Bien que cette méthode permette une analyse de grande échelle, elle est soumise aux limites suivantes :

La base OpenFoodTox couvre la majorité des pesticides, mais certaines molécules industrielles rares peuvent être absentes.

Les erreurs de frappe dans le registre national initial peuvent parfois compliquer l'appariement automatique ; nous avons utilisé un seuil de confiance de 85 % pour valider les correspondances.