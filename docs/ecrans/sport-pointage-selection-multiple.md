# Écran — Pointage : sélection multiple et actions groupées

Sources : CDC 3 (charte), 3.2, 3.3, 3.4, 4.7 (pointage), 4.8 (« Pointage : mêmes règles que pour les séances »), 5.1 et 5.2 (journal), 6.6 (hors connexion), 7.2, matrice 2.4 (ligne « Séances et matchs : pointage, répartition A/B »), 10.2 n° 6, 16, 25, 29 et 38, 10.3 n° 179 (Assistant du Coach), CLAUDE.md §2 règles 5, 6, 13 à 17. Demande du client : `remarques.md` l. 83, décidée le 15/11/2026.

Cette fiche **complète** `sport-seance.md` §3.1 (vue « Pointage ») et la vue de pointage de `sport-feuille-de-match.md`. Elle ne remplace rien : le pointage un par un (bouton « Arrivé ») reste le geste par défaut. Composants : `Checkbox`, `Button`, `ConfirmDialog`, `Modal`, `SegmentedControl`, `StatusBadge`, `Avatar`, `SyncIndicator`, `Toast`, `Loader`, `EmptyState`.

> **NOUVEAU (circuit 9.4, à valider par le client)** : tout ce document. Le CDC 4.7 ne prévoit qu'un pointage joueur par joueur. Les règles de fond (heure limite, retard compté absent, absence excusée réservée au Coach, joueurs bloqués, verrouillage à minuit) **ne changent pas**.

## 1. Objectif

Le dimanche matin, quand un groupe arrive d'un coup (un minibus, cinq joueurs ensemble), pointer tout le groupe en deux appuis au lieu de cinq. En fin de séance, marquer d'un coup les absences excusées connues du Coach. Sans jamais affaiblir les règles : l'heure enregistrée reste l'heure réelle, et le statut (Présent ou En retard) est toujours calculé par l'API.

## 2. Accès

| Rôle | Mode « Sélectionner » | « Pointer l'arrivée » groupé | « Heure d'arrivée commune » | « Absent excusé » groupé |
| --- | --- | --- | --- | --- |
| Coach, Assistant du Coach (10.3 n° 179) | Oui | Oui | Oui (le Coach corrige l'heure le jour même, 4.7) | Oui (4.7 : « Le Coach peut marquer une absence comme excusée ») |
| Capitaine | Oui | Oui | Non : heure du téléphone seulement | Non |
| Président | Oui | Oui (« É » sur le pointage, matrice 2.4) | Non | Non |
| Tous les autres rôles | Non (lecture seule) | — | — | — |

Les boutons ne sont affichés que si l'API renvoie le droit correspondant dans la réponse de la séance (`capabilities.can_bulk_mark`, `can_bulk_excuse`, `can_set_arrival_time`). L'interface ne déduit jamais un droit d'un rôle.

Le mode n'existe que **le jour même** (fuseau du club). Séance verrouillée (minuit, 4.7) : le bouton « Sélectionner » n'est pas affiché.

## 3. Structure (ajouts à la vue « Pointage »)

Rappel de l'existant (`sport-seance.md` §3.1) : compteurs, recherche, puces de filtre (« Non pointés » par défaut, « Tous », « Présents », « En retard », « Excusés »), liste de lignes de 56 px avec bouton « Arrivé ».

### 3.1 Entrée dans le mode

- À droite de la ligne des puces de filtre : bouton secondaire `sm` (36 px) **« Sélectionner »**, zone tactile 44 px.
- Un appui long (500 ms) sur une ligne non pointée entre aussi dans le mode avec cette ligne déjà cochée (raccourci, facultatif : le bouton reste le chemin principal, visible).

### 3.2 En mode sélection

1. **Barre d'en-tête de liste** (remplace la ligne des puces, collante sous les onglets) :
   - case à cocher à trois états (vide, partielle, pleine) + bouton texte **« Tout cocher »**, qui devient **« Tout décocher »** dès que toutes les lignes cochables visibles le sont. Libellé complet : « Tout cocher ({n}) » où {n} est le nombre de lignes cochables du filtre en cours ;
   - à droite, bouton texte **« Terminer »** (sort du mode, vide la sélection).
   - Les puces de filtre et la recherche restent utilisables (la recherche passe sous la barre). **« Tout cocher » ne coche que les lignes visibles** (filtre et recherche en cours) : on peut taper « 1 » dans la recherche puis « Tout cocher », sans risquer de cocher tout l'effectif hors de vue.
2. **Lignes** :
   - ligne **non pointée** : le bouton « Arrivé » est remplacé par une case à cocher à gauche de l'avatar (case de 20 px, zone tactile 44 × 56 px) ; un appui n'importe où sur la ligne coche ou décoche (il n'ouvre plus la modale « Pointage de {nom} ») ;
   - ligne **déjà pointée** (présent, en retard, excusé) : non cochable, case absente, ligne en opacité normale avec son badge. Raison : les deux actions groupées ne concernent que des joueurs non pointés ; un pointage existant se corrige un par un (modale « Pointage de {nom} », Coach).
   - **Joueur bloqué** (dette, suspension, inaptitude, attente d'adhésion) : **cochable**, comme aujourd'hui pointable un par un (le pointage est une présence, `sport-seance.md` §3.1). Il garde son petit badge (« Indisponible » en gris ou le motif, selon le rôle, §3.2 ter de `sport-seance.md`). Le pointer ne le rend **jamais** répartissable ni composable (CLAUDE.md règle 5, 10.2 n° 29).
   - Ordre de sélection : un petit numéro « 1 », « 2 »… (13 px, `--color-text-muted`) apparaît à droite de chaque ligne cochée. Il fixe l'**ordre d'arrivée** retenu (§5.2).
3. **Barre d'actions** collée en bas de l'écran (au-dessus de la zone de sécurité du téléphone), hauteur 56 px, fond `--color-surface`, bordure haute :
   - à gauche : « {n} sélectionné(s) » (14 px) ;
   - action principale **« Pointer l'arrivée ({n}) »** (bouton `primary`, 40 px) ;
   - action secondaire (Coach, Assistant) **« Absent excusé »** (bouton secondaire, 40 px). Pour les autres rôles, ce bouton n'existe pas (pas désactivé : absent).
   - Les deux boutons sont désactivés tant que {n} = 0, avec l'aide « Cochez au moins un joueur. » en texte masqué pour lecteur d'écran.
   - Une seule action principale dans la zone (3.1).

### 3.3 Maquette 360 px

```
┌──────────────────────────────────────┐
│ Séance du dimanche 22 novembre    ●  │ 20 px
│ {Club} · Rass. 07:30 · Limite 08:00  │ 14 px
│ [Pointage][Équipes A/B][Bilan]       │ onglets 40 px
├──────────────────────────────────────┤
│ Présents 9 · Retard 1 · Non pointés 14│
│ [☐▣] Tout cocher (14)      Terminer  │ barre collante 44 px
│ [ Nom ou numéro              ]       │ 36 px
│ ☑ (AV) Prénom Nom      n°7 · Mil. 1  │ 56 px
│ ☑ (AV) Prénom Nom      n°4 · Déf. 2  │
│ ☐ (AV) Prénom Nom  [Indisponible]    │
│ ☐ (AV) Prénom Nom      n°11 · Att.   │
│ …                                    │
├──────────────────────────────────────┤
│ 2 sélectionnés  [Absent excusé] [Pointer l'arrivée (2)] │ 56 px collée
└──────────────────────────────────────┘
```

À 360 px, si les deux boutons ne tiennent pas avec le compteur, le compteur passe au-dessus des boutons (barre de 88 px) ; les libellés ne sont **jamais** tronqués.

### 3.4 Ordinateur (≥ 1024 px)

La liste de pointage occupe la colonne gauche (40 %), les terrains la droite (`sport-seance.md` §6). La barre d'actions n'est pas collée au bas de la fenêtre : elle se place en bas de la colonne de la liste (collante dans la colonne). Raccourcis clavier : Espace coche la ligne active, Maj + clic coche une plage (l'ordre de sélection suit alors l'ordre de la liste), Échap sort du mode.

## 4. Modales

### 4.1 Confirmation « Pointer l'arrivée » — `ConfirmDialog`, taille `sm`, panneau bas sur mobile

- Titre : « Pointer l'arrivée de {n} joueur(s) ? »
- Corps :
  - « Heure enregistrée : {07:52} (heure de ce téléphone). »
  - si l'heure est postérieure à l'heure limite : bandeau `warning` « Il est plus de {08:00} : ces joueurs seront enregistrés en retard{, et comptés absents} selon la règle du club. » (le complément vient de l'API, 10.2 n° 25) ;
  - si la sélection contient des joueurs bloqués : « {k} de ces joueurs ne pourront pas être placés dans une équipe. » (aucun motif dans cette phrase, quel que soit le rôle) ;
  - « Ordre d'arrivée retenu : l'ordre dans lequel vous les avez cochés. » ;
  - liste repliée « Voir les joueurs » (avatar 24 px, « Prénom N. », rang).
- **Coach et Assistant seulement** : case « Indiquer une autre heure d'arrivée » ; cochée, elle affiche un `TimeField` « Heure d'arrivée commune » (défaut : heure actuelle). Erreurs : « L'heure doit être comprise dans la journée de la séance. » ; « L'heure ne peut pas être dans le futur. » Aide : « Utile si le groupe est arrivé avant que vous ayez pu le pointer. » Le statut est recalculé par l'API à partir de cette heure.
- Pied : « Annuler » / « Pointer ({n}) ».
- Pas de saisie libre : la fermeture par croix, Échap ou clic extérieur ne demande pas de confirmation, sauf si l'heure commune a été modifiée (« Abandonner les modifications ? »).

Pourquoi une confirmation alors que le pointage unitaire n'en a pas : le pointage unitaire a un toast « Annuler » de 5 s. Une annulation groupée supposerait « Retirer le pointage », reporté après le Lot 5 (`backlog-post-mvp.md` entrée 3). On confirme donc **avant**, pour ne pas devoir défaire **après**.

### 4.2 « Marquer {n} absences excusées » — `Modal`, taille `sm` (Coach, Assistant)

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Motif | `SegmentedControl` : Blessé / Voyage / Autre | Oui | Mêmes valeurs que la modale unitaire (`sport-seance.md` §4.1). « Choisissez un motif. » |
| Précision (facultatif) | `TextArea` | Non | 200 caractères max. Aide : « Ce texte est le même pour tous les joueurs cochés. N'y écrivez aucun détail médical. » |

- Rappel en tête : « Une absence excusée reste une absence ; elle est distinguée dans les statistiques. » (4.7)
- Liste repliée « Voir les joueurs ».
- Pied : « Annuler » / « Marquer excusés ({n}) ».

### 4.3 « Détail du pointage groupé » — taille `sm`

Ouverte depuis le toast de résultat partiel (§6). Deux listes : « Pointés ({n}) » (avatar, nom, heure, badge) et « Non pointés ({m}) » (avatar, nom, raison en français fournie par l'API, par exemple « Déjà pointé par une autre saisie à 07:49. »). Pied : « Fermer ».

## 5. Règles métier

1. **Aucune règle du 4.7 n'est modifiée.** L'action groupée appelle, joueur par joueur, le même service que le bouton « Arrivé » (`mark_arrival`) ou que l'absence excusée unitaire. Le statut Présent ou En retard est calculé par le service à partir de l'heure d'arrivée et de l'heure limite ; il n'existe **pas** d'action « Marquer présent » qui forcerait le statut. Le libellé « Pointer l'arrivée » le dit volontairement.
2. **Ordre d'arrivée** (répartition A/B par alternance, 10.2 n° 7) : tous les joueurs d'un lot reçoivent la même heure. Le rang d'arrivée entre eux suit l'**ordre de sélection** (transmis par l'interface, `selection_rank`). Avec « Tout cocher », c'est l'ordre d'affichage de la liste. Proposition, à valider (§9 question 2).
3. **Répartition automatique** : inchangée. Chaque joueur pointé Présent du lot est réparti par la règle du club, dans l'ordre du point 2 ; un joueur en retard va dans « À placer à la main » (10.2 n° 38) ; un joueur bloqué va dans « Ne peuvent pas jouer » (10.2 n° 29) et n'est jamais placé.
4. **Retard** : il découle de l'heure, jamais d'un choix. Il n'y a donc pas d'action groupée « Marquer en retard ». Le comptage en absence suit le réglage du club (10.2 n° 25).
5. **Absence excusée groupée** : seulement Coach et Assistant ; seulement sur des joueurs non pointés.
6. **Verrouillage** : à minuit (fuseau du club), l'API refuse tout lot (« Cette séance est verrouillée depuis minuit. Seul le support peut la corriger, à la demande du Président. »). Un lot préparé hors connexion avant minuit et envoyé après est refusé de la même façon, joueur par joueur, et le refus remonte dans `SyncIndicator`.
7. **Succès partiel** : chaque joueur est traité indépendamment (pas de « tout ou rien »). Au bord du terrain, un seul conflit (un joueur pointé entre-temps par le Capitaine) ne doit pas bloquer les vingt autres. Le résultat est détaillé joueur par joueur.
8. **Taille d'un lot** : 100 joueurs au plus par envoi (limite technique, pas une règle du CDC). Au-delà, l'interface envoie plusieurs lots.
9. **Matchs** : mêmes règles et même écran pour le pointage d'un match (4.8 : « mêmes règles que pour les séances »).

## 6. États et textes

| Cas | Affichage |
| --- | --- |
| Envoi en cours | Bouton « Pointer ({n}) » avec `Loader` 16 px et libellé « Pointage… » ; lignes concernées avec indicateur 16 px ; barre d'actions désactivée |
| Succès complet | Sortie du mode sélection, toast « {n} joueurs pointés à {07:52}. » ; absences : « {n} absences excusées enregistrées. » |
| Succès partiel | Toast `warning` « {n} joueurs pointés. {m} n'ont pas pu l'être. » + action « Voir le détail » (§4.3). Les lignes non traitées restent cochées, le mode reste ouvert |
| Échec total (en ligne) | Toast d'erreur « Pointage non enregistré. Réessayez. » ; sélection conservée |
| Hors connexion | Le lot est enregistré sur le téléphone ; lignes passées en « pointé » localement avec la mention « En attente d'envoi » (13 px) ; toast « {n} pointages enregistrés sur ce téléphone. Ils seront envoyés au retour du réseau. » |
| Conflit à la synchronisation | Par joueur, dans `SyncIndicator` : « Votre pointage de {nom} n'a pas été retenu : une autre saisie est arrivée avant. » (texte existant) |
| Aucune ligne cochable dans le filtre | « Tout cocher » désactivé ; dans la liste : « Tout le monde est pointé. » (texte existant) |
| Séance verrouillée pendant la sélection | Sortie du mode, bandeau de verrouillage, toast « La séance vient d'être verrouillée. Rien n'a été enregistré. » |
| Droit retiré pendant la sélection (rôle révoqué) | Refus 403 de l'API : toast « Vous n'avez plus le droit de pointer cette séance. » |

## 7. Données et API (noms proposés pour `backend-dev`)

- `POST /api/v1/sport/sessions/{id}/attendance/bulk/` et `POST /api/v1/sport/matches/{id}/attendance/bulk/`
  - corps : `{ "action": "arrive" | "excuse", "arrived_at": "…" (facultatif, Coach et Assistant seulement), "reason_code": "injured" | "travel" | "other" (si excuse), "reason_detail": "…", "items": [{ "membership_id", "client_uuid", "client_recorded_at", "selection_rank" }] }` ;
  - réponse 200 : `{ "batch_id", "results": [{ "membership_id", "outcome": "created" | "skipped" | "refused", "message", "attendance": {…} }], "counts": { "created", "skipped", "refused" } }` ; 400 si lot vide ou trop grand ; 403 si droit absent ; 409/400 si séance verrouillée.
  - Permissions : `CanRecordAttendance` (Coach, Assistant, Capitaine, Président) pour `arrive` ; `CanCorrectAttendanceTime` pour `arrived_at` ; permission d'excuse existante (Coach, Assistant) pour `excuse`.
- Service : `mark_arrivals_bulk(event, items, actor, arrived_at=None)` et `excuse_absences_bulk(…)` dans `apps/sport/services.py`, qui appellent les services unitaires existants pour chaque joueur (une transaction par joueur), après un contrôle unique du verrouillage de l'événement.
- `client_uuid` par joueur : l'idempotence du pointage hors connexion (6.6) est conservée telle quelle (contrainte `attendance_unique_client_uuid` existante).
- Réponse de la séance : ajouter `capabilities.can_bulk_mark`, `can_bulk_excuse`, `can_set_arrival_time`.
- **Aucune migration de modèle sport.** Voir §8 pour le journal.

## 8. Journal d'activité : proposition et justification

**Proposition : une entrée par pointage**, comme aujourd'hui, et chaque entrée porte l'identifiant du lot (`batch_id`) et sa taille. Pas d'entrée récapitulative supplémentaire.

Raisons :

1. **Règle 6 (CLAUDE.md) et 5.1** : chaque pointage crée une donnée distincte (une ligne `Attendance`, avec son heure et son auteur). Une entrée par donnée créée est la lecture la plus directe de la règle.
2. **Traçabilité par joueur** : la surveillance du Superuser (5.5) et une correction demandée par le Président (4.7) partent toujours d'un joueur précis (« qui a pointé X, à quelle heure ? »). Une entrée groupée obligerait à chercher un joueur à l'intérieur d'une liste stockée en JSON, ce qui est justement un comportement qui diffère entre SQLite et MySQL (CLAUDE.md §9).
3. **Succès partiel et hors connexion** : avec des résultats joueur par joueur et des conflits de synchronisation joueur par joueur, une entrée unique décrirait mal ce qui a vraiment été enregistré.
4. **Le lot reste visible** : le `batch_id` commun permet de retrouver « 12 pointages faits ensemble à 07:52 par {auteur} ». Le coût (une vingtaine d'entrées) est négligeable.

Contenu de chaque entrée (5.1) : auteur, date, club, action « Pointage (lot de {n}) » ou « Absence excusée (lot de {n}) », joueur concerné, heure retenue, statut calculé, indication « heure commune saisie par le Coach » le cas échéant. Le `batch_id` va dans les métadonnées existantes de `log_action` ; si le Superuser doit pouvoir **filtrer** par lot, il faut un champ indexé (`correlation_id`) dans `apps/audit` (migration réversible) — à décider avec `backend-dev`.

Notifications : aucune nouvelle (le 4.17 n'en prévoit pas pour le pointage).

## 9. Questions pour le client

1. **Validation de la fonction** (circuit 9.4) : sélection multiple, « Tout cocher » / « Tout décocher », deux actions groupées (arrivée, absence excusée).
2. **Ordre d'arrivée dans un lot** : l'ordre de sélection est-il le bon critère pour l'alternance A/B ? Autre option : ordre alphabétique, ou numéro de maillot.
3. **« Heure d'arrivée commune »** réservée au Coach et à l'Assistant : la garder ? Elle découle du droit du Coach de corriger l'heure le jour même (4.7), mais elle permet aussi de faire passer un groupe arrivé en retard pour un groupe à l'heure. Chaque usage est journalisé avec la mention « heure commune saisie par le Coach ».
4. **Le client a écrit « marquer présent »** : la spec ne propose pas de forcer le statut « Présent » (ce serait contraire au 4.7 et au 10.2 n° 25) ; elle enregistre l'heure et laisse l'API calculer. À confirmer.
5. **Journal** : une entrée par pointage avec identifiant de lot (§8) — à confirmer.
