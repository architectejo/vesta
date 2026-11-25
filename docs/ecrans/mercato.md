# Écran — Mercato

*Révision du Lot 4 (tâche 4.1, 29/09/2026). Ce document **remplace** `mercato-marche.md` (Lot 0). Changements :*

- *le déblocage automatique est désormais une décision tranchée (10.2 n° 30), et non plus une proposition ;*
- *aucun frais de sortie (10.2 n° 34) ;*
- *l'onglet « Aptitude » est retiré de la fiche publique vue par un autre club ;*
- *un autre club ne voit jamais le montant ni le motif d'un blocage ;*
- *le choix du destinataire est retiré de la messagerie ;*
- *l'écran du blocage et du déblocage est décrit en détail (§5).*

Sources : CDC 1.2, 2.4 (ligne « Mercato : offres et transferts »), 3.1 à 3.6, 4.2 (fiche publique, visibilité), 4.3 (adhésion), 4.6 (Contribuer), 4.14, 4.16 (publication automatique), 4.17, 6.3 (données publiques, club actif), 6.5 (interrogation régulière), 7.2, 9.2 (Lot 4) ; 10.2 n° 11, 16, 30, 31, 34 ; CLAUDE.md §2 (règles 2, 5, 6, 8, 9, 13 à 20) ; `docs/lot0/schema-donnees.md` §8 ; `docs/lot0/design-system.md`. Écrans liés : `comptes-mon-profil.md` §3 point 7 (disponibilité), `sport-feuille-de-match.md` §4.1 bis (convention d'affichage d'un motif de blocage), `club-carte-joueur.md` (fiche détaillée).

Composants : `PageHeader`, `Banner`, `Card`, `ListSection`, `DataTable`, `Tabs`, `StatusBadge`, `Modal`, `ConfirmDialog`, `PlayerSearch` (portée `public`), `ClubSearch`, `SegmentedControl`, `EmptyState`, `Skeleton`, `Toast`. Un seul élément nouveau : `TransferTimeline` (§4.3), une simple liste d'étapes. Pas de nouveau composant de formulaire.

## 1. Objectif

Chaque joueur gère sa disponibilité et répond à ses offres. Les dirigeants cherchent des joueurs dans tous les clubs Vesta, échangent entre clubs et suivent chaque transfert jusqu'au quitus. L'écran montre clairement pourquoi un transfert est bloqué, et le moment où il se débloque tout seul.

## 2. Accès

Route `/mercato`. Entrée « Mercato » (tous les joueurs du club, groupe « Club »).

| Section | Pdt | VP | DS | Trés | Coach | Adj, Int, Cap, Méd | Joueur |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Ma disponibilité, Mes offres | P | P | P | P | P | P | P |
| Marché (consultation, fiche publique) | É | L | É | L | L | — | — |
| Faire une offre | É | — | É | — | — | — | — |
| Offres du club (envoyées et reçues) | É | L | É | L | L | — | — |
| Montant à régulariser d'un de nos joueurs bloqué | L | L | — | L | — | — | P (le sien) |
| Messagerie entre clubs | É | — | É | — | — | — | — |
| Quitus (téléchargement) | Voir §4.3 et point ouvert n° 7 | | | | | | P |

Un joueur qui cumule plusieurs rôles voit l'union de ses droits (2.2). Les droits viennent de l'API ; les actions non autorisées sont masquées.

### 2.1 Étanchéité entre clubs (6.3, CLAUDE.md règle 8)

Le mercato est le seul écran du club qui affiche des données d'**autres clubs**. Règles impératives, contrôlées par `security-auditor` :

1. **Données d'un joueur d'un autre club** : uniquement les champs publics du 4.2, lus par les vues publiques dédiées (6.3). Ce sont : photo, nom, poste, numéro, âge (jamais la date de naissance), ville, club, note moyenne, statistiques sportives, notes d'évaluation, présences, discipline, carrière. **Jamais** : poids, taille, téléphone, email, finances (solde, dette, statut « En ordre » ou « En dette »), santé (aptitude, blessure, « Indisponible »), commentaires d'évaluation.
2. **Un autre club ne voit jamais le montant ni le motif d'un blocage.** Le club offrant voit « Quitus en attente », sans montant et sans le mot « dette » (§5.3).
3. **Identité des autres clubs** : leur nom et leur logo viennent de l'API, ligne par ligne. Ils ne modifient jamais le thème : barre latérale, couleurs Classic et en-tête restent ceux du club connecté. Aucun nom de club n'est écrit dans le code ni dans les textes. Tous les « {club} » ci-dessous sont des variables.
4. **Club actif** : il se déduit de l'adhésion en cours, pour chaque requête (règle 9). Après un transfert, l'interface le relit auprès de l'API (§5.4). Elle ne garde jamais en cache des données du club quitté.
5. **Messagerie** : seuls le Président et le DS des deux clubs d'un fil le lisent (point ouvert n° 5 : le schéma §8.2 prévoit une lecture plus large, à corriger).

## 3. Structure de la page

**En-tête** : titre « Mercato » ; contexte « {nom du club} · Saison {saison} ». Action principale (Président, DS) : « Faire une offre ». Menu « … » (Président, DS) : « Écrire à un club ».

**Bandeaux** (sous l'en-tête) :

1. Lecture seule, hors connexion : modèles standards.
2. **Transfert bloqué**, pour le joueur concerné seulement (§5.2) : `Banner` `danger` « Votre transfert vers {club B} est bloqué : régularisez {montant} auprès de {club A} pour obtenir votre quitus. » Actions : « Contribuer », si le club A a configuré un lien de paiement (4.6), et « Voir l'offre ».

**Sections en cartes, dans l'ordre** :

1. **Ma disponibilité** (tous) — SegmentedControl « Fermé aux offres » / « Sur le marché », à effet immédiat (interrupteur de préférence admis dans une page, design system §1.1). Aide : « Sur le marché, les dirigeants des autres clubs peuvent voir votre fiche publique et vous faire une offre. » Toasts : « Vous êtes maintenant sur le marché. » / « Vous êtes fermé aux offres. » Le même réglage existe dans « Mon profil » ; une seule source côté API.
2. **Mes offres** (tous) — les 5 dernières offres me concernant, puis « Voir plus ». Ligne : logo 24 et nom du club offrant, date, `StatusBadge` (« En attente », « Acceptée », « Refusée », « Bloquée (dette) », « Transfert effectué », « Annulée »). Une offre bloquée porte sous le nom du club, en 14 px : « À régulariser : {montant} ». Clic → modale « Offre reçue » (§4.3).
3. **Marché** (Président, VP, DS, Trésorier, Coach) — `DataTable` (§3.1).
4. **Offres du club** (Président, VP, DS, Trésorier, Coach) — `Tabs` « Envoyées » / « Reçues pour nos joueurs » (§3.2).
5. **Messagerie entre clubs** (Président, DS) — 5 dernières conversations, puis « Voir plus » (§3.3).

Footer.

### 3.1 Marché

- Tableau des joueurs « Sur le marché » de **tous les clubs**, y compris le nôtre (4.14).
- Recherche « Rechercher un joueur ». Filtres (4.14) : « Poste » (cases), « Âge » (plage), « Ville » (texte avec suggestions), « Club » (`ClubSearch`), « Note moyenne » (minimum, 0 à 10).
- Colonnes : **Joueur** (figée : avatar 24, nom) · Poste · Âge · Club (logo 20 + nom) · Ville · Note moyenne (tabular-nums, « — » sans évaluation).
- Tri par défaut : note moyenne décroissante. 20 lignes par page. Filtres et page dans l'URL.
- Les joueurs de notre club portent la mention « Votre club » (13 px, muted) sous le nom et n'offrent aucune action d'offre.
- **Aucun badge de statut** dans ce tableau : pas de situation financière, pas d'aptitude, pas de suspension (§2.1).
- Clic sur une ligne → modale « Fiche publique » (§4.1).

### 3.2 Offres du club

- `Tabs` « Envoyées » (nos offres à des joueurs d'autres clubs) et « Reçues pour nos joueurs » (offres d'autres clubs à nos joueurs). Compteur sur chaque onglet (« Envoyées · 3 »).
- `DataTable` (les transferts peuvent dépasser 30, 3.3) : recherche « Rechercher un joueur » ; filtre « Statut » ; colonnes **Joueur** (figée) · Club (l'autre club : logo + nom) · Date · Statut.
- Statuts affichés selon le côté (§5.3) :
  - onglet « Reçues » (nous sommes le club A) : « En attente », « Acceptée », « Refusée », « Bloquée (dette) », « Transfert effectué », « Annulée » ;
  - onglet « Envoyées » (nous sommes le club B) : même liste, mais « Bloquée (dette) » y devient « Quitus en attente ».
- Tri : date décroissante. Clic → modale « Offre de transfert » (§4.4).

### 3.3 Messagerie entre clubs

- Lignes (5 dernières conversations, puis « Voir plus ») : logo 32 et nom de l'autre club, objet (ou début du dernier message, une ligne, points de suspension), date relative (« il y a 2 h », puis « 28 sept. »), pastille « Non lu » (orange, avec libellé) s'il y a des messages non lus.
- Si la conversation porte sur une offre : puce « Offre · {joueur} » sous l'objet.
- Clic → modale « Conversation » (§4.6). Action de carte : « Écrire à un club » (§4.5).

## 4. Modales

Règles communes : design system §3.2 (fermeture par croix, Échap ou voile ; confirmation d'abandon si la saisie a commencé ; pied fixe ; plein écran sur mobile).

### 4.1 « Fiche publique » — taille `lg`

- En-tête : avatar 72, nom, poste, « {club} » (logo 20 + nom), `StatusBadge` « Sur le marché » (vert).
- Onglets : « Aperçu » (identité publique, radar, forme récente), « Statistiques », « Évaluations » (notes et courbe seulement, **jamais les commentaires**), « Présences », « Discipline », « Carrière ».
- **Pas d'onglet « Aptitude » quand la fiche est vue depuis un autre club** (point ouvert n° 1). Pour un joueur de notre club, la fiche suit `club-carte-joueur.md`.
- Pied : « Fermer » / (Président, DS ; joueur d'un autre club) « Faire une offre » (ouvre §4.2 au niveau 2, joueur prérempli).
- Menu « … » (Président, DS ; joueur d'un autre club) : « Écrire à son club » (ouvre §4.5, club prérempli).

### 4.2 « Faire une offre » (4.14) — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Joueur visé | `PlayerSearch` portée `public`, limitée aux joueurs « Sur le marché » des autres clubs ; ligne de suggestion : avatar, nom, poste, âge et, à droite, logo et nom du club. Prérempli et verrouillé si la modale vient de la fiche publique (bouton « Changer » disponible). | Oui | « Choisissez un joueur. » |
| Message | TextArea | Oui | 1 000 caractères max., compteur ; « Ce champ est obligatoire. » |
| Conditions (facultatif) | TextArea | Non | 1 000 caractères max. ; aide « Par exemple : poste envisagé, date d'arrivée souhaitée. » |

- Les joueurs fermés aux offres n'apparaissent pas dans les suggestions. Aucun badge financier ni médical n'y figure (§2.1).
- **Aucun champ de frais de sortie, ni de montant de transfert** (10.2 n° 34).
- Encadré d'information (fond `--color-surface-muted`, 14 px) :
  > « {prénom du joueur} et son club actuel seront prévenus. S'il accepte, Vesta vérifie qu'il est en ordre auprès de son club actuel : le quitus est alors établi et le transfert se fait automatiquement. Des frais d'adhésion à {nom de notre club} seront dus. Aucun frais de sortie n'est demandé par son club actuel. »
- Pied : « Annuler » / « Envoyer l'offre ».
- Succès : toast « Offre envoyée à {prénom nom}. Son club a été prévenu. » L'offre apparaît dans « Offres du club » › « Envoyées », statut « En attente ».
- Erreurs renvoyées par l'API, affichées dans le bandeau d'erreur de la modale : « {prénom nom} n'est plus sur le marché. » ; tout autre refus avec son message en français. Faut-il interdire deux offres du même club au même joueur ? C'est à trancher (point ouvert n° 8) ; l'interface affiche la réponse de l'API.

### 4.3 « Offre reçue » (le joueur) — taille `md`

- En-tête : « Offre de {club B} » (logo 24) ; sous-titre « Reçue le {date} » ; `StatusBadge` de l'offre.
- Corps :
  1. Message et conditions du club B (texte 16 px), signés « {nom}, {Président / Directeur sportif} de {club B} ».
  2. **Chronologie** (`TransferTimeline`) : liste verticale de 5 étapes, chacune avec pastille (faite : vert plein ; en cours : orange ; bloquée : rouge avec cadenas ; à venir : cercle vide gris), libellé 14 px et date en 13 px :
     1. « Offre reçue » ;
     2. « Votre réponse » (« Acceptée le {date} » / « Refusée le {date} ») ;
     3. « Vérification de votre solde auprès de {club A} » ;
     4. « Quitus » ;
     5. « Transfert effectué ».
     L'étape en cours ou bloquée porte une ligne d'explication (voir le tableau ci-dessous). La pastille n'est jamais la seule information : le libellé et la date sont toujours là.
  3. Rappel : « Des frais d'adhésion à {club B} seront dus. Aucun frais de sortie n'est demandé par {club A}. »

| Statut de l'offre | Contenu propre à l'état | Pied |
| --- | --- | --- |
| En attente | — | « Refuser » (secondaire) / « Accepter » |
| Refusée | « Vous avez refusé cette offre le {date}. » | « Fermer » |
| Acceptée (vérification en cours, état bref) | Étape 3 en orange : « Vérification en cours… » | « Fermer » |
| **Bloquée (dette)** | Encadré rouge (§5.2) | « Fermer » / « Contribuer » (si lien configuré) |
| Transfert effectué | Étapes 1 à 5 vertes et datées ; « Vous avez rejoint {club B} le {date}. » | « Fermer » / « Télécharger le quitus » |
| Annulée | Raison renvoyée par l'API, sinon « Cette offre n'est plus valable. » | « Fermer » |

- « Refuser » → `ConfirmDialog` « Refuser l'offre de {club B} ? » — « {club B} sera prévenu. » — « Annuler » / « Refuser l'offre ». Succès : « Offre refusée. »
- « Accepter » → `ConfirmDialog` « Accepter l'offre de {club B} ? » — texte :
  > « Si vous êtes en ordre auprès de {club A}, votre quitus sera établi et vous rejoindrez {club B} tout de suite. Sinon, le transfert sera bloqué jusqu'à ce que votre solde soit à jour, puis se fera automatiquement, sans nouvelle confirmation de votre part. Des frais d'adhésion à {club B} seront dus ; aucun frais de sortie. »

  Boutons « Annuler » / « Accepter l'offre ».
- **Réponse de l'API après acceptation**. L'interface ne vérifie jamais le solde elle-même : c'est `finance-engine.is_in_good_standing` côté API.
  - Transfert effectué → §5.4 (écran « Bienvenue »).
  - Bloqué → la modale reste ouverte et passe à l'état « Bloquée (dette) », avec l'encadré rouge du §5.2. Pas de toast, l'encadré suffit.
- **Quitus** : « Télécharger le quitus » ouvre le PDF servi par une vue authentifiée (6.7). Le PDF n'est jamais servi depuis un lien public. Il est aux couleurs du club A (émetteur), selon le gabarit de la tâche 4.9.

### 4.4 « Offre de transfert » (dirigeants) — taille `md`

- En-tête : « Offre pour {joueur} » ; sous-titre « {club B} → … » : l'autre club est toujours nommé, logo compris ; `StatusBadge` selon le côté (§5.3).
- Corps : joueur (avatar, nom, poste ; lien « Voir la fiche publique » quand c'est un joueur d'un autre club), message, conditions, auteur de l'offre, date, puis la même `TransferTimeline` que le §4.3. Deux adaptations : l'étape 2 s'appelle « Réponse du joueur » et l'étape 3 « Vérification du solde auprès du club actuel ».
- Contenu propre à l'état **Bloquée**, selon le côté et le rôle : voir §5.3.
- Aucune action d'opposition pour le club A : ni bouton, ni menu (10.2 n° 11).
- Pied : « Fermer ».
- Menu « … » (Président, DS) : « Écrire à {autre club} » (ouvre §4.5, fil lié à l'offre).
- « Retirer l'offre » reste reportée après le Lot 5 (`docs/backlog-post-mvp.md`, entrée 8).

### 4.5 « Écrire à un club » (4.14) — taille `md` (Président, DS)

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Club | `ClubSearch` (tous les clubs Vesta sauf le nôtre : logo, nom, ville) ; prérempli et verrouillé si la modale vient d'une fiche ou d'une offre | Oui | « Choisissez un club. » |
| Objet (facultatif) | TextField | Non | 160 caractères max. |
| Message | TextArea | Oui | 2 000 caractères max. ; « Ce champ est obligatoire. » |

- Information sous le champ Club, une fois le club choisi : « Le Président et le Directeur sportif de {club} recevront votre message. » Si le poste de DS y est vacant : « Le Président de {club} recevra votre message. » (information fournie par l'API).
- Si la modale vient d'une offre : puce en lecture « À propos de l'offre pour {joueur} ».
- Si un fil existe déjà avec ce club, le message y est ajouté, et le succès ouvre ce fil.
- Pied : « Annuler » / « Envoyer ». Succès : « Message envoyé à {club}. »

### 4.6 « Conversation » — taille `md` (plein écran sur mobile)

- En-tête : logo 24 et nom de l'autre club ; sous-titre : objet, ou « Échange entre dirigeants ». Puce « Offre · {joueur} » cliquable si le fil est lié à une offre (ouvre §4.4 au niveau 2).
- Corps : fil des messages, le plus récent en bas. Chaque bulle porte avatar 32, nom, rôle et club (13 px), heure, et texte 14 px. Nos messages sont alignés à droite, fond `--color-surface-muted`. Au-dessus du fil, « Messages précédents » charge les 20 messages plus anciens.
- Zone de réponse collée en bas, à la place du pied : TextArea d'une à quatre lignes (16 px), bouton « Envoyer » de 40 px. Les messages sont en texte seul (le 4.14 ne prévoit pas de pièce jointe).
- Envoi : la bulle apparaît tout de suite avec « Envoi… ». En cas d'échec, elle affiche « Non envoyé. » et le lien « Réessayer ».
- Mise à jour par interrogation toutes les 30 s tant que la modale est ouverte, suspendue si l'onglet n'est pas actif (6.5). À l'ouverture, les messages reçus sont marqués comme lus.
- Fermeture : croix, Échap, voile. Confirmation d'abandon si un brouillon de réponse est saisi.
- Hors connexion : zone de réponse désactivée, « Cette action nécessite une connexion. »

## 5. Blocage et déblocage d'un transfert (4.14, 10.2 n° 30, 9.2 Lot 4)

### 5.1 Déroulé et source de vérité

1. Le joueur accepte (§4.3).
2. L'API appelle `finance-engine.is_in_good_standing` pour son adhésion au club A.
3. Il est en ordre : le quitus est généré, l'adhésion au club A est clôturée, celle au club B est ouverte, et la publication automatique part sur le fil (§5.4).
4. Il n'est pas en ordre : l'offre passe « Bloquée (dette) » et le montant à régulariser vient de l'API (§5.2).
5. **Déblocage automatique (10.2 n° 30)** : dès qu'un paiement validé ramène le solde du joueur à zéro ou au-dessus dans le club A, l'API finalise le transfert, sans nouvelle acceptation du joueur (§5.4).

L'interface n'évalue jamais la dette, le montant ni le moment du déblocage. Elle affiche l'état et le montant renvoyés par l'API, et les relit :

- à chaque ouverture de la page ou d'une modale d'offre ;
- toutes les 30 s tant qu'une modale d'offre bloquée est ouverte ;
- au retour sur l'onglet.

### 5.2 Pendant le blocage : ce que voit le joueur

Même convention que le motif de blocage d'une composition (`sport-feuille-de-match.md` §4.1 bis) : icône cadenas, raison de l'API, 14 px minimum (10.2 n° 31), jamais la couleur seule.

- **Bandeau de page** (Mercato, §3) : « Votre transfert vers {club B} est bloqué : régularisez {montant} auprès de {club A} pour obtenir votre quitus. » Actions « Contribuer » et « Voir l'offre ».
- **Modale « Offre reçue »** : étape 3 de la chronologie en rouge avec cadenas, « Bloquée : En dette : {montant} ». Encadré rouge sous la chronologie :
  > **Transfert bloqué**
  > « Régularisez {montant} auprès de {club A} pour obtenir votre quitus. Le transfert se fera automatiquement dès que votre solde sera à jour : vous n'aurez rien à confirmer. »
  > Ligne 13 px : « Montant mis à jour le {date heure}. »

  Pied : « Fermer » / « Contribuer ». « Contribuer » ouvre le lien de paiement du **club A** dans un nouvel onglet (4.6), ou reste masqué si le club A n'en a pas configuré. Lien secondaire dans le corps : « Voir ma situation financière » (« Mon profil », section Situation financière, où se trouve aussi « J'ai payé »).
- **Mes offres** : badge « Bloquée (dette) » et « À régulariser : {montant} ».
- **Mon profil**, section Mercato : ligne « Transfert vers {club B} bloqué : {montant} à régulariser » + lien « Voir l'offre » (à ajouter à `comptes-mon-profil.md` §3 point 7).
- **Paiement partiel** : le montant affiché baisse à la relecture suivante ; l'offre reste bloquée. L'interface ne calcule pas le reste dû.
- **Déclaration « J'ai payé » en attente** : elle ne débloque rien tant que le Trésorier ne l'a pas validée. Si l'API signale une déclaration en attente, l'encadré ajoute « Votre déclaration de paiement du {date} attend la validation du trésorier. »

### 5.3 Pendant le blocage : ce que voient les dirigeants

| Qui | Badge | Contenu de la modale « Offre de transfert » |
| --- | --- | --- |
| Club A : Président, VP, Trésorier | « Bloquée (dette) » (rouge) | Étape 3 en rouge : « Bloquée : En dette : {montant} ». Texte : « Le transfert se fera automatiquement dès que le solde de {prénom} sera à jour. Le club ne peut pas s'y opposer une fois le solde régularisé. » Lien (Trésorier, Président, VP) : « Voir la situation de {prénom} » (grille des cotisations, ligne du joueur). |
| Club A : DS, Coach | « Bloquée (dette) » (rouge) | Même texte, **sans montant** : « Bloquée : situation financière à régulariser ». Ces rôles n'ont pas accès aux finances (matrice 2.4) ; point ouvert n° 3. |
| Club B : Président, VP, DS, Trésorier, Coach | « Quitus en attente » (orange) | Étape 3 en orange : « En attente du quitus de {club A} ». Texte : « {prénom} a accepté votre offre. Le transfert se fera automatiquement dès que son club actuel pourra établir le quitus. » **Aucun montant, aucune mention de dette** (§2.1 ; point ouvert n° 2). |

### 5.4 Au déblocage (ou à l'acceptation sans dette)

Tout se passe côté serveur, au moment où le paiement est validé (Trésorier, Caisse Terrain Express synchronisée, ou plus tard FlexPaie). Ce qui change à l'écran :

**Pour le joueur**

- Notification (cloche, et email : 4.17, ligne « Offre de transfert ») : titre « Transfert effectué : bienvenue à {club B} » ; corps « Votre solde auprès de {club A} est à jour. Votre quitus a été établi et vous êtes maintenant membre de {club B}. » (texte proposé pour l'annexe E).
- **Changement de club** : à la requête suivante, l'API renvoie un nouveau club actif (règle 9). L'interface :
  1. vide les données en cache du club A (TanStack Query : toutes les requêtes privées) ;
  2. affiche le chargement de page (barre de progression et squelette, jamais d'écran blanc) ;
  3. recharge l'identité du club B (nom, logo, couleurs Classic) ;
  4. mène à l'accueil du club B ;
  5. ouvre une fois la modale `sm` « Bienvenue à {club B} » :
     > « Votre transfert est effectué : vous avez quitté {club A} le {date}. Votre adhésion à {club B} est en attente : des frais d'adhésion de {montant} sont dus pour la finaliser. »

     Pied : « Télécharger le quitus » (secondaire) / « Continuer ». Le montant des frais vient de l'API (type de cotisation « adhésion » du club B).
- Si le joueur est connecté pendant le déblocage avec la modale d'offre ouverte, la relecture de 30 s détecte le changement et déclenche la même transition.
- Au club B, le joueur est « En attente » d'adhésion (4.3) : les écrans du club B l'affichent comme tel et il n'est pas composable tant que l'adhésion n'est pas finalisée (règle 5).

**Pour le club A**

- Le Trésorier qui vient de valider le paiement voit le toast « Paiement validé. Le transfert de {nom} vers {club B} a été effectué automatiquement. » Cela suppose que l'API renvoie cet effet dans sa réponse (à prévoir par `finance-engine`).
- Hors connexion, l'encaissement de la Caisse Terrain Express ne débloque rien sur le téléphone. Le déblocage a lieu quand le paiement arrive au serveur, et le toast vient à la synchronisation.
- Offre : badge « Transfert effectué » (vert), chronologie complète et datée.
- Le joueur passe « Parti » (gris) dans l'effectif. Son historique financier reste au club A.
- Notification au Président et au DS : « Transfert effectué : {nom} rejoint {club B} ».

**Pour le club B**

- Offre : « Quitus en attente » → « Transfert effectué ».
- Notification au Président et au DS : « {nom} a rejoint {club B} » ; corps « Son quitus a été établi. Son adhésion est en attente du paiement des frais d'adhésion. »
- Le joueur apparaît dans l'effectif avec le statut « En attente ».

**Fil public** : publication automatique (4.14 étape 6, 4.16), au nom du club B, sans aucun montant.

## 6. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Barre 3 px + squelette | — | Chaque carte échoue seule |
| Ma disponibilité | Squelette 1 ligne | — | Échec : retour à la valeur précédente + toast « Modification non enregistrée. Réessayez. » |
| Mes offres | 2 lignes | « Aucune offre reçue. » ; précision si fermé aux offres : « Passez « Sur le marché » pour que les autres clubs puissent vous faire une offre. » | Modèle standard |
| Marché | 5 lignes squelettes | « Aucun joueur sur le marché pour l'instant. » ; avec filtres : « Aucun résultat pour ces filtres. » + « Effacer les filtres » | Modèle standard |
| Offres du club | 5 lignes | Envoyées : « Aucune offre envoyée. » + (Pdt, DS) « Faire une offre » ; Reçues : « Aucune offre reçue pour vos joueurs. » | Modèle standard |
| Messagerie | 3 lignes | « Aucune conversation. » + (Pdt, DS) « Écrire à un club » | Modèle standard |
| Conversation | Squelette de 4 bulles | « Aucun message pour l'instant. » | « Impossible de charger la conversation. » + « Réessayer » |
| Offre (modales) | Squelette du corps, titre dès l'ouverture | — | « Impossible de charger cette offre. » + « Réessayer » ; 404 : « Cet élément n'existe plus. » |
| Joueur transféré qui rouvre un ancien lien du club A | — | — | « Vous n'avez pas accès à cette action. » puis redirection vers l'accueil du club actif |
| Club d'un joueur du marché avec une licence expirée ou suspendue | Selon la réponse de l'API (point ouvert n° 9) | — | Message de l'API |
| Hors connexion | — | — | Écriture désactivée (« Cette action nécessite une connexion. ») ; consultation des données déjà chargées |
| Lecture seule (licence expirée) | — | — | Bandeau `readonly` ; offres, disponibilité et messagerie en lecture |

## 7. Mobile (360 px) et ordinateur

- **360 px** :
  - sections empilées dans l'ordre du §3. Pour un joueur sans rôle de dirigeant, la page tient en deux cartes (Ma disponibilité, Mes offres) et le bandeau éventuel ;
  - tableaux avec colonne « Joueur » figée et défilement horizontal dans le cadre ; filtres du marché dans un panneau bas (« Effacer » / « Appliquer ») ;
  - `TransferTimeline` verticale, pastilles de 12 px, libellés sur une ou deux lignes, sans troncature ;
  - Conversation en plein écran, zone de réponse collée au-dessus du clavier (`visualViewport`).
- **≥ 640 px** : modales centrées.
- **≥ 1024 px** : colonne latérale (4) : Ma disponibilité, Mes offres, Messagerie. Colonne principale (8) : Marché, puis Offres du club. Le bandeau « Transfert bloqué » occupe toute la largeur.
- Trois thèmes via variables CSS. Logos des autres clubs en image seulement, sans effet sur les couleurs. Badges aux couleurs fixes, avec libellé.

## 8. Libellés et statuts

Clés de `StatusBadge` : existantes (`transfer_pending` « En attente », `transfer_accepted` « Acceptée », `transfer_refused` « Refusée », `transfer_blocked` « Bloquée (dette) », `transfer_done` « Transfert effectué », `mercato_open`, `mercato_closed`). À ajouter (propositions) :

| Clé | Libellé | Famille | Usage |
| --- | --- | --- | --- |
| `transfer_awaiting_quitus` | Quitus en attente | orange | Vue du club offrant (B) d'une offre bloquée : ne jamais utiliser `transfer_blocked` côté B |
| `transfer_cancelled` | Annulée | gris | Statut `cancelled` du schéma |
| `unread` | Non lu | orange | Conversations |

Le choix de la clé (`transfer_blocked` ou `transfer_awaiting_quitus`) est fait par l'API selon le club de l'utilisateur. L'interface ne choisit pas : elle affiche la clé reçue.

**Notifications** (textes proposés pour l'annexe E ; titre de 40 caractères au plus hors nom de club). Le 4.17 fixe « Offre de transfert : joueur, Président et DS des deux clubs, in-app et email ». Les événements de suivi ci-dessous le prolongent (point ouvert n° 6).

| Événement | Destinataires | Titre | Corps |
| --- | --- | --- | --- |
| Offre envoyée | Joueur | « Offre de transfert de {club B} » | « {club B} vous propose de le rejoindre. Ouvrez l'offre pour l'accepter ou la refuser. » |
| Offre envoyée | Pdt, DS du club A | « Offre de {club B} pour {nom} » | « {club B} a fait une offre de transfert à {nom}. Le joueur décide seul ; aucune action n'est attendue de votre part. » |
| Offre envoyée | Pdt, DS du club B (sauf l'auteur) | « Offre envoyée à {nom} » | « {auteur} a envoyé une offre à {nom} ({club A}). » |
| Offre refusée | Pdt, DS du club B | « {nom} a refusé votre offre » | « {nom} a refusé l'offre de {club B}. » |
| Transfert bloqué | Joueur | « Transfert bloqué : {montant} à régulariser » | « Votre transfert vers {club B} se fera automatiquement dès que votre solde auprès de {club A} sera à jour. » |
| Transfert bloqué | Pdt, DS du club B | « Quitus en attente pour {nom} » | « {nom} a accepté votre offre. Le transfert se fera dès que son club actuel pourra établir le quitus. » |
| Transfert effectué | Joueur ; Pdt, DS des clubs A et B | Voir §5.4 | Voir §5.4 |

Aucun montant n'apparaît dans une notification adressée au club B. Les emails suivent les mêmes règles.

## 9. Décisions appliquées

- **10.2 n° 11** : le club A ne peut pas s'opposer à un transfert sans dette. Aucun bouton d'opposition. Les frais d'adhésion au club B sont dus, et mentionnés dans l'offre, à l'acceptation et à l'arrivée.
- **10.2 n° 30** (tranché le 25/09/2026) : déblocage automatique dès que le solde redevient positif ou nul, sans nouvelle acceptation du joueur. Les textes le disent explicitement (« vous n'aurez rien à confirmer »). Aucun bouton « Confirmer le transfert ».
- **10.2 n° 34** : aucun frais de sortie. Aucun champ de frais ni de montant de transfert. Les textes le rappellent (« aucun frais de sortie »).
- **10.2 n° 16** : aucune information de santé ni d'indisponibilité n'est montrée à un autre club.
- **10.2 n° 31** : montants et motifs de blocage en 14 px ou plus.
- **Quitus** : il vient uniquement de `finance-engine.is_in_good_standing`. Le motif de blocage est affiché selon la même convention que la composition et le plan tactique (raison venant de l'API, cadenas, 14 px).

## 10. Points ouverts à faire trancher par le client

1. **Onglet « Aptitude » de la fiche publique : contradiction interne au 4.2.** La fiche détaillée comporte un onglet « Aptitude (apte, restriction ou inapte, sans diagnostic) », mais le même 4.2 dit que « la santé » n'est « jamais » publique. De plus, le 10.2 n° 16 ne montre qu'« Indisponible » aux coéquipiers eux-mêmes. **Position provisoire, la plus prudente** : pas d'onglet « Aptitude » quand la fiche est vue par un autre club (mercato, comparaison). La spec `mercato-marche.md` du Lot 0, qui l'affichait, est corrigée ici.
2. **Ce que le club offrant sait d'un blocage.** Le 4.14 ne dit pas ce que voit le club B. Position provisoire, la plus prudente : « Quitus en attente », sans montant ni mention de dette. Le club B peut malgré tout en déduire qu'il y a un problème de solde. Faut-il aller plus loin, et ne lui montrer que « Acceptée » jusqu'au transfert ?
3. **Montant du blocage pour le DS et le Coach du club A.** La matrice 2.4 ne leur donne pas accès aux finances, mais le 4.8 montre « En dette : {montant} » au Coach dans la composition. Position provisoire, la plus prudente : pas de montant pour eux dans le mercato. Faut-il aligner l'un sur l'autre ?
4. *(Sans objet : le code PIN est supprimé de l'application, décision du 11/10/2026. L'acceptation d'une offre se fait par confirmation simple.)*
5. **Lecture de la messagerie : écart entre le schéma §8.2 et le 4.14.** Le schéma ouvre la lecture d'un fil à « tous les membres de `club_a` ou `club_b` ». Le 4.14 réserve la messagerie au Président et au DS. Position provisoire, la plus prudente : Président et DS seulement. À corriger dans le schéma et l'API par `backend-dev`. Autre point : le 4.14 dit « écrire au Président ou au DS ». Le schéma n'a pas de destinataire individuel : le fil est de club à club, lu par les deux fonctions. La spec retire donc le choix du destinataire. À confirmer.
6. **Notifications de suivi** (refus, blocage, transfert effectué) et leur canal. Elles ne sont pas listées une à une au 4.17 ; proposition du §8 : même canal que l'offre (in-app et email). Faut-il aussi prévenir le Trésorier du club A d'un blocage ?
7. **Qui télécharge le quitus.** Proposition : le joueur, le Président et le Trésorier du club A (émetteur), le Président et le DS du club B (destinataire). À valider avec le gabarit de la tâche 4.9.
8. **Offres concurrentes.** Un joueur peut-il recevoir plusieurs offres, en accepter une pendant que d'autres sont en attente, ou en accepter une deuxième pendant qu'une première est bloquée ? Que deviennent les autres offres au transfert (« Annulée » ?) ? Un même club peut-il envoyer deux offres au même joueur ? Le 4.14 ne le dit pas. L'interface affiche les actions autorisées par l'API.
9. **Cas limites non couverts par le 4.14.**
   - Un joueur bloqué peut-il retirer son acceptation ?
   - Repasser « Fermé aux offres » annule-t-il une offre acceptée et bloquée ?
   - Que se passe-t-il si le paiement qui a débloqué le transfert est ensuite annulé (règle 4) : le transfert reste-t-il acquis ?
   - Que se passe-t-il si la licence du club B est expirée ou suspendue au moment du déblocage ?
10. **Parrainage à l'arrivée au club B.** Le schéma §8.1 prévoit une adhésion au club B « sans parrainage requis », en renvoyant à une question mercato non tranchée. Le 4.3 exige un parrain pour toute adhésion. L'écran « Bienvenue » (§5.4) ne parle que des frais d'adhésion en attendant.
11. **Accès des simples joueurs au Marché.** Le 1.2 range le mercato dans l'espace public ; la matrice 2.4 donne au Joueur « P » (ses propres données). Défaut maintenu : la matrice fait foi, et le tableau du Marché n'est visible que par le Président, le VP, le DS, le Trésorier et le Coach.
