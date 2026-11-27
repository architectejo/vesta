# Lot 0 — Design system Vesta

Spec de référence pour `frontend/src/design-system/`. Aucun code n'est écrit au Lot 0 : ce document fixe les tokens et le comportement des composants communs. `frontend-dev` implémente à partir de lui ; toute page doit utiliser ces composants avant d'en créer d'autres (CLAUDE.md §7).

Sources : cahier des charges chapitre 3 (3.1 à 3.6), 4.4.7, 4.7, 4.11, 6.6, 7.2 ; CLAUDE.md §2 « Interface ».

Usage de référence : un trésorier ou un coach, au bord du terrain le dimanche, sur un smartphone de 360 px, en plein soleil, avec un réseau faible. Chaque choix ci-dessous se justifie par cet usage.

---

## 1. Principes de mise en page

### 1.1 Anatomie d'une page

Toute page suit le même ordre, sans exception :

1. **En-tête de page** (`PageHeader`) : titre (20 px mobile, 24 px à partir de 1024 px, jamais plus), ligne de contexte (nom du club venant de l'API, période), puis au plus **une** action principale et une action secondaire ; les autres actions vont dans le menu « … ».
2. **Bandeaux d'état** éventuels (hors connexion, lecture seule, alerte rouge, session de support).
3. **Sections en cartes** (`Card`), dans l'ordre « consulter d'abord, agir ensuite ».
4. **Footer** unique (voir 3.10).

Une page ne contient jamais de formulaire complet : uniquement des boutons qui ouvrent des modales (3.2). Seules exceptions tolérées dans une page : un champ de recherche/filtre de liste, un interrupteur de préférence à effet immédiat, et les boutons d'action unitaire (ex. « Arrivé » au pointage).

### 1.2 Grille et points de rupture

| Nom | Largeur min. | Mise en page |
| --- | --- | --- |
| `base` | 360 px | 1 colonne, marges latérales 12 px, barre latérale en tiroir |
| `sm` | 640 px | 1 colonne, marges 16 px ; les modales deviennent des fenêtres centrées |
| `md` | 768 px | 2 colonnes possibles pour les cartes courtes (indicateurs, résumés) |
| `lg` | 1024 px | Barre latérale fixe de 248 px ; contenu 2 colonnes (8/4) si utile |
| `xl` | 1280 px | Contenu limité à 1200 px de large, centré |

Aucune page ne défile horizontalement. Seuls les tableaux défilent horizontalement, dans leur propre cadre (3.3).

### 1.3 Règles de densité (3.1)

- Texte courant 14 px (listes, tableaux) ou 16 px (lecture, champs de saisie).
- Boutons 36 px (dans les listes, tableaux, en-têtes de carte) ou 40 px (pieds de modale, en-tête de page). Jamais plus de 40 px.
- Zones tactiles ≥ 44 × 44 px sur mobile : obtenues par une marge de clic invisible (pseudo-élément ou padding), pas en agrandissant le bouton.
- Pas de boutons pleine largeur sur ordinateur. Sur mobile, seuls les boutons du pied de modale occupent la largeur (deux boutons côte à côte).
- Pas d'illustrations décoratives, pas de bannières d'accueil, pas de chiffres géants : les indicateurs clés sont à 20–24 px au maximum.

---

## 2. Tokens

Tous les tokens sont des variables CSS déclarées sur `:root` et surchargées par thème via l'attribut `data-theme` sur `<html>` (`classic`, `light`, `dark`). Tailwind lit ces variables (`colors.surface = 'rgb(var(--color-surface) / <alpha-value>)'`), aucune couleur n'est écrite en dur dans un composant.

### 2.1 Typographie

Police : pile système, pour ne rien télécharger sur un réseau faible.
`--font-sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;`
Les montants, numéros de maillot, heures et colonnes chiffrées utilisent `font-variant-numeric: tabular-nums`.

| Token | Taille / interligne | Usage |
| --- | --- | --- |
| `--text-xs` | 13 px / 18 px | Badges, aide sous un champ, message d'erreur de champ, en-têtes de colonnes, footer |
| `--text-sm` | 14 px / 20 px | Texte courant par défaut : listes, tableaux, cartes, boutons |
| `--text-base` | 16 px / 24 px | Champs de saisie (évite le zoom automatique iOS), texte de lecture (communiqués, consignes), titres de carte |
| `--text-lg` | 18 px / 26 px | Titre de modale |
| `--text-xl` | 20 px / 28 px | Titre de page sur mobile, chiffre d'un indicateur sur mobile |
| `--text-2xl` | 24 px / 32 px | Titre de page à partir de 1024 px, chiffre d'un indicateur sur ordinateur. **Maximum absolu.** |

Graisses : 400 (texte), 500 (libellés, boutons), 600 (titres). Pas de 700 ou plus. Pas de majuscules continues sauf sigles.

### 2.2 Espacements, rayons, tailles

| Token | Valeur | Usage |
| --- | --- | --- |
| `--space-1` | 4 px | Écart icône / texte |
| `--space-2` | 8 px | Écart entre éléments d'une ligne |
| `--space-3` | 12 px | Marge de page mobile, padding de carte mobile, écart entre cartes mobile |
| `--space-4` | 16 px | Padding de carte ≥ 640 px, écart entre champs d'un formulaire |
| `--space-5` | 20 px | Écart entre sections d'une modale |
| `--space-6` | 24 px | Marge de page ≥ 1024 px |
| `--space-8` | 32 px | Espace avant le footer |
| `--radius-sm` | 6 px | Boutons, champs, badges de grille |
| `--radius-md` | 8 px | Cartes, menus |
| `--radius-lg` | 12 px | Modales (coins supérieurs seulement pour le panneau bas) |
| `--radius-full` | 999 px | Badges de statut, avatars |
| `--control-h-sm` | 36 px | Bouton compact, champ de recherche de liste |
| `--control-h-md` | 40 px | Bouton standard, champ de formulaire |
| `--touch-min` | 44 px | Zone tactile minimale |
| `--row-h` | 48 px | Hauteur minimale d'une ligne de liste ou de tableau (56 px avec avatar 40 px) |
| `--sidebar-w` | 248 px | Barre latérale fixe (≥ 1024 px) |
| `--topbar-h` | 56 px | Barre supérieure mobile |
| `--icon-sm` / `--icon-md` | 16 px / 20 px | Icônes (un seul jeu d'icônes linéaires pour toute l'application) |

Ombres : une seule élévation pour les cartes (`0 1px 2px rgb(0 0 0 / .06)`), une pour les modales et menus (`0 8px 24px rgb(0 0 0 / .18)`). Pas d'autre effet.

Mouvements : 150 ms (survol, focus), 200 ms (ouverture de modale). Tout est coupé si `prefers-reduced-motion: reduce`.

Couches (`z-index`) : contenu 0, en-tête collant 10, barre latérale mobile 40, modale niveau 1 : 50, modale niveau 2 : 60, toast 70.

### 2.3 Couleurs neutres par thème

Objectif « plein soleil » (3.6) : texte principal ≥ 7:1 sur son fond, texte secondaire ≥ 4.5:1 (visé 7:1), bordures de champs ≥ 3:1. Le gris clair (type `#9CA3AF`) n'est **jamais** utilisé pour du texte lisible, seulement pour un élément désactivé.

| Variable | Clair (`light`) | Sombre (`dark`) | Usage |
| --- | --- | --- | --- |
| `--color-bg` | `#F4F5F7` | `#0B1220` | Fond de page |
| `--color-surface` | `#FFFFFF` | `#111A2B` | Cartes, modales, tableaux |
| `--color-surface-muted` | `#EEF0F3` | `#1A2438` | En-têtes de tableau, zones secondaires, cellule « à venir » |
| `--color-border` | `#E1E5EB` | `#26324A` | Séparateurs décoratifs |
| `--color-border-strong` | `#7B8699` | `#6B7A94` | Bordures de champs et de cases à cocher (≥ 3:1) |
| `--color-text` | `#111827` | `#F3F4F6` | Texte principal |
| `--color-text-muted` | `#4B5563` | `#B8C1CE` | Ligne de contexte, aides, libellés secondaires |
| `--color-text-disabled` | `#9CA3AF` | `#5E6B80` | Éléments désactivés uniquement |
| `--color-primary` | `#1D4ED8` | `#60A5FA` | Bouton principal, lien, élément actif (hors Classic) |
| `--color-on-primary` | `#FFFFFF` | `#0B1220` | Texte sur `--color-primary` |
| `--color-primary-text` | `#1D4ED8` | `#93C5FD` | Liens et textes d'accent sur `--color-surface` |
| `--color-focus` | `#2563EB` | `#93C5FD` | Anneau de focus clavier (2 px, décalé de 2 px) |
| `--color-overlay` | `rgb(17 24 39 / .55)` | `rgb(0 0 0 / .65)` | Voile derrière une modale |
| `--color-skeleton` | `#E3E6EB` | `#1F2A3D` | Blocs gris des squelettes |
| `--color-sidebar-bg` | `#FFFFFF` | `#0F1829` | Fond de la barre latérale |
| `--color-sidebar-text` | `#111827` | `#F3F4F6` | Texte de la barre latérale |

### 2.4 Thème Classic : couleurs du club (3.6)

Le thème Classic garde les neutres du thème Clair (lisibilité en plein soleil) et applique les couleurs du club **aux accents seulement** : fond de la barre latérale, bouton principal, élément de navigation actif, liens, onglet actif, liseré d'en-tête des PDF.

**Principe d'extraction** (pas d'algorithme figé) :

1. Au téléversement du logo (modale « Identité du club », Président), le serveur ou le navigateur analyse les pixels non transparents et non quasi blancs/noirs du logo et propose les deux teintes dominantes les plus saturées : **principale** (la plus présente) et **secondaire** (la plus éloignée de la principale).
2. Les deux couleurs proposées s'affichent en pastilles dans la modale ; le Président les accepte ou les corrige (sélecteur de couleur + saisie hexadécimale). Les couleurs retenues sont enregistrées dans l'identité du club et **servies par l'API** avec le nom et le logo. Aucune couleur de club n'est écrite dans le code.
3. L'interface dérive ensuite, au chargement, les variables de lisibilité :
   - `--club-primary`, `--club-secondary` : valeurs brutes de l'API.
   - `--color-sidebar-bg` = `--club-primary` ; `--color-sidebar-text` = blanc ou `#111827`, celui qui offre le meilleur contraste ; si aucun n'atteint 4.5:1, la teinte du fond est assombrie par pas jusqu'à l'atteindre.
   - `--color-primary` (fond du bouton principal) = `--club-primary`, ajustée de la même manière pour que `--color-on-primary` atteigne 4.5:1.
   - `--color-primary-text` (liens sur fond blanc) = `--club-primary` assombrie si besoin jusqu'à 4.5:1 sur `--color-surface`.
   - `--color-accent` = `--club-secondary`, utilisée seulement pour des éléments non textuels (liseré de l'élément actif de navigation, anneau d'avatar du joueur connecté).
4. Club sans logo ni couleurs : Classic retombe sur les valeurs du thème Clair. Aucun nom ni couleur par défaut propre à un club.
5. Les couleurs du club **ne remplacent jamais** les couleurs de statut (2.5). Si la couleur du club est proche d'une couleur de statut (club rouge ou vert), les badges restent lisibles parce qu'ils portent toujours un libellé et une pastille (jamais la couleur seule).

**Choix du thème** : propre à chaque utilisateur, mémorisé côté API (préférence du compte) et en `localStorage` pour le premier affichage sans flash. Thème par défaut à la première connexion : Classic. Le sélecteur est dans le menu utilisateur du bas de la barre latérale (« Thème : Classic, Clair, Sombre »).

### 2.5 Couleurs de statut (fixes, 3.4)

Cinq familles, identiques dans tous les thèmes (seule la luminance s'adapte au fond). Le texte du badge atteint ≥ 7:1 sur son fond de badge.

| Famille | Pastille (tous thèmes) | Clair / Classic : fond — texte | Sombre : fond — texte |
| --- | --- | --- | --- |
| `success` (vert) | `#16A34A` | `#DCFCE7` — `#14532D` | `#14532D` — `#BBF7D0` |
| `warning` (orange) | `#EA580C` | `#FFEDD5` — `#7C2D12` | `#7C2D12` — `#FED7AA` |
| `danger` (rouge) | `#DC2626` | `#FEE2E2` — `#7F1D1D` | `#7F1D1D` — `#FECACA` |
| `suspended` (violet) | `#9333EA` | `#F3E8FF` — `#581C87` | `#581C87` — `#E9D5FF` |
| `neutral` (gris) | `#6B7280` | `#F3F4F6` — `#1F2937` | `#374151` — `#E5E7EB` |

Variables : `--status-<famille>-dot`, `--status-<famille>-bg`, `--status-<famille>-fg`. Le bouton destructeur (`danger`) utilise `#B91C1C` en fond avec texte blanc (6.5:1).

**Correspondance statut → couleur.** Les lignes marquées « 3.4 » sont imposées par le cahier des charges ; les autres sont des **propositions à valider par le client** (le 3.4 ne les couvre pas).

| Libellé affiché | Famille | Source |
| --- | --- | --- |
| En ordre, Validé, Présent | vert | 3.4 |
| En attente, À justifier | orange | 3.4 |
| En dette, Refusé, Absent, Inapte | rouge | 3.4 |
| Suspendu | violet | 3.4 |
| Parti, Archivé | gris | 3.4 |
| Inscrit | vert | Proposition (état transitoire avant calcul du solde) |
| Blessé | rouge | Proposition (un blessé est inapte, 4.12 étape 3) |
| Apte | vert | Proposition |
| Apte avec restriction | orange | Proposition |
| En retard (compté absent) | rouge | Proposition (c'est une absence, 4.7) |
| Absent excusé | gris | Proposition (absence distinguée dans les stats, 4.7) |
| À valider (déclaration « J'ai payé », annulation demandée) | orange | Proposition (équivaut à « En attente ») |
| Annulé (paiement annulé par écriture) | gris | Proposition |
| En attente d'envoi (hors connexion) | orange | Proposition |
| Dépense : En attente / Libérée / Justifiée / Non justifiée / Refusée | orange / vert / vert / rouge / rouge | Proposition |
| Séance ou match : Ouverte / Verrouillée | vert / gris | Proposition |
| Composition : Brouillon / Publiée | orange / vert | Proposition |
| Défi entre clubs : En attente / Accepté / Refusé | orange / vert / rouge | Proposition |
| Offre de transfert : En attente / Acceptée / Refusée / Bloquée (dette) / Transfert effectué | orange / vert / rouge / rouge / vert | Proposition |
| AG : Convoquée / PV à signer / Clôturée | orange / orange / vert | Proposition |
| Licence : Essai / Active / Expirée (grâce) / Suspendue / Résiliée | vert / vert / orange / violet / gris | Proposition |
| Mercato : Sur le marché / Fermé aux offres | vert / gris | Proposition |
| Poste vacant | gris | Proposition |

### 2.6 Couleurs de la grille des cotisations (4.4.7)

Même palette que les statuts, appliquée en fond de cellule avec le montant en texte :

| État de cellule | Famille | Contenu affiché |
| --- | --- | --- |
| Payé | vert | Montant affecté |
| Partiel | orange | Montant affecté (ex. « 5 ») + pastille orange |
| Impayé échu | rouge | « 0 » + pastille rouge |
| À venir | `--color-surface-muted` | « — » |

Les cellules ne reposent jamais sur la seule couleur : la pastille (forme pleine, demi, vide) et le montant portent l'information pour les daltoniens et en plein soleil.

### 2.7 Couleurs de maillot (PitchBoard, 4.7)

Palette fermée (pas de couleur libre, pour garantir la lisibilité du numéro) :

| Nom | Fond | Texte du numéro |
| --- | --- | --- |
| Bleu (défaut A) | `#1D4ED8` | blanc |
| Rouge (défaut B) | `#DC2626` | blanc |
| Blanc | `#FFFFFF` (bordure `#111827`) | `#111827` |
| Noir | `#111827` | blanc |
| Jaune | `#FACC15` | `#111827` |
| Vert | `#15803D` | blanc |
| Orange | `#EA580C` | blanc |
| Violet | `#7C3AED` | blanc |
| Gris | `#6B7280` | blanc |
| Bleu ciel | `#38BDF8` | `#111827` |

Terrain : pelouse `--pitch-grass` `#2E7D32` (Sombre : `#1F5A24`), lignes `--pitch-line` `rgb(255 255 255 / .85)`. Chaque pion porte une bordure blanche de 2 px pour se détacher de la pelouse.

---

## 3. Composants

Pour chaque composant : rôle, anatomie, comportement mobile et ordinateur, états, accessibilité, textes. Les noms de propriétés sont indicatifs pour `frontend-dev`.

### 3.1 Composants de base (utilisés par tous les autres)

- **Button** : variantes `primary` (fond `--color-primary`), `secondary` (bordure `--color-border-strong`, fond surface), `ghost` (texte `--color-primary-text`, sans fond), `danger`. Tailles `sm` 36 px et `md` 40 px. Icône facultative à gauche (16 px). État `loading` : icône remplacée par un indicateur rotatif de 16 px, libellé remplacé par le libellé en cours (« Enregistrement… »), bouton désactivé. Une seule `primary` par zone (en-tête de page, carte, pied de modale).
- **IconButton** : 40 × 40 px visibles, zone tactile 44 px, `aria-label` obligatoire en français (« Fermer », « Ouvrir le menu », « Notifications »).
- **Menu « … »** : `IconButton` qui ouvre un menu déroulant (ordinateur) ou un panneau bas (mobile) listant les actions secondaires, lignes de 44 px.
- **Card** : fond surface, rayon 8 px, padding 12 px (16 px ≥ 640 px). En-tête : titre 16 px/600, compteur facultatif en `--text-muted` (« 5 sur 23 »), action de carte facultative à droite (bouton `sm` secondaire ou ghost). Pied facultatif : bouton ghost « Voir plus » pleine largeur de la carte, 40 px.
- **PageHeader** : titre `h1`, ligne de contexte (`--text-sm`, `--color-text-muted`, format « {nom du club} · {période} »), zone d'actions (à droite ≥ 640 px ; sous la ligne de contexte sur mobile, alignée à gauche, largeur automatique).
- **Champs de formulaire** (dans les modales uniquement) : libellé au-dessus (14 px/500), champ de 40 px, texte 16 px, bordure `--color-border-strong`. Les champs facultatifs portent la mention « (facultatif) » dans le libellé ; pas d'astérisques. Aide en dessous (13 px, muted). Erreur en dessous (13 px, `--status-danger-fg`, icône), le champ prend une bordure rouge, `aria-invalid` et `aria-describedby`. Types : `TextField`, `TextArea` (hauteur auto, 3 lignes min.), `MoneyField` (devise du club affichée en suffixe, clavier numérique, séparateur décimal virgule accepté), `NumberField` avec boutons − / +, `DateField` et `TimeField` natifs, `FileField` (bouton « Choisir un fichier » + « Prendre une photo » sur mobile, aperçu, formats JPEG, PNG, WebP, PDF, 10 Mo maximum, compression des photos dans le navigateur avant envoi, 6.7), `SegmentedControl` (2 à 4 options exclusives, préféré au select), `Checkbox`, `Switch`, `Select` natif (uniquement pour des listes courtes non-joueurs : type de cotisation, poste, fuseau). **Aucun `Select` ne liste des joueurs** : voir PlayerSearch.
- **Avatar** : photo ronde (24, 32, 40 ou 72 px) ; à défaut, initiales sur fond `--color-surface-muted`. Affiché partout où un nom de joueur apparaît (3.4). Une action faite en Ghost Mode s'affiche avec l'avatar « V » et le nom « Système Vesta » (5.4).
- **Tabs** : onglets horizontaux, 40 px, défilement horizontal si trop nombreux, onglet actif souligné en `--color-primary`. Utilisés dans les modales de détail et, sur la page Séance, comme bascule de vues.
- **Toast** : message bref après une action réussie (« Paiement enregistré. »), 4 secondes, `aria-live="polite"`. Mobile : en bas, au-dessus de la zone sûre ; ordinateur : en haut à droite. Peut porter une action « Annuler » quand l'action est réversible (déplacement A/B). Jamais utilisé pour une erreur de champ.
- **ConfirmDialog** : modale `sm` (panneau bas sur mobile) pour toute suppression ou action irréversible (3.4). Titre sous forme de question (« Révoquer Jean K. du rôle de Trésorier ? »), une phrase de conséquence, boutons « Annuler » (focus par défaut) et verbe explicite en `danger` (« Révoquer »). Jamais « OK » ni « Oui ».
- **Modale de confirmation d'une action sensible** (7.2) : variante de `ConfirmDialog` ; elle remplace `PinPrompt`, supprimé le 11/10/2026 (10.3 n° 177). Modale `sm` / panneau bas. Titre en question qui rappelle l'objet (« Valider le paiement de {montant} pour {nom} ? »), une phrase de conséquence, boutons « Annuler » (focus par défaut) et verbe explicite (« Valider », « Signer », « Libérer »). Variante `danger` pour une annulation ou une dérogation. Aucun champ de saisie, aucun code, aucun verrouillage.
- **KpiTile** : libellé (13 px, muted), valeur (20 px mobile, 24 px ordinateur, tabular-nums), variation ou précision facultative (13 px). Grille 2 × 2 sur mobile, 4 colonnes ≥ 1024 px.
- **ListSection** : liste des N derniers éléments d'une carte (3.3) : lignes de 48 à 56 px entièrement cliquables (ouvrent une modale de détail), bouton « Voir plus » qui ajoute les N suivants en place (le bouton passe en « Chargement… »), disparaît quand tout est affiché. N par défaut : 5 (séances, matchs, incidents), 20 (paiements), 10 (notifications).
- **Banner** : bandeau pleine largeur sous l'en-tête de page. Variantes : `danger` (alerte rouge : dépense non justifiée, rupture de chaîne), `warning` (licence en période de grâce), `info` (hors connexion), `readonly` (licence expirée : « La licence du club a expiré : le club est en lecture seule. Vos données restent consultables et exportables. »), `support` (session Superuser, voir espace Superuser).
- **SyncIndicator** (6.6) : pastille dans la barre supérieure. Masquée si rien n'est en attente. Sinon « {n} action(s) en attente d'envoi » (orange) ; hors connexion « Hors connexion — {n} en attente » ; au clic, modale listant les actions en file avec leur heure réelle, et les conflits signalés : « Votre saisie pour {nom} n'a pas été retenue : une autre saisie est arrivée avant. »
- **NotificationBell** (3.4, 4.17) : icône cloche 40 px avec compteur de non-lues (pastille rouge, « 9+ » au-delà de 9). Ouvre une modale « Notifications » : 10 dernières, « Voir plus », bouton « Tout marquer comme lu » en en-tête. Un clic sur une notification ferme la modale et mène à l'élément concerné (page + modale de détail). État vide : « Aucune notification. » Mise à jour par interrogation toutes les 30 s, suspendue si l'onglet est inactif (6.5).

### 3.2 Modal (3.2)

**Rôle** : contenir tout formulaire, toute modale de détail d'un élément, toute confirmation.

**Tailles**

| Taille | Largeur ordinateur | Mobile (< 640 px) | Usage |
| --- | --- | --- | --- |
| `sm` | 400 px | Panneau bas (hauteur selon contenu, 90 % max.) | Confirmation, choix court |
| `md` | 560 px | Plein écran | Formulaire standard (défaut) |
| `lg` | 800 px | Plein écran | Détail avec onglets, composition, grille d'un joueur |
| `xl` | 960 px | Plein écran | Assistant pas à pas, Caisse Terrain Express, évaluation rapide |

Sur ordinateur : centrée, hauteur maximale 90 vh, voile `--color-overlay`.

**Anatomie** (toutes tailles)

1. **En-tête** fixe : titre (18 px/600, `id` relié à `aria-labelledby`), sous-titre facultatif (13 px muted, ex. nom du joueur concerné), bouton croix à droite (`IconButton` « Fermer », zone 44 px). Sur un panneau bas, une poignée de 32 × 4 px au-dessus du titre.
2. **Corps** défilant (`overflow-y: auto`) : champs en une colonne sur mobile ; deux colonnes seulement pour des champs courts appariés (date + heure) à partir de 640 px. Un bandeau d'erreur globale s'affiche en haut du corps si l'erreur ne concerne aucun champ.
3. **Pied** fixe, toujours visible même quand le corps défile et quand le clavier virtuel est ouvert (hauteur calculée sur `visualViewport` / `100dvh`) : « Annuler » (secondaire) à gauche, action principale à droite (« Enregistrer » par défaut ; verbe précis quand il est plus clair : « Envoyer la demande », « Publier », « Encaisser »). Mobile : deux boutons de 40 px se partageant la largeur. Ordinateur : alignés à droite, largeur automatique. Les modales de détail (consultation) ont pour pied « Fermer » + éventuellement une action principale (« Modifier »), les actions destructrices étant dans le menu « … » de l'en-tête.

**Fermeture**

- Déclencheurs : croix, touche Échap, clic sur le voile (uniquement si l'appui ET le relâchement ont lieu sur le voile, pour ne pas fermer en sélectionnant du texte), bouton « Annuler », glissement vers le bas d'un panneau bas, bouton retour d'Android (l'ouverture ajoute une entrée d'historique ; le retour ferme la modale au lieu de quitter la page).
- Si le formulaire est modifié (`isDirty`) : tout déclencheur ouvre un `ConfirmDialog` « Abandonner les modifications ? » — texte « Les informations saisies seront perdues. » — boutons « Continuer la saisie » (focus par défaut) et « Abandonner » (danger).
- Pendant l'enregistrement : fermeture impossible, champs désactivés, bouton principal en état `loading`.

**Soumission**

1. Validation locale au clic sur le bouton principal (pas à chaque frappe) ; ensuite, revalidation du champ en erreur à chaque modification.
2. Erreurs sous le champ concerné, en français clair (3.2). Le corps défile jusqu'au premier champ en erreur et lui donne le focus.
3. Erreurs de l'API : chaque erreur de champ renvoyée est placée sous le bon champ ; une erreur générale va dans le bandeau d'erreur du corps. Aucun code ni message technique n'est affiché.
4. Action sensible : le bouton principal ouvre la modale de confirmation au-dessus (niveau 2). Une fois confirmée, la requête part.
5. Succès : fermeture de la modale, `Toast` bref, mise à jour de la page sans rechargement (invalidation ciblée des requêtes), focus rendu à l'élément qui avait ouvert la modale.

**Empilement** : deux niveaux au plus (détail → formulaire, formulaire → confirmation). Un formulaire ouvert depuis une modale de détail ramène à ce détail, mis à jour, après enregistrement. Au-delà de deux niveaux, le contenu du niveau 2 est remplacé (bouton « Retour » dans l'en-tête).

**Variante assistant** (`Wizard`, 3.2 exception) : taille `xl`. Sous le titre, indicateur « Étape {n} sur {total} — {nom de l'étape} » et barre de progression fine. Pied : « Annuler » à gauche ; « Précédent » (secondaire, masqué à l'étape 1) et « Suivant » / verbe final à droite. Validation étape par étape ; la confirmation d'abandon s'applique à tout l'assistant.

**Variante à onglets** (ex. « Modifier mon profil ») : chaque onglet a son propre bouton « Enregistrer » ; changer d'onglet avec des modifications non enregistrées ouvre la confirmation d'abandon.

**Modale bloquante** (cas unique : changement obligatoire du mot de passe initial, 4.1 et 7.1) : pas de croix, Échap et voile inactifs ; seule issue secondaire : « Se déconnecter ».

**Chargement** : une modale de détail affiche un squelette dans son corps pendant le chargement ; le titre est affiché dès l'ouverture si connu.

**Accessibilité** : `role="dialog"`, `aria-modal="true"`, focus piégé, focus initial sur le premier champ (formulaire) ou sur le titre (détail), retour du focus à la fermeture, arrière-plan `inert`.

**Textes standards** : « Fermer », « Annuler », « Enregistrer », « Enregistrement… », « Abandonner les modifications ? », « Les informations saisies seront perdues. », « Continuer la saisie », « Abandonner ».

### 3.3 DataTable (3.3, 4.4.7)

**Rôle** : toute liste pouvant dépasser 30 éléments (joueurs, transferts, marché, journal, utilisateurs), et la grille des cotisations.

**Anatomie**

1. **Barre d'outils** : champ de recherche 36 px avec icône loupe (placeholder contextuel, ex. « Rechercher un joueur »), bouton « Filtres » avec compteur de filtres actifs, action d'export facultative (« Exporter (CSV) », secondaire). Sous la barre : filtres actifs en puces supprimables et lien « Effacer les filtres ». Ligne de résultat : « {n} joueurs » (13 px, muted).
2. **Cadre défilant** : `overflow-x: auto` sur le seul cadre, jamais sur la page. Dégradé d'ombre sur le bord droit (et gauche après défilement) pour signaler du contenu caché. En-tête de colonnes collant en haut du cadre quand le tableau a sa propre hauteur.
3. **Colonnes figées** : option `stickyColumns` (0, 1 ou 2). Par défaut, la première colonne « Joueur » (avatar 24 px + nom) est figée dans tous les tableaux de joueurs ; obligatoire pour la grille des cotisations.
4. **Lignes** : hauteur ≥ 48 px, entièrement cliquables (`onRowClick` → modale de détail), focusables au clavier (Entrée ouvre). Aucun bouton d'action dans les lignes : les actions sont dans la modale de détail (3.3). Survol : fond `--color-surface-muted`.
5. **Pagination** : 20 lignes par page par défaut (50 pour la grille), « Précédent » / « Suivant » et « {début}–{fin} sur {total} ». Sur mobile, seulement les deux boutons et le compteur.

**Filtres** : ordinateur, menu ancré sous le bouton ; mobile, panneau bas `sm` avec « Effacer » et « Appliquer ». Types : choix multiple en cases, plage numérique (âge, note), plage de dates, recherche d'un club (suggestions). Les filtres et la recherche sont appliqués côté API (debounce 300 ms sur la recherche) et reflétés dans l'URL pour survivre au retour arrière.

**Tri** : en-têtes cliquables avec flèche et `aria-sort`. Tri par défaut défini par chaque écran.

**Cellules** : texte 14 px, retour à la ligne autorisé sur deux lignes (pas de troncature des noms) ; nombres et montants alignés à droite en tabular-nums ; statuts en `StatusBadge`.

**Variante grille** (`variant="grid"`, 4.4.7) : cellules de 56 px de large minimum (72 px pour « Total »), 44 px de haut, fond coloré selon 2.6, cellule cliquable (ouvre la modale « détail du mois »). Première colonne figée de 120 px sur mobile, 200 px sur ordinateur. Défilement initial automatique pour que le mois courant soit visible.

**États** : chargement = 5 lignes squelettes ; vide sans filtre = `EmptyState` de l'écran ; vide avec filtre = « Aucun résultat pour « {recherche} ». » + bouton « Effacer les filtres » ; erreur = `EmptyState` variante erreur avec « Réessayer ».

### 3.4 PlayerSearch (3.3)

**Rôle** : seul moyen de choisir un ou plusieurs joueurs. **Aucune liste déroulante `<select>` de joueurs n'existe dans Vesta.**

**Anatomie** : champ 40 px (texte 16 px), icône loupe, placeholder « Nom ou numéro du joueur ». Liste de suggestions sous le champ : jusqu'à 8 lignes de 56 px comprenant avatar 40 px, nom complet, « n° {numéro} · {poste} », `StatusBadge` du statut pertinent, et une information de contexte à droite fournie par l'écran (`renderMeta`), par exemple le solde dans la Caisse Terrain Express.

**Comportement**

- Recherche dès le premier caractère, debounce 250 ms, sur le nom, le prénom et le numéro (un nombre saisi remonte d'abord le joueur portant exactement ce numéro).
- Portée : `club` (défaut, joueurs du club actif seulement) ou `public` (mercato, comparaison : affiche en plus le nom du club).
- Filtre de contexte transmis à l'API (ex. `eligibleFor="match:{id}"`, `role="parrain"`) : les joueurs non éligibles restent **visibles mais grisés**, non sélectionnables (`aria-disabled`), avec la raison venant de l'API, filtrée par l'API selon le rôle (ex. « Non éligible », « Suspendu : encore {n} match(s) », « Inapte · retour prévu le {date} », « En attente d'adhésion » ; « En dette : {montant} » seulement pour le Président et le Vice-président, ainsi que pour le joueur lui-même ; le Trésorier lit « Indisponible » dans les écrans sportifs, CDC 10.3 n° 188). L'interface n'évalue jamais elle-même l'éligibilité.
- Sélection simple : le champ est remplacé par une « puce joueur » (avatar, nom, numéro) avec un bouton « Changer ». Sélection multiple : puces sous le champ, chacune avec une croix « Retirer {nom} ».
- Dans une modale sur mobile, la liste de suggestions s'insère dans le flux sous le champ (pas de fenêtre flottante masquée par le clavier), et le champ remonte en haut du corps au focus.
- Hors connexion (pointage, Caisse Terrain Express) : recherche dans la liste des joueurs mise en cache sur le téléphone, avec la mention « Données du {date heure} ».

**Clavier et accessibilité** : motif ARIA combobox (`role="combobox"`, `aria-expanded`, `aria-activedescendant`), flèches pour naviguer, Entrée pour choisir, Échap pour fermer la liste (premier appui) puis la modale (second appui).

**Textes** : aide initiale « Tapez un nom ou un numéro. » ; recherche en cours « Recherche… » ; aucun résultat « Aucun joueur ne correspond à « {saisie} ». » ; erreur « Recherche impossible. Vérifiez votre connexion. »

Variantes du même composant (même comportement, autre source) : `ClubSearch` (mercato, défis, journal) et `UserSearch` (espace Superuser).

### 3.5 Loader (3.4)

**Rôle** : aucun chargement ni aucune action sans retour visuel.

- **Chargement de page** : barre de progression de 3 px en haut du contenu (couleur `--color-primary`) + squelette reproduisant la structure de la page (bloc titre, bloc contexte, cartes). Jamais d'écran blanc ni de grand indicateur rotatif centré.
- **Squelettes de liste** (3.4 « blocs gris animés ») : `Skeleton` en variantes `row` (cercle 40 px + deux lignes de 60 % et 40 %), `table-row`, `card`, `kpi`, `pitch` (rectangle vert pâle). Couleur `--color-skeleton`, animation de pulsation 1,2 s, statique si `prefers-reduced-motion`.
- **Action en cours** : bouton en état `loading` (voir Button). Pour une action sans bouton (glisser-déposer, pointage), petit indicateur de 16 px sur l'élément concerné, qui reste à sa nouvelle place (mise à jour optimiste) ; en cas d'échec, retour à la place d'origine et toast d'erreur.
- **Délais** : l'indicateur n'apparaît qu'après 200 ms (pas de clignotement sur une réponse rapide) et reste au moins 300 ms une fois affiché. Au-delà de 10 s : « Le chargement prend plus de temps que prévu. » + bouton « Réessayer ».
- **Accessibilité** : `aria-busy="true"` sur la zone en chargement, message `aria-live` « Chargement… ».

### 3.6 EmptyState (3.4)

**Rôle** : chaque section vide le dit explicitement.

**Anatomie** (compacte, dans la carte, pas d'illustration) : icône linéaire 24 px muted, message (14 px, `--color-text`), précision facultative (13 px, muted), action facultative (bouton `sm`, secondaire). L'action n'est passée **que si le rôle de l'utilisateur la permet** (règle de la matrice 2.4, décidée par l'API via les permissions renvoyées) ; sinon, message seul.

**Variante erreur** : icône d'alerte, message « Impossible de charger cette section. », précision selon le cas (voir 4. Messages standards), bouton « Réessayer ». Une section en erreur n'empêche pas les autres sections de la page de s'afficher.

**Variante « aucun résultat »** : utilisée par DataTable et PlayerSearch quand un filtre ou une recherche ne donne rien.

### 3.7 StatusBadge (3.4)

**Anatomie** : pilule de 22 px de haut, padding 8 px, pastille ronde de 6 px (couleur `--status-*-dot`) + libellé 13 px/500 (couleur `--status-*-fg`) sur fond `--status-*-bg`. Jamais la couleur seule : le libellé est toujours affiché.

**API** : `status` appartient à une liste fermée de clés (`in_good_standing`, `in_debt`, `pending`, `suspended`, `left`, `present`, `absent`, `late`, `excused`, `unfit`, `fit`, `fit_restricted`, `to_validate`, `validated`, `refused`, `archived`, `cancelled`, `queued`, etc.). La couleur et le libellé français sont **dérivés** de la clé par la table 2.5 ; aucun écran ne passe une couleur. Le libellé peut recevoir un complément (« En dette · {montant} », « Suspendu · 1 match »).

**Superposition** : un joueur peut porter deux badges (situation financière + Suspendu ou Blessé, 4.1). Ordre d'affichage : financier, puis discipline, puis santé.

### 3.8 PitchBoard (4.7, 4.11)

**Rôle** : afficher et manipuler des joueurs sur un terrain. Trois modes.

| Mode | Écran | Contenu |
| --- | --- | --- |
| `teams` | Séance, match (répartition A/B, 4.7) | Deux terrains (A et B) aux couleurs des maillots, pions rangés en grille par ordre d'arrivée, zone « Non répartis » |
| `tactic` | Plan tactique (4.11) | Un terrain, emplacements selon la formation, banc des joueurs disponibles, calque « tableau noir » |
| `readonly` | Vestiaire du jour, plan publié, composition publiée | Même rendu, sans interaction de modification |

**Terrain** : rendu SVG, proportions 68 × 105 conservées, largeur = largeur disponible. Pelouse et lignes selon 2.7. En-tête de terrain : « Équipe A — {couleur} · {n} joueurs ».

**Pion joueur** : disque de 40 px à la couleur du maillot, numéro du jour au centre (16 px/600, couleur de texte de la palette 2.7), bordure blanche 2 px ; sous le disque, prénom + initiale du nom (« Jean K. », 13 px, fond sombre semi-opaque pour rester lisible sur la pelouse). Zone tactile 44 px. Pion grisé (opacité 50 %, motif hachuré) pour un joueur non éligible, avec icône cadenas ; au toucher, info-bulle portant la raison venue de l'API.

**Interactions**

- **Glisser-déposer** : événements pointeur unifiés (souris, doigt, stylet). Sur écran tactile, le glissement démarre après un appui long de 250 ms pour ne pas gêner le défilement de la page. La zone de dépôt valide s'éclaire (bordure `--color-focus` 2 px) ; une zone interdite reste inerte.
- **Alternative sans glissement** (obligatoire, 4.7 « bouton Passer en A/B ») : un toucher simple sur un pion ouvre un menu (panneau bas sur mobile) : « Passer en B » (ou « Passer en A »), « Voir la fiche du joueur ». En mode `tactic` : « Placer sur le terrain », « Retirer du terrain », « Modifier le numéro et le poste ».
- **Clavier** : Tab pour atteindre un pion, Espace pour le saisir, flèches pour choisir la destination, Entrée pour déposer, Échap pour annuler. Annonce `aria-live` : « Jean K. passé en équipe B. »
- **Enregistrement** : chaque déplacement est enregistré immédiatement (mise à jour optimiste + petit indicateur sur le pion). Toast « {nom} passé en équipe {A/B}. » avec action « Annuler ». Hors connexion, le déplacement est mis en file (SyncIndicator).
- **Non éligibles** : un pion non éligible ne peut être déposé ni sur un terrain ni sur un emplacement tactique (règle CLAUDE.md §2.5, contrôle réel côté API ; l'interface ne fait que refléter l'état renvoyé).

**Disposition**

- Mode `teams` : ≥ 768 px, deux terrains côte à côte ; < 768 px, l'un au-dessus de l'autre (4.7), chaque terrain à pleine largeur, zone « Non répartis » en dessous. Les pions sont rangés en grille de 4 colonnes (360 px) à 6 colonnes, dans l'ordre d'arrivée.
- Mode `tactic`, portrait : terrain vertical pleine largeur, banc en bande horizontale défilante sous le terrain, barre d'outils du tableau noir collée en bas. Paysage : terrain horizontal, banc en colonne à droite, barre d'outils à gauche (4.11). Le changement d'orientation conserve les positions (coordonnées relatives 0–1).
- Barre d'outils du tableau noir (mode `tactic`, Coach seulement) : « Sélection », « Flèche », « Zone », « Texte », « Gomme », « Annuler », « Rétablir » — icônes 40 px avec libellé en info-bulle et `aria-label`.

**États** : chargement = squelette `pitch` ; aucun joueur présent = « Aucun joueur pointé présent pour l'instant. Les équipes se forment au fil des arrivées. » ; séance verrouillée = mode `readonly` forcé + bandeau « Séance verrouillée ».

### 3.9 Sidebar (3.5)

**Rôle** : navigation principale et identité du club connecté.

**Haut de barre** (marque blanche) : logo du club (40 px, rayon 8 px) + nom du club (16 px/600, deux lignes au plus, puis points de suspension avec nom complet en info-bulle). Données issues de l'API au chargement ; squelette pendant le chargement ; sans logo, carré aux initiales du club. **Aucun nom ni logo de club dans le code.** Fond `--color-sidebar-bg` (couleur principale du club en thème Classic).

**Navigation** : groupes titrés (13 px, muted), éléments de 40 px (zone 44 px) avec icône 20 px et libellé 14 px. N'apparaissent que les entrées autorisées par les rôles de l'utilisateur (union des rôles, 2.2). Élément actif : fond teinté de la couleur principale + liseré gauche de 3 px `--color-accent`, `aria-current="page"`.

| Groupe | Entrées (rôles qui les voient) |
| --- | --- |
| — | Accueil (tous), Vestiaire du jour (tous), Fil d'actualité (tous), Mon profil (tous) |
| Club | Comité et bureau (tous), Assemblées générales (tous), Communiqués (tous), Chat (tous) |
| Sport | Espace coach (Coach, Capitaine, Président, VP, DS), Séances (tous), Matchs (tous), Vestiaire du jour (tous ; onglet « Plans » : lecture seule sauf Coach et Assistant), Discipline (tous) |
| Trésorerie | Tableau de bord (Pdt, VP, Trés, Adj), Grille des cotisations (Pdt, VP, Trés, Adj), Dépenses (Pdt, VP, Trés, Adj) |
| Club (suite) | Médical (Médecin, Coach, Pdt), Matériel (Intendant, Pdt, VP, Trés, Coach), Mercato (tous : section personnelle ; marché selon 2.4) |

**Bas de barre** (3.5, sans débordement) : ligne de 56 px contenant avatar 32 px, nom de l'utilisateur (14 px, une ligne, points de suspension, nom complet en info-bulle), rôle principal en dessous (13 px, muted, une ligne), et un `IconButton` « … » (menu utilisateur). Largeur totale = largeur de la barre moins 24 px de marges ; le nom se réduit, jamais les boutons. Menu utilisateur : « Mon profil », « Thème : Classic / Clair / Sombre » (sous-choix), « Se déconnecter ». « Se déconnecter » est aussi accessible en un appui depuis ce menu, sans autre confirmation.

**Mobile (< 1024 px)** : barre masquée, remplacée par une barre supérieure de 56 px : bouton menu (« Ouvrir le menu »), logo du club 28 px + nom du club (une ligne, points de suspension), `SyncIndicator`, `NotificationBell`. Le menu ouvre la barre latérale en tiroir depuis la gauche (280 px, 85 vw max.), fermeture par la croix, le voile, Échap ou un choix de navigation.

**Ordinateur (≥ 1024 px)** : barre fixe de 248 px, défilement interne si nécessaire, bas de barre toujours visible. `SyncIndicator` et `NotificationBell` dans une barre supérieure du contenu, à droite.

**Variante Superuser** : haut de barre « Vesta » + « Administration » (aucun club), couleurs du thème choisi (pas de Classic), entrées de l'espace Superuser.

### 3.10 Footer (3.5)

**Texte exact et unique** (CLAUDE.md §2.19) :

> VESTA by IMARA TECH Group — une partie de nos revenus est destinée aux orphelinats locaux

- Une seule constante dans tout le code de l'interface ; c'est la **seule** occurrence du nom de l'Éditeur. Il n'apparaît ni dans la barre latérale, ni dans les modales, ni dans les titres, ni dans les emails, ni dans les PDF générés.
- Affiché sur toutes les pages (y compris connexion et espace Superuser), en bas du contenu, **non collant** (il ne réduit pas la hauteur utile au bord du terrain).
- 13 px, `--color-text-muted`, centré, padding 16 px, séparateur supérieur `--color-border`. Retour à la ligne naturel sur 360 px, sans troncature.
- Non affiché dans les modales plein écran (il reste sur la page en dessous).

---

## 4. Messages standards

Mêmes libellés partout (3.1 « Cohérence »). Les écrans y renvoient au lieu de les réécrire.

| Situation | Message |
| --- | --- |
| Champ obligatoire vide | « Ce champ est obligatoire. » |
| Email invalide | « Saisissez une adresse email valide. » |
| Montant invalide | « Saisissez un montant supérieur à 0. » |
| Date future interdite | « La date ne peut pas être dans le futur. » |
| Fichier trop lourd | « Fichier trop lourd : 10 Mo maximum. » |
| Format refusé | « Format non accepté : JPEG, PNG, WebP ou PDF. » |
| Réseau indisponible | « Connexion impossible. Vérifiez votre réseau et réessayez. » |
| Erreur serveur | « Une erreur est survenue de notre côté. Réessayez dans un instant. » |
| Droit insuffisant (403) | « Vous n'avez pas accès à cette action. » |
| Élément introuvable (404) | « Cet élément n'existe plus. » |
| Session expirée | « Votre session a expiré. Reconnectez-vous. » |
| Hors connexion | « Vous êtes hors connexion. Les pointages, encaissements et incidents seront envoyés au retour du réseau. » |
| Action impossible hors connexion | « Cette action nécessite une connexion. » |
| Licence expirée (lecture seule) | « La licence du club a expiré : le club est en lecture seule. Vos données restent consultables et exportables. » |
| Écritures financières gelées (5.3) | « Les écritures financières du club sont suspendues le temps d'une vérification. Réessayez plus tard. » |
| Séance ou match verrouillé (4.7) | « Séance verrouillée depuis minuit. Seul le support peut la corriger, à la demande du Président. » |
| Confirmation d'abandon | « Abandonner les modifications ? » / « Les informations saisies seront perdues. » |

Formats : montants avec la devise du club venant de l'API (« 1 250 $ », « 25 000 FC » ; décimales masquées si nulles) ; dates « dim. 27 sept. 2026 » (listes) et « dimanche 27 septembre 2026 » (en-têtes) ; heures « 07:30 » ; tout dans le fuseau du club.

## 5. Mode lecture seule (licence expirée, 1.4)

Quand l'API signale un club en lecture seule : bandeau `readonly` sur toutes les pages, boutons de création et de modification masqués, exports conservés. Les modales de détail restent consultables. Aucun écran ne gère ce cas à sa façon.

## 6. Propositions à valider par le client

1. Correspondance des statuts non couverts par le 3.4 (tableau 2.5, lignes « Proposition »).
2. Thème Classic appliqué aux accents seulement (fond de page neutre) pour garantir la lecture en plein soleil.
3. Palette fermée de 10 couleurs de maillot (2.7).
4. Pied de page non collant.
5. Format des montants, dates et heures (section 4).

## 7. Révision du 28/09/2026 : thème Clair adouci, Classic et logo (remarques client)

Remarque du client (`remarques.md`) : « Le thème Classic doit se conformer aux couleurs du fichier image `./data/logo.jpeg`, et le thème Clair est d'un blanc qui brûle les yeux : adoucis-le en variant légèrement vers le gris. »

Statut : **proposition à appliquer par `frontend-dev`** (7.1, 7.2) ; **7.3 à faire trancher par le client**. Les ratios sont calculés avec la formule de `frontend/src/design-system/tokens/color-contrast.ts` (luminance relative WCAG 2.x). Les sections 2.3 à 2.5 restent valables sauf pour les valeurs remplacées ci-dessous.

### 7.1 Thème Clair adouci (s'applique aussi à Classic)

On abandonne le blanc pur `#FFFFFF` pour les grandes surfaces. Le gris retenu est **très légèrement froid** (teinte bleu ardoise d'environ 215°, saturation très faible), dans la famille des textes `#111827` et `#4B5563` déjà en place. La hiérarchie fond de page < carte est conservée, et même un peu renforcée (1,12:1 contre 1,09:1 aujourd'hui).

| Token | Avant | Après | Remarque |
| --- | --- | --- | --- |
| `--color-bg` | `#F4F5F7` | `#E8EBEF` | Fond de page, un cran plus gris |
| `--color-surface` | `#FFFFFF` | `#F6F7F9` | Cartes, modales, tableaux, champs |
| `--color-surface-muted` | `#EEF0F3` | `#E6E9EE` | En-têtes de tableau, survol, cellule « à venir » (écart avec la carte conservé : 1,14:1) |
| `--color-border` | `#E1E5EB` | `#D8DEE5` | Séparateurs décoratifs (écart avec la carte conservé : 1,26:1) |
| `--color-border-strong` | `#7B8699` | `#6B7689` | Bordures de champs : garde de la marge au-dessus de 3:1 sur tous les fonds neutres |
| `--color-skeleton` | `#E3E6EB` | `#DADEE5` | Squelettes (écart avec la carte conservé : 1,26:1) |
| `--color-sidebar-bg` | `#FFFFFF` | `#F6F7F9` | = `--color-surface` |
| `--color-status-neutral-bg` | `#F3F4F6` | `#E5E7EB` | Le badge gris deviendrait invisible sur `#F6F7F9` (1,03:1). Seule la luminance change, la famille reste grise (2.5) |
| `--color-text`, `--color-text-muted`, `--color-text-disabled`, `--color-primary*`, `--color-focus`, `--color-overlay` | inchangés | inchangés | |
| `--color-on-primary`, `--color-button-danger-fg`, `--color-jersey-white-bg` | `#FFFFFF` | inchangés | Texte sur bouton ou maillot : pas une grande surface |

Le thème Sombre n'est pas modifié.

**Ratios des paires critiques (après)**

| Paire | Avant | Après | Exigence |
| --- | --- | --- | --- |
| `--color-text` `#111827` sur `--color-surface` | 17,74 | 16,55 | ≥ 7 |
| `--color-text` sur `--color-bg` | 16,26 | 14,83 | ≥ 7 |
| `--color-text-muted` `#4B5563` sur `--color-surface` | 7,56 | 7,05 | ≥ 4,5 (visé 7) |
| `--color-text-muted` sur `--color-bg` | 6,93 | 6,32 | ≥ 4,5 |
| `--color-text-muted` sur `--color-surface-muted` (en-têtes, cellule « à venir ») | 6,62 | 6,21 | ≥ 4,5 |
| `--color-text` sur `--color-surface-muted` | 15,54 | 14,58 | ≥ 7 |
| `--color-border-strong` sur surface / fond / surface-muted | 3,68 / 3,37 / 3,22 (`#7B8699`) | 4,28 / 3,84 / 3,77 (`#6B7689`) | ≥ 3 |
| `--color-primary` Clair `#1D4ED8` en texte sur surface / fond / surface-muted | 6,70 / 6,14 / 5,87 | 6,25 / 5,60 / 5,51 | ≥ 4,5 |
| Blanc sur `--color-primary` `#1D4ED8` | 6,70 | 6,70 | ≥ 4,5 |
| `--color-focus` `#2563EB` sur `--color-bg` | – | 4,32 | ≥ 3 |
| Badge vert `#14532D` sur `#DCFCE7` | 8,30 | 8,30 | ≥ 7 |
| Badge orange `#7C2D12` sur `#FFEDD5` | 8,18 | 8,18 | ≥ 7 |
| Badge rouge `#7F1D1D` sur `#FEE2E2` | 8,20 | 8,20 | ≥ 7 |
| Badge violet `#581C87` sur `#F3E8FF` | 9,22 | 9,22 | ≥ 7 |
| Badge gris `#1F2937` sur fond gris | 13,34 (`#F3F4F6`) | 11,86 (`#E5E7EB`) | ≥ 7 |
| Montant `#111827` sur les cellules payé / partiel / impayé | 16,15 / 15,48 / 14,52 | inchangé | ≥ 7 |

Les fonds de badge vert et orange ont une luminance proche de la nouvelle carte (environ 1,03:1), mais leur teinte les distingue, ainsi que la pastille et le libellé (2.5, règle 5 de 2.4). Seul le gris, sans teinte, devait bouger.

**Classic** reprend les neutres du Clair (valeurs par défaut de `@theme`) : la modification s'y applique d'office, sans bloc supplémentaire.

**Conséquence dans le code :** `deriveReadableTextColor(rawHex, surfaceHex = "#FFFFFF")` calcule `--color-primary-text` contre un blanc qui n'existe plus. Il faut passer le neutre le plus sombre sur lequel un lien peut apparaître, c'est-à-dire `--color-surface-muted` `#E6E9EE` (bouton `ghost` survolé, en-têtes de tableau). C'est un neutre de la plateforme, pas une couleur de club : la règle 18 est respectée.

### 7.2 Classic et logo du club

**Couleurs du logo de Loisirs Club Discovery (`data/logo.jpeg`)**, relevées à l'œil sur l'image (à confirmer à la pipette, écart attendu de ± 10 par canal) :

| Zone | Couleur estimée |
| --- | --- |
| Bleu marine (blason, ruban, pièces du ballon) | `#1B2143` |
| Rouge (mains, tampons latéraux, point du « i ») | `#D2232A` |
| Blanc (fond, lettrage, ballon) | `#FFFFFF` |
| Bleu vif (reflets du ballon, surface très faible) | environ `#2F6FB5` |

**Ce que produit aujourd'hui `extractColorsFromImage`** (`frontend/src/routes/club-creation/colorFromImage.ts`) : l'image est réduite à 24 × 24 px, puis on calcule la **moyenne de tous les pixels** d'alpha ≥ 32. Un JPEG n'a pas de transparence, donc les 576 pixels comptent, y compris le fond blanc (à peu près la moitié de l'image). Avec environ 50 % de blanc, 40 % de marine et 7 à 10 % de rouge, on obtient :

- principale ≈ `#9A95A5` : un **gris mauve délavé**, ni marine ni rouge ;
- secondaire = principale × 0,6 ≈ `#5C5963` : un gris foncé, jamais le rouge.

`ThemeContext` en dérive ensuite :

- `--color-sidebar-bg` et `--color-primary` = `#9A95A5`, avec un texte `#111827` (6,1:1, contraste suffisant mais couleur fausse) ;
- `--color-primary-text` ≈ `#77737F` (assombri en 5 pas de 5 % jusqu'à 4,6:1 sur blanc) ;
- `--color-accent` = `#5C5963`.

Verdict : **l'algorithme ne capte ni le marine ni le rouge.** Il retient un mélange dominé par le blanc. Le code l'annonce d'ailleurs comme une « simplification », qui s'écarte du principe du 2.4 (exclure les pixels quasi blancs ou quasi noirs, garder les teintes saturées dominantes). Par ailleurs, `ClubIdentityModal.tsx` ne relance aucune extraction quand le logo change, alors que le 2.4 l'y prévoit.

**Correction de `extractColorsFromImage` (conforme au 2.4, étapes 1 et 2)**

1. Réduire l'image à 64 × 64 px, et non 24 × 24 : sinon les petites zones rouges se fondent dans leurs voisines.
2. Écarter les pixels d'alpha < 128, les pixels quasi blancs (luminosité HSL > 0,90), quasi noirs (< 0,08) et peu saturés (saturation HSL < 0,25). Le marine `#1B2143` passe ces filtres (luminosité 0,18, saturation 0,43). Le blanc et les gris d'anticrénelage sont éliminés.
3. Classer les pixels restants dans un histogramme de 24 cases de teinte (15° chacune) × 3 niveaux de luminosité. La couleur d'une case est la moyenne RVB de ses pixels, ce qui absorbe le bruit JPEG.
4. **Principale** = la case la plus peuplée (ici le marine, teinte ≈ 231°).
5. **Secondaire** = parmi les cases qui pèsent au moins 3 % des pixels retenus, celle dont la teinte est la plus éloignée de la principale sur le cercle. Ici, le rouge (≈ 358°, soit 127° d'écart) l'emporte sur le bleu du ballon (≈ 211°, 20° d'écart, de toute façon sous le seuil).
6. Cas de repli : moins de 2 % de pixels retenus (logo noir et blanc) → `null` : pas de proposition, les pastilles restent vides et Classic retombe sur le Clair. Une seule teinte → secondaire = principale.
7. Appeler la même fonction dans `ClubIdentityModal.tsx` au changement de logo, pour pré-remplir les pastilles. Le Président garde la main sur les valeurs.
8. Tests Vitest sur des tableaux de pixels synthétiques (jsdom ne sait pas dessiner une image) : blanc + marine + rouge → marine en principale, rouge en secondaire ; logo gris → `null`.

**Affectation recommandée** (déjà celle de `ThemeContext`, à condition que les bonnes couleurs arrivent de l'API) :

| Token Classic | Valeur obtenue pour ce club | Ratio |
| --- | --- | --- |
| `--club-primary` (API) | `#1B2143` | |
| `--club-secondary` (API) | `#D2232A` | |
| `--color-sidebar-bg` / `--color-sidebar-text` | `#1B2143` / `#FFFFFF` | 15,61 |
| `--color-primary` / `--color-on-primary` (bouton principal) | `#1B2143` / `#FFFFFF` | 15,61 |
| `--color-primary-text` (liens) | `#1B2143` | 14,56 sur surface, 13,05 sur fond, 12,83 sur surface-muted |
| `--color-accent` (liseré actif, anneau d'avatar, liseré PDF) | `#D2232A` | 4,88 sur surface, 4,30 sur surface-muted, **2,98 sur le marine** |

Le rouge reste **un accent non textuel**. Il ne sert ni pour le bouton principal ni pour du texte, pour ne pas être confondu avec le bouton destructeur `#B91C1C` ni avec le statut « En dette » (2.5).

**Défauts de lisibilité de la barre latérale sombre (existants, bloquants dès qu'une couleur de club est foncée)** — `frontend/src/design-system/components/Sidebar.tsx` :

- l. 136 (titres de groupe) et l. 210 (rôle de l'utilisateur) utilisent `text-text-muted` : `#4B5563` sur marine donne **2,81:1**, sous le seuil de 4,5:1 ;
- l. 154 : au survol, `hover:bg-surface-muted` avec `text-sidebar-text` affiche du blanc sur `#E6E9EE`, soit **1,15:1** : illisible ;
- l. 212 : le `IconButton` « … » est en `text-text-muted` sur marine (2,81:1).

Correction proposée : quatre nouveaux tokens de barre latérale, posés par `ThemeContext` en Classic et égaux aux neutres en Clair et Sombre.

| Nouveau token | Clair (défaut `@theme`) | Sombre | Classic (dérivé à l'exécution) | Exemple LCD |
| --- | --- | --- | --- | --- |
| `--color-sidebar-text-muted` | `#4B5563` | `#B8C1CE` | `sidebar-text` mélangé à 30 % vers `sidebar-bg`, contrôlé ≥ 4,5:1 (sinon réduire par pas de 5 %) | `#BBBCC7` : 8,27 |
| `--color-sidebar-hover-bg` | `#E6E9EE` | `#1A2438` | `sidebar-bg` mélangé à 10 % vers `sidebar-text` | `#323756` : blanc à 11,56 |
| `--color-sidebar-active-bg` | `#E6E9EE` | `#1A2438` | `--color-surface` (pastille claire sur la barre foncée) | `#F6F7F9` |
| `--color-sidebar-active-text` | `#111827` | `#F3F4F6` | `--color-primary-text` | `#1B2143` : 14,56 |

Élément actif en Classic : pastille claire, texte marine et liseré rouge (4,88:1 sur la pastille). Un fond actif teinté de marine ferait tomber le liseré rouge à 1,8:1, d'où ce choix. Même garde-fou pour tout club : si `--color-accent` n'atteint pas 3:1 sur `--color-surface`, l'assombrir avec `darkenUntilContrast(…, 3)`.

### 7.3 Question ouverte à faire trancher par le client (non tranchée)

Sans couleurs de club (page `/connexion`, club sans logo ni couleurs), Classic retombe sur le Clair (bleu `#1D4ED8`). Deux lectures de la remarque sont possibles :

- **(a)** Les couleurs de Loisirs Club Discovery, **enregistrées comme donnée de son club** (identité du club, servie par l'API), s'appliquent à son Classic. C'est conforme à CLAUDE.md règle 18, au CDC 3.6 (« couleurs extraites du logo du club ») et au 2.4 point 4 ci-dessus.
- **(b)** Le **défaut de la plateforme** sans club devient marine et rouge. Cela reviendrait à écrire la palette d'un club dans les tokens. **C'est contraire à CLAUDE.md règle 18** (« Aucun nom de club, logo ou lien de paiement écrit en dur » ; couleurs venant de l'API) et au 2.4 point 4 (« Aucun nom ni couleur par défaut propre à un club »). Tous les autres clubs verraient aussi, à leur page de connexion, les couleurs d'un club tiers.

**Option prudente proposée, à valider :** retenir (a). Le défaut de la plateforme reste neutre (valeurs Clair). Les couleurs du club pilote sont saisies comme **donnée** : le Président les enregistre dans la modale « Identité du club » (action journalisée), aidé par l'extraction corrigée (7.2). À vérifier au passage : la valeur `primary_color` / `secondary_color` actuellement enregistrée pour le club pilote, qui est sans doute le gris mauve issu de l'ancien algorithme. Si le client tient à une identité visuelle propre à Vesta sur les pages sans club, il faut définir une palette « Vesta » dédiée, distincte de celle de tout club.

Remarque connexe : `backend/apps/clubs/services.py` l. 1534 prend `(0.12, 0.16, 0.32)` (≈ `#1F2952`, un marine) comme couleur par défaut du bandeau PDF quand le club n'a pas de couleur. Ce n'est pas la palette d'un club, mais le défaut de la plateforme n'est alors pas neutre. Il faudra l'aligner sur la décision prise en 7.3.

---

## 8. Graphiques (tableau de bord du bureau, `docs/ecrans/club-tableau-de-bord-bureau.md` §6)

SVG écrit à la main, **aucune dépendance** (décision Q6 non tranchée : option proposée par la spec). Code : `frontend/src/design-system/charts/`, exporté par `design-system/index.ts`. Montants, unités, libellés et périodes sont fournis par l'appelant (donnees de l'API) ; aucun composant ne calcule de règle métier.

### 8.1 Tokens

`--color-series-1` à `-4` (`tokens.css`), distincts des couleurs de statut et jamais issus du club (marque blanche). Contraste >= 3:1 sur `--color-surface` et `--color-surface-muted`, contrôlé par `charts/series-tokens.test.ts`.

| Token | Clair / Classic | Sombre | Tracé (lignes) | Motif (surfaces) |
| --- | --- | --- | --- | --- |
| `--color-series-1` | `#1D4ED8` | `#60A5FA` | plein | plein |
| `--color-series-2` | `#0F766E` | `#2DD4BF` | tirets | hachures |
| `--color-series-3` | `#BE185D` | `#F472B6` | pointillés | points |
| `--color-series-4` | `#854D0E` | `#FACC15` | tirets-points | quadrillage |

Grille et axes : `--color-border` ; libellés : `--color-text-muted` ; valeurs écrites : `--color-text`. Texte des graphiques 12 px.

### 8.2 Règles communes

- `<figure aria-label={title}>` + `<figcaption class="sr-only">` (résumé généré, surchargeable par `summary`) ; `role="img"` sur le SVG, ou `role="group"` quand il porte des boutons ; « Voir les données » ouvre un `<table>` (`<details>`).
- Propriétés communes (`ChartCommonProps`) : `title`, `summary?`, `state?` (`ready` | `loading` | `error`), `emptyMessage?`, `errorMessage?`, `onRetry?`, `height?` (160 dans une carte, 220 dans une modale), `className?`.
- Chargement : `Loader` + `Skeleton variant="chart"` (nouveau) ; vide : `EmptyState` ; erreur : `EmptyState variant="error"` + « Réessayer ».
- Interaction : `onSelect` rend chaque colonne, ligne, segment ou axe cliquable (`role="button"`, Entrée/Espace, focus visible). Sans `onSelect`, aucun rôle interactif : dans une `ChartCard`, c'est la carte entière qui est cliquable (bouton étiré, un seul arrêt clavier). Un graphique interactif dans une carte passe `interactiveContent` sur la `ChartCard`.
- Cibles tactiles : colonnes de 36 px minimum quand `onSelect` est fourni (le graphique défile alors dans son cadre) ; lignes horizontales >= 44 px ; boutons de légende 36 px.
- Jamais la couleur seule : tracé + forme de marqueur (courbes, radar), motif (barres, segments), légende textuelle, valeurs écrites. Pas de camembert, pas de dégradé ; entrée de 200 ms (`.vesta-chart-enter`), coupée par `prefers-reduced-motion`.
- Échelles rondes (`niceScale`, pas 1/2/5 x 10^n), valeurs nulles, un seul point, `null` = trou ou absence de barre, grandes valeurs (axes compacts « 12 k »). Étiquettes d'axe jamais pivotées ni tronquées : espacées (courbe), coupées sur deux lignes (barres, radar) ou largeur de colonne adaptée avec défilement dans le cadre (pas de défilement de la page).

### 8.3 Composants

| Composant | Propriétés principales |
| --- | --- |
| `ChartCard` | `title`, `value?`, `caption?`, `periodLabel?`, `onOpen?`, `openLabel?`, `state?` (`ready` \| `loading` \| `error` \| `empty`), `emptyMessage?`, `errorMessage?`, `onRetry?`, `interactiveContent?`, `children` |
| `KpiTile` | `label`, `value`, `hint?`, `family?` + `statusLabel?` (pastille avec texte), `onClick?` |
| `LineChart` | `labels`, `series[{name, values: (number\|null)[]}]` (2 au plus), `yMin?`, `yMax?`, `unit?`, `reference?{value,label}`, `formatValue?`, `onSelect?(index)` |
| `BarChart` | `categories`, `series[{name, values}]` (4 au plus), `orientation?` (`vertical` \| `horizontal`), `stacked?`, `unit?`, `reference?` (vertical), `formatValue?`, `onSelect?(categoryIndex)` |
| `StackedBar` | `segments[{label, value, family?: StatusFamily}]`, `onSelect?(index, segment)` |
| `FormStrip` | `results[{outcome: win\|draw\|loss, opponent?, score?, date?}]` (5 affichés), `title?`, `state?`, `onSelect?(index, result)` |
| `RadarChart` | `axes[{label, max?}]` (3 à 8), `series[{name, values}]` (4 au plus), `maxValue?` (100), `unit?`, `onSelect?(axisIndex)` |
| `PeriodPicker` | `value: {mode:"month", month:"AAAA-MM"} \| {mode:"season", seasonId}`, `onChange`, `seasons?[{id,label}]` (récente d'abord), `minMonth?`, `maxMonth?` (mois en cours par défaut), `now?` |

`SegmentedControl` reçoit la propriété `hideLabel` (libellé `sr-only`) pour les barres compactes.

### 8.4 Écarts avec la spec §6 (à valider)

- `LineChart` / `BarChart` prennent `labels` + `series[{name, values}]` plutôt que `points[{x,label,value}]` : même contenu, adapté à deux séries et aux trous.
- `BarChart` : `onSelect` désigne la catégorie (groupe de barres), pas une barre isolée.
- `StackedBar` est en HTML (barre flex + légende en boutons de 36 px) et non en SVG : plus fiable pour des cibles tactiles et des libellés non tronqués.
- La spec cite `docs/design-system.md` ; le document de référence du dépôt est `docs/lot0/design-system.md` (ce fichier).
