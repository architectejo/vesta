# Écran — Plan tactique et tableau noir

Sources : CDC 3 (charte), 4.8 (plan rattaché à un match), 4.11, 4.17 (« Composition ou plan publié »), 6.5, 6.6, 9.2 (critère du Lot 3 : « un joueur en dette ne peut être ni composé ni placé dans un plan »), 10.2 n° 16, 31 et 32, CLAUDE.md §2.5, matrice 2.4 (« Plan tactique », « Numéro de maillot et poste des joueurs »), `docs/lot0/schema-donnees.md` §5.11. Composants : `PitchBoard` (modes `tactic` et `readonly`), `PlayerSearch`, `Modal`, `ConfirmDialog`, `StatusBadge`, `ListSection`, `EmptyState`, `Loader`, `docs/lot0/design-system.md` §2.7 et §3.8. Écrans liés : `sport-espace-coach.md` §3 point 8, `sport-feuille-de-match.md` §3 point 2.

## 1. Objectif

Le Coach prépare son onze sur un terrain : il choisit une formation, place les joueurs disponibles au doigt, puis dessine les déplacements et écrit ses consignes. Il publie ensuite le plan, que les joueurs consultent en lecture seule, sur leur téléphone, avant le match. On ne doit jamais pouvoir y placer un joueur qui n'a pas le droit de jouer.

**Exception à la règle des modales, actée (10.2 n° 32)** : le tableau noir est une **page d'édition**, pas une modale, car il faut toute la surface de l'écran pour dessiner. Tout ce qui reste un formulaire (création, paramètres, numéro et poste, texte d'une consigne, duplication) passe par une modale, conformément au 3.2.

## 2. Accès

Deux routes :

- `/vestiaire?onglet=plans` : liste des plans, onglet « Plans » du Vestiaire, accessible à tous par « Sport › Vestiaire › Plans » (l'ancienne route `/plans` y renvoie, `?plan=ID` conservé ; l'entrée « Plan tactique » de la barre latérale est supprimée, `remarques.md` l. 95) ;
- `/plans/{id}/tableau` : éditeur, réservé au Coach.

| Rôle | Liste et consultation | Édition (tableau noir) | Numéro et poste depuis le plan |
| --- | --- | --- | --- |
| Coach | Tous les plans, brouillons compris | É : créer, placer, dessiner, dupliquer, rattacher, publier, supprimer | É (matrice 2.4) |
| Président, VP, DS, Trésorier, adjoint, Intendant, Capitaine, Médecin, Joueur | Plans **publiés** seulement, en lecture seule (2.4 : « L » ; 4.11 : « lecture seule, sans pouvoir le modifier ni le supprimer ») | — | — |

Un non-Coach qui ouvre directement `/plans/{id}/tableau` est renvoyé vers `/vestiaire?onglet=plans`, où s'ouvre la modale « Plan » en lecture seule, si le plan est publié. Si le plan n'est pas publié, il voit le message standard « Vous n'avez pas accès à cette action. ».

Brouillons réservés au Coach : c'est une **position provisoire** (voir le §8, point ouvert 1).

## 3. Onglet « Plans » du Vestiaire (`/vestiaire?onglet=plans`)

**En-tête** (sous les onglets « Aujourd'hui » / « Plans ») : titre « Plans tactiques » ; contexte « {nom du club} · Saison {saison} ». Action principale (Coach et Assistant) : « Nouveau plan ». Aucune action pour les autres rôles, Capitaine et Président compris (lecture seule, position provisoire à valider par le client). Voir `sport-vestiaire.md` §10.

Sections :

1. **Plans** — une carte. Puces de filtre en haut de la carte, pour le Coach seulement : « Tous » (par défaut), « Publiés », « Brouillons ». La liste affiche les 5 derniers plans modifiés, puis un bouton « Voir plus » (3.3). Chaque ligne de 56 px contient :
   - le nom du plan (14 px/500) ;
   - en dessous, en 13 px muted : « {formation} · {11} joueurs · {Match contre {adversaire} du {date} | Aucun match rattaché} » ;
   - à droite, un `StatusBadge` « Brouillon » (orange) ou « Publié » (vert). Ces couleurs sont celles de la composition (design-system 2.5, proposition).
   - Pour un joueur placé sur un plan publié, la mention « Vous êtes placé » (13 px, `--color-primary-text`) s'ajoute sous la ligne.
   - Un clic sur la ligne ouvre la modale « Plan » (§4.1).
2. Pas d'autre section : la page reste une page de consultation.

Footer.

## 4. Modales

### 4.1 « Plan » (détail, lecture) — taille `lg` (plein écran sur mobile)

Ouverte depuis la liste, depuis le lien « Voir le plan tactique » de la page du match ou depuis la notification « Plan publié » (4.17).

- **En-tête** : titre « {nom du plan} » ; sous-titre « {formation} · {Match contre {adversaire} du {date}} » ; `StatusBadge` « Brouillon » ou « Publié le {date} ».
- **Corps** :
  1. `PitchBoard` en mode `readonly` : le terrain, les pions (numéro et « Prénom N. ») et le calque du tableau noir (flèches, zones, textes). Un toucher sur un pion ouvre une petite fenêtre avec le nom complet, le numéro, le poste et, s'il en a une, la consigne du joueur. Aucun glisser-déposer, aucune barre d'outils.
  2. **« Consignes »** : d'abord les consignes par ligne (« Défense », « Milieu », « Attaque »), puis les consignes par joueur (avatar 24 px, nom, texte). Pour un joueur connecté qui a une consigne, un bloc « Pour vous » apparaît en tête, sur fond `--color-surface-muted`.
  3. **Joueurs devenus indisponibles depuis la publication** : le pion est grisé, avec cadenas. Le Coach voit la raison complète (« En dette : {montant} », « Suspendu : encore {n} match(s) », « Inapte · retour prévu le {date} », « En attente d'adhésion »). Tous les autres rôles voient seulement le badge gris « Indisponible », sans motif (10.2 n° 16).
- **Pied** : « Fermer ». Pour le Coach seulement, action principale « Modifier sur le tableau noir » (vers `/plans/{id}/tableau`). Menu « … » de l'en-tête, pour le Coach : « Dupliquer », « Supprimer le plan ».

### 4.2 « Nouveau plan » — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Nom du plan | TextField | Oui | 120 caractères au plus ; « Ce champ est obligatoire. » |
| Effectif | SegmentedControl : 11 / 8 / 7 | Oui | Défaut : 11 |
| Formation | Liste de choix courte (non-joueurs), selon l'effectif | Oui | À 11 : 4-4-2 (défaut), 4-3-3, 4-2-3-1, 3-5-2, 3-4-3, 5-3-2, 4-1-4-1, 4-5-1 (4.11). À 7 et à 8 : liste du §8, point ouvert 3. Chaque option montre une mini-vignette du placement (48 × 72 px). |
| Match rattaché (facultatif) | Liste de choix des matchs à venir du club (ce ne sont pas des joueurs) : « {adversaire} · {date} » | Non | Option « Aucun match » par défaut |

Aide sous « Formation » : « Vous pourrez déplacer les emplacements ensuite : la formation deviendra « Personnalisée ». » Pied : « Annuler » / « Créer le plan ». En cas de succès, la modale se ferme, l'éditeur `/plans/{id}/tableau` s'ouvre et le toast « Plan créé. » s'affiche. Le plan est en brouillon.

### 4.3 « Paramètres du plan » — taille `md`

Mêmes champs que le §4.2, préremplis. Ouverte depuis le menu « … » de l'éditeur.

Si la formation ou l'effectif change alors que des joueurs sont placés, un bandeau orange apparaît dans le corps : « Les joueurs seront replacés sur les nouveaux emplacements, selon leur poste. Ceux qui n'ont plus de place retourneront sur le banc. Les dessins et les consignes sont conservés. » Pied : « Annuler » / « Enregistrer ». Succès : « Plan mis à jour. »

### 4.4 « Choisir un joueur » — taille `sm` (panneau bas sur mobile)

Ouverte par un toucher sur un emplacement vide (l'alternative au glisser-déposer, obligatoire, design-system 3.8).

- En-tête : « Choisir un joueur » ; sous-titre « Emplacement : {Défenseur central gauche} ».
- Corps : `PlayerSearch` avec la portée club et le contexte d'éligibilité `eligibleFor="plan:{id}"`. Les suggestions montrent d'abord les joueurs du poste de l'emplacement, puis les autres.
  - Les joueurs déjà placés sur ce plan apparaissent avec la mention « Déjà placé ({emplacement}) ». Les choisir les **déplace** vers cet emplacement.
  - Les joueurs **non éligibles** sont visibles mais grisés, non sélectionnables (`aria-disabled`), avec la raison de l'API en 14 px : « En dette : {montant} », « Suspendu : encore {n} match(s) », « Inapte (avis médical) », « En attente d'adhésion ».
- Pied : « Annuler » seul, car la sélection d'une suggestion place immédiatement le joueur. Toast : « {nom} placé en {emplacement}. », avec l'action « Annuler ».

### 4.5 « Modifier le numéro et le poste » (4.11) — taille `sm`

- Sous-titre : « {nom du joueur} ».
- Champs :
  - « Numéro de maillot » : NumberField − / +, valeurs de 1 à 99 ; message « Saisissez un numéro entre 1 et 99. ».
  - « Poste » : liste courte non-joueurs : « Gardien », « Défenseur », « Milieu », « Attaquant » (valeurs de `schema-donnees.md` §5.6).
- Aide : « La fiche du joueur sera mise à jour. » (4.11).
- Pied : « Annuler » / « Enregistrer ». Succès : « Numéro et poste de {nom} mis à jour. »
- Numéro déjà porté par un autre joueur du club : pas de règle dans le CDC. Seul un avertissement **non bloquant** s'affiche sous le champ : « Le numéro {n} est déjà porté par {nom}. » (voir le §8, point ouvert 4).

### 4.6 « Consigne » — taille `sm`

Ouverte par l'outil « Texte » (toucher un point du terrain), par « Ajouter une consigne » dans le panneau « Consignes » ou par « Consigne pour ce joueur » dans le menu d'un pion.

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Pour | SegmentedControl : Tout le monde / Une ligne / Un joueur | Oui | « Tout le monde » par défaut. Depuis l'outil « Texte », l'annotation est posée sur le terrain à l'endroit touché. |
| Ligne | SegmentedControl : Défense / Milieu / Attaque | Si « Une ligne » | « Choisissez une ligne. » |
| Joueur | `PlayerSearch` limité aux joueurs placés sur le plan | Si « Un joueur » | « Choisissez un joueur. » |
| Texte | TextArea | Oui | 300 caractères au plus ; « Ce champ est obligatoire. » |

Pied : « Annuler » / « Enregistrer ». Succès : « Consigne ajoutée. » Le détail d'une consigne existante s'ouvre dans la même modale. Son pied devient « Annuler » / « Enregistrer », et le menu « … » propose « Supprimer la consigne », avec un ConfirmDialog « Supprimer cette consigne ? » et le bouton « Supprimer ».

### 4.7 « Dupliquer le plan » — taille `sm`

- Champs :
  - « Nom de la copie » : prérempli « {nom} (copie) », 120 caractères au plus.
  - « Match rattaché (facultatif) » : même liste que le §4.2.
- Aide : « La copie est un brouillon. Les joueurs qui ne peuvent pas jouer aujourd'hui ne sont pas recopiés. »
- Pied : « Annuler » / « Dupliquer ».
- Succès : « Plan dupliqué. » Si des joueurs n'ont pas été recopiés, le toast devient « Plan dupliqué. {n} joueur(s) indisponible(s) n'ont pas été recopiés. », et leurs emplacements restent vides.
- La copie passe par le même contrôle d'éligibilité que tout placement (`schema-donnees.md` §5.11). Dupliquer un ancien plan ne doit jamais permettre de réintroduire un joueur bloqué.

### 4.8 « Publier le plan » — ConfirmDialog

- Titre : « Publier le plan « {nom} » ? »
- Texte, selon le cas :
  - plan rattaché à un match dont la composition est publiée : « Tous les joueurs du club pourront le consulter en lecture seule, après connexion. Les {n} joueurs convoqués seront prévenus. » ;
  - sinon : « Tous les joueurs du club pourront le consulter en lecture seule, après connexion. Les {n} joueurs placés sur le plan seront prévenus. » (voir le §8, point ouvert 2).
- Bouton : « Publier ». Succès : « Plan publié. »
- **Publication impossible** tant qu'un joueur placé est devenu non éligible. Dans ce cas, le bouton « Publier » de l'éditeur est désactivé et porte l'aide « Remplacez d'abord les joueurs qui ne peuvent plus jouer. » (position provisoire, §8 point ouvert 5).
- La publication se fait uniquement dans Vesta (4.11) : il n'existe ni bouton « Partager » ni lien externe.

### 4.9 « Supprimer le plan » — ConfirmDialog

« Supprimer le plan « {nom} » ? Il ne sera plus visible par les joueurs et ne pourra pas être récupéré. » — bouton « Supprimer » (danger). Succès : « Plan supprimé. » Côté serveur, la suppression est journalisée (CLAUDE.md §2.6).

## 5. Page « Tableau noir » (`/plans/{id}/tableau`, Coach)

### 5.1 Structure

1. **En-tête compact**, une seule ligne de 48 px sur mobile :
   - bouton retour « Plans » (IconButton, `aria-label` « Retour aux plans ») ;
   - titre « {nom du plan} » (18 px, une ligne, points de suspension si trop long) ;
   - indicateur d'enregistrement en 13 px muted : « Enregistré », « Enregistrement… » ou « Non enregistré » (en rouge, avec le lien « Réessayer ») ;
   - action principale « Publier » (bouton `sm`) si le plan est en brouillon. Si le plan est déjà publié, le badge « Publié » remplace le bouton ;
   - menu « … » : « Paramètres du plan », « Dupliquer », « Voir comme un joueur » (ouvre la modale §4.1), « Supprimer le plan ».
   - Ligne de contexte sous l'en-tête, à partir de 640 px seulement : « {nom du club} · {formation} · {Match contre {adversaire} du {date}} ».
2. **Bandeaux** éventuels :
   - `danger` : « {n} joueur(s) placé(s) ne peuvent plus jouer. Remplacez-les avant de publier. » ;
   - `info` : « Vous êtes hors connexion. Le tableau noir est en lecture seule jusqu'au retour du réseau. » ;
   - `readonly` : licence expirée.
3. **Terrain** : `PitchBoard` en mode `tactic`. Il montre les emplacements de la formation (cercles en pointillés de 40 px, avec l'abréviation du poste en 13 px : « G », « DD », « DC », « DG », « MD », « MC », « MG », « AD », « AC », « AG »), les pions placés et le calque du tableau noir.
4. **Banc** : tous les joueurs du club qui ne sont pas encore sur le terrain. Il comprend :
   - un champ de recherche « Nom ou numéro » (36 px) ;
   - les puces de poste « Tous », « Gardiens », « Défenseurs », « Milieux », « Attaquants » ;
   - si un match est rattaché et que sa composition existe, une puce « Composition du match » cochée par défaut. Ce n'est qu'un filtre d'affichage, pas une règle.
   - Ordre : joueurs éligibles d'abord (par poste, puis par nom), joueurs non éligibles ensuite, sous l'intertitre « Ne peuvent pas être placés ({n}) ».
   - Chaque joueur est un pion de 40 px (numéro, « Prénom N. »). Un pion non éligible est grisé, hachuré, avec cadenas, et porte la raison en 13 px sous le nom (§5.3).
5. **Barre d'outils du tableau noir** (design-system 3.8) : « Placer » (mode par défaut, équivalent de « Sélection »), « Flèche », « Zone », « Texte », « Gomme », « Annuler », « Rétablir », puis « Consignes » (compteur). « Consignes » ouvre un panneau latéral sur ordinateur, ou un panneau bas sur mobile, qui liste les consignes par ligne et par joueur, avec l'action « Ajouter une consigne » (§4.6). Chaque bouton fait 40 px avec une zone de 44 px et porte un `aria-label` ; l'outil actif a un fond `--color-primary` et un texte `--color-on-primary`.
6. Footer sous l'éditeur, non collant, à atteindre en défilant.

### 5.2 Interactions (mode « Placer »)

| Geste | Effet |
| --- | --- |
| Glisser un pion du banc vers un emplacement vide | Le joueur est placé. Toast : « {nom} placé en {emplacement}. », action « Annuler ». |
| Glisser un pion du banc vers un emplacement occupé | Échange : le joueur qui occupait l'emplacement retourne sur le banc. Toast : « {nom} remplace {nom2}. », action « Annuler ». |
| Glisser un pion du terrain vers un autre emplacement | Déplacement, ou échange si l'emplacement est occupé. |
| Glisser un pion du terrain vers un endroit libre de la pelouse | L'emplacement se déplace. La formation devient « Personnalisée » (indication dans l'en-tête). Proposition (§8, point ouvert 3). |
| Glisser un pion du terrain vers le banc | Le joueur est retiré du terrain. |
| Toucher un emplacement vide | Modale « Choisir un joueur » (§4.4). |
| Toucher un pion placé | Menu (panneau bas sur mobile) : « Changer de joueur », « Retirer du terrain », « Modifier le numéro et le poste », « Consigne pour ce joueur », « Voir la fiche du joueur ». |
| Toucher un pion du banc éligible | Menu : « Placer sur le terrain » (le mode place devient actif : on touche ensuite l'emplacement choisi), « Modifier le numéro et le poste », « Voir la fiche du joueur ». |
| Clavier | Mêmes règles que le design-system 3.8 : Tab, Espace pour saisir un pion, flèches entre les emplacements, Entrée pour déposer, Échap pour annuler. Le déplacement est annoncé par `aria-live`. |

Sur écran tactile, le glissement démarre après un appui long de 250 ms (design-system 3.8), pour que le banc puisse défiler normalement.

**Enregistrement** : chaque placement, retrait, échange ou tracé est enregistré immédiatement, avec une mise à jour optimiste et un indicateur de 16 px sur l'élément. En cas d'échec, l'élément revient à sa place et le toast « Modification non enregistrée. Réessayez. » s'affiche. Il n'y a pas de bouton « Enregistrer » global, puisque chaque geste est une écriture. Côté serveur, chaque écriture est journalisée (CLAUDE.md §2.6).

### 5.3 Joueurs non éligibles : aucun contournement (CLAUDE.md §2.5, CDC 4.11, critère 9.2 du Lot 3)

La raison est toujours affichée : « En dette : {montant} », « Suspendu : encore {n} match(s) », « Inapte (avis médical) », « En attente d'adhésion ». Le Coach est le seul à éditer, et il voit les raisons complètes du 4.8, sans jamais de diagnostic.

| Chemin | Comportement exigé |
| --- | --- |
| Glisser le pion depuis le banc | Le pion ne se soulève pas, les emplacements ne s'éclairent pas. |
| Toucher le pion | Panneau en lecture seule : « {nom} ne peut pas être placé : {raison} », avec « Voir la fiche du joueur » et « Modifier le numéro et le poste » (qui n'est pas un placement). Il ne propose **pas** « Placer sur le terrain ». |
| Modale « Choisir un joueur » (§4.4) | Suggestion grisée, non sélectionnable. |
| Échange (déposer sur un emplacement occupé) | Impossible : le pion ne peut pas être saisi. |
| « Annuler » d'un retrait (toast), « Rétablir » | Si le joueur est devenu non éligible entre-temps, l'API refuse. Toast : « Impossible : {nom} ne peut plus être placé ({raison}). » L'emplacement reste vide. |
| Changement de formation (§4.3) | Les joueurs non éligibles déjà placés ne sont pas replacés : ils retournent sur le banc. |
| Duplication (§4.7) | Les joueurs non éligibles ne sont pas recopiés. |
| Clavier | Espace sur le pion annonce : « {nom} ne peut pas être placé : {raison}. » |
| Hors connexion | L'éditeur passe en lecture seule (§6). Aucun placement n'est mis en file. |

**Joueur placé devenu non éligible** (après la pose, par exemple une dette constatée le 10 ou une blessure) : le pion reste à sa place, mais il est grisé, avec cadenas et la mention « Ne peut plus jouer : {raison} ». Le bandeau `danger` du §5.1 s'affiche et la publication est bloquée (§4.8). Un toucher ouvre le menu du pion, limité à « Changer de joueur », « Retirer du terrain » et « Voir la fiche du joueur ». Aucun retrait automatique n'a lieu (§8, point ouvert 5).

**Régularisation** : tant que l'éditeur est ouvert, l'éligibilité est relue toutes les 15 s (6.5 : pas de temps réel). Un joueur régularisé se dégrise sur le banc, avec le toast « {nom} peut de nouveau être placé. ».

### 5.4 Outils du tableau noir (4.11 : flèches, zones, annotations, consignes)

- **Flèche** : on appuie, on glisse, on relâche. Le trait est blanc, de 3 px, avec une pointe. Un tracé de moins de 12 px est ignoré, car c'est probablement un toucher involontaire.
- **Zone** : on appuie et on glisse pour dessiner un rectangle aux coins arrondis, rempli de blanc à 20 % avec un contour pointillé.
- **Texte** : un toucher sur le terrain ouvre la modale « Consigne » (§4.6). L'annotation apparaît à cet endroit, en 13 px, sur une étiquette sombre semi-opaque.
- **Gomme** : un toucher sur une flèche, une zone ou une annotation la supprime, sans confirmation puisque « Annuler » la rétablit. Toast « Élément effacé. », action « Annuler ».
- **Annuler / Rétablir** : sur les 20 derniers gestes de la session d'édition.
- En mode dessin, les pions ne se déplacent pas et le défilement de la page est bloqué au-dessus du terrain, pour que le doigt dessine au lieu de faire défiler. En mode « Placer », les dessins ne réagissent pas au toucher.
- Couleurs : les tracés sont blancs sur la pelouse (`--pitch-line`). Aucune couleur de club n'est utilisée : une couleur de club peut se confondre avec un maillot ou avec la pelouse.

## 6. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Liste des plans | 3 lignes squelettes | Coach : « Aucun plan tactique pour l'instant. » + « Nouveau plan ». Autres rôles : « Aucun plan publié pour l'instant. » | « Impossible de charger les plans. » + « Réessayer » |
| Filtre « Brouillons » ou « Publiés » vide | — | « Aucun plan dans ce filtre. » | — |
| Modale « Plan » | Squelette `pitch` + 3 lignes | Aucun joueur placé : « Aucun joueur n'est encore placé sur ce plan. » ; aucune consigne : « Aucune consigne. » | Modèle standard, avec « Réessayer » |
| Plan supprimé ou dépublié (lien de notification périmé) | — | — | « Cet élément n'existe plus. » |
| Éditeur | Squelette : en-tête, `pitch`, bande de banc | — | « Impossible de charger le plan. » + « Réessayer » |
| Banc vide (tous les joueurs placés) | — | « Tous les joueurs disponibles sont sur le terrain. » | — |
| Banc filtré vide | — | « Aucun joueur dans ce filtre. » | — |
| Aucun joueur éligible dans le club | — | Bandeau dans le banc : « Aucun joueur ne peut être placé pour l'instant. » La liste grisée reste visible, avec les raisons. | — |
| Enregistrement d'un geste en échec | — | — | L'élément revient à sa place ; toast « Modification non enregistrée. Réessayez. » ; l'indicateur d'en-tête passe à « Non enregistré » |
| Hors connexion | — | — | Bandeau `info` du §5.1. Outils et glissements désactivés ; la dernière version chargée reste visible. La consultation (modale « Plan ») fonctionne sur la dernière version en cache, avec la mention « Données du {date heure} ». |
| Placement refusé par l'API (joueur devenu non éligible) | Indicateur 16 px | — | Le pion retourne sur le banc ; toast « {nom} ne peut pas être placé : {raison}. » |
| Licence expirée | Lecture seule (design-system §5) | — | — |

## 7. Mobile (360 px), paysage et ordinateur

Le 4.11 exige un plan utilisable sur smartphone **en portrait et en paysage**. Les positions sont stockées en coordonnées relatives (0 à 100, `schema-donnees.md` §5.11) : un changement d'orientation ne déplace rien. Seul le repère tourne.

### 7.1 Portrait, 360 × 640 et plus (éditeur)

- La barre supérieure mobile (56 px) reste affichée, puis vient l'en-tête compact de 48 px. Pas de ligne de contexte.
- Le **terrain est vertical** (on attaque vers le haut), centré. Sa hauteur vaut : hauteur visible (`100dvh`) − 56 − 48 − banc (84 px) − barre d'outils (56 px). Sa largeur en découle, avec le rapport 68/105, et ne dépasse jamais 336 px (360 moins 2 × 12 px de marge). Sur un écran de 360 × 640, le terrain mesure environ 256 × 396 px ; sur un écran de 360 × 780, environ 336 × 518 px (exemples indicatifs).
- **Pions** : disque de 40 px, zone tactile de 44 px. Sur un terrain de moins de 300 px de large, l'étiquette sous le pion n'affiche que le prénom abrégé à 7 caractères. Le nom complet se trouve dans le menu du pion.
- **Banc** : bande horizontale de 84 px sous le terrain, qui défile latéralement, avec les pions de 40 px et le nom en dessous. La recherche et les puces de poste se trouvent dans un panneau bas, ouvert par une icône loupe en tête de bande, pour ne pas voler de hauteur au terrain.
- **Barre d'outils** : collée en bas de l'écran (56 px), au-dessus de la zone sûre. Elle compte 8 boutons de 40 px avec une zone de 44 px. Sur 336 px de large, « Annuler », « Rétablir » et « Consignes » passent dans un bouton « … » situé en bout de barre : il reste 5 boutons visibles plus « … », soit 6 × 44 = 264 px.
- Pas de zoom par pincement au MVP. La page ne défile jamais horizontalement.
- Glisser un joueur du banc vers le terrain : le mouvement se fait vers le haut, sur une courte distance, ce qui convient au pouce. Le toucher sur un emplacement vide (§4.4) reste l'alternative d'une seule main.

### 7.2 Paysage mobile (par exemple 740 × 360)

- La barre supérieure mobile est **masquée** tant que l'éditeur est affiché en paysage. L'en-tête compact (48 px) reprend le bouton retour, le titre, l'indicateur d'enregistrement, « Publier » et « … ».
- Le **terrain est horizontal** (on attaque vers la droite). Sa hauteur vaut 360 − 48 − 8 = 304 px, et sa largeur environ 470 px.
- La **barre d'outils** forme une colonne à gauche, de 52 px de large, avec des boutons de 40 px empilés. Elle défile verticalement si nécessaire.
- Le **banc** forme une colonne à droite, d'environ 150 px de large, avec la recherche en tête (36 px) et une liste verticale (avatar 32 px, numéro, nom).
- Au passage du portrait au paysage, l'outil actif, la sélection et la position de défilement du banc sont conservés.

### 7.3 Consultation (modale « Plan ») sur mobile

- La modale s'ouvre en plein écran. En portrait, le terrain est vertical, sur toute la largeur, et les consignes suivent en dessous. En paysage, le terrain est horizontal à gauche et les consignes forment une colonne à droite.
- Le pied « Fermer » reste visible dans les deux orientations.

### 7.4 Tablette et ordinateur

- **≥ 768 px** : terrain horizontal, banc en colonne à droite (280 px), barre d'outils en colonne à gauche.
- **≥ 1024 px** : barre latérale de l'application visible (248 px) ; en-tête complet avec la ligne de contexte ; terrain horizontal d'au plus 760 px de large ; colonne de droite de 300 px avec deux onglets, « Banc » et « Consignes ». La souris déplace un pion sans appui long ; au survol, un pion affiche le nom complet en info-bulle.
- **Onglet « Plans »** : une seule carte, d'au plus 800 px de large. La modale « Plan » est centrée, en taille `lg` (800 px), avec le terrain à gauche (60 %) et les consignes à droite (40 %).

## 8. Décisions appliquées et points ouverts

**Décisions appliquées :**

- **10.2 n° 32 (décidé)** : le tableau noir est une exception à la règle des boîtes modales. L'exception est limitée à la page d'édition ; tous les formulaires annexes restent en modale.
- **10.2 n° 16 (décidé)** : les non-membres du staff voient « Indisponible », sans motif, pour un joueur placé devenu indisponible.
- **10.2 n° 31 (décidé)** : le 13 px ne sert que pour les étiquettes de pion et les libellés secondaires. Une raison de blocage est une information critique : elle s'affiche en 14 px dans les listes et les modales. Sur le terrain, faute de place, elle est en 13 px, mais toujours reprise en 14 px dans le panneau du pion.
- **CLAUDE.md §2.5 et CDC 9.2 (Lot 3)** : aucun geste ne permet de placer un joueur non éligible (§5.3). Le contrôle réel est fait par le service, et l'interface n'évalue jamais l'éligibilité elle-même.

**Contradiction documentée (CLAUDE.md §1), non tranchée :**

- **CDC 4.11** : « Les joueurs en dette, suspendus ou inaptes sont grisés et ne peuvent pas être placés. » L'attente d'adhésion n'y figure pas. On retrouve la même formulation dans `schema-donnees.md` §5.11 (« Règle n° 5 rappelée : un joueur en dette, suspendu ou inapte… »).
- **CLAUDE.md §2, règle 5** : « Un joueur en dette, suspendu, inapte **ou en attente d'adhésion** ne peut être ni composé ni placé dans un plan tactique. »
- **Position provisoire appliquée**, la plus restrictive : un joueur en attente d'adhésion ne peut pas être placé, avec la raison « En attente d'adhésion ». Cette position rejoint le « même contrôle d'éligibilité que la composition » du même `schema-donnees.md` §5.11, et la composition inclut l'attente d'adhésion (4.8). **À faire confirmer par le client** avant de considérer le point clos.

**Points ouverts (à trancher par le client) :**

1. **Qui voit un plan en brouillon ?** La matrice 2.4 donne « L » à tous les rôles sur le plan tactique, mais le 4.11 lie la consultation par les joueurs à la **publication**. Position provisoire, la plus prudente : brouillons visibles par le Coach seul, plans publiés visibles par tous. Autre option : lecture des brouillons pour le Président, le VP et le DS.
2. **Destinataires de la notification « Plan publié »** (4.17 : « Joueurs convoqués ») quand le plan n'est rattaché à aucun match, ou que la composition du match n'est pas publiée. Proposition : les joueurs placés sur le plan.
3. **Formations à effectif réduit** : le 4.11 parle de formations « à 7 et 8 joueurs » sans les nommer. Proposition : à 7, 2-3-1 (défaut), 3-2-1 et 3-1-2 ; à 8, 3-3-1 (défaut), 3-2-2 et 2-3-2 (gardien non compté dans l'écriture). La formation « Personnalisée » s'obtient en déplaçant un emplacement. **Question liée** : faut-il pouvoir enregistrer une formation personnalisée dans la bibliothèque du club pour la réutiliser ? Le schéma ne prévoit que la valeur `custom` sur le plan. Proposition : non au MVP, puisque la duplication d'un plan couvre ce besoin.
4. **Numéro de maillot en double** : aucune règle d'unicité du numéro dans la fiche joueur. L'unicité ne vaut que pour le numéro du jour d'un match (`schema-donnees.md` §5.6). Proposition : simple avertissement non bloquant (§4.5).
5. **Joueur placé devenu non éligible** : le CDC interdit de le placer, mais ne dit pas ce que devient un placement existant. Position provisoire, la plus restrictive : le placement est conservé, mais grisé, et la publication ou la republication est bloquée tant qu'il n'est pas remplacé. Aucun retrait automatique n'a lieu. Autre option : retrait automatique, journalisé, avec notification au Coach. Même question que pour la composition (`sport-feuille-de-match.md` §7, point ouvert 1) : à trancher en une seule fois.
6. **Modification d'un plan déjà publié** : le CDC ne dit pas si elle renvoie une notification. Proposition : les modifications sont visibles immédiatement, sans nouvelle notification (même question que pour la composition modifiée après publication, `sport-feuille-de-match.md` §7). Il n'existe pas d'action « Retirer la publication », que le CDC ne prévoit pas (circuit 9.4 si le client la souhaite).
7. **Remplaçants sur le plan** : le 4.11 ne parle que du terrain. Le banc de l'éditeur est une réserve de joueurs, pas une liste de remplaçants. La liste des remplaçants reste dans la composition du match (4.8).
8. **Tableau noir hors connexion** : le 6.6 ne le cite pas. Défaut appliqué : l'éditeur passe en lecture seule sans réseau.

**Alignement demandé sur `sport-espace-coach.md` §3 point 8** : cette spec dit « Clic → page du plan ». Pour respecter le 3.3 (« un clic sur un élément ouvre une modale de détail »), le clic ouvre désormais la modale « Plan » (§4.1), dont le bouton « Modifier sur le tableau noir » mène à l'éditeur. `frontend-dev` doit suivre la présente spec.
