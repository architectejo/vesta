# Écran — Espace Superuser

Sources : CDC 1.4 (licences), 2.5, 4.1 (mot de passe oublié), 4.18, 5 (journal, Ghost Mode, surveillance), 7.1, 10.2 n° 1, 2, 14, 19, 20, 21, 26, 35. Composants : `Sidebar` variante Superuser, `DataTable`, `UserSearch`, `ClubSearch`, `docs/lot0/design-system.md`.

## 1. Objectif

Administrer la plateforme : licences et clubs, comptes, support en Ghost Mode, surveillance du journal, paramètres globaux. Espace séparé de l'espace club (2.5).

## 2. Accès

Routes `/admin/*`, réservées aux Superusers. Tout autre compte reçoit « Vous n'avez pas accès à cette action. » et est renvoyé à l'accueil de son club. Pas de fiche joueur, pas de marque blanche : haut de barre latérale « Vesta — Administration ». Le footer est identique aux autres pages.

Navigation (barre latérale) : « Tableau de bord », « Clubs et licences », « Utilisateurs », « Journal d'activité », « Paramètres ».

## 3. Structure des pages

### 3.1 Tableau de bord — `/admin`

**En-tête** : titre « Tableau de bord » ; contexte « Plateforme Vesta · {date du jour} ».

1. **Indicateurs** (4.18) : « Clubs actifs », « Licences à échéance sous 30 jours », « Anomalies en cours ». « Anomalies en cours » est un **nombre calculé en direct** par l'API (voir la carte 4 « Anomalies en cours » ci-dessous), pas un compteur d'éléments stockés.
2. **Demandes de réinitialisation de mot de passe** — ***Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrée 10) — non livrable au MVP***, ni en indicateur, ni en carte. Description conservée pour mémoire : 10 dernières, « Voir plus » : nom, email, club, date ; clic → modale « Utilisateur ». Au MVP, la réinitialisation se fait depuis « Utilisateurs » (§3.3) → modale « Utilisateur » (§4.5), comme prévu au 4.18.
3. **Échéances de licences** — 5 prochaines : club, date de fin, `StatusBadge`. Clic → modale « Club ».
4. **Anomalies en cours** (5.5) — **indicateur calculé en direct**, pas une liste d'éléments stockés : aucune entité « anomalie » n'existe en base. À chaque chargement, l'API évalue les conditions de surveillance à partir du journal d'activité et de la vérification de la chaîne financière, et renvoie celles qui sont **vraies à cet instant**. Une anomalie **disparaît d'elle-même** dès que la condition qui la déclenche n'est plus vraie ; il n'existe donc **aucune action « Fermer », « Traiter » ou « Marquer comme lue »**. Affichage : 5 premières, « Voir plus » (3.3) ; ligne : type (« Échecs de connexion répétés », « Annulations de paiements fréquentes », « Dérogations répétées », « Rupture de la chaîne financière »), club, « depuis le {date du premier événement déclencheur} », badge rouge. Clic → page « Journal d'activité » préfiltrée sur le club, le type d'action et la période des entrées qui déclenchent la condition (lecture seule). Mention sous le titre de la carte (13 px) : « Calculé en direct à partir du journal. Une anomalie disparaît quand sa cause n'est plus présente. »

### 3.2 Clubs et licences — `/admin/clubs`

**En-tête** : titre « Clubs et licences » ; action principale « Attribuer une licence ».

`DataTable` : recherche « Rechercher un club » ; filtres « Statut de licence » (Essai, Active, Expirée, Suspendue, Résiliée), « Date de fin » (plage de dates). Colonnes : Club (figée : logo, nom) · Début · Fin · Statut (`StatusBadge` : « Essai » violet, « Active » vert, « Expirée » orange — « Expirée (grâce) » pendant la période de grâce —, « Suspendue » rouge, « Résiliée » gris) · Joueurs · Dernière activité. **Aucune colonne ni filtre de prix ou de formule** (10.2 n° 20). Tri par défaut : date de fin croissante. Clic → modale « Club ».

### 3.3 Utilisateurs — `/admin/utilisateurs`

`DataTable` : recherche « Nom ou email » ; filtres « Club » (ClubSearch), « Rôle », « État » (Actif, Désactivé, Mot de passe à changer). Colonnes : Utilisateur (figée : avatar, nom) · Identifiant (email) · Club · Rôles · Dernière connexion · État. Clic → modale « Utilisateur ».

### 3.4 Journal d'activité — `/admin/journal` (5.5)

**En-tête** : titre « Journal d'activité » ; action secondaire « Exporter (CSV) ». Mention permanente sous le titre : « Le journal est en ajout seul : aucune entrée ne peut être modifiée ni supprimée. » Aide sous la mention (13 px, 10.2 n° 14 et n° 35) : « Conservation minimale : 5 ans pour les finances, 2 ans pour le reste. Aucune entrée n'est supprimée automatiquement. »

`DataTable` : filtres « Club » (ClubSearch), « Acteur » (UserSearch), « Type d'action » (choix multiple selon 5.2), « Période » (du / au), interrupteur « Alertes seulement ». Colonnes : Horodatage (fuseau du club, UTC en info-bulle) · Club · Acteur (identité réelle ; mention « support » si session de support) · Action · Objet. Tri par défaut : plus récent d'abord. 50 lignes par page. Clic → modale « Entrée du journal ». **Aucun bouton de modification ou de suppression, nulle part** (5.3).

### 3.5 Paramètres — `/admin/parametres` (4.18)

Cartes, chacune avec une action « Modifier » ouvrant une modale :
1. **Engagement solidaire** (1.1) — pourcentage, bénéficiaires, périodicité, montant reversé par an. Valeurs absentes : « À fixer par l'Éditeur. »
2. **Modèles de documents** — fiche d'adhésion, reçu, quitus, procès-verbal : nom, date de dernière modification. Clic → modale d'édition.
3. **Textes des CGU et de la politique de confidentialité** — version en vigueur, date. Action : « Publier une nouvelle version ».

## 4. Modales

### 4.1 « Club » (détail) — taille `lg`

Onglets : « Informations » (logo, nom, ville, pays, devise, Président, nombre de joueurs, dernière activité), « Licence » (date de début, date de fin, statut, jours restants), « Historique de licence » (liste datée des changements, auteur).
Pied : « Fermer » / action principale selon le statut : « Prolonger » (Active, Expirée) ou « Activer » (Essai, Suspendue). Menu « … » : « Suspendre », « Résilier », « Intervenir sur ce club ».

### 4.2 « Attribuer une licence » / « Prolonger la licence » / « Activer la licence » (1.4, 10.2 n° 20) — taille `sm`

Une seule modale simple ; le titre change selon le point d'entrée. **Aucune formule, aucun prix, aucune durée prédéfinie** : une licence est définie uniquement par ses deux dates.

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Club | ClubSearch (prérempli et en lecture seule quand la modale est ouverte depuis le détail d'un club) | Oui | « Choisissez un club. » |
| Date de début | DateField | Oui | « Indiquez la date de début. » Défaut : aujourd'hui ; pour une prolongation, lendemain de la date de fin actuelle |
| Date de fin | DateField | Oui | « Indiquez la date de fin. » ; « La date de fin doit être postérieure à la date de début. » |

Aide sous les dates (13 px) : « La licence est active entre ces deux dates. Après la date de fin, le club dispose de 15 jours de grâce avant de passer en lecture seule. »

Pied : « Annuler » / « Enregistrer ». Succès : « Licence enregistrée pour {club} jusqu'au {date de fin}. »

### 4.3 « Suspendre la licence » / « Résilier la licence » — taille `md`

« Motif » (TextArea, obligatoire). Texte de conséquence :
- Suspension : « Les membres de {club} ne pourront plus accéder à Vesta tant que la licence est suspendue. Ses données restent conservées. » **La suspension n'applique pas le mode lecture seule** : elle bloque l'accès du club ; seule une licence **expirée après la période de grâce** passe en lecture seule (1.4, décidé, cahier des charges 10.2 n° 19).
- Résiliation : « Cette action met fin à la licence de {club}. Ses données restent conservées. »
- Confirmation renforcée pour la résiliation — **Décidé, cahier des charges 10.2 n° 26** : champ « Saisissez le nom du club pour confirmer » (obligatoire, en plus du motif ; comparé au nom renvoyé par l'API, jamais à une valeur écrite en dur) ; le bouton « Résilier » reste désactivé tant que la saisie ne correspond pas. Aide sous le champ si différent : « Le nom saisi ne correspond pas au nom du club. »

Pied : « Annuler » / « Suspendre » ou « Résilier » (danger). Succès : « Licence suspendue. » / « Licence résiliée. »

### 4.4 « Intervenir sur ce club » (4.18, 5.4) — taille `md`

- Texte : « Vous allez agir dans l'espace de {club} pendant 60 minutes au plus. Le club verra vos actions comme « Système Vesta ». Votre identité réelle et ce motif sont enregistrés dans le journal. »
- « Motif de l'intervention » (TextArea, obligatoire) — « Indiquez le motif de l'intervention. »
- Pied : « Annuler » / « Démarrer la session ». Succès : ouverture de l'espace du club.
- **Pendant la session** : `Banner` variante `support`, collant en haut de chaque page : « Session de support — {club} — Motif : {motif} — reste {mm} min » + bouton « Terminer la session ». À 5 minutes de la fin : « La session se termine dans 5 minutes. » À 60 minutes : fin automatique, retour à `/admin`, toast « Session de support terminée. » Le déverrouillage d'une séance (4.7) se fait dans ce cadre.

### 4.5 « Utilisateur » (détail) — taille `md`

Lecture : nom, identifiant (email), club, rôles, état, dernière connexion, date de la dernière demande de réinitialisation.
Pied : « Fermer » / « Réinitialiser le mot de passe » → ConfirmDialog « Réinitialiser le mot de passe de {nom} ? Un mot de passe temporaire sera généré. Il sera valable 48 heures et {nom} devra le changer à sa prochaine connexion. » — « Annuler » / « Réinitialiser ». En cas de succès, la modale « Mot de passe temporaire » (§4.5 bis) s'ouvre à la place du ConfirmDialog.
Menu « … » : « Désactiver le compte » (ConfirmDialog avec « Motif » obligatoire — « Désactiver ») / « Réactiver le compte ».

### 4.5 bis « Mot de passe temporaire » (7.1, 10.2 n° 21) — taille `sm`

Titre : « Mot de passe temporaire de {nom} ».

Corps, dans l'ordre :
1. **Avertissement** (`Banner` orange, en tête, non masquable) : « Ce mot de passe ne sera plus jamais affiché. Copiez-le maintenant et transmettez-le à {nom} par un canal sûr. »
2. **Mot de passe** : les 8 caractères aléatoires générés par l'API, affichés en police à chasse fixe 16 px, espacement de lettres élargi, sans ambiguïté visuelle (caractère sur fond neutre, sélectionnable). À droite : bouton secondaire « Copier » (icône + libellé, 40 px). Après clic : le libellé devient « Copié » pendant 2 secondes et un toast « Mot de passe copié. » s'affiche. Si le presse-papiers est indisponible : toast « Copie impossible. Sélectionnez le mot de passe et copiez-le manuellement. »
3. **Mention** : « Valable 48 heures, le joueur devra le changer à sa prochaine connexion. »
4. Ligne de contexte (13 px) : « Identifiant : {email} · Expire le {date et heure, fuseau du club}. »

Pied : une seule action, « J'ai noté le mot de passe » (principale), qui ferme la modale. **Comportement de fermeture renforcé** : la croix, Échap et le clic extérieur ouvrent un ConfirmDialog « Fermer sans avoir copié le mot de passe ? Il ne pourra plus être affiché ; il faudra en générer un nouveau. » — « Revenir » / « Fermer » (seulement si « Copier » n'a pas été utilisé ; sinon fermeture directe). Le mot de passe n'est jamais conservé dans l'état de l'application après fermeture, ni dans l'URL, ni dans le stockage local ; il n'est pas réaffiché en revenant sur la fiche. Dans la modale « Utilisateur », l'état affiche ensuite « Mot de passe temporaire en attente de changement · expire le {date} ».

Erreur à la génération : le ConfirmDialog reste ouvert avec « La réinitialisation a échoué. Réessayez. » ; aucun mot de passe n'est affiché.

### 4.6 « Entrée du journal » (5.5) — taille `lg`

- Champs : horodatage (fuseau du club et UTC), club, acteur (identité réelle), session de support (motif) le cas échéant, type d'action, objet (type et identifiant), contexte (adresse IP, navigateur, appareil).
- **Comparaison avant / après** : deux colonnes (ordinateur) ou deux blocs successifs (mobile), clés alignées, champs modifiés surlignés en orange. Entrée médicale : « Contenu médical non copié dans le journal. » (5.2).
- Pied : « Fermer ». Aucune autre action.

### 4.7 Paramètres

- **« Engagement solidaire »** : « Pourcentage reversé » (NumberField %), « Bénéficiaires » (TextArea), « Périodicité du reversement » (SegmentedControl : Trimestrielle / Annuelle), « Montant reversé cette année » (MoneyField). Succès : « Engagement solidaire mis à jour. » Ces valeurs ne modifient pas le texte du footer.
- **« Modèle de document »** : éditeur de texte avec champs de fusion listés (ex. {nom du club}, {nom du joueur}, {montant}), aperçu PDF. Aucun nom de club ni mention de l'Éditeur dans les modèles.
- **« Nouvelle version des CGU »** : « Texte » (TextArea), « Date d'entrée en vigueur ». Aide : « Chaque joueur devra accepter la nouvelle version à sa prochaine connexion. »

## 5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Indicateurs | 3 squelettes KPI | Valeurs à 0 | Modèle standard |
| Demandes de réinitialisation (*reporté après le Lot 5*) | 3 lignes | « Aucune demande en attente. » | Modèle standard |
| Échéances | 3 lignes | « Aucune licence n'expire dans les 30 jours. » | Modèle standard |
| Anomalies en cours | 3 lignes | « Aucune anomalie en cours. » | Modèle standard ; le calcul est refait au prochain chargement (« Réessayer ») |
| Clubs | 5 lignes | « Aucun club sur la plateforme. » | Modèle standard |
| Utilisateurs | 5 lignes | « Aucun utilisateur. » ; recherche : « Aucun utilisateur ne correspond à « {saisie} ». » | Modèle standard |
| Journal | 10 lignes | « Aucune entrée pour ces filtres. » + « Effacer les filtres » | Modèle standard |
| Session de support | — | — | « La session n'a pas pu démarrer. Réessayez. » |

## 6. Mobile (360 px) et ordinateur

Usage principal sur ordinateur, mais tout fonctionne à 360 px :
- **360 px** : barre supérieure (menu, « Vesta — Administration », cloche). Tableaux avec première colonne figée et défilement horizontal dans le cadre ; filtres en panneau bas. Comparaison avant/après en blocs successifs. Bandeau de session de support sur deux lignes, bouton « Terminer » toujours visible.
- **≥ 1024 px** : barre latérale fixe ; tableau de bord en deux colonnes (échéances / anomalies).

## 7. Décisions par défaut et points ouverts

- **10.2 n° 1** appliquée : essai de 30 jours, période de grâce de 15 jours (affichées dans le détail de licence et utilisées pour « Expirée (grâce) »).
- **Décidé, cahier des charges 10.2 n° 20 (Q5)** : aucune formule ni tarif au MVP. La carte « Formules de licence », la modale « Formule de licence », le champ « Formule » et la colonne/filtre « Formule » sont supprimés ; une licence = club + date de début + date de fin (§4.2).
- **Décidé, cahier des charges 10.2 n° 21 (Q7)** : réinitialisation par mot de passe temporaire de 8 caractères, affiché une seule fois (§4.5 bis), valable 48 h, changement obligatoire à la connexion suivante.
- **Décidé, cahier des charges 10.2 n° 19 (Q6)** : une licence suspendue bloque l'accès (pas de lecture seule).
- **10.2 n° 2** : pourcentage et bénéficiaires « À fixer par l'Éditeur » ; champs prévus mais vides.
- **10.2 n° 14, précisée par le n° 35 (Q17)** : 5 ans (finances) et 2 ans (autres) sont des durées de **conservation minimale**, sans purge automatique au MVP ; elles motivent un futur archivage, jamais une suppression. Aide affichée sur la page Journal : « Conservation minimale : 5 ans pour les finances, 2 ans pour le reste. Aucune entrée n'est supprimée automatiquement. »
- **Décidé, cahier des charges 10.2 n° 26** : confirmation par saisie du nom du club pour une résiliation, en plus du motif (§4.3).
- **Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrée 10)** : indicateur et carte « Demandes de réinitialisation ». Retirés des indicateurs du MVP ; la réinitialisation reste possible depuis la modale « Utilisateur » (§4.5).
- **Proposition** : « Clubs » et « Licences » (2.5 et 4.18) fusionnés en un seul tableau.
- **Anomalies** : indicateur calculé en direct (aucune entité stockée, aucune action de clôture) ; l'indicateur « Anomalies en cours » remplace le libellé « Anomalies ouvertes » relevé par `cdc-reviewer` comme ajout de confort (circuit 9.4).
