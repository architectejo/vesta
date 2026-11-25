# Écrans — Dépenses et assistance sociale

Sources : CDC 3.1 à 3.6, 2.4, 4.4 à 4.6, 4.17, 7.2 (confirmation explicite), 10.2 n° 22, 33 et 37 ; CLAUDE.md §2 (règles 6, 7, 8, 13 à 20) ; `docs/lot0/design-system.md` §1 à 3. Composants : `PageHeader`, `Card`, `ListSection`, `DataTable`, `PlayerSearch`, `StatusBadge`, `Modal`, `ConfirmDialog` (variante action sensible), `FileField`, `MoneyField`, `EmptyState`, `Loader`.

## 1. Objectif et périmètre

Permettre au Trésorier et à son adjoint de saisir et suivre les dépenses du club, et au Président et au Vice-président de les examiner et de prendre les décisions prévues. Permettre aux joueurs de suivre leurs demandes d'assistance depuis leur profil et aux responsables concernés de traiter les demandes reçues.

Le tableau de bord Trésorerie, ses indicateurs et la grille des cotisations restent spécifiés dans `tresorerie-tableau-de-bord.md` et `tresorerie-grille-cotisations.md`. Le formulaire d'envoi d'une demande par un joueur reste dans `comptes-mon-profil.md` §4.3 ; la présente spec couvre la consultation et le traitement des demandes.

## 2. Accès et permissions

Routes proposées : `/tresorerie/depenses` et `/tresorerie/assistance`. Le lien « Dépenses » du menu de la Trésorerie ouvre la première. La cloche et les liens depuis la première page ouvrent le détail concerné. La page Assistance est réservée au traitement des demandes ; le joueur accède à ses propres demandes depuis « Mon profil ».

| Rôle | Dépenses | Catégories | Assistance sociale |
| --- | --- | --- | --- |
| Président | Lecture, traitement et dérogation en cas de blocage | Créer, modifier, archiver | Traiter les demandes selon CDC 4.5.3 ; lecture de ses propres demandes en tant que joueur |
| Vice-président | Lecture et traitement | Lecture seule | Traiter les demandes selon CDC 4.5.3 ; lecture de ses propres demandes en tant que joueur |
| Trésorier | Lecture et saisie | Créer, modifier, archiver | Ses propres demandes uniquement, en tant que joueur |
| Trésorier adjoint | Lecture et saisie | Aucun accès d'écriture | Ses propres demandes uniquement, en tant que joueur |
| Autres joueurs | Aucun accès à la page Dépenses | Aucun accès | Déposer et suivre uniquement ses propres demandes depuis « Mon profil » |
| Superuser | Aucun accès à l'espace club dans cette spec | Aucun accès | Aucun accès |

Les contrôles d'accès sont appliqués côté serveur et toute donnée affichée est limitée au club actif. Les actions non autorisées sont masquées. La portée de consultation des demandes par le Président et le Vice-président reste à confirmer au §9.

## 3. Page « Dépenses »

### 3.1 Structure

En-tête : titre « Dépenses » ; contexte « {nom du club} · {période} ». Action principale (Trésorier, adjoint) : « Saisir une dépense ». Menu « … » (Président, Trésorier) : « Gérer les catégories ».

Bandeau de blocage, uniquement si une dépense est « Non justifiée » : `Banner` rouge « Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée. » ; lien « Voir la dépense » ouvre son détail. Le bandeau de gel des écritures, lecture seule et hors connexion suit les composants communs du tableau de bord Trésorerie.

1. **À traiter** — 20 dernières dépenses en attente, du plus récent au plus ancien, puis « Voir plus » charge les suivantes. Ligne : catégorie, bénéficiaire, montant et devise, date, saisisseur, `StatusBadge` « En attente ». Clic ouvre « Détail de la dépense ».
2. **Dépenses récentes** — 20 dernières dépenses libérées, justifiées, non justifiées ou refusées, puis « Voir plus ». Ligne : catégorie, bénéficiaire, montant, date, statut. Clic ouvre le même détail. Une dépense présente dans « À traiter » n'est pas répétée ici.
3. **Catégories** (Président, Trésorier) — liste des catégories actives : nom, plafond s'il existe, « Justificatif obligatoire » ou « Justificatif facultatif », « Réservée aux membres en ordre » si applicable. Action « Créer une catégorie » ; clic sur une catégorie ouvre son détail et, selon le rôle, « Modifier » ou « Archiver ».

Lorsque l'ensemble des dépenses dépasse 30 éléments, « Voir plus » ouvre une `DataTable` paginée avec recherche « Rechercher une dépense » et filtres « Catégorie », « Statut », « Période » ; colonnes Date · Catégorie · Bénéficiaire · Montant · Saisie par · Statut. Le détail s'ouvre au clic sur la ligne. Les règles de filtre et de pagination ne modifient jamais les droits d'accès.

### 3.2 Modale « Saisir une dépense » — taille `md`

Trésorier et adjoint. Champs :

| Champ | Composant | Règle affichée |
| --- | --- | --- |
| Catégorie | Champ de choix des catégories actives | Afficher le plafond et les options de justificatif et de réservation de la catégorie choisie. |
| Montant | `MoneyField` | Devise du club ; refuser une valeur non positive avec « Saisissez un montant supérieur à 0. » |
| Bénéficiaire | `PlayerSearch` si le bénéficiaire est un joueur | La portée de ce champ (joueur uniquement ou autre bénéficiaire aussi) est à confirmer au §9. Ne pas utiliser de liste déroulante de joueurs. |
| Motif | `TextArea` | Libellé « Motif » ; afficher l'erreur « Ce champ est obligatoire. » si vide. |
| Date | `DateField` | Libellé « Date ». Ne pas présumer de date par défaut. |
| Justificatif | `FileField` | Facultatif à la saisie ; photo ou PDF. |

Pied fixe : « Annuler » / « Enregistrer la dépense ». Si une catégorie exige un justificatif, conserver l'information dans le récapitulatif ; le justificatif reste facultatif au moment de la saisie selon le CDC. Le bouton passe en chargement « Enregistrement… ». Succès : « Dépense enregistrée. » ; la dépense apparaît dans « À traiter » et une notification est envoyée au Président et au Vice-président (4.17). En cas de saisie non enregistrée, fermeture par croix, Échap ou clic extérieur demande confirmation : « Abandonner la saisie ? » — « Continuer la saisie » / « Abandonner ».

### 3.3 Modale « Détail de la dépense » — taille `lg`

En-tête : « Dépense · {catégorie} », montant, `StatusBadge` (« En attente », « Refusée », « Libérée », « Justifiée », « Non justifiée »). Corps en lecture : catégorie, montant, bénéficiaire, motif, date, justificatif (lien privé servi par une vue authentifiée), auteur et date de saisie ; si libérée, date de libération et échéance de justification fournie par l'API ; motif de refus ou de dérogation, s'il y en a un. Aucun justificatif n'est servi depuis un chemin public.

- **En attente** — Président ou VP : « Refuser » / « Valider et libérer ». La validation ouvre une modale de confirmation (`ConfirmDialog`, variante action sensible) : « Libérer cette dépense de {montant} ? » — « Annuler » / « Libérer la dépense ». Succès : « Dépense libérée. Le justificatif est attendu sous {n} jours. »
- **Refuser** — modale niveau 2, `TextArea` « Motif du refus » obligatoire, erreur « Indiquez le motif du refus. » ; pied « Annuler » / « Refuser la dépense ». Succès : « Dépense refusée. {saisisseur} a été prévenu. »
- **Blocage par dépense non justifiée** — afficher le bandeau rouge exact de §3.1 et désactiver « Valider et libérer ». Président seulement : « Libérer par dérogation » ouvre une modale niveau 2 avec `TextArea` « Motif de la dérogation » obligatoire, aide « La dérogation sera journalisée et signalée à la prochaine assemblée générale. », puis modale de confirmation (« Libérer cette dépense de {montant} par dérogation ? » — « Annuler » / « Libérer par dérogation »). Succès : « Dépense libérée par dérogation. »
- **Libérée et justificatif manquant** — Trésorier ou adjoint : « Ajouter le justificatif » ouvre la modale de dépôt ci-dessous. Afficher « À justifier avant le {date} » ou « Délai dépassé le {date} », selon la date calculée par l'API.
- **Justifiée, non justifiée ou refusée** — lecture seule, bouton « Fermer ».

### 3.4 Modale « Ajouter le justificatif » — taille `md`

Ouverte depuis le détail d'une dépense libérée. `FileField` obligatoire, photo ou PDF ; aide « Les photos sont compressées avant l'envoi. » Pied : « Annuler » / « Envoyer le justificatif », état « Envoi… ». Succès : « Justificatif envoyé. » ; le détail affiche le statut fourni par l'API. Si le formulaire est modifié, demander confirmation avant fermeture. La permission de dépôt est à confirmer au §9, le CDC ne la nomme pas distinctement.

### 3.5 Modales « Catégorie de dépense » — taille `md`

Modale de création ou modification, Président et Trésorier uniquement :

| Champ | Composant | Règle affichée |
| --- | --- | --- |
| Nom | `TextField` | Obligatoire ; erreur « Ce champ est obligatoire. » |
| Plafond | `MoneyField` | Facultatif ; devise du club. |
| Justificatif obligatoire | `Checkbox` | Coché par défaut. |
| Réservée aux membres en ordre | `Checkbox` | Pour les dépenses bénéficiant à un joueur, selon CDC 4.5.1. |

Pied : « Annuler » / « Enregistrer ». Succès : « Catégorie enregistrée. » Détail de catégorie : champs en lecture ; pied « Fermer » / « Modifier » ; menu « … » → « Archiver », puis `ConfirmDialog` « Archiver cette catégorie ? » — « Annuler » / « Archiver ». Succès : « Catégorie archivée. » Les règles d'effet d'un plafond et le comportement d'une catégorie déjà utilisée ne sont pas précisés par le CDC ; ne pas ajouter de suppression ni de règle d'archivage implicite.

## 4. Page « Assistance sociale »

### 4.1 Structure

En-tête : titre « Assistance sociale » ; contexte « {nom du club} ». Consultation d'abord, sans formulaire sur la page. Les joueurs déposent une demande depuis « Mon profil » (voir `comptes-mon-profil.md` §4.3) ; les pages de gestion sont destinées au traitement.

1. **À traiter** — 20 dernières demandes non traitées, du plus récent au plus ancien, puis « Voir plus ». Ligne : nom du joueur, événement, date de l'événement, montant prévu, éligibilité, date de réception. Clic ouvre « Demande d'assistance de {nom} ».
2. **Demandes traitées** — 20 dernières demandes dont le traitement est terminé selon le statut transmis par l'API, puis « Voir plus ». Ligne : nom, événement, date, montant, statut. Clic ouvre le même détail.

Au-delà de 30 demandes, « Voir plus » ouvre une `DataTable` paginée avec recherche « Rechercher un joueur » et filtres « Événement », « Statut », « Période » ; colonnes Joueur · Événement · Date de l'événement · Montant prévu · Éligibilité · Statut. Le clic ouvre le détail. La liste agrégée est réservée aux rôles disposant du droit de traitement ; le périmètre exact est à confirmer au §9.

### 4.2 Modale « Demande d'assistance de {nom} » — taille `lg`

Ouverte depuis la liste, la notification « Demande d'assistance sociale » ou « Voir plus » dans la cloche. Consultation sans modification des champs soumis. Corps : nom du joueur ; événement (« Naissance », « Mariage » ou « Décès ») ; date de l'événement ; description ; pièce justificative avec aperçu et téléchargement sécurisé ; date de dépôt ; montant prévu par le barème du club ; délai de traitement fourni par l'API ; éligibilité calculée par l'API à la date de l'événement. Ne pas recalculer montant, délai ou solde dans l'interface.

- Éligible : `StatusBadge` vert « Éligible ».
- Non éligible : `StatusBadge` orange « Non éligible · {montant} à régulariser » et bandeau orange « {prénom} n'était pas en ordre à la date de l'événement ({montant} à régulariser). Vous décidez au cas par cas. » Cette situation n'empêche pas le joueur d'envoyer sa demande (10.2 n° 33).
- Si le joueur est encore en dette au moment où la demande est examinée, la décision 10.2 n° 37 interdit de l'approuver ou de la libérer. Présenter l'état et le montant à régulariser fournis par l'API ; ne pas proposer une dérogation UI.
- Refus : « Refuser » ouvre une modale de niveau 2, `TextArea` « Motif du refus » obligatoire, erreur « Indiquez le motif du refus. » ; pied « Annuler » / « Refuser la demande ». Succès : « Demande refusée. {prénom} a été prévenu. »
- Acceptation : le CDC dit que le Président ou le VP valide et que la demande devient une dépense, mais le circuit de cette dépense restent à arbitrer (§9). Ne pas mettre en production une transition ni un libellé de confirmation qui choisirait une branche avant arbitrage. Selon la décision, l'action primaire sera soit « Accepter la demande » suivie du circuit de dépense défini, soit une action combinée validée par une seule confirmation ; le libellé final et le succès seront fixés après décision.

Toutes les décisions sont soumises à l'API, non optimistes. Le bouton en cours affiche « Enregistrement… ». Toute création, modification ou décision est journalisée selon la règle d'activité append-only. Les accès aux pièces jointes et les consultations suivent l'authentification et les permissions du club.

## 5. États, erreurs et retours

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Liste « À traiter » des dépenses | 5 lignes squelettes | « Aucune dépense à traiter. » | « Impossible de charger les dépenses à traiter. » + « Réessayer » |
| Dépenses récentes | 5 lignes squelettes | « Aucune dépense enregistrée pour l'instant. » + (Trés., Adj.) « Saisir une dépense » | « Impossible de charger les dépenses. » + « Réessayer » |
| Catégories | 3 lignes squelettes | « Aucune catégorie de dépense. » + (Pdt, Trés.) « Créer une catégorie » | « Impossible de charger les catégories. » + « Réessayer » |
| Assistance « À traiter » | 5 lignes squelettes | « Aucune demande d'assistance à traiter. » | « Impossible de charger les demandes d'assistance. » + « Réessayer » |
| Demandes traitées | 5 lignes squelettes | « Aucune demande traitée pour l'instant. » | « Impossible de charger les demandes traitées. » + « Réessayer » |
| Détail | Squelette du contenu et du justificatif | Sans objet | « Impossible de charger ce détail. » + « Réessayer » ; ne pas afficher les données privées en cache si le droit d'accès échoue |
| Toute action | Bouton désactivé avec libellé d'avancement | Sans objet | Erreur API en français, saisie conservée et possibilité de réessayer |

Chaque section échoue indépendamment. Les listes se rafraîchissent après une action réussie. Succès de refus et de libération : messages indiqués dans les modales. Toute alerte de blocage est également visible sur le tableau de bord Trésorerie, qui demeure spécifié dans son propre document.

## 6. Comportement des modales et adaptation mobile

Toutes les modales de formulaire ferment par croix, Échap ou clic extérieur. Si des valeurs ont été modifiées, afficher un `ConfirmDialog` avant abandon : « Abandonner les modifications ? » — « Continuer la saisie » / « Abandonner ». Les boutons « Annuler » et l'action principale restent visibles dans un pied fixe. Les modales de validation utilisent la modale de confirmation (`ConfirmDialog`, variante action sensible) au moment imposé par la décision métier ; aucune confirmation renforcée n'est demandée pour un refus simple. Niveau 2 au-dessus du niveau 1 selon les couches du design system.

- **360 px** : pages en une colonne, marges de 12 px ; titres 20 px ; corps 14 px, texte de lecture et champs 16 px ; boutons 36 px dans les listes et 40 px dans les pieds, cibles tactiles d'au moins 44 px. Lignes compactes sur deux niveaux, montant aligné et badge toujours visible. Les modales de formulaire et de détail passent en plein écran ou panneau bas, avec défilement du corps seulement et pied fixe. Justificatifs ouvrables dans un aperçu ajusté à la largeur ; ne jamais imposer de défilement horizontal à la page.
- **À partir de 640 px** : modales centrées ; largeur `md` ou `lg` du design system.
- **À partir de 1024 px** : contenu limité à la grille 8/4 si la densité le justifie ; formulaire et liste de demandes restent dans leur ordre de lecture. Les tableaux larges défilent dans leur cadre propre.
- Utiliser les trois thèmes `Classic`, `Clair` et `Sombre`, les couleurs fixes de statut du design system, les contrastes plein soleil, le logo et le nom du club fournis par l'API. Le footer est celui de l'application, jamais dupliqué par section.

## 7. Libellés français

- Actions de page : « Saisir une dépense », « Gérer les catégories », « Créer une catégorie », « Voir plus », « Rechercher une dépense », « Rechercher un joueur ».
- États de dépense : « En attente », « Refusée », « Libérée », « Justifiée », « Non justifiée ».
- Assistance : « À traiter », « Demandes traitées », « Éligible », « Non éligible · {montant} à régulariser », « Demande d'assistance sociale ».
- États réseau : « Chargement… », « Réessayer », « Enregistrement… », « Envoi… ».
- Les noms de catégorie, club, personne, montants, dates, délais et motifs sont injectés depuis l'API, jamais écrits en dur.

## 8. Décisions appliquées

- **10.2 n° 33 (Q14)** : la demande peut être envoyée même si le joueur est non éligible ; l'avertissement et le montant à régulariser viennent de l'API. Le formulaire est déjà décrit dans `comptes-mon-profil.md` §4.3.
- **10.2 n° 37 (Q19)** : un joueur qui demeure en dette ne peut pas faire approuver ni libérer sa demande. La page n'offre aucune dérogation à cette règle.
- **10.2 n° 22 (Q16)** : concerne la Caisse Terrain Express ; sans effet direct sur ces écrans.
- Les listes à 20 éléments, puis « Voir plus », et la bascule vers une table filtrable au-delà de 30 sont des choix de présentation cohérents avec les conventions d'écran ; ils ne modifient aucune règle métier.

## 9. Questions ouvertes — ne pas arbitrer dans l'interface

1. **Approbation d'assistance et dépense (club-accueil.md §5.7 / CDC 4.5.3, 4.5.2 et 7.2).** Le CDC dit que le Président ou le VP valide la demande, puis qu'elle devient une dépense ; la validation d'une dépense exige une confirmation explicite. Décider si l'approbation de la demande crée une dépense qui repasse par « Dépense à valider » et requiert une seconde confirmation, ou si l'approbation vaut aussi validation/libération de cette dépense. En attendant, aucun flux de succès d'acceptation n'est réputé décidé.
2. **Éligibilité Q14 et catégorie « réservée aux membres en ordre » (CDC 4.5.1, 4.5.3, 10.2 n° 33 et 37).** Q14 autorise l'envoi et laisse le Président/VP trancher au cas par cas ; Q19 interdit d'approuver ou de libérer si le joueur est encore en dette. Le CDC ne précise pas comment l'option de catégorie réservée aux membres en ordre s'articule avec ces décisions, ni si elle qualifie l'éligibilité à la date de l'événement, à la décision, ou les deux. Ne pas contourner l'interdiction de Q19 ; faire préciser l'effet exact de l'option.
3. **Portée des données d'assistance (matrice 2.4 / CDC 4.5.3 et 4.17).** La matrice marque « Demande d'assistance sociale » P (données propres) pour tous les rôles ; 4.5.3 attribue au Président et au VP la validation des demandes, et 4.17 leur notifie les demandes reçues. Confirmer explicitement que le Président/VP peuvent consulter les demandes d'autres joueurs et leurs justificatifs pour les traiter, et si d'autres données du dossier restent masquées.
4. **Bénéficiaire d'une dépense (CDC 4.5.2).** Le CDC demande un bénéficiaire sans préciser si celui-ci est toujours un joueur ou peut être une personne/fournisseur extérieur ; confirmer le type de saisie avant de figer `PlayerSearch` ou un champ texte.
5. **Dépôt du justificatif après libération (CDC 4.5.2).** Le CDC impose le justificatif pour clôturer la dépense et fixe un délai après libération, mais ne précise pas quel rôle peut téléverser la facture. La proposition d'action Trésorier/adjoint dans §3.4 reste à confirmer.
6. **Plafond de catégorie (CDC 4.5.1).** Son effet lorsqu'une saisie dépasse le plafond n'est pas défini ; afficher le plafond ne suffit pas à décider si la saisie doit être bloquée, avertie ou autorisée.
