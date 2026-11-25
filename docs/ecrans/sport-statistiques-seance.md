# Écran — Statistiques des séances d'entraînement et tests de performance

Sources : CDC 3 (charte), 4.2 (carte, fiche détaillée, radar), 4.7 (pointage, retard, absence excusée, verrouillage), 4.10 (évaluations : évaluateurs, 48 h, grille, moyenne de plusieurs évaluateurs, commentaire visible ou non), 4.12 et CLAUDE.md règle 11 (santé), 5 (journal), 6.5 (pas de WebSocket), 6.6 (hors connexion), matrice 2.4 (lignes « Séances », « Séances et matchs : pointage », « Évaluation des performances »), 10.2 n° 9, 16, 25, 10.3 n° 179. Demande du client : `remarques.md` l. 85, décidée le 15/11/2026, précisée le même jour (bloc « Notes du Coach »). Écrans liés : `sport-seance.md` (vue « Bilan »), `sport-espace-coach.md` §4.3 (modale « Séance ») et §4.6 (« Évaluer les joueurs »), `club-carte-joueur.md` (radar, point ouvert 12), `club-tableau-de-bord-bureau.md` §6 (composants de graphiques).

Composants : `Modal`, `Tabs`, `SegmentedControl`, `StatusBadge`, `Avatar`, `DataTable`, `NumberField`, `PlayerSearch`, `Checkbox`, `Loader`, `Skeleton`, `EmptyState`, `ConfirmDialog`, `SyncIndicator` ; **nouveaux** : `KpiTile`, `LineChart`, `BarChart`, `ChartCard`, `Stopwatch` (§7.4), définis au §6 de `club-tableau-de-bord-bureau.md` pour les graphiques.

Ce document a trois parties :

- **Partie A — Statistiques d'une séance** : présence et « Notes du Coach ». Demandées explicitement ; calculées à partir de données qui existent déjà (pointages, évaluations).
- **Partie B — Évolution d'une séance à l'autre** : courbes du taux de présence et de la note moyenne.
- **Partie C — Tests de performance** (chrono, vitesse, répétitions…). **Entièrement NOUVEAU** (circuit 9.4) : aucun modèle de mesure n'existe dans le CDC.

> **NOUVEAU par rapport au CDC (à valider)** : le CDC prévoit seulement, dans la vue « Bilan » d'une séance, le taux de présence, les retards et les absences excusées (`sport-seance.md` §3.3), et dans la fiche du joueur la courbe de ses notes (4.2). Sont nouveaux : le bloc « Notes du Coach » agrégé par séance, l'évolution d'équipe, la page « Entraînements » et toute la partie C.

---

# PARTIE A — Statistiques d'une séance

## A1. Objectif

Après la séance, le Coach (et le bureau) voit en un écran : combien étaient là, qui était en retard ou excusé, comment l'équipe a été notée, qui s'est distingué et qui a décroché.

## A2. Où elles s'affichent

1. **Page Séance › vue « Bilan »** (`sport-seance.md` §3.3) : les sections « Présence » et « Notes du Coach » ci-dessous remplacent le point 1 « Présences » actuel et s'ajoutent au point 4 « Évaluations ». Les sections « Incidents », « Blessures » restent inchangées.
2. **Modale « Séance »** (détail, `sport-espace-coach.md` §4.3) : nouvel onglet **« Statistiques »**, placé après « Présences ». Contenu identique, en lecture seule.
3. **Page « Entraînements »** (partie B) : chaque ligne de séance ouvre cette même modale.

Aucune page n'est créée pour une séance isolée : les statistiques sont une lecture de la séance existante.

## A3. Accès et visibilité

| Bloc | Coach, Assistant, Président, VP | Directeur sportif | Capitaine, Médecin, autres joueurs | Le joueur pour lui-même |
| --- | --- | --- | --- | --- |
| Présence (compteurs, taux, listes nominatives) | Oui | Oui | Oui : la ligne « Séances et matchs : pointage » leur donne « L » (matrice 2.4) | Oui |
| Notes du Coach : moyenne, meilleures et plus faibles notes, joueurs évalués | Oui | Oui, lecture seule (« L ») | **Non** | **Sa note seulement** (« P ») |
| Détail des notes par joueur (modale A5.3) | Tous les joueurs, tous les critères, tous les commentaires (comportement actuel de l'API `events/{id}/evaluations/`) | Idem, lecture | **Non** | Sa ligne ; commentaire seulement s'il est marqué « visible par le joueur » (4.10) |

Raison du « Non » pour les coéquipiers : la matrice 2.4 donne « P » au joueur sur les évaluations. Une moyenne d'équipe, un « meilleur » et un « plus faible » sont calculés à partir des notes des autres ; les montrer à un joueur reviendrait à exposer ces notes (en particulier les plus faibles, avec le nom). **Position prudente**, voir question C-Q1.

**Filtrage par l'API** : l'endpoint ne renvoie le bloc « Notes du Coach » qu'aux rôles autorisés (`evaluations: null` pour les autres, `my_evaluation` pour le joueur) ; l'interface ne cache rien elle-même.

## A4. Structure (vue « Bilan » et onglet « Statistiques »)

### A4.1 Carte « Présence »

1. **Tuiles** (`KpiTile`, grille 2 × 3 à 360 px, 6 en ligne à ≥ 1024 px) :
   - « Taux de présence » : « 72 % » (valeur principale, 20 px, chiffres tabulaires) ; sous-ligne « {n} sur {m} joueurs attendus » ;
   - « Présents » {n} (pastille verte) ;
   - « En retard » {n} (pastille rouge si le club compte le retard comme absence, orange sinon — texte et famille servis par l'API, 10.2 n° 25) ;
   - « Absents » {n} (pastille rouge) — non pointés ;
   - « Excusés » {n} (pastille grise) ;
   - « Écart avec la moyenne » : « +6 points par rapport aux 10 dernières séances » / « −4 points… » (texte, sans flèche colorée seule). Masquée s'il y a moins de 3 séances antérieures.
2. **Barre de répartition** : une barre horizontale 100 % empilée (`StackedBar`, 16 px de haut) Présents / En retard / Excusés / Absents, chaque segment avec son libellé et son nombre en légende sous la barre (jamais la couleur seule).
3. **Listes** (dépliables, repliées par défaut à 360 px) : « En retard ({n}) » (avatar 32, nom, heure d'arrivée) ; « Excusés ({n}) » (avatar, nom, motif « Blessé / Voyage / Autre » — jamais de détail médical) ; « Absents ({n}) » (avatar, nom). 5 lignes puis « Voir plus » (3.3).
4. Clic sur une tuile → la liste correspondante se déplie et défile à l'écran (pas de modale supplémentaire).

**Définitions (calculées par l'API, jamais par l'interface)** :

- **Joueurs attendus** : les joueurs du club ayant une adhésion active à la date de la séance (statut « Inscrit » ; les joueurs partis et ceux arrivés après la date sont exclus). Un joueur bloqué (dette, suspension, inaptitude) **est** attendu : le pointage est une présence. Le statut « En attente d'adhésion » : exclu (proposition, question C-Q2).
- **Taux de présence** = présents ÷ attendus, arrondi à l'unité. Un retardataire compte comme absent si le club le décide (défaut, 10.2 n° 25), comme présent sinon. Une absence excusée **reste une absence** (4.7) : elle est au dénominateur et pas au numérateur.
- Les quatre compteurs font toujours la somme des attendus.

### A4.2 Carte « Notes du Coach » (rôles du tableau A3)

Titre : « Notes du Coach ». Contexte (13 px) : « Évaluations ouvertes encore {h} h » ou « Évaluations verrouillées depuis le {date} » (4.10, 48 h).

1. **Tuiles** :
   - « Note moyenne » : « 6,8 sur 10 » (virgule décimale) ; sous-ligne « Moyenne des notes globales retenues » ;
   - « Joueurs évalués » : « {n} sur {m} » où {m} = joueurs pointés à la séance (présents et retardataires : ceux que la saisie rapide liste, 4.10) ; barre de progression fine sous la valeur ;
   - « Écart avec la moyenne » : « +0,4 par rapport aux 10 dernières séances » (masquée sous 3 séances).
2. **« Meilleures notes »** : les 3 meilleures, ligne de 44 px : rang, avatar 32, « Prénom Nom », note « 8,5 » (16 px, gras). Ex æquo : même rang, tous affichés (au plus 5 lignes).
3. **« Notes les plus faibles »** : les 3 plus faibles, même ligne. Titre volontairement neutre : jamais « Les pires ».
4. **Répartition des notes** (facultative à 360 px, dépliable « Voir la répartition ») : `BarChart` vertical, 5 tranches (« 0 à 2 », « 2 à 4 », « 4 à 6 », « 6 à 8 », « 8 à 10 »), nombre de joueurs sur chaque barre.
5. Action de carte : bouton secondaire « Voir toutes les notes » → modale A5.3. Pour le Coach, l'Assistant, le Président et le VP pendant les 48 h : bouton principal « Évaluer les joueurs » (modale existante `sport-espace-coach.md` §4.6) si des joueurs restent à évaluer ; c'est l'unique action principale de la carte.

**Note retenue d'un joueur** : moyenne des notes globales de ses évaluateurs (4.10 « Plusieurs évaluateurs : la note retenue est la moyenne »), arrondie à 0,1. **Note moyenne de la séance** : moyenne des notes retenues des joueurs évalués (un joueur non évalué n'entre pas dans la moyenne et ne compte jamais comme 0).

**Vue du joueur** (rôle J sans autre rôle évaluateur) : la carte devient « Ma note » : « Votre note : 7,0 sur 10 » ; critères renseignés en dessous (« Technique 7 · Physique 6… ») ; commentaire si visible ; sinon « Vous n'avez pas encore été évalué pour cette séance. » Aucune moyenne d'équipe, aucun classement.

### A4.3 Carte « Mesures de la séance » (partie C)

Résumé des tests de performance réalisés pendant la séance : une ligne par test (« Sprint 30 m · 14 joueurs mesurés · meilleur temps 4,21 s »). Clic → modale C6.4. Action (Coach, Assistant, jour même et 48 h après) : « Mesurer » → modale C6.1. Vide : « Aucune mesure pendant cette séance. » + (Coach, Assistant) « Mesurer ».

### A4.4 Maquette 360 px (vue « Bilan »)

```
┌──────────────────────────────────────┐
│ Présence                              │ titre de carte 16 px/600
│ ┌──────────┐┌──────────┐┌──────────┐ │
│ │ 72 %     ││ 18       ││ 3        │ │ KpiTile 72 px de haut
│ │ Taux     ││ Présents ││ En retard│ │
│ └──────────┘└──────────┘└──────────┘ │
│ ┌──────────┐┌──────────┐┌──────────┐ │
│ │ 4 Absents││ 2 Excusés││ +6 points│ │
│ └──────────┘└──────────┘└──────────┘ │
│ ████████████▓▓░░░▒▒▒                  │ barre empilée
│ Présents 18 · Retard 3 · Excusés 2 · Absents 4 │
│ ▸ En retard (3)   ▸ Excusés (2)   ▸ Absents (4) │
├──────────────────────────────────────┤
│ Notes du Coach   Ouvertes encore 31 h │
│ [ 6,8 sur 10 ] [ 19 sur 21 évalués ]  │
│ Meilleures notes                      │
│ 1 (AV) Prénom Nom              8,5    │
│ 2 (AV) Prénom Nom              8,0    │
│ Notes les plus faibles                │
│ …                                     │
│ [Voir toutes les notes] [Évaluer les joueurs] │
├──────────────────────────────────────┤
│ Mesures de la séance        [Mesurer] │
└──────────────────────────────────────┘
```

À 360 px : tuiles en grille de 3 colonnes de 104 px (336 − 2 × 12 d'écart ÷ 3), libellés sur 2 lignes au plus, sans troncature. Si une police système déborde, la grille passe à 2 colonnes.

### A4.5 Ordinateur (≥ 1024 px)

Vue « Bilan » sous les deux colonnes Pointage/Terrains (`sport-seance.md` §6) : « Présence » et « Notes du Coach » côte à côte (6/6), « Mesures » en dessous, puis Incidents et Blessures.

## A5. Modales

### A5.1 Onglet « Statistiques » de la modale « Séance »

Contenu des cartes A4.1 à A4.3, en lecture seule (aucun bouton « Évaluer » ni « Mesurer » ; on passe par « Ouvrir la séance »).

Les listes de présence (retards, excusés, absents) se déplient dans la carte : pas de modale dédiée.

### A5.3 « Notes de la séance du {date} » — taille `lg` (plein écran mobile)

- En-tête : titre ; sous-titre « {n} joueurs évalués sur {m} · moyenne {6,8} sur 10 ».
- Barre : recherche « Nom ou numéro » ; tri (`SegmentedControl`) « Note » / « Nom ».
- `DataTable` (défilement horizontal dans son cadre, première colonne figée 140 px) : « Joueur » (avatar 24 + nom) · « Note » · « Technique » · « Physique » · « Tactique » · « Mental » · « Attitude » · « Évaluateurs » (nombre) · « Commentaire » (icône + « Voir », ouvre un panneau bas avec le texte et la mention « Visible par le joueur » / « Non visible par le joueur »). Critère non renseigné : « — ».
- Lignes « Non évalué » en bas, regroupées : « Pas encore évalués ({k}) » (avatar, nom).
- Pour le joueur (vue « P ») : la modale s'appelle « Ma note — séance du {date} » et ne contient que sa ligne.
- Pied : « Fermer ». Coach, Assistant, Président, VP pendant les 48 h : « Modifier les notes » (ouvre « Évaluer les joueurs »).

## A6. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Carte Présence | 6 tuiles squelettes + barre | Séance du jour, personne pointé : « Personne n'est encore pointé. » (tuiles à 0, taux « — ») | « Impossible de charger les statistiques. » + « Réessayer » |
| Notes du Coach | 2 tuiles + 3 lignes squelettes | « Aucune note pour cette séance. » + (évaluateurs, 48 h) « Évaluer les joueurs » ; après 48 h : « Aucune note n'a été saisie dans les 48 heures. » | Idem |
| Meilleures / plus faibles | — | Moins de 2 joueurs évalués : les deux listes sont remplacées par « Pas assez de notes pour un classement. » | — |
| Mesures | 2 lignes | Voir A4.3 | Idem |
| Séance du jour en cours | Statistiques recalculées à chaque rafraîchissement (interrogation 30 s, 6.5) avec « Mis à jour à {heure} » | — | — |
| Hors connexion | Dernière version en cache + « Données du {heure} » | — | — |

---

# PARTIE B — Évolution d'une séance à l'autre : page « Entraînements »

## B1. Objectif et accès

Route `/entrainements`, entrée de barre latérale **« Entraînements »** dans le groupe « Sport » (après « Vestiaire du jour »). Visible par tous les joueurs du club (les séances sont « L » pour tous, matrice 2.4), avec un contenu filtré par rôle.

> **NOUVEAU (circuit 9.4)** : cette page. Aujourd'hui, la liste des séances (4.7 : 5 dernières + « Voir plus ») est prévue dans l'Espace coach (`sport-espace-coach.md` §3 point 5), qui n'a pas d'entrée de menu dans le code actuel. La page « Entraînements » porte cette liste pour tous, avec les statistiques.

## B2. Structure

**En-tête** : titre « Entraînements » ; contexte « {nom du club} · Saison {saison} ». Action principale (Coach, Assistant) : « Créer une séance » (modale existante). Filtre de période (`SegmentedControl`, 36 px) : « 10 dernières séances » (défaut) / « Saison ».

Sections en cartes :

1. **« Taux de présence »** — `LineChart` : une valeur par séance (axe horizontal : dates courtes « 08/11 », axe vertical 0 à 100 %). Ligne de référence en tirets : moyenne de la période, libellée « Moyenne {74} % ». Point de la dernière séance mis en avant (cercle plein 8 px + valeur écrite). Au-dessus du graphique, la valeur clé : « Dernière séance : 72 % · moyenne 74 % ». Toucher un point → modale « Séance » (onglet « Statistiques »). Visible par tous.
2. **« Note moyenne des séances »** — même `LineChart`, échelle 0 à 10. Séance sans note : point absent et trait interrompu (jamais un 0). **Coach, Assistant, Président, VP, DS seulement.** Pour un joueur : la carte devient **« Mes notes »** (sa note retenue par séance, même graphique, « Ma moyenne : {6,9} »).
3. **« Séances »** — liste des 5 dernières, « Voir plus » (+5) (4.7, 3.3). Ligne de 56 px : date (« Dim. 22 nov. »), terrain, « {n} présents · {72} % », pour les rôles A3 « note {6,8} », `StatusBadge` « Ouverte » / « Verrouillée ». Clic → modale « Séance ».
4. **« Assiduité »** (Coach, Assistant, Président, VP, DS) — deux listes de 5 : « Les plus assidus » et « Les moins assidus » sur la période (avatar, nom, « {9} séances sur {10} · 90 % »). « Voir tout » → modale « Assiduité des joueurs » (`DataTable` triable : joueur, présences, retards, excusés, absences, taux ; recherche). Pour un joueur : carte « Mon assiduité » (« Vous avez participé à {8} séances sur {10} · 80 % »).
5. **« Tests de performance »** — partie C, §C5.

Footer.

## B3. Graphiques : règles de lecture (mobile)

- Une courbe = une seule mesure ; jamais deux axes verticaux sur le même graphique.
- À 360 px : graphique de 328 × 180 px ; au plus 10 points ; libellés d'axe 13 px ; une étiquette de date sur deux si elles se chevauchent. Sur la période « Saison » au-delà de 10 séances : le graphique défile horizontalement dans son cadre (3.3), aimanté sur la dernière séance.
- Toucher = action (ouvrir la séance), jamais une info réservée au survol. Sur ordinateur, le survol affiche en plus une info-bulle « {date} · {72} % ».
- Alternative textuelle : chaque graphique a un bouton discret « Voir les données » qui affiche le tableau des valeurs sous le graphique (accessibilité et lecture en plein soleil).

## B4. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Barre de progression + squelettes de 3 cartes | — | Chaque carte gère son erreur (« Impossible de charger … » + « Réessayer ») |
| Courbes | Squelette de graphique (rectangle 180 px) | Moins de 2 séances : « Il faut au moins 2 séances pour afficher une évolution. » ; aucune séance : « Aucune séance pour l'instant. » + (Coach) « Créer une séance » | Idem |
| Note moyenne | Idem | « Aucune séance notée sur la période. » | Idem |
| Assiduité | 5 lignes | « Aucune séance sur la période. » | Idem |

## B5. Ordinateur (≥ 1024 px)

Deux colonnes 8/4. Principale : Taux de présence, Note moyenne (côte à côte en 6/6 à partir de 1280 px), Séances. Latérale : Assiduité, Tests de performance.

---

# PARTIE C — Tests de performance (NOUVEAU, circuit 9.4)

## C1. Objectif

Permettre au Coach de mesurer des qualités sportives pendant une séance (vitesse, endurance, répétitions, adresse), d'en garder l'historique et d'en suivre l'évolution, sans matériel : le téléphone sert de chronomètre.

## C2. Modèle générique « test de performance »

Un **test** est défini une fois par club, puis réutilisé à chaque séance.

| Champ | Règle |
| --- | --- |
| Nom | Texte, 60 caractères max., unique dans le club parmi les tests actifs (« Un test porte déjà ce nom. ») |
| Type | Un des 4 types ci-dessous ; **non modifiable** dès qu'un résultat existe |
| Paramètres du type | Distance, durée ou nombre de tentatives, selon le type ; non modifiables dès qu'un résultat existe (sinon les résultats ne seraient plus comparables). Pour changer, on archive et on crée un nouveau test |
| Sens du classement | Déduit du type (temps : plus bas = meilleur ; distance, répétitions : plus haut = meilleur) ; choisi pour « Saisie libre » |
| Description | Facultative, 300 caractères (« Départ arrêté, ligne de but à ligne des 30 m ») |
| Statut | Actif / Archivé (jamais supprimé s'il a des résultats) |

**Les 4 types**

| Type | Paramètres | Saisie par joueur | Résultat principal | Calcul dérivé (par l'API) | Exemples |
| --- | --- | --- | --- | --- | --- |
| « Chrono sur distance » | Distance en mètres (1 à 5 000) | Temps (chrono ou saisie), au centième | Temps, en secondes « 4,52 s » ; au-delà de 60 s « 1 min 05,30 s » | **Vitesse moyenne** = distance ÷ temps, affichée en km/h (« 23,9 km/h ») et en m/s (« 6,64 m/s ») | Sprint 30 m ; navette 5 × 10 m (distance totale 50 m) |
| « Distance en temps donné » | Durée (mm:ss, 00:10 à 60:00) | Distance parcourue en mètres (saisie directe ou « tours × longueur du tour + reste ») | Distance « 2 650 m » | Vitesse moyenne = distance ÷ durée, en km/h | Test de Cooper 12 min ; 6 min |
| « Nombre de répétitions » | Facultatif : nombre de tentatives (1 à 100) ; facultatif : durée limite | Nombre réussi (compteur − / +) | « 7 » ou « 7 sur 10 » | Si tentatives : taux de réussite « 70 % » | Tirs cadrés sur 10 ; jongles en 1 min ; allers-retours de navette |
| « Saisie libre » | Unité choisie dans une liste fermée : « secondes », « mètres », « km/h », « répétitions », « points », « pourcentage » ; nombre de décimales (0 à 2) ; sens du classement | Valeur | « {valeur} {unité} » | Aucun | Palier atteint ; précision de passes sur 20 points |

**Pas de donnée de santé** (CLAUDE.md règle 11, 4.12) : il n'existe aucune unité « kg », « cm », « battements par minute », « tension ». L'unité est une liste fermée, jamais un texte libre. Aide sous le nom du test : « Les tests mesurent une performance sportive. N'y enregistrez aucune donnée de santé (poids, taille, fréquence cardiaque) : elles relèvent du Médecin. » Aucune estimation physiologique (VO2 max, VMA « médicale ») n'est calculée : la vitesse moyenne suffit et reste une donnée sportive.

**Modèles proposés** : à la création, le Coach peut partir d'un modèle (« Sprint 30 m », « Sprint 10 m », « Navette 5 × 10 m », « Test de Cooper (12 min) », « Tirs cadrés sur 10 », « Jongles en 1 minute »). Les modèles sont une liste de référence servie par l'API depuis le code (pas une migration, pas une donnée de démonstration, CLAUDE.md §3) ; choisir un modèle préremplit la modale, rien n'est créé sans « Enregistrer ».

**Résultat** : un résultat appartient à un test, une séance et un joueur. Il conserve la **valeur brute** (temps en millisecondes entières, distance en mètres décimaux, nombre entier, valeur décimale — jamais de `float` côté API), la méthode (« Chrono » ou « Saisie manuelle »), l'auteur et l'heure. Un joueur peut avoir **plusieurs essais** pour un même test dans une même séance (« Essai 1 », « Essai 2 ») ; son résultat de la séance est le **meilleur essai** (proposition, question C-Q5). Statut « Abandon » possible (joueur tombé, n'a pas fini) : pas de valeur, jamais classé, jamais compté comme 0.

## C3. Accès

| Action | Coach, Assistant | Président, VP | Directeur sportif | Capitaine | Autres joueurs | Le joueur lui-même |
| --- | --- | --- | --- | --- | --- | --- |
| Créer, modifier, archiver un test | É | — | — | — | — | — |
| Mesurer (chrono, saisie) | É | — (proposition, C-Q3) | — | — (proposition, C-Q3) | — | — |
| Corriger, retirer un résultat | É | — | — | — | — | — |
| Voir tous les résultats, classements, évolution de chacun | L | L | L | — | — | — |
| Voir ses propres résultats et son évolution | — | — | — | — | — | L (« P ») |

Rattachement à la matrice : ligne « Évaluation des performances » (Coach É, DS L, J P). Pour le Président et le VP, la matrice donne « É » sur les évaluations ; la spec leur laisse provisoirement la lecture seule sur les mesures (le chrono est un outil de terrain du staff technique). À trancher (C-Q3).

**Joueurs mesurables** : seulement les joueurs **pointés** à la séance (présents ou retardataires) : ils sont physiquement là. Un joueur **inapte** n'est pas mesurable : sa ligne est grisée, avec le texte que l'API sert pour le rôle (« Inapte · retour prévu le {date} » pour le Coach, jamais de diagnostic). « Apte avec restriction » : mesurable, avec le badge orange « Apte avec restriction » en rappel. Dette, suspension, attente d'adhésion : mesurables (ces blocages concernent la composition et le placement, pas l'entraînement) — proposition, C-Q4.

**Données sportives, jamais de santé** : les résultats ne sont jamais servis par le module médical, ni visibles par le Médecin à ce titre (il les voit comme tout joueur : les siens seulement). Ils ne sont **pas publics** (pas sur le fil public, pas dans la comparaison entre clubs), position prudente, C-Q6.

## C4. Lien avec le radar de la carte (4.2)

Le 4.2 dit que les attributs du radar sont « calculés à partir des évaluations (4.10) et des statistiques », sans formule, et la liste des axes n'est pas tranchée (`club-carte-joueur.md` points ouverts 4 et 12). **Aucun lien n'est fait par défaut** : les mesures n'alimentent ni le radar ni la note globale tant que le client n'a pas décidé. Option à soumettre : un axe « Vitesse » ou « Endurance » calculé à partir du rang du joueur dans le club sur un test choisi (par exemple percentile sur le sprint 30 m de la saison), ou une contribution à l'axe « Physique ». À trancher avec les points 4 et 12 de la carte (C-Q7). En attendant, la fiche détaillée du joueur (4.2, onglet « Statistiques ») peut afficher une section « Tests de performance » (meilleur résultat de la saison par test), visible selon C3 — proposition.

## C5. Carte « Tests de performance » (page « Entraînements »)

- Staff (rôles « L » de C3) : une ligne par test actif : nom, type en clair (« Chrono sur 30 m »), « Dernière mesure le {date} · {n} joueurs », meilleur résultat de la saison (« 4,21 s · Prénom N. »). Clic → modale « Classement : {test} » (C6.5). Action de carte (Coach, Assistant) : « Nouveau test » (C6.6). Menu « … » : « Tests archivés ».
- Joueur : carte « Mes tests » : une ligne par test où il a un résultat : « Sprint 30 m · meilleur 4,52 s · dernier 4,60 s le {date} ». Clic → modale « Mon évolution : {test} » (C6.7).
- Vide : staff « Aucun test de performance pour l'instant. » + (Coach) « Nouveau test » ; joueur « Vous n'avez pas encore de mesure. »

## C6. Modales

### C6.1 « Mesurer » — taille `md` (panneau bas sur mobile), étape de choix

| Champ | Composant | Obligatoire | Règle |
| --- | --- | --- | --- |
| Test | Liste de choix des tests actifs (ce n'est pas un choix de joueur ; `SegmentedControl` s'il y en a 4 au plus, liste radio sinon) + lien « Nouveau test » | Oui | « Choisissez un test. » |
| Méthode | `SegmentedControl` : « Chronomètre » / « Saisie manuelle » | Oui | « Chronomètre » proposé seulement pour « Chrono sur distance » et « Distance en temps donné » |
| Départ (chrono sur distance) | `SegmentedControl` : « Départ groupé » / « Un par un » | Oui | Défaut : « Départ groupé » |
| Joueurs | Liste des joueurs pointés, cases à cocher, recherche « Nom ou numéro », « Tout cocher » / « Tout décocher » (même composant que `sport-pointage-selection-multiple.md`) — **jamais de `<select>`** | Oui, 1 au moins | « Cochez au moins un joueur. » ; aide en départ groupé : « 6 joueurs au plus conseillés par départ : au-delà, il devient difficile d'arrêter chaque chrono au bon moment. » (pas un blocage, maximum technique 12) |

Pied : « Annuler » / « Commencer ». Ouvre C6.2 ou C6.3 en remplaçant le contenu de la modale (même modale, passage en plein écran sur mobile).

### C6.2 « Chronomètre : {test} » — plein écran sur mobile, taille `xl` sur ordinateur

**Départ groupé (chrono sur distance)** :

```
┌──────────────────────────────────────┐
│ ✕  Sprint 30 m · essai 1             │ en-tête 48 px
├──────────────────────────────────────┤
│            00:04,37                  │ 24 px, gras, tabulaire
│        Chrono en cours · 4 sur 6     │ 14 px
├──────────────────────────────────────┤
│ (AV) Prénom N.   n°7    [ Arrêter ]  │ ligne 64 px, bouton 40 px
│ (AV) Prénom N.   n°4      4,21 s  ↺  │ arrêté : temps + « Reprendre »
│ (AV) Prénom N.   n°11   [ Arrêter ]  │
│ (AV) Prénom N.   n°9      4,35 s  ↺  │
│ (AV) Prénom N.   n°2    [ Arrêter ]  │
│ (AV) Prénom N.   n°5    Abandon   ↺  │
├──────────────────────────────────────┤
│ [ … ]                 [ Terminer ]   │ pied collant
└──────────────────────────────────────┘
```

- Avant le départ : chrono « 00:00,00 », lignes sans bouton, action principale du pied **« Départ »** (40 px, pleine largeur du pied). Option dans « … » : « Compte à rebours de 3 s » (« 3, 2, 1, partez » à l'écran et vibration), désactivée par défaut.
- Après « Départ » : chaque ligne porte **« Arrêter »** ; la ligne entière (64 px) est la zone tactile du bouton, pour viser sans regarder. Les lignes **ne changent jamais de place** pendant le chrono (un réordonnancement ferait arrêter le mauvais joueur).
- Joueur arrêté : son temps s'affiche à la place du bouton (16 px, gras) et une icône « Reprendre » (zone 44 px, libellé lecteur d'écran « Reprendre le chrono de {nom} ») permet de corriger un appui accidentel **tant que le chrono tourne** : son temps repart du chrono commun.
- Menu « … » de chaque ligne (appui sur l'avatar) : « Abandon » ; « Retirer de ce départ ».
- Quand tous sont arrêtés ou en abandon, le chrono s'arrête seul. Le pied propose alors : « Nouvel essai » (secondaire, même joueurs, essai 2) / **« Enregistrer ({n}) »** (principal). Avant cela, « Terminer » arrête le chrono pour tous ceux qui courent encore, avec confirmation « Arrêter le chrono ? {k} joueurs n'ont pas été arrêtés : ils seront notés « Abandon ». » — « Continuer le chrono » / « Arrêter ».
- Vitesse : après l'arrêt, sous le temps, en 13 px : « 23,9 km/h » (calcul affiché à titre indicatif ; la valeur officielle est recalculée par l'API à l'enregistrement).

**Un par un** : même écran ; une seule ligne active à la fois ; chaque ligne a « Départ » puis « Arrêter » ; la ligne suivante devient active automatiquement.

**Distance en temps donné (Cooper)** : le chrono **décompte** la durée (« 11:59 »). Pas d'arrêt par joueur. À 0 : vibration, signal sonore court si le son est activé, message « Temps écoulé. Saisissez la distance de chaque joueur. » Le contenu passe à la saisie (C6.3) avec, pour chaque joueur, deux aides : « Tours » × « Longueur du tour (m) » (longueur commune saisie une fois) + « Mètres en plus ».

**Fonctionnement technique (exigences pour `frontend-dev`)** :

- Le temps est calculé par **horodatage monotone** (`performance.now()`), jamais par un compteur incrémenté : il reste exact si l'écran se met en veille, si l'utilisateur change d'application ou si le téléphone ralentit. L'affichage est rafraîchi par `requestAnimationFrame` (10 fois par seconde suffisent).
- Demande de maintien de l'écran allumé (Wake Lock) pendant le chrono quand le navigateur le permet ; sinon, bandeau `info` « Gardez l'écran allumé pendant le chrono. »
- **Hors connexion** : le chrono fonctionne sans réseau ; les résultats sont mis en file (6.6) avec un `client_uuid` chacun, puis envoyés au retour du réseau (`SyncIndicator`).
- Fermeture (croix, Échap, retour arrière du téléphone) pendant ou après un chrono non enregistré : « Abandonner ces mesures ? Les temps non enregistrés seront perdus. » — « Continuer » / « Abandonner ». Pas de fermeture par clic extérieur en plein écran.
- Précision affichée : le centième. Aide permanente en 13 px sous le chrono : « Chronométrage manuel : comptez environ 0,2 s d'écart selon la réaction de la personne qui arrête. »
- `prefers-reduced-motion` : aucun clignotement ; le compte à rebours reste textuel.

### C6.3 « Saisie manuelle : {test} » — plein écran sur mobile

- Une ligne par joueur coché : avatar 32, nom, champ adapté au type :
  - temps : `NumberField` « Temps (s) » avec virgule décimale (« 4,52 »), ou deux champs « min » / « s » au-delà de 60 s ;
  - distance : `NumberField` « Distance (m) » (+ aide tours × longueur) ;
  - répétitions : compteur − / + (boutons de 40 px, zone 44 px) et valeur éditable ; « sur {N} » affiché si tentatives ;
  - libre : `NumberField` avec l'unité en suffixe.
- Case « Abandon » par ligne. Ligne laissée vide = joueur non mesuré (rien n'est enregistré pour lui).
- Erreurs sous le champ : « Saisissez un temps supérieur à 0. » ; « Ce temps paraît trop court pour {30} m (moins de {2,5} s) : vérifiez-le. » (avertissement non bloquant, seuil = vitesse > 45 km/h) ; « Le nombre ne peut pas dépasser {10} tentatives. » ; « La distance doit être comprise entre 0 et 10 000 m. »
- Récapitulatif collant : « {n} résultats saisis sur {m} joueurs ».
- Pied : « Annuler » / « Enregistrer ({n}) ». Succès : « {n} résultats enregistrés. » ; hors connexion : « {n} résultats enregistrés sur ce téléphone. Ils seront envoyés au retour du réseau. »

### C6.4 « {test} — séance du {date} » (résultats d'une séance) — taille `lg`

- Sous-titre : « {n} joueurs mesurés · meilleur {4,21 s} · moyenne {4,63 s} ».
- Liste classée (staff) : rang, avatar, nom, résultat principal (16 px gras), dérivé (13 px : « 23,9 km/h »), méthode (icône chrono ou crayon + texte lecteur d'écran), « Essai 2 sur 3 » si plusieurs. « Abandon » en bas, non classé. Badge texte « Record personnel » (pas un `StatusBadge` de couleur de statut) si c'est le meilleur résultat du joueur sur ce test.
- Clic sur une ligne → C6.8 (détail et correction).
- Joueur : la modale ne montre que sa ligne et « Votre meilleur résultat sur ce test : {4,45 s} le {date} ».
- Pied : « Fermer » ; Coach, Assistant (dans les 48 h) : « Ajouter des mesures » (→ C6.1 avec le test choisi).

### C6.5 « Classement : {test} » — taille `lg`

- Filtre : `SegmentedControl` « Dernière séance » / « Saison » (meilleur résultat de chaque joueur sur la saison).
- `DataTable` (recherche, tri, pagination au-delà de 30) : rang, joueur, meilleur résultat, dérivé, date, nombre de mesures, tendance (« en progrès de 0,12 s » / « en recul de 0,08 s » sur ses deux dernières mesures, en texte).
- `BarChart` horizontal des 10 premiers au-dessus du tableau (dépliable à 360 px).
- Clic sur un joueur → C6.7. Pied : « Fermer » ; menu « … » (Coach) : « Modifier le test », « Archiver le test ».

### C6.6 « Nouveau test » / « Modifier le test » — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Partir d'un modèle | Puces des modèles (C2) | Non | Préremplit les champs |
| Nom | `TextField` | Oui | 60 caractères ; « Un test porte déjà ce nom. » |
| Type | `SegmentedControl` (4 types, sur 2 lignes à 360 px) | Oui | Verrouillé si des résultats existent : aide « Le type ne peut plus changer : des résultats existent. Archivez ce test et créez-en un nouveau. » |
| Distance (m) | `NumberField` | Oui pour « Chrono sur distance » | 1 à 5 000 ; « Saisissez une distance entre 1 et 5 000 m. » |
| Durée | Deux `NumberField` min / s | Oui pour « Distance en temps donné » | 10 s à 60 min |
| Nombre de tentatives | `NumberField` | Non | 1 à 100 |
| Durée limite | min / s | Non | — |
| Unité | `SegmentedControl` (liste fermée C2) | Oui pour « Saisie libre » | — |
| Décimales | `SegmentedControl` 0 / 1 / 2 | Oui pour « Saisie libre » | — |
| Meilleur résultat | `SegmentedControl` « Le plus élevé » / « Le plus bas » | Oui pour « Saisie libre » | — |
| Description | `TextArea` | Non | 300 caractères |

Aide santé (C2) sous le nom. Pied : « Annuler » / « Enregistrer ». Succès : « Test créé. » / « Test modifié. » Archivage : `ConfirmDialog` « Archiver le test « {nom} » ? Ses résultats restent consultables, mais il ne sera plus proposé pour de nouvelles mesures. » — « Archiver ».

### C6.7 « Évolution : {test} — {joueur} » (ou « Mon évolution : {test} ») — taille `md`

- Tuiles : « Meilleur » (valeur, date), « Dernier », « Progression » (« −0,31 s depuis la première mesure » ; le texte dit « en progrès » ou « en recul » selon le sens du test, jamais la couleur seule).
- `LineChart` : une valeur par séance mesurée (meilleur essai), axe dans le bon sens (pour un temps, la courbe qui **descend** est un progrès : l'axe vertical n'est pas inversé, mais une légende « Plus bas = plus rapide » est affichée).
- Liste des mesures (5 + « Voir plus ») : date, résultat, dérivé, méthode.
- Accès : staff (L) pour tout joueur ; joueur pour lui-même. Pied : « Fermer ».

### C6.8 « Résultat de {joueur} » (détail et correction) — taille `sm`

- Lecture : test, séance, essai, valeur, dérivé, méthode, « Mesuré par {nom} à {heure} » ; si corrigé : « Corrigé par {nom} le {date} : {ancienne valeur} → {nouvelle valeur} · motif : {motif} ».
- Coach, Assistant, **jusqu'à 48 h après la séance** (même délai que les évaluations, 4.10 ; proposition C-Q8) : « Corriger » → champs de valeur du type + `TextArea` « Motif de la correction » (obligatoire, « Indiquez le motif. ») ; pied « Annuler » / « Enregistrer la correction ». Menu « … » : « Retirer ce résultat » → `ConfirmDialog` avec motif obligatoire, « Retirer le résultat de {nom} ({4,52 s}) ? Il ne sera plus compté, mais restera dans l'historique des corrections. » — « Retirer ».
- Après 48 h : lecture seule, bandeau « Résultat verrouillé (plus de 48 heures). »
- Un résultat n'est jamais supprimé physiquement : la correction crée une nouvelle version, le retrait marque le résultat « Retiré » (même esprit que la règle 4).

## C7. Règles, cas limites, journal, notifications

**Règles**

1. Toute valeur dérivée (vitesse, taux de réussite, classement, meilleur essai, progression) est calculée par `apps/sport/services.py`, en `Decimal`. L'interface n'affiche le calcul local qu'à titre indicatif pendant le chrono.
2. Pas de mesure sur une séance **verrouillée par les 48 h** ; la séance elle-même se verrouille à minuit pour le pointage (4.7), mais la mesure suit le délai des évaluations (proposition C-Q8).
3. Un joueur ne peut être mesuré que s'il est pointé à la séance ; inapte : refusé par l'API avec « {nom} est inapte : il ne peut pas être mesuré. » (texte filtré selon le rôle).
4. Un test archivé n'est plus proposé ; ses résultats restent lisibles.

**Cas limites**

| Cas | Comportement |
| --- | --- |
| Appel ou SMS pendant le chrono | Le chrono continue (horodatage) ; au retour, l'écran est à jour |
| Le téléphone s'éteint (batterie) | Les temps non enregistrés sont perdus ; proposition : sauvegarde locale de l'état du chrono toutes les secondes, restaurée à la réouverture avec « Un chrono non enregistré a été retrouvé ({test}, {heure}). » — « Reprendre » / « Abandonner » |
| Deux téléphones mesurent le même joueur sur le même test | Deux essais distincts, chacun avec son auteur ; le meilleur est retenu |
| Joueur dé-pointé entre la mesure et l'envoi (impossible au MVP : « Retirer le pointage » est reporté) | Sans objet |
| Joueur devenu inapte entre la mesure et l'envoi hors connexion | Le résultat est enregistré (il a été mesuré avant) ; pas de refus a posteriori |
| Temps aberrant (vitesse > 45 km/h) | Avertissement non bloquant à la saisie ; enregistré si confirmé |
| Test modifié après des résultats | Impossible sur le type et les paramètres (C2) ; seuls le nom et la description changent |

**Journal d'activité** (règle 6, 5.2) : création, modification, archivage d'un test ; **une entrée par résultat enregistré** (avec l'identifiant du départ ou de la saisie groupée, comme `batch_id` dans `sport-pointage-selection-multiple.md` §8) ; chaque correction (ancienne et nouvelle valeur, motif) ; chaque retrait (motif). Aucune consultation n'est journalisée.

**Notifications** (NOUVEAU, le 4.17 n'en prévoit pas) : proposition, une seule notification in-app par joueur et par séance, envoyée 1 h après la dernière mesure : « Vos mesures de la séance du {date} sont disponibles. » Pas de notification par résultat (trop de bruit). À valider (C-Q9).

## C8. Données et API (noms proposés pour `backend-dev`)

**Statistiques (parties A et B)** — aucune migration :

- `GET /api/v1/sport/sessions/{id}/stats/` → `{ attendance: { expected, present, late, absent, excused, rate, late_counts_as_absent, late_label, late_family, delta_vs_average, late_list[], excused_list[], absent_list[] }, evaluations: null | { average, evaluated, eligible, delta_vs_average, best[], lowest[], distribution[], open_until, locked }, my_evaluation: null | {…}, measures: [{ test_id, name, measured_count, best }], capabilities: { can_evaluate, can_measure } }`. Le bloc `evaluations` est `null` pour les rôles sans « L » ni « É » sur les évaluations (A3).
- `GET /api/v1/sport/sessions/stats/history/?period=last10|season` → `[{ session_id, date, attendance_rate, average_rating | null, my_rating | null }]` (`average_rating` seulement pour les rôles A3 ; `my_rating` pour tous).
- `GET /api/v1/sport/attendance/ranking/?period=…` → assiduité par joueur (rôles A3) ; `GET /api/v1/sport/attendance/me/?period=…` pour le joueur.
- Le détail des notes réutilise `GET /api/v1/sport/events/{id}/evaluations/` (filtrage par rôle déjà en place).

**Tests de performance (partie C)** — nouvelles tables (migration réversible dans `apps/sport`) :

- `PerformanceTest` (`TenantModel`) : `name`, `kind` (`timed_distance` | `distance_in_time` | `repetitions` | `free`), `distance_m` (Decimal, null), `duration_s` (entier, null), `attempts` (entier, null), `time_limit_s` (entier, null), `unit` (choix fermé, null), `decimals`, `higher_is_better`, `description`, `archived_at`, `created_by`.
- `PerformanceRun` (`TenantModel`) : un départ ou une saisie groupée — `event`, `test`, `method` (`stopwatch` | `manual`), `start_mode` (`group` | `individual` | null), `recorded_by`, `client_uuid`.
- `PerformanceResult` (`TenantModel`) : `run`, `membership`, `attempt_no`, `time_ms` (entier, null), `distance_m` (Decimal, null), `count` (entier, null), `value` (Decimal, null), `outcome` (`done` | `dnf`), `status` (`active` | `voided`), `client_uuid` (unique par club), `created_at`.
- `PerformanceResultCorrection` (append-only) : `result`, `old_*`, `new_*`, `reason`, `actor`, `created_at`.
- Endpoints : `GET|POST /api/v1/sport/performance-tests/`, `PATCH /performance-tests/{id}/`, `POST /performance-tests/{id}/archive/`, `GET /performance-test-templates/`, `GET /events/{id}/performance-results/?test=`, `POST /events/{id}/performance-results/bulk/` (`{ test_id, method, start_mode, client_uuid, items: [{ membership_id, attempt_no, time_ms | distance_m | count | value, outcome, client_uuid }] }`, résultats joueur par joueur comme le pointage groupé), `PATCH /performance-results/{id}/` (`{ …valeur, reason }`), `POST /performance-results/{id}/void/` (`{ reason }`), `GET /performance-tests/{id}/leaderboard/?period=last|season` (rôles « L »), `GET /players/{membership_id}/performance/?test=` (staff « L » ou le joueur lui-même ; 404 pour un autre joueur).
- Permissions : `CanManagePerformanceTests` (Coach, Assistant) ; `CanViewAllPerformance` (Coach, Assistant, Président, VP, DS) ; sinon le joueur ne lit que ses propres résultats. Isolation par club par les managers tenant-aware ; tests d'étanchéité à prévoir.

## C9. Questions pour le client

- **C-Q1** Les coéquipiers doivent-ils voir la note moyenne de l'équipe et le classement des notes ? Position provisoire : non (matrice 2.4 « P »). Le joueur voit sa note seulement.
- **C-Q2** Un joueur « En attente d'adhésion » fait-il partie des « joueurs attendus » pour le taux de présence ? Proposition : non.
- **C-Q3** Qui peut **mesurer** ? Proposition : Coach et Assistant. Faut-il ouvrir au Capitaine (souvent celui qui tient le chrono) et au Président / VP (« É » sur les évaluations) ?
- **C-Q4** Un joueur en dette, suspendu ou en attente d'adhésion peut-il être mesuré ? Proposition : oui (seule l'inaptitude bloque).
- **C-Q5** Plusieurs essais par séance : retenir le meilleur (proposition) ou la moyenne ?
- **C-Q6** Les résultats des tests sont-ils publics (fil public, comparaison entre clubs), comme les « statistiques sportives » du 4.2 ? Position provisoire : non, internes au club.
- **C-Q7** Les mesures doivent-elles alimenter le radar (axe « Vitesse », « Endurance », ou l'axe « Physique ») ? À trancher avec les points ouverts 4 et 12 de `club-carte-joueur.md`. Défaut : aucun lien.
- **C-Q8** Délai de correction d'un résultat : 48 h comme les évaluations (proposition) ?
- **C-Q9** Notification « Vos mesures sont disponibles » : oui (une par séance) ou non ?
- **C-Q10** Validation globale de la partie C (circuit 9.4), y compris la liste fermée d'unités et l'absence de toute estimation physiologique.
