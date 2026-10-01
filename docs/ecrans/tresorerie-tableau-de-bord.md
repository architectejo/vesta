# Écran — Trésorerie : tableau de bord

Sources : CDC 4.4.1 à 4.4.6, 4.4.8, 4.5.2 (blocage), 4.6, 5.3 (gel des écritures), 6.6 (hors connexion), 7.2 (PIN), matrice 2.4, 10.2 n° 22 (session de caisse). Composants : `docs/lot0/design-system.md`.

## 1. Objectif

Donner au trésorier la situation du club en un écran (indicateurs, membres, derniers paiements) et lui permettre d'encaisser vite, y compris au bord du terrain, sans jamais quitter la page.

## 2. Accès

Route `/tresorerie`. Entrée de barre latérale « Trésorerie › Tableau de bord ».

| Rôle | Accès |
| --- | --- |
| Trésorier, Trésorier adjoint | Lecture + enregistrement des paiements, Caisse Terrain Express, import, validation des déclarations |
| Président | Lecture ; création/modification des types de cotisation (É) ; validation des annulations (PIN) |
| Vice-président | Lecture seule |
| Trésorier | Création/modification des types de cotisation (É) ; l'adjoint les voit en lecture |
| Autres rôles | Aucun accès (leur situation est dans « Mon profil ») |

Les boutons non autorisés ne sont pas affichés (et non simplement désactivés).

## 3. Structure de la page

**En-tête** : titre « Trésorerie » ; contexte « {nom du club} · {mois année} ». Action principale (Trés., Adj.) : « Enregistrer un paiement ». Action secondaire : « Caisse Terrain Express ». Menu « … » : « Importer des cotisations (CSV) » (Trés., Adj.), « Grille des cotisations », « Dépenses ».

**Bandeaux** : alerte rouge de blocage des dépenses (4.5.2) « Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée. » + lien « Voir la dépense » ; gel des écritures (5.3) ; lecture seule ; hors connexion ; **session de caisse ouverte** (Trés., Adj., seulement pour l'utilisateur qui l'a ouverte, sur n'importe lequel des appareils où il est connecté, §4.2) : `Banner` vert « Session de caisse ouverte jusqu'à minuit » + bouton « Reprendre la caisse » (ouvre §4.2 directement) + bouton secondaire « Fermer la session ».

Sections :

1. **Indicateurs** (4.4.6) — 4 `KpiTile` : « Encaissé du mois » ({montant}), « Taux de recouvrement » ({n} %), « Total des dettes » ({montant}, texte rouge si > 0), « Caisse disponible » ({montant}, aide : « Encaissements moins dépenses libérées »). Chiffres calculés par l'API.
2. **À valider** (Trés., Adj. ; Président pour les annulations) — visible seulement si non vide. Lignes : avatar, nom, « Déclaration J'ai payé · {montant} · {date} » ou « Annulation demandée · {montant} », badge « À valider ». Clic → modale de validation (§4.5 ou §4.4).
3. **Membres du club** (4.4.6) — `DataTable` : recherche « Rechercher un joueur » ; filtres « Type de cotisation » (choix multiple), « Statut » (En ordre, En dette, En attente, Suspendu, Parti) ; tri par défaut : solde croissant (les dettes en premier). Colonnes : Joueur (figée : avatar 24, nom, n°) · Statut · Type mensuel · Solde (aligné à droite, rouge si négatif) · Dernier paiement (date). 20 lignes par page. Clic → modale « Situation financière ».
4. **Derniers paiements** (4.4.6) — `ListSection` de 20 (3.3) : avatar, nom, type, montant, date, mode, `StatusBadge` (Validé, À valider, Annulé). « Voir plus ». Clic → modale « Détail du paiement ».
5. **Types de cotisation** (4.4.1) — liste des types actifs : nom, nature (texte « Obligatoire » ou « Libre »), montant (« suggéré » pour les libres), périodicité, échéance. Action de carte (Président, Trésorier) : « Nouveau type ». Lien en pied : « Voir les types archivés ». Clic → modale « Type de cotisation ».

Footer.

## 4. Modales

### 4.1 « Enregistrer un paiement » (4.4.3, 4.4.4) — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Joueur | PlayerSearch (portée club, `renderMeta` = solde) | Oui | « Choisissez un joueur. » |
| Type de cotisation | Select (types actifs) | Oui | Défaut : type mensuel du joueur choisi |
| Montant | MoneyField | Oui | « Saisissez un montant supérieur à 0. » |
| Mode | SegmentedControl : Espèces / Mobile money / Lien de paiement | Oui | Défaut : Espèces |
| Référence | TextField | Oui si Mobile money ou Lien de paiement | « Indiquez la référence de la transaction. » |
| Date | DateField | Oui | Défaut : aujourd'hui ; « La date ne peut pas être dans le futur. » |
| Pièce jointe | FileField | Non | Formats standard |

**Aperçu** (calculé par l'API dès que joueur, type et montant sont remplis ; jamais calculé dans l'interface) :
- Tableau « Répartition » : mois · montant affecté · état après paiement (ex. « mars 2026 · 10 $ · Payé »).
- « Solde actuel : {montant} → Nouveau solde : {montant} » et `StatusBadge` du statut après paiement.
- Type libre : « Cotisation libre : ce paiement n'entre pas dans le solde. » (4.4.2).
- Pendant le calcul : squelette de 3 lignes.

Pied : « Annuler » / « Enregistrer » → `PinPrompt` (« Valider le paiement de {montant} pour {nom} »). Succès : toast « Paiement enregistré. Reçu n° {numéro} envoyé à {prénom}. » ; indicateurs, tableau et derniers paiements mis à jour.

Erreurs spécifiques : gel des écritures (message standard) ; « Ce type de cotisation est archivé. »

### 4.2 « Caisse Terrain Express » (4.4.5, 10.2 n° 22) — taille `xl` (plein écran sur mobile)

Conçue pour une main, au soleil, réseau faible.

**Étape préalable obligatoire — ouverture d'une session de caisse.** Au clic sur « Caisse Terrain Express » :
- si l'utilisateur a déjà une session de caisse ouverte et non expirée : la caisse s'ouvre directement ;
- sinon : la modale **« Ouvrir une session de caisse »** (§4.2 bis) s'ouvre d'abord ; la caisse ne s'ouvre qu'après son succès.

**Bandeau de session** (collant en haut du corps de la caisse, sous le titre, toujours visible) : `Banner` vert « Session de caisse ouverte jusqu'à minuit » ; en seconde ligne (13 px) « {n} encaissements · {total} » ; à droite, bouton secondaire « Fermer la session » (facultatif : sans action de l'utilisateur, la session expire d'elle-même à minuit, fuseau du club). Si l'heure du téléphone n'est pas dans le fuseau du club, la seconde ligne ajoute « minuit heure de {fuseau du club} ».

- **Zone 1 — Joueur** : PlayerSearch en haut, focus automatique, clavier numérique proposé par un bouton « 123 » (recherche par numéro). Suggestions avec photo 40 px, nom, numéro, solde et statut.
- **Zone 2 — Carte du joueur choisi** : photo 72 px, nom, « n° {numéro} », « Solde : {montant} », `StatusBadge`, bouton « Changer ».
- **Zone 3 — Encaissement** : « Montant en espèces » (MoneyField, 16 px) ; « Type » (Select, défaut : sa mensuelle). Aperçu de répartition et du nouveau statut (API).
  - *Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrée 7) — non livrable au MVP* : raccourcis de montant en puces « 1 mois ({montant}) », « 2 mois », « 3 mois » calculés sur son type, sous le champ « Montant en espèces ».
- Pied : « Quitter la caisse » / « Encaisser ». **Aucun code PIN n'est demandé à l'encaissement** : la session de caisse ouverte en tient lieu, en ligne comme hors connexion (4.4.5, 10.2 n° 22). Aide sous le pied, la première fois dans la session (13 px) : « Quitter la caisse ne ferme pas la session. »
- **Après succès** (la modale reste ouverte) : encadré vert « {nom} est en ordre. Il peut être composé. » (ou « {nom} reste en dette : {montant}. ») ; bouton « Encaisser pour un autre joueur » (remet à zéro, focus sur la recherche). Le compteur du bandeau de session est mis à jour.
- **Hors connexion** (6.6) : second bandeau orange sous celui de la session : « Hors connexion — les paiements seront envoyés au retour du réseau. » ; recherche dans la liste en cache ; chaque encaissement porte le badge « En attente d'envoi » ; `SyncIndicator` à jour. Les encaissements sont rattachés à l'identifiant de la session de caisse et journalisés avec lui à la synchronisation. **Aucun code PIN n'est stocké sur l'appareil**, ni en clair ni haché ; l'appareil ne garde que l'identifiant et l'heure de fin de la session. Hors connexion, « il peut être composé » ne vaut que sur ce téléphone jusqu'à l'envoi ; l'encadré le précise : « Il pourra être composé dès l'envoi du paiement. »
- **Expiration à minuit** (fuseau du club), la caisse étant ouverte : le bouton « Encaisser » est désactivé, le bandeau de session devient orange « Session de caisse expirée à minuit. Ouvrez une nouvelle session pour continuer. » + bouton « Ouvrir une session » (§4.2 bis, connexion requise). Les encaissements saisis avant minuit et en attente d'envoi restent valides et sont envoyés normalement.
- **« Fermer la session »** : ConfirmDialog « Fermer la session de caisse ? Pour encaisser à nouveau, il faudra ouvrir une nouvelle session avec votre code PIN. » — « Annuler » / « Fermer la session ». Possible hors connexion : la fermeture prend effet immédiatement sur l'appareil et est transmise au serveur au retour du réseau ; les encaissements déjà saisis restent en attente d'envoi. Succès : toast « Session de caisse fermée. » ; la caisse se ferme et le bandeau disparaît de la page Trésorerie.

### 4.2 bis « Ouvrir une session de caisse » (4.4.5, 7.2, 10.2 n° 22) — taille `sm`

Trés., Adj. uniquement. **Connexion requise** : le code PIN est vérifié par le serveur, jamais sur l'appareil.

- Texte : « Vous allez ouvrir une session de caisse valable jusqu'à minuit (heure du club). Pendant cette session, vos encaissements en espèces ne demanderont plus votre code PIN, y compris hors connexion. Ouvrez-la avant d'aller au terrain si le réseau y est faible. »
- Champ « Votre code PIN » (champ PIN 4–6 chiffres du `PinPrompt`, clavier numérique, focus automatique).
- Pied : « Annuler » / « Ouvrir la session ». Bouton en état `loading` « Vérification… » pendant l'appel.
- Succès : toast « Session de caisse ouverte jusqu'à minuit. » ; la modale se ferme et la Caisse Terrain Express s'ouvre avec son bandeau de session.
- Erreurs : PIN incorrect et blocage après échecs répétés = messages standard du `PinPrompt` ; **hors connexion** : bouton « Ouvrir la session » désactivé et `Banner` orange « Connexion requise pour ouvrir une session de caisse. Réessayez quand le réseau revient. » ; gel des écritures (5.3) : message standard.

### 4.3 « Situation financière » — taille `lg`

En-tête : avatar, nom, `StatusBadge`. Corps :
- Résumé : solde, montant dû échu, prochaine échéance.
- Onglets : « Impayés » (mois échus non couverts), « Paiements » (20 + « Voir plus »), « Cotisations libres » (suivi, hors solde), « Grille {année} » (ligne du joueur pour chaque type).
Pied : « Fermer » / (Trés., Adj.) « Enregistrer un paiement » → ouvre §4.1 au niveau 2, joueur prérempli ; au retour, la situation est rafraîchie.

### 4.4 « Détail du paiement » — taille `md`

Champs en lecture : joueur, type, montant, mode, référence, date, pièce jointe (lien sécurisé), saisi par (« Système Vesta » en Ghost Mode), validé le, n° de reçu, répartition par mois. Pied : « Fermer » / « Télécharger le reçu ».
Menu « … » :
- (Trés., Adj.) « Demander l'annulation » → modale niveau 2 : TextArea « Motif de l'annulation » (obligatoire, « Indiquez le motif. »), aide « Le paiement ne sera pas supprimé : une écriture d'annulation sera créée après validation du Président. » ; pied « Annuler » / « Envoyer la demande ». Succès : « Demande d'annulation envoyée au Président. »
- (Président, si annulation demandée) boutons dans le corps : « Refuser » (secondaire) / « Valider l'annulation » (danger → `PinPrompt`). Succès : « Paiement annulé. Le solde de {nom} a été recalculé. »

### 4.5 « Déclaration à valider » (4.6) — taille `md`

Lecture : joueur, type, montant déclaré, référence, capture (aperçu agrandissable), date de déclaration. Pied : « Refuser » (secondaire) / « Valider » (→ aperçu de répartition puis `PinPrompt`). « Refuser » ouvre un niveau 2 : « Motif du refus » (obligatoire), pied « Annuler » / « Refuser la déclaration ». Succès : « Déclaration validée. Reçu envoyé à {prénom}. » / « Déclaration refusée. {prénom} a été prévenu. »

### 4.6 « Type de cotisation » (création / modification, 4.4.1) — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Nom | TextField | Oui | « Ce champ est obligatoire. » ; « Un type porte déjà ce nom. » |
| Nature | SegmentedControl : Obligatoire / Libre | Oui | Aide : « Seule une cotisation obligatoire crée une dette. » |
| Montant (Obligatoire) / Montant suggéré (Libre) | MoneyField | Oui / Non | « Saisissez un montant supérieur à 0. » |
| Périodicité | SegmentedControl : Mensuelle / Annuelle / Ponctuelle | Oui | — |
| Jour d'échéance | NumberField | Oui si Mensuelle ou Annuelle | Défaut : 10 ; « Saisissez un jour entre 1 et 28. » |
| Mois d'échéance | Select (Janvier … Décembre, 12 valeurs fixes) | Oui si Annuelle | Affiché seulement si la périodicité est « Annuelle » ; pas de valeur par défaut ; « Choisissez le mois d'échéance. » Aide : « La cotisation annuelle sera due le {jour} {mois} de chaque année. » |
| Date limite | DateField | Oui si Ponctuelle | « Ce champ est obligatoire. » |
| Frais d'adhésion | Checkbox | — | Aide : « Son paiement fait passer le joueur Inscrit. » |
| Concernés | SegmentedControl : Tous / Liste de joueurs / Joueurs rattachés | Oui | « Liste de joueurs » affiche un PlayerSearch multiple |

En modification d'un montant : encadré orange « Le nouveau montant s'appliquera à partir de {mois communiqué par l'API}. Les mois passés ne changent pas. » (4.4.1).
Pied : « Annuler » / « Enregistrer ». Succès : « Type de cotisation enregistré. »

Détail d'un type (clic dans la liste) : lecture des attributs ; pied « Fermer » / « Modifier » ; menu « … » : « Archiver » (ConfirmDialog « Archiver ce type ? Il ne sera plus proposé pour de nouveaux paiements. » — « Archiver ») ; « Supprimer » affiché **seulement** si l'API indique que le type n'a encore **ni reçu aucun paiement, ni généré aucun montant dû** (ConfirmDialog — « Supprimer »). Dès qu'il existe au moins un paiement **ou** au moins un montant dû sur ce type, il ne peut plus qu'être archivé, jamais supprimé ; « Supprimer » est alors masqué.

### 4.7 « Importer des cotisations » (4.4.8) — assistant `xl`, 3 étapes

1. **Fichier** : « Type de cotisation » (Select, obligatoire), « Année » (NumberField, défaut : année en cours), « Fichier CSV » (FileField `.csv`). Lien « Télécharger le modèle CSV ». Aide : « Une ligne par joueur (email ou nom), une colonne par mois. « ok » = mois payé au montant plein ; un montant = paiement réparti ; vide = rien payé. » Bouton : « Analyser le fichier ».
2. **Aperçu** : `DataTable` variante grille, lecture seule, avec la grille résultante ; lignes en échec surlignées en rouge avec leur message. Résumé : « {n} lignes prêtes · {m} lignes en échec ». Boutons : « Précédent » / « Importer {n} lignes ».
3. **Rapport** : « {n} lignes importées. » et liste des échecs : « Ligne {k} : joueur introuvable », « Ligne {k} : valeur illisible en {mois} ». Bouton « Télécharger le rapport » ; pied « Fermer ».

## 5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Indicateurs | 4 squelettes KPI | Valeurs à 0 (pas de message) | Modèle standard + « Réessayer » |
| À valider | — | Section masquée | Modèle standard |
| Membres du club | 5 lignes squelettes | « Aucun joueur dans le club. » | Modèle standard |
| Derniers paiements | 5 lignes squelettes | « Aucun paiement enregistré pour l'instant. » + (Trés., Adj.) « Enregistrer un paiement » | Modèle standard |
| Types de cotisation | 3 lignes | « Aucun type de cotisation. Créez-en un pour commencer. » + (Pdt, Trés.) « Nouveau type » | Modèle standard |

## 6. Mobile (360 px) et ordinateur

- **360 px** : en-tête avec « Enregistrer un paiement » et « Caisse Terrain Express » côte à côte (36 px). KPI en 2 × 2. Tableau des membres : colonne Joueur figée (120 px), défilement horizontal dans le cadre. Derniers paiements : ligne sur deux niveaux (nom + montant ; type · date + badge).
- **≥ 1024 px** : KPI sur une ligne de 4 ; puis deux colonnes 8/4 : principale « Membres du club », « Derniers paiements » ; latérale « À valider », « Types de cotisation ».

## 7. Décisions par défaut et points ouverts

- **10.2 n° 4** appliquée : jour d'échéance proposé par défaut = 10, sans tolérance.
- **10.2 n° 5** : sans effet direct sur cet écran (mois d'arrivée entier dû : visible dans l'aperçu de répartition calculé par l'API).
- **Point ouvert — écart à la charte** : le CDC 4.4.5 parle d'« écran simplifié » pour la Caisse Terrain Express. Une page réduite à un formulaire est interdite par 3.2 ; elle est donc spécifiée en **modale plein écran**. À valider par le client.
- **Décidé, cahier des charges 10.2 n° 22 (Q16)** : session de caisse ouverte en ligne avec PIN vérifié par le serveur (§4.2 bis), valable jusqu'à minuit (fuseau du club) ; aucun PIN redemandé à chaque encaissement de la Caisse Terrain Express, y compris hors connexion ; aucun PIN stocké sur l'appareil ; encaissements synchronisés et journalisés avec l'identifiant de session. La modale « Enregistrer un paiement » (§4.1), hors Caisse Terrain Express, garde son `PinPrompt` à chaque validation.
- **Portée de la session de caisse** (`docs/lot0/schema-treasury.md` §5.4) : la session est rattachée au club et à l'utilisateur qui l'a ouverte, jamais à un appareil précis — une session par utilisateur, quel que soit l'appareil utilisé pour s'y connecter. Le bandeau de session et « Reprendre la caisse » apparaissent sur chacun de ses appareils connectés ; le Trésorier et l'adjoint peuvent avoir chacun leur propre session le même jour.
- **Encaissement saisi avant minuit, synchronisé après** (`docs/lot0/schema-treasury.md` §5.4) : il est accepté et reste rattaché à sa session, car la condition porte sur l'heure de l'encaissement, pas sur l'heure de la synchronisation. Un encaissement dont l'heure de saisie tombe hors de la validité de la session est refusé et signalé à son auteur dans la file de synchronisation.
- **Point ouvert** : fermeture de session hors connexion (proposition : effet immédiat sur l'appareil, transmission au retour du réseau). À confirmer avec `finance-engine`.
- Hors connexion, « le joueur devient immédiatement sélectionnable » ne vaut que sur le téléphone qui encaisse, jusqu'à l'envoi du paiement.
- **Point ouvert** : circuit de l'annulation. Interprétation retenue du 4.4.4 : le trésorier ou l'adjoint demande l'annulation avec motif, le Président la valide par PIN. À confirmer.
- **Proposition** : motif obligatoire pour le refus d'une déclaration « J'ai payé » ; référence obligatoire pour Mobile money et Lien ; jour d'échéance limité à 1–28 (mois de février). Les raccourcis de montant « 1 / 2 / 3 mois » de la caisse sont reportés après le Lot 5 (`docs/backlog-post-mvp.md`, entrée 7).
