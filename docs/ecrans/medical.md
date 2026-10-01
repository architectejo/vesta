# Écran — Médical (fiche de santé, blessures, aptitude, accès du Président)

Sources : CDC 4.12 (en entier), 2.2 (cumul de rôles), 2.3, 2.4 (ligne « Fiches de santé et blessures » et précisions), 3.1 à 3.6, 4.1 (« Mon profil », statut « Blessé »), 4.2 (onglet « Aptitude » sans diagnostic, visibilité publique), 4.17 (« Blessure déclarée »), 5.2 (« Médical »), 6.6, 6.7, 7.5, 9.2 (critère du Lot 4), 10.2 n° 15, 16 et 17. CLAUDE.md §2.5, §2.6, §2.11. Schéma : `docs/lot0/schema-donnees.md` §6 (`HealthRecord`, `Injury`, `InjuryFollowUp`, règle `can_president_read_full_record`). Composants : `docs/lot0/design-system.md`. Écrans liés : `comptes-mon-profil.md` (carte Santé, §4.4 « Ma fiche de santé », §4.5 « Consentement médical »), `sport-seance.md` (§3.2 ter, §4.3 « Déclarer une blessure »), `sport-feuille-de-match.md`, `sport-plan-tactique.md`, `sport-espace-coach.md`, `club-carte-joueur.md`.

**Ce document fait référence pour tous les textes et toutes les règles d'affichage des données de santé.** Les autres specs y renvoient ; en cas d'écart, c'est celle-ci qui s'applique, et l'écart est à corriger dans l'autre spec (liste au §10).

---

## 1. Objectif

Au bord du terrain, le Médecin prend en charge une blessure en quelques gestes et fixe l'aptitude. Le Coach sait, sans rien de plus, qui peut jouer et quand un joueur reviendra. Le joueur garde la maîtrise de son dossier : lui seul et le Médecin en voient le contenu, sauf s'il en ouvre l'accès au Président.

## 2. Qui voit quoi (règle d'affichage unique)

### 2.1 Niveaux d'information

| Niveau | Contenu | Libellés possibles |
| --- | --- | --- |
| **N0 — Indisponible** | Seulement le fait qu'un joueur ne peut pas jouer, sans motif, là où les écrans sportifs l'affichent déjà | `StatusBadge` gris « Indisponible » (même badge que pour une dette, une suspension ou une attente d'adhésion : 10.2 n° 16) |
| **N1 — Aptitude** | Niveau d'aptitude + date de retour prévue. **Rien d'autre** : ni « Blessé », ni date de la blessure, ni auteur, ni date de mise à jour, ni nombre de blessures | « Apte », « Apte avec restriction », « Inapte · retour prévu le {date} », « Inapte · date de retour non fixée » |
| **N2 — Dossier complet** | N1 + « Blessé », fiche de santé, blessures (déclaration, bilan, suivi), historique | Tous les écrans du §4 |

### 2.2 Par rôle

| Qui | Page « Médical » | Écrans sportifs (séance, match, plan, recherche de joueur) | Fiche d'un joueur (modale « Fiche du joueur ») |
| --- | --- | --- | --- |
| **Médecin / référent santé** | N2 pour tous les joueurs du club | N1 (texte servi par `describe_reason_for_viewer`) | Aucune donnée de santé (la fiche publique n'en porte jamais) |
| **Le joueur concerné** | Pas de page ; N2 sur **son** dossier, dans « Mon profil » › « Ma fiche de santé » | N1 sur lui-même | — |
| **Coach** | N1 ; section « Inaptes et restrictions » seulement | N1 | Aucune donnée de santé |
| **Président, sans consentement actif pour son mandat** | N1 + tableau de l'effectif avec la colonne « Dossier complet » | N1 | Aucune donnée de santé |
| **Président, avec consentement actif** | N2 **pour ce joueur seulement**, en lecture seule, chaque ouverture journalisée | N1 (les écrans sportifs n'affichent jamais de diagnostic, pour personne) | Aucune donnée de santé |
| **Vice-président, Directeur sportif** | Pas de page (matrice 2.4 : « — ») | N1 (10.2 n° 16 : « aptitude visible par Pdt/VP/DS/Coach/Médecin ») | Aucune donnée de santé |
| **Capitaine, Trésorier, adjoint, Intendant, autres joueurs** | Pas de page | N0 | Aucune donnée de santé |
| **Autre club (mercato, comparaison, fil public)** | — | — | **Jamais** aucune donnée de santé, pas même l'aptitude (4.2 : « la santé [n'est] jamais [publique] ») |

Cumul de rôles (2.2) : les droits s'additionnent. Un Président qui est aussi Médecin voit N2 en tant que Médecin. Cas du Coach qui serait aussi Médecin : voir le point ouvert 1 (§11).

Le Vice-président qui assure la suppléance du Président n'a **jamais** l'accès N2 : le consentement est donné à la fonction de Président (10.2 n° 15), pas à sa suppléance.

### 2.3 Libellé du rôle

Le rôle s'affiche **« Médecin / référent santé »** partout où un nom de rôle apparaît (puces de rôles, Comité et bureau, bas de la barre latérale, expéditeur d'une notification). Dans les phrases, on écrit « le Médecin ». Aucune qualification n'est demandée ni affichée (10.2 n° 17). Voir le point ouvert 2.

### 2.4 Contrat avec le module sportif (`get_unfitness_reason`)

`apps.medical.services.get_unfitness_reason(membership, at_date=None)`, déjà attendu par `apps.sport.services._get_medical_unfitness` :

| Aptitude à `at_date` | Retour | Effet sportif |
| --- | --- | --- |
| Apte | `None` | Sélectionnable |
| Apte avec restriction | `None` | Sélectionnable (CLAUDE.md §2.5 ne bloque que l'inaptitude ; voir le point ouvert 5) |
| Inapte, date de retour connue | `("Inapte · retour prévu le {date}", date)` | Bloqué |
| Inapte, sans date | `("Inapte · date de retour non fixée", None)` | Bloqué |

- Une blessure « En cours » rend le joueur inapte **dès sa déclaration** (schéma §6.2 ; `sport-seance.md` §4.3). Voir le point ouvert 3.
- Une date de retour **dépassée** ne rend pas le joueur apte : seul le Médecin déclare le retour (4.12, étape 5). Le texte reste « Inapte · retour prévu le {date} ».
- **Ce texte ne contient jamais** « Blessé », « blessure », une localisation, une gravité ou un nom de soignant. Il passe par `describe_reason_for_viewer`, qui le remplace par « Indisponible » pour les rôles N0. L'interface l'affiche tel quel.
- Format de date : « dim. 12 oct. 2026 » (design-system §4), fuseau du club.

---

## 3. Page « Médical »

Route `/medical`. Entrée de la barre latérale « Club › Médical », visible pour le Médecin, le Coach et le Président (design-system §3.9). Un autre rôle qui saisit l'adresse voit `EmptyState` « Vous n'avez pas accès à cette page. » + bouton « Retour à l'accueil ». La réponse est identique quel que soit le joueur ou l'état du club (aucune fuite).

La page exige une connexion. Elle n'est **jamais** mise en cache sur le téléphone (voir §5.4).

**En-tête** : titre « Médical » ; contexte « {nom du club} · Situation au {date du jour} ». Action principale (Médecin et Coach) : « Déclarer une blessure » (§4.1). Le Président n'a pas d'action principale, sauf s'il est aussi Médecin ou Coach.

Sections en cartes, dans cet ordre (chaque section n'apparaît que pour les rôles indiqués) :

### 3.1 « Blessures à compléter » — Médecin

Blessures déclarées que le Médecin n'a pas encore complétées (4.12, étape 2). Toutes affichées (liste courte par nature), les plus anciennes en premier.

Ligne de 56 px, entièrement cliquable : avatar 40 px, nom, « Déclarée le {date} à {heure} · {Séance du …} / {Match contre …} / Hors séance ou match » (13 px, muted), `StatusBadge` orange « À compléter ». Clic → modale « Blessure » (§4.3).

Compteur dans l'en-tête de carte : « {n} ».

### 3.2 « Inaptes et restrictions » — Médecin, Coach, Président

Joueurs dont l'aptitude n'est pas « Apte ». Tri : inaptes d'abord, par date de retour croissante (sans date en dernier), puis restrictions. 5 premiers + « Voir plus » (3.3).

| Élément de ligne | Médecin | Coach, Président sans consentement pour ce joueur | Président avec consentement pour ce joueur |
| --- | --- | --- | --- |
| Avatar, nom, « n° {numéro} » | Oui | Oui | Oui |
| `StatusBadge` d'aptitude | Oui | Oui | Oui |
| Date | « Retour prévu le {date} » / « Date de retour non fixée » ; si dépassée : « Retour prévu le {date} · dépassé » en `--status-warning-fg` | « Retour prévu le {date} » / « Date de retour non fixée » (jamais « dépassé » : l'écart de date signalerait un suivi médical) | Comme le Coach |
| `StatusBadge` « Blessé » | Si une blessure est en cours | Jamais | Jamais sur la ligne (visible dans le dossier) |
| Clic | Modale « Fiche de santé » (§4.2) | Coach : ligne **non cliquable** (il n'y a rien de plus à montrer). Président : modale « Aptitude de {nom} » (§4.6) | Modale « Aptitude de {nom} » (§4.6) |

Exception à la règle 3.3 « clic = détail » pour le Coach : assumée, car toute modale de détail ne ferait que répéter la ligne. Les lignes non cliquables n'ont ni curseur de lien ni chevron.

### 3.3 « Effectif » — Médecin, Président

`DataTable` (plus de 30 joueurs possibles, 3.3). Recherche « Rechercher un joueur ». Première colonne figée « Joueur » (avatar 24 px + nom). Tri par défaut : nom. 20 lignes par page.

| Colonne | Médecin | Président |
| --- | --- | --- |
| Joueur | Oui | Oui |
| N° | Oui | Oui |
| Aptitude (`StatusBadge`) | Oui | Oui |
| Retour prévu | Oui | Oui |
| Fiche | « À jour » (texte muted) · « À compléter » (orange) · « Consentement manquant » (orange) | — |
| Dossier complet | — | « Partagé » (texte) ou « — » |

Filtres : « Aptitude » (Apte, Apte avec restriction, Inapte) ; Médecin : « Fiche » (À jour, À compléter, Consentement manquant) ; Président : « Dossier complet » (Partagé, Non partagé).

Clic sur une ligne : Médecin → « Fiche de santé » (§4.2) ; Président → « Aptitude de {nom} » (§4.6).

La colonne « Dossier complet » ne dit **jamais** pourquoi un dossier n'est pas partagé : jamais accordé, révoqué ou accordé à un Président précédent s'affichent tous « — ».

Le Coach n'a pas cette section : l'aptitude d'un joueur apte ne lui apprend rien, et la section 3.2 couvre son besoin.

### 3.4 « Dernières blessures » — Médecin

Historique du club, toutes blessures confondues : 5 dernières (3.3), « Voir plus ». Ligne : avatar, nom, « {date} · {Séance/Match/Hors séance ou match} », `StatusBadge` (« À compléter » orange, « En cours » orange, « Retour déclaré » vert). Clic → modale « Blessure » (§4.3).

Footer.

---

## 4. Modales

### 4.1 « Déclarer une blessure » (4.12, étape 1) — taille `md`

Ouverte depuis : la page Médical (Médecin, Coach), la vue « Bilan » d'une séance, la section « Blessures » d'un match (Coach, Capitaine, Médecin). **Même modale partout.** Elle remplace la description de `sport-seance.md` §4.3, dont elle reprend les champs.

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Joueur | `PlayerSearch` (présents d'abord si ouverte depuis une séance ou un match) | Oui | « Choisissez un joueur. » |
| Séance ou match | Ouverte depuis une séance ou un match : **lecture seule**, préremplie (« Séance du {date} » / « Match contre {adversaire} »). Ouverte depuis la page Médical : `Select` court des séances et matchs du jour + option « Hors séance ou match » (liste d'évènements, pas de joueurs : `Select` autorisé) | Oui | « Indiquez quand la blessure est survenue. » |
| Moment | `TimeField` (séance, hors séance) ; `NumberField` « Minute » (match) | Oui | Défaut : heure actuelle. « L'heure doit être comprise dans la journée. » ; « Saisissez une minute entre 0 et 130. » |
| Circonstances | `TextArea`, placeholder « Ce qui s'est passé, en quelques mots. » | Oui | « Décrivez brièvement les circonstances. » |

Aide, en haut du corps (encadré neutre, icône cadenas) : « Le Médecin sera prévenu et complétera la fiche. Après l'envoi, seuls le Médecin et le joueur pourront relire ces informations. Le staff verra seulement l'aptitude et la date de retour. »

Pied : « Annuler » / « Déclarer ». Pas de code PIN (hors liste 7.2).

Succès : toast « Blessure déclarée. Le Médecin a été prévenu. » Le joueur devient inapte (calcul de l'API). S'il était réparti en équipe A/B, il rejoint « Ne peuvent pas jouer » (`sport-seance.md` §3.2).

**Après l'envoi, l'auteur ne peut plus relire ni corriger la déclaration** (sauf s'il est Médecin ou s'il s'agit de lui-même). Aucun écran ne lui affiche les circonstances.

**Hors connexion** (6.6, déclarée depuis une séance ou un match) : la déclaration entre dans la file. `SyncIndicator` affiche « Blessure déclarée pour {nom} » **sans les circonstances**. Dès l'envoi réussi, la déclaration est effacée du téléphone. Depuis la page Médical, la modale exige une connexion (« Cette action nécessite une connexion. »).

**Cas limites**
- Joueur déjà inapte (autre blessure en cours) : la déclaration est acceptée ; une blessure distincte est créée.
- Joueur non joueur du club (parti) : absent de la recherche.
- Consentement du joueur au traitement des données de santé manquant : la déclaration est acceptée telle quelle (l'auteur n'en est pas informé : ce serait lui révéler un réglage personnel). Voir le point ouvert 4.

### 4.2 « Fiche de santé » — taille `lg` (Médecin)

Titre « Fiche de santé » ; sous-titre « {Prénom} {Nom} · n° {numéro} ». Chaque ouverture est journalisée (§8).

**Bandeau** (si le joueur n'a pas donné son consentement au traitement de ses données de santé) : `Banner warning` « {Prénom} n'a pas encore donné son consentement au traitement de ses données de santé. Vous pouvez fixer son aptitude et suivre ses blessures déclarées, mais pas compléter sa fiche. Il peut le donner depuis son profil. » (position provisoire, point ouvert 4).

Onglets (`Tabs`, collants sous l'en-tête) :

**Onglet « Aptitude »** (par défaut)
1. `StatusBadge` d'aptitude ; « Retour prévu le {date} » / « Date de retour non fixée » ; « Fixée par {nom} le {date} » (13 px, muted).
2. « Blessures en cours » : liste (toutes), ligne comme §3.4. Clic → « Blessure » (§4.3, niveau 2). Vide : « Aucune blessure en cours. »

**Onglet « Fiche »**
Liste de définitions, une valeur par ligne, « Non renseigné » si vide : « Groupe sanguin », « Allergies », « Antécédents », « Traitements en cours », « Contact d'urgence » (nom et téléphone ; le téléphone est un lien d'appel `tel:`, utile au bord du terrain), « Déclaration du joueur » (avec « Mise à jour par le joueur le {date} » en 13 px muted ; « Le joueur n'a pas encore rempli sa déclaration. » si vide).

**Onglet « Historique »**
Blessures terminées (« Retour déclaré »), 5 dernières + « Voir plus ». Ligne : « {date} · {localisation ou « Localisation non renseignée »} », `StatusBadge`. Clic → « Blessure » (§4.3). Vide : « Aucune blessure passée. »

Pied, selon l'onglet (une seule action principale) :
- « Aptitude » : « Fermer » / « Modifier l'aptitude » (§4.4) ;
- « Fiche » : « Fermer » / « Modifier la fiche » (§4.5) ; bouton masqué si le consentement manque ;
- « Historique » : « Fermer ».

### 4.3 « Blessure » — taille `lg` (Médecin : écriture ; joueur concerné et Président avec consentement : lecture seule)

Titre « Blessure du {date} » ; sous-titre « {Prénom} {Nom} » ; `StatusBadge` à côté du titre : « À compléter » (orange), « En cours » (orange) ou « Retour déclaré » (vert).

Corps, en sections :
1. **Déclaration** : « Déclarée par {nom} le {date} à {heure} » ; « Survenue : {Séance du …} / {Match contre …, {n}e minute} / Hors séance ou match, à {heure} » ; « Circonstances » (texte).
2. **Bilan du Médecin** (4.12, étape 2) : « Localisation », « Gravité », « Soins donnés sur place », « Orientation », « Durée d'indisponibilité estimée » (« {n} jours »), « Complété par {nom} le {date} ». Tant que rien n'est saisi : « Le Médecin n'a pas encore complété cette blessure. »
3. **Suivi** (4.12, étape 4) : entrées datées, la plus récente en premier, 5 dernières + « Voir plus ». Ligne : date (« dim. 12 oct. 2026 »), texte complet (pas de troncature), auteur en 13 px muted. Vide : « Aucune entrée de suivi pour l'instant. »
4. **Retour** (si déclaré) : « Retour déclaré le {date} par {nom}. »

Pied :

| Situation | Médecin | Joueur concerné, Président avec consentement |
| --- | --- | --- |
| À compléter | « Fermer » / « Compléter » (§4.7) | « Fermer » |
| En cours | « Fermer » / secondaire « Déclarer le retour » (§4.9) / principal « Ajouter un suivi » (§4.8). Menu « … » de l'en-tête : « Modifier le bilan » (§4.7) | « Fermer » |
| Retour déclaré | « Fermer ». Menu « … » : « Modifier le bilan » | « Fermer » |

### 4.4 « Modifier l'aptitude » — taille `sm` (Médecin), niveau 2

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Aptitude | `SegmentedControl` : Apte / Apte avec restriction / Inapte | Oui | — |
| Date de retour prévue | `DateField`, affiché seulement si « Inapte » | Non | « La date de retour ne peut pas être dans le passé. » |

Aide : « Le Coach et le Président voient uniquement l'aptitude et la date de retour prévue. »

Si une blessure est en cours : options « Apte » et « Apte avec restriction » désactivées, avec l'aide « {Prénom} a une blessure en cours. Déclarez son retour depuis la blessure pour le rendre apte. » (cohérence avec le schéma §6.2 : une blessure en cours rend inapte).

Bandeau de conséquence, si « Inapte » est choisi alors que le joueur était apte : « {Prénom} ne pourra plus être composé, réparti en équipe ni placé dans un plan tactique tant qu'il est inapte. »

Pied : « Annuler » / « Enregistrer ». Succès : « Aptitude mise à jour. »

### 4.5 « Modifier la fiche » — taille `md` (Médecin), niveau 2

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Groupe sanguin | `Select` court : A+, A−, B+, B−, AB+, AB−, O+, O−, « Non renseigné » | Non | — |
| Allergies | `TextArea` | Non | — |
| Antécédents | `TextArea` | Non | — |
| Traitements en cours | `TextArea` | Non | — |
| Contact d'urgence : nom | `TextField` | Non | — |
| Contact d'urgence : téléphone | `TextField` `tel` | Non | « Numéro de téléphone invalide. » |

La déclaration du joueur est affichée en lecture seule au-dessus des champs (« Déclaration du joueur »), elle n'est pas modifiable par le Médecin.

Pied : « Annuler » / « Enregistrer ». Succès : « Fiche de santé mise à jour. »

### 4.6 « Aptitude de {nom} » — taille `sm` (Président)

Corps :
1. `StatusBadge` d'aptitude ; « Retour prévu le {date} » / « Date de retour non fixée ».
2. Bloc « Dossier médical complet » :
   - **consentement actif pour le mandat en cours** : texte « {Prénom} vous a donné accès à son dossier médical complet. Chaque consultation est enregistrée dans le journal du club. » ; bouton principal « Consulter le dossier complet » ;
   - **sinon** (jamais accordé, révoqué ou accordé à un Président précédent : même texte dans les trois cas) : « {Prénom} n'a pas partagé son dossier médical complet avec le Président. Vous voyez seulement son aptitude et sa date de retour prévue. » Aucun bouton.

Pied : « Fermer » (+ « Consulter le dossier complet » dans le premier cas).

Ce texte ne révèle rien sur la santé : il porte sur un réglage que le joueur a lui-même choisi, et il est le même pour un joueur apte sans aucun antécédent et pour un joueur blessé.

**« Consulter le dossier complet »** remplace le contenu par la modale « Dossier médical de {nom} » (niveau 2, taille `lg`) : même contenu que §4.2 (onglets « Aptitude », « Fiche », « Historique ») et §4.3 (détail d'une blessure), **tout en lecture seule**, sans bandeau de consentement ni action. En haut du corps, `Banner info` : « Consultation enregistrée dans le journal du club. »

**Révocation pendant la consultation** : tant que le dossier est ouvert, l'interface le redemande toutes les 30 s et au retour sur l'onglet. Si l'API refuse, le contenu est effacé de l'écran et remplacé par `EmptyState` « Ce dossier n'est plus accessible. » + « Fermer ». Toute ouverture d'une blessure après la révocation reçoit le même refus.

### 4.7 « Compléter la blessure » / « Modifier le bilan » (4.12, étape 2) — taille `md` (Médecin)

Rappel en lecture seule en haut : joueur, date, moment, circonstances.

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Localisation | `TextField`, placeholder « Ex. cheville droite » | Oui (proposition) | « Indiquez la localisation. » |
| Gravité | `SegmentedControl` : Légère / Modérée / Grave | Oui (proposition) | « Choisissez la gravité. » |
| Soins donnés sur place | `TextArea` | Non | — |
| Orientation | `SegmentedControl` : Repos / Consultation / Hôpital | Oui (proposition) | « Choisissez une orientation. » |
| Durée d'indisponibilité estimée | `NumberField` (jours, 0 à 365) | Non | « Saisissez un nombre de jours entre 0 et 365. » |
| Date de retour prévue | `DateField`, préremplie à « date de la blessure + durée » dès que la durée est saisie, modifiable | Non | « La date de retour ne peut pas être avant la blessure. » |

Aide sous la date : « Seules l'aptitude et cette date sont visibles par le Coach et le Président. »

Pied : « Annuler » / « Enregistrer ». Succès : « Blessure complétée. » (ou « Bilan mis à jour. »). Bloqué si le consentement manque (point ouvert 4) : bouton remplacé par l'aide du bandeau §4.2.

### 4.8 « Ajouter un suivi » (4.12, étape 4) — taille `md` (Médecin)

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Date | `DateField`, défaut aujourd'hui | Oui | « La date ne peut pas être dans le futur. » ; « La date ne peut pas être avant la blessure. » |
| Suivi | `TextArea`, placeholder « Évolution, soins, examens. » | Oui | « Ce champ est obligatoire. » |
| Nouvelle date de retour prévue | `DateField`, préremplie avec la date actuelle | Non | « La date de retour ne peut pas être dans le passé. » |

Pied : « Annuler » / « Ajouter ». Succès : « Suivi ajouté. » Une entrée de suivi ne se modifie pas et ne se supprime pas ; une correction se fait par une nouvelle entrée (proposition, point ouvert 7).

### 4.9 « Déclarer le retour » (4.12, étape 5) — `ConfirmDialog`, taille `sm` (Médecin)

Titre « Déclarer le retour de {prénom} ? ». Texte : « Il redeviendra apte et pourra de nouveau être composé. » Champ `DateField` « Date du retour » (défaut aujourd'hui, ni future, ni avant la blessure). Si une autre blessure du joueur est en cours : texte remplacé par « Cette blessure sera close, mais {prénom} restera inapte : une autre blessure est en cours. »

Boutons « Annuler » / « Déclarer le retour » (bouton `primary`, pas `danger` : l'action n'est pas destructrice). Pas de code PIN (hors liste 7.2). Succès : « Retour déclaré. {Prénom} est de nouveau apte. » (ou « Retour déclaré. {Prénom} reste inapte. »). Pour mettre le joueur « Apte avec restriction » ensuite : « Modifier l'aptitude ».

### 4.10 Côté joueur : « Ma fiche de santé » (depuis « Mon profil », carte Santé)

Précise `comptes-mon-profil.md` §4.4. Taille `lg`. Titre « Ma fiche de santé ». Chaque ouverture est journalisée (schéma §6).

- Onglets « Aptitude », « Ma fiche », « Mes blessures » : même contenu que §4.2 (le joueur voit « Blessé », le bilan, le suivi, l'historique), en lecture seule, sauf sa déclaration.
- Onglet « Ma fiche », en tête : « Déclaration sur mon état de santé » (texte ou « Vous n'avez pas encore rempli votre déclaration. »).
- Pied de l'onglet « Ma fiche » : « Fermer » / « Mettre à jour ma déclaration » → modale `md`, niveau 2 : `TextArea` « Déclaration sur mon état de santé » (facultatif) ; si le consentement manque, `Checkbox` « J'accepte que le Médecin du club traite mes données de santé. » (obligatoire pour enregistrer une déclaration : « Cochez la case pour enregistrer votre déclaration. »). Pied « Annuler » / « Enregistrer ». Succès : « Déclaration enregistrée. »
- Aide permanente sous les onglets (13 px, muted) : « Seuls le Médecin et vous voyez ces informations. Le Coach voit uniquement votre aptitude et votre date de retour prévue. »
- Clic sur une blessure → modale « Blessure » (§4.3) en lecture seule.

### 4.11 Côté joueur : « Consentement médical » (accès du Président) — taille `sm`

Déjà spécifiée dans `comptes-mon-profil.md` §4.5 ; textes reproduits ici à l'identique, avec deux compléments (marqués **nouveau**). Accessible au seul joueur concerné.

Titre : « Autoriser le Président à consulter mon dossier médical complet ».

Corps :
1. État actuel :
   - accordé : `StatusBadge` vert « Accordé » + « Autorisation accordée depuis le {date}. »
   - non accordé : `StatusBadge` gris « Non accordé » + « Autorisation non accordée. »
   - **nouveau** — accordée à un Président précédent, puis passation : `StatusBadge` gris « Non accordé » + « Votre autorisation au Président précédent a pris fin le {date de la passation}. Le Président actuel ne voit que votre aptitude et votre date de retour prévue. »
2. « Par défaut, le Président voit seulement votre aptitude (apte, apte avec restriction, inapte) et votre date de retour prévue, comme le Coach. Si vous l'autorisez, il pourra aussi consulter votre diagnostic, vos blessures et leur suivi. Le Coach, lui, ne voit jamais votre diagnostic. »
3. Encadré information : « Cette autorisation est donnée à la fonction de Président, pas à la personne. Si le club change de Président, votre autorisation ne le suit pas automatiquement ; vous devrez l'accorder à nouveau au nouveau titulaire si vous le souhaitez. »
4. « Votre autorisation, sa révocation et chaque consultation de votre dossier par le Président sont enregistrées dans le journal du club. Le contenu médical n'y est jamais copié. »

Pied :
- non accordé : « Annuler » / « Autoriser ». Succès : « Autorisation accordée au Président. »
- accordé : « Fermer » / « Révoquer » (`danger`) → `ConfirmDialog` « Révoquer l'autorisation ? » — « La révocation prend effet immédiatement : le Président ne pourra plus consulter votre dossier médical complet. » — « Annuler » / « Révoquer ». Succès : « Autorisation révoquée. »

Pas de code PIN. Pas de mise à jour optimiste : l'état affiché est toujours celui du serveur.

**Nouveau — état effectif** : la carte Santé et cette modale affichent l'état **calculé** par la règle `can_president_read_full_record` (schéma §6 : accordé, non révoqué, **et postérieur à la dernière passation**). Après une passation, le joueur ne doit jamais lire « Accordé » alors que le nouveau Président n'a pas accès.

**Effet de la révocation** : immédiat. La prochaine requête du Président sur ce dossier est refusée, y compris s'il l'a ouvert à l'écran (§4.6). La ligne du tableau §3.3 repasse à « — ». Le Président n'est pas prévenu (aucune notification prévue au 4.17 ; point ouvert 6).

---

## 5. Non-divulgation : règles pour l'interface et l'API

Liste exhaustive, qui sert aussi de liste de tests pour `test-engineer` (critère du Lot 4, 9.2 : « le diagnostic d'une blessure est invisible pour le Coach »).

### 5.1 Contenu des réponses

1. Pour un lecteur N1 (Coach, Président sans consentement, VP, DS), l'API renvoie **uniquement** `fitness_status` et `fitness_return_date` (`get_fitness_summary`, schéma §6). Pas de `has_open_injury`, pas de compteur, pas de `fitness_set_at`, pas de `fitness_set_by`, pas de statut de consentement du joueur au traitement de ses données.
2. La réponse a **la même forme pour tous les joueurs** : un joueur sans fiche et un joueur avec dix blessures produisent les mêmes clés.
3. Les points d'accès N2 (fiche, blessure, suivi) répondent à un lecteur non habilité par **le même refus**, que le joueur ait des blessures ou non. Pour un joueur d'un autre club : 404 (isolation, règle n° 8).
4. `PlayerSearch`, la liste des joueurs et la fiche publique (`PlayerPublicCardSerializer`) ne portent **aucune** donnée de santé ; la raison d'inéligibilité vient seulement de `describe_reason_for_viewer`.
5. Le badge « Blessé » n'est envoyé qu'aux lecteurs N2 (le joueur lui-même, le Médecin, le Président avec consentement) ; les autres reçoivent « Inapte » (N1) ou « Indisponible » (N0).

### 5.2 Chemins d'interface à vérifier (Coach, Capitaine, coéquipier)

| Chemin | Ce qui doit s'afficher au plus |
| --- | --- |
| Page Médical (Coach) | Nom, aptitude, date de retour |
| Séance « Bilan » › Blessures, match › Blessures | Voir §10, écart 1 |
| Zone « Ne peuvent pas jouer », banc du plan tactique, composition | Texte de `describe_reason_for_viewer` (N1 ou N0) |
| `PlayerSearch` avec filtre d'éligibilité | Idem |
| Espace coach › « Joueurs indisponibles » › onglet « Inaptes » | « Inapte · retour prévu le {date} » |
| Fiche du joueur, carte FIFA, comparaison, marché, fil public | Rien |
| Notifications | Textes du §7, sans circonstance ni localisation |
| `SyncIndicator` (déclaration hors connexion) | « Blessure déclarée pour {nom} », sans circonstances |
| Titre d'onglet du navigateur, URL | Jamais de donnée de santé (les URL portent un identifiant, pas de libellé) |

### 5.3 Journal visible du Superuser

Le journal ne contient que la métadonnée (§8). La comparaison avant/après de l'espace Superuser affiche « Contenu médical non copié dans le journal. » (`superuser-espace.md`).

### 5.4 Cache et téléphone

- Les réponses N2 ne sont **jamais** conservées : pas de cache du service worker, pas de stockage local, requêtes TanStack Query avec `gcTime: 0` et suppression à la fermeture de la modale.
- La file hors connexion ne garde une déclaration de blessure que jusqu'à son envoi réussi.
- À la déconnexion, tout cache de données de santé est vidé.

---

## 6. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Barre de 3 px + squelette (en-tête, 2 cartes) | — | « Impossible de charger la page. » + « Réessayer » ; hors connexion : « Cette page nécessite une connexion. » (aucune version en cache, §5.4) |
| Blessures à compléter | 2 lignes squelettes | Section affichée avec « Aucune blessure à compléter. » | Modèle standard (`EmptyState` erreur + « Réessayer ») |
| Inaptes et restrictions | 3 lignes squelettes | « Tous les joueurs sont aptes. » | Modèle standard |
| Effectif | 5 lignes `table-row` | Sans filtre : « Aucun joueur dans le club. » ; avec filtre : « Aucun résultat pour « {recherche} ». » + « Effacer les filtres » | Modèle standard |
| Dernières blessures | 2 lignes | « Aucune blessure déclarée. » + (Médecin) « Déclarer une blessure » | Modèle standard |
| Modale « Fiche de santé » / « Dossier médical » | Squelette du corps, titre affiché | Fiche vide : chaque ligne « Non renseigné » ; en tête : « Fiche non encore complétée. » | « Impossible de charger la fiche. » + « Réessayer » |
| Modale « Blessure » | Squelette de 3 sections | Bilan / suivi : textes du §4.3 | Idem ; blessure supprimée ou d'un autre club : « Cet élément n'existe plus. » |
| Dossier du Président après révocation | — | — | « Ce dossier n'est plus accessible. » + « Fermer » |
| Accès refusé à une action (403) | — | — | « Vous n'avez pas accès à cette action. » |
| Envoi d'un formulaire | Bouton `loading` (« Enregistrement… », « Déclaration… ») | — | Erreurs sous les champs ; erreur générale en bandeau du corps |

Succès : toasts listés au §4 ; mise à jour sans rechargement (invalidation de l'aptitude, des listes et, côté sport, de l'éligibilité).

---

## 7. Notifications (4.17)

Seul évènement médical prévu par le 4.17 : « Blessure déclarée » → Médecin, Coach, in-app. L'auteur de la déclaration n'est pas notifié de sa propre action (proposition).

| Destinataire | Texte | Clic |
| --- | --- | --- |
| Médecin / référent santé (tous les titulaires) | « Blessure déclarée : {prénom nom} ({Séance du {date}} / {Match contre {adversaire}} / hors séance ou match). À compléter. » | Page Médical + modale « Blessure » |
| Coach | « {prénom nom} est inapte : blessure déclarée le {date}. » | Page Médical |

Aucun texte ne contient les circonstances, la localisation ou la gravité (y compris dans l'email si le Médecin a activé les emails). Le mot « blessure » adressé au Coach est imposé par le 4.17 ; voir le point ouvert 8.

---

## 8. Journal d'activité (5.2, règle n° 6, règle n° 11)

Chaque entrée : acteur, horodatage, club, type d'action, objet (type + identifiant). **Jamais** de contenu médical dans `before`/`after` (garde-fou déjà en place dans `apps.audit.services`). Seuls `fitness_status` et `fitness_return_date` peuvent y figurer (données N1).

| Action | Type d'action proposé |
| --- | --- |
| Ouverture de la fiche par le Médecin ou par le joueur | `medical.record.viewed` |
| Ouverture du dossier complet (et de chaque blessure) par le Président | `medical.record.viewed_by_president` |
| Consentement accordé / révoqué (accès du Président) | `medical.president_access.granted` / `medical.president_access.revoked` |
| Consentement au traitement des données de santé | `medical.processing_consent.given` |
| Modification de la fiche / de la déclaration du joueur | `medical.record.updated` / `medical.self_declaration.updated` |
| Aptitude modifiée | `medical.fitness.updated` |
| Blessure déclarée / complétée ou bilan modifié / suivi ajouté / retour déclaré | `medical.injury.reported` / `medical.injury.completed` / `medical.injury.followup_added` / `medical.injury.resolved` |
| Consultation de la page Médical (liste d'aptitudes) par le Coach ou le Président | `medical.fitness_list.viewed` (proposition, point ouvert 9) |

---

## 9. Mobile (360 px) et ordinateur

- **360 px** : une colonne, cartes dans l'ordre du §3, marges 12 px. « Déclarer une blessure » sous la ligne de contexte (PageHeader). Lignes de liste de 56 px, badge d'aptitude sous le nom si la ligne manque de place (jamais de troncature du nom). `DataTable` : colonne « Joueur » figée (120 px), les autres défilent dans le cadre. Toutes les modales `md`/`lg` en plein écran ; `sm` en panneau bas. Onglets de la fiche collants sous l'en-tête ; pied de modale toujours visible, clavier ouvert compris. `SegmentedControl` à trois options (« Légère / Modérée / Grave », « Repos / Consultation / Hôpital ») sur une ligne de 328 px ; « Apte avec restriction » passe sur deux lignes dans son segment plutôt que d'être abrégé.
- **≥ 1024 px** : Médecin — deux colonnes 8/4 : à gauche « Blessures à compléter » puis « Inaptes et restrictions », à droite « Dernières blessures » ; « Effectif » en pleine largeur dessous. Coach : une carte centrée (8 colonnes). Président : « Inaptes et restrictions » (8) puis « Effectif » en pleine largeur.
- **Plein soleil** : aucune information portée par la couleur seule (badges toujours libellés) ; textes 14 px minimum, sauf les mentions secondaires à 13 px (10.2 n° 31).
- Vérifications obligatoires à 360 px : nom de 40 caractères ; circonstances de 500 caractères ; 10 entrées de suivi ; thèmes Clair, Sombre et Classic.

---

## 10. Écarts constatés dans les specs existantes (à corriger par `frontend-dev` / `backend-dev`)

1. **Bloquant — `sport-seance.md` §3.3 point 3 et `sport-feuille-de-match.md` §3 point 6 (« Blessures »)** : la liste (joueur, moment, aptitude) est visible de tous les lecteurs de la séance ou du match, coéquipiers compris. Elle révèle qu'un coéquipier est blessé (10.2 n° 16). Correction : liste visible du Médecin, du Coach, du Président, du VP et du DS, avec le texte N1 ; le joueur concerné voit sa propre ligne ; pour le Capitaine, la section ne garde que le bouton « Déclarer une blessure » et la phrase « Les blessures déclarées sont suivies par le Médecin. » ; pour les autres, section masquée.
2. **Bloquant — `mercato-marche.md` l. 38** : la fiche détaillée d'un joueur d'un autre club comporte un onglet « Aptitude ». Contraire au 4.2 (« la santé [n'est] jamais [publique] »). Correction : onglet retiré de toute vue publique ou inter-clubs. Même règle pour la fiche détaillée à venir (`club-carte-joueur.md` B2.5) : onglet « Aptitude » réservé aux lecteurs N1/N2 du même club, masqué (pas « Indisponible ») pour les autres.
3. **Bloquant — `sport-seance.md` §4.1** : le motif d'absence excusée « Blessé » s'affiche dans la liste de pointage, lisible par les coéquipiers. Correction proposée : motif visible des seuls rôles N1 et du joueur ; les autres voient « Absent excusé » sans motif.
4. **`sport-espace-coach.md` §2 et §3 point 2** : le Capitaine a accès à la section « Disponibilité de l'effectif », dont le compteur « {n} inaptes » et l'onglet « Inaptes » ; il ne figure pas parmi les rôles N1 (10.2 n° 16, et position provisoire de `sport-seance.md` §7 point 3). Correction : pour le Capitaine, un seul compteur « {n} indisponibles ». Même spec, §7 : la mention du 10.2 n° 10 est caduque (n° 17 réécrit).
5. **Harmonisation du texte d'inaptitude** : `sport-feuille-de-match.md`, `sport-plan-tactique.md` et `design-system.md` §3.4 écrivent « Inapte (avis médical) » ; `sport-seance.md` écrit « Inapte · retour prévu le {date} ». Texte de référence : celui du §2.4 (servi par l'API, jamais recomposé par l'interface).
6. **`sport-seance.md` §4.3** : remplacer l'aide par celle du §4.1 (« Médecin » avec majuscule, mention de l'impossibilité de relire).
7. **`comptes-mon-profil.md` §4.5 et §3 point 6** : afficher l'**état effectif** du consentement (règle de la passation, §4.11) et ajouter le troisième état.
8. **`club-comite-bureau.md` §3 point 3** : libellé du rôle « Médecin / référent santé » (§2.3).
9. **`design-system.md` §2.5** : ajouter « À compléter » (orange), « En cours » (orange), « Retour déclaré » (vert), « Indisponible » (gris) ; préciser que « Blessé » n'est affiché qu'aux lecteurs N2.

---

## 11. Décisions appliquées et points ouverts

### Décisions tranchées appliquées

- **10.2 n° 15 / CLAUDE.md règle n° 11** : diagnostic et suivi visibles du seul Médecin et du joueur ; Coach limité à l'aptitude et à la date de retour, sans exception ; accès complet du Président seulement sur consentement du joueur, donné et révoqué dans « Mon profil » (modale), effet immédiat, attaché à la fonction (règle de la passation du schéma §6), octroi, révocation et chaque consultation journalisés sans contenu médical.
- **10.2 n° 16** : coéquipiers et rôles non listés : « Indisponible », badge gris, sans motif ; VP et DS : aptitude (N1) dans les écrans sportifs, pas de page Médical (matrice 2.4).
- **10.2 n° 17 (réécrit)** : pas de scénario « sans Médecin » ; libellé « Médecin / référent santé » ; pleins droits du rôle ; aucune qualification demandée. Le n° 10 est caduc.
- **10.2 n° 31** : mentions secondaires à 13 px seulement.

### Points ouverts à remonter au client

1. **Coach qui serait aussi Médecin** (non tranché). CDC 4.12 et 2.4 : « sans exception pour le Coach » ; CDC 2.2 : « ses droits sont alors l'union des droits de ses rôles » ; 10.2 n° 17 : « pleins droits du rôle ». Position provisoire : l'union s'applique **uniquement dans le module Médical** (sinon le club n'aurait plus de Médecin opérationnel) ; les écrans sportifs n'affichent jamais de diagnostic, à personne. Recommandation : que la modale de nomination avertisse le Président du cumul (ce serait un ajout, circuit 9.4). À trancher.
2. **Libellé « Médecin / référent santé »** : le 10.2 n° 17 l'emploie « dans ce cas » (joueur sans qualification), mais aucun champ de qualification n'existe (consigne reçue). Position provisoire : libellé unique pour tous. À confirmer.
3. **Moment où le joueur devient inapte** : le 4.12 place « Le joueur passe « Blessé » et inapte » (étape 3) après le bilan du Médecin (étape 2). Le schéma §6.2 et `sport-seance.md` §4.3, déjà validés, le rendent inapte dès la déclaration. Position retenue : dès la déclaration (plus sûr pour le joueur, et c'est ce qui est déjà validé). À confirmer.
4. **Joueur sans consentement au traitement des données de santé** (7.5, 4.12 ; schéma §6.1 : consentement « obligatoire avant toute écriture clinique »). Le CDC ne dit pas quoi faire d'une blessure survenue avant ce consentement (joueurs importés qui ne se sont jamais connectés, par exemple). Position provisoire : la déclaration (étape 1) et l'aptitude restent possibles, car nécessaires à la règle n° 5 ; le bilan, le suivi et la fiche sont bloqués jusqu'au consentement. Faut-il au contraire refuser l'enregistrement des circonstances ? À trancher.
5. **« Apte avec restriction »** : le CDC ne dit ni si le joueur est sélectionnable (position : oui, seule l'inaptitude bloque, CLAUDE.md §2.5), ni s'il existe une description de la restriction, ni qui la voit. Aucun champ ajouté. Si le client veut un texte de restriction visible du Coach, c'est une décision nouvelle (le Coach ne voit aujourd'hui que le niveau).
6. **Notifications absentes du 4.17** : retour déclaré (au Coach), blessure déclarée (au joueur concerné), octroi ou révocation du consentement (au Président), fin du consentement à la passation (au joueur). Aucune n'est ajoutée. À décider (circuit 9.4).
7. **Correction d'une entrée de suivi** : non prévue par le CDC. Proposition : pas de modification ni de suppression ; on ajoute une nouvelle entrée. À confirmer.
8. **Mot « blessure » dans la notification au Coach** : imposé par le 4.17, alors que les listes montrent au Coach « Inapte » sans la cause (une inaptitude peut aussi venir d'une maladie). Position : on suit le 4.17. À confirmer si le client préfère « {prénom nom} est inapte. ».
9. **Journalisation des consultations N1** : 7.5 dit « chaque consultation [des données de santé] est journalisée » ; le schéma ne journalise que les consultations du Médecin, du joueur et du Président (dossier complet). Proposition : journaliser aussi l'ouverture de la page Médical par le Coach et le Président, mais pas chaque affichage d'un texte d'inéligibilité dans les écrans sportifs (volume). À confirmer.
10. **Accès du Superuser** (non tranché). CDC 2.5 : « Le Superuser a accès à tout » ; CDC 4.12 : diagnostic et suivi visibles « que par le Médecin et le joueur ». Position provisoire, la plus prudente : pas d'accès au contenu médical en session de support ; le Superuser voit le journal (métadonnées). À trancher.
11. **Documents médicaux** (6.7 les cite, schéma J9 aussi) : ni le 4.12 ni le schéma §6.3 ne prévoient de pièce jointe sur une blessure ou un suivi. Aucun champ ajouté. À décider.
12. **Contact d'urgence** : le 4.12 le range dans la fiche que « le Médecin complète ». Faut-il que le joueur puisse le saisir lui-même (il le connaît mieux) ? Position : non, seul le Médecin, conformément au texte.
13. **Joueur parti ou transféré** : le dossier reste dans le club d'origine (isolation). Le joueur peut-il encore le consulter ou l'exporter (7.5) ? Non traité ici ; à trancher avec la suppression et l'export de données.
14. **Le Médecin qui fixe sa propre aptitude** : le CDC ne l'interdit pas. Aucun contrôle ajouté ; signalé pour information.
15. **Champs obligatoires du bilan** (localisation, gravité, orientation) : propositions ; le CDC liste les champs sans dire lesquels sont obligatoires.
