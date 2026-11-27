# Écran — Tableau de bord du club (Président et Vice-président)

Sources : CDC 2.2, 2.4 (matrice : Président et VP lisent paiements, grille, dépenses, matériel ; « É » sur évaluations et validation des dépenses ; santé : aptitude seulement), 3 (charte), 4.1 (premier accès), 4.4.2 (solde calculé), 4.4.6 (indicateurs de trésorerie), 4.5 (dépenses, non justifiées), 4.7, 4.8, 4.9, 4.10, 4.12, 4.13, 4.15, 4.16, 6.5 (pas de WebSocket), 7.5, 10.2 n° 15 et 16, CLAUDE.md règles 2, 3, 11, 16 à 19. Demande du client : `remarques.md` l. 88, décidée le 15/11/2026. Écrans liés : `club-accueil.md` (reste l'accueil de tous), `tresorerie-tableau-de-bord.md`, `tresorerie-depenses-assistance.md`, `sport-statistiques-seance.md`, `medical.md`, `logistique.md`, `assemblees-page-ag.md`.

> **NOUVEAU (circuit 9.4, à valider)** : toute la page, la redirection à la connexion et les composants de graphiques. Le CDC ne prévoit pour le Président que la mise en avant du vestiaire sur l'accueil (4.7) et, pour la trésorerie, les indicateurs du 4.4.6.

## 1. Objectif

Donner au Président et au Vice-président, en 30 secondes sur smartphone, l'état du club : l'effectif, l'assiduité, l'argent, les résultats, la discipline, ce qui arrive. Chaque graphique est une porte d'entrée : un toucher ouvre le détail dans une modale. La page **lit** ; elle ne remplace aucune page de module et ne porte aucun formulaire de module.

## 2. Accès et arrivée à la connexion

Route `/tableau-de-bord`. Entrée de barre latérale **« Tableau de bord du club »**, premier élément du premier groupe (au-dessus de « Accueil »), visible **seulement** pour le Président et le Vice-président (union des rôles, 2.2 : un VP également Trésorier la voit aussi). L'API renvoie le droit (`capabilities.can_view_board_dashboard` dans le profil) ; l'interface ne le déduit pas d'un rôle.

| Rôle | Accès |
| --- | --- |
| Président, Vice-président | Lecture de toute la page |
| Autres rôles | Pas d'entrée de menu ; l'URL directe affiche la page standard « Cette page est réservée au Président et au Vice-président. » + lien « Retour à l'accueil » ; l'API répond 403 |
| Superuser | Pas d'entrée (il n'est pas joueur) ; en Ghost Mode dans un club, il voit la page comme le Président (5.4) |

**Arrivée directe** :

1. Après une connexion réussie (`ConnexionPage`), si le profil a le droit ci-dessus et qu'**aucune adresse de suite** (`?suite=`, lien de notification, lien partagé) n'est demandée, l'utilisateur est envoyé sur `/tableau-de-bord` au lieu de `/`. Une adresse de suite l'emporte toujours.
2. **Premier accès d'abord** : les modales bloquantes du premier accès (« Changez votre mot de passe », « Vos données et votre consentement », `club-accueil.md` §3) passent **avant** le tableau de bord, exactement comme avant l'accueil. Comme elles sont aujourd'hui portées par l'accueil, elles doivent être déplacées au niveau de la mise en page commune (`AppLayout`) pour s'appliquer quelle que soit la page d'arrivée. Point bloquant pour `frontend-dev` : sans ce déplacement, un Président à sa première connexion contournerait le changement de mot de passe obligatoire (7.1).
3. Réouverture de l'application avec une session encore valide (application installée, onglet rouvert) : arrivée sur `/tableau-de-bord` aussi (proposition : c'est l'adresse de départ « par défaut » du Président). À confirmer (Q2).
4. L'**Accueil** reste accessible par le menu (« Accueil ») et garde tout son contenu (communiqués, vestiaire du jour, ma situation…). Le tableau de bord renvoie vers l'accueil par un lien « Voir l'accueil » dans la ligne de contexte.
5. Le Président et le VP perdent la page dès qu'ils perdent le rôle (révocation, passation) : à la connexion suivante, ils arrivent sur l'accueil.

## 3. Structure de la page

**En-tête** : titre « Tableau de bord du club » ; contexte « {nom du club} · {novembre 2026} · Mis à jour à {08:12} » et lien « Voir l'accueil ». Pas d'action principale (page de lecture).

**Filtre de période** (collant sous l'en-tête sur mobile, 44 px) :

- `SegmentedControl` « Mois » / « Saison » ;
- en « Mois » : sélecteur à flèches « ‹ novembre 2026 › » (boutons de 40 px ; pas de mois futur) ;
- en « Saison » : « Saison {2026-2027} » (saison des paramètres du club, 4.9) avec flèches vers les saisons précédentes.
- Le filtre s'applique à toutes les cartes qui ont une période (§4) ; les cartes « instantanées » (effectif aujourd'hui, suspensions en cours, aptitude, matériel à retourner, prochaines échéances) l'ignorent et l'écrivent : « Aujourd'hui ».

**Bandeaux** (si applicable, repris de l'accueil) : dépense non justifiée qui bloque les libérations (alerte rouge, 4.5.2) ; licence proche de l'expiration ; hors connexion (« Données du {heure} »).

**Cartes**, dans l'ordre de priorité du §4. Chaque carte est un `ChartCard` (§6) : titre 16 px/600, chiffre clé 20 px, une phrase de lecture 14 px, un graphique simple, un lien « Voir le détail ». **Toute la carte est cliquable** (zone tactile = la carte) et ouvre la modale de détail.

Footer.

## 4. Cartes proposées et priorisées

Priorité **P1** = demandé par le client ; **P2** = proposé, forte valeur pour une vue globale ; **P3** = proposé, utile, livrable ensuite. Le client choisit (Q1).

| # | Carte | Prio | Source des données (calcul par l'API) | Période | Lecture (graphique adapté à 360 px) | Confidentialité |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Présences** | P1 | Pointages des séances (4.7) : taux par séance, moyenne de la période ; mêmes définitions que `sport-statistiques-seance.md` A4.1 | Mois / Saison | Chiffre clé « 74 % de présence moyenne » ; `LineChart` du taux par séance (10 points max.) | Données d'équipe, « L » pour le bureau |
| 2 | **Cotisations** | P1 | Trésorerie (4.4.2, 4.4.6) : encaissé, dû échu, taux de recouvrement = encaissé ÷ dû échu (types obligatoires seulement, règle 2 ; cotisations libres comptées à part, jamais en dette, règle 3) | Mois / Saison | Chiffre clé « 82 % recouvré » + « {1 240 $} encaissés » ; `BarChart` vertical encaissé par mois (6 mois à 360 px, 12 sur ordinateur) avec la ligne « dû » en repère | Pdt et VP « L » sur paiements et grille |
| 3 | **Nouveaux venus** | P1 | Adhésions (4.3) dont la date d'inscription tombe dans la période ; à part, adhésions « En attente » (parrain, frais) | Mois / Saison | Chiffre clé « 3 nouveaux joueurs en novembre » ; avatars 32 px des 5 premiers ; mini `BarChart` des arrivées par mois | Identité seulement |
| 4 | **Résultats** | P1 | Matchs joués (4.8) : victoires, nuls, défaites, buts pour / contre | Mois / Saison | Bande de forme des 5 derniers matchs (`FormStrip` : « V », « N », « D » écrits dans des pastilles) ; « {7} V · {2} N · {3} D · {24} buts marqués, {15} encaissés » | Public |
| 5 | **Discipline** | P1 | Incidents (4.9) : cartons jaunes, rouges, sanctions internes ; suspensions en cours | Mois / Saison (+ suspensions « Aujourd'hui ») | Chiffre clé « {2} joueurs suspendus » ; `BarChart` empilé jaunes / rouges par mois ; texte « {11} jaunes, {1} rouge sur la période » | Cause visible (le bureau a « L » sur incidents) |
| 6 | **Situation de l'effectif** | P2 | Statut calculé de chaque joueur actif : en ordre, en dette (solde calculé, règle 2), en attente d'adhésion, suspendu ; partis exclus | Aujourd'hui | `StackedBar` horizontal 100 % (jamais de camembert : illisible à 360 px et en plein soleil), segments aux couleurs fixes de statut (vert, rouge, orange, violet) **avec libellé et nombre écrits** | Dette : Pdt / VP « L » sur la grille ; aucun montant individuel sur la carte |
| 7 | **Caisse : encaissements et dépenses** | P2 | Paiements validés et dépenses libérées (4.4.6, 4.5) ; caisse disponible = encaissements − dépenses libérées | Mois / Saison | Chiffre clé « Caisse disponible : {860 $} » ; `BarChart` groupé par mois (encaissé / dépensé, deux tracés distincts + légende texte) | Finances du club, « L » pour Pdt et VP |
| 8 | **Dépenses par catégorie** | P2 | Dépenses libérées par catégorie (4.5.1) ; compteurs « à valider » et « non justifiées » | Mois / Saison | `BarChart` horizontal trié (5 catégories + « Autres ») ; ligne d'alerte « {1} dépense non justifiée » (badge orange « À justifier ») | Bénéficiaire d'une assistance sociale **non affiché** sur la carte (seulement dans la modale, comme sur la page Dépenses) |
| 9 | **Évolution de l'effectif** | P2 | Nombre de joueurs actifs en fin de mois ; arrivées et départs | 12 derniers mois (ou saison) | `LineChart` de l'effectif + texte « +3 arrivées, −1 départ sur la période » | Identité seulement |
| 10 | **Aptitude de l'effectif** | P2 | Module médical (4.12) : nombre d'aptes, aptes avec restriction, inaptes ; date de retour prévue | Aujourd'hui | `StackedBar` vert / orange / rouge + liste des inaptes avec « retour prévu le {date} » | **Jamais de diagnostic** (règle 11, 10.2 n° 15 et 16), **même si le joueur a donné son consentement au Président** : le dossier complet ne se consulte que dans le module médical, où chaque consultation est journalisée |
| 11 | **Prochaines échéances** | P2 | Matchs à venir (4.8), prochaine séance, AG convoquée (4.15), échéance de licence | Aujourd'hui → 30 jours | Liste de 5 lignes datées (pas de graphique) | — |
| 12 | **Assiduité par joueur** | P3 | Taux de présence individuel sur la période | Mois / Saison | Deux listes « Les plus assidus » / « Les moins assidus » (5 chacune, barres fines horizontales avec le pourcentage écrit) | Données d'équipe |
| 13 | **À traiter** | P3 | Dépenses à valider, demandes d'assistance à traiter, PV à signer, adhésions bloquées | Aujourd'hui | Compteurs cliquables (pas de graphique) | Ce que Pdt / VP traitent déjà ; recoupe la carte « À faire » de l'accueil, **reportée après le Lot 5** : à décider (Q4) |
| 14 | **Matériel à retourner** | P3 | Logistique (4.13) : prêts en cours et en retard ; **en retard** = plus de 7 jours (`EQUIPMENT_OVERDUE_AFTER_DAYS`) écoulés depuis la date du match (sinon du prêt) sans retour, le modèle n'ayant pas d'échéance de retour (décidé le 16/11/2026) | Aujourd'hui | Chiffre clé « {4} articles à retourner » + 5 lignes (article, joueur, depuis) | Pdt et VP « L » sur matériel |
| 15 | **Notes du Coach** | P3 | Note moyenne de l'équipe, séances et matchs (4.10) : note retenue par joueur et par événement, moyenne de chaque joueur sur la période, puis moyenne des moyennes par joueur (CDC 10.3 n° 190) | Mois / Saison | `LineChart` 0 à 10 | Pdt et VP sont évaluateurs (« É ») |
| 16 | **Activité du fil** | P3 | Publications et réactions du club (4.16) | Mois | Chiffre clé « {12} publications » + `BarChart` par semaine | Public |
| 17 | **Tests de performance** | P3 | `sport-statistiques-seance.md` partie C (si validée) | Saison | Meilleur résultat par test | Données sportives, jamais de santé |

**Ordre à l'écran** (360 px) : 1 Présences, 2 Cotisations, 6 Situation de l'effectif, 7 Caisse, 4 Résultats, 5 Discipline, 3 Nouveaux venus, 10 Aptitude, 11 Prochaines échéances, 8 Dépenses par catégorie, 9 Évolution de l'effectif, puis les P3. Raison : ce qui demande une décision du bureau (argent, effectif disponible) avant ce qui s'informe.

**Aucun montant individuel** sur une carte : les montants par joueur n'apparaissent que dans les modales (le Président et le VP y ont droit, matrice 2.4), et l'écran peut être vu par-dessus l'épaule au bord du terrain.

## 5. Modales de détail (une par carte)

Toutes : taille `lg`, plein écran sur mobile, pied « Fermer » (lecture seule, pas de confirmation d'abandon). En-tête : titre de la carte + période (« Cotisations · novembre 2026 »). Le filtre de période est **repris dans la modale** et modifiable sans la fermer. Chaque modale contient, dans l'ordre : le graphique en grand, un bouton « Voir les données » (tableau des valeurs, accessibilité), puis la liste ou le tableau du détail. Un toucher sur un élément (barre, point, segment) filtre la liste du dessous sur cet élément (« Novembre 2026 » → paiements de novembre). Les listes suivent 3.3 (N derniers + « Voir plus », `DataTable` au-delà de 30). Un clic sur une ligne ouvre la modale de détail existante du module, au niveau 2 (détail d'un paiement, d'un match, d'un incident…), sans quitter le tableau de bord.

| Carte | Contenu de la modale | Liens vers les modules |
| --- | --- | --- |
| 1 Présences | Courbe du taux par séance ; tableau des séances (date, présents, retards, excusés, absents, taux) ; clic → modale « Séance » onglet « Statistiques » | « Ouvrir les entraînements » |
| 2 Cotisations | Barres par mois ; par type de cotisation : dû, encaissé, taux ; liste des 20 derniers paiements (« Voir plus ») ; joueurs en dette triés par montant (nom, montant dû) | « Ouvrir la trésorerie » |
| 3 Nouveaux venus | Liste : avatar, nom, poste, date d'inscription, parrain ; à part « En attente d'adhésion ({n}) » avec l'étape (« Frais non payés », « Signature du parrain attendue ») ; clic → « Fiche du joueur » | « Ouvrir Comité et bureau » |
| 4 Résultats | Tous les matchs de la période (5 + « Voir plus ») : date, adversaire, score, résultat ; totaux ; meilleurs buteurs et passeurs de la période (5) | — |
| 5 Discipline | Suspensions en cours (joueur, matchs restants) ; incidents de la période (5 + « Voir plus ») avec cause ; joueurs les plus sanctionnés (5) | — |
| 6 Situation de l'effectif | Onglets « En ordre » / « En dette » / « En attente » / « Suspendus » ; ligne : avatar, nom, et pour « En dette » le montant (Pdt / VP « L ») | « Ouvrir la grille des cotisations » |
| 7 Caisse | Barres groupées ; tableau par mois : encaissé, dépensé, solde du mois, caisse cumulée | « Ouvrir la trésorerie » |
| 8 Dépenses | Barres par catégorie ; liste des dépenses de la période (statut en badge : « En attente », « Libérée », « Justifiée », « Non justifiée ») ; clic → détail de la dépense (validation possible depuis cette modale existante, qui garde sa propre confirmation, 7.2) | « Ouvrir les dépenses » |
| 9 Évolution de l'effectif | Courbe ; liste des arrivées et des départs de la période | — |
| 10 Aptitude | Trois listes : « Inaptes » (avatar, nom, « retour prévu le {date} »), « Apte avec restriction », « Aptes » (repliée) ; **aucun diagnostic, aucune circonstance de blessure** ; mention 13 px « Le détail médical n'est visible que par le Médecin et le joueur. » | Aucun lien vers un dossier médical depuis cette modale |
| 11 Échéances | Liste sur 30 jours ; clic → détail du match, de la séance ou de l'AG | — |
| 12 Assiduité | `DataTable` triable de tous les joueurs (présences, retards, excusés, absences, taux), recherche | — |
| 13 À traiter | Liste des éléments ; clic → modale d'action existante du module | — |
| 14 Matériel | Prêts en cours : article, quantité, joueur, depuis, « en retard de {n} jours » ({n} = jours au-delà du délai de 7 jours) | « Ouvrir le matériel » |

## 6. Composants du design system (à créer)

**Constat** (recherche dans `frontend/src/design-system/` et `frontend/package.json`, 15/11/2026) : **aucune bibliothèque de graphiques n'est installée** et le design system n'a **aucun composant de graphique** ; les tokens `--color-series-*` prévus par `club-carte-joueur.md` B3.3 n'existent pas encore dans `tokens.css` ; le radar de la comparaison n'est pas dessiné (`PlayerComparisonModal.tsx` affiche un état vide).

**Proposition** : graphiques en **SVG écrit à la main** dans le design system, sans bibliothèque. Raisons : réseau faible au bord du terrain (une bibliothèque complète pèse plusieurs dizaines de ko compressés pour 5 formes simples), contrôle total des couleurs de thème et du contraste, cohérence avec le radar déjà spécifié en SVG. Si le client ou l'équipe préfère une bibliothèque, c'est une décision à prendre (Q6).

| Composant | Rôle | Propriétés principales |
| --- | --- | --- |
| `ChartCard` | Carte cliquable : titre, chiffre clé, phrase de lecture, emplacement du graphique, lien « Voir le détail », états chargement / vide / erreur intégrés | `title`, `value`, `caption`, `onOpen`, `state`, `emptyMessage`, `periodLabel` |
| `KpiTile` | Tuile chiffre clé (valeur 20 px tabulaire, libellé 13 px sur 2 lignes max., pastille de statut facultative) | `label`, `value`, `hint`, `family?` |
| `LineChart` | Courbe d'une série (deux au plus), points marqués, ligne de référence en tirets, trous pour les valeurs absentes | `points[{x,label,value|null}]`, `yMin`, `yMax`, `unit`, `reference?`, `onPointPress` |
| `BarChart` | Barres verticales ou horizontales, simples, groupées (2 séries) ou empilées ; valeur écrite sur chaque barre | `orientation`, `series`, `stacked`, `onBarPress` |
| `StackedBar` | Barre 100 % horizontale à segments, légende textuelle obligatoire | `segments[{label,value,family}]`, `onSegmentPress` |
| `FormStrip` | 5 pastilles « V / N / D » avec texte, lecteur d'écran « Victoire contre {adversaire}, {3-1} » | `results[]` |
| `RadarChart` | Radar 3 à 8 axes, 1 à 4 séries (spec `club-carte-joueur.md` B3.3, à extraire ici) | `axes`, `series` |
| `PeriodPicker` | `SegmentedControl` Mois / Saison + flèches | `value`, `onChange`, `seasons` |

**Règles communes** (tokens dans `tokens.css`, aucune couleur en dur, aucune couleur de club dans les séries) :

- Couleurs : séries `--color-series-1` à `-4` (valeurs de `club-carte-joueur.md` B3.3, contrôlées ≥ 3:1 sur `--color-surface` en Clair, Sombre et Classic) ; segments de statut : les familles de `StatusBadge` (vert, orange, rouge, violet, gris) — **jamais réutilisées** pour autre chose qu'un statut. Grille et axes : `--color-border` ; libellés `--color-text-muted`, 13 px.
- Deux séries se distinguent aussi par le tracé (plein / tirets) ou le motif (barre pleine / hachurée), jamais par la couleur seule ; légende textuelle toujours visible.
- Valeurs écrites sur le graphique (au moins la dernière et la référence) : en plein soleil, on lit un chiffre, pas une nuance.
- Pas de camembert, pas d'anneau, pas de 3D, pas de dégradé, pas d'animation au-delà d'une entrée de 200 ms (coupée par `prefers-reduced-motion`).
- Accessibilité : `<figure>` + `<figcaption>` ; `role="img"` et `aria-label` résumant la lecture (« Taux de présence : 74 % en moyenne, dernière séance 72 % ») ; « Voir les données » affiche un `<table>`.
- Toucher = action ; le survol n'apporte qu'une info-bulle de confort sur ordinateur.
- Taille : largeur fluide (100 % du cadre), hauteur fixe 160 px dans une carte, 220 px dans une modale ; libellés d'axe jamais tronqués (rotation interdite : on espace les étiquettes).
- Squelette : `Skeleton variant="chart"` (rectangle à la hauteur du graphique).

Ces composants servent aussi à `sport-statistiques-seance.md` et à `club-cartes-joueurs.md`.

## 7. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Barre de progression + squelettes de 4 cartes (chiffre clé + graphique) | — | Chaque carte gère son erreur ; si tout échoue : « Impossible de charger le tableau de bord. » + « Réessayer » |
| Présences | Squelette | « Aucune séance sur la période. » | « Impossible de charger les présences. » + « Réessayer » |
| Cotisations | Squelette | « Aucune cotisation due sur la période. » | Idem modèle |
| Nouveaux venus | Squelette | « Aucun nouveau joueur ce mois-ci. » / « … cette saison. » | Idem |
| Résultats | Squelette | « Aucun match joué sur la période. » | Idem |
| Discipline | Squelette | « Aucun carton ni suspension sur la période. » | Idem |
| Situation de l'effectif | Squelette | — (toujours au moins le Président) | Idem |
| Caisse | Squelette | « Aucun mouvement de caisse sur la période. » | Idem |
| Dépenses | Squelette | « Aucune dépense sur la période. » | Idem |
| Aptitude | Squelette | « Tous les joueurs sont aptes. » (si aucun inapte ni restriction) ; sans module médical renseigné : « Aucune information d'aptitude enregistrée. » | Idem |
| Échéances | 3 lignes | « Rien de prévu dans les 30 prochains jours. » | Idem |
| Matériel | 3 lignes | « Aucun matériel à retourner. » | Idem |
| Période sans données (mois futur impossible ; mois avant la création du club) | — | Flèche « › » désactivée sur le mois en cours ; flèche « ‹ » désactivée sur le mois de création du club | — |
| Rafraîchissement | Interrogation toutes les 5 min tant que l'onglet est actif (6.5 ; pas de besoin de temps réel), et au retour sur l'onglet ; « Mis à jour à {heure} » | — | « Mise à jour impossible · {heure} » (orange) + « Réessayer », sans toast |
| Hors connexion | Dernière version en cache + bandeau « Données du {heure} » | — | — |

## 8. Mobile (360 px) et ordinateur

**360 px** : une colonne, marges 12 px, cartes empilées dans l'ordre du §4, filtre de période collant. Chaque carte fait au plus 260 px de haut (titre, chiffre clé, une phrase, graphique de 160 px). Les graphiques à barres montrent 6 mois au plus ; au-delà, défilement horizontal dans leur cadre.

```
┌──────────────────────────────────────┐
│ Tableau de bord du club               │ 20 px
│ {Club} · novembre 2026 · Voir l'accueil│ 14 px
│ [ Mois | Saison ]   ‹ novembre 2026 › │ 44 px collant
├──────────────────────────────────────┤
│ Présences                     Voir ›  │ 16 px/600
│ 74 % de présence moyenne              │ 20 px
│ Dernière séance 72 % · 4 séances      │ 14 px
│  ╭─╮    ╭──●  (courbe 160 px)         │
│ ─┴─┴────┴───  Moyenne 74 %            │
├──────────────────────────────────────┤
│ Cotisations                   Voir ›  │
│ 82 % recouvré · 1 240 $ encaissés     │
│ ▇ ▇ ▆ ▇ ▅ ▇  (6 mois)                 │
├──────────────────────────────────────┤
│ Situation de l'effectif       Voir ›  │
│ ███████████▓▓▓░░▒                     │
│ En ordre 24 · En dette 6 · En attente 2 · Suspendus 1 │
├──────────────────────────────────────┤
│ …                                     │
└──────────────────────────────────────┘
```

**≥ 768 px** : grille de 2 colonnes de cartes. **≥ 1280 px** : 3 colonnes. Toutes les cartes ont la même largeur (grille simple, hauteur alignée par ligne) ; les P1 occupent les deux premières lignes. Le filtre de période n'est plus collant : il reste dans l'en-tête, à droite du titre. Les modales passent en taille `lg` (800 px), graphique au-dessus, tableau en dessous.

## 9. Règles métier, journal, notifications

- Aucune règle n'est calculée par l'interface : chaque chiffre vient de l'API, qui réutilise les services existants (solde calculé `apps/treasury/services.py`, jamais un champ stocké, règle 2 ; cotisations libres jamais en dette, règle 3 ; aptitude du module médical sans diagnostic, règle 11).
- Les définitions sont identiques à celles des modules : un taux de recouvrement, une caisse disponible ou un taux de présence affichés ici doivent être **égaux** à ceux des pages Trésorerie et Entraînements pour la même période (critère d'acceptation à tester). Période commune aux deux écrans : la saison en cours ou choisie ; la vue « Mois » du tableau de bord n'a pas d'équivalent sur la page « Entraînements », dont les périodes sont « 10 dernières séances » et « Saison ». Une séance de la saison est celle dont la date tombe dans les dates de la saison. Une séance sans aucun pointage s'affiche « Non pointée » sur les deux écrans, sans compteurs de présence. Pour la présence : taux par séance arrondi à l'unité (A4.1 de `sport-statistiques-seance.md`), servi en chaîne (« 34 »), et moyenne de la période selon la définition unique du CDC 10.3 n° 185 (séances seulement, séance non pointée exclue). Le tableau de bord n'a pas de calcul propre : il appelle la fonction de `apps/sport`. Pour les notes : définition unique du CDC 10.3 n° 190 (`apps.sport.session_stats.summarize_ratings`) ; la valeur « séances seules » du tableau de bord est égale à la note moyenne de la page « Entraînements » pour la même saison.
- La page ne crée, ne modifie ni ne supprime rien : **aucune entrée de journal** pour sa consultation. Les actions faites depuis une modale de module ouverte au niveau 2 (par exemple valider une dépense) journalisent comme d'habitude, dans leur module.
- Aucune notification nouvelle.
- Devise : celle du club, servie par l'API ; montants en `Decimal` côté API, affichés au format du club.

## 10. Données et API (noms proposés pour `backend-dev` et `finance-engine`)

- `GET /api/v1/clubs/board-dashboard/?period=month&month=2026-11` ou `?period=season&season={id}` → un objet par carte : `{ attendance, contributions, newcomers, results, discipline, squad_status, cash, expenses_by_category, squad_trend, fitness, upcoming, attendance_ranking, to_process, equipment_out }`. **Un seul appel** pour la page (réseau faible : un aller-retour au lieu de quinze) ; chaque section peut valoir `{ "error": "…" }` sans faire échouer les autres.
- `GET /api/v1/clubs/board-dashboard/{section}/?period=…&limit=&offset=` → détail paginé d'une carte pour sa modale.
- Permission : `IsPresidentOrVicePresident` (nouvelle), sur ces deux endpoints. Club actif déduit de l'adhésion (règle 9), managers tenant-aware (règle 8), test d'étanchéité entre clubs.
- Sections financières (`contributions`, `squad_status`, `cash`, `expenses_by_category`) : calculées par `finance-engine` dans `apps/treasury/services.py` (fonctions de lecture dédiées, par exemple `board_contributions_summary(club, period)`).
- Section `fitness` : servie par `apps/medical/services.py` avec **les seuls champs** aptitude et date de retour, par une fonction qui n'a pas accès au diagnostic (même filtre que la vue Coach), y compris quand un consentement existe.
- Profil : `capabilities.can_view_board_dashboard` et `default_landing` (`"board_dashboard"` ou `"home"`) pour la redirection à la connexion.
- **Aucune migration** (lecture seule), sauf si le client retient l'historique de l'effectif par mois (carte 9) : il se recalcule à partir des dates d'adhésion et de départ, sans table nouvelle.

**Positions DÉCIDÉES (recommandations acceptées par le client le 16/11/2026) :**

- **Taux de recouvrement** = dû couvert ÷ dû échu (types obligatoires seulement), comme la page Trésorerie.
- **Statut « Suspendu »** prioritaire sur « En dette » dans la situation de l'effectif.
- **Droits** : Président et Vice-président seulement (Trésorier, Secrétaire et Directeur sportif exclus).
- **Prochaines échéances financières** : carte servie sous la clé `upcoming_finance`.
- **Matériel en retard** : plus de 7 jours depuis la date du match (sinon du prêt) sans retour (`EQUIPMENT_OVERDUE_AFTER_DAYS = 7` dans `apps/clubs/board_dashboard.py`) ; `overdue_days` = jours au-delà de ce délai.

### 10.1 Contrat API financier

Implémenté par `finance-engine` dans `backend/apps/treasury/dashboard.py` (fonctions pures de lecture, aucune écriture, aucune entrée de journal, aucune vue : l'endpoint est branché dans `apps/clubs`, qui porte la permission Président / VP). Tests : `backend/apps/treasury/tests/test_dashboard.py`.

- `finance_cards(club, period) -> dict` : valeurs des cartes 2, 6, 7, 8 et des échéances financières, à placer dans la réponse de `GET /api/v1/clubs/board-dashboard/` sous les clés du même nom.
- `finance_section(club, section, period, *, limit=20, offset=0, only=None) -> dict` : détail d'une carte pour sa modale. `section` ∈ `contributions`, `squad_status`, `cash`, `expenses_by_category`, `upcoming_finance`. `limit` (1 à 100) et `offset` (≥ 0) paginent chaque liste ; `only` (nom d'une liste) ne renvoie que cette liste (« Voir plus »).
- **Période** (contrat du `PeriodPicker`) : `{"mode": "month", "month": "AAAA-MM"}` ou `{"mode": "season", "season_id": 3}` ; `null` = mois en cours dans le fuseau du club. Une saison est arrondie aux mois entiers. Mois futur, mois mal formé, saison d'un autre club : `TreasuryValidationError` (message en français, à renvoyer en 400).
- **Erreurs par carte** : si une carte échoue de façon inattendue, `finance_cards` renvoie pour elle `{"error": "Impossible de charger la caisse."}` (et équivalents) sans faire échouer les autres.
- Montants : chaînes à 2 décimales dans la devise du club (`currency`) ; taux : chaînes en pourcentage à 2 décimales, ou `null` s'il n'y a pas de dénominateur.

**Définitions** (identiques à la page Trésorerie, une seule source dans `apps/treasury/services.py`) :

| Valeur | Définition |
| --- | --- |
| `collected` | Paiements validés et scellés moins les annulations approuvées (l'annulation porte la date de valeur du paiement d'origine), tous types, date de valeur dans la période. Ventilé en `collected_mandatory` / `collected_free` (libres comptées à part, jamais en dette) |
| `due_total` | Montants dus générés pour les mois de la période (types obligatoires), échus ou non |
| `matured_due_total`, `matured_due_covered`, `collection_rate` | Dus **échus aujourd'hui** (échéance + tolérance) des mois de la période ; part couverte par la répartition 4.4.3, plafonnée au dû ; taux = couvert ÷ échu (identique à l'indicateur 4.4.6) |
| `squad_status` | Aujourd'hui : adhésions non parties. « En attente » = adhésion en attente ; sinon « En dette » si le solde calculé est négatif, « En ordre » sinon. Le statut « Suspendu » relève de `apps/sport` et n'est pas calculé ici |
| `cash.spent` | Dépenses libérées (date de libération dans la période) ; `available_cash` = encaissements − dépenses libérées, aujourd'hui, tous mouvements |
| `expenses_by_category` | Dépenses libérées dans la période par catégorie (5 + « Autres » sur la carte) ; `pending_*`, `unjustified_count`, `release_blocked` : aujourd'hui (`can_release_expense`) |
| `upcoming_finance` | Aujourd'hui → 30 jours : montants dus pas encore échus restant à couvrir (par type et date d'échéance ; `debt_on` = jour où ils deviennent dette) et justificatifs de dépense attendus |

**`finance_cards`** :

```json
{
  "period": {"mode": "month", "month": "2026-11", "season_id": null, "label": "novembre 2026",
             "start": "2026-11-01", "end": "2026-11-30", "months": ["2025-12", "…", "2026-11"]},
  "currency": "USD",
  "contributions": {
    "collected": "17.00", "collected_mandatory": "14.00", "collected_free": "3.00",
    "due_total": "30.00", "matured_due_total": "30.00", "matured_due_covered": "14.00",
    "collection_rate": "46.67",
    "series": [{"month": "2026-11", "label": "novembre 2026", "collected": "17.00",
                "matured_due_total": "30.00", "matured_due_covered": "14.00", "collection_rate": "46.67"}]
  },
  "squad_status": {"as_of": "2026-11-15", "total": 10,
                   "in_good_standing": {"count": 7, "rate": "70.00"},
                   "in_debt": {"count": 2, "rate": "20.00", "amount": "26.00"},
                   "pending": {"count": 1, "rate": "10.00"}},
  "cash": {"collected": "10.00", "spent": "8.00", "net": "2.00", "available_cash": "19.00",
           "series": [{"month": "2026-11", "label": "novembre 2026", "collected": "10.00", "spent": "8.00"}]},
  "expenses_by_category": {
    "total_spent": "8.00",
    "categories": [{"category_id": 3, "name": "Transport", "amount": "5.00", "count": 1},
                   {"category_id": null, "name": "Autres", "amount": "3.00", "count": 2}],
    "pending_count": 1, "pending_amount": "40.00", "unjustified_count": 1,
    "release_blocked": true,
    "release_blocked_reason": "Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée."
  },
  "upcoming_finance": {
    "as_of": "2026-11-15", "until": "2026-12-15", "count": 2,
    "items": [
      {"kind": "contribution_due", "date": "2026-11-20", "debt_on": "2026-11-21",
       "label": "Échéance « Mensuelle 10 »", "contribution_type_id": 4, "players_count": 6, "amount": "60.00"},
      {"kind": "expense_justification", "date": "2026-11-22",
       "label": "Justificatif attendu : Arbitrage", "expense_id": 9, "amount": "12.00"}
    ]
  }
}
```

En mode « Mois », les séries couvrent les 12 mois se terminant au mois choisi ; en mode « Saison », les mois de la saison jusqu'au mois en cours (jamais de mois futur). La carte ne contient **aucun montant individuel** ni bénéficiaire de dépense.

**`finance_section`** : toujours `{"section": "…", "period": {…}, "currency": "USD", …}` ; une liste paginée vaut `{"items": [...], "count": 12, "next_offset": 20 | null}`.

| `section` | Clés supplémentaires |
| --- | --- |
| `contributions` | `summary` (carte sans `series`), `series`, `by_type` : `[{"contribution_type_id", "name", "nature": "mandatory" \| "free", "nature_label", "collected", "due_total", "matured_due_total", "matured_due_covered", "collection_rate"}]` (champs de dû `null` pour un type libre) ; `payments` (liste : `payment_id`, `paid_on`, `membership_id`, `player_name`, `contribution_type_id`, `contribution_type_name`, `nature`, `amount`, `status` `validated` \| `cancelled`, `status_label` « Validé » \| « Annulé »), tri date de valeur décroissante ; `debtors` (liste + `as_of` : `membership_id`, `player_name`, `amount_due`), tri montant dû décroissant |
| `squad_status` | `summary` (carte) ; listes `in_good_standing`, `pending` (`membership_id`, `player_name`) et `in_debt` (+ `amount_due`), tri par nom (dette : montant décroissant) |
| `cash` | `summary` (carte sans `series`) ; `opening_cash` (caisse avant le premier mois affiché) ; `months` : `[{"month", "label", "collected", "spent", "net", "cash_end"}]` (caisse cumulée en fin de mois) |
| `expenses_by_category` | `summary` (carte sans `categories`) ; `categories` (toutes, sans regroupement) ; `expenses` (liste des dépenses dont la date tombe dans la période, refusées exclues : `expense_id`, `expense_date`, `category_id`, `category_name`, `amount`, `beneficiary_name`, `status`, `status_label`, `justification_deadline`, `is_overdue`) |
| `upcoming_finance` | `upcoming` : `{"as_of", "until", "items", "count", "next_offset"}` |

Montants individuels : seulement `amount_due` des joueurs en dette, dans les modales (fiche §5 cartes 2 et 6 ; Q5 ouverte).

## 11. Tableaux de bord pour d'autres rôles (option, non spécifiée)

Question au client (Q7), **sans spécification à ce stade** :

- **Trésorier et Trésorier adjoint** : ils ont déjà le tableau de bord de la trésorerie (4.4.6). Option : y ajouter les cartes 2, 6, 7 et 8 avec les mêmes graphiques, sans nouvelle page.
- **Coach et Assistant** : l'Espace coach (`sport-espace-coach.md`) et la page « Entraînements » (`sport-statistiques-seance.md` partie B) couvrent l'essentiel. Option : cartes 1, 4, 5, 10, 12 et 15 dans l'Espace coach.
- **Directeur sportif** : option : cartes 1, 4, 5, 9, 12, 15 et 17, sans aucune carte financière (le DS n'a aucun accès à la trésorerie, matrice 2.4) et avec l'aptitude seulement (10.2 n° 16).

Si le client le souhaite, chaque option devient une demande 9.4 à part, réutilisant les mêmes composants et les mêmes endpoints filtrés par rôle.

## 12. Questions pour le client

1. **Q1 — Cartes retenues** : valider les P1 et choisir parmi les P2 et P3 (§4).
2. **Q2 — Arrivée directe** : seulement après la saisie du mot de passe, ou aussi à chaque réouverture de l'application ? Proposition : les deux.
3. **Q3 — Libellé du menu** : « Tableau de bord du club » (proposé, pour le distinguer du « Tableau de bord » de la Trésorerie).
4. **Q4 — Carte « À traiter »** : elle recoupe la carte « À faire » de l'accueil, reportée après le Lot 5. L'avancer pour le Président et le VP seulement ?
5. **Q5 — Montants individuels** : la liste des joueurs en dette avec leur montant est dans la modale (droit « L » du Président et du VP). La garder ou n'afficher que des totaux ?
6. **Q6 — Bibliothèque de graphiques** : SVG maison (proposé) ou bibliothèque externe ?
7. **Q7 — Tableaux de bord pour d'autres rôles** (§11) : utiles ? lesquels ?
8. **Q8 — Vice-président et aptitude** : la matrice 2.4 lui donne « — » sur les fiches de santé, mais le 10.2 n° 16 lui ouvre l'aptitude. La carte 10 lui est montrée (aptitude seule) en application du n° 16 ; à confirmer.
