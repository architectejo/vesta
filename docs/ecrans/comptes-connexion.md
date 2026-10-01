# Écran — Connexion

Sources : CDC 3.1, 3.2, 3.5 (filigrane du club sur la page de connexion), 3.6, 4.1 (mot de passe initial, mot de passe oublié, critère d'acceptation), 5.2 (connexion, échec de connexion, changement de mot de passe, réinitialisation), 7.1, 7.3, 7.4, 7.5, 7.6 ; 10.2 n° 13, 19, 21, 27. Schéma : `docs/lot0/schema-donnees.md` §3.1 (`User`), §3.6 (`TermsVersion`), §4.1 (`Club.slug`, `Club.logo`), §13.2 (`PasswordResetRequest`). Composants : `docs/lot0/design-system.md`. Suite du parcours de première connexion : `docs/ecrans/club-accueil.md` §3.

## 1. Objectif

Permettre à un joueur ou à un Superuser d'entrer dans Vesta en quelques secondes, sur smartphone, avec un réseau faible, et reconnaître immédiatement son club quand il arrive par l'adresse de celui-ci. Aucun accès aux données tant que le mot de passe initial ou temporaire n'a pas été changé.

## 2. Accès et adresses

| Adresse | Présentation | Qui |
| --- | --- | --- |
| `/connexion` | **Neutre** : aucun logo, aucun nom, aucune couleur de club (7.3) | Tout le monde, Superusers compris |
| `/c/{slug}` | **Identité du club** : logo en filigrane, logo et nom du club, couleurs du club en thème Classic (3.5, 7.3) | Tout le monde ; le club est identifié par `Club.slug` |

- Le nom, le logo et les couleurs viennent de l'API publique d'identité du club (lecture de `Club` seulement, jamais de `ClubSettings`). **Aucun nom de club, aucun logo ni aucune couleur de club n'est écrit dans le code.**
- L'adresse `/c/{slug}` n'est qu'une présentation : après connexion, l'interface prend l'identité du club de l'adhésion en cours du joueur (7.3, 6.3), même si ce n'est pas le club de l'adresse. Aucune erreur n'est affichée dans ce cas.
- Un utilisateur déjà connecté **dans cet onglet** qui ouvre `/connexion` ou `/c/{slug}` est renvoyé vers `/` (joueur) ou `/admin` (Superuser).
- Session propre à chaque onglet (7.4, 10.2 n° 13) : un nouvel onglet ou un lien collé arrive sur cette page. Le lien demandé est conservé dans le paramètre `?suite=` et rouvert après connexion (chemins internes uniquement ; tout autre valeur est ignorée et remplacée par `/`).

## 3. Structure de la page

Cas particulier reconnu de la règle 3.2 : une page de connexion est nécessairement une page dédiée (7.3). C'est la **seule** page de l'application qui contient un formulaire (voir §7). Les deux autres formulaires de ce parcours (« Mot de passe oublié », « Changez votre mot de passe ») sont des modales.

Pas de barre latérale, pas de barre supérieure. De haut en bas :

1. **Zone d'identité** (au-dessus de la carte)
   - `/c/{slug}` : logo du club 40 px (rayon 8 px ; à défaut, carré aux initiales du club) + nom du club (18 px/600, deux lignes au plus, sans troncature en dessous). Derrière cette zone, **filigrane** : le logo du club, 200 px de large sur mobile (280 px ≥ 640 px), centré, opacité 8 % (Clair, Classic) ou 10 % (Sombre), `aria-hidden="true"`, non cliquable. Le filigrane n'est **jamais** placé sous un champ, un libellé ou un message : la carte du formulaire a un fond opaque `--color-surface`, ce qui garantit le contraste en plein soleil.
   - `/connexion` : mot « Vesta » (18 px/600) seul, sans logo de club ni filigrane.
2. **Carte de connexion** (`Card`, 400 px de large au plus)
   - Titre `h1` : « Connexion » (20 px/600).
   - Ligne de contexte (14 px, muted) : `/c/{slug}` : « Accédez à l'espace de {nom du club}. » ; `/connexion` : « Accédez à l'espace de votre club. »
   - Bandeau d'erreur globale (réservé, vide par défaut, voir §5).
   - Champs :

     | Champ | Composant | Règle / erreur |
     | --- | --- | --- |
     | Email | TextField `type="email"`, `autocomplete="username"`, `inputmode="email"`, `autocapitalize="none"`, espaces retirés avant envoi | « Ce champ est obligatoire. » ; « Saisissez une adresse email valide. » |
     | Mot de passe | TextField `type="password"`, `autocomplete="current-password"`, bouton texte « Afficher » / « Masquer » à droite dans le champ (zone 44 px) | « Ce champ est obligatoire. » |

   - Ligne d'actions : à gauche, lien-bouton `ghost` « Mot de passe oublié ? » (ouvre la modale §4.1) ; à droite, bouton `primary` `md` « Se connecter » (largeur automatique, pas pleine largeur, design-system 1.3). Entrée dans un champ soumet le formulaire.
   - Aide sous la ligne d'actions (13 px, muted) : « Par sécurité, chaque onglet demande sa propre connexion. »
   - **Pas de case « Rester connecté »** ni aucune option qui partagerait la session entre onglets (7.4).
3. **Lien de création de club** — uniquement sur `/connexion` (jamais sur `/c/{slug}`), sous la carte : texte 14 px « Vous voulez inscrire votre équipe sur Vesta ? » + bouton `secondary` `sm` « Créer un club ». Ouvre l'assistant `docs/ecrans/clubs-creation.md` par-dessus cette page (adresse `/connexion?action=creer-club`, pour que le lien puisse être partagé et que le retour arrière ferme l'assistant).
4. **Footer** unique (design-system §3.10), non collant.

Une seule action principale sur la page : « Se connecter ».

**Thème** avant connexion (aucune préférence d'utilisateur n'est encore connue) : le dernier thème mémorisé sur l'appareil (`localStorage`) s'il existe ; sinon, sur `/c/{slug}`, Classic avec les couleurs du club (design-system 2.4, ajustement de lisibilité compris) ; sur `/connexion`, Clair ou Sombre selon `prefers-color-scheme`. Après connexion, la préférence du compte s'applique.

## 4. Modales

### 4.1 « Mot de passe oublié » (4.1, 7.1, 10.2 n° 21) — taille `sm` (panneau bas sur mobile)

Titre : « Mot de passe oublié ».

Texte d'explication (14 px) : « Indiquez l'email de votre compte. Votre demande sera transmise au support Vesta, qui réinitialisera votre mot de passe. Vous recevrez un mot de passe temporaire, valable 48 heures, que vous devrez changer dès votre prochaine connexion. »

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Email | TextField `email`, pré-rempli avec l'email déjà saisi sur la page | Oui | « Ce champ est obligatoire. » ; « Saisissez une adresse email valide. » |

Pied : « Annuler » / « Envoyer la demande » (état `loading` : « Envoi… »). Confirmation d'abandon seulement si l'email a été modifié par rapport à la valeur pré-remplie.

Succès — la modale **reste ouverte** et son corps est remplacé par un message (le joueur doit le lire, un toast de 4 s ne suffit pas) :
- Encadré vert (icône de validation) : « Demande envoyée. »
- Texte : « Si un compte existe avec cette adresse, le support Vesta vous transmettra un mot de passe temporaire. Il sera valable 48 heures. À votre prochaine connexion, vous devrez choisir un nouveau mot de passe. »
- Pied : « Fermer » seul.

**Même message de succès, que l'email corresponde ou non à un compte**, pour ne pas révéler quelles adresses sont inscrites. L'API applique la limitation de requêtes du 7.6 sur ce point d'accès ; au-delà : bandeau « Trop de demandes envoyées. Réessayez dans quelques minutes. »

Erreurs : réseau et serveur = messages standard (design-system §4) dans le bandeau d'erreur du corps ; hors connexion : bouton « Envoyer la demande » désactivé et bandeau « Cette action nécessite une connexion. »

Journal (5.2) : chaque demande enregistrée crée une `PasswordResetRequest` (schéma §13.2) et une entrée « demande de réinitialisation ».

### 4.2 « Changez votre mot de passe » — modale **bloquante** (4.1, 7.1, 10.2 n° 21) — taille `md` (plein écran sur mobile)

Même modale que `club-accueil.md` §3 étape 1 ; précisée ici pour son point de déclenchement.

**Déclenchement** : juste après une connexion réussie, si l'API signale `must_change_password` (mot de passe initial = email, ou mot de passe temporaire donné par le support). La modale s'ouvre **par-dessus la page de connexion**, pas par-dessus l'accueil : aucune page du club n'est chargée, aucune donnée du club ni du joueur n'est demandée à l'API. Tant que le changement n'est pas fait, l'API refuse tout autre appel que « changer le mot de passe » et « se déconnecter » (contrôle côté API, l'interface ne fait que le refléter — critère d'acceptation 4.1 et 9.2 Lot 1).

Variante bloquante du design system (§3.2) : **pas de croix, Échap et clic sur le voile inactifs**, bouton retour d'Android sans effet. Seule issue secondaire : « Se déconnecter ».

Titre : « Changez votre mot de passe ».

Texte, selon le cas renvoyé par l'API :
- Mot de passe initial : « Pour protéger votre compte, choisissez un nouveau mot de passe. Tant que ce n'est pas fait, vous ne pouvez consulter aucune donnée. »
- Mot de passe temporaire : « Vous vous êtes connecté avec un mot de passe temporaire. Choisissez maintenant votre propre mot de passe. Tant que ce n'est pas fait, vous ne pouvez consulter aucune donnée. »

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Nouveau mot de passe | TextField `password`, `autocomplete="new-password"`, bouton « Afficher » | Oui | « Le mot de passe doit contenir au moins 8 caractères. » ; « Le mot de passe doit être différent de votre email. » ; mot de passe temporaire uniquement, voir §7 : « Choisissez un mot de passe différent du mot de passe temporaire. » |
| Confirmez le mot de passe | TextField `password`, `autocomplete="new-password"` | Oui | « Les deux mots de passe ne correspondent pas. » |

Aide sous le premier champ (13 px, muted) : « 8 caractères minimum, différent de votre email. »

Pied : « Se déconnecter » (secondaire, à gauche, sans confirmation) / « Enregistrer » (principal ; `loading` : « Enregistrement… »).

Succès : toast « Mot de passe modifié. » puis suite du parcours de première connexion, dans l'ordre de `club-accueil.md` §3 :
1. si une version des CGU n'a pas encore été acceptée par ce compte, ou pour les consentements du 7.5 non encore recueillis : modale bloquante « Vos données et votre consentement » (`club-accueil.md` §3 étape 2), elle aussi **par-dessus la page de connexion** ;
2. redirection vers la page demandée (`?suite=`) ou `/` (Superuser : `/admin`) ;
3. sur l'accueil, modale non bloquante « Ajoutez votre photo » si le joueur n'a pas de photo.

Erreurs :
- Session courte expirée pendant la saisie (jeton de 15 minutes, 7.1) : la modale se ferme, la page de connexion affiche le message standard dans son bandeau d'erreur : « Votre session a expiré. Reconnectez-vous. »
- Réseau, serveur : messages standard dans le bandeau d'erreur du corps ; les champs saisis sont conservés.

Journal (5.2) : « changement de mot de passe ».

## 5. États

### 5.1 Page

| Situation | Affichage |
| --- | --- |
| Chargement de l'identité du club (`/c/{slug}`) | La carte de connexion s'affiche **immédiatement** et reste utilisable ; seule la zone d'identité montre un squelette (carré 40 px + ligne de 60 %). Le formulaire n'attend jamais l'identité du club (réseau faible). |
| Identité du club indisponible (erreur réseau) | Zone d'identité remplacée par la présentation neutre, sans message d'erreur ; la connexion reste possible. |
| Adresse `/c/{slug}` inconnue | Présentation neutre + `Banner` `info` en haut de la carte : « Aucun club ne correspond à l'adresse « /c/{slug} ». Vous pouvez vous connecter ici : votre espace s'ouvrira sur votre club. » |
| Hors connexion | `Banner` `info` : « Vous êtes hors connexion. La connexion nécessite un réseau. » ; « Se connecter » désactivé ; il se réactive seul au retour du réseau. |
| Envoi en cours | « Se connecter » en état `loading` : « Connexion… » ; champs désactivés. Au-delà de 10 s : « Le chargement prend plus de temps que prévu. » + « Réessayer » (design-system 3.5). |

### 5.2 Résultats d'une tentative de connexion

Les erreurs d'authentification s'affichent dans le **bandeau d'erreur globale** de la carte (`Banner` `danger`, jamais sous un champ, pour ne pas indiquer lequel des deux est faux). Le champ « Mot de passe » est vidé, l'email est conservé, le focus revient sur « Mot de passe ».

| Cas (renvoyé par l'API) | Message exact | Effet |
| --- | --- | --- |
| Email ou mot de passe faux | « Email ou mot de passe incorrect. » | — |
| Idem, 2 essais ou moins avant blocage | « Email ou mot de passe incorrect. Encore {n} essai(s) avant un blocage de 15 minutes. » | Nombre fourni par l'API (voir §7) |
| Blocage après 5 échecs (7.1) | « Trop de tentatives. Pour protéger votre compte, la connexion est bloquée pendant 15 minutes. Réessayez dans {m} min. » — à moins d'une minute : « Réessayez dans moins d'une minute. » | « Se connecter » désactivé jusqu'à l'heure de fin renvoyée par l'API (`login_locked_until`) ; décompte mis à jour chaque minute sur l'appareil ; bouton réactivé et bandeau retiré à l'échéance. « Mot de passe oublié ? » reste disponible. |
| Mot de passe temporaire expiré (48 h, 10.2 n° 21) | « Ce mot de passe temporaire a expiré. Faites une nouvelle demande avec « Mot de passe oublié ? ». » | Lien « Mot de passe oublié ? » mis en évidence (focus) |
| Compte désactivé par le support (4.18) — affiché seulement si le mot de passe est juste | « Ce compte est désactivé. Contactez le support Vesta. » | — |
| Licence du club suspendue (10.2 n° 19) — affiché seulement si le mot de passe est juste | « L'accès à votre club est suspendu. Contactez le Président de votre club. » | Aucune session ouverte |
| Aucune adhésion en cours (joueur parti, sans nouveau club) | Voir §7 (point ouvert) | — |
| Limitation de requêtes (7.6) | « Trop de tentatives depuis cet appareil. Réessayez dans quelques minutes. » | — |
| Réseau, serveur | Messages standard (design-system §4) | Rien n'est compté comme un échec |
| Succès, `must_change_password` | — | Modale bloquante §4.2 |
| Succès, nouvelle version des CGU à accepter (10.2 n° 27) | — | Modale bloquante « Vos données et votre consentement » (`club-accueil.md` §3 étape 2) par-dessus la page de connexion |
| Succès, cas général | — | Redirection vers `?suite=` ou `/` (Superuser : `/admin`) ; l'interface prend l'identité du club du joueur ; licence expirée au-delà de la grâce : bandeau lecture seule standard sur les pages |

Journal (5.2) : chaque connexion réussie et chaque échec ; chaque blocage (déclenche l'alerte « Échecs de connexion répétés » de l'espace Superuser, 5.5).

## 6. Mobile (360 px) et ordinateur

- **360 px** : marges 12 px ; zone d'identité en haut (logo 40 px + nom sur une ligne, filigrane derrière cette zone uniquement) ; carte pleine largeur (moins les marges), padding 12 px ; « Mot de passe oublié ? » et « Se connecter » sur la même ligne (lien à gauche, bouton de 40 px à droite, largeur automatique). Pas de mise au point automatique sur le champ email (le clavier masquerait l'identité du club). Le formulaire complet tient sans défilement au-dessus du clavier : titre, contexte, deux champs et la ligne d'actions (hauteur utile visée ≤ 420 px). Footer sous le lien « Créer un club », non collant.
- **≥ 640 px** : carte de 400 px centrée horizontalement, placée dans le premier tiers de la hauteur (pas centrée verticalement sur un grand écran) ; filigrane de 280 px derrière la zone d'identité ; mise au point automatique sur le champ email.
- **≥ 1024 px** : même composition, rien de plus (pas d'image décorative, pas de colonne de présentation).
- Modale §4.1 : panneau bas sur mobile, 400 px centrée sur ordinateur. Modale §4.2 : plein écran sur mobile (pied collé au-dessus du clavier), 560 px centrée sur ordinateur.

## 7. Décisions par défaut et points ouverts

- **Décidé, 10.2 n° 13** : session propre à chaque onglet ; aucune case « Rester connecté » ; mention « Par sécurité, chaque onglet demande sa propre connexion. »
- **Décidé, 10.2 n° 21** : mot de passe oublié traité par le support (Superuser) par mot de passe temporaire de 8 caractères, valable 48 h, changement obligatoire à la connexion suivante ; la création initiale d'un compte garde mot de passe = email.
- **Décidé, 10.2 n° 19** : licence suspendue = accès bloqué (message §5.2), pas de lecture seule.
- **Décidé, 10.2 n° 27** : une nouvelle version des CGU est redemandée à la connexion, avant tout accès aux données.
- **À valider par le client (3.2)** : la page de connexion est une page qui ne contient qu'un formulaire. Le 7.3 l'impose implicitement, mais le 3.2 exige qu'une page dédiée soit « justifiée et validée par le client ». Validation écrite à demander avec la maquette.
- **Point ouvert, sécurité (à confirmer par `security-auditor`)** : pour ne pas révéler quelles adresses ont un compte, l'API doit répondre de la même façon (même message, même compteur d'essais, même blocage de 15 minutes, temps de réponse comparable) qu'un email existe ou non ; les messages « compte désactivé » et « licence suspendue » ne sont renvoyés que si le mot de passe est juste. Le compteur « Encore {n} essai(s) » n'est affiché que si l'API le fournit dans ces conditions ; sinon il est retiré et seul le message générique reste.
- **Proposition à valider** : refuser un nouveau mot de passe identique au mot de passe temporaire (le 7.1 n'exige que « différent de l'email »). Position prudente appliquée à titre provisoire.
- **Point ouvert (hors écran, signalé)** : au MVP, la carte « Demandes de réinitialisation » de l'espace Superuser est reportée après le Lot 5 (`backlog-post-mvp.md`, entrée 10) et le tableau 4.17 ne prévoit aucune notification au Superuser. Une demande envoyée depuis cette modale n'est donc visible que dans la modale « Utilisateur » (date de la dernière demande), sans alerte : risque qu'aucune demande ne soit traitée. Décision du client nécessaire (notification in-app au Superuser, ou filtre « Demande de réinitialisation en attente » dans le tableau des utilisateurs).
- **Point ouvert** : message et comportement pour un compte sans adhésion en cours (joueur parti sans nouveau club). Non couvert par le cahier des charges. Proposition : « Votre compte n'est rattaché à aucun club pour l'instant. » sans ouverture de session.
- **Point ouvert** : licence résiliée — le 1.4 ne décrit que la suspension (accès bloqué) et l'expiration (lecture seule). Proposition provisoire, la plus prudente : même traitement que la suspension (accès bloqué, même message).
- **Proposition** : thème avant connexion (§3) et filigrane limité à la zone d'identité (lisibilité en plein soleil), à valider sur la maquette.
