# Écran — Cartes des joueurs et statistiques côte à côte

Sources : CDC 3 (charte), 3.3 (listes, tableau au-delà de 30 éléments), 3.4 (avatar, badges), 4.2 (carte style FC/FIFA, six indicateurs, fiche détaillée, attributs du radar, comparaison de 2 à 4 joueurs, visibilité publique), 4.7 à 4.10, 4.12 (aptitude sans diagnostic), 6.3, 6.7, 7.5 (consentement de publication, mineurs), matrice 2.4, 10.2 n° 16, CLAUDE.md règles 11, 15, 16, 18. Demande du client : `remarques.md` l. 90, décidée le 15/11/2026. Écrans liés : `club-carte-joueur.md` (composant `PlayerTradingCard`, parties A et B, comparaison B3 — **référence pour tout ce qui concerne la carte**), `club-comite-bureau.md` (Effectif), `sport-statistiques-seance.md`, `club-tableau-de-bord-bureau.md` §6 (graphiques).

> **NOUVEAU (circuit 9.4, à valider)** : la **page** qui présente toutes les cartes et, à côté de chaque carte, ses statistiques. Le CDC 4.2 prévoit la carte, la fiche détaillée ouverte au clic et la comparaison, mais aucune page qui les rassemble. La carte, ses six indicateurs, la fiche détaillée et la comparaison restent ceux du 4.2 et de `club-carte-joueur.md`.

## 1. Objectif

Parcourir l'effectif comme un album de cartes, trouver un joueur en deux appuis (recherche, poste), et lire d'un coup d'œil, à côté de sa carte, ses chiffres de la saison : matchs, buts, passes, cartons, présence, note, radar, forme récente. Comparer deux à quatre joueurs depuis la même page.

## 2. Accès

Route `/club/joueurs`. Entrée de barre latérale **« Cartes des joueurs »** dans le groupe « Club », après « Comité et bureau ».

| Rôle | Accès |
| --- | --- |
| Tout membre actif du club | Lecture des cartes et des statistiques sportives de tous les joueurs **de son club** |
| Coach, Assistant, Président, VP, Directeur sportif, Médecin | En plus : filtre « Disponibilité » et section « Aptitude » de la fiche (10.2 n° 16) |
| Superuser | Pas d'entrée (non joueur) ; en Ghost Mode, vue d'un membre |

La page est **interne au club** (connexion obligatoire). La version publique des cartes (fil public, comparaison « Tous les clubs ») passe par la vue publique du 6.3 et reste régie par `club-carte-joueur.md` B3.1 et points ouverts 10, 13, 14.

**Données jamais affichées sur cette page, quel que soit le rôle** (4.2, visibilité) : poids, taille, téléphone, adresse, finances (solde, dette, montants), santé (diagnostic, blessure, soins). Même le Président et le Trésorier n'y voient aucune donnée financière : c'est une page sportive.

## 3. Structure de la page

**En-tête** : titre « Cartes des joueurs » ; contexte « {nom du club} · Saison {saison} · {n} joueurs ». Action principale : **« Comparer »** (bouton secondaire `sm` : il n'y a pas d'action d'écriture ; il passe la grille en mode sélection, §3.4).

**Barre d'outils** (collante sous l'en-tête sur mobile) :

1. Recherche « Nom ou numéro » (36 px), suggestions en direct (filtre local si l'effectif est chargé, sinon API).
2. Puces « Poste » : « Tous » · « Gardien » · « Défenseur » · « Milieu » · « Attaquant » (libellés servis par l'API, en toutes lettres).
3. Bouton « Filtres » (36 px, compteur de filtres actifs) → panneau bas :
   - « Statut » : « Joueurs actifs » (défaut) / « Anciens joueurs » (partis) ;
   - **« Disponibilité »** (seulement pour les rôles qui y ont droit, §2) : « Tous » / « Disponibles » / « Indisponibles » ; le motif n'est pas filtrable ici ;
   - « Saison » : saison en cours (défaut) et saisons précédentes (flèches ‹ ›) ;
   - pied : « Réinitialiser » / « Afficher {n} joueurs ».
4. Tri : bouton « Trier : {Nom} » → panneau bas à choix unique : « Nom », « Numéro », « Note moyenne », « Buts », « Passes décisives », « Taux de présence », « Matchs joués ». Les valeurs « — » (pas encore de donnée) sont toujours en fin de liste.
5. Bascule d'affichage (`SegmentedControl` 36 px) : **« Cartes »** (défaut) / **« Tableau »**.

### 3.1 Affichage « Cartes » — mobile (< 1024 px)

- Grille de **cartes `size="sm"`** (`PlayerTradingCard`, `club-carte-joueur.md` B2.1) : 2 colonnes à 360 px (cartes fluides de 156 à 168 px, écart 12 px), 3 colonnes à partir de 600 px.
- **Sous chaque carte**, une **bande de statistiques** (c'est « à côté de la carte » sur un petit écran) : 3 valeurs sur une ligne, 13 px, chiffres tabulaires : « {12} matchs · {5} buts · {7,4} note ». Les trois valeurs suivent le tri choisi (si tri « Taux de présence » : la présence remplace la note). Libellés en toutes lettres, retour à la ligne autorisé, jamais d'abréviation.
- Pagination : **24 cartes**, puis bouton « Voir plus » (+24) en bas (3.3). Le nombre total est rappelé : « {24} sur {38} joueurs ».
- Toucher une carte → **modale « Fiche du joueur »** (§4.1), plein écran : la carte, puis les statistiques juste en dessous.

### 3.2 Affichage « Cartes » — ordinateur (≥ 1024 px) : carte et statistiques côte à côte

Mise en page maître-détail, sans modale :

- **Colonne gauche (5/12)** : la grille de cartes `sm` (2 colonnes à 1024 px, 3 à partir de 1440 px), défilement propre à la colonne.
- **Colonne droite (7/12), collante** : le **panneau du joueur choisi** :
  - à gauche du panneau, la **carte `md`** (280 px, effet 3D au survol, `club-carte-joueur.md` A5.1) ;
  - à droite de la carte, **les statistiques** (§4.2) : six indicateurs détaillés, radar, forme récente, présence, discipline ;
  - en bas du panneau : « Voir la fiche détaillée » (ouvre la fiche détaillée du 4.2 en modale) et « Comparer avec… » (ouvre la comparaison avec ce joueur déjà choisi).
- À l'arrivée, le panneau montre le premier joueur de la liste triée ; le joueur choisi est surligné dans la grille (bordure `--color-primary` 2 px et `aria-current="true"`). Les flèches ↑ ↓ ← → déplacent la sélection dans la grille.
- L'adresse reflète le joueur choisi (`/club/joueurs?joueur={id}`) pour pouvoir partager le lien à un membre du club.

### 3.3 Affichage « Tableau »

`DataTable` (3.3 : au-delà de 30 joueurs, tableau avec recherche, filtres et pagination ; mêmes recherche, puces et filtres que l'affichage « Cartes ») :

- colonnes : « Joueur » (avatar 32 + « Prénom Nom », figée, 160 px) · « Numéro » · « Poste » · « Matchs » · « Buts » · « Passes décisives » · « Cartons » (« {j} jaunes, {r} rouge(s) ») · « Taux de présence » · « Note moyenne » · « Forme » (5 dernières notes en mini-barres + valeur de la dernière) ;
- tri en cliquant sur l'en-tête ; pagination de 25 lignes ;
- défilement horizontal dans son cadre à 360 px (première colonne figée, ombre de bord) ;
- clic sur une ligne → même modale « Fiche du joueur » (mobile) ou même panneau (ordinateur).

**Raison de l'affichage par défaut « Cartes »** malgré la règle 3.3 : c'est l'objet même de la demande du client. La grille respecte l'esprit de la règle (recherche, filtres, pagination) et le tableau reste à un toucher. **Écart à la charte signalé, à valider** (Q1).

### 3.4 Mode « Comparer »

- « Comparer » fait apparaître une case à cocher en haut à gauche de chaque carte (zone 44 px) et une barre collée en bas : « {n} joueur(s) choisi(s) · 2 à 4 » + bouton principal « Comparer ({n}) » (actif de 2 à 4) + « Annuler ».
- À 4 joueurs cochés, les autres cases sont désactivées avec l'aide « 4 joueurs au maximum. Retirez-en un pour en ajouter un autre. » (texte de `club-carte-joueur.md` B3).
- « Comparer ({n}) » ouvre la **modale « Comparer des joueurs » existante** (`club-carte-joueur.md` B3, `PlayerComparisonModal`) avec les joueurs déjà choisis ; on peut y en ajouter par la recherche (jamais de `<select>`).
- Le mode sélection est aussi disponible dans l'affichage « Tableau » (case en première colonne).

### 3.5 Maquettes

**360 px**

```
┌──────────────────────────────────────┐
│ Cartes des joueurs        [Comparer] │ 20 px
│ {Club} · Saison 2026-2027 · 38 joueurs│ 14 px
│ [ Nom ou numéro               ]      │ 36 px
│ (Tous)(Gardien)(Défenseur)(Milieu)…  │ puces défilantes
│ [Filtres] [Trier : Nom] [Cartes|Tableau] │
├──────────────────────────────────────┤
│ ┌───────────┐   ┌───────────┐        │
│ │  carte sm │   │  carte sm │        │ ~230 px
│ │  (photo,  │   │           │        │
│ │ note, nom)│   │           │        │
│ └───────────┘   └───────────┘        │
│ 12 matchs · 5 buts  10 matchs · 0 but │ 13 px
│ · 7,4 note          · 6,9 note        │
│ …                                     │
│        24 sur 38 joueurs              │
│           [ Voir plus ]               │
└──────────────────────────────────────┘
```

**≥ 1024 px**

```
┌────────────────────────┬─────────────────────────────────────────┐
│ [carte][carte]         │ ┌──────────┐  Statistiques · Saison …  │
│ [carte][carte]         │ │ carte md │  Matchs 12  Buts 5        │
│ [carte][carte]         │ │  280 px  │  Passes décisives 3       │
│  …  (défile)           │ │          │  Cartons 2 (2 jaunes, 0 rouge)│
│                        │ └──────────┘  Taux de présence 85 %    │
│                        │               Note moyenne 7,4 sur 10  │
│                        │  Radar des attributs   Forme récente   │
│                        │  (RadarChart 240 px)   ▂▅▆▄▇ (5 notes) │
│                        │  Présences : 17 séances sur 20, 2 retards│
│                        │  [Voir la fiche détaillée] [Comparer avec…]│
└────────────────────────┴─────────────────────────────────────────┘
```

## 4. Modales et panneau

### 4.1 « Fiche du joueur » (mobile) — modale `lg`, plein écran

Même modale que `club-carte-joueur.md` A2/A3 (`PlayerCardModal`), enrichie :

1. la carte `md` centrée (avec la grille des six indicateurs de B2.3) ;
2. sous la carte, les **sections de statistiques** du §4.2, dans des cartes neutres ;
3. section « Au club » (statut, membre depuis, rôles) inchangée.

Pied : « Fermer » (secondaire) ; « Comparer » (secondaire) ; « Voir la fiche détaillée » (principal). Navigation entre joueurs : glisser à gauche / à droite sur l'en-tête de la modale **ou** boutons « Joueur précédent » / « Joueur suivant » (40 px, dans l'en-tête), dans l'ordre de la liste filtrée — l'alternative par bouton est obligatoire (le glissement ne doit jamais être le seul chemin).

### 4.2 Contenu des statistiques (panneau ordinateur et fiche mobile)

Toutes calculées par l'API, pour la saison choisie (`season_label` toujours affiché). Les mêmes sections servent au panneau d'ordinateur (à droite de la carte) et à la fiche mobile (sous la carte).

| Section | Contenu | Sans donnée |
| --- | --- | --- |
| « Statistiques · Saison {saison} » | Les six indicateurs du 4.2, en `KpiTile` (2 × 3 à 360 px, 3 × 2 sur ordinateur) : « Matchs », « Buts », « Passes décisives », « Cartons » (« {j} jaunes, {r} rouge(s) »), « Taux de présence », « Note moyenne » (« 7,4 sur 10 ») ; en plus, « Minutes » n'est **pas** affiché (non suivi par le CDC) | « 0 » pour les compteurs (vraies valeurs) ; « — » pour taux et note (« Pas encore de donnée ») |
| « Radar des attributs » | `RadarChart` 1 série, axes servis par l'API (`club-carte-joueur.md` B3.3), échelle 0 à 10, valeurs écrites dans la légende | Moins de 3 axes : « Pas assez d'attributs pour tracer le radar. » ; aucune évaluation : « Pas encore de donnée » |
| « Forme récente » | 5 dernières notes (séances et matchs, 4.2 « Aperçu ») : mini `BarChart` + liste « {date} · {Séance / Match contre X} · {7,0} » | « Aucune note pour l'instant. » |
| « Présences » | « {17} séances sur {20} · {85} % », « {2} retards », « {1} absence excusée » | « Aucune séance pointée cette saison. » |
| « Discipline » | Cartons de la saison avec leur cause (4.2 « Discipline ») : 3 derniers + « Voir plus » ; suspension en cours : « Suspendu : encore {n} match(s) », **seulement pour les rôles du 10.2 n° 16 et le joueur lui-même** (voir la note ci-dessous) | « Aucun carton cette saison. » |
| « Aptitude » | Seulement pour Coach, Assistant, Président, VP, DS, Médecin et le joueur lui-même (10.2 n° 16) : `StatusBadge` « Apte » (vert) / « Apte avec restriction » (orange) / « Inapte » (rouge) + « retour prévu le {date} » ; **jamais de diagnostic** (règle 11) | « Aucune information d'aptitude. » |
| « Tests de performance » | Si la partie C de `sport-statistiques-seance.md` est validée : meilleur résultat par test, visible selon C3 de cette fiche (staff et le joueur lui-même seulement) | Section masquée |

**Note sur la suspension (10.2 n° 16)** : le n° 16 réserve le motif d'indisponibilité (dont « Suspendu ») au staff et au joueur ; les coéquipiers ne voient que « Indisponible ». Or le 4.2 met « Discipline : cartons avec leur cause, suspensions » dans la fiche détaillée, et les statistiques sportives sont publiques. **Position provisoire, la plus prudente** : les cartons et leur cause sont affichés à tous (statistique sportive, publique au 4.2) ; la **suspension en cours** n'est affichée qu'aux rôles du n° 16 et au joueur lui-même ; pour les autres, rien (pas même « Indisponible » : ce n'est pas une page de disponibilité). Contradiction à faire trancher (Q3).

**Ce que voit un simple coéquipier** : carte, six indicateurs, radar (club interne : oui, voir Q4), forme récente, présences, cartons. Pas d'aptitude, pas de suspension en cours, pas de statut d'adhésion autre que celui que l'API sert déjà filtré (`club-carte-joueur.md` point ouvert 3).

### 4.3 Fiche détaillée et comparaison

- « Voir la fiche détaillée » ouvre la fiche du 4.2 (Aperçu, Statistiques, Évaluations, Présences, Discipline, Carrière, Aptitude), spec à venir `club-fiche-detaillee.md` (`club-carte-joueur.md` B2.5). Tant qu'elle n'existe pas, le bouton n'est pas affiché ; le panneau et la fiche mobile suffisent.
- « Comparer » / « Comparer avec… » : modale existante `club-carte-joueur.md` B3, inchangée.

## 5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Barre de progression + 6 squelettes de carte `sm` (`Skeleton variant="player-card"`) avec leur bande | — | « Impossible de charger les cartes des joueurs. » + « Réessayer » |
| Grille filtrée | — | « Aucun joueur ne correspond à ces filtres. » + « Réinitialiser les filtres » | — |
| Recherche | Indicateur 16 px dans le champ | « Aucun joueur trouvé. » | — |
| Club sans autre joueur | — | « Vous êtes le seul joueur du club pour l'instant. » | — |
| Panneau / fiche | Squelette de carte `md` + 6 tuiles + radar | Statistiques à zéro : valeurs réelles « 0 » / « — » ; jamais de valeur inventée (CLAUDE.md §3) | « Impossible de charger les statistiques de {prénom}. » + « Réessayer » (la carte reste affichée) |
| Photo | Fond de zone photo réservé | Silhouette (`club-carte-joueur.md` A4.4) | Silhouette |
| Joueur parti pendant la consultation | — | — | « Ce joueur ne fait plus partie du club. » dans le panneau |
| Hors connexion | Dernière version en cache + « Données du {heure} » ; recherche locale seulement | — | — |

## 6. Mobile (360 px) et ordinateur — vérifications

- 360 px : 2 cartes par ligne sans débordement ; nom de 40 caractères sur 2 lignes sans coupure dans la carte `sm` ; bande de statistiques sur 2 lignes au plus ; aucun défilement horizontal de la page (seul le tableau défile dans son cadre).
- Thèmes Classic, Clair et Sombre : la carte suit les tokens de `club-carte-joueur.md` A6 ; la bande de statistiques est hors de la carte, sur `--color-surface`, en `--color-text`.
- Images : 24 photos par page ; chargement différé (`loading="lazy"`), taille réservée. Proposition (`club-carte-joueur.md` point ouvert 9) : vignette servie par l'API (`photo_thumb`, 320 px) pour la grille, original seulement dans la carte `md`.
- ≥ 1024 px : panneau collant ; la carte `md` et les statistiques tiennent dans la hauteur d'un écran de 768 px (radar 240 px).

## 7. Données et API (noms proposés pour `backend-dev`)

Les statistiques de la carte (`club-carte-joueur.md` B1) **ne sont pas encore servies** : `GET /api/v1/clubs/players/{id}/card/` ne renvoie que l'identité, et `PlayerComparisonModal` affiche « — » pour cette raison. Cette page en dépend.

- `GET /api/v1/clubs/players/cards/?search=&position=&status=active|left&availability=&season=&ordering=&limit=24&offset=` → `{ count, results: [{ membership_id, first_name, last_name, photo, photo_thumb, jersey_number, position, position_label, overall_rating | null, stats: { matches_played, goals, assists, yellow_cards, red_cards, attendance_rate | null, average_rating | null }, availability: null | { label, family } }], season_label }`. `availability` n'est rempli que pour les rôles du 10.2 n° 16 ; le filtre `availability` est refusé (400) pour les autres.
- `GET /api/v1/clubs/players/{id}/stats/?season=` → `{ stats, radar: { axes: [{ key, label, value | null }] }, recent_form: [{ date, event_type, label, rating }], attendance: { sessions_expected, sessions_present, late, excused }, discipline: { cards: [...], active_suspension: null | {...} }, fitness: null | { status, label, return_date }, performance: null | [...] , season_label }` — `active_suspension` et `fitness` filtrés par rôle côté API ; aucun champ financier, médical détaillé, poids, taille ni téléphone dans le sérialiseur (test à prévoir).
- Calculs dans `apps/sport/services.py` (statistiques, forme, présence) ; `overall_rating` reste `null` tant que sa formule n'est pas tranchée (`club-carte-joueur.md` point ouvert 4) ; axes du radar selon le point ouvert 12.
- Permissions : `IsActiveClubMember` ; isolation par club (managers tenant-aware), joueur d'un autre club → 404.
- Aucune migration, sauf la vignette `photo_thumb` si elle est retenue (champ image ou génération à l'envoi, 6.7).

## 8. Journal et notifications

Page de lecture : aucune entrée de journal, aucune notification.

## 9. Questions pour le client

1. **Q1 — Affichage par défaut** : « Cartes » (demande du client) plutôt que le tableau imposé par 3.3 au-delà de 30 joueurs ; la grille a recherche, filtres et pagination, et le tableau reste à un toucher. Écart à valider.
2. **Q2 — Libellé et place du menu** : « Cartes des joueurs » dans le groupe « Club ».
3. **Q3 — Suspension en cours sur la fiche** : contradiction entre le 4.2 (discipline et suspensions dans la fiche, statistiques publiques) et le 10.2 n° 16 (motif réservé au staff). Position provisoire : cartons pour tous, suspension en cours pour le staff et le joueur seulement.
4. **Q4 — Radar visible par les coéquipiers** : il est calculé à partir des évaluations (« P » pour le joueur dans la matrice 2.4). À l'intérieur du club, le 4.2 le place sur la fiche ouverte au clic, donc visible ; à confirmer, avec le point ouvert 13 de `club-carte-joueur.md` pour l'extérieur.
5. **Q5 — Note moyenne et forme récente pour les coéquipiers** : la note moyenne fait partie des six indicateurs publics de la carte (4.2) ; la forme récente (5 dernières notes) est dans l'« Aperçu » de la fiche. Les deux sont donc affichées à tous ; à confirmer, car elles dérivent des évaluations.
6. **Q6 — Anciens joueurs** : faut-il pouvoir consulter les cartes des joueurs partis (filtre « Anciens joueurs ») ? Proposition : oui, en lecture.
