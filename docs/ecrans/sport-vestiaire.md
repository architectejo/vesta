# Écran — Vestiaire (onglets « Aujourd'hui » et « Plans »)

Sources : CDC 3 (charte), 2.1, 2.4 (précision : « Le Joueur voit en lecture seule […] le vestiaire »), 4.7 (« Vestiaire du jour »), 4.8 (pointage des matchs, composition publiée), 4.12 (confidentialité), 6.5, 6.6, 10.2 n° 16, 25, 29 et 38, CLAUDE.md §2.5 et §2.11. Composants : `PitchBoard` (mode `readonly`), `StatusBadge`, `Avatar`, `SegmentedControl`, `EmptyState`, `Loader`, `docs/lot0/design-system.md` §3.8. Écrans liés : `sport-seance.md` (source du pointage et des équipes), `sport-feuille-de-match.md`, `club-accueil.md` §3 point 2 (carte « Vestiaire du jour »).

*Révision du 16/11/2026* : la page porte deux onglets, « Aujourd'hui » (vestiaire du jour) et « Plans » (bibliothèque des plans tactiques, `remarques.md` l. 95) ; l'entrée « Plan tactique » de la barre latérale est supprimée (§10). Le texte décrit aussi la vue « Terrain » modifiable (CDC 4.7, 10.2 n° 40).

*Révision du 15/11/2026* : ajout du §9 « Photos des joueurs sur les terrains et les bancs » (demande du client, `remarques.md` l. 92, décidée le 15/11/2026). Rappel : depuis le 01/10/2026 (CDC 4.7, 10.2 n° 40), la vue « Terrain » est modifiable par le Coach, l'Assistant, le Capitaine et le Président (formation, placement, échange, passage d'un banc à l'autre) ; les mentions « consultation pure » et « aucun glisser-déposer » ci-dessous ne valent plus que pour les autres rôles.

## 1. Objectif

Répondre en un coup d'œil, le dimanche matin, à trois questions : qui est là, dans quelle équipe je joue, et qui manque encore. L'onglet « Aujourd'hui » se remplit tout seul à partir du pointage (4.7) : personne n'y saisit de présence. Seul le **placement sur le terrain** (formation, positions, équipe A/B) est modifiable, par les rôles du §2. L'onglet « Plans » regroupe les plans tactiques du club (§10).

## 2. Accès

Route `/vestiaire`. Entrée de barre latérale « Vestiaire du jour » (menu Sport), visible par tous (design-system 3.9). L'onglet actif est mémorisé dans l'adresse : `/vestiaire?onglet=plans` (sans paramètre, c'est « Aujourd'hui »). L'ancienne route `/plans` renvoie vers `/vestiaire?onglet=plans`, en conservant `?plan=ID`. Depuis l'accueil, on y arrive par le lien « Ouvrir le vestiaire » (`club-accueil.md`).

| Rôle | Accès |
| --- | --- |
| Tous les joueurs du club, bureau et staff compris (2.1) | Lecture seule (4.7 : « visible par tous les joueurs du club ») |
| Coach, Assistant, Capitaine, Président | Lecture, raccourci « Ouvrir le pointage » vers la page Séance ou la page du match (« É » sur le pointage, matrice 2.4), et **édition du terrain** de la séance du jour (formation, placement, échange, passage d'un banc à l'autre ; 10.2 n° 40), tant que la séance n'est pas verrouillée. |
| Superuser | Pas d'entrée : il n'est pas joueur (2.1). En Ghost Mode, il voit la page comme un joueur du club. |

La page affiche **l'événement du jour**, selon la date dans le fuseau du club. À minuit, elle bascule sur le jour suivant. L'historique se consulte depuis les pages Séances et Matchs, pas ici.

## 3. Structure de la page

**Onglets** : tout en haut, un `SegmentedControl` « Aujourd'hui » / « Plans », affiché **dans tous les cas**, y compris les jours sans événement (les plans restent accessibles).

**En-tête** (onglet « Aujourd'hui ») : titre « Vestiaire du jour » ; contexte « {nom du club} · {dimanche 27 septembre} ». Pas d'action principale. Action secondaire, pour le Coach, l'Assistant, le Capitaine et le Président pendant la journée : « Ouvrir le pointage ». Indicateur « Mis à jour à {08:12} » en 13 px muted, à droite du contexte (sous le contexte sur mobile).

**Choix de l'événement** : s'il y a une séance **et** un match le même jour, un `SegmentedControl` apparaît sous l'en-tête : « Séance · {07:30} » / « Match · {15:00} ». Par défaut, il sélectionne l'événement en cours ou le prochain. S'il n'y a qu'un événement, aucun sélecteur.

Sections en cartes :

1. **Rendez-vous** — une ligne :
   - séance : « Séance · rassemblement {07:30} · limite {08:00} · {terrain} » ;
   - match : « Match contre {adversaire} · {15:00} · {lieu} ».
   - Si le terrain ou le lieu n'est pas renseigné, le segment est omis.
   - À droite, un `StatusBadge` « Ouverte » (vert).
   - En dessous, les compteurs en une ligne : « {n} présents » (vert), « {m} en retard » (rouge si le club compte le retard comme une absence, orange sinon, texte venu de l'API, 10.2 n° 25).
   - Pour une séance, un lien « Voir les consignes » ouvre la modale « Consignes » (taille `sm`, lecture, pied « Fermer »), si des consignes existent.
2. **Ma situation** — pour le joueur connecté, une ligne avec son avatar de 40 px et l'un des textes suivants :
   - « Vous êtes pointé présent à {07:42} · Équipe {A} » (badge vert « Présent », pastille de la couleur de maillot) ;
   - « Vous êtes arrivé à {08:14}, après l'heure limite : vous êtes compté absent. Le Coach ou le Capitaine peut vous placer dans une équipe. » (badge « En retard · compté absent ») ;
   - si le retardataire a déjà été placé : « Vous êtes arrivé à {08:14}, après l'heure limite · Équipe {B} » ;
   - « Vous n'êtes pas encore pointé. Présentez-vous au Coach ou au Capitaine à votre arrivée. » ;
   - « Absence excusée · {motif} » (badge gris) ;
   - **si le joueur ne peut pas être placé**, la ligne donne **son propre** motif, puisqu'il s'agit de ses données (matrice 2.4, P) :
     - « Vous êtes pointé, mais vous ne pouvez pas jouer aujourd'hui : en dette de {montant}. Régularisez auprès du Trésorier pour être placé. » ;
     - « … : suspendu, encore {n} match(s). » ;
     - « … : inapte, retour prévu le {date}. » ;
     - « … : adhésion en attente de finalisation. »
     - Aucun lien de paiement n'est écrit en dur. Le paiement en ligne est hors du MVP (Lot 6).
   - Match avec composition publiée : une ligne de plus, « Vous êtes convoqué : titulaire » / « remplaçant » / « Vous n'êtes pas convoqué pour ce match. ».
3. **Équipes** (séance, ou match si la répartition A/B existe, voir `sport-feuille-de-match.md` §7) :
   - Bascule « Liste » / « Terrain » en haut de la carte (`SegmentedControl`, 36 px), avec « Liste » par défaut sous 768 px et « Terrain » à partir de 768 px (proposition, §7). Le choix est mémorisé sur l'appareil.
   - **Vue « Liste »** : deux colonnes côte à côte, même à 360 px. Chacune a pour titre « Équipe A · {couleur} · {n} » avec la pastille de maillot. Les lignes de 44 px contiennent l'avatar de 32 px, le numéro en tabular-nums et « Prénom N. ». Elles sont triées par ordre d'arrivée. Le joueur connecté est mis en avant (fond `--color-surface-muted` et mention « Vous »).
   - **Vue « Terrain »** : deux terrains aux couleurs des maillots (empilés sous 768 px, côte à côte au-delà). Un toucher sur un pion ouvre une info-bulle avec le nom complet, le numéro et le poste. Pour les joueurs, c'est une consultation pure (`PitchBoard` en mode `readonly`).
   - **Édition (Coach, Assistant, Capitaine, Président)** : choix de la formation de chaque équipe, placement d'un joueur du banc sur le terrain, échange de deux joueurs, passage d'une équipe à l'autre (« Passer en B »). Les joueurs non jouables (dette, suspension, inaptitude, attente d'adhésion) ne peuvent jamais être placés (CLAUDE.md §2.5) ; l'API refuse et la page affiche sa raison.
4. **Présents sans équipe** — les joueurs pointés (présents ou en retard) qui ne sont dans aucune équipe, c'est-à-dire la zone « Non répartis » de `sport-seance.md` §3.2. Deux groupes, dans cet ordre :
   - « En attente de placement ({n}) » : les retardataires non encore placés, avec le badge « En retard » (10.2 n° 38) ;
   - « Ne jouent pas aujourd'hui ({n}) » : les joueurs en dette, suspendus, inaptes ou en attente d'adhésion (10.2 n° 29). **Pour tous les rôles**, ils n'ont que le badge gris « Indisponible », sans motif, conformément au 10.2 n° 16. Le vestiaire est une vue commune à tout le club : le motif est consulté sur la page Séance par les rôles qui y ont droit (`sport-seance.md` §3.2 ter). Seule exception, le joueur concerné voit son propre motif, dans « Ma situation » seulement.
   - Ligne de 44 px : avatar de 32 px, « Prénom N. », badge. Aucune action.
5. **Pas encore pointés** — **visible seulement par le Coach, le Capitaine et le Président**, c'est-à-dire les rôles qui pointent. Pour les autres, la carte n'est pas affichée (proposition, §7). La carte affiche un compteur, « {n} joueurs pas encore pointés », et une liste repliée par défaut (bouton « Afficher »). Chaque ligne contient l'avatar, le nom et le numéro. Un clic sur une ligne ouvre la page Séance, filtre « Non pointés ». Cette carte n'apparaît que pendant la journée de l'événement.

Footer.

## 4. Modales

Onglet « Aujourd'hui » : « Consignes » (taille `sm`, panneau bas sur mobile, texte en 16 px, pied « Fermer ») et la fiche du joueur. Onglet « Plans » : les modales du §10. L'édition du terrain se fait directement sur le terrain, sans formulaire.

## 5. Mise à jour et réseau

- Tant que l'onglet est actif, la page se met à jour **toutes les 30 s par interrogation**, sans WebSocket (6.5), et l'interrogation est suspendue quand l'onglet est inactif. L'indicateur « Mis à jour à {heure} » change à chaque rafraîchissement. Un joueur qui vient d'être pointé ou déplacé apparaît avec un léger surlignage pendant 2 s, coupé si `prefers-reduced-motion` est actif.
- Hors connexion, la dernière version reçue reste affichée avec le bandeau `info` : « Vous êtes hors connexion. Vestiaire du {heure} : il sera mis à jour au retour du réseau. »
- Sur le téléphone qui pointe (Coach ou Capitaine), les pointages hors connexion en attente ne sont **pas** mêlés au vestiaire : celui-ci ne montre que l'état confirmé par le serveur. La page Séance reste la seule vue qui montre l'état local.

## 6. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Barre de progression, puis squelettes : en-tête, 1 ligne « Rendez-vous », 1 ligne « Ma situation », 2 colonnes de 5 lignes | — | « Impossible de charger le vestiaire. » + « Réessayer » ; hors connexion, dernière version en cache (§5) |
| Aucun événement aujourd'hui | — | Les onglets restent affichés ; `EmptyState` : « Aucune séance ni aucun match aujourd'hui. », avec la précision « Prochain rendez-vous : {Séance · dimanche 4 octobre · 07:30} » si l'API en renvoie un (sinon, précision omise). Action pour le Coach : « Créer une séance », qui ouvre la modale de `sport-espace-coach.md` §4.1. Pour les autres rôles, message seul. | — |
| Événement du jour, personne n'est pointé | — | Carte « Équipes » : « Personne n'est encore pointé. Les équipes apparaîtront au fil des arrivées. » | — |
| Pointés, mais aucune équipe formée (tous non répartis) | — | Carte « Équipes » : « Aucune équipe n'est encore formée. » | — |
| Une équipe vide | — | Dans la colonne : « Aucun joueur pour l'instant. » | — |
| « Présents sans équipe » | — | Carte masquée | — |
| « Pas encore pointés » | — | « Tout le monde est pointé. » | — |
| Match sans répartition A/B | — | La carte « Équipes » devient « Présents ({n}) » : une seule liste, avec la mention « Titulaire » ou « Remplaçant » (texte 13 px, pas un badge) si la composition est publiée | — |
| Match reporté ou supprimé dans la journée | — | Retour à l'état « Aucun événement aujourd'hui » au rafraîchissement suivant | — |
| Rafraîchissement en échec (en ligne) | — | — | Aucun toast toutes les 30 s. L'indicateur devient « Mise à jour impossible · {heure} » (orange), suivi du lien « Réessayer ». |

## 7. Mobile (360 px) et ordinateur

- **360 px** : ordre du §3. La carte « Ma situation » vient juste après « Rendez-vous », parce que c'est ce que le joueur cherche en premier.
  - Vue « Liste » en deux colonnes de 162 px (360 − 2 × 12 de marge − 12 d'écart, divisé par 2), avec l'avatar de 32 px et le numéro. Les noms se limitent à « Prénom N. », sur deux lignes au plus, sans troncature.
  - La page tient sans défilement horizontal.
- **Paysage mobile / ≥ 768 px** : « Terrain » par défaut, avec les deux terrains côte à côte.
- **≥ 1024 px** : deux colonnes 8/4. En principal : Rendez-vous, Équipes. En latéral : Ma situation, Présents sans équipe, Pas encore pointés.
- **Plein soleil** : les couleurs de maillot ne portent jamais seules l'information. Le titre de colonne écrit toujours « Équipe A » ou « Équipe B », en plus de la pastille (design-system 2.7).

## 8. Décisions appliquées et points ouverts

**Décisions appliquées :**

- **4.7** : la page affiche automatiquement les joueurs pointés du jour avec leur équipe, et elle est visible par tous. La mise en avant sur l'accueil du Président est traitée par `club-accueil.md`.
- **10.2 n° 16 (décidé)** : sur le vestiaire, vue commune à tout le club, un joueur qui ne peut pas jouer apparaît « Indisponible », sans motif, **quel que soit le rôle** de la personne qui consulte. Le motif ne figure que sur la page Séance, pour les rôles qui y ont droit, et dans « Ma situation » pour le joueur lui-même.
- **10.2 n° 25 (décidé)** : le texte « compté absent » et la couleur du compteur de retards viennent du réglage du club, transmis par l'API.
- **10.2 n° 29 et n° 38 (décidés)** : les deux catégories de la zone « Non répartis » sont reprises en lecture seule : « En attente de placement » (retardataires, que le Coach ou le Capitaine peuvent placer) et « Ne jouent pas aujourd'hui » (jamais placeables). Le vestiaire n'offre aucune action de placement, ni légitime ni de contournement.
- **CLAUDE.md §2.11** : aucune information médicale sur cette page, sinon la date de retour prévue du joueur, montrée à lui seul, dans « Ma situation ».

**Points ouverts et propositions (à valider par le client) :**

1. **Retardataires dans le vestiaire** : le 4.7 parle des « joueurs pointés présents ». Un retardataire est pointé, mais compté absent par défaut. Proposition : il figure dans le vestiaire, dans son équipe s'il a été placé, sinon dans « En attente de placement », parce qu'il est physiquement là et peut jouer (10.2 n° 6 et n° 38).
2. **Carte « Pas encore pointés »** : elle n'est pas demandée par le 4.7. Proposition : la réserver au Coach, au Capitaine et au Président, parce qu'elle aide au pointage, et ne pas la montrer aux joueurs, pour ne pas exposer les absents à tout le club. Si le client la refuse, elle est retirée sans autre impact.
3. **Vue « Liste » par défaut sous 768 px** : proposition de densité, parce que deux terrains empilés demandent beaucoup de défilement à 360 px. La vue « Terrain » reste à un toucher.
4. **Événement du jour sans A/B pour un match** : cette question dépend du point ouvert 2 de `sport-feuille-de-match.md` §7 (le schéma ne rattache la répartition qu'aux séances).
5. **Plusieurs séances le même jour** : le CDC ne l'exclut pas. Le sélecteur « Choix de l'événement » accepte donc plus de deux entrées ; au-delà de trois, il est remplacé par des puces défilantes.

## 9. Photos des joueurs sur les terrains et les bancs (révision du 15/11/2026)

> **NOUVEAU (circuit 9.4, à valider)** : le CDC 3.4 dit déjà « la photo du joueur est affichée partout où son nom apparaît ; à défaut, ses initiales ». Les pions du terrain affichent aujourd'hui seulement le numéro sur la couleur du maillot. La demande applique donc la règle 3.4 aux pions ; seul le **dessin du pion** est nouveau.

### 9.1 Portée

- Vestiaire du jour, vue « Terrain » : terrains A et B, bancs A et B, sous-zones « En attente de placement » et « Ne jouent pas aujourd'hui ».
- **Même composant partout** : `PitchPin` du design system (`frontend/src/design-system/components/PitchBoard.tsx`). La page Séance (`sport-seance.md` §3.2) et le plan tactique (`sport-plan-tactique.md`) en profitent automatiquement ; c'est voulu (cohérence, 3.1).
- La vue « Liste » a déjà l'avatar de 32 px : inchangée.
- Tous les rôles voient les photos (lecture seule ou édition selon le 10.2 n° 40).

### 9.2 Dessin du pion

Le **pied du pion ne change pas** : cercle de 40 × 40 px, centré sur sa coordonnée (`-translate-x-1/2 -translate-y-1/2`), étiquette du nom en dessous. Les formations, les cases et les échanges (10.2 n° 39) gardent donc exactement leur géométrie.

| État | Cercle de 40 px | Pastille (18 px, en bas à droite, chevauche le cercle de 6 px) | Bordure |
| --- | --- | --- | --- |
| Avec photo | Photo `object-fit: cover`, recadrée sur le visage (centre haut : `object-position: 50% 25%`) | Numéro de maillot, 11 px gras, chiffres tabulaires, fond = couleur du maillot, texte blanc ou noir choisi par `color-contrast.ts` (≥ 4,5:1) | 3 px couleur du maillot + liseré extérieur blanc 1 px (le pion se détache de la pelouse) |
| Sans photo, ou image en échec | Initiales (« PN »), 13 px semi-gras, sur la couleur du maillot, texte blanc ou noir par `color-contrast.ts` | Numéro, comme ci-dessus | Idem |
| Sans numéro | Inchangé | Pastille absente | Idem |
| Bloqué (« Ne jouent pas aujourd'hui », 10.2 n° 29) | Photo en niveaux de gris à 60 % d'opacité (ou initiales sur fond `bg-black/30`) | **Cadenas** à la place du numéro (fond `--color-status-neutral-dot`) | Tirets blancs à 60 % (comme aujourd'hui) |
| « Vous » (joueur connecté) ou pion armé pour un placement | Inchangé | Inchangé | 3 px `--color-primary` + liseré blanc 1 px |

- **Étiquette du nom** sous le pion : « Prénom N. » sur fond `bg-black/50`, texte blanc ; **12 px** (au lieu de 11 px, plus lisible en plein soleil), 2 lignes au plus, sans ellipse (CDC 4.2 « aucun libellé tronqué » ; aujourd'hui l'étiquette est tronquée à 64 px). Largeur max. 72 px.
- Le cadenas et le gris ne disent **rien du motif** (10.2 n° 16) : identiques pour la dette, la suspension, l'inaptitude et l'attente d'adhésion.
- Aucune information ne repose sur la seule couleur : la photo ou les initiales identifient le joueur, le numéro est écrit, l'équipe est écrite dans le titre de chaque terrain (« Équipe A ») — §7 « Plein soleil ».

### 9.3 Lisibilité à 360 px

- Terrain portrait de 336 px de large (360 − 2 × 12), soit environ 519 px de haut. Une ligne de 5 joueurs (4-5-1) laisse 67 px entre deux centres : un pion de 40 px + pastille et une étiquette de 72 px au plus tiennent sans se chevaucher ; deux lignes de joueurs sont espacées d'au moins 90 px, assez pour un pion et une étiquette de 2 lignes (≈ 70 px).
- Zone tactile de 44 × 44 px autour du cercle (marge invisible de 2 px), comme exigé par 3.1.
- Sur ordinateur, la largeur du terrain est plafonnée par `useTeamsPitchWidthStyle` (environ 336 px sur un écran de 900 px de haut) : même taille de pion qu'en mobile, pas de changement.
- Bancs et sous-zones : grille de 4 colonnes à 360 px (inchangée), même pion en mode `standalone`.

### 9.4 Glisser-déposer : ce qui ne doit pas casser (exigences pour `frontend-dev`)

1. L'image est **décorative** dans un bouton qui porte déjà `aria-label` : `alt=""`.
2. L'image ne doit jamais capter le geste : `draggable={false}`, `pointer-events: none`, `-webkit-user-drag: none`, `user-select: none` ; sur le pion, `-webkit-touch-callout: none`. Sans cela, sur iPhone, l'appui long ouvre le menu « Enregistrer l'image » au lieu de soulever le pion, et sur ordinateur le navigateur lance son propre glisser d'image, qui court-circuite `pitchDragBus`.
3. Le chargement de l'image ne doit pas changer la taille du pion (taille fixe, fond de couleur du maillot pendant le chargement), sinon les coordonnées de dépose glissent.
4. Échec de chargement (`onError`) : bascule une seule fois sur les initiales, sans nouvelle tentative en boucle.
5. Fantôme de glissement (`PitchDragGhost`) : proposition, ajouter l'avatar de 24 px à gauche du nom (`PitchDragItem` reçoit `photoUrl` facultatif). Le fantôme reste `pointer-events: none`.
6. Pions bloqués : toujours impossibles à soulever (`sport-seance.md` §3.2 bis) ; la photo n'y change rien.

### 9.5 Données et réseau

- La photo est déjà servie en **URL absolue** par l'API (`serialize_membership_brief` → champ `photo`, `request.build_absolute_uri`), et l'écran l'utilise déjà pour les avatars de la vue « Liste » (`VestiairePage.tsx`). Il manque seulement le passage de `item.player.photo` dans les pions : `TeamFieldPanel.tsx` l. 159-167 (terrain) et l. 330-339 (banc), plus les pions des sous-zones. `PitchPinData` reçoit un champ facultatif `photoUrl` (et `initials` calculées par le composant à partir du nom complet, pas de « Prénom N. »).
- À vérifier par `backend-dev` : `photo` présent dans toutes les réponses qui alimentent les pions (`locker-room/`, `sessions/{id}/`, `sessions/{id}/unassigned/`, affectations d'équipe, plan tactique).
- **Poids** : jusqu'à 30 photos chargées d'un coup sur un réseau faible. Proposition (déjà ouverte en `club-carte-joueur.md` point 9) : une vignette carrée de 96 px (`photo_thumb`, 2 × 40 px + marge pour les écrans haute densité) générée à l'envoi de la photo. En attendant, l'original est utilisé avec `decoding="async"` ; les pions sous la ligne de flottaison (bancs) en `loading="lazy"`.
- Hors connexion : les photos déjà en cache s'affichent ; les autres passent aux initiales, sans message d'erreur.
- L'interrogation toutes les 30 s (§5) ne recharge pas les images (même URL : cache du navigateur).

### 9.6 États

| Cas | Affichage |
| --- | --- |
| Photo en cours de chargement | Cercle à la couleur du maillot, sans initiales (évite un clignotement initiales → photo) ; au-delà de 1,5 s, initiales |
| Photo absente | Initiales + numéro |
| Photo en échec | Initiales + numéro, sans message |
| Joueur sans nom complet (cas d'import incomplet) | « ? » + numéro |

### 9.7 Tests à prévoir (`test-engineer`)

- `PitchPin` : avec photo, sans photo, échec de chargement, sans numéro, bloqué, « Vous » ; le pion garde une boîte de 40 × 40 px dans tous les cas.
- Glisser-déposer d'un pion avec photo (pointeur, toucher simulé) : le pion est soulevé et déposé comme sans photo ; `img` a `draggable="false"`.
- Contraste de la pastille de numéro sur les 8 couleurs de maillot de la palette (design-system 2.7).
- Vérification visuelle à 360 px en 4-4-2, 4-5-1 et 3-5-2, thèmes Clair, Sombre et Classic.

### 9.8 Questions pour le client

1. Valider le dessin : photo dans le cercle, numéro dans une pastille, bordure à la couleur du maillot.
2. Valider l'extension à la page Séance et au plan tactique (même composant).
3. Valider la vignette de 96 px côté serveur (réseau faible).

## 10. Onglet « Plans » (révision du 16/11/2026)

Demande du client (`remarques.md` l. 95) : tout ce que faisait la page « Plans tactiques » est repris dans le Vestiaire. Détail des plans, formulaire et tableau noir : `sport-plan-tactique.md`.

- **Contenu** : liste paginée (5 plans puis « Voir plus »), filtres « Tous / Publiés / Brouillons » (Coach et Assistant), ligne = nom, formation, effectif, match rattaché (« Match n° X » tant que l'API ne fournit pas l'adversaire et la date), badge Publié ou Brouillon. Un clic ouvre la modale « Plan » (lecture).
- **Actions réservées au Coach et à l'Assistant** : « Nouveau plan » (modale), « Dupliquer », « Supprimer le plan » (confirmation), « Modifier sur le tableau noir ». Le Capitaine et le Président ont la lecture seule des plans (**position provisoire, à valider par le client**). Les joueurs ne voient que les plans publiés (filtre de l'API).
- **Tableau noir** : reste une **page** `/plans/{id}/tableau` (exception documentée, CDC 10.2 n° 32). Son bouton « Retour aux plans », la suppression d'un plan et la redirection d'un non-Coach renvoient vers `/vestiaire?onglet=plans`.
- **Lien d'une notification « Plan publié »** : `/vestiaire?onglet=plans&plan={id}` ouvre le plan en lecture ; le Coach va directement sur le tableau noir.
- **États** : chargement (squelettes), erreur avec « Réessayer », vide (« Aucun plan tactique pour l'instant. » pour le Coach, avec « Nouveau plan » ; « Aucun plan publié pour l'instant. » pour les autres).
- Cet onglet n'est pas rafraîchi toutes les 30 s (le polling ne concerne que l'onglet « Aujourd'hui »).
