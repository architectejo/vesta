# Annexe E — Textes des notifications et emails

Cahier des charges 10.1 (Annexe E) et 4.17. Ce document fixe le **texte validé**
(titre et corps) de chaque notification émise par le Lot 1. Il est complété à
chaque lot, au fur et à mesure que les autres lignes du tableau 4.17 sont câblées
(trésorerie, sport, médical, mercato, AG).

**Portée Lot 1 : 5 lignes du tableau 4.17, soit 6 textes** (la ligne « Refus du
parrain, ou silence après 7 jours » recouvre deux événements distincts dans le
code).

**Règle de synchronisation.** Chaque texte renvoie à la fonction backend qui le
produit. Le texte de ce document est la cible validée ; tant que la colonne
« État du code » indique un écart, c'est à `backend-dev` d'aligner le code, puis
à `test-engineer` d'ajouter un test qui vérifie la chaîne exacte. Une fois
l'écart résorbé, toute modification d'un texte passe par ce document **et** par
le code dans le même commit ; un écart constaté plus tard est un défaut à
corriger, pas une tolérance.

## 0. Règles communes à tous les textes

1. **Français correctement accentué.** Tous les textes et libellés actuels du
   backend sont écrits sans accents (« Vous avez ete nomme », « adhesion »,
   « President »). Ce n'est pas acceptable dans un texte visible par un joueur
   (CLAUDE.md règle 20). Les fichiers Python sont en UTF-8 : les chaînes
   affichées doivent porter leurs accents. Les commentaires et docstrings ne
   sont pas concernés.
2. **Titre explicite passé par l'appelant.** Le titre affiché sous la cloche (et
   l'objet de l'email) est passé explicitement via le paramètre `title=` de
   `create_notification` pour chacun des 6 textes ci-dessous. Le libellé de
   `Notification.EventType` reste un nom de catégorie (fidèle au tableau 4.17)
   et ne sert que de valeur de repli ; il doit néanmoins être accentué, puisque
   ce repli peut s'afficher (voir §7).
3. **Titre court** : 40 caractères au plus hors nom de club, lisible en une
   ligne sur un écran de 360 px. **Corps** : une à trois phrases, le fait
   d'abord, l'action attendue ensuite.
4. **Aucun identifiant technique** (`event_type`, code de rôle, identifiant
   numérique) dans un texte. Les rôles s'affichent par leur libellé.
5. **Marque blanche** : le nom du club vient toujours de `club.name`. « Vesta »
   désigne le produit et peut apparaître ; « IMARA TECH Group » n'apparaît
   jamais dans une notification ni dans un email (CLAUDE.md règle 19).
6. **Guillemets français** « … » avec une espace normale autour du contenu ;
   deux-points précédés d'une espace normale. (Point clarifié à la tâche 1.14 :
   aucun texte validé du §8 ni aucun code livré n'utilise d'espace insécable ;
   ce document n'en exige donc plus, pour rester cohérent avec ce qui est
   réellement implémenté — une espace normale suffit pour un texte affiché en
   français dans ce produit.)
7. Aucun texte ne promet une action que le code ne permet pas réellement
   (voir §3.2).

### Variables utilisées

| Variable | Source dans le code |
| --- | --- |
| `{recrue}` | `_recruit_full_name(application)` — prénom et nom du joueur en attente d'adhésion |
| `{parrain}` | prénom et nom de `application.membership.sponsor.user` |
| `{motif}` | `application.sponsor_refused_reason` (obligatoire, déjà nettoyé par `refuse_sponsor_application`) |
| `{rôle}` | libellé **effectif** du rôle (voir §4, point sur le Médecin) |
| `{club}` | `club.name` |
| `{jours}` | `days_remaining` dans `process_licence_reminders` (valeurs possibles : 30, 7, 1) |
| `{date}` | `licence.end_date` au format `JJ/MM/AAAA` |
| `{grâce}` | `licence.grace_period_days` |

## 1. Fiche d'adhésion à signer

| | |
| --- | --- |
| Ligne 4.17 | « Fiche d'adhésion à signer » — Parrain — In-app |
| Déclencheur réel | Première notification au parrain désigné (CDC 4.3 étape 4), ou au nouveau parrain après `reassign_sponsor` |
| Code | `backend/apps/clubs/services.py`, `notify_sponsor` (branche `is_reminder` faux), `event_type=MEMBERSHIP_SIGNATURE_PENDING` |
| Canal | In-app seulement |
| État du code | **Conforme** (depuis la tâche 1.7 ; vérifié caractère par caractère à la tâche 1.14) |

**Texte validé**

- Titre : `Fiche d'adhésion à signer`
- Corps : `{recrue} attend votre parrainage. Ouvrez sa fiche d'adhésion pour la signer avec votre code PIN, ou pour refuser en indiquant un motif.`

Justification : le parrain doit savoir qu'il peut refuser (le code le permet,
`refuse_sponsor_application`, motif obligatoire) ; sans cette mention, un parrain
réticent laisse la notification sans suite et le dossier part en rappel puis en
alerte au Président. La tournure « attend votre parrainage » évite tout accord
en genre et ne prétend pas savoir qui a choisi le parrain (la personne qui ajoute
le joueur, `add_player_with_sponsor`, ou le Président, `reassign_sponsor`).

## 2. Rappel au parrain sans réponse (3 jours)

| | |
| --- | --- |
| Ligne 4.17 | « Rappel au parrain sans réponse (3 jours) » — Parrain — In-app |
| Déclencheur réel | `process_sponsor_reminders_and_alerts` : dossier toujours en attente, `sponsor_notified_at` vieux d'au moins 3 jours, un seul rappel par dossier |
| Code | `backend/apps/clubs/services.py`, `notify_sponsor` (branche `is_reminder` vrai), `event_type=SPONSOR_REMINDER` |
| Canal | In-app seulement |
| État du code | **Conforme** (depuis la tâche 1.7 ; vérifié caractère par caractère à la tâche 1.14) |

**Texte validé**

- Titre : `Rappel : fiche d'adhésion à signer`
- Corps : `La fiche d'adhésion de {recrue} attend votre réponse depuis 3 jours. Signez-la avec votre code PIN, ou refusez en indiquant un motif.`

« Depuis 3 jours » est fidèle au seuil du code (`SPONSOR_REMINDER_DELAY`). Le
mot « Rappel » passe dans le titre, le corps n'a plus à le répéter.

## 3. Refus du parrain, ou silence après 7 jours (Président)

### 3.1 Refus explicite du parrain

| | |
| --- | --- |
| Ligne 4.17 | « Refus du parrain, ou silence après 7 jours » — Président — In-app |
| Déclencheur réel | `refuse_sponsor_application` (motif obligatoire) → `notify_president_of_sponsor_refusal` ; omis si le club n'a aucun Président en poste |
| Code | `backend/apps/clubs/services.py`, `notify_president_of_sponsor_refusal`, `event_type=SPONSOR_REFUSED` |
| Canal | In-app seulement |
| État du code | **Conforme** (depuis la tâche 1.7 ; vérifié caractère par caractère à la tâche 1.14) |

**Texte validé**

- Titre : `Parrainage refusé`
- Corps : `{parrain} a refusé de parrainer {recrue}. Motif : « {motif} ». Désignez un autre parrain ou annulez l'adhésion.`

Les deux actions citées existent réellement pour un dossier refusé
(`reassign_sponsor`, `cancel_membership_application`) : le texte reste fidèle
au code et au CDC 4.3.

### 3.2 Silence du parrain après 7 jours

| | |
| --- | --- |
| Ligne 4.17 | même ligne que 3.1 |
| Déclencheur réel | `process_sponsor_reminders_and_alerts` : dossier toujours en attente, `sponsor_notified_at` vieux d'au moins 7 jours, une seule alerte par dossier ; omis sans Président en poste |
| Code | `backend/apps/clubs/services.py`, `notify_president_of_no_response`, `event_type=SPONSOR_ALERT_PRESIDENT` |
| Canal | In-app seulement |
| État du code | **Conforme** (corrigé à la tâche 1.7 ; vérifié caractère par caractère à la tâche 1.14) |

Historique (résolu) : le texte promettait initialement au Président deux
actions que le code refusait tant que le dossier n'était pas « refusé ».
Problème (désormais corrigé) : dans ce cas, le dossier est toujours « en attente » (pas « refusé »).
Or `reassign_sponsor` et `cancel_membership_application` exigent tous deux
`sponsor_decision == REFUSED` et lèvent une erreur sinon. Le Président qui suit
la notification se heurte donc à un refus. Le CDC 4.3 prévoit seulement « alerte
au Président après 7 jours », sans dire ce que le Président peut faire ensuite
(voir point ouvert n° 2).

**Texte validé (fidèle au code actuel)**

- Titre : `Parrain sans réponse`
- Corps : `{parrain} n'a toujours pas signé la fiche d'adhésion de {recrue}, 7 jours après l'avoir reçue. Un rappel lui a déjà été envoyé.`

« Un rappel lui a déjà été envoyé » est exact : le rappel à 3 jours part
toujours avant l'alerte à 7 jours dans le même traitement. Le nom du parrain est
ajouté : le Président doit savoir qui relancer. Si le client décide que le
Président peut agir dès le silence (point ouvert n° 2), ajouter alors
` Désignez un autre parrain ou annulez l'adhésion.` à la fin du corps, en même
temps que la modification du code.

## 4. Nomination ou révocation

| | |
| --- | --- |
| Ligne 4.17 | « Nomination ou révocation » — Joueur concerné — In-app |
| Déclencheur réel | Nomination ou révocation d'un rôle du bureau, du Capitaine, et passation de présidence (l'ancien Président reçoit la révocation, le nouveau la nomination) |
| Code | `backend/apps/clubs/services.py`, `notify_role_change`, `event_type=ROLE_APPOINTED_OR_REVOKED` |
| Canal | In-app seulement |
| État du code | **Conforme** (depuis la tâche 1.7 ; vérifié caractère par caractère à la tâche 1.14) |

**Texte validé — nomination** (`event == "appointed"`)

- Titre : `Nouveau rôle`
- Corps : `Vous avez désormais le rôle « {rôle} » au sein de {club}.`

**Texte validé — révocation** (`event == "revoked"`)

- Titre : `Fin de rôle`
- Corps : `Vous n'avez plus le rôle « {rôle} » au sein de {club}.`

Justification : la tournure « le rôle « … » » évite tout accord en genre
(nommé / nommée) et reste correcte quel que soit le libellé, y compris
« Joueur autorisé à ajouter des joueurs ». « Au sein de {club} » évite « au club
Loisirs Club Discovery ».

`{rôle}` doit être le **libellé effectif** (`get_effective_role_label`,
CDC 10.2 n° 17) : un Médecin non qualifié doit lire « Médecin / référent
santé », pas « Médecin ». Aujourd'hui `notify_role_change` utilise
`MembershipRole.Role(role).label`. Libellés des rôles à accentuer dans
`MembershipRole.Role` : Président, Vice-président, Trésorier, Trésorier adjoint,
Médecin, Joueur autorisé à ajouter des joueurs.

## 5. Licence proche de l'expiration

| | |
| --- | --- |
| Ligne 4.17 | « Licence proche de l'expiration » — Président — In-app, email |
| Déclencheur réel | `process_licence_reminders` : licence en essai ou active, exactement 30, 7 ou 1 jour avant `end_date`, une fois par palier ; omis sans Président en poste |
| Code | `backend/apps/licences/services.py`, `process_licence_reminders`, `event_type=LICENCE_EXPIRING` |
| Canal | In-app **et** email (si le Président a laissé l'email activé, `NotificationPreference`) |
| État du code | **Conforme** (depuis la tâche 1.7 ; vérifié caractère par caractère à la tâche 1.14, y compris le cas `{grâce}` = 1, voir plus bas) |

**Le texte varie selon le palier** : un « 30 jours » est une information, un
« demain » est une urgence. Le titre porte le délai pour que le Président le
lise sans ouvrir la notification, et pour que l'objet de l'email soit explicite.

**Licence active** (`licence.status == ACTIVE`)

| `{jours}` | Titre | Corps |
| --- | --- | --- |
| 30 | `{club} : licence à renouveler dans 30 jours` | `La licence Vesta de {club} expire le {date}, dans 30 jours. Contactez le support Vesta pour la renouveler.` |
| 7 | `{club} : licence à renouveler dans 7 jours` | `La licence Vesta de {club} expire le {date}, dans 7 jours. Contactez le support Vesta pour la renouveler.` |
| 1 | `{club} : la licence expire demain` | `La licence Vesta de {club} expire demain, le {date}. Contactez le support Vesta dès aujourd'hui pour la renouveler.` |

**Période d'essai** (`licence.status == TRIAL`) : même tableau en remplaçant,
dans le titre, « licence à renouveler » par « fin de l'essai » (« {club} : fin de
l'essai dans 30 jours », « {club} : l'essai se termine demain ») et, dans le
corps, « La licence Vesta de {club} expire » par « La période d'essai de Vesta
pour {club} se termine », et « pour la renouveler » par « pour souscrire une
licence ».

**Phrase ajoutée à tous les corps** (licence et essai), à la fin :
`Sans renouvellement, le club passera en lecture seule {grâce} jours après cette date : les données resteront consultables et exportables.`

Cette phrase est fidèle au code (`process_licence_expirations` : passage en
lecture seule quand la date du jour dépasse `end_date + grace_period_days`) et au
CDC 1.4. Si `{grâce}` vaut 0, remplacer « {grâce} jours après cette date » par
« dès le lendemain de cette date » ; si `{grâce}` vaut 1, écrire « 1 jour après
cette date » (singulier, accord grammatical — cas limite corrigé à la tâche
1.14, `_build_licence_reminder_text`).

Exemple complet (licence active, 7 jours, grâce 15 jours) :

> **Loisirs Club Discovery : licence à renouveler dans 7 jours**
> La licence Vesta de Loisirs Club Discovery expire le 12/10/2026, dans 7 jours.
> Contactez le support Vesta pour la renouveler. Sans renouvellement, le club
> passera en lecture seule 15 jours après cette date : les données resteront
> consultables et exportables.

(Nom de club cité à titre d'exemple dans ce document uniquement ; il vient
toujours de `club.name` dans le code.)

## 6. Email

`send_pending_notification_emails` (`backend/apps/notifications/services.py`)
envoie `notification.title` comme objet et `notification.body` comme corps, en
texte brut, **sans gabarit distinct**. Pour le Lot 1, seul l'événement
« Licence proche de l'expiration » part par email : les textes du §5 sont donc
aussi l'objet et le corps de cet email. Ils ont été rédigés pour se lire seuls,
hors de l'application (nom du club dans l'objet et dans le corps, date
explicite).

Ce qui manque à cet email pour être correct (voir point ouvert n° 3) : formule
d'appel, lien vers l'application, mention de l'origine du message, lien de
désactivation des emails.

## 7. Libellés de `Notification.EventType` (valeur de repli)

Fichier : `backend/apps/notifications/models.py`, `Notification.EventType`. Les
libellés restent des noms de catégorie fidèles au tableau 4.17, mais doivent être
accentués puisqu'ils s'affichent si un appelant omet `title=` :

| Valeur | Libellé actuel | Libellé validé |
| --- | --- | --- |
| `membership_signature_pending` | Fiche d'adhesion a signer | `Fiche d'adhésion à signer` |
| `sponsor_reminder` | Rappel au parrain sans reponse (3 jours) | `Rappel au parrain sans réponse` |
| `sponsor_alert_president` | Alerte au President (parrain sans reponse a 7 jours) | `Parrain sans réponse depuis 7 jours` |
| `sponsor_refused` | Refus du parrain | `Refus du parrain` |
| `role_appointed_or_revoked` | Nomination ou revocation | `Nomination ou révocation` |
| `licence_expiring` | Licence proche de l'expiration | `Licence proche de l'expiration` (inchangé) |

Les autres libellés de l'enum (événements des lots suivants) sont hors périmètre
de cette annexe ; ils seront accentués et validés quand leur module sera câblé.
Modifier un libellé de `choices` génère une migration Django sans effet sur les
données : elle doit être créée et réversible (CLAUDE.md §9).

## 8. Récapitulatif pour application dans le code

| # | Fonction | Titre (`title=`) | Corps (`message=`) |
| --- | --- | --- | --- |
| 1 | `clubs.services.notify_sponsor` (première notification) | `Fiche d'adhésion à signer` | `{recrue} attend votre parrainage. Ouvrez sa fiche d'adhésion pour la signer avec votre code PIN, ou pour refuser en indiquant un motif.` |
| 2 | `clubs.services.notify_sponsor` (rappel) | `Rappel : fiche d'adhésion à signer` | `La fiche d'adhésion de {recrue} attend votre réponse depuis 3 jours. Signez-la avec votre code PIN, ou refusez en indiquant un motif.` |
| 3 | `clubs.services.notify_president_of_sponsor_refusal` | `Parrainage refusé` | `{parrain} a refusé de parrainer {recrue}. Motif : « {motif} ». Désignez un autre parrain ou annulez l'adhésion.` |
| 4 | `clubs.services.notify_president_of_no_response` | `Parrain sans réponse` | `{parrain} n'a toujours pas signé la fiche d'adhésion de {recrue}, 7 jours après l'avoir reçue. Un rappel lui a déjà été envoyé.` |
| 5a | `clubs.services.notify_role_change` (`appointed`) | `Nouveau rôle` | `Vous avez désormais le rôle « {rôle} » au sein de {club}.` |
| 5b | `clubs.services.notify_role_change` (`revoked`) | `Fin de rôle` | `Vous n'avez plus le rôle « {rôle} » au sein de {club}.` |
| 6 | `licences.services.process_licence_reminders` | voir §5 (selon palier et statut) | voir §5 (selon palier et statut) + phrase sur la lecture seule |

## 9. Points ouverts

1. **Accents dans tout le backend** : le constat du §0.1 dépasse cette annexe
   (messages d'erreur des services, libellés de `choices` : « Defenseur »,
   « Demission », « Adhesion annulee avant inscription », « Expiree »…). À traiter
   par `backend-dev` dans une passe dédiée, avec vérification par `cdc-reviewer`.
2. **Que peut faire le Président quand le parrain se tait ?** Le CDC 4.3 prévoit
   l'alerte à 7 jours sans dire si le Président peut alors désigner un autre
   parrain ou annuler l'adhésion ; le code ne le permet qu'après un refus
   explicite. Question au client. En attendant, le texte 3.2 ne promet aucune
   action.
3. **Gabarit d'email distinct** (proposition, à décider) : formule d'appel
   « Bonjour {prénom}, », corps de la notification, lien vers l'application,
   phrase « Vous recevez cet email car les notifications par email sont activées
   dans votre profil. », et nom d'expéditeur. À trancher avec le client : le
   footer « VESTA by IMARA TECH Group — … » ne doit **pas** être ajouté à
   l'email sans décision, la règle 19 limitant cette mention à un seul endroit.
   Réalisation par `backend-dev` si retenu.
4. **Où mène le clic sur la notification de licence ?** La cible est l'objet
   `Licence`, que le Président ne consulte pas (espace Superuser, CDC 4.18). À
   préciser dans la spec de la modale des notifications (cloche) : proposition,
   la notification s'ouvre en modale de détail sans navigation.
5. **« Contactez le support Vesta »** : aucun moyen de contact n'est défini
   (mode de paiement des licences encore ouvert, CDC 1.4). Le texte reste
   générique tant que ce canal n'existe pas ; il faudra y ajouter l'adresse ou
   le lien dès qu'il sera fixé.
6. **Tests mis à jour** (fait, tâche 1.7t) : `apps/clubs/tests/test_notifications_wiring.py`,
   `apps/clubs/tests/test_services_roles.py`, `apps/notifications/tests/test_services.py`
   et `apps/notifications/tests/factories.py` comparent désormais la chaîne
   exacte de cette annexe (plus aucune recherche par mot-clé). Point clos.
