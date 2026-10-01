# Écran — Club : carte de joueur (style FC/FIFA, effet 3D)

Sources : CDC 4.2 (carte, fiche détaillée, comparaison, visibilité publique), 3.1 à 3.6, 4.8 (mise à jour des statistiques), 4.9, 4.10, 6.3 (données publiques), 6.7, 7.5 (consentement de publication, mineurs), 9.1 (lots), 10.2 n° 16. Remarque client : `inscriptions.md` l. 5 (« la carte du joueur doit ressembler à celle de carte joueur de FIFA avec effet 3D »). Écrans liés : `club-comite-bureau.md` §4.7 (modale « Fiche du joueur »), `comptes-mon-profil.md` §4.4 (« Ma carte de joueur »). Composants et tokens : `docs/lot0/design-system.md`.

Ce document a **deux parties strictement séparées** :

- **Partie A — Livrable maintenant** : refonte visuelle de la carte avec les seules données déjà servies par l'API (`PlayerPublicCardSerializer`). Aucune statistique, aucune note.
- **Partie B — Lot 4, NE PAS IMPLÉMENTER MAINTENANT** : carte complète (note globale et six indicateurs) et comparaison de 2 à 4 joueurs. Décrite ici pour que `backend-dev` et `frontend-dev` l'aient sous la main au Lot 4 ; elle dépend de données qui n'existent pas encore (matchs, buts, passes, cartons, présences : Lot 3 ; évaluations : Lot 3 selon le CDC 9.1 ; cartes et comparaison : Lot 4).

Aucun chiffre ne doit être inventé, simulé ou affiché « pour la démonstration » dans la partie A (CLAUDE.md §3).

---

# PARTIE A — Version disponible maintenant

## A1. Objectif

Donner à la « Fiche du joueur » l'allure d'une carte de joueur FC/FIFA : un objet d'identité fort, aux couleurs du club connecté, avec un relief 3D. La carte ne présente que des informations réelles : photo, nom, poste, poste précis, numéro, logo du club. Le statut d'adhésion et les rôles restent affichés sous la carte, dans une section sobre.

## A2. Accès

La carte reste dans la modale existante `frontend/src/routes/club/PlayerCardModal.tsx`. Aucune page dédiée n'est créée (règle 13).

| Point d'entrée | Titre de la modale |
| --- | --- |
| Comité et bureau › Effectif › clic sur une ligne (`club-comite-bureau.md` §3 section 6) | « Fiche du joueur » |
| Mon profil › menu « … » › « Voir ma carte de joueur » (`comptes-mon-profil.md` §3) | « Ma carte de joueur » (libellé de `comptes-mon-profil.md` §4.4 ; aujourd'hui le code affiche « Fiche du joueur » dans les deux cas) |
| Séance, plan tactique, vestiaire › pion › « Voir la fiche du joueur » (specs du Lot 3, quand ces écrans existeront) | « Fiche du joueur » |

| Rôle | Accès |
| --- | --- |
| Tout membre actif du club | Lecture de la carte de n'importe quel joueur **de son club** (API `GET /clubs/players/{id}/card/`, `IsActiveClubMember`, isolation par le manager tenant-aware ; un joueur d'un autre club donne 404) |
| Parrain désigné, Président | Boutons conditionnels du pied, inchangés (`club-comite-bureau.md` §4.7) |

**Rappel sur le consentement de publication (CDC 7.5, `card_publication_consent_at`)** : la partie A ne rend la carte visible **qu'aux membres connectés du même club**. Ce n'est pas une publication publique, donc le consentement n'y intervient pas. Toute exposition hors du club (fil public, marché, comparaison entre clubs : partie B) devra passer par une vue publique dédiée (CDC 6.3) qui exclut les joueurs sans consentement et masque par défaut les mineurs. Le composant de carte ne décide jamais seul de la publication.

## A3. Structure de la modale

Modale `Modal`, taille `lg` (plein écran sur mobile, 800 px sur ordinateur), titre selon A2. Pas de sous-titre.

Corps, dans l'ordre :

1. **La carte** (`PlayerTradingCard`, voir A4), centrée.
2. **Section « Au club »** : une carte neutre standard (`bg-surface`, bordure `--color-border`, rayon `--radius-lg`, padding 12 px), sur fond de modale, **hors** de la carte FIFA :
   - `StatusBadge` du statut d'adhésion, avec le libellé servi par l'API (`membership_status_label`) ; voir le point ouvert 3 (10.2 n° 16).
   - « Membre depuis {mois année} » (14 px, `--color-text-muted`), à partir de `joined_on`, au format du club (ex. « Membre depuis mars 2024 »). Ligne masquée si `joined_on` est vide.
   - Sous-titre « Rôles » (14 px, semi-gras) puis les rôles en puces (`bg-surface-muted`, 13 px, hauteur 24 px). Si aucun : « Aucun rôle particulier. »

Pied (règle 3.2 et `club-comite-bureau.md` §4.7) : bouton secondaire « Fermer », toujours visible. S'y ajoutent, inchangés, les boutons conditionnels « Signer la fiche d'adhésion » (parrain désigné, joueur « En attente ») et « Décider de l'adhésion » (Président, après refus ou silence du parrain). **Écart actuel** : `PlayerCardModal.tsx` l. 39 passe `hideFooter` ; la modale n'a donc ni « Fermer » ni emplacement pour ces boutons. À corriger dans la même tâche.

Aucune donnée financière ni médicale, ni sur la carte ni dans la section « Au club » (CDC 4.2, visibilité ; la réponse de l'API ne les contient déjà pas).

## A4. Composant `PlayerTradingCard` (design system)

Nouveau composant `frontend/src/design-system/components/PlayerTradingCard.tsx`, exporté par `design-system/index.ts`. Il est commun à la fiche, à « Ma carte de joueur » et, au Lot 4, à la comparaison et au fil public. Il ne fait aucun appel réseau.

### A4.1 Propriétés (partie A)

| Propriété | Type | Remarque |
| --- | --- | --- |
| `firstName`, `lastName` | texte | Obligatoires |
| `photoUrl` | texte ou `null` | `null` : silhouette (A4.4) |
| `positionLabel` | texte | Vide : « Poste non renseigné » |
| `positionDetail` | texte | Facultatif (poste précis) |
| `jerseyNumber` | nombre ou `null` | `null` : pas de numéro sur la carte (A4.3) |
| `clubLogoUrl` | texte ou `null` | Partie A : `useClubBranding().logoUrl` (club actif, le seul possible pour cette API) |
| `clubName` | texte | Sert seulement au texte alternatif du logo. Partie A : `useClubBranding().name`. Jamais écrit en dur |
| `motion` | `"interactive"` ou `"static"` | Défaut `"interactive"` (A5) |

Les propriétés du Lot 4 (`overallRating`, `stats`, `size`, `onOpen`, `palette`) sont décrites en B2 ; elles **ne sont pas créées maintenant**.

### A4.2 Gabarit

- Largeur : `min(100%, 280px)`. Hauteur : automatique (aucune hauteur fixe, pour qu'un nom long ne déborde jamais). Hauteur attendue en partie A : environ 320 px.
- **Silhouette de carte à collectionner** : rectangle aux coins supérieurs biseautés de 18 px et au bord inférieur légèrement en pointe (le milieu du bas descend de 10 px), obtenu par `clip-path: polygon(...)`. Les coins restent lisibles à 360 px.
- **Cadre** : deux couches découpées par le même `clip-path` : la couche extérieure est un dégradé de `--color-player-card-frame` vers `--color-player-card-frame-highlight` (reflet métallique, en diagonale 135°) ; la couche intérieure, en retrait de 3 px, porte le fond de la carte.
- **Fond** : dégradé linéaire 160° de `--color-player-card-from` (haut) vers `--color-player-card-to` (bas), plus une bande de reflet diagonale fixe (blanc à 8 %, 40 px de large, à 30 % de la largeur) pour l'aspect glacé. Aucune image de fond.
- **Relief au repos** (tous appareils, sans mouvement) : ombre portée `drop-shadow(0 10px 18px rgb(0 0 0 / 0.28))` et `drop-shadow(0 2px 4px rgb(0 0 0 / 0.2))` posée sur l'élément parent (une `box-shadow` serait coupée par le `clip-path`, voir A5.3) ; liseré intérieur clair de 1 px en haut (blanc à 25 %) et foncé en bas (noir à 25 %) pour l'effet biseauté.

### A4.3 Contenu de la carte (partie A)

De haut en bas, padding intérieur de 14 px :

1. **Zone haute**, en deux colonnes :
   - **Colonne gauche** (72 px) :
     - numéro de maillot, 24 px, gras, chiffres tabulaires, `--color-player-card-fg` ; lu par les lecteurs d'écran « Numéro {n} » ;
     - dessous, le poste en toutes lettres, 13 px, semi-gras, `--color-player-card-fg-muted`, retour à la ligne autorisé, **jamais de majuscules forcées ni d'abréviation** (« Défenseur », pas « DEF ») ;
     - dessous, séparateur de 24 × 1 px (`--color-player-card-fg-muted`) puis le logo du club : 28 × 28 px dans une pastille ronde de 32 px en `--color-surface`, pour que tout logo reste visible sur n'importe quelle couleur de club. Texte alternatif : « Logo de {nom du club} ». Pas de logo : pastille absente (jamais d'initiales de club inventées).
     - Sans numéro : la colonne commence directement par le poste.
   - **Colonne droite** : la photo, 152 × 152 px, rayon 10 px, liseré de 2 px en `--color-player-card-frame`, `object-fit: cover`, `loading="lazy"`, `decoding="async"`. Texte alternatif : « Photo de {prénom} {nom} ». C'est l'élément dominant de la carte.
2. **Bandeau du nom**, sur toute la largeur intérieure, collé sous la photo : fond **opaque** `--color-player-card-band-bg`, texte `--color-player-card-band-fg`, padding 8 × 12 px, centré.
   - « {Prénom} {Nom} », 18 px, gras, 2 lignes au plus, `text-wrap: balance`, `overflow-wrap: anywhere` ; **aucune ellipse ni coupure** (CDC 4.2 : aucun libellé tronqué). Si le nom demande une 3e ligne, la carte s'allonge.
   - Dessous, si `positionDetail` est rempli : poste précis, 13 px, `--color-player-card-band-fg` à l'opacité du `fg-muted` (valeur de token, pas d'opacité libre), retour à la ligne autorisé.
3. **Pied de carte (partie A)** : une seule pastille centrée « Statistiques à venir », 13 px, hauteur 24 px, bordure 1 px `--color-player-card-fg-muted`, texte `--color-player-card-fg`, fond transparent. Marge haute 12 px, basse 18 px (pour la pointe). Rien d'autre : pas de grille vide, pas de tirets, pas de zéros.

   Motif : la place des indicateurs est signalée sans afficher de fausses valeurs. La carte reste compacte ; au Lot 4, la pastille est remplacée par la grille B2.3 (la carte grandit alors d'environ 110 px).

Aucun texte n'est posé directement sur la photo.

### A4.4 Absence de photo

Silhouette de joueur (SVG en ligne, trait `--color-player-card-fg-muted`, 50 % de la zone) centrée dans la zone photo, sur fond `--color-player-card-band-bg`. **Pas d'initiales en grand** (pas de gros caractères décoratifs, 3.1) : le nom figure déjà dans le bandeau. Même rendu si l'image échoue au chargement (`onError`).

### A4.5 Accessibilité

- La carte est un `<figure aria-label="Carte de joueur de {prénom} {nom}">`. En partie A, elle n'est ni cliquable ni focalisable.
- L'effet 3D est purement décoratif : aucune information ne dépend du mouvement ni de la couleur seule.
- `prefers-reduced-motion: reduce` : aucune inclinaison, aucune animation d'entrée, aucun reflet mobile (déjà coupé globalement par `tokens.css` ; le composant ne doit pas relancer d'animation JavaScript dans ce cas).

## A5. Effet 3D

Réalisé en **CSS pur** (`perspective`, `transform`, variables CSS mises à jour par un petit gestionnaire de pointeur). **`framer-motion` n'est pas une dépendance du projet** (`frontend/package.json`) et n'est pas nécessaire. Aucune nouvelle librairie.

### A5.1 Ordinateur (`@media (hover: hover) and (pointer: fine)`)

- **Inclinaison qui suit la souris** : au survol, la carte pivote de ±8° au plus (`rotateX` selon la position verticale du pointeur, `rotateY` selon sa position horizontale) et grossit à 1,02. Calcul : `rotateY = (x − 0,5) × 16°`, `rotateX = (0,5 − y) × 16°`, avec x et y la position relative du pointeur (0 à 1).
- **Profondeur (parallaxe)** : la photo se décale de 6 px au plus et la colonne gauche de 3 px au plus, dans le sens du pointeur (`translate` 2D, voir A5.3).
- **Reflet** : un calque entre le fond et le contenu, `radial-gradient` blanc de 0 à **12 %** d'opacité centré sur le pointeur (`--mx`, `--my`). Le calque est sous le texte : le contraste du texte n'est jamais réduit.
- Mise à jour par `requestAnimationFrame`, en écrivant des variables CSS sur l'élément (`--rx`, `--ry`, `--mx`, `--my`), **jamais par un état React** (pas de rendu à chaque mouvement). `will-change: transform` seulement pendant le survol.
- Sortie du pointeur : retour à plat en 300 ms, `ease-out`.

### A5.2 Mobile et tablette (écran tactile)

**Position retenue : carte statique en relief, sans inclinaison au doigt ni au gyroscope.**

- Relief permanent (A4.2 : ombre, cadre métallique, biseau, bande de reflet).
- **Animation d'ouverture** unique, sur tous les appareils : la carte arrive en `rotateY(−14°)` et `opacity: 0`, puis se pose à plat en 450 ms (`cubic-bezier(0.2, 0.8, 0.2, 1)`) ; 200 ms plus tard, un reflet traverse une fois la carte en diagonale (700 ms). Plus rien ne bouge ensuite.
- Pourquoi pas le gyroscope : sur iPhone, `DeviceOrientationEvent.requestPermission()` impose une fenêtre d'autorisation du système, déroutante pour une simple fiche ; au bord du terrain, la carte tremblerait en main et, en plein soleil, un reflet mobile gêne la lecture ; enfin, c'est un coût de batterie pour un effet décoratif. Voir le point ouvert 1 si le client y tient.
- Pourquoi pas l'inclinaison au doigt : la modale défile verticalement sur 360 px ; capter le glisser sur la carte (`touch-action: none`) bloquerait le défilement quand le pouce est posé dessus. Et au Lot 4, le toucher sur la carte ouvrira la fiche détaillée (B2.5).

### A5.3 Contraintes techniques à respecter

- Structure en trois niveaux : **A** conteneur (`perspective: 900px`) › **B** élément incliné (`transform: rotateX(var(--rx)) rotateY(var(--ry))`, porte le `filter: drop-shadow`) › **C** carte découpée (`clip-path`, cadre, fond, contenu).
- `clip-path` et `filter` aplatissent le rendu 3D des enfants (`transform-style` repasse à `flat`) : la profondeur des calques se fait donc par **translations 2D** (A5.1), pas par `translateZ`.
- L'ombre est sur B, jamais sur C : un `drop-shadow` sur l'élément découpé serait coupé par son propre `clip-path`.

## A6. Couleurs : tokens de la carte

Le dégradé suit le thème de l'utilisateur, comme le reste de l'application : **Classic** = couleurs du club (servies par l'API) ; **Clair** et **Sombre** = versions neutres (CDC 3.6). Aucune couleur de club n'est écrite dans le code (règle 18).

Nouveaux tokens, à ajouter dans `frontend/src/design-system/tokens/tokens.css` (valeurs Clair dans `@theme`, surcharge dans `[data-theme="dark"]`) :

| Token | Clair (défaut, aussi Classic sans couleurs de club) | Sombre | Usage |
| --- | --- | --- | --- |
| `--color-player-card-from` | `#1D4ED8` | `#1E40AF` | Haut du dégradé |
| `--color-player-card-to` | `#1E3A8A` | `#172554` | Bas du dégradé |
| `--color-player-card-fg` | `#FFFFFF` | `#F3F4F6` | Numéro, pastille |
| `--color-player-card-fg-muted` | `#DBEAFE` | `#BFDBFE` | Poste, séparateurs, silhouette |
| `--color-player-card-band-bg` | `#172554` | `#0B1220` | Bandeau du nom, fond de la zone photo vide |
| `--color-player-card-band-fg` | `#FFFFFF` | `#F3F4F6` | Nom, poste précis |
| `--color-player-card-frame` | `#C7CED8` | `#6B7A94` | Cadre, liseré de la photo |
| `--color-player-card-frame-highlight` | `#F6F7F9` | `#B8C1CE` | Reflet du cadre |

Ratios obtenus (formule de `color-contrast.ts`) : blanc sur `#1D4ED8` 6,7:1 et sur `#1E3A8A` environ 10:1 ; `#DBEAFE` sur `#1D4ED8` 5,5:1 et sur `#1E3A8A` 8,5:1 ; blanc sur `#172554` 14,7:1 ; `#F3F4F6` sur `#1E40AF` 7,9:1 ; `#BFDBFE` sur `#1E40AF` 6,1:1.

**Classic avec couleurs de club** : `ThemeContext` dérive ces tokens à l'exécution et les ajoute à `CLASSIC_ACCENT_PROPERTIES` (retirés hors Classic, comme les autres) :

1. `from` = `deriveAccentPair(primary).bg` ; `fg` = `deriveAccentPair(primary).fg`.
2. `to` : si `fg` est clair, `from` assombri de 30 % ; si `fg` est foncé, `from` éclairci de 30 %. Le second arrêt s'éloigne toujours de la couleur du texte : le contraste ne peut que s'améliorer vers le bas de la carte.
3. `band-bg` : `to` poussé encore de 15 % dans le même sens ; `band-fg` = `fg`. Exigence : **≥ 7:1** (nom lu en plein soleil). Sinon, poursuivre par pas de 5 %.
4. `fg-muted` : `fg` mélangé à 20 % vers `from`, contrôlé **≥ 4,5:1 sur `from` et sur `to`** ; sinon, réduire le mélange par pas de 5 % (même méthode que `--color-sidebar-text-muted`, design-system §7.2).
5. `frame` = `--color-accent` déjà calculé (couleur secondaire du club, ≥ 3:1 sur la surface : le cadre détache la carte du fond de la modale) ; `frame-highlight` = `frame` mélangé à 40 % vers le blanc.
6. Exigence générale : `fg` ≥ 4,5:1 sur `from` **et** sur `to`, visé 7:1.

La fonction de mélange est celle qu'utilise déjà `deriveClassicSidebarTokens` ; l'exposer si besoin, sans dupliquer. Tests Vitest à prévoir : club marine et rouge, club jaune (texte foncé), club sans couleur (valeurs du Clair).

Exemple, pour information seulement (donnée du club pilote, jamais dans le code) : marine `#1B2143` et rouge `#D2232A` donnent un dégradé marine vers marine très foncé, texte blanc (15,6:1), cadre rouge.

Les couleurs de statut restent hors de la carte : le `StatusBadge` est dans la section « Au club », sur surface neutre (2.4 point 5).

## A7. États

| Zone | Chargement | Vide / absent | Erreur |
| --- | --- | --- | --- |
| Carte | Squelette en forme de carte : bloc `--color-skeleton` 280 × 320 px avec la même silhouette (`clip-path`), animé (`animate-pulse`), puis deux lignes squelettes pour « Au club ». Nouvelle variante `Skeleton variant="player-card"` | Photo absente : silhouette (A4.4) ; poste vide : « Poste non renseigné » ; numéro absent : non affiché ; logo absent : pastille masquée | `EmptyState variant="error"` + « Réessayer » (existant). Joueur introuvable (404) : message de l'API « Ce joueur n'existe pas dans ce club. » + bouton « Fermer » |
| Photo | Fond `--color-player-card-band-bg` pendant le chargement (pas de saut de mise en page : taille réservée) | Silhouette | Silhouette |
| Au club | (squelette ci-dessus) | Rôles : « Aucun rôle particulier. » ; date : ligne masquée | Idem carte |

Pas d'état « succès » : la modale est en lecture seule.

## A8. Mobile (360 px) et ordinateur

- **360 px** : modale plein écran. Carte centrée, largeur 280 px (marge de 24 px de chaque côté du corps de 328 px), puis section « Au club » en pleine largeur. Pied collé en bas avec « Fermer » (et, le cas échéant, le bouton du parrain ou du Président). Le corps défile ; la carte ne capte aucun geste.
- **≥ 640 px** (modale de 800 px) : deux colonnes, carte à gauche (280 px, alignée en haut), section « Au club » à droite (reste de la largeur, gouttière de 24 px). Inclinaison au survol active si `hover: hover` et `pointer: fine`.
- Vérifications obligatoires à 360 px : nom de 40 caractères sur 2 lignes sans coupure ; poste « Défenseur » et poste précis long sans débordement ; thèmes Clair, Sombre et Classic ; photo absente ; logo absent.

## A9. Textes exacts (partie A)

- Titres : « Fiche du joueur » / « Ma carte de joueur ».
- « Poste non renseigné »
- « Statistiques à venir »
- « Au club »
- « Membre depuis {mois année} »
- « Rôles » ; « Aucun rôle particulier. »
- Texte alternatif : « Photo de {prénom} {nom} », « Logo de {nom du club} », « Carte de joueur de {prénom} {nom} », « Numéro {n} ».
- Pied : « Fermer » (+ « Signer la fiche d'adhésion », « Décider de l'adhésion » selon §4.7).

---

# PARTIE B — Version complète (Lot 4)

Préconditions : statistiques de matchs, buts, passes décisives et cartons (4.8, 4.9), présences (4.7) et évaluations (4.10) en place ; vue publique des cartes (6.3) ; règles de calcul de la note globale tranchées (point ouvert 4).

> **Statut au 29/09/2026 (tâche 4.1 du Lot 4, finalisation)** : les Lots 2 et 3 sont livrés, les données sportives existent. La partie B est **implémentable** (tâches 4.6 et 4.8 du plan), **sauf** ce qui dépend d'un point encore ouvert, qui reste bloqué et n'est pas tranché ici :
> - **note globale** (point ouvert 4) : tant qu'il n'est pas tranché, l'API renvoie `overall_rating = null` et la carte affiche « — » (texte alternatif « Note globale : pas encore de donnée ») ; aucune formule provisoire n'est codée ;
> - **période des indicateurs** (point ouvert 5) : la proposition « saison en cours » reste une proposition ; `season_label` est affiché pour que la période soit toujours explicite ;
> - **points d'entrée et accès à la comparaison** (point ouvert 7) : propositions de B3, non tranchées ;
> - **axes du radar** (point ouvert 12, ajouté) et **caractère public des attributs du radar** (point ouvert 13, ajouté).
>
> Compléments de cette finalisation signalés « (finalisation 29/09) » : B3.1 à B3.5, points ouverts 12 à 14. Rien de la partie A n'est modifié.

## B1. Données attendues de l'API (à définir par `backend-dev` au Lot 4)

Calculées par l'API, jamais dans l'interface. Portée par défaut : **saison en cours** du club (point ouvert 5).

| Champ | Affichage | Aucune donnée |
| --- | --- | --- |
| `overall_rating` (entier) | Note globale, zone haute gauche | « — » |
| `matches_played` | Matchs | « 0 » (valeur réelle) |
| `goals` | Buts | « 0 » |
| `assists` | Passes décisives | « 0 » |
| `yellow_cards`, `red_cards` | Cartons | « 0 » |
| `attendance_rate` (pourcentage) | Taux de présence | « — » si aucune séance ni match pointé |
| `average_rating` (décimal sur 10) | Note moyenne | « — » si aucune évaluation |
| `season_label` | « Saison {saison} » sous la carte | — |

Les zéros sont de vraies valeurs ; « — » signifie « pas encore de donnée » et porte le texte alternatif « Pas encore de donnée ».

## B2. Carte complète

### B2.1 Propriétés ajoutées au composant

| Propriété | Remarque |
| --- | --- |
| `overallRating` | Nombre ou `null` |
| `stats` | Objet B1 ou `null`. `null` : pied de la partie A (« Statistiques à venir ») |
| `size` | `"md"` (280 px, défaut) ou `"sm"` (168 px, comparaison, sans grille : note, photo, nom, poste) |
| `onOpen` | Si fourni : la carte devient un bouton « Voir la fiche détaillée de {prénom} {nom} » |
| `palette` | Tokens de couleur d'un **autre club** (comparaison entre clubs, B3), dérivés par la même fonction qu'en A6 et posés en variables sur la carte seule |

### B2.2 Zone haute

- Colonne gauche : **note globale** (24 px, gras, chiffres tabulaires ; texte alternatif « Note globale : {n} ») à la place du numéro, puis le poste en toutes lettres, puis le logo du club.
- Le numéro passe dans le bandeau du nom : « n° {numéro} · {Prénom} {Nom} » ; sans numéro, le nom seul.
- Pas de couleur de carte selon la note (bronze, argent, or) : le CDC ne le prévoit pas, la carte garde les couleurs du club.

### B2.3 Grille des six indicateurs (remplace la pastille « Statistiques à venir »)

Liste de définitions (`<dl>`), 2 colonnes × 3 lignes, séparateurs 1 px `--color-player-card-fg-muted` à 40 %. Chaque cellule : valeur 18 px gras chiffres tabulaires (`--color-player-card-fg`), libellé 13 px (`--color-player-card-fg-muted`) **en toutes lettres, retour à la ligne autorisé, jamais d'ellipse ni d'abréviation** (pas de « MJ », « PD », « PRÉ »).

| Ordre | Libellé exact | Valeur |
| --- | --- | --- |
| 1 | « Matchs » | « 12 » |
| 2 | « Buts » | « 5 » |
| 3 | « Passes décisives » | « 3 » |
| 4 | « Cartons » | total, avec en 2e ligne 13 px « {j} jaunes, {r} rouge(s) » (accord : « 1 jaune », « 0 rouge ») |
| 5 | « Taux de présence » | « 85 % » (espace insécable) |
| 6 | « Note moyenne » | « 7,4 sur 10 » (virgule décimale) |

Les valeurs ci-dessus illustrent le format ; ce ne sont pas des données. Largeur de cellule à 280 px : environ 118 px, suffisante pour « Passes décisives » et « Taux de présence » à 13 px. Si une police système plus large force un retour à la ligne, la cellule grandit.

Sous la carte, hors cadre : « Saison {saison} » (13 px, `--color-text-muted`).

### B2.4 Mise à jour

Les statistiques suivent la feuille de match, y compris les corrections du Coach (4.8) ; la carte relit l'API à chaque ouverture (TanStack Query, pas de cache long).

### B2.5 Clic sur la carte

Ouvre la **fiche détaillée** (CDC 4.2 : Aperçu, Statistiques, Évaluations, Présences, Discipline, Carrière, Aptitude sans diagnostic). Elle fera l'objet d'une spec séparée au Lot 4 (`docs/ecrans/club-fiche-detaillee.md`). La carte y sert d'en-tête. L'onglet « Aptitude » applique 10.2 n° 15 et n° 16.

## B3. Modale « Comparer des joueurs » (CDC 4.2) — taille `xl`

**Points d'entrée (proposition)** : bouton secondaire « Comparer » dans le pied de la « Fiche du joueur » (ouvre la comparaison au niveau 2, avec ce joueur déjà choisi) ; action « Comparer des joueurs » dans le menu « … » de la section Effectif (`club-comite-bureau.md`).

Corps, dans l'ordre :

1. **Choix des joueurs** : `PlayerSearch` multiple, 2 à 4 joueurs, libellé « Ajouter un joueur à comparer ». `SegmentedControl` au-dessus : « Mon club » / « Tous les clubs ». En « Tous les clubs », la recherche passe par la vue publique (6.3) : seuls les joueurs **ayant consenti à la publication de leur carte** apparaissent, les mineurs sont exclus par défaut (7.5), et le club de chaque suggestion est affiché (« {nom} · {club} »). Joueurs choisis : puces avec avatar 24 px, nom, bouton de retrait « Retirer {nom} » (zone tactile 44 px). Jamais de `<select>`.
2. **Cartes** : une `PlayerTradingCard size="sm"` par joueur. Chaque carte d'un autre club garde le logo et les couleurs **de son club** (propriété `palette`, en Classic seulement ; en Clair et Sombre, toutes les cartes sont neutres).
3. **Tableau côte à côte** : première colonne figée (120 px) avec les libellés en toutes lettres, une colonne par joueur. Lignes : « Club », « Poste », « Note globale », les six indicateurs de B2.3, « Saison ». La meilleure valeur de chaque ligne est en gras et suivie de « (meilleur) » en texte masqué pour lecteur d'écran ; aucune mise en valeur sur « Cartons » (pas de jugement). Pas de statut d'adhésion, de rôle, de finance ni de santé.
4. **Radar superposé** : SVG écrit à la main (aucune librairie de graphiques n'est installée ; en ajouter une serait un point ouvert). Un polygone par joueur, avec 4 couleurs de série propres aux graphiques (nouveaux tokens `--color-series-1` à `-4`, distincts des couleurs de statut), des **tracés différents** (plein, tirets, pointillés, tirets-points) et une légende textuelle (nom de chaque joueur) : jamais la couleur seule. Axes : attributs du radar (CDC 4.2, liste définitive à valider avec la grille d'évaluation, 4.10).

Pied : « Fermer ». Pas de formulaire, donc pas de confirmation d'abandon.

**États** :

| Cas | Affichage |
| --- | --- |
| Chargement | Squelettes de cartes `sm` et de 8 lignes de tableau |
| Moins de 2 joueurs | `EmptyState` : « Choisissez au moins 2 joueurs à comparer. » |
| 4 joueurs choisis | Recherche désactivée, aide « 4 joueurs au maximum. Retirez-en un pour en ajouter un autre. » |
| Aucun résultat | « Aucun joueur trouvé. » ; en « Tous les clubs » : « Aucun joueur trouvé. Seules les cartes publiées sont visibles. » |
| Erreur | Modèle standard + « Réessayer » |

**360 px** : modale plein écran ; les cartes `sm` défilent horizontalement dans leur bande (défilement par glissement, aimanté carte par carte) ; tableau avec première colonne figée et défilement horizontal dans son cadre (3.3) ; radar à pleine largeur (320 px) sous le tableau, légende en dessous. **≥ 1024 px** : cartes alignées en haut, puis tableau (7/12) et radar (5/12) côte à côte.

### B3.1 Accès (finalisation 29/09) — renvoi au point ouvert 7, non tranché

La matrice 2.4 n'a pas de ligne « comparaison » ; le CDC 4.2 ne dit pas qui l'ouvre. Rien n'est tranché ici. Ce que l'écran garantit quel que soit le choix du client :
- en « Mon club », les données viennent de l'API club (membre actif, isolation par club) ;
- en « Tous les clubs », elles viennent **uniquement** de la vue publique (6.3) : seuls les champs publics (carte et statistiques sportives, 4.2) ; jamais poids, taille, téléphone, finances, santé ;
- le bouton « Comparer » n'est affiché que si l'API renvoie le droit correspondant (`can_compare`) ; l'interface ne le déduit d'aucun rôle.

### B3.2 Recherche des joueurs : précisions (finalisation 29/09)

- `PlayerSearch` multiple **sans `StatusBadge`** dans les suggestions (propriété `hideStatus`) : la comparaison n'a pas à dire qu'un coéquipier est « En attente », « Suspendu » ou « Inapte » (10.2 n° 16). `renderMeta` affiche seulement « n° {numéro} · {poste} » et, en « Tous les clubs », le logo 16 px et le nom du club.
- Aucun joueur n'est grisé pour cause de dette, suspension ou aptitude : ces blocages concernent la composition et le plan tactique (CLAUDE.md règle 5), pas la consultation de statistiques.
- Changer de portée (« Mon club » ↔ « Tous les clubs ») **conserve** les joueurs déjà choisis ; seule la source des suggestions change.
- Un joueur ne peut être choisi deux fois : il reste visible dans les suggestions, grisé, avec « Déjà choisi ».
- Le joueur de départ (ouverture depuis sa fiche) est une puce comme les autres, retirable.

### B3.3 Radar : précisions (finalisation 29/09)

- **Axes** : liste servie par l'API (libellés en toutes lettres, jamais abrégés), dans l'ordre renvoyé. L'interface ne code aucune liste d'axes (point ouvert 12). Échelle 0 à 10, 5 cercles concentriques de repère (`--color-border`), libellés d'axes 13 px `--color-text-muted` placés hors du polygone, retour à la ligne autorisé.
- Si l'API renvoie **moins de 3 axes**, le radar n'est pas dessiné (un polygone à 2 axes n'a pas de sens) : message « Pas assez d'attributs pour tracer le radar. »
- **Joueur sans attribut** (aucune évaluation) : pas de polygone ; la légende affiche « {nom} — pas encore de donnée » (tracé de légende barré). Si aucun joueur n'a d'attribut : `EmptyState` « Aucun attribut à comparer pour ces joueurs. » à la place du radar ; le tableau reste affiché.
- **Joueur d'un autre club** dont l'API ne sert pas d'attributs publics (point ouvert 13) : même rendu que « pas encore de donnée », avec la légende « {nom} — attributs non publics ».
- Tokens de série à ajouter dans `tokens.css` (distincts des couleurs de statut 2.5 et des couleurs de club ; valeurs à contrôler avec `color-contrast.ts`, exigence ≥ 3:1 sur `--color-surface`, élément graphique) :

| Token | Clair et Classic | Sombre | Tracé |
| --- | --- | --- | --- |
| `--color-series-1` | `#1D4ED8` (bleu) | `#60A5FA` | Plein |
| `--color-series-2` | `#0F766E` (bleu-vert) | `#2DD4BF` | Tirets |
| `--color-series-3` | `#BE185D` (framboise) | `#F472B6` | Pointillés |
| `--color-series-4` | `#854D0E` (brun) | `#FACC15` | Tirets-points |

  Remplissage de chaque polygone à 12 % d'opacité, trait de 2 px ; points de sommet 6 px (formes différentes par série : rond, carré, triangle, losange) pour que la lecture ne dépende ni de la couleur ni du tracé seul. Le même numéro de série colore la bordure supérieure de la carte `sm` du joueur et l'en-tête de sa colonne dans le tableau (liseré de 3 px), pour relier les trois vues.
- **Alternative textuelle** : le radar est un `<figure>` avec `<figcaption>` « Radar des attributs » ; ses valeurs sont déjà dans le tableau. Proposition : ajouter dans le tableau une ligne par attribut du radar (« {attribut} : {valeur} sur 10 »), ce qui rend le radar entièrement redondant pour un lecteur d'écran.

### B3.4 Tableau : précisions (finalisation 29/09)

- Chaque colonne de joueur a pour en-tête : avatar 24 px, « {Prénom} {Nom} » (2 lignes max., pas de troncature), liseré de série.
- Largeur des colonnes de joueur : 112 px min. ; à 360 px avec 4 joueurs, le tableau défile dans son cadre (120 + 4 × 112 = 568 px), première colonne figée, ombre de bord (DataTable §3.3).
- « — » (pas encore de donnée) n'entre jamais en compétition pour « (meilleur) ». En cas d'égalité, toutes les valeurs égales sont en gras.
- Joueurs de clubs différents : la ligne « Saison » montre la saison de chaque club (les saisons peuvent ne pas coïncider) ; aucune conversion.

### B3.5 États complémentaires (finalisation 29/09)

| Cas | Affichage |
| --- | --- |
| Un joueur choisi a quitté le club ou retiré son consentement pendant la consultation | Sa colonne affiche « Ce joueur n'est plus consultable. » et sa puce reste retirable ; les autres colonnes sont conservées |
| Hors connexion | Données déjà chargées lisibles ; recherche désactivée avec « Cette action nécessite une connexion. » |
| Joueur de départ introuvable (404) à l'ouverture depuis la fiche | Comparaison ouverte vide, toast « Cet élément n'existe plus. » |

Textes ajoutés : « Déjà choisi », « Pas assez d'attributs pour tracer le radar. », « {nom} — pas encore de donnée », « {nom} — attributs non publics », « Aucun attribut à comparer pour ces joueurs. », « Radar des attributs », « {attribut} : {valeur} sur 10 », « Ce joueur n'est plus consultable. », « Note globale : pas encore de donnée ».

## B4. Textes exacts (partie B)

« Note globale », « Matchs », « Buts », « Passes décisives », « Cartons », « {j} jaunes, {r} rouge(s) », « Taux de présence », « Note moyenne », « sur 10 », « Saison {saison} », « Pas encore de donnée », « Voir la fiche détaillée de {prénom} {nom} », « Comparer », « Comparer des joueurs », « Ajouter un joueur à comparer », « Mon club », « Tous les clubs », « Retirer {nom} », « Choisissez au moins 2 joueurs à comparer. », « 4 joueurs au maximum. Retirez-en un pour en ajouter un autre. », « Aucun joueur trouvé. », « Aucun joueur trouvé. Seules les cartes publiées sont visibles. », « Club », « Poste ».

---

## 7. Décisions par défaut et points ouverts

1. **Effet 3D sur mobile** (proposition, à valider par le client) : relief statique et animation d'ouverture unique, sans inclinaison au doigt ni au gyroscope (motifs en A5.2). Si le client tient à la parallaxe au mouvement du téléphone, elle ne pourrait être qu'**optionnelle** et activée par l'utilisateur (sur iPhone, une autorisation système est obligatoire). Elle est alors à traiter comme une demande nouvelle (circuit 9.4).
2. **Carte et thème** (proposition) : la carte suit le thème de l'utilisateur. Couleurs du club en Classic, carte neutre bleue en Clair et en Sombre (CDC 3.6 : Clair et Sombre sont des versions neutres). Si le client veut la carte toujours aux couleurs du club, quel que soit le thème, il faut une décision explicite, car ce serait la seule exception à cette règle.
3. **10.2 n° 16 et statut sur la fiche (écart possible, à vérifier par `backend-dev` et `security-auditor`)** : `PlayerCardView` renvoie `membership_status` / `membership_status_label` à **tout** membre du club. Pour un joueur « En attente », un simple coéquipier voit donc « En attente », alors que le 10.2 n° 16 (déjà appliqué par `PlayerListView` au filtre) veut que les coéquipiers ne voient que « Indisponible », sans motif. Position provisoire, la plus prudente : l'interface affiche le libellé tel que l'API le sert, et c'est l'API qui doit servir « Indisponible » (badge gris `neutral`) aux rôles non autorisés. À confirmer. Même logique au Lot 3 pour Suspendu et Inapte, s'ils apparaissent sur la fiche.
4. **Note globale : règle de calcul non définie par le CDC** (4.2 la cite sans formule ; 4.10 définit une « note globale sur 10 » par évaluation, ce qui correspond à la « note moyenne » de la carte). Aucune proposition par défaut n'existe dans le 10.2. Options à soumettre au client : (a) moyenne des attributs du radar, ramenée sur 100 (proche du FIFA) ; (b) note moyenne × 10. Préférence du designer : (a), car elle ne double pas l'indicateur « Note moyenne ». **À trancher avant le Lot 4.**
5. **Période des indicateurs** (non précisée par le CDC) : proposition, saison en cours sur la carte ; cumul de carrière dans la fiche détaillée (onglet « Statistiques », 4.2 « par saison et en cumul »). À valider.
6. **Lot des évaluations** : le CDC 9.1 range les évaluations au **Lot 3** (pas au Lot 4) ; seules les cartes et la comparaison sont au Lot 4. Cela ne change pas la partie A. Au Lot 4, les données seront donc déjà disponibles.
7. **Points d'entrée de la comparaison** (B3) : le CDC ne les fixe pas. Ce sont des propositions.
8. **Libellé de la modale depuis « Mon profil »** : « Ma carte de joueur » (spec `comptes-mon-profil.md` §4.4), alors que le code affiche « Fiche du joueur ». À aligner en partie A.
9. **Poids des photos** (réseau faible) : la carte affiche la photo à 152 px, mais l'API sert l'original compressé côté navigateur (6.7). Une vignette de 320 px servie par l'API réduirait le temps d'ouverture de la fiche. C'est une amélioration à décider (`backend-dev`) ; elle ne bloque pas la partie A.
10. **Consentement de publication** : sans effet sur la partie A (carte vue seulement par les membres connectés du club). Il est bloquant pour la partie B « Tous les clubs » et pour le fil public. La portée globale ou par club de ce consentement reste ouverte (`docs/lot0/schema-donnees.md` Q4).
11. **Remarque client** : elle est consignée dans `inscriptions.md` (l. 5), pas dans `remarques.md`. À cocher quand la partie A sera livrée et validée sur smartphone réel (3.7).
12. **Axes du radar** (finalisation 29/09) : le CDC donne deux listes différentes. 4.2 : « par exemple technique, physique, mental, discipline, assiduité, contribution offensive » ; 4.10 (critères d'évaluation, 10.2 n° 9) : « technique, physique, tactique, mental, attitude ». Les axes « discipline », « assiduité », « contribution offensive » seraient calculés à partir des statistiques (4.2 « à partir des évaluations et des statistiques »), sans formule définie. Non tranché : l'écran affiche les axes servis par l'API. **À trancher avec le point 4** (même nature : règle de calcul).
13. **Attributs du radar en « Tous les clubs »** (finalisation 29/09) : 4.2 rend publiques « la carte et les statistiques sportives » et permet la comparaison entre clubs « sur les données publiques », mais ne dit pas si les attributs issus des **évaluations** (4.10, notes données par le Coach, le Président, le VP) sont publics. Position provisoire la plus prudente : l'API ne sert les attributs d'un joueur d'un autre club que si le client le confirme ; en attendant, « attributs non publics » (B3.3). La « note moyenne » figure sur la carte (4.2) et reste affichée. À trancher.
14. **Consentement de publication et comparaison « Tous les clubs »** (rappel du point 10, finalisation 29/09) : sans décision sur la portée du consentement (`schema-donnees.md` Q4), la vue publique doit exclure tout joueur sans consentement enregistré et tout mineur (7.5). Condition bloquante pour la portée « Tous les clubs », pas pour « Mon club ».
