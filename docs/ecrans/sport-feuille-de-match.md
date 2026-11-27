# Écran — Match et feuille de match

Sources : CDC 3 (charte), 4.8, 4.9, 4.11 (plan rattaché), 4.12, 4.13 (équipements), 4.4.5 (régularisation sur place), 4.17, 6.6, 9.2 (critères du Lot 3), 10.2 n° 6, 8, 16, 17, 25 et 38, CLAUDE.md §2.5, matrice 2.4. Composants : `PlayerSearch`, `PitchBoard` (`teams` / `readonly`), `SyncIndicator`, `docs/lot0/design-system.md`. Écrans liés : `sport-seance.md`, `sport-plan-tactique.md`, `sport-vestiaire.md`.

*Révision du 29/09/2026 (tâche 3.1 du Lot 3)* : ajout du §4.1 bis (non-contournement de la composition), de la composition devenue non conforme, du fonctionnement hors connexion de la feuille de match (6.6) et de nouveaux points ouverts. La référence au 10.2 n° 10, désormais caduque, est corrigée (n° 17).

## 1. Objectif

Une page par match qui suit la rencontre de bout en bout : composer, publier, pointer, puis saisir score, buteurs, cartons, blessures et équipements. La page montre toujours l'état du match ; chaque saisie passe par une modale.

## 2. Accès

Route `/matchs/{id}`. Depuis la modale « Match » (espace coach, accueil, page Matchs).

| Rôle | Accès |
| --- | --- |
| Coach | É : composition, publication, score, buts et passes, cartons, blessures, équipements, publication du résultat |
| Capitaine | Pointage et répartition A/B (É), incidents (É), blessure (déclaration) ; reste en lecture |
| Président | Pointage et répartition A/B (É) ; reste en lecture |
| Autres rôles | Lecture ; composition visible **seulement après publication** (4.8) |
| Médecin | Lecture + blessures (É dans le module médical) |

## 3. Structure de la page

**En-tête** : titre « {nom du club} – {adversaire} » (les deux noms viennent de l'API) ; contexte « {Amical} · {Domicile} · {sam. 3 oct. 2026 · 15:00} · {lieu} » ; `StatusBadge` : « Défi en attente » / « Composition brouillon » / « Composition publiée » / « Joué ». **Une seule action principale, selon la phase** (Coach) :

| Phase | Action principale | Secondaire |
| --- | --- | --- |
| Pas de composition | « Composer l'équipe » | — |
| Composition en brouillon | « Publier la composition » | « Modifier la composition » |
| Jour du match | « Ouvrir le pointage » (défile vers la section) | « Modifier la composition » |
| Après le match, sans score | « Saisir le score » | — |
| Score saisi | « Publier le résultat sur le fil » (4.8, une fois) | « Modifier le score » (jour du match seulement) |

Menu « … » (Coach) : « Modifier le match », « Rattacher un plan tactique ».

Sections :

1. **Score** (après le match) — « {nom du club} {3} – {1} {adversaire} » (24 px max., tabular-nums). Dessous, buteurs par minute : « 12' {buteur} (passe : {passeur}) ».
2. **Composition** — état (« Brouillon — visible seulement par le staff » ou « Publiée le {date} ») ; deux listes « Titulaires ({n}) » et « Remplaçants ({m}) » : avatar 32, « n° du jour », nom, poste du jour. Lien « Voir le plan tactique » si un plan **publié** est rattaché (il ouvre la modale « Plan » de `sport-plan-tactique.md` §4.1). Pour le Coach, le lien apparaît aussi quand le plan est en brouillon. Pour un joueur, une mention en haut : « Vous êtes convoqué : titulaire » / « remplaçant » / « Vous n'êtes pas convoqué pour ce match. »
   - **Composition devenue non conforme** (un joueur composé est ensuite passé en dette, a été suspendu, déclaré inapte, etc.) : pour le Coach, la ligne du joueur est grisée avec cadenas et la raison de l'API : « N'est plus sélectionnable : {raison} ». La carte porte en plus un bandeau orange : « {n} joueur(s) de la composition ne peuvent plus jouer. Retirez-les ou attendez leur régularisation. », avec le bouton « Modifier la composition ». Pour les autres joueurs, une composition publiée affiche ce joueur avec le seul badge gris « Indisponible », sans motif (10.2 n° 16).
   - **Publication bloquée tant que la composition compte un joueur non sélectionnable** : c'est une position provisoire (voir le §7). Le bouton « Publier la composition » est désactivé et porte l'aide « Retirez d'abord les joueurs qui ne peuvent plus jouer. »
3. **Pointage** (jour du match, 4.8 « mêmes règles que les séances ») — même composant que la page Séance (`sport-seance.md` §3.1, §3.2, §3.2 bis et §3.2 ter) : compteurs, liste avec « Arrivé », puis équipes A/B si le club les utilise pour le match (point ouvert au §7 : le schéma ne rattache la répartition qu'aux séances). Les règles du retardataire s'appliquent à l'identique (10.2 n° 6, 25 et 38) : il est compté absent par défaut et n'est pas réparti automatiquement. Il reste **composable** : le retard n'exclut pas de la composition, contrairement à la dette, à la suspension, à l'inaptitude et à l'attente d'adhésion (`schema-donnees.md` §5.3).
4. **Buts et passes décisives** (Coach) — liste : minute, buteur, passeur. Action de carte : « Ajouter un but ». Clic → modale « But ».
5. **Cartons et incidents** (4.9) — 5 derniers, « Voir plus » ; action (Coach, Capitaine) « Ajouter un carton » (modale « Signaler un incident », `sport-espace-coach.md` §4.5, match prérempli).
6. **Blessures** (4.12) — liste : joueur, minute, aptitude seule (jamais de diagnostic pour le Coach). Action (Coach, Capitaine, Médecin) : « Déclarer une blessure » (modale `sport-seance.md` §4.3, champ « Moment » remplacé par « Minute »).
7. **Équipements reçus** (4.8, 4.13) — lignes : article, quantité, état « Sorti » (orange) / « Rendu » (vert). Actions (Coach) : « Ajouter des équipements » ; sur une ligne, détail avec « Enregistrer le retour ».

Footer.

## 4. Modales

### 4.1 « Composer l'équipe » (4.8) — taille `lg` (plein écran mobile)

- **Barre haute collante** : recherche « Nom ou numéro » ; puces de poste « Tous », « Gardiens », « Défenseurs », « Milieux », « Attaquants » ; récapitulatif « {n} titulaires · {m} remplaçants ».
- **Liste de tous les joueurs du club** (pas de limite, 4.8). Ligne :
  - case à cocher (zone 44 px), avatar 40, nom, poste habituel ;
  - si cochée, la ligne se déplie : SegmentedControl « Titulaire » / « Remplaçant » (défaut : Titulaire), « Poste du jour » (Select de postes, défaut : poste habituel), « N° du jour » (NumberField, défaut : numéro de maillot) ;
  - **joueur non sélectionnable** : ligne grisée, case désactivée, raison de l'API sous le nom : « Non éligible » (joueur bloqué par une dette : ni montant ni mention de dette pour le Coach, CDC 10.3 n° 188), « Suspendu : encore {n} match(s) », « Inapte · retour prévu le {date} » ou « Inapte · date de retour non fixée » (aptitude et date de retour seulement, jamais de diagnostic, CLAUDE.md règle 11), « En attente d'adhésion ». Pour le Trésorier ou l'adjoint connecté, lien « Encaisser » (ouvre la Caisse Terrain Express au niveau 2, joueur prérempli).
- **Régularisation sur place** (4.8) : l'éligibilité est rafraîchie toutes les 15 s tant que la modale est ouverte ; un joueur régularisé devient cochable, avec toast « {nom} est désormais sélectionnable. »
- Tri : sélectionnables d'abord (par poste puis nom), non sélectionnables ensuite.
- Erreurs : « Le numéro {n} est déjà attribué à {nom} pour ce match. » ; si un joueur devient non sélectionnable entre-temps, l'API refuse et la ligne affiche « {nom} n'est plus sélectionnable : {raison}. »
- Pied : « Annuler » / « Enregistrer ». Succès : « Composition enregistrée (brouillon). »

### 4.1 bis Composition : aucun contournement (CLAUDE.md §2.5, CDC 4.8, critère 9.2 du Lot 3)

Le service de composition fait le contrôle réel : il refuse un joueur en dette, suspendu, inapte ou en attente d'adhésion, avec la raison. Dans la modale, l'interface respecte en plus les règles suivantes :

| Chemin | Comportement exigé |
| --- | --- |
| Case à cocher | Désactivée (`aria-disabled`), zone tactile inerte. La raison reste lisible sous le nom, en 14 px (et non en 13 px, puisque c'est une information critique, 10.2 n° 31). |
| Toucher le reste de la ligne | Le panneau n'est qu'une information : « {nom} ne peut pas être sélectionné : {raison} ». Pour un Coach qui cumule le rôle de Trésorier ou d'adjoint, il porte aussi « Encaisser ». Il ne propose ni « Titulaire » ni « Remplaçant ». |
| Recherche « Nom ou numéro » | Le joueur apparaît quand même, grisé, avec sa raison : on ne le cache pas, pour que le Coach comprenne pourquoi il ne peut pas le cocher. |
| Sélection groupée | Aucune case « Tout cocher » n'est prévue. Si le client en demande une (circuit 9.4), elle ne devra cocher que les joueurs sélectionnables. |
| Joueur devenu non sélectionnable pendant la saisie | Au rafraîchissement de 15 s, la case se décoche et se désactive. Bandeau d'erreur en haut du corps : « {nom} n'est plus sélectionnable : {raison}. Il a été retiré de votre sélection. » L'enregistrement n'est pas bloqué pour les autres joueurs. |
| Enregistrement malgré tout (course entre deux requêtes) | L'API refuse ce joueur. L'erreur s'affiche sur sa ligne et la modale reste ouverte. |
| Hors connexion | « Composer l'équipe » et « Publier la composition » exigent une connexion : la composition n'est pas dans la liste du 6.6. Bouton désactivé avec l'aide « Cette action nécessite une connexion. » |

**Raison affichée dans la modale** : seul le Coach ouvre cette modale (matrice 2.4, « Feuille de match et composition » : É pour le Coach uniquement). Il voit les raisons complètes prévues au 4.8 : « Non éligible » (joueur bloqué par une dette : ni montant ni mention de dette pour le Coach, CDC 10.3 n° 188), « Suspendu : encore {n} match(s) », « Inapte · retour prévu le {date} » ou « Inapte · date de retour non fixée » (aptitude et date de retour seulement, jamais de diagnostic, CLAUDE.md règle 11), « En attente d'adhésion ». Il ne voit jamais de diagnostic (4.12). Le montant de « Non éligible » (joueur bloqué par une dette : ni montant ni mention de dette pour le Coach, CDC 10.3 n° 188) est affiché au format monétaire du club (voir CDC 10.3 n° 188).

**Régularisation sur place** (critère du Lot 3 : « il devient sélectionnable dès son paiement en caisse ») : dès que l'API renvoie le joueur comme sélectionnable, la ligne se dégrise sans fermer la modale et le toast « {nom} est désormais sélectionnable. » s'affiche. Le délai maximal est celui de l'interrogation (15 s). Si la modale est ouverte sur le même téléphone que la Caisse Terrain Express, l'éligibilité est rechargée immédiatement après l'encaissement.

### 4.2 « Publier la composition » — ConfirmDialog

« Publier la composition ? Les {n} joueurs convoqués seront prévenus et pourront la consulter après connexion. » — « Publier ». Succès : « Composition publiée. » (4.17 : notification aux convoqués). Une modification après publication renvoie une notification (proposition, voir §7).

### 4.3 « Saisir le score » — taille `sm`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Buts {nom du club} | NumberField − / + | Oui | 0 à 99 |
| Buts {adversaire} | NumberField − / + | Oui | 0 à 99 |

Aide : « Les buteurs se saisissent ensuite, but par but. » Pied : « Annuler » / « Enregistrer ». Succès : « Score enregistré. » Hors connexion (6.6, « saisie de la feuille de match ») : « Score enregistré sur ce téléphone. Il sera envoyé au retour du réseau. » La saisie en attente apparaît dans `SyncIndicator`. En cas de conflit (le score a été saisi depuis un autre téléphone), c'est la première saisie reçue qui fait foi, et l'autre auteur en est averti par `SyncIndicator`. Si le nombre de buts saisis dans « Buts et passes » diffère du score : avertissement orange sur la page « {n} but(s) du club sans buteur renseigné. »

### 4.4 « Ajouter un but » / « But » (4.8) — taille `md`, fonctionne hors connexion

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Buteur | PlayerSearch (limité aux joueurs de la composition) | Oui | « Choisissez le buteur. » |
| Passeur décisif | PlayerSearch (idem) | Non | « Le passeur doit être différent du buteur. » |
| Minute | NumberField | Non | 0 à 130 |

Succès : « But ajouté. Les statistiques de {nom} sont à jour. » Détail d'un but : pied « Fermer » / « Modifier » ; menu « … » : « Supprimer ce but » (ConfirmDialog « Supprimer ce but ? Les statistiques des joueurs seront recalculées. » — « Supprimer »). Chaque modification est journalisée (4.8) : mention en bas du détail « Modifié par {nom} le {date}. »

### 4.5 « Ajouter des équipements » (4.8, 4.13) — taille `md`

Lignes répétables : « Article » (recherche dans le catalogue du matériel, suggestions ; ce ne sont pas des joueurs), « Quantité » (NumberField ≥ 1). Bouton « Ajouter une ligne » ; icône « Retirer la ligne ». Erreur : « Quantité supérieure au stock disponible ({n}). » Pied : « Annuler » / « Enregistrer ». Succès : « Équipements enregistrés. Sortie ajoutée au registre du matériel. »

Détail d'un équipement : article, quantité, date de sortie ; action « Enregistrer le retour » → « Quantité rendue » (NumberField), « Observation (facultatif) ». Succès : « Retour enregistré. »

### 4.6 « Publier le résultat sur le fil » — ConfirmDialog

« Publier le résultat sur le fil d'actualité ? » + aperçu de la publication (score, buteurs, logo et nom du club). — « Publier ». Succès : « Résultat publié. »

### 4.7 « Modifier le match » — taille `md`

Champs de « Créer un match » (`sport-espace-coach.md` §4.2), adversaire non modifiable pour un défi accepté.

## 5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Squelette en-tête + 3 cartes | — | « Impossible de charger le match. » + « Réessayer » |
| Composition | 6 lignes | Coach : « Aucune composition pour l'instant. » + « Composer l'équipe » ; joueur : « La composition n'est pas encore publiée. » | Modèle standard |
| Buts | 2 lignes | « Aucun but saisi. » + (Coach) « Ajouter un but » | Modèle standard |
| Cartons | 2 lignes | « Aucun incident pour l'instant. » + (Coach, Cap.) « Ajouter un carton » | Modèle standard |
| Blessures | 1 ligne | « Aucune blessure déclarée. » | Modèle standard |
| Équipements | 2 lignes | « Aucun équipement enregistré pour ce match. » + (Coach) « Ajouter des équipements » | Modèle standard |
| Défi en attente | — | Bandeau orange « En attente de la réponse de {club}. » | — |
| Défi refusé | — | Bandeau rouge « {club} a refusé le défi. » | — |
| Verrouillé (lendemain) | Lecture seule, sauf buts et passes modifiables après coup par le Coach (4.8) | — | — |
| Composition non conforme | — | — | Bandeau orange du §3, point 2, et publication désactivée |
| Composition sans aucun joueur sélectionnable | — | Dans la modale, en haut de la liste : « Aucun joueur n'est sélectionnable pour l'instant. » La liste reste affichée, grisée, avec les raisons. | — |
| Saisies de la feuille en attente d'envoi (hors connexion) | — | — | Badge orange « En attente d'envoi » sur chaque ligne concernée (but, carton, score), puis `SyncIndicator` |
| Ajout d'équipements hors connexion | — | — | Bouton désactivé : « Cette action nécessite une connexion. » (le contrôle du stock demande le serveur ; proposition, voir §7) |

## 6. Mobile (360 px) et ordinateur

- **360 px** : sections empilées dans l'ordre du §3 ; avant le match, « Composition » en premier ; le jour même, « Pointage » en premier ; après le match, « Score » en premier. Composition : titulaires et remplaçants en deux listes successives. Modale de composition plein écran, barre de recherche et récapitulatif collants, pied collant au-dessus du clavier.
- **≥ 1024 px** : deux colonnes 8/4. Principale : Score, Composition, Pointage. Latérale : Buts, Cartons, Blessures, Équipements.

## 7. Décisions par défaut et points ouverts

- **10.2 n° 6** : retardataires autorisés à jouer, comptés absents (pointage identique aux séances).
- **10.2 n° 8** : suspensions affichées selon l'API (1 match).
- **10.2 n° 17 (réécrit le 25/09/2026)** : le n° 10 est **caduc**. Il n'y a jamais de club sans Médecin : le Président nomme toujours un joueur à ce rôle (« Médecin / référent santé »). Le Coach ne fixe jamais l'aptitude ; sur cet écran, il voit seulement l'aptitude et la date de retour (CLAUDE.md §2.11). *Corrige la version précédente de cette spec, qui citait le n° 10.*
- **10.2 n° 16** appliquée : un joueur composé devenu non sélectionnable apparaît « Indisponible », sans motif, pour les joueurs qui ne sont pas du staff.
- **10.2 n° 25 et n° 38** appliquées au pointage du match : mêmes règles que la séance (`sport-seance.md` §7).

**Décision du 16/11/2026 (CDC 10.3 n° 180) : score verrouillé après minuit.** Le score n'est plus modifiable après minuit (fuseau du club) : l'API refuse avec 409 et le code `event_locked` (« Ce match est verrouillé depuis minuit : son score ne peut plus être modifié. Seul le support peut le corriger, à la demande du Président. »). Le Superuser en session de support reste autorisé. Les buts et passes restent modifiables après coup (4.8). Le score d'un match joué le jour D se saisit donc jusqu'à minuit le jour D. Si le résultat est déjà publié, toute modification du score (avant minuit) ou d'un but met à jour le post existant (même publication, visibilité « Club »), journalisé `sport.match_result_post_updated`.

**Points ouverts ajoutés le 29/09/2026 (à trancher par le client) :**

1. **Composition publiée contenant un joueur devenu non sélectionnable** : le CDC interdit de composer un tel joueur (4.8, CLAUDE.md §2.5), mais il ne dit pas ce que devient une composition **déjà enregistrée**. Position provisoire, la plus restrictive : le joueur reste dans la composition, marqué « N'est plus sélectionnable », et toute publication ou republication est bloquée tant que le Coach ne l'a pas retiré ou qu'il n'est pas régularisé. Aucun retrait automatique n'a lieu, car l'API ne doit pas modifier une composition sans action du Coach. Autre option possible : retrait automatique, journalisé, avec notification au Coach.
2. **Répartition A/B d'un match** : la matrice 2.4 parle de « Séances et matchs : pointage, répartition A/B », mais `schema-donnees.md` §5.4 (`TeamAssignment`) ne rattache la répartition qu'à une **séance**. À trancher : faut-il des équipes A/B pour un match (par exemple un match interne), ou seulement un pointage ? D'ici là, la section « Pointage » d'un match n'affiche que le pointage, sans terrains A/B. À signaler à `backend-dev`.
3. **Cartons saisis après minuit** : la feuille de match comprend les cartons (4.8), mais le verrouillage à minuit (4.7, `schema-donnees.md` §5.1) bloque aussi l'écriture des incidents. Un match du samedi soir dont la feuille est remplie le dimanche ne pourrait donc plus recevoir ses cartons. Le 4.8 n'autorise la modification « après coup » que pour les buts et les passes. Position provisoire : cartons verrouillés à minuit, comme le prévoit le schéma. Le Coach saisit les cartons le jour même, hors connexion si besoin. À confirmer.
4. **Ajout d'équipements hors connexion** : le 6.6 cite « la saisie de la feuille de match » sans détailler. Proposition : score, buts et passes, cartons et blessures fonctionnent hors connexion ; les équipements exigent une connexion, parce que le stock est contrôlé par le serveur (4.13). À valider.
- **Point ouvert** : faut-il renvoyer une notification aux convoqués si la composition est modifiée après publication ? Proposé : oui, notification « Composition modifiée ».
- **Point ouvert** : qui enregistre le retour des équipements (Coach ou Intendant) ? Le 4.13 parle d'une sortie « puis un retour » sans l'attribuer. Proposé : Coach et Intendant.
- **Proposition** : défaut « Titulaire » au cochage ; rafraîchissement de l'éligibilité toutes les 15 s dans la modale de composition (pas de temps réel, 6.5).
