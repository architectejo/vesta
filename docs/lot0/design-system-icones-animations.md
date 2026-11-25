# Lot 0 — Design system Vesta : icônes et animations

Complément de `docs/lot0/design-system.md` (sections 2.2 « Mouvements » et `--icon-sm` / `--icon-md`, 3.1 IconButton, 3.5 Loader, 3.9 Sidebar). Ce document fixe la bibliothèque d'icônes, l'approche des animations et la liste des remplacements à faire. `frontend-dev` installe et intègre ; aucun code n'est écrit ici.

Demande du client : « Il faut mettre les icônes et les animations dans la plateforme (ex: lucide-react ou autre que tu trouveras mieux). »

Sources : cahier des charges chapitre 3 (3.1 densité, 3.4 loaders, 3.6 thèmes) ; CLAUDE.md §2 « Interface » (règles 16, 17, 18).

Usage de référence, inchangé : trésorier ou coach au bord du terrain, smartphone de 360 px, plein soleil, réseau faible. Une icône sert à reconnaître une action plus vite, une animation sert à comprendre ce qui vient de changer. Rien de décoratif.

---

## 1. Décision : bibliothèque d'icônes

**Retenu : `lucide-react`** (dépendance de production, une seule bibliothèque d'icônes pour toute l'application).

Justification :

1. **Poids** : chaque icône est un composant ESM importé par son nom ; Vite n'embarque que les icônes réellement utilisées (environ 0,3 à 0,5 Ko par icône compressée). Une soixantaine d'icônes coûte moins qu'une seule image de logo, ce qui compte sur un réseau faible.
2. **Style** : trait linéaire de 2 px sur une grille de 24, coins arrondis, terminé par `currentColor`. C'est exactement le dessin des SVG faits main déjà présents dans le code (`viewBox="0 0 24 24"`, `stroke="currentColor"`, `strokeWidth={2}`, `strokeLinecap="round"`). Le remplacement ne change donc pas l'aspect de l'interface, il l'unifie. C'est aussi le « seul jeu d'icônes linéaires » prévu au 2.2 du design system.
3. **Licence et maintenance** : licence ISC (permissive, aucune mention obligatoire dans l'interface, donc aucun conflit avec la règle 19 sur l'unique mention de l'Éditeur), projet très actif, plus de 1 500 icônes, compatible React 19 et Vite.
4. **Alternatives écartées** : Heroicons (catalogue trop court : pas de stéthoscope, de maillot, de marteau de juge) ; Phosphor (six graisses par icône, ce qui invite à l'incohérence, et un paquet React plus lourd) ; Tabler (comparable, mais l'API React est moins répandue et rien ne justifie de s'écarter de la suggestion du client).

À l'installation, `frontend-dev` vérifie que la version courante de `lucide-react` déclare React 19 dans ses `peerDependencies`. Certains noms d'icônes ont été renommés au fil des versions (ex. `MoreHorizontal` devenu `Ellipsis`, `AlertTriangle` devenu `TriangleAlert`, `Home` devenu `House`, `Loader2` devenu `LoaderCircle`) : toujours prendre **le nom actuel**, jamais l'alias déprécié. Si un nom de ce document n'existe pas dans la version installée, prendre l'équivalent le plus proche et le signaler dans le compte rendu.

### 1.1 Règles d'import (obligatoires)

- Un seul point d'entrée : `frontend/src/design-system/icons.ts`, qui ré-exporte les icônes retenues sous des **noms métier** (`IconBack`, `IconClose`, `IconMore`…, voir 3). Les écrans importent depuis le design system, jamais directement depuis `lucide-react`. Ainsi la table de la section 3 reste la seule source, et changer une icône se fait en un seul endroit.
- Imports nommés uniquement (`import { ArrowLeft } from "lucide-react"`). **Interdits** : `import * as icons from "lucide-react"`, l'objet `icons`, le composant `DynamicIcon` ou tout chargement d'icône par nom calculé : ils embarquent la bibliothèque entière.
- Aucun SVG d'icône fait main dans les écrans. Exceptions : les graphismes qui ne sont pas des icônes (tracé du terrain `PitchMarkings`, calque d'annotations `AnnotationsLayer` du `PitchBoard`, silhouette `PlayerSilhouette` de la carte de joueur).
- Pas d'emoji ni de glyphe Unicode utilisé comme icône (`←`, `×`, `⋯`, `▾`, `‹`…). Les flèches qui font partie d'une **phrase** (« Solde actuel : 50 $ → Nouveau solde : 0 $ », « Club A → Club B ») restent du texte : ce sont de la typographie, pas des icônes.

---

## 2. Décision : animations

**Retenu : transitions et animations CSS natives (classes Tailwind + quelques `@keyframes` dans `tokens.css`). Pas de `framer-motion` / `motion`, ni d'autre bibliothèque d'animation.**

Justification :

1. Les besoins de Vesta sont tous simples : apparition et disparition d'une modale, d'un panneau bas, d'un tiroir, d'un menu ou d'un toast, rotation d'un chevron, rotation d'un indicateur de chargement, pulsation d'un squelette, changement de couleur au survol. Le CSS fait tout cela sur `transform` et `opacity`, accélérés par le processeur graphique, sans JavaScript.
2. Une bibliothèque comme `framer-motion` ajoute plusieurs dizaines de Ko compressés au premier chargement, pour un gain nul dans ces cas. Sur un réseau faible au bord du terrain, ce coût passe avant l'agrément.
3. `prefers-reduced-motion` est déjà traité globalement dans `tokens.css` (l. 198 à 206) : toute animation CSS en hérite sans effort, alors qu'une bibliothèque JS demande de le gérer composant par composant.
4. L'hébergement cPanel n'est pas en cause (tout se passe dans le navigateur), mais la règle « pas de dépendance inutile » vaut aussi côté interface.

Seul cas qui pourrait justifier du JavaScript : le glisser-déposer du `PitchBoard` et l'inclinaison de `PlayerTradingCard`, qui suivent déjà le doigt en posant `transform` directement en JS. On garde cette approche ; aucune bibliothèque n'est ajoutée pour eux.

### 2.1 Tokens de mouvement (à ajouter dans `tokens.css`, bloc `@theme`)

| Token | Valeur | Usage |
| --- | --- | --- |
| `--duration-fast` | 150 ms | Survol, focus, appui, menu déroulant, rotation de chevron, fermeture de toute surface |
| `--duration-base` | 200 ms | Ouverture d'une modale, d'un panneau bas, du tiroir mobile, d'un toast |
| `--duration-slow` | 300 ms | Retournement de la carte de joueur (existant), retour d'un pion à sa place après un échec d'enregistrement. **Maximum absolu** |
| `--ease-out` | `cubic-bezier(0.2, 0, 0, 1)` | Tout ce qui **apparaît** ou arrive à sa place |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | Tout ce qui **disparaît** |
| `--ease-standard` | `cubic-bezier(0.2, 0, 0.2, 1)` | Changements d'état sur place (couleur, rotation de chevron) |

Les fermetures sont plus courtes que les ouvertures (150 ms contre 200 ms) : on ne fait pas attendre quelqu'un qui veut partir.

### 2.2 Animations retenues

| Élément | Entrée | Sortie | Remarque |
| --- | --- | --- | --- |
| Voile de modale | `opacity` 0 → 1, 200 ms, `--ease-out` | 1 → 0, 150 ms, `--ease-in` | |
| Modale centrée (≥ 640 px) | `opacity` 0 → 1 + `scale` 0,98 → 1, 200 ms | inverse, 150 ms | Pas de rebond, pas de translation longue |
| Modale plein écran (< 640 px) | `opacity` 0 → 1 + `translateY` 16 px → 0, 200 ms | inverse, 150 ms | |
| Panneau bas | `translateY` 100 % → 0, 200 ms | 0 → 100 %, 150 ms | Le glissement vers le bas au doigt suit le doigt (pas de durée), puis termine en 150 ms |
| Tiroir de navigation mobile | `translateX` −100 % → 0, 200 ms | inverse, 150 ms | |
| Menu « … » / menu déroulant / filtres (ordinateur) | `opacity` + `scale` 0,98 → 1, 150 ms, origine au bouton | `opacity` 1 → 0, 100 ms | |
| Toast | `opacity` + `translateY` 8 px → 0, 200 ms | `opacity` 1 → 0, 150 ms | |
| Chevron d'une zone repliable | `rotate` 0 → 180°, 150 ms, `--ease-standard` | | Ex. « joueurs pas encore pointés » (Vestiaire) |
| Survol, focus, appui des boutons et lignes | `transition-colors`, 150 ms | | Existant dans `Button` et `IconButton`, à généraliser (lignes de liste, lignes de tableau, onglets, éléments de navigation) |
| Indicateur de chargement (bouton, action) | `animate-spin` sur `LoaderCircle` 16 px, 0,8 s linéaire | | Remplace la bordure tournante actuelle de `Button` |
| Squelettes | pulsation d'opacité 1,2 s (design system 3.5) | | Tailwind `animate-pulse` dure 2 s : déclarer une animation `--animate-skeleton` à 1,2 s et l'utiliser dans `Skeleton`, `Loader` et `AuthenticatedImage` |
| Barre de progression de page (3 px) | progression indéterminée en `translateX`, 1,2 s | | `Loader.tsx` l. 72 utilise aujourd'hui `animate-pulse` : à remplacer par un glissement |
| Pion déposé sur le terrain (`PitchBoard`) | `transform` vers sa place, 150 ms | retour à l'origine en 300 ms si l'API refuse | |
| Barre de progression d'assistant (`Wizard`) | `transform: scaleX`, 200 ms | | |

**Sortie des modales et menus** : la disparition demande de garder l'élément monté le temps de l'animation. Méthode retenue : attribut `data-state="open" | "closing"` posé par le composant ; à `closing`, l'animation de sortie joue et le démontage a lieu sur `animationend`, avec un délai de secours de 200 ms (si l'événement ne vient pas, par exemple en mouvement réduit). Le focus est rendu à l'élément d'origine dès le début de la fermeture, pas à la fin.

### 2.3 Ce qui n'est jamais animé

- Les changements de page (pas de transition entre routes) : la barre de 3 px et le squelette suffisent.
- L'apparition des lignes d'une liste ou d'un tableau (pas d'effet en cascade), y compris après « Voir plus ».
- Les chiffres des indicateurs (pas de compteur qui défile), les montants, les soldes.
- Les icônes elles-mêmes (pas d'icône animée, pas de cloche qui sonne), hormis l'indicateur de chargement et la rotation d'un chevron.
- Les badges de statut (pas de clignotement, même pour « En dette »).
- Les cartes au survol (pas d'agrandissement, pas d'ombre qui grandit).
- Le défilement (pas d'effet au défilement, pas de parallaxe).
- Aucune animation ne dépasse 300 ms ; aucune n'utilise de rebond ni d'effet élastique ; aucune n'anime `width`, `height`, `top`, `left` ou `margin` (seulement `transform` et `opacity`, plus les couleurs).

### 2.4 Mouvement réduit

La règle globale de `tokens.css` (durées ramenées à 0,01 ms, une seule itération) reste la référence. Conséquence acceptée : l'indicateur rotatif s'arrête ; c'est sans gêne parce que tout état de chargement porte aussi un texte (« Enregistrement… », « Chargement… », `aria-busy`). Aucun composant ne doit contourner cette règle.

---

## 3. Spec d'usage des icônes

### 3.1 Tailles

| Taille | Token | Où |
| --- | --- | --- |
| 16 px | `--icon-sm` | Dans un bouton texte `sm` ou `md` (icône à gauche du libellé, écart `--space-1` 4 px), dans un champ (loupe, suffixe), dans une puce de filtre ou une puce joueur (croix « Retirer »), dans un message d'erreur de champ, devant un libellé de liste (cadenas, épingle) |
| 20 px | `--icon-md` | Seule dans un `IconButton` de 40 px (zone tactile 44 px), éléments de navigation de la barre latérale, barre supérieure mobile, barre d'outils du tableau noir |
| 24 px | — | Uniquement dans `EmptyState` (icône muted au-dessus du message). Jamais ailleurs |

Pas d'autre taille. Pas d'icône agrandie pour « attirer l'œil » (règle 16 : pas de gros éléments). Une icône de 12 px (`h-3`, `TransferTimeline` l. 32) passe à 16 px.

Trait : `strokeWidth={2}` (valeur par défaut de Lucide) à 16 et 20 px ; `1.5` pour l'icône 24 px d'`EmptyState`. Ne pas activer `absoluteStrokeWidth`.

### 3.2 Couleur

- Toujours `currentColor` (valeur par défaut de Lucide) : l'icône prend la couleur du texte de son parent, donc du thème (Classic, Clair, Sombre). Ne jamais passer la propriété `color` ni une classe de couleur fixe.
- Icône neutre (fermer, menu, retour, rechercher…) : `--color-text-muted` au repos, `--color-text` au survol, comme l'`IconButton` actuel. Sur la barre latérale : jetons `--color-sidebar-*` (variante `sidebar` d'`IconButton`).
- Icône dans un bouton : couleur du libellé du bouton (`--color-on-primary` sur un bouton principal, blanc sur un bouton `danger`).
- Icône de statut (alerte d'erreur, avertissement, succès) : la couleur `--status-<famille>-fg` de la famille concernée, jamais seule (toujours accompagnée d'un texte).
- **Jamais une couleur de club en dur**, et jamais `--club-primary` / `--color-accent` sur une icône neutre : la couleur du club arrive sur une icône uniquement par héritage (icône d'un bouton principal, icône de l'élément de navigation actif via `--color-sidebar-active-text`).
- Icône désactivée : hérite de l'opacité du bouton désactivé, pas de couleur propre.

### 3.3 Accessibilité

- Une icône est toujours décorative : Lucide pose `aria-hidden="true"` ; le sens est porté par le libellé visible ou par l'`aria-label` du bouton (déjà obligatoire sur `IconButton`).
- Un bouton qui n'affiche qu'une icône est **toujours** un `IconButton` (40 × 40 px, zone 44 px, `aria-label` en français). Pas de `<Button>` dont le seul contenu est une icône ou « … ».
- Pas d'icône sans libellé pour une action rare ou ambiguë : préférer un bouton avec icône 16 px et libellé (« Exporter (CSV) »).

### 3.4 Correspondance action → icône

Noms à exporter depuis `frontend/src/design-system/icons.ts`. L'`aria-label` donné est celui par défaut ; un écran peut le préciser (« Retirer Jean K. »).

| Nom métier | Icône Lucide | `aria-label` / libellé | Usage |
| --- | --- | --- | --- |
| `IconBack` | `ArrowLeft` | « Retour » (ou « Retour aux plans »…) | Retour à la page parente, retour au niveau précédent d'une modale |
| `IconClose` | `X` | « Fermer » | Croix de modale, de tiroir, de bandeau d'aide |
| `IconRemove` | `X` | « Retirer {élément} » | Croix d'une puce (filtre, joueur, image) — même dessin, 16 px |
| `IconMenu` | `Menu` | « Ouvrir le menu » | Barre supérieure mobile |
| `IconMore` | `Ellipsis` | « Plus d'actions » | Menu « … » (horizontal partout, y compris pied de barre latérale) |
| `IconUndo` / `IconRedo` | `Undo2` / `Redo2` | « Annuler » / « Rétablir » | Tableau noir |
| `IconEdit` | `Pencil` | « Modifier » | |
| `IconDelete` | `Trash2` | « Supprimer » | Toujours dans un menu « … » ou une modale de détail, suivi d'un `ConfirmDialog` |
| `IconAdd` | `Plus` | « Ajouter… » (verbe précis) | Bouton de création ; « + » du `NumberField` |
| `IconDecrease` | `Minus` | « Diminuer » | « − » du `NumberField` |
| `IconSearch` | `Search` | — | Loupe dans `DataTable`, `PlayerSearch`, `ClubSearch`, `ArticleSearch` |
| `IconFilter` | `SlidersHorizontal` | « Filtres » (libellé visible) | Bouton « Filtres » de `DataTable` |
| `IconChevronLeft` / `IconChevronRight` | `ChevronLeft` / `ChevronRight` | « Année précédente » / « Année suivante », « Image précédente »… | Navigation par période ou par élément ; pagination |
| `IconChevronDown` | `ChevronDown` | — | Zone repliable, `Select` natif ; tourne de 180° à l'ouverture |
| `IconSortAsc` / `IconSortDesc` | `ArrowUp` / `ArrowDown` | (porté par `aria-sort`) | En-tête de colonne triée ; colonne non triée : rien |
| `IconMoveUp` / `IconMoveDown` | `ArrowUp` / `ArrowDown` | « Monter » / « Descendre » | Réordonner (ordre du jour d'AG) |
| `IconCheck` | `Check` | — | Case cochée, action réussie dans un toast |
| `IconLock` | `Lock` | — | Joueur non éligible (pion, suggestion), séance verrouillée, canal du bureau, transfert bloqué |
| `IconPin` | `Pin` | — | Communiqué épinglé |
| `IconNotifications` | `Bell` | « Notifications » | `NotificationBell` |
| `IconDownload` | `Download` | « Exporter (CSV) », « Télécharger » | Exports, reçus, PDF |
| `IconUpload` | `Upload` | « Importer » | Import CSV |
| `IconCamera` | `Camera` | « Prendre une photo » | `FileField` mobile |
| `IconAttachment` | `Paperclip` | « Choisir un fichier » | `FileField` |
| `IconImage` | `Image` | — | Image indisponible (`AuthenticatedImage`) |
| `IconError` | `CircleAlert` | — | `EmptyState` variante erreur, erreur de champ, bandeau d'erreur |
| `IconWarning` | `TriangleAlert` | — | Bandeau `warning` / `danger` |
| `IconInfo` | `Info` | — | Bandeau `info`, aide |
| `IconSuccess` | `CircleCheck` | — | Toast de succès |
| `IconEmpty` | `Inbox` | — | `EmptyState` par défaut |
| `IconLoading` | `LoaderCircle` | — | Bouton `loading`, action en cours (16 px, `animate-spin`) |
| `IconOffline` | `WifiOff` | — | `SyncIndicator` hors connexion |
| `IconPublic` / `IconPrivate` | `Globe` / `Users` | — | Visibilité d'une publication (fil) |
| `IconShow` / `IconHide` | `Eye` / `EyeOff` | « Afficher » / « Masquer » le mot de passe | |
| `IconLogout` | `LogOut` | « Se déconnecter » | Menu utilisateur |
| `IconTheme` | `Palette` | « Thème » | Menu utilisateur |

**Barre d'outils du tableau noir (design system 3.8)** : Sélection `MousePointer2`, Flèche `MoveUpRight`, Zone `Square`, Texte `Type`, Gomme `Eraser`, Annuler `Undo2`, Rétablir `Redo2`.

**Navigation de la barre latérale (3.9)** — aujourd'hui, aucun élément de `AppLayout.tsx` (l. 50 à 85) ne porte d'icône, alors que le 3.9 en prévoit une de 20 px. Proposition :

| Entrée | Icône |
| --- | --- |
| Accueil | `House` |
| Vestiaire du jour | `Shirt` |
| Fil d'actualité | `Newspaper` |
| Mon profil | `UserRound` |
| Comité et bureau | `Users` |
| Assemblées générales | `Landmark` |
| Communiqués | `Megaphone` |
| Chat | `MessagesSquare` |
| Espace coach | `ClipboardList` |
| Séances | `CalendarDays` |
| Matchs | `Trophy` |
| ~~Plan tactique~~ (entrée supprimée le 16/11/2026, plans dans Vestiaire › Plans) | ~~`Presentation`~~ (retirée) |
| Discipline | `Gavel` |
| Trésorerie — Tableau de bord | `Wallet` |
| Grille des cotisations | `Grid3x3` |
| Dépenses | `Receipt` |
| Assistance sociale | `HandHeart` |
| Médical | `Stethoscope` |
| Matériel | `Package` |
| Mercato | `ArrowLeftRight` |
| Espace Superuser (entrées d'administration) | `Shield` |

Une icône identique ne sert jamais à deux entrées de navigation différentes.

---

## 4. Recensement des remplacements à faire

Relevé du 06/10/2026 sur `frontend/src`. Chaque ligne : fichier, ligne, état actuel, remplacement attendu.

### 4.1 Glyphes Unicode utilisés comme icônes

| # | Fichier : ligne | Actuel | Remplacement |
| --- | --- | --- | --- |
| 1 | `routes/sport/TableauNoirPage.tsx:558` | `↶` dans `IconButton` « Annuler » | `IconUndo` 20 px |
| 2 | `routes/sport/TableauNoirPage.tsx:559` | `↷` dans `IconButton` « Rétablir » | `IconRedo` 20 px |
| 3 | `routes/sport/TableauNoirPage.tsx:660` | `←` dans `IconButton` « Retour aux plans » | `IconBack` 20 px |
| 4 | `routes/sport/TableauNoirPage.tsx:673` | `⋯` dans `IconButton` « Menu du plan » | `IconMore` 20 px ; `aria-label` « Plus d'actions » |
| 5 | `routes/admin/UserDetailModal.tsx:95` | `…` dans `IconButton` | `IconMore` |
| 6 | `routes/admin/ClubDetailModal.tsx:67` | `…` dans `IconButton` | `IconMore` |
| 7 | `routes/club/communiques/AnnouncementDetailModal.tsx:110` | `…` dans un `Button` secondaire | `IconButton` + `IconMore`, `aria-label` « Plus d'actions » |
| 8 | `routes/club/assemblees/AssembleesPage.tsx:108` | `…` dans un bouton de menu | `IconButton` + `IconMore` |
| 9 | `routes/logistics/ArticleDetailModal.tsx:105` | `…` dans un `Button` ghost | `IconButton` + `IconMore`, `aria-label` à ajouter s'il manque |
| 10 | `routes/mercato/OfferDetailModal.tsx:226` | `…` dans un `Button` ghost | idem 9 |
| 11 | `routes/mercato/FichePubliqueModal.tsx:63` | `…` dans un `Button` ghost | idem 9 |
| 12 | `routes/medical/InjuryDetailModal.tsx:282` | `…` dans un bouton bordé | `IconButton` variante `secondary` + `IconMore` |
| 13 | `routes/medical/InjuryDetailModal.tsx:320` | idem | idem |
| 14 | `routes/fil/PostDetailModal.tsx:139` | `⋯` dans un bouton `p-2` | `IconButton` + `IconMore` |
| 15 | `routes/fil/PostDetailModal.tsx:217` | `⋯` sur un bouton « Supprimer le commentaire » | **Erreur de sens** : le glyphe annonce un menu alors que l'action supprime. `IconButton` + `IconDelete` (16 px dans la ligne de commentaire, zone tactile 44 px conservée), suivi d'un `ConfirmDialog` |
| 16 | `routes/treasury/GrilleCotisationsPage.tsx:446` | `‹` « Année précédente » | `IconButton` + `IconChevronLeft` |
| 17 | `routes/treasury/GrilleCotisationsPage.tsx:455` | `›` « Année suivante » | `IconButton` + `IconChevronRight` |
| 18 | `routes/treasury/GrilleCotisationsPage.tsx:489` | `×` « Fermer l'aide » | `IconButton` + `IconClose` |
| 19 | `routes/treasury/ImportContributionsModal.tsx:588` | `‹` année précédente | `IconButton` + `IconChevronLeft` |
| 20 | `routes/treasury/ImportContributionsModal.tsx:598` | `›` année suivante | `IconButton` + `IconChevronRight` |
| 21 | `routes/treasury/ImportContributionsModal.tsx:687` | `‹ Modifier le type, l'année ou le fichier` | `Button` ghost avec `IconChevronLeft` 16 px à gauche du libellé |
| 22 | `design-system/components/DataTable.tsx:218` | `×` « Retirer le filtre » | `IconRemove` 16 px |
| 23 | `design-system/components/DataTable.tsx:276` | `▲` / `▼` tri | `IconSortAsc` / `IconSortDesc` 16 px |
| 24 | `design-system/components/PlayerSearch.tsx:363` | `×` « Retirer {joueur} » | `IconRemove` 16 px |
| 25 | `routes/fil/ImagePickerField.tsx:92` | `×` « Retirer l'image » (pastille de 24 px) | `IconRemove` 16 px ; la pastille garde 24 px visibles mais reçoit une zone tactile de 44 px (pseudo-élément) |
| 26 | `routes/sport/VestiairePage.tsx:288` | `▴` / `▾` dans le libellé | `IconChevronDown` 16 px avec rotation 180° animée (2.2) |
| 27 | `routes/club/ComiteBureauPage.tsx:298` | texte « CSV » passé comme icône | `Button` secondaire `sm` « Exporter (CSV) » avec `IconDownload` 16 px (design system 3.3) |

À **conserver** (flèches typographiques dans une phrase, pas des icônes) : `routes/treasury/RecordPaymentModal.tsx:422`, `routes/treasury/ImportContributionsModal.tsx:193`, `routes/mercato/OfferDetailModal.tsx:215`. `design-system/components/PlayerTradingCard.tsx:270` (`—` valeur absente) est du texte, à conserver. `IconButton.test.tsx:7` (`x`) est un test : à laisser ou aligner, sans effet sur l'interface.

### 4.2 SVG d'icônes faits main à remplacer par Lucide

| # | Fichier : ligne | Icône actuelle | Remplacement |
| --- | --- | --- | --- |
| 28 | `design-system/components/Modal.tsx:335` | croix | `IconClose` 20 px |
| 29 | `design-system/components/Sidebar.tsx:217` | trois points | `IconMore` 20 px |
| 30 | `design-system/components/Sidebar.tsx:291` | menu (trois traits) | `IconMenu` 20 px |
| 31 | `design-system/components/Sidebar.tsx:316` | croix du tiroir | `IconClose` 20 px |
| 32 | `design-system/components/NumberField.tsx:18` et `:26` | moins / plus | `IconDecrease` / `IconAdd` |
| 33 | `design-system/components/EmptyState.tsx:30` à `:48` | icônes par défaut et d'erreur | `IconEmpty` / `IconError` 24 px |
| 34 | `design-system/components/DataTable.tsx:174` | loupe | `IconSearch` 16 px |
| 35 | `design-system/components/PlayerSearch.tsx:141` | loupe | `IconSearch` 16 px |
| 36 | `design-system/components/ClubSearch.tsx:149` | loupe | `IconSearch` 16 px |
| 37 | `design-system/components/ArticleSearch.tsx:160` | loupe | `IconSearch` 16 px |
| 38 | `design-system/components/PitchBoard.tsx:251` | cadenas | `IconLock` 16 px |
| 39 | `design-system/components/TransferTimeline.tsx:30` | cadenas plein 12 px | `IconLock` 16 px (linéaire) |
| 40 | `design-system/components/AuthenticatedImage.tsx:62` | image | `IconImage` 20 px |
| 41 | `design-system/components/Button.tsx:73` | bordure tournante | `IconLoading` 16 px + `animate-spin` |
| 42 | `routes/treasury/KebabMenu.tsx:46` | trois points | `IconMore` |
| 43 | `routes/profil/ProfilPage.tsx:146` | trois points | `IconMore` |
| 44 | `routes/fil/PostCard.tsx:98` | trois points | `IconMore` |
| 45 | `routes/fil/PostCard.tsx:138` | visibilité publique / club | `IconPublic` / `IconPrivate` 16 px |
| 46 | `routes/fil/ImageViewerModal.tsx:64` | croix | `IconClose` |
| 47 | `routes/fil/ImageViewerModal.tsx:77` / `:99` | chevrons gauche / droite (24 px) | `IconChevronLeft` / `IconChevronRight` 20 px |
| 48 | `routes/club/communiques/CommuniquesPage.tsx:16` | épingle pleine | `IconPin` 16 px |
| 49 | `routes/club/chat/ChatPage.tsx:12` | icônes de canal (cadenas…) | `IconLock` pour le canal du bureau, `Users` pour le canal général, 20 px |
| 50 | `routes/club/assemblees/ConveneAssemblyWizard.tsx:21` / `:29` | flèches haut/bas, croix | `IconMoveUp` / `IconMoveDown` / `IconRemove` |
| 51 | `routes/medical/InjuryReportModal.tsx:190` | cadenas (mention de confidentialité) | `IconLock` 16 px |
| 52 | `routes/logistics/AddMatchEquipmentModal.tsx:135` | croix | `IconRemove` |
| 53 | `routes/dev/DesignSystemDemo.tsx:229` | cloche | `IconNotifications` (page de démonstration) |
| 54 | `layouts/AppLayout.tsx:50` à `:85` | aucune icône de navigation | ajouter les icônes du tableau 3.4 « Navigation » |

À **conserver** en SVG propre (graphismes, pas des icônes) : `PitchBoard.tsx:88` (`PitchMarkings`), `PitchBoard.tsx:119` (`AnnotationsLayer`), `PlayerTradingCard.tsx:111` (`PlayerSilhouette`).

### 4.3 Écarts d'animation existants

| # | Fichier : ligne | Écart | Correction |
| --- | --- | --- | --- |
| 55 | `design-system/components/Skeleton.tsx:17`, `:54` ; `Loader.tsx:76` ; `AuthenticatedImage.tsx:72` | `animate-pulse` de Tailwind (2 s) | animation `skeleton` à 1,2 s (design system 3.5) |
| 56 | `design-system/components/Loader.tsx:72` | barre de progression en pulsation | glissement indéterminé (2.2) |
| 57 | `design-system/components/Modal.tsx` | pas d'animation d'ouverture ni de fermeture | animations 2.2 avec `data-state` |
| 58 | `design-system/components/Sidebar.tsx` (tiroir mobile), `Toast.tsx`, menus « … » | pas d'animation | animations 2.2 |
| 59 | `PlayerTradingCard.tsx:216`, `PlayerTradingCard.css:35`, `:156` | durées et courbes écrites en dur (`300ms ease-out`, `200ms ease-out`) | `var(--duration-slow) var(--ease-out)`, `var(--duration-base) var(--ease-out)` |

---

## 5. Ordre d'intégration conseillé pour `frontend-dev`

1. Installer `lucide-react` ; créer `design-system/icons.ts` (tableau 3.4) et l'exporter depuis `design-system/index.ts`.
2. Ajouter les tokens de mouvement et les `@keyframes` dans `tokens.css`.
3. Composants du design system (lignes 22 à 24, 28 à 41, 55 à 59) : ils couvrent la majorité des écrans d'un coup.
4. Écrans (lignes 1 à 21, 25 à 27, 42 à 54).
5. Vérification à 360 px en thèmes Classic, Clair et Sombre, et avec le mouvement réduit activé.
6. Contrôle final : aucune occurrence restante de `↶ ↷ ← ⋯ … ‹ › × ▲ ▼ ▴ ▾` utilisée comme contenu de bouton dans `frontend/src` (les flèches de phrase listées en 4.1 exceptées), aucun `<svg` d'icône hors de `PitchBoard` et `PlayerTradingCard`, aucun import direct de `lucide-react` hors de `design-system/icons.ts`.

## 6. Points à valider par le client

1. Icônes proposées pour la navigation (tableau 3.4) : notamment « Assemblées générales » (`Landmark`), qui n'ont pas d'équivalent évident.
2. Sobriété des animations : uniquement des apparitions/disparitions courtes (≤ 300 ms) et des changements d'état, pas d'animation décorative (2.3). Si le client attendait des effets plus visibles, c'est à trancher ici, car la charte (3.1 « densité maîtrisée », réseau faible) va dans le sens de la sobriété.
