# Écran — Séance (pointage et équipes A/B)

Sources : CDC 3 (charte), 4.7, 4.9, 4.10, 4.12 (déclaration de blessure), 6.6 (hors connexion), 10.2 n° 6, 7, 16, 25, 29 et 38, CLAUDE.md §2.5 (joueurs non sélectionnables), matrice 2.4. Composants : `PitchBoard` (mode `teams`), `SyncIndicator`, `docs/lot0/design-system.md`. Écrans liés : `sport-vestiaire.md` (vestiaire du jour), `sport-feuille-de-match.md` (même pointage pour les matchs).

*Révision du 29/09/2026 (tâche 3.1 du Lot 3)* : ajout des §3.2 bis (non-contournement), §3.2 ter (motifs visibles selon le rôle), des cas limites du §5 et des points ouverts du §7. Le reste de la spec validée est inchangé.

## 1. Objectif

Le dimanche matin, au bord du terrain, d'une main : pointer chaque arrivée en un appui, voir les équipes A et B se former automatiquement et les ajuster, puis enchaîner incidents et évaluations. Tout fonctionne sans réseau.

## 2. Accès

Route `/seances/{id}`. On y arrive par « Ouvrir le pointage » (accueil, espace coach) ou « Ouvrir la séance » (modale de détail).

| Rôle | Pointage | Répartition A/B | Incidents | Évaluations |
| --- | --- | --- | --- | --- |
| Coach | É (corrige l'heure, absence excusée) | É | É | É |
| Capitaine | É (pointe, sans corriger l'heure) | É | É | — |
| Président | É | É | L | É |
| Vice-président | L | L | L | É |
| DS, Médecin, autres joueurs | L | L | L (les siens pour J) | — |

Trésorier, Trésorier adjoint et Intendant ont « — » sur la ligne « Séances et matchs » de la matrice 2.4, mais ils sont aussi joueurs (2.1) : ils reçoivent donc la lecture du rôle Joueur (union des droits, 2.2).

**Placement manuel d'un retardataire** : le 10.2 n° 38 le réserve au « Coach ou [au] Capitaine ». Le Président, qui a « É » sur la répartition (matrice 2.4), peut déplacer un joueur déjà réparti de A vers B. En revanche, **à titre provisoire**, il ne peut pas placer un retardataire depuis « Non répartis » : c'est la lecture littérale du n° 38. Voir le point ouvert du §7.

**Modification limitée au jour même** (fuseau du club). À minuit, la page passe en lecture seule pour tous (4.7).

## 3. Structure de la page

**En-tête** : titre « Séance du {dimanche 27 septembre} » ; contexte « {nom du club} · Rassemblement {07:30} · Limite {08:00} · {terrain} » (terrain facultatif : segment omis s'il n'est pas renseigné) ; `StatusBadge` « Ouverte » / « Verrouillée ». Pas d'action principale en en-tête (l'action principale est dans chaque vue). Menu « … » (Coach, jour même) : « Modifier la séance », « Voir les consignes ». `SyncIndicator` dans la barre supérieure.

**Bandeaux** : hors connexion (« Vous êtes hors connexion. Les pointages sont enregistrés sur ce téléphone et seront envoyés au retour du réseau. ») ; verrouillage (message standard).

**Bascule de vues** (`Tabs` collants sous l'en-tête sur mobile) : « Pointage » · « Équipes A/B » · « Bilan ».

### 3.1 Vue « Pointage » (4.7)

> *Révision du 15/11/2026* : sélection multiple, « Tout cocher » / « Tout décocher » et actions groupées (arrivée, absence excusée), spécifiées dans `sport-pointage-selection-multiple.md` (demande nouvelle, circuit 9.4, à valider). Le pointage un par un ci-dessous reste inchangé. La vue « Bilan » (§3.3) est complétée par `sport-statistiques-seance.md`.

1. **Compteurs** (une ligne) : « Présents {n} » (vert) · « En retard {n} » (rouge) · « Non pointés {n} » · « Excusés {n} » (gris). Heure actuelle affichée à droite (« 07:52 »), avec rappel « Limite 08:00 » qui passe en rouge après l'heure limite.
2. **Recherche et filtres** : champ « Nom ou numéro » (36 px) ; puces « Non pointés » (par défaut), « Tous », « Présents », « En retard », « Excusés ».
3. **Liste des joueurs** du club (tri : non pointés par ordre alphabétique ; pointés par ordre d'arrivée). Ligne de 56 px :
   - avatar 40 px, nom, « n° {numéro} · {poste} » ;
   - à droite, si non pointé : bouton secondaire `sm` **« Arrivé »** (zone 44 px) ;
   - si pointé : heure « 07:42 » + `StatusBadge` « Présent » (vert) ou « En retard · compté absent » (rouge) ; rang d'arrivée « #{rang} » en 13 px muted. Le complément « compté absent » vient de l'API, selon le réglage du club (10.2 n° 25 : configurable par club, compté absent par défaut). Si le club a choisi de ne pas compter le retard comme une absence, l'API renvoie « En retard » seul, en orange (proposition : ce n'est alors plus une absence). L'interface ne décide pas du comptage elle-même ;
   - si absence excusée : `StatusBadge` « Absent excusé » + motif.
   - Un joueur en dette, suspendu, inapte ou en attente d'adhésion **peut être pointé** (le pointage est une présence) ; un petit badge de statut rappelle qu'il ne pourra pas être réparti (voir 3.2). Le libellé de ce badge suit le tableau du §3.2 ter : « Indisponible » en gris pour le Capitaine et les joueurs, le motif pour les rôles qui y ont droit.
4. Appui sur « Arrivé » : enregistrement immédiat de l'heure exacte du téléphone (mise à jour optimiste, indicateur 16 px sur la ligne), la ligne quitte le filtre « Non pointés » avec une courte animation, toast « {prénom} pointé à {07:42}. » avec action « Annuler » (5 s).
5. Appui sur le reste de la ligne → modale « Pointage de {nom} ».

### 3.2 Vue « Équipes A/B » (4.7)

1. **Règle** (une ligne, 13 px) : « Répartition automatique : alternance selon l'ordre d'arrivée (1er en A, 2e en B…). » Équilibre : « A : {n} joueurs · B : {m} joueurs ».
2. **`PitchBoard` mode `teams`** : terrain A (couleur de maillot A) et terrain B, pions en ordre d'arrivée. Chaque nouveau pointé **présent** s'ajoute automatiquement à l'équipe que lui donne la règle, sans déplacer les joueurs déjà placés à la main. Un joueur pointé **en retard** n'est **pas** ajouté automatiquement : il apparaît dans « Non répartis » (point 4) et doit être placé à la main s'il joue (10.2 n° 38, décidé le 25/09/2026).
3. **Déplacement** : glisser-déposer d'un terrain à l'autre, ou toucher un pion → « Passer en B » / « Passer en A », « Voir la fiche du joueur ». Toast « {nom} passé en équipe {B}. » + « Annuler ».
4. **Zone « Non répartis »** (sous les terrains) — décidée par le client (cahier des charges 10.2 n° 29 et n° 38, décidé le 25/09/2026 ; questions Q4/Q21 de `docs/lot0/analyse.md`, voir §7). **Origine des données** : l'appartenance à cette zone est **calculée à la volée** par l'API à chaque lecture (aucun champ stocké : un joueur pointé sans affectation A/B apparaît ici). Elle regroupe **deux catégories bien distinctes**, affichées séparément :
   - **Retardataires** (pion normal, pas de cadenas, badge « En retard ») : **placeables à la main**, par glisser-déposer vers un terrain ou bouton « Passer en A/B », comme n'importe quel joueur déjà réparti. Compté absent dans les statistiques quel que soit son placement.
   - **Non sélectionnables** (en dette, suspendus, inaptes, en attente d'adhésion) : pions grisés avec cadenas et raison fournie par l'API. Le texte de la raison dépend du rôle de la personne connectée (§3.2 ter), par exemple « Suspendu : encore 1 match(s) » pour le Coach et « Indisponible » pour un coéquipier ; une dette n'apparaît jamais au Coach que comme « Non éligible » (décision du client, CDC 10.3 n° 188). **Ils ne peuvent pas être déplacés vers un terrain**, pas même à la main : le service refuse la création de l'affectation, et l'interface ne propose aucun geste qui y mène (§3.2 bis). Dès qu'un joueur est régularisé (Caisse Terrain Express), il quitte cette catégorie. S'il avait été pointé **Présent** (à l'heure), il rejoint l'équipe que lui donne la règle d'alternance (4.7 : les présents sont répartis automatiquement), avec le toast « {nom} peut maintenant jouer : ajouté en équipe {A}. ». S'il avait été pointé **en retard**, il passe dans la catégorie « Retardataires », où il reste à placer à la main (10.2 n° 38), avec le toast « {nom} peut maintenant être placé. ». La mise à jour se fait par interrogation toutes les 15 s.
   - **Joueur à la fois en retard et non sélectionnable** : il apparaît **uniquement** dans « Non sélectionnables », où le blocage l'emporte. Il n'apparaît jamais dans les deux catégories, pour ne pas laisser croire qu'on peut le placer.
   - **Titres exacts des deux sous-zones** : « À placer à la main ({n}) » avec l'aide « Arrivés après l'heure limite : ils ne sont pas répartis automatiquement. » ; « Ne peuvent pas jouer ({n}) » avec l'aide « Ces joueurs ne peuvent être placés dans aucune équipe tant que leur situation n'est pas régularisée. »
   - **Joueur devenu non sélectionnable après avoir été réparti** (par exemple une blessure déclarée pendant la séance, §4.3) : l'API le retire de son équipe et le renvoie dans « Ne peuvent pas jouer ». Toast pour le staff : « {nom} a quitté l'équipe {A} : il ne peut plus jouer. » Côté serveur, ce retrait est une écriture, donc une entrée du journal (CLAUDE.md §2.6).
5. *Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrée 4) — non livrable au Lot 3* : menu « … » de la vue (Président, Coach, Capitaine) « Réappliquer la répartition automatique » → ConfirmDialog « Réappliquer la répartition automatique ? Les déplacements faits à la main seront perdus. » — « Réappliquer ».

### 3.2 bis Aucun contournement possible pour un joueur non sélectionnable (10.2 n° 29, CLAUDE.md §2.5)

Le contrôle réel est fait par le service `assign_team`, qui refuse la création d'une affectation. L'interface ne doit pourtant proposer **aucun** geste qui laisse croire le contraire. Liste exhaustive des chemins à neutraliser, qui sert aussi de liste de tests pour `test-engineer` :

| Chemin | Comportement exigé pour un pion « Ne peuvent pas jouer » |
| --- | --- |
| Glisser-déposer (doigt, souris, stylet) | Le pion ne se soulève pas : pas d'appui long, pas de fantôme. Les terrains ne s'éclairent pas. |
| Toucher simple du pion | Panneau bas en lecture seule, avec le titre « {nom} ne peut pas jouer », la raison (§3.2 ter), le lien « Voir la fiche du joueur » et le bouton « Fermer ». **Pas** de « Passer en A » ni de « Passer en B », même désactivés. |
| Clavier (Espace, flèches, Entrée) | Espace sur le pion annonce : « {nom} ne peut pas être placé : {raison}. » La saisie n'est pas possible. |
| « Annuler » du toast après un déplacement | Si le joueur est devenu non sélectionnable entre-temps, l'API refuse et le toast d'erreur affiche : « Impossible : {nom} ne peut plus jouer. » |
| Répartition automatique (y compris la future « Réappliquer », reportée) | Ignore ces joueurs. |
| Hors connexion | L'éligibilité affichée est celle du dernier chargement, avec la mention « Données du {heure} ». Un joueur non sélectionnable à ce moment le reste à l'écran jusqu'à ce que le serveur confirme sa régularisation : un paiement encaissé hors connexion ne débloque rien tant qu'il n'est pas synchronisé et validé. Si un déplacement a été mis en file alors que l'éligibilité avait changé côté serveur, le refus remonte dans `SyncIndicator` : « Le placement de {nom} n'a pas été retenu : il ne peut pas jouer ({raison}). » |
| Appel direct à l'API (hors interface) | Refus 400 ou 403 du service, avec la raison en français. Ce cas relève des tests API, pas de l'écran. |

### 3.2 ter Raison affichée selon le rôle (10.2 n° 16, matrice 2.4)

Le blocage n'est jamais muet : chaque pion bloqué porte un texte. Ce texte varie selon le rôle, car les coéquipiers ne doivent jamais connaître le motif (10.2 n° 16), et le montant d'une dette relève de la trésorerie (matrice 2.4). **L'API renvoie le texte déjà filtré pour le rôle connecté** ; l'interface l'affiche tel quel, sans jamais le reconstruire.

| Motif | Coach, Président, Vice-président | Directeur sportif, Médecin | Capitaine, autres joueurs | Le joueur lui-même |
| --- | --- | --- | --- | --- |
| Dette | Coach (et Assistant du Coach) : « Non éligible » (décision du client, CDC 10.3 n° 188) ; Président, Vice-président : « En dette : {montant} » | « Indisponible » | « Indisponible » | « En dette : {montant} » |
| Suspension | « Suspendu : encore {n} match(s) » | Idem | « Indisponible » | Idem |
| Inaptitude | « Inapte · retour prévu le {date} » (jamais de diagnostic) | Idem | « Indisponible » | Idem |
| Attente d'adhésion | « En attente d'adhésion » | Idem | « Indisponible » | Idem |

Lorsque le texte reçu est « Indisponible », le panneau du pion ajoute cette précision : « Ce joueur ne peut pas être placé pour l'instant. Le Coach connaît le motif. »

Le libellé « Indisponible » est un `StatusBadge` gris (famille `neutral`). Il ne reprend pas la couleur du motif réel, qui trahirait la raison.

Ce tableau est une **position provisoire prudente** : seuls les droits décidés (10.2 n° 16) et la ligne trésorerie de la matrice 2.4 y sont appliqués. Il est à confirmer, en particulier pour le Capitaine, voir le §7.

### 3.3 Vue « Bilan »

1. **Présences** : taux de présence de la séance, liste des retards (heure), absences excusées.
2. **Incidents de la séance** : 5 derniers, « Voir plus ». Action (Coach, Capitaine) : « Signaler un incident » (modale définie dans `sport-espace-coach.md` §4.5, séance préremplie).
3. **Blessures** : liste (joueur, moment ; aptitude seulement). Action (Coach, Capitaine, Médecin) : « Déclarer une blessure ».
4. **Évaluations** (Coach, Président, VP) : « {n} joueurs à évaluer · reste {h} h ». Action principale : « Évaluer les joueurs » (modale `sport-espace-coach.md` §4.6).

Footer.

## 4. Modales

### 4.1 « Pointage de {nom} » — taille `sm` (panneau bas sur mobile)

- Lecture : heure d'arrivée, statut, rang.
- Coach, jour même :
  - « Heure d'arrivée » (TimeField) — « L'heure doit être comprise dans la journée de la séance. » Le statut Présent / En retard est recalculé par l'API.
  - Bouton secondaire « Marquer absent excusé » → sous-formulaire : « Motif » (SegmentedControl : Blessé / Voyage / Autre), « Précision (facultatif) ».
  - *Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrée 3) — non livrable au Lot 3* : menu « … » « Retirer le pointage » (ConfirmDialog « Retirer le pointage de {nom} ? Il repassera « non pointé » et quittera son équipe. » — « Retirer »).
- Pied : « Annuler » / « Enregistrer ». Succès : « Pointage corrigé. »

### 4.2 « Modifier la séance » — taille `md`

Mêmes champs que « Créer une séance » (`sport-espace-coach.md` §4.1). Un changement de couleur de maillot met à jour les terrains. Succès : « Séance mise à jour. »

### 4.3 « Déclarer une blessure » (4.12, étape 1) — taille `md`, fonctionne hors connexion

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Joueur | PlayerSearch (présents d'abord) | Oui | « Choisissez un joueur. » |
| Moment | TimeField | Oui | Défaut : heure actuelle |
| Circonstances | TextArea | Oui | « Décrivez brièvement les circonstances. » |

Aide : « Le médecin sera prévenu et complétera la fiche. Seule l'aptitude sera visible par le staff. » Pied : « Annuler » / « Déclarer ». Succès : « Blessure déclarée. Le médecin a été prévenu. » Le joueur passe inapte (calcul API) et, s'il était réparti, rejoint « Non répartis ».

## 5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Squelette en-tête + 8 lignes | — | « Impossible de charger la séance. » + « Réessayer » ; hors connexion : dernière version en cache + mention « Données du {heure} » |
| Liste « Non pointés » | — | « Tout le monde est pointé. » | — |
| Liste filtrée | — | « Aucun joueur dans ce filtre. » | — |
| Équipes | Squelette `pitch` × 2 | « Aucun joueur pointé présent pour l'instant. Les équipes se forment au fil des arrivées. » | Modèle standard |
| Non répartis | — | Zone masquée | — |
| Incidents | 2 lignes | « Aucun incident pour l'instant. » + (Coach, Cap.) « Signaler un incident » | Modèle standard |
| Blessures | 1 ligne | « Aucune blessure déclarée. » | Modèle standard |
| Échec d'un pointage (en ligne) | — | — | Ligne revenue à « non pointé », toast « Pointage non enregistré. Réessayez. » |
| Conflit de synchronisation (6.6) | — | — | Via `SyncIndicator` : « Votre pointage de {nom} n'a pas été retenu : une autre saisie est arrivée avant. » |
| Verrouillée | Lecture seule : boutons « Arrivé », menus et glisser-déposer retirés | — | — |
| « À placer à la main » | — | Sous-zone masquée | — |
| « Ne peuvent pas jouer » | — | Sous-zone masquée | — |
| Placement refusé par l'API (joueur devenu non sélectionnable) | Indicateur 16 px sur le pion | — | Le pion revient dans « Ne peuvent pas jouer ». Toast d'erreur : « {nom} ne peut pas être placé : {raison}. » |
| Tentative du Président de placer un retardataire (provisoire, §2) | — | — | Aucun geste n'est proposé : pour le Président, le panneau du pion affiche « Seuls le Coach et le Capitaine placent un retardataire. » |
| Tous les pointés sont non sélectionnables | — | Terrains vides : « Aucun joueur ne peut être réparti pour l'instant. » | — |

## 6. Mobile (360 px) et ordinateur

- **360 px** : bascule de vues collante ; « Pointage » par défaut avant l'heure limite + 30 min, « Équipes A/B » ensuite (proposition). Liste de pointage : bouton « Arrivé » à portée du pouce (côté droit). Terrains empilés (A au-dessus de B, 4.7), pions en 4 colonnes. Une vue à la fois, pas de défilement horizontal.
- **Paysage mobile / ≥ 768 px** : terrains A et B côte à côte.
- **≥ 1024 px** : pas de bascule entre « Pointage » et « Équipes » : liste de pointage à gauche (40 %) et terrains à droite (60 %), le pointage alimentant les terrains en direct ; « Bilan » sous les deux colonnes.
- **Zone « Non répartis » à 360 px** : sous le terrain B, les deux sous-zones sont empilées, « À placer à la main » en premier (c'est là qu'il y a une action), puis « Ne peuvent pas jouer ». Les pions sont en grille de 4 colonnes et la raison s'affiche en 13 px sous le prénom. Si « Ne peuvent pas jouer » compte plus de 8 joueurs, elle est repliée par défaut sur une ligne « {n} joueurs ne peuvent pas jouer » avec le bouton « Afficher ».
- **Glisser un retardataire vers un terrain à 360 px** : les terrains sont au-dessus de la zone. Pendant le glissement, la page défile automatiquement quand le doigt approche du bord haut de l'écran. Le bouton « Passer en A/B » du panneau reste l'alternative recommandée d'une seule main.

## 7. Décisions par défaut et points ouverts

- **10.2 n° 6 / n° 25 / n° 38, tranchées le 25/09/2026** (`docs/lot0/analyse.md` §4 Q21) : un joueur en retard **peut jouer** mais est **compté absent** dans les statistiques (comptage configurable par club). Il n'est **pas** réparti automatiquement selon son rang d'arrivée : il arrive dans « Non répartis », badge « En retard », et doit être placé **à la main** par le Coach ou le Capitaine s'il joue — à la différence des joueurs en dette/suspendus/inaptes, qui restent non-placeables même à la main (voir ci-dessous).
- **10.2 n° 7** appliquée : alternance selon l'ordre d'arrivée pour les présents à l'heure ; le libellé de la règle vient de l'API (le club pourra en choisir une autre).
- **Décidé, cahier des charges 10.2 n° 29** : un joueur en dette, suspendu, inapte ou en attente d'adhésion peut être pointé mais reste dans « Non répartis », **non placeable même à la main**, jusqu'à régularisation. Cette zone n'est qu'une **vue calculée à la volée** par les services existants (solde, suspension, aptitude, adhésion) ; **aucun champ n'est stocké** sur l'affectation d'équipe pour la matérialiser.
- **Reporté après le Lot 5** (`docs/backlog-post-mvp.md`, entrées 3 et 4) : « Retirer le pointage » (non prévu par le 4.7, qui ne mentionne que la correction d'heure et l'absence excusée) et « Réappliquer la répartition automatique ». Ni l'un ni l'autre n'est livré au Lot 3.
- **Proposition** : bascule automatique vers « Équipes A/B » 30 min après l'heure limite ; toast « Annuler » de 5 s après un pointage.
- **10.2 n° 25, portée vérifiée** : la décision rend configurable par club **le comptage** d'un retard comme absence dans les statistiques, et rien d'autre. Elle ne change pas la règle du n° 38 : même dans un club qui ne compte pas le retard comme une absence, le retardataire n'est **pas** réparti automatiquement. **Point ouvert** : faut-il qu'un club qui compte les retardataires présents les voie aussi répartis automatiquement ? À faire confirmer par le client. Défaut appliqué d'ici là : jamais de répartition automatique d'un retardataire. Le réglage lui-même relève des paramètres du club, pas de cet écran.

**Points ouverts ajoutés le 29/09/2026 (à trancher par le client) :**

1. **Le Président peut-il placer un retardataire à la main ?** Le 10.2 n° 38 dit « le Coach ou le Capitaine », alors que la matrice 2.4 donne « É » au Président sur la répartition A/B. Position provisoire, par lecture littérale du n° 38 : non. Il déplace les joueurs déjà répartis, mais ne place pas les retardataires.
2. **L'attente d'adhésion bloque-t-elle la répartition A/B ?** Le 10.2 n° 29 (« dette/suspendu/inapte/en retard ») et le n° 38 (« dette/suspendu/inapte ») ne la citent pas. CLAUDE.md §2.5 la cite, mais pour la composition et le plan tactique. Position provisoire, la plus restrictive : un joueur en attente d'adhésion est bloqué comme les autres (c'est aussi ce que prévoit `schema-donnees.md` §5.4). À confirmer.
3. **Motif visible par le Capitaine (§3.2 ter)** : le Capitaine répartit les équipes, mais il ne figure pas dans la liste des rôles qui voient l'aptitude (10.2 n° 16) et il n'a aucun accès à la trésorerie (matrice 2.4). Position provisoire : il voit « Indisponible », sans motif. Même question pour le montant de la dette vu par le Directeur sportif et le Médecin, qui voient provisoirement « Indisponible » eux aussi.
4. **Régularisation d'un joueur pointé à l'heure** : son ajout automatique dans l'équipe suivante (§3.2, point 4) est une **proposition**, déduite du 4.7 (« les présents sont répartis automatiquement »). Le n° 29 dit seulement « jusqu'à régularisation ».
