# Écran — Accueil

Sources : CDC 3.1, 3.5, 4.1 (premier accès), 4.7 (vestiaire du jour), 4.16 (communiqués), 4.17 (aucune liste de notifications sur l'accueil), 7.1, 7.5. Composants : `docs/lot0/design-system.md`.

## 1. Objectif

Donner à chaque joueur, en moins de 5 secondes sur smartphone, ce qui le concerne aujourd'hui : communiqués à lire, sa propre situation, le prochain rendez-vous. Les actions en attente lui parviennent par les notifications (4.17) ; la carte « À faire » et les raccourcis sont reportés après le Lot 5 (§4, §8). L'accueil ne duplique pas les autres pages : il résume et renvoie.

## 2. Accès

Route `/`. Tous les joueurs du club (tous rôles). Le contenu varie selon les rôles cumulés (union, 2.2). Un Superuser est redirigé vers `/admin`.

| Section | Visible par |
| --- | --- |
| Communiqués épinglés | Tous ; bouton « Publier un communiqué » : Président, VP, Secrétaire (révision 11/10, voir `fil-public-communication.md` B2) |
| À faire — *reporté après le Lot 5* | Tous (contenu selon les rôles) |
| Vestiaire du jour | Tous ; mis en avant (position 2, déplié) pour le Président (4.7) |
| Ma situation | Tous |
| Prochain rendez-vous | Tous |
| Raccourcis — *reporté après le Lot 5* | Trésorier, adjoint, Coach, Capitaine, Président |
| Derniers résultats | Tous |

## 3. Premier accès (avant l'accueil)

Enchaînement bloquant, dans cet ordre, à la première connexion ou après une réinitialisation :

1. **Modale bloquante « Changez votre mot de passe »** (4.1, 7.1) — sans croix, Échap et voile inactifs.
   - Texte : « Pour protéger votre compte, choisissez un nouveau mot de passe. Tant que ce n'est pas fait, vous ne pouvez consulter aucune donnée. »
   - Champs : « Nouveau mot de passe » (8 caractères minimum), « Confirmez le mot de passe ».
   - Erreurs : « Le mot de passe doit contenir au moins 8 caractères. » ; « Le mot de passe doit être différent de votre email. » ; « Les deux mots de passe ne correspondent pas. »
   - Pied : « Se déconnecter » (secondaire) / « Enregistrer ».
2. **Modale bloquante « Vos données et votre consentement »** (7.5) : acceptation des CGU et de la politique de confidentialité (cases obligatoires), consentement au traitement des données de santé et à la publication de la carte de joueur (cases distinctes). Pied : « Se déconnecter » / « Continuer ». Liens vers les textes, ouverts dans une modale de lecture.
3. **Modale « Ajoutez votre photo »** (4.1, photo demandée à la première connexion) — non bloquante : « Plus tard » / « Enregistrer la photo ».

## 4. Structure de la page

**En-tête** : titre « Bonjour, {prénom} » ; contexte « {nom du club} · {date du jour longue} ». Pas d'action d'en-tête (l'accueil résume et renvoie ; les actions se font dans les pages et modales des modules).

**Bandeaux** (si applicable) : lecture seule (licence expirée), hors connexion, alerte rouge « Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée. » (Trésorier, adjoint, Président ; lien « Voir la dépense »), licence proche de l'expiration (Président : « La licence du club expire le {date}. »).

Sections en cartes, dans l'ordre :

1. **Communiqués** — au plus 3 communiqués épinglés, du plus récent au plus ancien. Chaque ligne : titre (16 px/600), auteur (avatar 24 px + nom), date, pastille « Non lu » si non lu. Clic → modale « Communiqué ». Pied : « Voir tous les communiqués » (lien vers la page Communiqués). Action de carte (Président, VP, Secrétaire — révision 11/10) : « Publier un communiqué ».
2. **Vestiaire du jour** (4.7) — seulement s'il y a une séance ou un match aujourd'hui.
   - Président : carte dépliée avec `PitchBoard` `readonly` compact (liste des présents par équipe A/B, avatars 32 px) et compteur « {n} présents ».
   - Autres rôles : ligne résumé « {Séance / Match contre X} · {n} présents · Vous êtes en équipe {A/B} » + lien « Ouvrir le vestiaire ».
3. **À faire** — ***Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrée 1) — non livrable au MVP.*** Description conservée pour mémoire. Aucune action du MVP ne dépend de cette carte : chaque modale citée ci-dessous a son propre point d'entrée livré avec son module (voir §5.3 à §5.7). Éléments en attente d'une action de l'utilisateur, calculés par l'API (ce n'est **pas** une liste de notifications, 4.17). 5 au plus + « Voir plus ». Chaque ligne : libellé, badge orange, clic → ouvre directement la modale d'action concernée. Exemples selon rôle :
   - Parrain : « Fiche d'adhésion de {nom} à signer » (4.3) → modale §5.4.
   - Président : « Parrainage de {nom} refusé : décision à prendre » (4.3, cas limite) → modale §5.5 ; « {nom} attend la signature de son parrain depuis 7 jours » (4.3) → même modale §5.5.
   - Président, VP : « Dépense de {montant} à valider » → modale §5.6 ; « Demande d'assistance de {nom} à traiter » → modale §5.7 ; « Procès-verbal de l'AG du {date} à signer » (`assemblees-page-ag.md`).
   - Trésorier, adjoint : « Déclaration « J'ai payé » de {nom} à valider ».
   - Coach, Président, VP : « {n} joueurs à évaluer — séance du {date} — reste {h} h ».
   - Joueur : « Offre de transfert de {club} à examiner ».
4. **Ma situation** — `StatusBadge` financier (+ Suspendu / Blessé superposés), « Solde : {montant} » (tabular-nums, 20 px), « Prochaine échéance : {montant} le {date} », aptitude (`StatusBadge`). Action principale de la carte : « Contribuer » (ouvre le lien de paiement du club dans un nouvel onglet ; masqué si le club n'en a pas configuré). Lien « Voir mon profil ».
5. **Prochain rendez-vous** — prochaine séance ou prochain match : date, heure de rassemblement, lieu, heure limite d'arrivée ; si composition publiée : « Vous êtes convoqué : titulaire » / « remplaçant » / « non convoqué » et lien « Voir la composition ». Clic → modale de détail de la séance ou du match (voir `sport-espace-coach.md`).
6. **Raccourcis** — ***Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrée 2) — non livrable au MVP.*** Description conservée pour mémoire ; chaque action citée reste accessible depuis sa page de module (Trésorerie, Espace coach, Séance). (Selon rôles, 3 boutons au plus, secondaires, aucune `primary`) :
   - Trésorier / adjoint : « Enregistrer un paiement », « Caisse Terrain Express ».
   - Coach : « Créer une séance », « Créer un match ».
   - Capitaine / Président (jour de séance) : « Ouvrir le pointage ».
   Chaque bouton ouvre directement la modale correspondante (ou la page Séance pour le pointage).
7. **Derniers résultats** — 5 derniers matchs joués (3.3) : date, adversaire, score, badge « Victoire » / « Nul » / « Défaite » en texte simple (pas de badge de statut). « Voir plus » ajoute 5 résultats. Clic → modale de détail du match.

Footer.

## 5. Modales

### 5.1 « Communiqué » (détail)

- En-tête : titre du communiqué ; sous-titre « Publié par {nom} le {date} ».
- Corps : texte (16 px), images éventuelles.
- Pied : « Fermer » ; action principale « J'ai lu » (accusé de lecture, 4.16) — remplacée par « Lu le {date} » (texte) une fois fait. Secondaire : « Partager sur WhatsApp » (ouvre WhatsApp avec le titre et le lien Vesta ; le contenu reste accessible après connexion uniquement).
- Menu « … » (Président, VP, Secrétaire — révision 11/10) : « Désépingler », « Voir les accusés de lecture » (liste : avatar, nom, date de lecture, filtre « Lu / Non lu »).

### 5.2 « Publier un communiqué » (Président, VP, Secrétaire — révision 11/10)

| Champ | Composant | Obligatoire | Règle | Erreur |
| --- | --- | --- | --- | --- |
| Titre | TextField | Oui | 120 caractères max. | « Ce champ est obligatoire. » |
| Message | TextArea | Oui | 2 000 caractères max., compteur | « Ce champ est obligatoire. » |
| Images | FileField (images) | Non | 4 au plus, compressées à 1 600 px (4.16) | « 4 images au maximum. » |
| Épingler en tête de l'accueil | Checkbox | — | Cochée par défaut | — |

Pied : « Annuler » / « Publier ». Succès : toast « Communiqué publié. Tous les joueurs ont été prévenus. »

### 5.3 Modales d'action et leurs points d'entrée

La carte « À faire » et les raccourcis étant reportés après le Lot 5, **aucune de ces modales n'est ouverte depuis l'accueil au MVP**. Chacune s'ouvre depuis la notification correspondante (4.17 : « un clic sur une notification mène à l'élément concerné ») et depuis la page de son module. Définies dans les specs des écrans concernés (non dupliquées ici) : déclaration « J'ai payé » à valider (`tresorerie-tableau-de-bord.md` §4.5), signature de PV (`assemblees-page-ag.md`), évaluation rapide (`sport-espace-coach.md` §4.6), enregistrement d'un paiement et Caisse Terrain Express (`tresorerie-tableau-de-bord.md`), création de séance et de match (`sport-espace-coach.md`), offre de transfert (`mercato-marche.md`).

Les quatre modales suivantes n'ont pas encore d'écran de module au Lot 0. Les modales d'adhésion restent spécifiées ici au minimum et seront détaillées au Lot 1 (§5.4 à §5.5). Les modales de dépense et d'assistance sont détaillées dans `tresorerie-depenses-assistance.md` (§3.3 et §4.2) ; cette page ne les duplique pas. Les actions sensibles utilisent la modale de confirmation (`ConfirmDialog`, variante action sensible) du design system : texte explicite de l'action, boutons « Annuler » / action ; l'auteur est écrit au journal d'activité (décision du 11/10/2026 : le code PIN est supprimé).

### 5.4 « Fiche d'adhésion de {nom} » — signature par le parrain (4.3) — taille `lg`

> **Spec minimale. Modale détaillée au Lot 1 (adhésion, cf. CDC 4.3).**

- Accès : le parrain désigné uniquement.
- **Points d'entrée (Lot 1)** :
  1. **Notification « Fiche d'adhésion à signer »** (CDC 4.3 étape 4, tableau 4.17 : Parrain, in-app) et son rappel à 3 jours (4.3) : un clic ouvre directement cette modale, par-dessus la page en cours. La notification reste accessible dans la modale des notifications (« Voir plus ») tant que la fiche est en attente, même marquée comme lue.
  2. **Fiche du joueur** ouverte depuis l'Effectif de « Comité et bureau » (`club-comite-bureau.md` §3, section 6) : pour le parrain désigné, si le joueur est « En attente » et la fiche générée, bouton principal « Signer la fiche d'adhésion » dans le pied de la fiche → ouvre cette modale au niveau 2.
- Si l'utilisateur n'est plus le parrain désigné, ou si la fiche n'est plus en attente, la modale s'ouvre en lecture seule avec le message « Cette fiche a déjà été signée ou n'est plus en attente. »
- Lecture : aperçu de la fiche d'adhésion PDF (servie par vue authentifiée, 10), identité du nouveau joueur (avatar, nom, poste), « Frais d'adhésion payés le {date} » (la fiche n'est générée qu'après le paiement, 4.3 étapes 2–3).
- Pied : « Refuser » (secondaire) / « Signer la fiche » (principal) → modale de confirmation (`ConfirmDialog`, variante action sensible) « Signer la fiche d'adhésion de {prénom} ? » — texte « Votre signature est enregistrée dans le journal d'activité du club. » — « Annuler » / « Signer »
- « Refuser » ouvre un niveau 2 : TextArea « Motif du refus » (obligatoire, « Indiquez le motif. ») ; pied « Annuler » / « Refuser le parrainage ».
- Succès : « Fiche signée. {prénom} est maintenant inscrit. » / « Refus enregistré. Le Président a été prévenu. »
- Erreurs : « Cette fiche a déjà été signée ou n'est plus en attente. »

### 5.5 « Adhésion de {nom} » — décision du Président après refus ou silence du parrain (4.3) — taille `md`

> **Spec minimale. Modale détaillée au Lot 1 (adhésion, cf. CDC 4.3).**

- Accès : Président.
- **Points d'entrée (Lot 1)** :
  1. **Notification au Président** « Le parrain de {nom} a refusé l'adhésion : décision à prendre » (CDC 4.3, cas limite « le parrain refuse ») et **alerte** « {nom} attend la signature de son parrain depuis 7 jours » (4.3, cas limite « le parrain ne répond pas ») : un clic ouvre directement cette modale. Ces deux notifications découlent du 4.3 (le tableau 4.17 ne les liste pas ; libellés exacts à fixer au livrable E « Textes des notifications », Lot 1).
  2. **Fiche du joueur** ouverte depuis l'Effectif de « Comité et bureau » (`club-comite-bureau.md` §3, section 6 ; filtre « Statut : En attente ») : pour le Président, si le parrainage est refusé ou sans réponse depuis 7 jours, bouton principal « Décider de l'adhésion » dans le pied de la fiche → ouvre cette modale au niveau 2.
- Lecture : joueur, parrain actuel, `StatusBadge` « Parrainage refusé » (rouge) avec motif et date, ou « Sans réponse depuis {n} jours » (orange) ; état des frais d'adhésion (« Payés le {date} · {montant} » ou « Non payés »).
- Choix (SegmentedControl, obligatoire) : « Désigner un autre parrain » / « Annuler l'adhésion ».
  - « Désigner un autre parrain » : PlayerSearch « Nouveau parrain » (joueurs inscrits seulement). Pied : « Annuler » / « Désigner ». Succès : « {nom du parrain} a été prévenu et doit signer la fiche. »
  - « Annuler l'adhésion » : si les frais ont été payés, « Sort du paiement d'adhésion » (SegmentedControl, obligatoire : « Rembourser » / « Conserver ») — le sort est enregistré (4.3) ; aide : « Un paiement validé n'est jamais supprimé : un remboursement passe par une écriture d'annulation. » ; TextArea « Motif » (obligatoire). Pied : « Annuler » / « Annuler l'adhésion » (bouton `danger`) → modale de confirmation dans les deux cas (`ConfirmDialog`, variante action sensible) : « Annuler l'adhésion de {nom} et rembourser les frais ? » si « Rembourser » (annulation d'un paiement), « Annuler l'adhésion de {nom} ? » si « Conserver ». Succès : « Adhésion de {nom} annulée. »
- Point à trancher au Lot 1 avec `finance-engine` : traduction comptable exacte du choix « Rembourser » / « Conserver ».

### 5.6 « Dépense à valider » (4.5.2) — taille `md`

> **Spec détaillée :** `tresorerie-depenses-assistance.md` §3.3. Point d'entrée : notification « Dépense saisie » (4.17) ou liste de la page Dépenses.

### 5.7 « Demande d'assistance de {nom} » — traitement (4.5.3) — taille `md`

> **Spec détaillée :** `tresorerie-depenses-assistance.md` §4.2. Point d'entrée : notification « Demande d'assistance sociale » (4.17) ou liste de la page Assistance. Les décisions ouvertes et leurs conséquences sur l'action d'acceptation sont consignées dans la spec dédiée §9.

## 6. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Barre de progression + squelettes de 4 cartes | — | Chaque carte gère son erreur séparément |
| Communiqués | 2 lignes squelettes | « Aucun communiqué pour l'instant. » + (Pdt, VP, Secrétaire) « Publier un communiqué » | « Impossible de charger les communiqués. » + « Réessayer » |
| Vestiaire du jour | Squelette `pitch` compact | Carte masquée s'il n'y a ni séance ni match aujourd'hui ; si séance sans présent : « Personne n'est encore pointé. » | Idem modèle |
| À faire (*reporté après le Lot 5*) | 3 lignes squelettes | « Rien à faire pour l'instant. » | Idem modèle |
| Ma situation | Squelette KPI | — (toujours une valeur, solde à 0 compris) | Idem modèle |
| Prochain rendez-vous | 1 ligne squelette | « Aucune séance ni aucun match prévu. » + (Coach) « Créer une séance » | Idem modèle |
| Derniers résultats | 3 lignes squelettes | « Aucun match joué pour l'instant. » | Idem modèle |

Succès : toasts listés dans chaque modale.

## 7. Mobile (360 px) et ordinateur

- **360 px** : une colonne, cartes empilées dans l'ordre du §4, marges 12 px. « Ma situation » : solde et statut sur une ligne, échéance et aptitude en dessous. (Après le Lot 5 seulement — Raccourcis : boutons sur une ligne défilante si 3, pas d'empilement pleine largeur.)
- **≥ 1024 px** : deux colonnes 8/4. Colonne principale : Communiqués, Vestiaire du jour, Derniers résultats. Colonne latérale : Ma situation, Prochain rendez-vous. (Après le Lot 5 : « À faire » dans la colonne principale, « Raccourcis » dans la latérale.)

## 8. Décisions par défaut et propositions

- Aucune décision du 10.2 n'est directement engagée par cet écran.
- **Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrées 1 et 2)** : carte « À faire » et carte « Raccourcis ». Décision du client du 25/09/2026 (`docs/lot0/analyse.md` §4). Non développées avant le Lot 5, sauf nouvelle demande suivant le circuit 9.4.
- **Conséquence pour le Lot 1** : la signature de la fiche d'adhésion par le parrain (§5.4) et la décision du Président après un refus ou un silence du parrain (§5.5) sont des actions du MVP (CDC 4.3). Elles s'ouvrent depuis la notification correspondante et depuis la fiche du joueur dans l'Effectif de « Comité et bureau », jamais seulement depuis la carte « À faire ».
- **Proposition** : la photo est demandée par une modale non bloquante (« Plus tard » autorisé), le CDC 4.1 dit « demandée » sans l'imposer.
