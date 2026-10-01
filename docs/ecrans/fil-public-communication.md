# Écrans — Fil d'actualité, communiqués et chat d'équipe

Sources : CDC 1.2 (espace public / espace privé), 3.1 à 3.6, 4.2 (visibilité publique : jamais poids, taille, téléphone, finances, santé), 4.16, 4.17, 5.2 (« publications et modération »), 5.4 (Ghost Mode), 6.3 (vues publiques dédiées), 6.5 (pas de WebSockets, interrogation 10–30 s suspendue onglet inactif), 6.6 (actions hors connexion : le fil et le chat n'en font pas partie), 6.7 (images), 7.4 (un lien ne donne jamais accès sans connexion), 7.5 (consentement de publication, mineurs), matrice 2.4 (lignes « Communiqués officiels », « Fil public : publier », « Chat d'équipe »), 10.2 n° 12, 16 et 23. Données : `docs/lot0/schema-donnees.md` §10.1 à §10.4. Composants : `docs/lot0/design-system.md`.

Écrans liés (non dupliqués ici) : modales « Communiqué » et « Publier un communiqué » dans `club-accueil.md` §5.1 et §5.2 ; publication automatique d'un résultat dans `sport-feuille-de-match.md` §4.6 ; carte de joueur dans `club-carte-joueur.md`.

Trois pages, une par entrée de la barre latérale (`design-system.md` §3.9) :

| Partie | Route | Entrée de navigation |
| --- | --- | --- |
| A. Fil d'actualité | `/fil` | « Fil d'actualité » (tous) |
| B. Communiqués | `/club/communiques` | « Club › Communiqués » (tous) |
| C. Chat d'équipe | `/club/chat` | « Club › Chat » (tous) |

## 0. Règles communes aux trois pages

### 0.1 Rafraîchissement sans WebSockets (6.5, 4.16)

L'hébergement n'autorise ni WebSockets ni processus permanent. Tout se met à jour par **interrogation régulière** de l'API (TanStack Query `refetchInterval`) :

| Zone | Intervalle | Pendant ce temps |
| --- | --- | --- |
| Conversation de chat ouverte (modale C3) | **10 s** (4.16 : « toutes les 10 secondes environ ») | Nouveaux messages ajoutés en bas |
| Liste des canaux (page C) | 30 s | Compteurs de non-lus mis à jour |
| Fil d'actualité (page A) | 30 s | Pastille « Nouvelles publications », jamais d'insertion directe |
| Modale « Publication » ouverte (commentaires) | 30 s | Nouveaux commentaires ajoutés en bas |
| Communiqués | Pas d'interrogation propre ; rechargement à l'ouverture de la page. Les nouveaux communiqués arrivent par la cloche (30 s, `NotificationBell`) | — |

- **Onglet inactif** (`document.visibilityState = "hidden"`) : interrogation suspendue ; au retour, un appel immédiat puis reprise du rythme.
- **Réseau faible** : en cas d'échec, l'intervalle double à chaque échec (10 → 20 → 30 s, jamais plus de 30 s) et revient à la normale au premier succès. Après 3 échecs consécutifs, `Banner info` en haut de la zone : « Connexion instable : les nouveaux messages s'afficheront dès le retour du réseau. »
- **Demandes incrémentales** : chaque interrogation demande seulement ce qui est plus récent que le dernier élément reçu (`?after={id}`), pour ne pas recharger toute la liste sur un réseau lent. Point à confirmer par `backend-dev`.
- Aucune interrogation quand la page ou la modale concernée n'est pas affichée.

### 0.2 Hors connexion

Le fil, les communiqués et le chat ne font pas partie des actions hors connexion (6.6). Sans réseau : les contenus déjà chargés restent lisibles ; tous les boutons d'écriture (« Publier », « Envoyer », « J'aime », « Commenter », « Signaler », « J'ai lu ») sont désactivés, avec l'aide « Cette action nécessite une connexion. » Aucun message n'est mis en file d'attente, aucun `SyncIndicator` n'est concerné.

### 0.3 Ce qui n'est jamais affiché (4.2, 6.3, 10.2 n° 16)

Sur ces trois pages, pour tout joueur (auteur, commentateur, participant au chat, personne citée dans une publication automatique) :

- jamais de poids, taille, téléphone, email, date de naissance, solde, montant dû ou payé, information médicale ou d'aptitude ;
- **aucun `StatusBadge` de joueur** (ni « En dette », ni « Suspendu », ni « Inapte », ni « En attente ») : ces pages ne servent pas à consulter une situation. C'est aussi ce qui garantit le 10.2 n° 16 sans cas particulier ;
- seulement : avatar (photo ou initiales), prénom et nom, et pour le fil public, nom et logo du club.

Ces règles sont **garanties par l'API** (vues publiques dédiées, 6.3) ; l'interface ne masque pas des champs qu'elle aurait reçus. Si une réponse contient un champ interdit, c'est une anomalie à remonter à `security-auditor`.

### 0.4 Lecture seule, Ghost Mode

- Licence expirée (lecture seule, `design-system.md` §5) : bandeau `readonly` ; « Publier », « Envoyer », « J'aime », « Commenter », « Publier un communiqué » masqués ; lecture possible. « Signaler » reste disponible (ce n'est pas une écriture dans les données du club : c'est une alerte à la plateforme). Point ouvert 9.
- Une publication, un commentaire ou un message supprimé en session de support porte « Action effectuée par le Système Vesta » (avatar « V »), 5.4.

---

# PARTIE A — Fil d'actualité

## A1. Objectif

Faire vivre le club et le réseau : publications des joueurs, résultats, transferts et arrivées, publiques ou réservées au club, avec « J'aime », commentaires et signalement.

## A2. Accès (matrice 2.4)

| Action | Qui |
| --- | --- |
| Lire les publications « Réservées au club » | Membres actifs du club d'origine de la publication |
| Lire les publications « Publiques » | Tout utilisateur connecté de Vesta, quel que soit son club (1.2, espace public). **Jamais sans connexion** (7.4) — voir point ouvert 1 |
| Publier | Tous les joueurs (2.4 « Fil public : publier » : É pour tous) |
| « J'aime », commenter | Tous ceux qui peuvent lire la publication |
| Supprimer une publication | Son auteur ; le Président **du club d'origine** de la publication (4.16) |
| Signaler une publication | Tout joueur qui peut la lire, sur chaque publication (4.16, **10.2 n° 23**) |

Superuser : n'est pas joueur, n'apparaît pas dans le fil et n'y publie pas ; il reçoit les signalements (A6).

## A3. Structure de la page

**En-tête** (`PageHeader`) : titre « Fil d'actualité » ; contexte « {nom du club} · Actualités du club et des autres clubs ». Action principale : « Publier » (ouvre A5.1). Pas de menu « … ».

**Filtre** (sous l'en-tête, hors carte) : `SegmentedControl` « Mon club » / « Tous les clubs ».
- « Mon club » (défaut) : publications de mon club, publiques et réservées.
- « Tous les clubs » : publications publiques de tous les clubs (y compris les miennes) **et** les publications réservées de mon club. Il n'existe pas de vue qui mélangerait des publications réservées d'autres clubs.
- Le choix est mémorisé dans l'URL (`?portee=tous`) pour le retour arrière.

**Pastille de nouveautés** : quand l'interrogation (0.1) trouve des publications plus récentes, une pastille collante en haut de la liste « {n} nouvelle(s) publication(s) — Afficher » ; au clic, la liste remonte en haut et les insère. Rien ne s'insère tout seul pendant que l'utilisateur lit.

**Liste des publications** : les **10 dernières** (3.3 ne fixe pas N pour le fil ; 10 retenu comme pour les notifications), du plus récent au plus ancien, bouton « Voir plus » en bas (ajoute les 10 suivantes, passe en « Chargement… »). Une carte (`Card`) par publication, anatomie A4.

Footer.

## A4. Carte de publication

De haut en bas, padding 12 px (16 px ≥ 640 px) :

1. **En-tête** (ligne de 48 px) : avatar 40 px ; à droite, sur deux lignes : « {Prénom} {Nom} » (14 px/600) puis « {date courte} · {heure} » (13 px, muted, format `design-system.md` §4, fuseau du club). Si la publication vient d'un autre club : sous le nom, logo du club 16 px + « {nom du club} » (13 px). À droite de l'en-tête : puce de visibilité (voir ci-dessous) et `IconButton` « … » (« Plus d'actions »).
   - **Publication automatique** (`post_kind` ≠ `manual`) : l'avatar est le logo du club (32 px dans une pastille de 40 px), le nom affiché est celui du club, et une ligne 13 px précise l'origine : « Résultat de match », « Transfert », « Nouveau joueur ».
2. **Puce de visibilité** : icône 16 px + texte 13 px, fond `--color-surface-muted`, **pas un badge de statut** (aucune couleur de statut) : « Publique » (icône globe) / « Club » (icône cadenas). Texte alternatif : « Visible par tous les clubs » / « Réservée aux membres du club ».
3. **Texte** : 16 px (lecture), retours à la ligne respectés, liens rendus cliquables (ouverture dans un nouvel onglet, `rel="noopener noreferrer"`), aucun HTML interprété. Au-delà de 6 lignes : texte coupé à 6 lignes et lien « Lire la suite » qui déplie **en place**.
4. **Images** (0 à 4) : grille à coins arrondis 8 px, écart 4 px, chargement différé (`loading="lazy"`), taille réservée (pas de saut de page) :
   - 1 image : pleine largeur, ratio d'origine, hauteur max 360 px (`object-fit: cover`) ;
   - 2 : deux colonnes carrées ;
   - 3 : une grande à gauche (2/3), deux petites empilées à droite ;
   - 4 : grille 2 × 2.
   Toucher une image → visionneuse (A5.4). Texte alternatif : « Image {i} sur {n} de la publication de {nom} ».
5. **Contenu d'une publication automatique** (rendu par l'API, affiché tel quel) :
   - Résultat : « {Club} {score} {Adversaire} » (16 px/600, chiffres tabulaires), puis « Buteurs : {noms} » (14 px). Aucune note, aucun carton nominatif (proposition : les cartons relèvent de la discipline, pas de la vitrine publique ; à valider, point ouvert 6).
   - Transfert : « {Prénom} {Nom} rejoint {club B} » avec les deux logos 24 px.
   - Nouveau joueur : « Bienvenue à {Prénom} {Nom} ! » + poste. Pour un joueur **sans consentement de publication de sa carte** ou **mineur** (7.5), l'API ne peut créer cette publication qu'en « Club » (point ouvert 5).
6. **Barre d'actions** (ligne de 44 px, boutons `ghost` `sm` 36 px avec zone 44 px, icône + texte) : « J'aime · {n} » (bascule, état actif en `--color-primary-text`, `aria-pressed`) ; « Commenter · {n} » (ouvre A5.2 avec le champ de commentaire focalisé). Sans compteur si 0 : « J'aime », « Commenter ».
7. **Aperçu des commentaires** : les 2 derniers commentaires (avatar 24 px, nom 13 px/600, texte 14 px sur 2 lignes max.) puis le lien « Voir les {n} commentaires » si plus de 2. Clic → A5.2.

Toucher la zone du texte ou de l'en-tête (hors boutons) ouvre la modale « Publication » (A5.2), conformément à 3.3.

**Menu « … »** (menu déroulant sur ordinateur, panneau bas sur mobile, lignes de 44 px) :
- « Signaler la publication » — **sur chaque publication**, pour tout lecteur (10.2 n° 23). Si l'utilisateur l'a déjà signalée : ligne désactivée « Signalée le {date} » (proposition, point ouvert 3).
- « Supprimer la publication » — auteur, ou Président du club d'origine. Texte en `--status-danger-fg`.
- « Voir la carte de {Prénom} {Nom} » — ouvre la « Fiche du joueur » (`club-carte-joueur.md`) pour un auteur de mon club ; pour un auteur d'un autre club, uniquement si l'API renvoie une carte publique consultable (consentement, 7.5), sinon la ligne n'apparaît pas.

## A5. Modales

### A5.1 « Nouvelle publication » — taille `md` (plein écran sur mobile)

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Texte | TextArea (16 px, hauteur auto, 4 lignes min.), placeholder « Quoi de neuf au club ? », compteur « {n} / 2 000 » | Oui si aucune image | « Écrivez un texte ou ajoutez au moins une image. » ; « 2 000 caractères au maximum. » |
| Images (facultatif) | FileField images : boutons « Ajouter des images » et, sur mobile, « Prendre une photo » ; vignettes 72 px avec `IconButton` « Retirer l'image {i} » | Non | 4 au plus (4.16) : « 4 images au maximum. » ; formats JPEG, PNG, WebP : « Format non accepté : JPEG, PNG ou WebP. » ; « Fichier trop lourd : 10 Mo maximum. » Compression et redimensionnement à 1 600 px de côté max. dans le navigateur **avant** l'envoi (4.16, 6.7), avec indicateur « Préparation de l'image… » sur la vignette |
| Visibilité | SegmentedControl « Club » / « Publique » | Oui | Défaut : **« Club »** (proposition, la plus prudente : point ouvert 2) |

Aide sous la visibilité, selon le choix :
- « Club » : « Visible uniquement par les membres de {nom du club}. »
- « Publique » : « Visible par les membres de tous les clubs sur Vesta. N'y mettez ni numéro de téléphone, ni information de santé, ni montant. » (13 px, `Banner warning` compact)

Pied : « Annuler » / « Publier ». Pendant l'envoi : « Publication… » (les images partent déjà compressées ; sur réseau lent, barre de progression fine sous l'en-tête de la modale). Succès : fermeture, toast « Publication ajoutée. », la publication apparaît en tête de liste. Fermeture avec saisie : confirmation standard « Abandonner les modifications ? ».

Erreurs : de champ sous le champ ; générale dans le bandeau du corps (« Connexion impossible. Vérifiez votre réseau et réessayez. ») ; la saisie et les images sont conservées.

### A5.2 « Publication » (détail et commentaires) — taille `md` (plein écran sur mobile)

- **En-tête** : titre « Publication de {Prénom} {Nom} » (ou « Publication de {nom du club} » pour une publication automatique) ; sous-titre « {date longue} · {heure} · {Publique / Club} » ; menu « … » (mêmes lignes qu'en A4) ; croix « Fermer ».
- **Corps** : la publication en entier (texte complet, images, barre d'actions A4.6), puis section « Commentaires ({n}) » : les **10 derniers** du plus ancien au plus récent (lecture de conversation), bouton « Commentaires précédents » **en haut** de la section pour charger les 10 d'avant. Chaque commentaire : avatar 32 px, « {Prénom} {Nom} » 13 px/600, texte 14 px, « {date courte} · {heure} » 13 px muted ; pour son auteur et pour le Président du club d'origine de la publication, `IconButton` « … » → « Supprimer le commentaire » (proposition, point ouvert 4).
- **Pied** (variante « conversation », toujours visible, au-dessus du clavier) : TextArea 1 à 4 lignes, 16 px, placeholder « Écrire un commentaire… », compteur au-delà de 900 caractères (« {n} / 1 000 ») ; bouton principal « Envoyer » (40 px, désactivé tant que le champ est vide). Pas de bouton « Annuler » dans cette variante : la croix ferme la modale (confirmation standard si un commentaire est en cours de saisie).
- Envoi : le commentaire s'ajoute aussitôt en bas avec la mention « Envoi… » (13 px, muted) ; succès : mention retirée ; échec : mention « Non envoyé » en `--status-danger-fg` + bouton `ghost` « Réessayer », le texte n'est pas perdu.
- Rafraîchissement : 30 s (0.1).

### A5.3 « Signaler la publication » — taille `sm` (panneau bas sur mobile) — **10.2 n° 23**

- Titre : « Signaler cette publication ? »
- Texte : « L'équipe Vesta sera prévenue et examinera la publication. Elle reste visible en attendant. »
- Champ « Motif (facultatif) » : TextArea 3 lignes, 500 caractères max. (« 500 caractères au maximum. »), aide « Ex. : propos insultants, image choquante, information personnelle. »
- Pied : « Annuler » / « Signaler » (bouton principal, pas `danger` : ce n'est pas une destruction). Pas de code PIN (7.2 ne le demande pas).
- Succès : fermeture, toast « Merci. La publication a été signalée à l'équipe Vesta. » ; la ligne du menu devient « Signalée le {date} ».
- Effet côté API (rappel, aucune logique dans l'interface) : création d'un `PostReport`, **notification au Superuser** et **entrée dans le journal d'activité** (`social.post.reported`), `schema-donnees.md` §10.4. Le signalement n'est pas montré à l'auteur ni aux autres joueurs.
- Vocabulaire : « équipe Vesta » désigne les Superusers ; le nom de l'Éditeur n'apparaît pas (CLAUDE.md règle 19).

### A5.4 Visionneuse d'images — modale plein écran (toutes tailles)

Fond `--color-overlay` opaque à 90 %, image centrée (`object-fit: contain`), compteur « {i} sur {n} » en haut, croix « Fermer » (44 px). Navigation : glissement horizontal sur mobile, `IconButton` « Image précédente » / « Image suivante » et flèches du clavier sur ordinateur. Échap et bouton retour d'Android ferment. Aucune action d'écriture. Pas de téléchargement proposé (proposition).

### A5.5 « Supprimer la publication » — `ConfirmDialog`

Titre « Supprimer cette publication ? » ; texte « Elle disparaîtra du fil pour tout le monde, avec ses commentaires et ses « J'aime ». » ; boutons « Annuler » (focus) / « Supprimer » (`danger`). Succès : toast « Publication supprimée. », la carte disparaît de la liste (et la modale A5.2 se ferme si elle était ouverte). Suppression logique et journalisée par l'API (4.16, 5.2). Même modèle pour un commentaire : « Supprimer ce commentaire ? » — « Il disparaîtra pour tout le monde. » — « Supprimer » — toast « Commentaire supprimé. »

## A6. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Liste | 3 cartes squelettes (en-tête rond + 3 lignes + bloc image) | « Mon club » : « Aucune publication pour l'instant. » + action « Publier » ; « Tous les clubs » : « Aucune publication publique pour l'instant. » | `EmptyState` erreur « Impossible de charger le fil. » + « Réessayer » |
| « Voir plus » | Bouton « Chargement… » | Bouton retiré quand tout est affiché | Toast « Connexion impossible. Vérifiez votre réseau et réessayez. », bouton rétabli |
| Image | Fond `--color-skeleton` à la taille réservée | — | Bloc `--color-surface-muted` + icône + « Image indisponible » (13 px) |
| « J'aime » | Mise à jour optimiste immédiate | — | Retour à l'état précédent + toast « Votre « J'aime » n'a pas été enregistré. » |
| Modale « Publication » | Publication affichée depuis la liste, squelette de 3 commentaires | « Aucun commentaire. Soyez le premier à réagir. » | « Impossible de charger les commentaires. » + « Réessayer » |
| Publication supprimée entre-temps | — | — | À l'ouverture : « Cette publication n'existe plus. » + « Fermer » ; retirée de la liste |
| Publication publique d'un club dont la licence est suspendue | — | — | Non servie par l'API (proposition, point ouvert 8) |

## A7. Mobile (360 px) et ordinateur

- **360 px** : cartes pleine largeur, marges 12 px ; « Publier » sous la ligne de contexte (largeur automatique, pas pleine largeur). Barre d'actions sur une ligne : « J'aime · 12 » et « Commenter · 4 » tiennent en 336 px. Modales A5.1 et A5.2 plein écran ; dans A5.2 le pied de conversation reste au-dessus du clavier (`visualViewport`). Menu « … » en panneau bas.
- **≥ 768 px** : colonne de lecture centrée de **640 px max.** (pas de fil sur toute la largeur : une ligne de texte trop longue se lit mal).
- **≥ 1024 px** : colonne de 640 px + colonne latérale de 320 px à droite contenant une seule carte « Communiqués » (3 derniers, lien « Voir tous les communiqués ») — proposition ; masquée sous 1024 px pour ne pas allonger la page.
- Vérifications à 360 px : nom d'auteur de 40 caractères + nom de club long sans débordement ; 4 images ; texte sans espace (URL longue) avec `overflow-wrap: anywhere` ; thèmes Classic, Clair, Sombre.

---

# PARTIE B — Communiqués officiels

## B1. Objectif

Informer officiellement tous les joueurs et savoir qui a lu. Le communiqué est épinglé en tête de l'accueil (4.16) ; cette page donne l'historique complet.

## B2. Accès (matrice 2.4 « Communiqués officiels »)

| Action | Qui |
| --- | --- |
| Lire, accuser réception (« J'ai lu »), partager sur WhatsApp | Tous les joueurs du club |
| Publier, épingler / désépingler, voir les accusés de lecture | Président, Vice-président |

Les communiqués ne sont **jamais publics** : ils ne figurent pas dans le fil « Tous les clubs ».

## B3. Structure de la page

**En-tête** : titre « Communiqués » ; contexte « {nom du club} · {n} non lu(s) » (ou « {nom du club} · Tout est lu »). Action principale (Président, VP) : « Publier un communiqué » → modale `club-accueil.md` §5.2 (inchangée).

1. **Épinglés** — carte, tous les communiqués épinglés (en pratique peu nombreux), du plus récent au plus ancien. Masquée s'il n'y en a aucun.
2. **Tous les communiqués** — carte, **10 derniers** + « Voir plus ».

Ligne de communiqué (56 px min., entièrement cliquable) : titre 16 px/600 (2 lignes max., pas de troncature en une ligne) ; dessous, avatar 24 px + « {nom} · {date courte} » 13 px muted ; à droite, pastille « Non lu » (point 8 px `--color-primary` + texte 13 px) si non lu ; icône « Épinglé » (16 px, avec texte masqué pour lecteur d'écran) dans la liste générale. Pour Président et VP : « Lu par {n} sur {total} » (13 px) sous le titre.

Clic → modale « Communiqué » (`club-accueil.md` §5.1, inchangée : « J'ai lu », « Partager sur WhatsApp », menu « … » Président/VP « Désépingler » / « Épingler », « Voir les accusés de lecture »).

Footer.

## B4. Modales ajoutées

### B4.1 « Accusés de lecture » — taille `md`, Président et VP (précise `club-accueil.md` §5.1)

- Sous-titre : titre du communiqué.
- Résumé : « Lu par {n} joueurs sur {total} ({x} %) ».
- `SegmentedControl` « Non lus ({n}) » / « Lus ({n}) » (défaut : « Non lus », pour relancer les retardataires) ; champ de recherche « Nom ou numéro » (l'effectif peut dépasser 30 joueurs, 3.3).
- Liste : avatar 32 px, nom, et pour « Lus » la date « Lu le {date} à {heure} ». Aucun badge de statut (0.3).
- Pied : « Fermer ». Lecture seule.
- États : squelette 5 lignes ; « Tous les joueurs ont lu ce communiqué. » ; « Personne n'a encore lu ce communiqué. » ; erreur standard + « Réessayer ».

### B4.2 « Désépingler » / « Épingler »

Action directe du menu « … » (pas de formulaire) : toast « Communiqué désépinglé. Il n'apparaît plus sur l'accueil. » / « Communiqué épinglé en tête de l'accueil. » Journalisé par l'API.

### B4.3 « Partager sur WhatsApp » (4.16, 10.2 n° 12)

Ouvre `https://wa.me/?text=` avec : « {titre du communiqué} — {nom du club} : {lien Vesta du communiqué} ». **Le corps du communiqué n'est pas copié dans WhatsApp** (position la plus prudente : 4.16 dit « le contenu reste accessible uniquement après connexion » ; point ouvert 7). Le lien ouvre la page de connexion si l'utilisateur n'est pas connecté (7.4), puis la modale du communiqué. Aucune API WhatsApp Business (hors MVP, 10.2 n° 12).

## B5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Épinglés | 2 lignes squelettes | Carte masquée | Modèle standard |
| Tous | 5 lignes squelettes | « Aucun communiqué pour l'instant. » + (Pdt, VP) « Publier un communiqué » | « Impossible de charger les communiqués. » + « Réessayer » |
| « J'ai lu » | Bouton `loading` « Enregistrement… » | — | Toast « Connexion impossible. Vérifiez votre réseau et réessayez. » |

Succès : « Communiqué publié. Tous les joueurs ont été prévenus. » (`club-accueil.md`) ; « Lecture confirmée. » après « J'ai lu ».

## B6. Mobile (360 px) et ordinateur

- **360 px** : cartes pleine largeur, lignes de 56 px min. ; modales plein écran ; « Publier un communiqué » sous la ligne de contexte.
- **≥ 1024 px** : colonne unique de 800 px max. centrée (lecture), cartes « Épinglés » puis « Tous ».

---

# PARTIE C — Chat d'équipe

## C1. Objectif

Échanger rapidement entre membres du club, sans quitter Vesta : un canal général et un canal du bureau (4.16). **Pas d'autre canal au MVP** : le CDC n'en prévoit que deux (ni canal libre, ni message privé entre joueurs, ni canal par équipe A/B) ; toute demande en ce sens suit le circuit 9.4.

## C2. Accès (matrice 2.4 « Chat d'équipe » : É pour tous)

| Canal | Qui le voit et y écrit |
| --- | --- |
| « Général » | Tous les joueurs actifs du club |
| « Bureau » | Les membres du bureau uniquement, selon l'API (`schema-donnees.md` §10.3 : « accès restreint aux rôles du bureau »). **Composition non définie par le CDC** : position provisoire la plus restrictive, Président, Vice-président, Directeur sportif, Trésorier, Trésorier adjoint, Intendant (2.3 distingue « les membres du bureau et le Médecin » ; le Coach et le Capitaine n'en font pas partie). Point ouvert 10 |

Un joueur qui n'a pas accès au canal « Bureau » **ne le voit pas du tout** (pas de ligne grisée, pas de compteur). Un membre révoqué du bureau perd l'accès immédiatement, y compris à l'historique (proposition). Le Superuser n'a pas accès au chat hors session de support.

## C3. Structure de la page `/club/chat`

**En-tête** : titre « Chat » ; contexte « {nom du club} · {n} canal / canaux ». Pas d'action principale (on écrit dans une conversation).

**Carte « Canaux »** : une ligne par canal accessible (2 au plus), 64 px, entièrement cliquable :
- icône du canal 40 px (« # » pour Général, cadenas pour Bureau) ; nom « Général » / « Bureau » (14 px/600) ; description 13 px muted : « Tous les joueurs du club » / « Membres du bureau » ;
- dernier message sur une ligne : « {Prénom} : {début du texte} » ou « {Prénom} a envoyé une image » (13 px, une ligne avec points de suspension — c'est un aperçu, le message complet est dans la conversation) ; heure ou date à droite ;
- compteur de non-lus (pastille `--color-primary`, texte `--color-on-primary`, « 99+ » au-delà).

Clic → modale « Conversation » (C4). **Pourquoi une modale** : le champ de saisie est un formulaire ; il vit donc dans une modale (3.2, règle 13), et le clic sur un élément de liste ouvre une modale (3.3). Sur mobile, la modale plein écran se comporte comme un écran de messagerie ordinaire ; le bouton retour d'Android la ferme.

Footer.

## C4. Modale « Conversation » — taille `lg` (plein écran sur mobile)

- **En-tête** : titre « Général » ou « Bureau » ; sous-titre « {n} membres » ; croix « Fermer ».
- **Corps** (défilant, ancré en bas à l'ouverture) :
  - les **30 derniers messages** ; bouton `ghost` « Messages précédents » en haut, qui charge les 30 d'avant sans faire sauter la position de lecture ;
  - séparateurs de jour centrés (13 px muted) : « Aujourd'hui », « Hier », « {jour date} » ;
  - séparateur « Nouveaux messages » (ligne `--color-primary-text`) avant le premier message non lu ; l'ouverture positionne la lecture sur ce séparateur s'il existe ;
  - **message d'un autre membre** : à gauche, avatar 32 px (seulement sur le premier message d'une série du même auteur), « {Prénom} {Nom} » 13 px/600 au-dessus de la bulle, bulle `--color-surface-muted`, texte 14 px, heure 13 px muted sous la bulle ; largeur max. 80 % ;
  - **mon message** : à droite, sans avatar ni nom, bulle teintée (`--color-primary` à 12 % sur la surface, texte `--color-text` : contraste ≥ 7:1 conservé en plein soleil), heure dessous ; états « Envoi… » puis rien ; échec : « Non envoyé » en `--status-danger-fg` + `ghost` « Réessayer » + « Supprimer le brouillon » ;
  - **image** : vignette 240 px de large max., coins 8 px, ouverture dans la visionneuse (A5.4) ; texte alternatif « Image envoyée par {Prénom} {Nom} » ;
  - liens cliquables, aucun HTML interprété, `overflow-wrap: anywhere`.
  - **Arrivée de nouveaux messages** (interrogation 10 s, 0.1) : si l'utilisateur est en bas, défilement automatique ; s'il lit plus haut, pastille flottante « {n} nouveau(x) message(s) ↓ » (bouton 36 px) qui ramène en bas. Annonce `aria-live="polite"` limitée au nombre de nouveaux messages, pas à leur contenu.
- **Pied** (variante « conversation », toujours visible au-dessus du clavier) : `IconButton` « Ajouter une image » (40 px) ; TextArea 1 à 4 lignes, 16 px, placeholder « Écrire un message… », 2 000 caractères max. (« 2 000 caractères au maximum. » au-delà) ; bouton principal « Envoyer » (40 px, libellé visible, désactivé si le champ est vide et sans image).
  - Ordinateur : Entrée envoie, Maj + Entrée passe à la ligne (aide 13 px sous le champ au premier focus : « Entrée pour envoyer, Maj + Entrée pour aller à la ligne »). Mobile : Entrée passe à la ligne, on envoie par le bouton.
  - Image : une par message (`schema-donnees.md` §10.3) ; aperçu 72 px au-dessus du champ avec `IconButton` « Retirer l'image » ; compression à 1 600 px dans le navigateur avant envoi (6.7) ; formats et poids : mêmes messages qu'en A5.1.
  - Fermeture avec un message en cours de saisie : confirmation standard « Abandonner les modifications ? ».
- **Lecture** : ouvrir la conversation marque comme lus les messages affichés (l'API reçoit le dernier identifiant vu) ; le compteur de la page se met à jour.
- Pas de modification ni de suppression de message, pas de réaction, pas de signalement dans le chat : le CDC ne les prévoit pas (point ouvert 11).

## C5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Canaux | 2 lignes squelettes | Aucun cas (le canal Général existe toujours, créé avec le club) | `EmptyState` erreur « Impossible de charger les canaux. » + « Réessayer » |
| Canal sans message | — | « Aucun message pour l'instant. Lancez la conversation. » (dans le corps de la modale, le pied reste actif) | — |
| Conversation | 6 bulles squelettes alternées | — | « Impossible de charger les messages. » + « Réessayer » ; pied désactivé |
| Envoi | « Envoi… » sous la bulle | — | « Non envoyé » + « Réessayer » ; texte conservé |
| Accès retiré pendant la lecture (révocation du bureau) | — | — | Réponse 403 à l'interrogation : la modale affiche « Vous n'avez plus accès à ce canal. » + « Fermer », le canal disparaît de la liste |
| Réseau instable | — | — | `Banner info` « Connexion instable : les nouveaux messages s'afficheront dès le retour du réseau. » (0.1) |

## C6. Mobile (360 px) et ordinateur

- **360 px** : page = une carte de 2 lignes ; modale plein écran ; en-tête 56 px ; pied collé au clavier (`visualViewport`), la zone de messages occupe le reste. Bulles 80 % de 336 px, texte 14 px, jamais plus gros.
- **≥ 1024 px** : modale `lg` (800 px, 90 vh). Proposition d'amélioration ultérieure, **non incluse** : liste des canaux et conversation côte à côte dans la page ; elle obligerait à mettre le champ de saisie dans la page (exception à la règle 3.2 à faire valider, comme le tableau noir, 10.2 n° 32). Au MVP, on reste en modale.

---

## D. Journal et notifications (rappel pour `backend-dev` et `test-engineer`)

| Événement | Journal (5.2) | Notification |
| --- | --- | --- |
| Publication créée, supprimée | Oui | Aucune au MVP (4.17 n'en prévoit pas) |
| Commentaire créé, supprimé | Oui | Aucune (4.17 n'en prévoit pas ; proposition d'avenir : prévenir l'auteur de la publication, circuit 9.4) |
| « J'aime » | Oui (création/suppression d'une donnée, règle 6) | Aucune |
| **Signalement** | **Oui** (`social.post.reported`) | **Superuser**, in-app (10.2 n° 23) : « Publication signalée dans le club {nom du club} » ; le clic ouvre la publication dans l'espace Superuser (point ouvert 3) |
| Communiqué publié | Oui | Tous les joueurs, in-app (texte de `club-accueil.md` : « Tous les joueurs ont été prévenus » ; ligne absente du tableau 4.17, point ouvert 12) |
| Accusé de lecture, épinglage | Oui | Aucune |
| Message de chat | Oui (règle 6 : création de donnée ; contenu à ne pas dupliquer intégralement dans le journal, à voir avec `backend-dev`) | Aucune notification cloche ; compteur de non-lus sur l'entrée « Chat » de la barre latérale (proposition) |

## E. Textes exacts

**Communs** : « Cette action nécessite une connexion. » ; « Connexion instable : les nouveaux messages s'afficheront dès le retour du réseau. » ; « Envoi… » ; « Non envoyé » ; « Réessayer » ; « Format non accepté : JPEG, PNG ou WebP. » ; « Fichier trop lourd : 10 Mo maximum. » ; « Préparation de l'image… » ; « Image indisponible » ; « Image précédente » ; « Image suivante » ; « {i} sur {n} ».

**Fil** : « Fil d'actualité » ; « {nom du club} · Actualités du club et des autres clubs » ; « Publier » ; « Mon club » ; « Tous les clubs » ; « {n} nouvelle(s) publication(s) — Afficher » ; « Publique » ; « Club » ; « Visible par tous les clubs » ; « Réservée aux membres du club » ; « Résultat de match » ; « Transfert » ; « Nouveau joueur » ; « Buteurs : {noms} » ; « {Prénom} {Nom} rejoint {club} » ; « Bienvenue à {Prénom} {Nom} ! » ; « Lire la suite » ; « J'aime » ; « Commenter » ; « Voir les {n} commentaires » ; « Plus d'actions » ; « Signaler la publication » ; « Signalée le {date} » ; « Supprimer la publication » ; « Voir la carte de {Prénom} {Nom} » ; « Nouvelle publication » ; « Quoi de neuf au club ? » ; « Écrivez un texte ou ajoutez au moins une image. » ; « 2 000 caractères au maximum. » ; « Ajouter des images » ; « Prendre une photo » ; « Retirer l'image {i} » ; « 4 images au maximum. » ; « Visibilité » ; « Visible uniquement par les membres de {nom du club}. » ; « Visible par les membres de tous les clubs sur Vesta. N'y mettez ni numéro de téléphone, ni information de santé, ni montant. » ; « Publication… » ; « Publication ajoutée. » ; « Publication de {Prénom} {Nom} » ; « Commentaires ({n}) » ; « Commentaires précédents » ; « Écrire un commentaire… » ; « Envoyer » ; « Aucun commentaire. Soyez le premier à réagir. » ; « Signaler cette publication ? » ; « L'équipe Vesta sera prévenue et examinera la publication. Elle reste visible en attendant. » ; « Motif (facultatif) » ; « Ex. : propos insultants, image choquante, information personnelle. » ; « 500 caractères au maximum. » ; « Signaler » ; « Merci. La publication a été signalée à l'équipe Vesta. » ; « Supprimer cette publication ? » ; « Elle disparaîtra du fil pour tout le monde, avec ses commentaires et ses « J'aime ». » ; « Supprimer » ; « Publication supprimée. » ; « Supprimer ce commentaire ? » ; « Il disparaîtra pour tout le monde. » ; « Commentaire supprimé. » ; « Aucune publication pour l'instant. » ; « Aucune publication publique pour l'instant. » ; « Impossible de charger le fil. » ; « Impossible de charger les commentaires. » ; « Cette publication n'existe plus. » ; « Votre « J'aime » n'a pas été enregistré. » ; « Image {i} sur {n} de la publication de {nom} ».

**Communiqués** : « Communiqués » ; « {nom du club} · {n} non lu(s) » ; « {nom du club} · Tout est lu » ; « Épinglés » ; « Tous les communiqués » ; « Non lu » ; « Épinglé » ; « Lu par {n} sur {total} » ; « Accusés de lecture » ; « Lu par {n} joueurs sur {total} ({x} %) » ; « Non lus ({n}) » ; « Lus ({n}) » ; « Lu le {date} à {heure} » ; « Tous les joueurs ont lu ce communiqué. » ; « Personne n'a encore lu ce communiqué. » ; « Épingler » ; « Désépingler » ; « Communiqué désépinglé. Il n'apparaît plus sur l'accueil. » ; « Communiqué épinglé en tête de l'accueil. » ; « Lecture confirmée. » ; « Aucun communiqué pour l'instant. » ; « Impossible de charger les communiqués. ».

**Chat** : « Chat » ; « Canaux » ; « Général » ; « Bureau » ; « Tous les joueurs du club » ; « Membres du bureau » ; « {Prénom} a envoyé une image » ; « {n} membres » ; « Messages précédents » ; « Aujourd'hui » ; « Hier » ; « Nouveaux messages » ; « {n} nouveau(x) message(s) » ; « Ajouter une image » ; « Retirer l'image » ; « Écrire un message… » ; « Entrée pour envoyer, Maj + Entrée pour aller à la ligne » ; « Supprimer le brouillon » ; « Image envoyée par {Prénom} {Nom} » ; « Aucun message pour l'instant. Lancez la conversation. » ; « Impossible de charger les canaux. » ; « Impossible de charger les messages. » ; « Vous n'avez plus accès à ce canal. ».

## F. Décisions appliquées et points ouverts

**Décisions appliquées**

- **10.2 n° 23 (décidé)** : « Signaler » sur chaque publication, pour tout joueur ; notification au Superuser et entrée de journal (A4, A5.3, D).
- **10.2 n° 12** : aucune liaison WhatsApp par API ; partage par lien uniquement (B4.3).
- **10.2 n° 16** : aucun statut de joueur affiché sur ces pages (0.3).
- **6.5 / 4.16** : interrogation 10 s pour la conversation ouverte, 30 s ailleurs, suspendue onglet inactif, espacée en cas d'échec (0.1).
- **3.2 / règle 13** : le champ de saisie du chat et des commentaires est dans une modale (C3, A5.2) ; aucune exception de page demandée (seule la forme du pied est à valider, point 14).

**Points ouverts à soumettre au client**

1. **Qui lit le fil public** : « tout utilisateur connecté de Vesta » (position appliquée, la plus prudente, cohérente avec 7.4). Une lecture sans connexion (visiteurs) n'est pas prévue ; si le client la veut, c'est une demande nouvelle (9.4).
2. **Visibilité par défaut d'une publication** : « Club » (proposition, la plus prudente). Le CDC ne fixe pas de défaut.
3. **Signalement** : un joueur peut-il signaler deux fois la même publication (proposition : non, une fois par personne) ? Où le Superuser traite-t-il les signalements, et que peut-il faire (masquer, supprimer, classer) ? `superuser-espace.md` ne le prévoit pas ; 5.2 cite la « modération » sans la décrire. À spécifier avant l'implémentation de la notification (lien de destination).
4. **Suppression d'un commentaire** : non décrite au 4.16 (qui ne parle que des publications). Proposition : auteur du commentaire ou Président du club d'origine de la publication.
5. **Publications automatiques et consentement** (7.5) : un « Nouveau joueur » ou un « Transfert » concernant un joueur sans consentement de publication de sa carte, ou mineur, doit-il être publié en « Club » seulement ? Position provisoire la plus prudente : oui, jamais public. Visibilité par défaut des publications automatiques à fixer (le ConfirmDialog de `sport-feuille-de-match.md` §4.6 ne propose pas de choix).
6. **Contenu public d'un résultat** : buteurs oui (statistiques sportives publiques, 4.2) ; cartons nominatifs exclus (proposition). À valider.
7. **Texte partagé sur WhatsApp** : 4.16 dit « le texte et le lien » puis « le contenu reste accessible uniquement après connexion ». Position appliquée, la plus prudente : titre et lien seulement, pas le corps. À confirmer.
8. **Publications publiques d'un club dont la licence est suspendue ou résiliée** : restent-elles visibles des autres clubs ? Proposition : non servies. À trancher.
9. **Club en lecture seule (licence expirée)** : « Signaler » maintenu (alerte plateforme) ; publication, commentaires, « J'aime » et chat bloqués. À confirmer.
10. **Composition du canal « Bureau »** : non définie par le CDC. Position provisoire, la plus restrictive : Président, VP, DS, Trésorier, Trésorier adjoint, Intendant (sans Médecin, Coach ni Capitaine ; 2.3 cite « le bureau et le Médecin » séparément). Attention : l'écran `club-comite-bureau.md` range le Médecin dans la section « Bureau » ; l'incohérence est à lever par le client.
11. **Chat : modification, suppression, signalement d'un message** : non prévus au CDC ; non spécifiés. Si le client veut pouvoir retirer un message injurieux, c'est une demande nouvelle (9.4).
12. **Notification de communiqué** : `club-accueil.md` annonce « Tous les joueurs ont été prévenus », mais le tableau 4.17 n'a pas de ligne « Communiqué publié ». À ajouter au 4.17 (et à l'annexe E) ou à retirer du message de succès.
13. **Pour `security-auditor` et `backend-dev` — confidentialité des images** : `schema-donnees.md` §1 classe `Image` comme fichier **public** (servi comme un asset). C'est correct pour les images de publications « Publiques », mais **pas** pour les images des publications « Club », des communiqués et du **chat** (surtout du canal « Bureau ») : quiconque obtient l'adresse les verrait sans connexion, contraire à 7.4 et à l'esprit de la règle 10. Position provisoire la plus prudente : ces images doivent être servies par une vue authentifiée qui vérifie le club (et le canal). À trancher avant la tâche 4.6.
14. **Variante de pied « conversation »** (A5.2, C4) : champ + « Envoyer », **sans bouton « Annuler »**, alors que 3.2 veut « Annuler » et « Enregistrer » visibles en bas. La fermeture reste possible par la croix, Échap, le voile et le retour Android, avec confirmation si une saisie est en cours. Écart mineur à la lettre du 3.2, proposé pour ne pas encombrer un pied de 360 px ; à valider par le client et à ajouter au `design-system.md` §3.2 s'il l'accepte. Sinon : bouton « Fermer » secondaire à gauche du champ.
15. **Messages de chat dans le journal** : la règle 6 impose une entrée par création de donnée ; copier le texte des messages (canal « Bureau ») dans un journal lisible par les Superusers est discutable. Proposition : journaliser l'événement sans le texte. À valider avec `backend-dev`.
