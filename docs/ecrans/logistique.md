# Écran — Matériel (logistique)

Sources : CDC 3.1 à 3.6, 2.2 (Intendant), 2.4 (ligne « Matériel et inventaires »), 4.5.2 (dépenses), 4.8 (équipements reçus pour un match), 4.13, 4.17, 5.2 (« Logistique » journalisée), 6.5 (cron), 6.6 ; CLAUDE.md §2 (règles 6, 8, 13 à 20) ; `docs/lot0/schema-donnees.md` §7 (`Article`, `StockMovement`, `Inventory`, `InventoryLine`) et §17 (`inventory_open_alert`) ; `docs/lot0/design-system.md`. Écrans liés : `sport-feuille-de-match.md` §3 point 7 et §4.5 (équipements reçus), `tresorerie-depenses-assistance.md` §3.3 (détail d'une dépense).

Composants : `PageHeader`, `Banner`, `Card`, `ListSection`, `DataTable`, `StatusBadge`, `Modal`, `ConfirmDialog`, `PlayerSearch`, `NumberField`, `SegmentedControl`, `EmptyState`, `Skeleton`, `Toast`. Un seul composant nouveau : `ArticleSearch` (§4.8), variante du combobox de `PlayerSearch` (design system §3.4, « variantes du même composant »).

## 1. Objectif

Donner à l'Intendant un outil simple pour savoir ce que le club possède, ce qui sort et ce qui rentre. Au trimestre, il compare le stock réel au stock calculé et justifie chaque écart. Le Président est alerté quand un inventaire n'est pas clôturé. Usage réel : l'Intendant compte les maillots dans le local ou au bord du terrain, sur son smartphone, parfois avec un réseau faible.

## 2. Accès

Route `/materiel`. Entrée « Matériel » dans le groupe « Club » de la barre latérale (déjà prévue au design system §3.9).

| Rôle | Accès (matrice 2.4) | Ce qu'il peut faire sur cette page |
| --- | --- | --- |
| Intendant | É | Tout : articles, mouvements, inventaire (ouvrir, compter, justifier, clôturer), retour d'équipements d'un match |
| Président | L | Consultation. Reçoit l'alerte hebdomadaire (§6). Aucun bouton d'action. |
| Vice-président, Trésorier | L | Consultation seule |
| Coach | L | Consultation seule. Il sort les équipements d'un match depuis la feuille de match (`sport-feuille-de-match.md` §4.5), pas depuis cette page. |
| Directeur sportif, Trésorier adjoint, Capitaine, Médecin, Joueur | — | Pas d'entrée de menu. Un accès direct à l'adresse affiche « Vous n'avez pas accès à cette page. » |

Les actions non autorisées sont **masquées**, pas désactivées. Les droits viennent de l'API (permissions renvoyées avec les données). L'interface ne les déduit jamais d'un nom de rôle. Toutes les données sont limitées au club actif.

## 3. Structure de la page

**En-tête** : titre « Matériel » ; contexte « {nom du club} · {libellé du trimestre en cours} » (ex. « 3e trimestre 2026 », libellé fourni par l'API). Action principale (Intendant) : « Enregistrer un mouvement ». Menu « … » (Intendant) : « Ajouter un article ».

**Bandeaux** (sous l'en-tête, dans cet ordre) :

1. Lecture seule (licence expirée) et hors connexion : modèles standards du design system.
2. **Inventaire non clôturé** (§6.1), visible par tous les rôles qui ont accès à la page.

**Sections en cartes, dans l'ordre** :

1. **Inventaire trimestriel** (§6) — état de l'inventaire en cours ou du dernier inventaire, avec l'action du moment.
2. **Catalogue** — `DataTable` des articles et de leur stock.
3. **Sortis pour un match** — équipements prêtés pour un match et pas encore rendus en totalité.
4. **Registre des mouvements** — `DataTable` de tous les mouvements.
5. **Inventaires passés** — 5 derniers inventaires clôturés, puis « Voir plus ».

Footer.

### 3.1 Carte « Catalogue »

- En-tête de carte : « Catalogue » + compteur « {n} articles ». Action de carte (Intendant) : « Ajouter un article » (bouton `sm` secondaire).
- `DataTable` (le catalogue peut dépasser 30 articles, 3.3) :
  - recherche « Rechercher un article » ;
  - filtres : « Catégorie » (Maillots, Bas, Bottines, Ballons, Matériel divers), « État » (Neuf, Bon état, Usé, Abîmé), case « Afficher les articles archivés » (décochée par défaut) ;
  - colonnes : **Article** (figée : nom, et unité en 13 px dessous) · Catégorie · **En stock** (alignée à droite, tabular-nums, « {n} {unité} ») · Sortis (match) (nombre prêté pour un match et non rendu, « — » si 0) · État · Statut (`StatusBadge` « Archivé » seulement pour un article archivé, sinon vide) ;
  - tri par défaut : catégorie, puis nom ; 20 lignes par page.
- Le stock affiché est **toujours la valeur renvoyée par l'API**. Elle est calculée à partir des mouvements et n'est jamais stockée (schéma §7.1). L'interface ne fait aucune addition.
- Stock à 0 : la valeur « 0 » s'affiche normalement, sans couleur d'alerte. Aucun seuil d'alerte n'est prévu au 4.13.
- Clic sur une ligne → modale « Article » (§4.1).

### 3.2 Carte « Sortis pour un match »

- Lignes (5 dernières sorties non soldées, puis « Voir plus ») : « {adversaire} · {dim. 4 oct. 2026} » en première ligne ; « {article} · {quantité sortie} sortis · {quantité rendue} rendus » en seconde ligne ; `StatusBadge` « Sorti » (orange) ou « Rendu partiellement » (orange).
- Clic → modale « Équipements du match » (§4.6), la même que celle de la feuille de match.
- Cette carte rend visible sur la page Matériel ce que le Coach a sorti depuis la feuille de match. Elle permet aussi à l'Intendant d'enregistrer le retour.

### 3.3 Carte « Registre des mouvements »

- `DataTable` (dépasse vite 30 lignes) :
  - recherche « Rechercher un article ou un joueur » ;
  - filtres : « Sens » (Entrée, Sortie), « Type » (Achat, Dotation, Retour, Distribution, Prêt pour un match, Usure, Perte), « Catégorie », « Période » (plage de dates), « Lié à » (Un match, Une dépense) ;
  - colonnes : Date · **Article** (figée) · Type · Quantité (« +12 » ou « −3 », alignée à droite, tabular-nums, jamais en couleur seule : le signe porte l'information) · Joueur (avatar 24 + nom, ou « — ») · Lien (« Match du {date} », « Dépense du {date} » ou « — ») · Saisi par ;
  - tri par défaut : date décroissante, puis heure de saisie ; 20 lignes par page.
- Clic sur une ligne → modale « Mouvement » (§4.3).

### 3.4 Carte « Inventaires passés »

- 5 derniers inventaires clôturés, puis « Voir plus ». Ligne : « {3e trimestre 2026} », « Clôturé le {date} par {nom} », « {n} écart(s) justifié(s) », `StatusBadge` « Clôturé » (vert).
- Clic → modale « Inventaire du {trimestre} » en lecture seule (§4.9).

## 4. Modales

Toutes les modales de formulaire suivent le design system §3.2 : fermeture par la croix, Échap ou un clic sur le voile ; confirmation « Abandonner les modifications ? » si la saisie a commencé ; pied fixe toujours visible ; plein écran sur mobile.

### 4.1 « Article » (détail) — taille `lg`

- En-tête : nom de l'article ; sous-titre « {catégorie} · {unité} » ; `StatusBadge` « Archivé » s'il y a lieu.
- Corps :
  - trois valeurs en ligne (`KpiTile` compacts) : « En stock » ({n} {unité}), « Sortis pour un match » ({n}), « État » ({Neuf / Bon état / Usé / Abîmé}) ;
  - « Derniers mouvements » : 10 derniers mouvements de cet article (date, type, quantité signée, joueur, lien), puis « Voir plus ». Clic → modale « Mouvement » au niveau 2 ;
  - mention en bas : « Ajouté par {nom} le {date}. »
- Pied : « Fermer » / (Intendant, article actif) « Enregistrer un mouvement » (ouvre §4.4 au niveau 2, article prérempli).
- Menu « … » de l'en-tête (Intendant) : « Modifier l'article » (§4.2) ; « Archiver l'article » ou « Réactiver l'article ».
  - « Archiver l'article » → `ConfirmDialog` « Archiver {nom} ? » — texte « L'article n'apparaîtra plus dans les choix de mouvement ni dans les prochains inventaires. Son historique est conservé. » — « Annuler » / « Archiver ». Succès : « Article archivé. »
  - Si l'API refuse l'archivage, son motif s'affiche dans le bandeau d'erreur du `ConfirmDialog` (par exemple un stock non nul, si le client retient cette règle : point ouvert n° 6).

### 4.2 « Ajouter un article » / « Modifier l'article » — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Nom | TextField | Oui | 120 caractères max. ; « Ce champ est obligatoire. » |
| Catégorie | SegmentedControl sur deux lignes à 360 px (« Maillots », « Bas », « Bottines », « Ballons », « Matériel divers ») ; `Select` natif à partir de 640 px | Oui | « Choisissez une catégorie. » |
| Unité | TextField, prérempli « pièce » | Oui | 20 caractères max. ; aide « Par exemple : pièce, paire, lot. » |
| État | SegmentedControl « Neuf » / « Bon état » / « Usé » / « Abîmé » | Oui, « Neuf » par défaut | — |

Aide sous le formulaire (création seulement) : « Le stock démarre à 0. Enregistrez ensuite une entrée (achat, dotation) pour indiquer les quantités. » La quantité ne se saisit pas ici : le stock est toujours la somme des mouvements (schéma §7.1).

Pied : « Annuler » / « Enregistrer ». Succès (création) : toast « Article ajouté. » avec action « Enregistrer une entrée » (ouvre §4.4, article prérempli, sens « Entrée »). Succès (modification) : « Article modifié. »

### 4.3 « Mouvement » (détail) — taille `md`

- En-tête : « {Achat / Dotation / …} · {article} » ; sous-titre « {date} ».
- Corps en lecture : sens, type, article, quantité signée avec unité, date, motif (ou « Aucun motif »), joueur concerné (avatar + nom) ; lien vers le match (« Voir le match », ouvre la page du match) ; lien vers la dépense (voir ci-dessous) ; « Saisi par {nom} le {date heure} ». Une saisie faite en Ghost Mode affiche « Système Vesta » (5.4).
- **Dépense liée** :
  - Président, Vice-président, Trésorier : ligne « Dépense du {date} · {catégorie} · {montant} » + lien « Voir la dépense ». Le lien ouvre le détail de la dépense de `tresorerie-depenses-assistance.md` §3.3.
  - Intendant et Coach : ligne « Dépense du {date} · {catégorie} · {montant} », sans lien, sans bénéficiaire, sans motif ni justificatif (point ouvert n° 1).
- Pied : « Fermer ». **Aucune action de modification ni de suppression** (point ouvert n° 5).

### 4.4 « Enregistrer un mouvement » — taille `md` (Intendant)

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Sens | SegmentedControl « Entrée » / « Sortie » | Oui | Change les choix de « Type ». |
| Type | SegmentedControl. Entrée : « Achat », « Dotation », « Retour ». Sortie : « Distribution », « Prêt pour un match », « Usure », « Perte » | Oui | « Choisissez le type de mouvement. » |
| Article | `ArticleSearch` (§4.8), articles actifs du club | Oui | « Choisissez un article. » |
| Quantité | NumberField − / +, ≥ 1, suffixe = unité de l'article | Oui | « Saisissez une quantité supérieure à 0. » Sortie au-delà du stock, erreur renvoyée par l'API : « Quantité supérieure au stock disponible ({n}). » (même texte que la feuille de match) |
| Date | DateField, date du jour par défaut | Oui | « La date ne peut pas être dans le futur. » (message standard ; proposition, point ouvert n° 9) |
| Joueur concerné (facultatif) | `PlayerSearch` portée `club` | Non | Affiché pour « Distribution », « Prêt pour un match », « Retour », « Perte ». Jamais de liste déroulante de joueurs. |
| Match (facultatif) | Champ de recherche « Rechercher un match » (même combobox, source : matchs du club, les plus proches d'aujourd'hui d'abord ; ligne : adversaire, date) | Non | Affiché seulement pour « Prêt pour un match » et « Retour ». |
| Dépense liée (facultatif) | Champ de recherche « Rechercher une dépense » (même combobox, §4.8) | Non | Affiché seulement pour « Achat ». Aide : « Rattachez l'achat à la dépense saisie par la trésorerie. » |
| Motif (facultatif) | TextArea | Non | 500 caractères max. |

- Aucune règle de stock n'est calculée dans l'interface. Le contrôle de quantité est fait par l'API ; l'erreur s'affiche sous « Quantité ».
- Pied : « Annuler » / « Enregistrer le mouvement ». Succès : toast « Mouvement enregistré. Stock de {article} : {n} {unité}. » (valeur renvoyée par l'API). Le catalogue et le registre se mettent à jour sans rechargement.
- Hors connexion : bouton de pied désactivé, aide « Cette action nécessite une connexion. » Le 6.6 ne cite pas la logistique, et le stock est contrôlé par le serveur.

### 4.5 « Ajouter des équipements » (depuis la feuille de match) — taille `md` (Coach)

Cette modale complète `sport-feuille-de-match.md` §4.5. Le rapport de la tâche 3.7 indique qu'elle n'a pas été livrée faute de route `apps.logistics`. Elle s'ouvre depuis l'action « Ajouter des équipements » de la section « Équipements reçus » de la page du match.

- Sous-titre : « {nom du club} – {adversaire} · {date} ».
- Lignes répétables (une ligne par article) :
  - « Article » : `ArticleSearch` en mode sortie (§4.8) ; un article déjà choisi sur une autre ligne n'est plus proposé ;
  - « Quantité » : NumberField ≥ 1 ; erreur API « Quantité supérieure au stock disponible ({n}). » ;
  - icône « Retirer la ligne » (`IconButton`, `aria-label` « Retirer {article} »).
- Bouton ghost « Ajouter une ligne » sous la dernière ligne. Une ligne vide est présente à l'ouverture.
- Aide : « Chaque équipement crée une sortie « Prêt pour un match » dans le registre du matériel. Enregistrez le retour après le match. »
- Pied : « Annuler » / « Enregistrer ». Succès : « Équipements enregistrés. Sortie ajoutée au registre du matériel. » (texte déjà validé dans la feuille de match).
- Le mouvement est de type « Prêt pour un match », lié au match, et « Saisi par » = le Coach (4.13 : « les équipements reçus par le Coach créent une sortie »).
- Si une ligne est refusée par l'API (stock insuffisant, article archivé entre-temps), l'erreur s'affiche sur cette ligne et **rien n'est enregistré**. Proposition : enregistrement tout ou rien, pour ne pas laisser une sortie partielle que le Coach n'aurait pas vue (point ouvert n° 10).
- Hors connexion : bouton désactivé, « Cette action nécessite une connexion. » (déjà proposé dans la feuille de match, §7 point 4).

### 4.6 « Équipements du match » (détail) — taille `md`

Ouverte depuis la section « Équipements reçus » de la feuille de match ou depuis la carte « Sortis pour un match » (§3.2).

- En-tête : « Équipements · {adversaire} » ; sous-titre « {date du match} ».
- Liste : article, « {n} sortis le {date} », « {m} rendus », `StatusBadge` « Sorti » (orange, rien de rendu), « Rendu partiellement » (orange) ou « Rendu » (vert, tout rendu). Pour une ligne partiellement rendue : « {k} non rendus » en 14 px (information critique, 10.2 n° 31).
- Pied : « Fermer » / (Coach, Intendant ; au moins une ligne non soldée) « Enregistrer le retour ».

**Sous-modale « Enregistrer le retour »** (niveau 2, taille `md`) :

- Une ligne par article non soldé : nom, « Sortis : {n} · déjà rendus : {m} », champ « Quantité rendue » (NumberField, 0 à {n − m}, prérempli avec {n − m}).
- « Observation (facultatif) » (TextArea, 500 caractères max.).
- Erreur : « La quantité rendue ne peut pas dépasser la quantité sortie ({n}). »
- Pied : « Annuler » / « Enregistrer le retour ». Succès : « Retour enregistré. » Chaque quantité rendue crée une entrée « Retour » liée au match.
- Une quantité rendue inférieure à la quantité sortie laisse la ligne en « Rendu partiellement ». Ce qui manque n'est ni requalifié en perte ni en usure par l'interface (point ouvert n° 3).

### 4.7 « Justifier l'écart » — taille `sm` (panneau bas sur mobile) — Intendant

- Titre : « Justifier l'écart » ; sous-titre : « {article} ».
- Rappel en lecture : « Stock théorique : {t} · Stock compté : {p} · Écart : {+/−e} {unité} » (tabular-nums, 16 px).
- Champ « Cause de l'écart » : SegmentedControl « Vol » / « Usure » / « Oubli » / « Perte » (4.13, liste fermée). Erreur : « Choisissez la cause de l'écart. »
- Pied : « Annuler » / « Justifier ». Succès : « Écart justifié. » La ligne passe au badge « Justifié » (vert).
- Une justification déjà faite peut être changée tant que l'inventaire est ouvert. La modale s'ouvre alors avec la cause actuelle sélectionnée.

### 4.8 `ArticleSearch` et recherches liées (composant à ajouter au design system)

Même comportement que `PlayerSearch` (design system §3.4 : combobox ARIA, debounce 250 ms, 8 suggestions, suggestions dans le flux sur mobile, puce de sélection avec « Changer »). Seule la source change.

| Variante | Placeholder | Ligne de suggestion | Éléments grisés (raison venant de l'API) |
| --- | --- | --- | --- |
| `ArticleSearch` mode entrée | « Nom de l'article » | Nom, « {catégorie} · {unité} », à droite « En stock : {n} » | Aucun ; les articles archivés ne sont pas proposés |
| `ArticleSearch` mode sortie | « Nom de l'article » | Idem | Stock nul : grisé « Stock épuisé » |
| Recherche de match | « Adversaire ou date » | « {adversaire} · {date} » | Aucun |
| Recherche de dépense | « Catégorie, date ou montant » | « {date} · {catégorie} · {montant} » + `StatusBadge` de la dépense | Dépenses non rattachables selon l'API, avec la raison (point ouvert n° 1) |

Textes : aide « Tapez le nom de l'article. » ; aucun résultat « Aucun article ne correspond à « {saisie} ». » ; erreur « Recherche impossible. Vérifiez votre connexion. »

La recherche de dépense n'expose **que** la date, la catégorie, le montant et le statut, jamais le bénéficiaire, le motif ou le justificatif. C'est un filtre côté API, pas un masquage côté interface.

### 4.9 « Inventaire du {trimestre} » (détail) — taille `lg`

- En-tête : « Inventaire du {3e trimestre 2026} » ; `StatusBadge` « En cours », « Non clôturé » ou « Clôturé » ; sous-titre « Ouvert le {date} par {nom} » (et « · clôturé le {date} par {nom} »).
- Barre haute collante : recherche « Rechercher un article » ; puces « Tous », « À compter », « Écarts à justifier », « Justifiés » ; résumé « {c} articles comptés sur {m} · {e} écarts à justifier ».
- `DataTable` des lignes : **Article** (figée) · Théorique · Compté · Écart (« +2 », « −3 », « 0 ») · Cause (« Vol », « Usure », « Oubli », « Perte » ou « — ») · `StatusBadge` (« À compter » gris, « À justifier » orange, « Justifié » vert, « Sans écart » vert).
  - La colonne « Théorique » affiche l'instantané figé au moment du comptage (schéma §7.3). Elle reste vide (« — ») tant que l'article n'est pas compté.
  - Inventaire ouvert, Intendant : clic sur une ligne « À justifier » ou « Justifié » → §4.7 au niveau 2.
- Pied selon l'état :
  - ouvert, Intendant : « Fermer » / « Saisir le comptage » (§4.10). « Clôturer l'inventaire » est dans le menu « … » de l'en-tête, et aussi dans la carte de la page (§6.2) ;
  - ouvert, autres rôles, ou clôturé : « Fermer ».

### 4.10 « Saisir le comptage » — taille `xl` (plein écran sur mobile) — Intendant

- Titre : « Comptage · {3e trimestre 2026} ».
- Barre haute collante : recherche « Rechercher un article » ; puces de catégorie (« Toutes », « Maillots », « Bas », « Bottines », « Ballons », « Divers ») ; puce « Pas encore comptés » ; résumé « {c} sur {m} comptés ».
- Une ligne par article actif du catalogue (hauteur 56 px) : nom, « {catégorie} · {unité} », champ « Stock compté » (NumberField − / +, ≥ 0, clavier numérique, 16 px). Les articles déjà comptés affichent la valeur saisie, modifiable tant que l'inventaire est ouvert.
- **Comptage à l'aveugle** (proposition, point ouvert n° 8) : le stock théorique n'est pas affiché dans cette modale, pour que l'Intendant compte réellement au lieu de recopier. L'écart apparaît après l'enregistrement, dans la carte et dans le détail (4.13 : « l'application affiche l'écart »).
- Un champ laissé vide = article non compté (pas d'enregistrement de 0 implicite). Erreur : « Saisissez un nombre entier supérieur ou égal à 0. »
- Pied : « Annuler » / « Enregistrer le comptage » (enregistre toutes les lignes modifiées). L'enregistrement partiel est normal : on peut compter en plusieurs fois.
- Succès : toast « Comptage enregistré : {n} article(s). {e} écart(s) à justifier. » La modale se ferme et la carte « Inventaire trimestriel » montre les écarts.
- Si le stock compté d'un article déjà justifié change, l'écart est recalculé par l'API. Si la valeur de l'écart change, la justification est effacée et la ligne repasse « À justifier » (proposition, point ouvert n° 8). Toast complémentaire : « {n} justification(s) à refaire après modification. »
- Hors connexion : bouton de pied désactivé, « Cette action nécessite une connexion. » Les valeurs saisies restent dans la modale tant qu'elle n'est pas fermée.

## 5. Lien avec les dépenses et avec les matchs

### 5.1 Dépenses (4.13 « un achat peut être rattaché à la dépense correspondante »)

- **Sens du lien** : un mouvement d'entrée « Achat » porte une référence facultative à une dépense (`StockMovement.expense`, schéma §7.2). C'est l'Intendant qui crée le lien, depuis « Enregistrer un mouvement » (§4.4).
- **Côté trésorerie** : à ajouter dans `tresorerie-depenses-assistance.md` §3.3 (« Détail de la dépense »), une section en lecture « Matériel acheté » : « {article} · {quantité} {unité} · entré le {date} » pour chaque mouvement lié, et un lien « Voir dans le matériel » (ouvre `/materiel`, modale « Mouvement »). La section est visible par le Président, le Vice-président et le Trésorier, qui ont un accès en lecture au matériel. Elle est **masquée pour le Trésorier adjoint**, qui n'a aucun accès au matériel (matrice 2.4). Sans lien : section absente, pas d'état vide.
- Une dépense peut être liée à plusieurs mouvements (plusieurs articles achetés sur une seule facture). La réciproque (un mouvement lié à plusieurs dépenses) n'est pas prévue par le schéma.

### 5.2 Matchs (4.8 et 4.13 « les équipements reçus par le Coach créent une sortie, puis un retour »)

| Étape | Où | Qui | Mouvement créé |
| --- | --- | --- | --- |
| Sortie | Feuille de match, « Ajouter des équipements » (§4.5) ; ou page Matériel, « Enregistrer un mouvement », type « Prêt pour un match » + match (§4.4) | Coach (feuille de match) ; Intendant (page Matériel) | Sortie « Prêt pour un match », liée au match |
| Suivi | Feuille de match, section « Équipements reçus » ; page Matériel, carte « Sortis pour un match » | Lecture : tous les rôles qui voient ces pages | — |
| Retour | Modale « Équipements du match » → « Enregistrer le retour » (§4.6) | Coach et Intendant (proposition déjà faite dans la feuille de match, point ouvert n° 4) | Entrée « Retour », liée au match |

La section « Équipements reçus » de la feuille de match affiche, par ligne : article, « {n} sortis · {m} rendus », `StatusBadge` « Sorti » / « Rendu partiellement » / « Rendu ». Son état vide reste « Aucun équipement enregistré pour ce match. » + (Coach) « Ajouter des équipements ».

## 6. Inventaire trimestriel, blocage et alerte au Président

### 6.1 Bandeau « Inventaire non clôturé »

Condition d'affichage : l'API signale que l'inventaire d'un trimestre est toujours ouvert et qu'il bloque l'ouverture du suivant (`blocking_inventory` dans la réponse). L'interface n'évalue **jamais** elle-même la date de fin du trimestre.

- `Banner` `danger` sous l'en-tête de la page Matériel, pour tous les rôles qui y ont accès.
- Texte : « L'inventaire du {3e trimestre 2026} n'est pas clôturé : l'inventaire du {4e trimestre 2026} ne peut pas être ouvert. »
- Deuxième ligne (13 px) : « Reste à faire : {c} article(s) à compter, {e} écart(s) à justifier. »
- Action du bandeau :
  - Intendant : « Reprendre l'inventaire » (ouvre §4.9) ;
  - Président, VP, Trésorier, Coach : « Voir l'inventaire » (§4.9 en lecture).
- Le bandeau ne se ferme pas (pas de croix) tant que la situation dure.

### 6.2 Carte « Inventaire trimestriel » — états

| État (fourni par l'API) | Contenu de la carte | Action (Intendant seulement) |
| --- | --- | --- |
| Aucun inventaire jamais ouvert | `EmptyState` « Aucun inventaire pour l'instant. » ; précision « L'inventaire compare le stock compté au stock enregistré, une fois par trimestre. » | « Ouvrir l'inventaire du {trimestre} » |
| Dernier inventaire clôturé, ouverture possible | « Dernier inventaire : {2e trimestre 2026}, clôturé le {date}. » | « Ouvrir l'inventaire du {3e trimestre 2026} » |
| Ouverture impossible pour une autre raison renvoyée par l'API | Même texte + raison de l'API en 14 px | Bouton désactivé, raison en aide |
| Inventaire en cours | `StatusBadge` « En cours » (orange) ; « Ouvert le {date} par {nom} » ; barre de progression fine « {c} articles comptés sur {m} » ; liste « Écarts à justifier » (5 premiers : article, « Écart : −3 », badge « À justifier » ; puis « Voir plus ») ; lien « Voir tout l'inventaire » (§4.9) | Principale : « Saisir le comptage » (§4.10). Secondaire : « Clôturer l'inventaire » |
| Inventaire non clôturé (bloquant) | Comme « En cours », mais `StatusBadge` « Non clôturé » (rouge) et le bandeau §6.1 en haut de page | Idem. Aucun bouton d'ouverture d'un nouvel inventaire n'est affiché. |

**Bouton d'ouverture bloqué** : dans l'état bloquant, l'action « Ouvrir l'inventaire du {trimestre suivant} » n'est pas affichée, même désactivée, pour ne pas laisser croire qu'elle existe. Le bandeau explique le blocage. Si l'Intendant appelle quand même l'ouverture (double onglet, lien ancien), l'API refuse et l'interface affiche son message dans un toast d'erreur : « L'inventaire du {3e trimestre 2026} doit d'abord être clôturé. »

**Ouvrir l'inventaire** → `ConfirmDialog` « Ouvrir l'inventaire du {3e trimestre 2026} ? » — texte « Vous saisirez ensuite le stock compté de chaque article. Le stock théorique de chaque article est figé au moment de son comptage. » — « Annuler » / « Ouvrir l'inventaire ». Succès : « Inventaire du {3e trimestre 2026} ouvert. » La modale « Saisir le comptage » ne s'ouvre pas d'elle-même : l'Intendant la lance quand il est devant le matériel.

**Clôturer l'inventaire** :

- Désactivé tant que l'API ne l'autorise pas. L'aide sous le bouton reprend la raison de l'API, par exemple « Comptez tous les articles et justifiez chaque écart avant de clôturer. ({c} à compter, {e} à justifier) ».
- Autorisé → `ConfirmDialog` « Clôturer l'inventaire du {3e trimestre 2026} ? » — texte « Les comptages et les justifications ne pourront plus être modifiés. L'inventaire du trimestre suivant pourra ensuite être ouvert. » — « Annuler » / « Clôturer ». Pas de code PIN : la clôture ne figure pas dans la liste du 7.2.
- Succès : « Inventaire du {3e trimestre 2026} clôturé. » Le bandeau §6.1 disparaît. L'inventaire rejoint « Inventaires passés ».

### 6.3 Alerte hebdomadaire au Président (4.13, schéma §17 `inventory_open_alert`)

- **Canal** : notification in-app (cloche), une fois par semaine, envoyée par la tâche cron tant que l'inventaire bloquant reste ouvert. L'email n'est pas prévu : le tableau 4.17 ne cite pas cet événement (point ouvert n° 2).
- **Destinataire** : le Président (4.13). Il n'a qu'un accès en lecture au matériel : la notification l'informe et lui permet de relancer l'Intendant, pas d'agir à sa place.
- **Texte proposé pour l'annexe E** :
  - titre : « Inventaire du {T3 2026} non clôturé » ;
  - corps : « L'inventaire du {3e trimestre 2026} est toujours ouvert ({c} article(s) à compter, {e} écart(s) à justifier). L'inventaire suivant ne peut pas être ouvert tant qu'il n'est pas clôturé. »
- **Clic** : ouvre `/materiel` puis la modale « Inventaire du {trimestre} » en lecture.
- **Accueil** : proposition d'ajouter, pour le Président et l'Intendant, un bandeau rouge sur l'accueil identique au §6.1, sur le modèle du bandeau « dépense non justifiée » (`club-accueil.md` §4). C'est un choix de présentation qui n'est pas exigé par le 4.13 (point ouvert n° 2).

## 7. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Barre de progression 3 px + squelette (titre, 4 cartes) | — | Chaque carte échoue seule (variante erreur d'`EmptyState`, « Réessayer ») |
| Inventaire trimestriel | Squelette `card` | Voir §6.2 | « Impossible de charger l'inventaire. » + « Réessayer ». Le bandeau §6.1 n'est pas affiché si l'état est inconnu. |
| Catalogue | 5 lignes squelettes | « Aucun article dans le catalogue. » + (Intendant) « Ajouter un article » ; avec filtre : « Aucun résultat pour « {recherche} ». » + « Effacer les filtres » | Modèle standard |
| Sortis pour un match | 2 lignes | « Aucun équipement sorti pour un match. » | Modèle standard |
| Registre des mouvements | 5 lignes squelettes | « Aucun mouvement enregistré. » + (Intendant) « Enregistrer un mouvement » ; avec filtre : modèle « aucun résultat » | Modèle standard |
| Inventaires passés | 2 lignes | « Aucun inventaire clôturé. » | Modèle standard |
| Modales de détail | Squelette du corps, titre affiché dès l'ouverture | Derniers mouvements d'un article : « Aucun mouvement pour cet article. » | « Impossible de charger ce détail. » + « Réessayer » |
| Toute action | Bouton en état `loading` (« Enregistrement… ») | — | Erreur sous le champ concerné ou dans le bandeau d'erreur de la modale ; saisie conservée |
| Hors connexion | — | — | Actions d'écriture désactivées avec « Cette action nécessite une connexion. » ; consultation des données déjà chargées |
| Licence expirée | — | — | Bandeau `readonly`, actions masquées (design system §5) |

## 8. Mobile (360 px) et ordinateur

- **360 px** :
  - une colonne, marges 12 px, titre 20 px ; les cartes dans l'ordre du §3 ;
  - l'Intendant est dans son local ou au bord du terrain : l'action « Enregistrer un mouvement » reste dans l'en-tête (pas de bouton flottant) ;
  - tableaux : colonne « Article » figée, défilement horizontal dans le cadre, jamais de la page ; filtres dans un panneau bas ;
  - « Saisir le comptage » en plein écran : barre de recherche et résumé collants en haut, pied collant au-dessus du clavier. Chaque NumberField fait 40 px de haut, ses boutons − / + ont une zone de 44 px. Le focus passe à la ligne suivante avec la touche « Suivant » du clavier ;
  - SegmentedControl à 4 options (« Vol », « Usure », « Oubli », « Perte ») sur une ligne ; les 5 catégories d'article sur deux lignes.
- **≥ 640 px** : modales centrées (`md` 560 px, `lg` 800 px, `xl` 960 px).
- **≥ 1024 px** : deux colonnes 8/4. Principale : Catalogue, Registre des mouvements. Latérale : Inventaire trimestriel, Sortis pour un match, Inventaires passés. Le bandeau §6.1 occupe toute la largeur au-dessus des deux colonnes.
- Trois thèmes via variables CSS ; badges aux couleurs fixes ; quantités en tabular-nums ; aucun texte critique en 13 px (les quantités et écarts sont en 14 px au moins, 10.2 n° 31).

## 9. Libellés et statuts

- Catégories : « Maillots », « Bas », « Bottines », « Ballons », « Matériel divers ».
- États d'article : « Neuf », « Bon état », « Usé », « Abîmé » (texte simple, pas de badge de statut).
- Types de mouvement : « Achat », « Dotation », « Retour » (entrées) ; « Distribution », « Prêt pour un match », « Usure », « Perte » (sorties).
- Causes d'écart : « Vol », « Usure », « Oubli », « Perte ».
- Trimestre : « {1er / 2e / 3e / 4e} trimestre {année} » en toutes lettres, « T{n} {année} » dans les titres de notification. Libellés fournis par l'API.

Clés de `StatusBadge` à ajouter à `statusMap.ts` (propositions, design system §2.5) :

| Clé | Libellé | Famille |
| --- | --- | --- |
| `equipment_out` | Sorti | orange |
| `equipment_partially_returned` | Rendu partiellement | orange |
| `equipment_returned` | Rendu | vert |
| `inventory_open` | En cours | orange |
| `inventory_overdue` | Non clôturé | rouge |
| `inventory_closed` | Clôturé | vert |
| `inventory_line_to_count` | À compter | gris |
| `inventory_line_no_gap` | Sans écart | vert |
| `inventory_line_justified` | Justifié | vert |
| (existante) `to_justify` | À justifier | orange |
| (existante) `archived` | Archivé | gris |

## 10. Journal et notifications

- Chaque création d'article, modification, archivage, mouvement, retour, ouverture d'inventaire, comptage, justification et clôture écrit une entrée dans le journal d'activité (CLAUDE.md règle 6, CDC 5.2 « Logistique »). C'est le rôle de l'API. L'interface affiche seulement « Saisi par {nom} le {date} ».
- Notifications : seule l'alerte hebdomadaire du §6.3 est prévue par le 4.13. Aucune autre notification n'est inventée ici.

## 11. Décisions appliquées

- **CDC 4.13** : blocage de l'inventaire suivant et alerte hebdomadaire au Président, repris tels quels (§6).
- **10.2 n° 31** : 13 px réservé aux libellés secondaires ; quantités, écarts et raisons de blocage en 14 px ou plus.
- **10.2 n° 16** : sans objet ici (aucune donnée de santé).
- Aucune règle de stock, de trimestre ou de clôture n'est évaluée par l'interface. Elle affiche ce que l'API renvoie : stock, écart, possibilité d'ouvrir ou de clôturer, raison d'un refus.

## 12. Points ouverts à faire trancher par le client

1. **Accès de l'Intendant aux dépenses : contradiction entre 4.13 et la matrice 2.4.** Le 4.13 prévoit qu'un achat « peut être rattaché à la dépense correspondante » ; le registre est tenu par l'Intendant. Mais la matrice 2.4 ne lui donne **aucun accès** aux dépenses (« Saisie d'une dépense » et « Validation d'une dépense » : « — » pour Int). **Position provisoire, la plus prudente** : l'Intendant rattache l'achat au moyen d'une recherche qui n'expose que la date, la catégorie, le montant et le statut. Jamais le bénéficiaire, le motif ni le justificatif. Le filtrage est fait par l'API. Alternative à proposer au client : le lien est fait par le Trésorier depuis le détail de la dépense, mais le Trésorier n'a qu'un accès en lecture au matériel. Autre question : quelles dépenses peut-on rattacher ? Proposition : dépenses libérées, justifiées ou non justifiées, jamais en attente ni refusées.
2. **Alerte au Président.** Le canal (in-app seul, ou aussi par email ?) n'est pas précisé : le tableau 4.17 ne cite pas cet événement. Faut-il aussi alerter l'Intendant, qui est le seul à pouvoir clôturer ? Faut-il ajouter un bandeau sur l'accueil (§6.3) ?
3. **Ce qui n'est pas rendu après un match.** Si 18 maillots sur 20 reviennent, les 2 manquants restent en sortie « Prêt pour un match » et le stock théorique en tient déjà compte. Rien n'oblige à les qualifier (perte, usure). Faut-il demander une cause pour la part non rendue, ou laisser l'inventaire la révéler ? Aucune règle n'est appliquée par l'interface en attendant.
4. **Qui enregistre le retour des équipements d'un match ?** Déjà ouvert dans `sport-feuille-de-match.md` §7. Proposition reprise : Coach et Intendant.
5. **Correction d'un mouvement erroné.** Le 4.13 ne dit pas si un mouvement peut être modifié ou supprimé. Position provisoire, la plus prudente : aucune modification ni suppression dans l'interface, puisque le registre sert de base au stock et à l'inventaire. Le mode de correction reste à décider : mouvement inverse avec motif, ou modification journalisée.
6. **Archivage d'un article dont le stock n'est pas nul.** Autorisé ou refusé ? L'interface affiche la réponse de l'API.
7. **Stock existant au démarrage.** Le club pilote possède déjà du matériel. Aucun type de mouvement ne correspond à un « stock initial » : achat et dotation faussent l'historique, et un premier inventaire créerait des écarts « Oubli » artificiels. Faut-il un type d'entrée « Stock initial » ? Ce serait un ajout à faire passer par le circuit 9.4.
8. **Déroulé du comptage.** Trois propositions de présentation, sans règle métier nouvelle, à valider : (a) comptage à l'aveugle, sans afficher le stock théorique pendant la saisie ; (b) chaque article actif doit être compté avant clôture (à confirmer côté API) ; (c) si le comptage d'une ligne change et que l'écart change, la justification est à refaire.
9. **Date d'un mouvement dans le futur.** Proposition : refusée (message standard). À confirmer.
10. **Sortie d'équipements pour un match à plusieurs lignes.** Proposition : tout ou rien, si une ligne est refusée.
11. **Définition du « trimestre non clôturé » (4.13 et schéma §7.3), à faire préciser.** Le schéma dit : alerte « tant qu'il reste ouvert ». Pris à la lettre, un inventaire ouvert au milieu de son propre trimestre déclencherait déjà l'alerte hebdomadaire. La lecture qui paraît naturelle : l'alerte et le blocage ne s'appliquent qu'une fois le trimestre de l'inventaire terminé. Deux autres questions en découlent. Un trimestre écoulé **sans aucun inventaire ouvert** bloque-t-il aussi, et déclenche-t-il l'alerte ? Les trimestres sont-ils ceux du calendrier ou ceux de la saison du club ? L'interface affiche l'état renvoyé par l'API dans tous les cas.
12. **Effet de la clôture sur le stock théorique.** Le 4.13 et le schéma ne disent pas si la clôture ajuste le stock théorique au stock compté, par exemple avec une sortie « Perte » ou « Usure » pour chaque écart justifié. Sans ajustement, le même écart réapparaît à l'inventaire suivant. Deux points à trancher : l'ajustement lui-même, puis le type de mouvement pour « Vol », « Oubli » et un écart positif (plus de matériel que prévu), qui n'existent pas dans les types de mouvement du schéma. Le texte de confirmation de clôture (§6.2) ne promet rien sur ce point.
13. **Intendant vacant.** Si le poste est vacant, personne ne peut clôturer un inventaire (le Président n'a qu'un accès en lecture). Le blocage durerait jusqu'à une nomination. Est-ce voulu ?
