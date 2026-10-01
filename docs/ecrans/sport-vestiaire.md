# Écran — Vestiaire du jour

Sources : CDC 3 (charte), 2.1, 2.4 (précision : « Le Joueur voit en lecture seule […] le vestiaire »), 4.7 (« Vestiaire du jour »), 4.8 (pointage des matchs, composition publiée), 4.12 (confidentialité), 6.5, 6.6, 10.2 n° 16, 25, 29 et 38, CLAUDE.md §2.5 et §2.11. Composants : `PitchBoard` (mode `readonly`), `StatusBadge`, `Avatar`, `SegmentedControl`, `EmptyState`, `Loader`, `docs/lot0/design-system.md` §3.8. Écrans liés : `sport-seance.md` (source du pointage et des équipes), `sport-feuille-de-match.md`, `club-accueil.md` §3 point 2 (carte « Vestiaire du jour »).

## 1. Objectif

Répondre en un coup d'œil, le dimanche matin, à trois questions : qui est là, dans quelle équipe je joue, et qui manque encore. La page est une vue de **consultation pure**. Elle se remplit toute seule à partir du pointage (4.7) : personne n'y saisit rien.

## 2. Accès

Route `/vestiaire`. Entrée de barre latérale « Vestiaire du jour », visible par tous (design-system 3.9). Depuis l'accueil, on y arrive par le lien « Ouvrir le vestiaire » (`club-accueil.md`).

| Rôle | Accès |
| --- | --- |
| Tous les joueurs du club, bureau et staff compris (2.1) | Lecture seule (4.7 : « visible par tous les joueurs du club ») |
| Coach, Capitaine, Président | Lecture, plus un raccourci « Ouvrir le pointage » vers la page Séance ou la page du match (ils ont « É » sur le pointage, matrice 2.4). Le vestiaire lui-même ne se modifie pas. |
| Superuser | Pas d'entrée : il n'est pas joueur (2.1). En Ghost Mode, il voit la page comme un joueur du club. |

La page affiche **l'événement du jour**, selon la date dans le fuseau du club. À minuit, elle bascule sur le jour suivant. L'historique se consulte depuis les pages Séances et Matchs, pas ici.

## 3. Structure de la page

**En-tête** : titre « Vestiaire du jour » ; contexte « {nom du club} · {dimanche 27 septembre} ». Pas d'action principale. Action secondaire, pour le Coach, le Capitaine et le Président pendant la journée : « Ouvrir le pointage ». Indicateur « Mis à jour à {08:12} » en 13 px muted, à droite du contexte (sous le contexte sur mobile).

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
   - **Vue « Terrain »** : `PitchBoard` en mode `readonly`, avec les deux terrains aux couleurs des maillots (empilés sous 768 px, côte à côte au-delà). Un toucher sur un pion ouvre une info-bulle avec le nom complet, le numéro et le poste. Il n'y a aucun glisser-déposer ni aucun menu d'action.
   - Aucun bouton « Passer en A/B » : cette page ne modifie rien, même pour le Coach, qui passe par « Ouvrir le pointage ».
4. **Présents sans équipe** — les joueurs pointés (présents ou en retard) qui ne sont dans aucune équipe, c'est-à-dire la zone « Non répartis » de `sport-seance.md` §3.2. Deux groupes, dans cet ordre :
   - « En attente de placement ({n}) » : les retardataires non encore placés, avec le badge « En retard » (10.2 n° 38) ;
   - « Ne jouent pas aujourd'hui ({n}) » : les joueurs en dette, suspendus, inaptes ou en attente d'adhésion (10.2 n° 29). **Pour tous les rôles**, ils n'ont que le badge gris « Indisponible », sans motif, conformément au 10.2 n° 16. Le vestiaire est une vue commune à tout le club : le motif est consulté sur la page Séance par les rôles qui y ont droit (`sport-seance.md` §3.2 ter). Seule exception, le joueur concerné voit son propre motif, dans « Ma situation » seulement.
   - Ligne de 44 px : avatar de 32 px, « Prénom N. », badge. Aucune action.
5. **Pas encore pointés** — **visible seulement par le Coach, le Capitaine et le Président**, c'est-à-dire les rôles qui pointent. Pour les autres, la carte n'est pas affichée (proposition, §7). La carte affiche un compteur, « {n} joueurs pas encore pointés », et une liste repliée par défaut (bouton « Afficher »). Chaque ligne contient l'avatar, le nom et le numéro. Un clic sur une ligne ouvre la page Séance, filtre « Non pointés ». Cette carte n'apparaît que pendant la journée de l'événement.

Footer.

## 4. Modales

Seule modale : « Consignes » (taille `sm`, panneau bas sur mobile). Elle affiche le texte des consignes de la séance en 16 px, avec le pied « Fermer ». Aucun formulaire : le vestiaire est une page de consultation.

## 5. Mise à jour et réseau

- Tant que l'onglet est actif, la page se met à jour **toutes les 30 s par interrogation**, sans WebSocket (6.5), et l'interrogation est suspendue quand l'onglet est inactif. L'indicateur « Mis à jour à {heure} » change à chaque rafraîchissement. Un joueur qui vient d'être pointé ou déplacé apparaît avec un léger surlignage pendant 2 s, coupé si `prefers-reduced-motion` est actif.
- Hors connexion, la dernière version reçue reste affichée avec le bandeau `info` : « Vous êtes hors connexion. Vestiaire du {heure} : il sera mis à jour au retour du réseau. »
- Sur le téléphone qui pointe (Coach ou Capitaine), les pointages hors connexion en attente ne sont **pas** mêlés au vestiaire : celui-ci ne montre que l'état confirmé par le serveur. La page Séance reste la seule vue qui montre l'état local.

## 6. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Barre de progression, puis squelettes : en-tête, 1 ligne « Rendez-vous », 1 ligne « Ma situation », 2 colonnes de 5 lignes | — | « Impossible de charger le vestiaire. » + « Réessayer » ; hors connexion, dernière version en cache (§5) |
| Aucun événement aujourd'hui | — | `EmptyState` : « Aucune séance ni aucun match aujourd'hui. », avec la précision « Prochain rendez-vous : {Séance · dimanche 4 octobre · 07:30} » si l'API en renvoie un (sinon, précision omise). Action pour le Coach : « Créer une séance », qui ouvre la modale de `sport-espace-coach.md` §4.1. Pour les autres rôles, message seul. | — |
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
