# Écran — Trésorerie : grille des cotisations

Sources : CDC 4.4.3, 4.4.7, 3.3 (tableaux larges), matrice 2.4. Composants : `DataTable` variante grille, `docs/lot0/design-system.md` 2.6 et 3.3.

## 1. Objectif

Voir, pour un type de cotisation et une année, qui a payé quel mois, en reproduisant les fichiers de suivi que le club tient aujourd'hui — lisible sur un téléphone de 360 px.

## 2. Accès

Route `/tresorerie/grille`. Entrée de barre latérale dédiée « Trésorerie › Grille des cotisations » (4.4.7).

| Rôle | Accès |
| --- | --- |
| Trésorier, Trésorier adjoint | Lecture de toutes les lignes ; depuis le détail d'une cellule : « Enregistrer un paiement » ; export CSV ; import CSV (modale « Importer les cotisations », `tresorerie-import-cotisations.md`) |
| Président, Vice-président | Lecture de toutes les lignes ; export CSV |
| Joueur (tout rôle sans accès ci-dessus) | Pas d'accès à cette page ; sa propre ligne est dans « Mon profil » (4.4.7) |

La grille ne se modifie jamais directement : toute écriture passe par un paiement (règle de répartition 4.4.3).

## 3. Structure de la page

**En-tête** : titre « Grille des cotisations » ; contexte « {nom du club} · {année} ». Actions secondaires : (Trés., Adj.) « Importer (CSV) », puis « Exporter (CSV) ». Pas d'action principale (page de consultation).

1. **Barre de sélection** (collante sous l'en-tête au défilement vertical) :
   - « Type » : puces défilantes horizontalement, une par type actif (+ puce « Types archivés » qui ouvre un menu). Type par défaut : le premier type mensuel obligatoire.
   - « Année » : sélecteur « ‹ {année} › » (boutons 40 px « Année précédente » / « Année suivante »).
   - Recherche « Rechercher un joueur » (36 px).
   - Filtre segmenté : « Tous » / « Avec impayés ».
2. **Légende** (une ligne, 13 px) : pastilles « Payé », « Partiel », « Impayé échu », « À venir » (couleurs design-system 2.6). Rappel : « Montants en {devise}. »
3. **Grille** — `DataTable` `variant="grid"`, un tableau par type (4.4.7) :
   - Colonne figée « Joueur » : avatar 24 px, nom (deux lignes au plus, pas de troncature), n°.
   - Colonnes « janv. », « févr. », « mars », « avr. », « mai », « juin », « juil. », « août », « sept. », « oct. », « nov. », « déc. », puis « Total ».
   - Cellule : montant affecté au mois (tabular-nums) sur fond d'état ; « — » pour à venir ; « 0 » pour impayé échu. Un paiement anticipé apparaît étalé sur plusieurs mois (4.4.3), selon l'affectation calculée par l'API.
   - Type libre : aucune cellule rouge (une cotisation libre ne crée jamais de dette) ; les mois sans versement affichent « — ».
   - *Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrée 6) — non livrable au MVP* : ligne de pied « Total du mois » (collante en bas du cadre), puis total annuel.
   - Pagination : 50 lignes par page. Tri par défaut : nom ; tri possible sur « Total ».
   - Au chargement de l'année en cours, le cadre défile pour montrer le mois courant.
   - Clic sur une cellule → modale « Détail du mois ». Clic sur le nom → modale « Situation financière » (définie dans `tresorerie-tableau-de-bord.md` §4.3).

Footer.

## 4. Modales

### 4.1 « Détail du mois » — taille `md`

- En-tête : « {mois année} — {nom du joueur} » ; sous-titre : nom du type.
- Corps : « Montant dû : {montant} », « Montant affecté : {montant} », `StatusBadge` d'état (Payé / Partiel / Impayé échu / À venir), liste des paiements ayant alimenté ce mois : date, montant total du paiement, part affectée à ce mois, n° de reçu, mode. Aide pour un paiement étalé : « Paiement de {montant} du {date}, réparti de {mois début} à {mois fin}. »
- Pied : « Fermer » / (Trés., Adj.) « Enregistrer un paiement » → modale « Enregistrer un paiement » au niveau 2, joueur et type préremplis. Après enregistrement, la grille est mise à jour sans rechargement.

### 4.2 Export CSV

Pas de modale : le bouton passe en état `loading` puis télécharge le fichier du type et de l'année affichés. Nom du fichier : `grille-{type}-{annee}.csv` (généré à partir des données, aucun nom de club en dur). Toast « Export téléchargé. »

## 5. États

| Situation | Affichage |
| --- | --- |
| Chargement | Barre de sélection affichée, grille en squelette (8 lignes × 13 colonnes grises) |
| Aucun type de cotisation dans le club | EmptyState « Aucun type de cotisation. » + précision « Les types se créent depuis le tableau de bord de la trésorerie. » + (Pdt, Trés.) bouton « Aller à la trésorerie » |
| Aucun joueur rattaché au type | « Aucun joueur n'est rattaché à ce type de cotisation. » |
| Recherche sans résultat | « Aucun joueur ne correspond à « {saisie} ». » + « Effacer la recherche » |
| Filtre « Avec impayés » vide | « Aucun impayé pour ce type en {année}. » |
| Année sans données | Grille affichée, cellules « — » ; aucune erreur |
| Erreur | « Impossible de charger la grille. » + « Réessayer » |

## 6. Mobile (360 px) et ordinateur

- **360 px** : barre de sélection sur deux lignes (puces de type ; puis année + filtre), recherche sous la barre. Cadre de la grille haut de `100dvh − en-tête − barre`, défilement horizontal et vertical **dans le cadre uniquement**, colonne « Joueur » figée de 120 px, colonnes de mois de 56 px, « Total » de 72 px. Au premier affichage, aide discrète refermable : « Faites défiler vers la droite pour voir les autres mois, ou tournez votre téléphone. »
- **Paysage mobile** : même grille, environ 8 mois visibles.
- **≥ 1024 px** : colonne « Joueur » de 200 px, les 12 mois et le total visibles sans défilement horizontal à partir de 1280 px.

## 7. Décisions par défaut et points ouverts

- **10.2 n° 4** : l'état « Impayé échu » est calculé par l'API à partir de l'échéance (le 10 par défaut, sans tolérance) ; l'interface n'applique aucune règle.
- **Point ouvert — accès du Vice-président** : le 4.4.7 réserve le menu au Trésorier, à l'adjoint et au Président, alors que la matrice 2.4 donne la lecture au VP. **Défaut appliqué : la matrice 2.4 fait foi, le VP voit la grille en lecture.** À confirmer.
- **Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrée 6)** : ligne « Total du mois » (non demandée par le 4.4.7, aide au rapprochement de caisse).
- **Proposition** : pagination à 50 lignes pour garder un club de 40 joueurs sur une seule page tout en respectant 3.3.
- **Proposition** : correspondance des états de cellule avec les couleurs de statut (design-system 2.6), le « Partiel » en orange.
