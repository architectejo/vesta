# Écran — Trésorerie : modale « Importer les cotisations »

Sources : CDC 4.4.8 (import historique), 4.4.3 (répartition), 4.4.7 (grille), 7.2 (actions sensibles : confirmation explicite), 3 (charte), matrice 2.4. Tâche 2.6 du Lot 2.
Composants : `Modal`, `ConfirmDialog` (variante action sensible), `Banner`, `Button`, `SegmentedControl`, `StatusBadge`, `DataTable` (`variant="grid"` et liste), `EmptyState`, `Loader`, `useToast` (design system).
Référence de famille : `routes/club/ImportPlayersModal.tsx` (sélection de fichier, rapport) et `routes/treasury/RecordPaymentModal.tsx` (enchaînement modale → modale de confirmation).

**Aucune règle métier dans l'interface.** L'analyse du fichier, la recherche des joueurs, les paiements et montants dus prévus, les soldes : tout vient de l'API. L'écran affiche le rapport tel quel.

## 1. Objectif

Permettre au Trésorier de reprendre lui-même, lui-même, après confirmation, les fichiers de suivi du club (une ligne par joueur, une colonne par mois) pour un type de cotisation et une année, après avoir vu l'aperçu de la grille résultante.

## 2. Accès

| Rôle | Accès |
| --- | --- |
| Trésorier, Trésorier adjoint | Bouton « Importer (CSV) » sur la grille ; modale complète ; téléchargement du rapport |
| Tout autre rôle (Président et VP compris) | Bouton absent. L'API refuse de toute façon (`CanImportContributions`) |

Condition d'affichage du bouton : `capabilities.can_record_payments === true` (même ensemble de rôles que `CONTRIBUTION_IMPORTERS` côté API — voir §11, point 1).

## 3. Entrée

Page `GrilleCotisationsPage.tsx`, en-tête, à gauche de « Exporter (CSV) » : bouton `variant="secondary"` `size="sm"` **« Importer (CSV) »**. Pas d'action principale sur la page (page de consultation, inchangé).
À 360 px : les deux boutons sur une ligne sous le titre, alignés à gauche, 36 px de haut.

Au clic : modale ouverte avec le type et l'année actuellement affichés dans la grille préremplis (si le type affiché n'est pas importable, champ « Type » vide).

## 4. Modale — structure générale

- `Modal` niveau 1, taille `xl` (desktop) ; **plein écran** à moins de 640 px ; pied collant, boutons toujours visibles.
- Titre : « Importer les cotisations ». Sous le titre, ligne d'étape 13 px, couleur `text-muted` : « Étape 1 sur 3 · Fichier » / « Étape 2 sur 3 · Aperçu » / « Étape 3 sur 3 · Résultat ».
- Fermeture : croix, Échap, clic extérieur. Confirmation (`isDirty`) dès qu'un fichier est choisi, aux étapes 1 et 2 : « Abandonner l'import ? Le fichier choisi et l'aperçu seront perdus. » — boutons « Continuer l'import » / « Abandonner ». Pendant l'import définitif (`isSubmitting`) : fermeture impossible. À l'étape 3 : aucune confirmation.
- Une seule action principale par étape (bouton primaire du pied).

## 5. Étape 1 — Fichier

Champs, dans l'ordre :

1. **Type de cotisation** (obligatoire) — `<select>` natif (autorisé : ce n'est pas un joueur), 40 px. Options : types **actifs** et importables, c'est-à-dire `is_free === true` ou `periodicity === "monthly"` (filtre d'affichage calqué sur le refus de l'API ; l'API reste juge). Libellé d'option : « {nom} — {montant} {devise} » ou « {nom} — libre ». Aide sous le champ, 13 px : « Seuls les types mensuels et les cotisations libres peuvent être importés. »
2. **Année** (obligatoire) — sélecteur « ‹ {année} › » identique à la page (boutons 40 px « Année précédente » / « Année suivante »), borné de 2000 à l'année en cours (le bouton suivant est désactivé sur l'année en cours).
3. **Fichier CSV** (obligatoire) — zone de dépôt 44 px minimum : « Choisir un fichier CSV » ; `accept=".csv,text/csv"`. Une fois choisi : « {nom du fichier} · {taille} Ko » + lien « Changer ».
4. **Aide au format** (repliable, fermée par défaut, libellé « Format attendu ») :
   « Une ligne par joueur. Une colonne « email » ou « nom » (ou les deux), puis une colonne par mois (« janv. », « févr. »… ou « 01/2026 »). Dans une cellule : un montant = paiement de ce montant ; « ok » = mois payé au montant plein ; vide, « - » ou « 0 » = rien payé. Les autres colonnes (« N° », « Total ») sont ignorées. Fichier enregistré en UTF-8, 500 lignes au plus, 10 Mo au plus. »
   Lien « Télécharger un modèle vide » : fichier généré côté navigateur, en-tête seul `email;nom;janv.;févr.;mars;avr.;mai;juin;juil.;août;sept.;oct.;nov.;déc.`, nom `modele-import-cotisations.csv`. Aucune ligne d'exemple (voir §11, point 4).

Pied : « Annuler » / **« Voir l'aperçu »** (désactivé tant que type, année et fichier ne sont pas renseignés ; en cours : « Analyse du fichier… »).

Action : `POST /treasury/contribution-imports/preview/` en multipart (`contribution_type_id`, `year`, `file`). Aucune écriture côté serveur.

Erreurs de l'étape 1 (bandeau `Banner variant="danger"` en haut du corps, texte `detail` de l'API tel quel) : fichier non UTF-8, en-tête introuvable, mois d'une autre année, mois en double, plus de 500 lignes, plus de 10 Mo, type archivé, type non importable, année invalide. Le formulaire reste rempli ; « Voir l'aperçu » redevient cliquable.

Toute modification du type, de l'année ou du fichier **après** un aperçu annule cet aperçu (retour à l'étape 1).

## 6. Étape 2 — Aperçu

Ordre du corps :

1. Lien discret en haut : « ‹ Modifier le type, l'année ou le fichier » (retour à l'étape 1, champs conservés).
2. **Ligne de contexte** : « {type} · {année} · {nom du fichier} ».
3. **Carte « Résumé »** — grille de chiffres 2 colonnes à 360 px, 4 à partir de 768 px (chiffre 18 px tabular-nums, libellé 13 px) :
   - « Lignes lues » : `summary.rows_total`
   - « Lignes prêtes » : `summary.rows_succeeded` (vert)
   - « Lignes en échec » : `summary.rows_failed` (rouge si > 0)
   - « Paiements à créer » : `summary.payments_count` · « {payments_total} {devise} »
   - « Montants dus à créer » : `summary.dues_count`
   - « Déjà importés (ignorés) » : `summary.already_imported_count` — affiché seulement si > 0
4. **Bandeaux d'information** (`Banner variant="info"`, seulement si non vides) :
   - « Colonnes ignorées : {liste}. »
   - « Lignes ignorées (titre ou ligne vide) : {numéros}. »
5. **Rappel avant import** (`Banner variant="warning"`, toujours) : « Les paiements importés seront enregistrés comme validés, avec un reçu. Ils ne pourront plus être supprimés : une erreur se corrige par une annulation. »
6. **Détail des lignes** — `SegmentedControl` : « En échec ({n}) » · « Prêtes ({n}) » · « Grille ». Onglet par défaut : « En échec » s'il y en a, sinon « Prêtes ». Au-dessus de la liste, si plus de 30 lignes : recherche « Rechercher un joueur » (36 px, filtre local sur `identity` et nom du joueur).
   - **En échec** : liste, 20 premières lignes puis « Voir plus ». Élément : « Ligne {line_number} · {identity} », `StatusBadge` rouge « Échec », puis chaque message de `errors` (14 px, `status-danger-fg`). Pas de clic (tout est affiché). État vide : « Aucune ligne en échec. »
   - **Prêtes** : liste, 20 premières lignes puis « Voir plus ». Élément (hauteur ≥ 44 px, cliquable) : avatar 24 px, nom du joueur (`player`) ou `identity`, sous-ligne 13 px « {nb paiements} paiement(s) · {montant} {devise} · solde {balance_before} → {balance_after} » ; `StatusBadge` vert « Prête », ou orange « À vérifier » si `warnings` n'est pas vide. Clic → modale « Détail de la ligne » (§6.1). État vide : « Aucune ligne n'est prête à être importée. »
   - **Grille** : aperçu de la grille résultante (CDC 4.4.8) — `DataTable variant="grid"` des lignes prêtes, mêmes colonnes, cellules, couleurs et légende que la page grille (`rows[].cells`, `rows[].total`, en-têtes `months[].label`). Mêmes largeurs et défilement que `tresorerie-grille-cotisations.md` §6. Aide 13 px au-dessus : « Grille telle qu'elle sera après l'import. La répartition suit la règle du club : les mois impayés les plus anciens sont couverts en premier. »

Pied : « Annuler » / **« Importer »** (libellé complet : « Importer {rows_succeeded} ligne(s) »).
Bouton désactivé si `rows_succeeded === 0` ou si `payments_count + dues_count === 0`, avec, à sa place dans le corps, `Banner variant="info"` : « Rien à importer : aucune ligne ne crée de paiement ni de montant dû. » (proposition, §11 point 6).

Clic sur « Importer » → modale de confirmation (§7). Le fichier, le type et l'année envoyés à l'import sont **exactement** ceux de l'aperçu (même objet `File` conservé en mémoire).

### 6.1 « Détail de la ligne » — `Modal` niveau 2, taille `md`, lecture seule

- Titre : « Ligne {line_number} — {nom} ».
- Section « Paiements qui seront créés » : tableau court — « Mois » · « Date de valeur » (`paid_on`, JJ/MM/AAAA) · « Montant » · « Origine » (« Montant du fichier » si `origin="amount"`, « « ok » non couvert » si `origin="ok"`). Vide : « Aucun paiement à créer pour cette ligne. »
- Section « Déjà importés (ignorés) » : même tableau sur `already_imported`, affichée seulement si non vide.
- Section « Montants dus qui seront créés » : « Mois » · « Montant » · « Échéance ». Vide : « Aucun montant dû à créer. »
- Section « Solde » : « Avant l'import : {balance_before} {devise} » · « Après l'import : {balance_after} {devise} » + `StatusBadge` de `player_status_after`.
- Section « À vérifier » (si `warnings`) : chaque message tel quel, sur fond orange clair.
- Pied : « Fermer ».

## 7. Confirmation simple (position provisoire)

Modale de confirmation niveau 2 (`ConfirmDialog`, variante action sensible), par-dessus la modale. Position provisoire : l'import historique se valide par une confirmation simple, sans champ ; à confirmer par le client. L'auteur est écrit au journal d'activité.

- Titre : « Importer cet historique ? ».
- Description : « Importer {payments_count} paiement(s) pour {payments_total} {devise} et {dues_count} montant(s) dû(s) — {type}, {année}. »
- Boutons : « Annuler » / « Importer » ; libellé de chargement : « Import en cours… ».
- Appel : `POST /treasury/contribution-imports/` en multipart (`contribution_type_id`, `year`, `file`) ; plus de paramètre `pin`.

Pendant l'appel : la modale de confirmation affiche « Import en cours… », et le corps de la modale niveau 1 affiche un `Loader` avec « Import en cours. Cela peut prendre jusqu'à une minute : ne fermez pas cette fenêtre. » (l'import est synchrone, §11 point 5).

Erreurs :
- **Toute autre erreur** (fichier devenu invalide, type archivé entre-temps, écritures gelées, droits retirés) : la modale de confirmation se ferme, retour à l'étape 2 avec `Banner variant="danger"` = `detail` de l'API.
- **Réseau coupé / délai dépassé** : retour à l'étape 2 avec `Banner variant="warning"` : « La connexion a été interrompue : l'import a peut-être été enregistré. Relancez l'aperçu : les paiements déjà importés y apparaîtront comme « déjà importés » et ne seront pas recréés. » + bouton secondaire « Relancer l'aperçu ».

## 8. Étape 3 — Résultat

Réponse 201 : même format de rapport, `is_preview=false`, `import_batch_id` renseigné.

- Bandeau `Banner variant="success"` : « Import terminé. »
- Carte « Résumé » (même disposition qu'à l'étape 2) : « Lignes importées » (`rows_succeeded`), « Paiements créés » (`payments_count` · `payments_total` {devise}), « Montants dus créés » (`dues_count`), « Déjà importés (ignorés) » si > 0, « Lignes en échec » (`rows_failed`).
- Si `rows_failed > 0` :
  - `Banner variant="warning"` : « {n} ligne(s) n'ont pas été importées. Corrigez-les dans le fichier puis relancez un import : les lignes déjà importées ne seront pas recréées. »
  - Liste des lignes en échec (même rendu qu'à l'étape 2, 20 + « Voir plus »). Le résultat peut différer de l'aperçu : afficher ce que renvoie l'import, pas l'aperçu.
  - Bouton secondaire **« Télécharger le rapport (CSV) »** : `GET /clubs/imports/{import_batch_id}/report/` par le client authentifié (téléchargement en blob, jamais un lien direct), nom proposé `rapport-import-cotisations-{annee}.csv`. En cours : « Téléchargement… ». Erreur : toast « Impossible de télécharger le rapport. Réessayez. »
- Pied : **« Fermer »** (seul bouton).

À la fermeture : invalidation des requêtes de la grille (type et année), du tableau de bord trésorerie et des soldes ; toast « Import terminé : {payments_count} paiement(s) enregistré(s). ». La grille affiche l'année importée.

## 9. États

| Situation | Affichage |
| --- | --- |
| Chargement des types à l'ouverture | Champ « Type » en squelette 40 px ; autres champs visibles |
| Aucun type importable | `EmptyState` « Aucun type de cotisation ne peut être importé. » + « Seuls les types actifs, mensuels ou libres, peuvent être importés. » ; pied : « Fermer » |
| Erreur de chargement des types | « Impossible de charger les types de cotisation. » + « Réessayer » |
| Analyse du fichier (aperçu) | Bouton « Analyse du fichier… » + `Loader` dans le corps, champs désactivés |
| Aperçu : tout en échec | Onglet « En échec » ouvert, bouton « Importer » désactivé |
| Import en cours | §7 |
| Hors connexion | `Banner variant="warning"` « Vous êtes hors connexion. L'aperçu et l'import nécessitent une connexion. » ; boutons primaires désactivés |
| Erreur serveur inattendue | « Une erreur est survenue de notre côté. Réessayez dans un instant. » |

## 10. Mobile (360 px) et ordinateur

- **360 px** : modale plein écran ; en-tête collant (titre + étape) ; pied collant (Annuler à gauche, action principale à droite, 40 px) ; zones cliquables ≥ 44 px ; texte 14 px, chiffres du résumé 18 px, aucun titre au-delà de 20 px. Les listes sont des cartes empilées ; l'onglet « Grille » défile dans son cadre uniquement (colonne joueur figée 120 px, mois 56 px), avec l'aide « Faites défiler vers la droite pour voir les autres mois, ou tournez votre téléphone. ».
- **≥ 768 px** : `Modal` `xl` centrée, hauteur max 90 vh, corps défilant ; résumé sur 4 colonnes ; listes en tableau (« Ligne » · « Joueur » · « Paiements » · « Montant » · « Solde après » · « État »).
- Contraste : états par `StatusBadge` (texte + couleur, jamais la couleur seule), lisible en plein soleil dans les trois thèmes.
- Marque blanche : aucun nom de club dans la modale ni dans les noms de fichiers.

## 11. Décisions par défaut et points ouverts

1. **Capacité d'affichage** : l'API n'expose pas de `can_import_contributions` ; le bouton s'appuie sur `can_record_payments`, identique aujourd'hui (`CONTRIBUTION_IMPORTERS = PAYMENT_RECORDERS`). Si ces ensembles divergent un jour, ajouter la capacité dédiée.
2. **Aperçu obligatoire** : imposé par l'interface (le bouton « Importer » n'existe qu'à l'étape 2). L'API d'import ne vérifie pas qu'un aperçu a eu lieu.
3. **URL du rapport** : la réponse d'import donne `import_batch_id` mais pas l'URL ; l'interface la construit (`/clubs/imports/{id}/report/`, vue authentifiée existante, permission selon le type du lot).
4. **Annexe C, partie 4 (format des cotisations) jamais rédigée** (CDC 10.1 : « modèles d'import… avec exemples »). Le modèle proposé ici n'a qu'un en-tête ; l'annexe doit être complétée à partir de l'en-tête de `services.py` (section « Import des cotisations historiques CSV »).
5. **Import synchrone** (jusqu'à 500 lignes, environ 0,1 s par paiement) : risque de délai dépassé sur l'hébergement et le réseau mobile ; le message du §7 s'appuie sur le fait qu'un réimport ne crée pas de doublon.
6. **Proposition** : désactiver « Importer » quand l'aperçu ne prévoit ni paiement ni montant dû.
7. **Q17 (schema-treasury, provisoire)** : l'import crée les montants dus manquants ; l'aperçu les montre explicitement (« Montants dus à créer ») pour que le Trésorier le voie avant de confirmer.
