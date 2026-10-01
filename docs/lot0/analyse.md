# Lot 0 — Analyse de cadrage

Session principale · 25/09/2026 · Réalisé avant tout code applicatif, conformément au Lot 0 (cahier des charges 9.1).

## 0. Vérification des subagents

Les 9 subagents attendus au chapitre 8 de `CLAUDE.md` sont bien présents dans `.claude/agents/` et chargés : `backend-dev`, `cdc-reviewer`, `data-import`, `devops-cpanel`, `finance-engine`, `frontend-dev`, `security-auditor`, `test-engineer`, `ui-designer`. Chacun référence correctement `docs/cahier-des-charges.md` et ses sections de responsabilité (trésorerie exclue de `backend-dev`, lecture seule pour `security-auditor` et `cdc-reviewer`).

## 1. Contradictions et incohérences corrigées ou signalées

### 1.1 Chemin du cahier des charges (corrigé)

Le fichier livré était `docs/cahier_des_charges.md` (tiret bas), alors que `CLAUDE.md` et les 9 subagents référencent tous `docs/cahier-des-charges.md` (tiret). Sans correction, aucun subagent n'aurait pu retrouver le fichier par son chemin documenté. **Correction appliquée** : renommage en `docs/cahier-des-charges.md`. Aucune autre action requise.

### 1.2 Confidentialité médicale — contradiction entre le cahier des charges et CLAUDE.md, **tranchée par le client le 25/09/2026**

- Cahier des charges **2.4**, précisions : « Le Président voit la même chose [que le Coach, seulement l'aptitude], **sauf consentement du joueur pour un accès complet** [au diagnostic]. »
- Cahier des charges **4.12**, confidentialité : « Le diagnostic et le suivi ne sont visibles que par le Médecin et le joueur concerné. » — aucune exception pour le Président n'était mentionnée.
- `CLAUDE.md`, règle non négociable **§2.11** (version initiale) : « Le diagnostic médical n'est visible que par le Médecin et le joueur concerné. Le Coach et le Président ne voient que l'aptitude. » — formulé sans aucune exception.

Une première version de ce document tranchait seule en faveur de `CLAUDE.md`, au nom de la mention « ces instructions OVERRIDE any default behavior ». C'était une erreur, corrigée en cours de Lot 0 : cette mention gouverne le comportement de l'assistant pendant la session, elle ne fait pas de `CLAUDE.md` une source de vérité supérieure au cahier des charges sur une règle métier. `CLAUDE.md` chapitre 1 porte désormais une règle explicite : en cas de contradiction frontale entre les deux documents sur une règle métier, la session documente, retient une position provisoire prudente, et pose la question au client plutôt que de trancher seule.

**Décision du client (25/09/2026, cahier des charges 10.2 n° 15)** : la règle du cahier des charges s'applique, avec consentement du joueur, complétée par quatre précisions :
1. Par défaut, le diagnostic et le suivi ne sont visibles que par le Médecin et le joueur ; le Coach ne voit jamais que l'aptitude et la date de retour, **sans aucune exception**.
2. Le joueur peut donner au Président un accès complet à son dossier médical, depuis son profil, dans une modale.
3. Ce consentement est **révocable à tout moment**, avec effet immédiat.
4. Chaque consentement, chaque révocation et chaque consultation du dossier par le Président sont journalisés (métadonnée seule, jamais le contenu médical).
5. **Précision ajoutée par le client, au-delà de ce que la session avait formulé** : le consentement est donné à la **fonction** de Président, pas à la personne. S'il change de Président, le consentement ne se transfère pas automatiquement au nouveau titulaire — un joueur qui a fait confiance à une personne n'a pas forcément accepté que son successeur lise son dossier. Le nouveau Président devra recueillir un nouveau consentement s'il veut cet accès.

`CLAUDE.md` §2.11 et le cahier des charges (2.4, 4.12) sont désormais alignés sur cette règle. `schema-donnees.md` §6/§6.1 a été corrigé en conséquence par `backend-dev` : consentement révocable, lié à la fonction de Président. **Correction supplémentaire (après relecture `cdc-reviewer`)** : la première version de ce correctif ne vérifiait que le rôle actif de Président, pas la date de la dernière passation — un successeur aurait donc hérité automatiquement du consentement donné à son prédécesseur, à l'exact inverse de la décision du client. Corrigé : l'accès exige désormais que `president_access_granted_at` soit postérieur à la dernière `PresidencyTransfer` du club.

### 1.3 Formules de licence : question ouverte incomplète dans le 10.2, **tranchée par le client le 25/09/2026**

Le 1.4 liste trois questions ouvertes : noms/contenus/prix des formules, durée de l'essai et de la période de grâce, mode de paiement des licences. Seule la durée de l'essai et de la période de grâce est reprise dans le tableau de décisions du **10.2 (n° 1)**. Les deux autres (grille tarifaire des formules, mode de paiement des licences côté Éditeur) n'avaient pas de proposition par défaut dans le cahier des charges.

Une première version de ce document proposait un défaut chiffré (formule unique « Standard », tarification au joueur, paiement hors Vesta). `cdc-reviewer` a relevé à juste titre qu'il s'agissait d'une **règle métier inventée**, non couverte par le 10.2. Une seconde version modélisait une entité `LicencePlan` générique (formules multiples possibles, sans en fixer le nombre ni le tarif) pour ne pas bloquer le schéma en attendant la réponse.

**Décision du client (25/09/2026, cahier des charges 10.2 n° 20)** : encore plus simple que prévu — **aucune formule ni tarif pour l'instant**. Une licence est définie uniquement par une date de début et une date de fin, saisies par le Superuser à chaque attribution ou prolongation. Le cycle de vie reste inchangé (essai → active → expirée avec période de grâce → suspendue → résiliée, 10.2 n° 1 et n° 19). **`LicencePlan` est retiré du schéma** : ajouter des formules plus tard (nom, prix, modules) se fera par une migration additive (nouvelle table + FK facultative sur `Licence`), donc non destructive, conformément à la consigne du client. Voir la délégation à `backend-dev` pour la correction du schéma.

### 1.4 Ligne isolée « Imitation de la blockchain » (7.1)

Le chapitre 7.1 « Authentification » se termine par une ligne isolée « Imitation de la blockchain », sans lien apparent avec l'authentification. Elle fait vraisemblablement écho au chaînage cryptographique des transactions financières du **5.3** (« Les transactions financières sont chaînées... »), mal placée lors de la rédaction. **Aucune règle n'est tirée de cette ligne au 7.1** ; le chaînage financier reste normé exclusivement par le 5.3 et par `finance-engine`. À faire confirmer par le client lors de la prochaine révision du document (incrémenter la version selon le 9.4 si une clarification change le texte).

### 1.5 Granularité des applications Django : AG absente du 6.2

Le 6.2 énumère les domaines d'applications : « comptes, clubs, licences, trésorerie, sport, médical, logistique, mercato, communication, notifications, audit ». Il ne mentionne pas explicitement les assemblées générales (module complet au 4.15) ni ne sépare fil public/chat de « communication ». `CLAUDE.md` (chapitre 5) tranche déjà en créant une app `assemblies` séparée et en scindant `social` (fil public, cartes, mercato public) de `notifications`. Ce n'est pas une contradiction bloquante — c'est une décision d'implémentation cohérente avec le contenu fonctionnel du 4.15 — mais elle mérite d'être actée explicitement : **décision par défaut appliquée** : `assemblies` est une app à part entière ; `communication` du 6.2 se traduit par l'app `social` (fil public, chat, communiqués) déjà prévue dans `CLAUDE.md`.

### 1.6 Règles de discipline « à confirmer » non toutes reprises au 10.2

Le tableau du **4.9** marque quatre règles « à confirmer » : seuil de suspension au cumul de jaunes (5e), durée de suspension au cumul, durée de suspension sur rouge direct, remise à zéro des compteurs en début de saison. Le **10.2 n° 8** ne reprend que les deux durées de suspension, pas le seuil du 5e carton ni la remise à zéro annuelle. **Décision par défaut appliquée pour les quatre lignes** : valeurs du tableau 4.9 telles quelles (5e jaune de la saison, 1 match par cumul, 1 match sur rouge direct, remise à zéro à chaque début de saison), configurables ensuite par club. Signalé pour confirmation explicite par le client avant le Lot 3.

## 1.7 Contradictions relevées par `ui-designer` lors des specs d'écran

En rédigeant les specs (chapitre 3 et modules du 4), `ui-designer` a relevé les contradictions suivantes, non détectées à la première lecture :

- **4.4.5 et 4.10 contredisent 3.2** : le cahier des charges qualifie la Caisse Terrain Express et l'écran d'évaluation rapide d'« écran simplifié » / « un écran liste les joueurs », ce qui suggère une page dédiée à un formulaire — interdite par la règle des boîtes modales (3.2, CLAUDE.md §2.13). **Résolu en faveur de 3.2** : les deux sont spécifiés comme des modales plein écran ouvertes depuis une page de consultation, sans créer de page-formulaire.
- **4.11 (plan tactique) — tranché le 25/09/2026 (10.2 n° 32)** : le tableau noir est un espace d'édition qui vit nécessairement en page (glisser-déposer sur un terrain), pas dans une modale. Le client a validé cette exception à la règle des modales, comme le permet le 3.2 (« Une page dédiée n'est admise que sur justification validée par le client »).
- **4.4.7 contredit 2.4 sur l'accès du Vice-président à la grille des cotisations** : le 4.4.7 réserve le menu au Trésorier, à l'adjoint et au Président ; la matrice 2.4 donne une lecture seule (L) au VP sur « Grille des cotisations ». **Décision par défaut appliquée : la matrice 2.4 prévaut** (le VP a accès en lecture), car c'est elle que `CLAUDE.md` et tous les agents backend citent comme référence des permissions.
- **1.2 contredit 2.4 sur la visibilité du mercato** : le 1.2 range le mercato dans l'« espace public » ; la matrice 2.4 ne donne au simple Joueur qu'un accès à ses propres données (P) sur « Mercato : offres et transferts », donc pas de lecture du marché. **Décision par défaut appliquée : la matrice 2.4 prévaut** (marché visible par Pdt, VP, DS, Trés, Coach uniquement, pas par un Joueur simple ni en public anonyme). À confirmer avec le client car cela restreint la portée « publique » annoncée au 1.2 et au 4.14 (« tableau des joueurs disponibles de tous les clubs »).
- **3.4 (badges de statut) incomplet** : le tableau ne couvre que 5 couleurs pour une douzaine de statuts réels du cahier des charges (Inscrit, Blessé, Apte avec restriction, En retard, Absent excusé, états des dépenses, des licences, des offres de transfert, des AG…). `ui-designer` a proposé une correspondance complète dans `design-system.md` §2.5, marquée « Proposition » et non « règle du cahier des charges ». **À faire valider par le client avant le Lot 1**, car les couleurs de statut sont une règle d'interface non négociable (3.4).

Ces cinq points s'ajoutent aux points 1.1 à 1.6 ci-dessus dans la liste de questions transmise au client en fin de Lot 0.

## 2. Rappel des 14 décisions du 10.2 et valeur par défaut appliquée

Sans réponse du client à la fin du Lot 0, ces propositions par défaut s'appliquent (cahier des charges 10.2) :

| N° | Question | Section | Valeur par défaut appliquée |
| --- | --- | --- | --- |
| 1 | Formules, prix et durée d'essai des licences | 1.4 | Essai gratuit de 30 jours, période de grâce de 15 jours. **Complété au n° 20** (25/09/2026) : aucune formule ni tarif au MVP — mode de paiement des licences reste seul ouvert |
| 2 | Pourcentage reversé aux orphelinats et bénéficiaires | 1.1 | À fixer par l'Éditeur (aucun calcul automatique construit au MVP) |
| 3 | Nombre de titulaires par rôle du bureau | 2.3 | Un seul par rôle. **Complété au n° 24** (25/09/2026) : configurable par club, décision acceptée |
| 4 | Tolérance après échéance avant dette | 4.4.2 | Échéance le 10, sans tolérance supplémentaire (0 jour) |
| 5 | Cotisation du mois d'arrivée et suspension pour absence longue | 4.4.2 | Mois entier dû ; suspension de cotisation sur décision tracée du Président |
| 6 | Un joueur en retard peut-il jouer la séance ? | 4.7 | Oui, mais compté absent dans les statistiques. **Complété au n° 25** (25/09/2026) : configurable par club. **Tension à lever avec le n° 29** (zone « Non répartis »), voir Q21 ci-dessous |
| 7 | Règle de répartition A/B | 4.7 | Alternance selon l'ordre d'arrivée (1er A, 2e B, 3e A…) |
| 8 | Durées de suspension (5e jaune, rouge) | 4.9 | 1 match chacune (voir aussi 1.6 ci-dessus pour le seuil et la remise à zéro) |
| 9 | Grille d'évaluation des joueurs | 4.10 | Note globale sur 10 + 5 critères facultatifs sur 10 |
| 10 | Qui fixe l'aptitude sans Médecin ? | 4.12 | Le Coach |
| 11 | Opposition du club d'origine à un transfert, frais d'adhésion au nouveau club | 4.14 | Pas d'opposition possible si le joueur n'est pas en dette ; frais d'adhésion dus au club B |
| 12 | Liaison WhatsApp par API payante | 4.16 | Hors MVP ; partage par lien simple uniquement |
| 13 | Session propre à chaque onglet | 7.4 | Retenue (jeton en mémoire/`sessionStorage`, pas de partage entre onglets) |
| 14 | Durées de conservation du journal | 5.5 | 5 ans (entrées financières), 2 ans (les autres). **Précisé au n° 35** (25/09/2026) : conservation minimale, sans purge automatique au MVP |

Toutes ces valeurs par défaut sont reprises dans les specs d'écrans et le schéma de données du Lot 0, et devront être confirmées ou modifiées par le client avant le Lot 1 (voir la liste de questions en fin de compte rendu).

## 3. Risques techniques pour l'hébergement cPanel / LiteSpeed

1. **Pas de processus permanent (Passenger)** : toute tâche différée (échéances mensuelles, passage en dette, rappels de licence, vérification quotidienne de la chaîne financière, envoi des emails en file, nettoyage des sessions) doit passer par des commandes de gestion Django déclenchées par cron. Risque : disponibilité et fréquence des cron jobs dépendent de l'offre cPanel du client (souvent limitée à des intervalles de 5 minutes minimum, parfois moins de crons simultanés autorisés). **Mitigation** : documenter précisément la liste et la fréquence minimale nécessaire (6.5) dans `docs/exploitation.md` (livrable de `devops-cpanel`) et vérifier ces quotas avant le Lot 5.
2. **Absence de WebSockets** : chat et notifications reposent sur un polling 10-30 s. Sur un hébergement mutualisé, de nombreux clients en polling simultané (plusieurs dizaines de joueurs un dimanche) peuvent saturer le pool de processus Passenger. **Mitigation** : polling suspendu si l'onglet n'est pas actif (déjà prévu au 6.5), fenêtre de polling large (30 s) par défaut, et vérifier le nombre de processus Passenger alloués par le plan cPanel.
3. **Mode hors connexion (6.6)** : pointage, Caisse Terrain Express, incidents et feuille de match doivent fonctionner sans réseau puis se synchroniser. Risque technique : gestion des conflits (« la première saisie reçue fait foi ») nécessite une horloge fiable côté client (téléphone) et un identifiant local stable par action pour la déduplication à la synchronisation. **Mitigation** : concevoir dès le Lot 3 un identifiant d'action idempotent (UUID côté client) et une file locale IndexedDB dans la PWA.
4. **Base de données** : MySQL/MariaDB imposé (SQLite exclu). Sur cPanel mutualisé, les quotas de connexions simultanées et de taille de base sont souvent limités. **Mitigation** : vérifier le nombre de connexions autorisées et configurer un pool de connexions raisonnable côté Django ; prévoir les index sur les FK `club` de chaque table privée pour que le filtrage tenant-aware reste performant (agrégations de solde sur 500 joueurs, 6.4/`finance-engine`).
5. **Fichiers privés hors `public_html`** : cPanel place généralement le webroot du sous-domaine dans `public_html/<sous-domaine>` ; le stockage privé doit être placé dans un chemin frère hors de cet arbre, accessible en lecture par l'application Python mais jamais servi statiquement par LiteSpeed. **Mitigation** : à valider concrètement lors du premier déploiement (Lot 5), avec un test explicite qu'une URL directe vers un fichier privé renvoie 404/403.
6. **Chaînage cryptographique des transactions (5.3)** : la clé de calcul doit être hors base de données (variable d'environnement). Sur Passenger, un redémarrage de l'application recharge les variables d'environnement depuis la configuration cPanel : **risque de divergence** si la clé change accidentellement entre deux configurations (rupture de chaîne signalée à tort). **Mitigation** : documenter une procédure stricte de gestion de cette clé dans `docs/exploitation.md`, sans rotation sans migration planifiée de la chaîne.
7. **Emails via SMTP de l'hébergement** : les cPanel mutualisés appliquent souvent des quotas d'envoi horaires/journaliers. Avec les reçus, convocations et alertes, ce quota peut être atteint un dimanche de match avec plusieurs paiements. **Mitigation** : les notifications s'enregistrent en base et sont envoyées par une commande cron dédiée (déjà prévu dans `backend-dev.md`), ce qui permet de lisser l'envoi et de respecter un quota horaire.
8. **Génération de PDF côté serveur** (fiches d'adhésion, reçus, quitus, PV) : les bibliothèques de rendu PDF (ex. WeasyPrint) ont des dépendances système (Pango, Cairo) pas toujours installables sur un hébergement mutualisé sans accès root. **Mitigation** : choisir une bibliothèque PDF pure Python (ex. ReportLab) ou vérifier tôt (Lot 2) la disponibilité des dépendances système sur le cPanel cible.

## 4. Liste consolidée des questions Q1–Q20 — **toutes tranchées par le client le 25/09/2026**

Cette liste réunissait les points relevés par la session principale (1.1 à 1.7) et par le contrôle de conformité `cdc-reviewer` de fin de Lot 0. Le client a répondu aux vingt : la colonne « Décision » ci-dessous remplace les anciennes « propositions par défaut » (certaines confirmées telles quelles, d'autres modifiées — voir la colonne « Écart avec la proposition initiale »). Reportées mot pour mot au cahier des charges, chapitre 10.2, entrées 15 à 37.

| N° | Question | Section | Statut | Décision (25/09/2026) | Écart avec la proposition initiale |
| --- | --- | --- | --- | --- | --- |
| Q1 | Consentement du joueur pour donner au Président un accès complet au diagnostic médical | 2.4 vs CLAUDE.md §2.11 | **Décidé** (10.2 n° 15) | La règle du 2.4 s'applique : consentement possible depuis le profil du joueur (modale), révocable à tout moment avec effet immédiat, journalisé (consentement, révocation, chaque consultation), et **attaché à la fonction de Président** — un changement de titulaire ne transfère pas le consentement. Coach : aptitude et date de retour seulement, sans aucune exception. Voir 1.2 ci-dessus et CLAUDE.md §2.11 (corrigé) | La session n'avait proposé aucun défaut ; le client tranche en faveur du 2.4, avec une précision supplémentaire de sa part (consentement lié à la fonction, non transférable à un successeur) que la session n'avait pas anticipée |
| Q2 | Qui voit l'aptitude, y compris les coéquipiers ? | 2.4 vs 4.2 vs 4.14 | **Décidé** (10.2 n° 16) | Proposition par défaut confirmée : Pdt/VP/DS/Coach/Médecin et le joueur voient l'aptitude ; masquée du marché public et des autres clubs. **Précision ajoutée par le client** : les coéquipiers (simples joueurs) ne voient ni l'aptitude ni le motif — seulement « Indisponible » | Défaut confirmé + précision sur les coéquipiers, absente de la proposition initiale |
| Q3 | Sans Médecin, le Coach voit-il le détail clinique ? | 4.12, 10.2 n° 10 | **Décidé, re-tranché le 25/09/2026** (10.2 n° 17, réécrit) | **Remplacé** par la réponse à Q22 (ci-dessous) : il n'y a plus de scénario « sans Médecin » à proprement parler — le Président nomme toujours un joueur au rôle Médecin, même sans qualification médicale (libellé « Médecin / référent santé »), avec les pleins droits du rôle, diagnostic inclus. La décision originale du 10.2 n° 10 (« le Coach fixe l'aptitude ») est **caduque** : elle ne s'applique plus, il n'y a jamais de club sans titulaire du rôle Médecin | Le client écarte l'idée d'un rôle « tiers de confiance » séparé et la question de ce qu'il verrait ; il simplifie en réutilisant le rôle Médecin existant |
| Q4 | Un joueur en dette/suspendu/inapte/en retard en équipe A/B de séance ? | 4.7 | **Décidé, précisé le 25/09/2026** (10.2 n° 29, précisé au n° 38) | Un retardataire est compté absent dans les statistiques, n'est **pas** réparti automatiquement, et arrive dans la zone « Non répartis » — mais, à la différence d'un joueur en dette, suspendu ou inapte (qui restent **impossibles à placer, même manuellement**), le Coach ou le Capitaine **peut le placer manuellement** en équipe A ou B | La proposition initiale groupait retardataire et dette/suspension/inaptitude sans cette distinction placeable/non-placeable ; le client la précise |
| Q5 | Formules et tarifs de licence | 1.4 | **Décidé** (10.2 n° 20) | Aucune formule ni tarif au MVP. Licence = date de début + date de fin saisies par le Superuser. `LicencePlan` retiré du schéma ; ajout futur de formules par migration additive (non destructive) | Va plus loin que la proposition « aucun défaut, schéma générique » : le client simplifie en écartant même la notion de formule pour l'instant |
| Q6 | Licence suspendue = lecture seule ? | 1.4 | **Décidé** (10.2 n° 19) | Proposition par défaut confirmée telle quelle (bloque l'accès, pas de lecture seule) | Aucun |
| Q7 | Réinitialisation du mot de passe | 7.1 | **Décidé** (10.2 n° 21) | **Changé** : mot de passe temporaire aléatoire de 8 caractères, affiché une seule fois au Superuser, valable 48 h, changement obligatoire à la connexion suivante. La création initiale reste mot de passe = email | Contraire à la proposition par défaut (« redevient l'email ») : le client choisit l'option écartée par la session |
| Q8 | Déblocage automatique d'un transfert bloqué pour dette | 4.14 | **Décidé** (10.2 n° 30) | Proposition par défaut confirmée telle quelle | Aucun |
| Q9 | Seuil de quorum d'AG | 4.15 | **Décidé** (10.2 n° 18) | **Précisé** : configurable par club, **50 % par défaut** (la proposition initiale n'avançait aucune valeur plancher) | Valeur chiffrée ajoutée par le client |
| Q10 | Signature du PV si VP vacant | 4.15 | **Décidé** (10.2 n° 28) | Proposition par défaut confirmée telle quelle | Aucun |
| Q11 | Signalement d'une publication | 4.16 | **Décidé** (10.2 n° 23) | **Tranché** : bouton « Signaler » sur chaque publication, accessible à tout joueur, notifie le Superuser et écrit une entrée dans le journal | La session n'avait proposé aucun défaut ; le client choisit l'option « bouton joueur » |
| Q12 | Textes secondaires à 13 px | 3.1 | **Décidé** (10.2 n° 31) | Proposition par défaut confirmée telle quelle | Aucun |
| Q13 | Plan tactique = exception aux boîtes modales | 3.2, 4.11 | **Décidé** (10.2 n° 32) | Proposition par défaut confirmée telle quelle | Aucun |
| Q14 | Assistance sociale : demande envoyable si non éligible ? | 4.5.3 | **Décidé** (10.2 n° 33) | Proposition par défaut confirmée telle quelle | Aucun |
| Q15 | Frais de sortie du club d'origine | 4.14 | **Décidé** (10.2 n° 34) | Proposition par défaut confirmée telle quelle | Aucun |
| Q16 | Vérification du PIN hors connexion (Caisse Terrain Express) | 6.6, 7.2 | **Décidé** (10.2 n° 22) | **Changé** : pas de PIN stocké sur l'appareil. Le Trésorier ouvre une **session de caisse** en ligne (PIN vérifié serveur), valable jusqu'à minuit (fuseau du club) ; les encaissements hors connexion de cette session ne redemandent pas le PIN, synchronisés/journalisés avec l'identifiant de session | Contraire à la proposition par défaut (« PIN haché mis en cache localement ») : le client écarte tout PIN sur l'appareil au profit d'une session serveur |
| Q17 | Portée des durées de conservation du journal | 5.5, 5.3 | **Décidé** (10.2 n° 35) | Proposition par défaut confirmée telle quelle | Aucun |
| Q18 | PIN pour l'annulation d'adhésion avec remboursement | 4.3, 7.2 | **Décidé** (10.2 n° 36) | Proposition par défaut confirmée telle quelle | Aucun |
| Q19 | Assistance sociale non éligible : approbation/libération possible ? | 4.5.1, 4.5.3 | **Décidé** (10.2 n° 37) | Proposition par défaut confirmée telle quelle | Aucun |
| Q20 | Unité du seuil de quorum | 4.15 | **Décidé** (10.2 n° 18, fusionné avec Q9) | Pourcentage des joueurs actifs, confirmé | Aucun |

### Q21 et Q22 — relevées par `cdc-reviewer`, **tranchées par le client le 25/09/2026**

Ces deux points sont apparus **après** le premier tour de réponses (Q1–Q20) : ce n'étaient pas des angles morts du Lot 0, mais une tension entre deux réponses données à des moments différents. La session ne les a pas tranchées seule (voir la règle ajoutée au chapitre 1 de `CLAUDE.md`) ; le client a répondu aux deux.

| N° | Question | Section | Décision (25/09/2026) |
| --- | --- | --- | --- |
| Q21 | Un joueur en retard, compté absent : peut-il jouer normalement, ou reste-t-il dans la zone « Non répartis » jusqu'à régularisation ? | 4.7 | **Décidé** (10.2 n° 38) : il est compté absent dans les statistiques, **n'est pas réparti automatiquement** et arrive dans la zone « Non répartis » — mais, à la différence d'un joueur en dette/suspendu/inapte (qui restent **impossibles à placer, même manuellement**), le Coach ou le Capitaine **peut le placer manuellement** en A ou en B. La zone « Non répartis » distingue donc deux catégories : « placeable manuellement » (retardataire) et « jamais placeable » (dette, suspension, inaptitude, attente d'adhésion). À implémenter au Lot 3 ; `docs/lot0/schema-donnees.md` §5.4 et `docs/ecrans/sport-seance.md` à corriger en conséquence (fait, voir plus bas). |
| Q22 | Le « tiers de confiance non-médecin » (ancien 10.2 n° 17) voit-il le diagnostic qu'il doit lui-même renseigner ? | 4.12 | **Décidé** (10.2 n° 17, réécrit) : **pas de rôle séparé**. Si le club n'a pas de Médecin, le Président nomme un joueur au rôle Médecin lui-même (libellé affiché : « Médecin / référent santé »), avec **exactement les droits du rôle Médecin**, diagnostic inclus pour ce qu'il saisit. La décision originale du 10.2 n° 10 (« le Coach fixe l'aptitude sans Médecin ») devient caduque : il n'y a plus jamais de club sans titulaire du rôle Médecin. Aucune deuxième exception à CLAUDE.md §2.11 : le rôle Médecin reste le seul, quel que soit son titulaire. `docs/lot0/schema-donnees.md` (`ClubSettings.no_doctor_fitness_setter`) et CDC 4.12 à corriger en conséquence (fait, voir plus bas), sans effet sur le Lot 1. |

### Ajouts hors périmètre — décision du client (25/09/2026)

**Acceptés, intégrés au cahier des charges** (10.2 n° 24 à 27) : `late_arrival_counts_absent` et `board_seats_per_role` configurables par club (extensions des n° 6 et n° 3) ; versionnement des CGU avec trace de l'acceptation (n° 27) ; confirmation de résiliation d'une licence par saisie du nom du club (n° 26).

**Reportés après le Lot 5** : toutes les « cartes de confort » relevées par `cdc-reviewer` (cartes « À faire »/raccourcis sur l'accueil, retrait de pointage, réapplication de la répartition automatique, notification de composition modifiée, ligne « Total du mois » de la grille, raccourcis de montant en caisse, retrait d'une offre de mercato, indicateurs « Anomalies »/« Demandes de réinitialisation » présentés comme des actions plutôt que des indicateurs calculés). Liste complète et détaillée dans **`docs/backlog-post-mvp.md`**. Rien de cette liste n'est développé avant le Lot 5, sauf nouvelle demande explicite du client suivant le circuit 9.4.
