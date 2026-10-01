# Écran — Assistant de création d'un club

Sources : CDC 1.4 (licence d'essai), 2.1, 2.3 (le créateur devient Président), 3.2 (exception : assistant pas à pas dans une grande modale), 3.5, 3.6, 4.1 (« Création d'un club », tableau des champs d'« Ajout d'un joueur »), 5.2, 6.7, 7.1, 7.5, 7.6 ; 10.2 n° 1, 18, 20, 24, 27. Schéma : `docs/lot0/schema-donnees.md` §3.1 (`User`), §3.2 (`Membership`), §3.4 (`MembershipRole`), §3.6 (`TermsVersion`, `TermsAcceptance`), §4.1 (`Club`), §4.2 (`ClubSettings`), §4.5 (`Licence`). Composants : `Modal` variante assistant (`Wizard`, design-system §3.2). Point d'entrée : `docs/ecrans/comptes-connexion.md` §3.

## 1. Objectif

Permettre à un responsable d'équipe de créer son club seul, depuis son smartphone, en moins de cinq minutes : identité du club, sa propre fiche joueur (il devient Président), licence d'essai, acceptation des CGU. Rien n'est enregistré avant le dernier clic : une seule transaction crée tout, ou rien.

## 2. Accès

- Ouvert depuis la page de connexion **neutre** (`/connexion`), bouton « Créer un club » ; adresse partageable `/connexion?action=creer-club`. Jamais depuis `/c/{slug}` ni depuis l'espace d'un club.
- Utilisateur **non connecté** dans cet onglet. Si une session est ouverte dans l'onglet, `/connexion` redirige déjà vers l'espace du club (voir `comptes-connexion.md` §2).
- Le point d'accès de création est public : l'API applique la limitation de requêtes du 7.6.

## 3. Structure

L'assistant est une modale `xl` (plein écran sur mobile) ouverte **par-dessus la page de connexion**, qui reste en dessous. Ce n'est pas une page (3.2).

**En-tête fixe**
- Titre : « Créer votre club ».
- Sous le titre : « Étape {n} sur 3 — {nom de l'étape} » (13 px, muted) et barre de progression fine (3 px, `--color-primary`, largeur 1/3, 2/3, 3/3).
- Croix « Fermer » à droite (zone 44 px).

**Corps défilant** : contenu de l'étape, champs en une colonne sur mobile ; deux colonnes à partir de 640 px uniquement pour des champs courts appariés (Ville + Pays, Devise + Fuseau horaire, Prénom + Nom, Poids + Taille).

**Pied fixe**, toujours visible (y compris clavier ouvert) : « Annuler » (secondaire) à gauche ; à droite « Précédent » (secondaire, masqué à l'étape 1) et l'action principale : « Suivant » aux étapes 1 et 2, « Créer mon club » à l'étape 3.

| Étape | Nom affiché |
| --- | --- |
| 1 | Votre club |
| 2 | Votre fiche joueur |
| 3 | Licence et validation |

Les trois étapes reprennent exactement les trois étapes du CDC 4.1 ; l'acceptation des CGU et le récapitulatif sont intégrés à l'étape 3 pour que l'indicateur reste « 1 sur 3 » à « 3 sur 3 » (voir §8).

**Règles de navigation**
- « Suivant » valide les champs de l'étape courante (validation locale, design-system §3.2 « Soumission ») ; en cas d'erreur, le corps défile jusqu'au premier champ en erreur. On ne peut pas sauter une étape.
- « Précédent » ne valide rien et conserve toutes les saisies.
- Aucune donnée n'est envoyée à l'API avant « Créer mon club » : pas de sauvegarde partielle en base, ni dans le stockage du navigateur (données personnelles). Le logo reste dans la mémoire de la page jusqu'à l'envoi final.
- Seul appel pendant la saisie : lecture des paramètres publics nécessaires à l'affichage (durée de l'essai, durée de grâce, version en vigueur des CGU et son texte, liste des fuseaux). Aucune de ces valeurs n'est écrite dans le code.

## 4. Étapes

### 4.1 Étape 1 — « Votre club »

Texte d'introduction (14 px, muted) : « Ces informations s'affichent sur l'espace de votre club. Vous pourrez les modifier plus tard. »

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Nom du club | TextField | Oui | 120 caractères max. ; « Ce champ est obligatoire. » ; « 120 caractères au maximum. » |
| Logo | FileField image (JPEG, PNG, WebP) + aperçu carré 72 px, bouton « Retirer » | Non | « Format non accepté : JPEG, PNG ou WebP. » ; « Fichier trop lourd : 10 Mo maximum. » Compressé dans le navigateur avant l'envoi final (6.7). Aide : « Le logo apparaît en haut du menu et sur la page de connexion de votre club. » |
| Couleur principale | Pastilles proposées depuis le logo + sélecteur de couleur + saisie hexadécimale | Non (voir §8) | « Saisissez une couleur au format #RRGGBB. » |
| Couleur secondaire | Idem | Non | Idem |
| Ville | TextField | Oui | 80 caractères max. ; « Ce champ est obligatoire. » |
| Pays | TextField avec suggestions (liste des pays en français), choix dans la liste | Oui | « Ce champ est obligatoire. » ; « Choisissez un pays dans la liste. » |
| Devise | SegmentedControl : « USD » / « CDF » | Oui | Défaut USD (4.1). Aide : « Devise de toutes les cotisations et dépenses du club. Elle ne pourra plus être changée une fois des paiements enregistrés. » |
| Fuseau horaire | Select natif (liste courte non-joueurs, autorisée par design-system §3.1) | Oui | Pré-rempli avec le fuseau du pays choisi (le premier s'il y en a plusieurs, fuseaux du pays en tête de liste) ; sans pays, fuseau de l'appareil. Aide : « Sert à dater les séances, les paiements et les échéances. » ; « Ce champ est obligatoire. » |

**Couleurs** (design-system §2.4) :
- Dès qu'un logo est choisi, l'analyse est faite **dans le navigateur** (rien n'est envoyé avant la fin) et un bloc s'affiche : « Couleurs proposées à partir du logo » + deux pastilles + bouton `secondary` `sm` « Utiliser ces couleurs ».
- Sans logo ni couleur : aide « Sans couleurs, votre club utilisera un thème neutre. Vous pourrez les ajouter plus tard. »
- **Aperçu** compact sous les couleurs (hauteur 88 px) : mini barre latérale (logo ou initiales, nom du club, un élément de menu actif) et un bouton principal aux couleurs choisies. Si l'ajustement de lisibilité s'applique : « Pour rester lisible, la teinte sera légèrement assombrie à l'affichage. »

L'adresse de connexion du club (`/c/{slug}`) n'est pas saisie : elle est attribuée par l'API à la création, à partir du nom (voir §8).

### 4.2 Étape 2 — « Votre fiche joueur »

Bandeau `info` en haut du corps : « Sur Vesta, tout membre du club est un joueur, le Président aussi. Vous deviendrez Président de ce club et figurerez dans son effectif. »

Mêmes champs que la modale « Ajouter un joueur » (`club-comite-bureau.md` §4.5, CDC 4.1), **sans « Parrain »** (le créateur n'en a pas besoin) **ni « Type de cotisation mensuelle »** (aucun type n'existe encore dans un club qui n'est pas créé) :

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Prénom | TextField, `autocomplete="given-name"` | Oui | 80 caractères max. ; « Ce champ est obligatoire. » |
| Nom | TextField, `autocomplete="family-name"` | Oui | 80 caractères max. ; « Ce champ est obligatoire. » |
| Email | TextField `email` | Oui | « Saisissez une adresse email valide. » ; à l'envoi final : « Cette adresse email est déjà utilisée. » (voir §6). Aide : « Ce sera votre identifiant de connexion. » |
| Téléphone (WhatsApp) | TextField `tel` | Non | « Numéro de téléphone invalide. » Aide : « Pour recevoir les reçus et les communiqués. » |
| Poste | SegmentedControl : Gardien / Défenseur / Milieu / Attaquant | Oui | « Choisissez un poste. » |
| Poste précis | TextField | Non | 60 caractères max. ; exemple en aide : « Arrière gauche » |
| Numéro de maillot | NumberField | Non | 1 à 99 ; « Saisissez un numéro entre 1 et 99. » |
| Date de naissance | DateField | Non | « La date ne peut pas être dans le futur. » |
| Poids (kg) | NumberField | Non | 30 à 200 ; « Saisissez un poids entre 30 et 200 kg. » |
| Taille (cm) | NumberField | Non | 120 à 230 ; « Saisissez une taille entre 120 et 230 cm. » |

Pas de champ photo : elle est demandée à la première connexion (4.1, `club-accueil.md` §3 étape 3).

Aide en bas du corps (13 px, muted) : « Vous n'avez pas besoin de parrain. Votre cotisation sera définie plus tard, quand le club aura créé ses types de cotisation. »

### 4.3 Étape 3 — « Licence et validation »

Trois blocs, dans l'ordre, puis la case des CGU.

**1. Licence d'essai** (`Card` à fond `--color-surface-muted`, pas de badge de statut) — valeurs lues dans les paramètres publics de l'API, jamais écrites dans le code :
- Titre (16 px/600) : « Licence d'essai gratuite de {durée d'essai} jours »
- Texte : « Elle démarre dès la création du club. À son terme, le club garde un accès complet pendant {durée de grâce} jours. Ensuite, il passe en lecture seule : vos données restent consultables et exportables. Vous serez prévenu avant l'échéance. »
- Texte (13 px, muted) : « Pour continuer au-delà de l'essai, ou si le support Vesta vous a déjà accordé une licence, le support l'activera sur votre club après sa création. »
- Aucune formule, aucun prix, aucun choix (10.2 n° 20) : ce bloc est une information, pas un champ.

**2. Récapitulatif** — deux sous-blocs en lecture, chacun avec un lien-bouton `ghost` `sm` « Modifier » qui ramène à l'étape concernée (les saisies sont conservées) :
- « Votre club » : logo (40 px) ou initiales, nom, pastilles des couleurs (ou « Thème neutre »), « {ville}, {pays} », « Devise : {devise} », « Fuseau : {fuseau} », « Adresse de connexion : attribuée à la création, à partir du nom du club ».
- « Votre fiche joueur » : prénom et nom, email, « {poste} · n° {numéro} » (« Sans numéro » si vide), téléphone, date de naissance, poids, taille (« Non renseigné » pour chaque valeur absente), « Rôle : Président ».

**3. Conditions générales** (10.2 n° 27, 7.5)
- Checkbox obligatoire : « J'accepte les conditions générales d'utilisation et la politique de confidentialité de Vesta (version {numéro de version}). »
- Lien « Lire les conditions générales » : ouvre une modale de lecture de niveau 2 (taille `lg`, plein écran sur mobile), titre « Conditions générales d'utilisation — version {numéro} », texte en 16 px, pied « Fermer ». Les CGU mentionnent les interventions du support sur les données (5.4) ; l'assistant ne les résume pas.
- Erreur au clic sur « Créer mon club » si la case n'est pas cochée : « Vous devez accepter les conditions générales pour créer votre club. »

**Bouton final** : « Créer mon club » (principal ; `loading` : « Création du club… »). Pendant l'envoi, l'assistant ne peut pas être fermé et tous les champs sont désactivés.

## 5. Envoi final et écran de succès

**Envoi** : une seule requête contient toutes les saisies des trois étapes, le logo, la version des CGU acceptée et une **clé d'idempotence** générée à l'ouverture de l'assistant (un double appui ou une nouvelle tentative après une coupure réseau ne crée jamais deux clubs). Côté API, une seule transaction (à spécifier par `backend-dev`) crée : le club et ses paramètres (valeurs par défaut du schéma, dont le seuil de quorum de 50 %, 10.2 n° 18, et un titulaire par rôle du bureau, 10.2 n° 24), la licence d'essai (10.2 n° 1 et 20), le compte (mot de passe initial = email, changement obligatoire, 7.1), l'adhésion, le rôle de Président, l'acceptation des CGU et les entrées du journal (5.2 : création du club, licence, compte, nomination). Si une seule écriture échoue, rien n'est créé.

**Succès** — le corps de l'assistant est remplacé par un écran de confirmation (pas un toast : les informations doivent être lues) ; l'indicateur d'étape et « Précédent » disparaissent ; la croix est masquée :
- Encadré vert (icône de validation) : « Votre club {nom du club} est créé. »
- « Adresse de connexion de votre club : vesta.eschoolb.com/c/{slug} » + bouton `secondary` `sm` « Copier l'adresse » (toast « Adresse copiée. »). Aide : « Partagez-la avec vos joueurs : la page de connexion affichera le logo et le nom de votre club. »
- « Licence d'essai jusqu'au {date de fin renvoyée par l'API}. »
- « Votre mot de passe provisoire est votre email. Vous allez devoir le changer tout de suite. »
- Pied : un seul bouton principal « Accéder à mon club ».

« Accéder à mon club » : la réponse de création ouvre la session de l'onglet dans l'état `must_change_password` (aucune donnée accessible). La modale bloquante « Changez votre mot de passe » s'ouvre immédiatement par-dessus la page de connexion (`comptes-connexion.md` §4.2), puis la modale des consentements du 7.5 (`club-accueil.md` §3 étape 2 ; les CGU venant d'être acceptées, seules les cases de consentement aux données de santé et à la publication de la carte de joueur restent à remplir), puis l'accueil du club avec la modale « Ajoutez votre photo ».

## 6. États et erreurs

| Situation | Affichage |
| --- | --- |
| Ouverture de l'assistant | Titre et indicateur affichés immédiatement ; le corps de l'étape 1 est utilisable tout de suite. Les paramètres publics (fuseaux, CGU, durées) se chargent en arrière-plan : squelette sur le Select « Fuseau horaire » et sur le bloc licence de l'étape 3 tant qu'ils ne sont pas reçus. |
| Paramètres publics indisponibles | À l'étape 3 : bloc licence et case des CGU remplacés par `EmptyState` variante erreur « Impossible de charger les conditions de la licence et les CGU. » + « Réessayer » ; « Créer mon club » désactivé tant qu'ils ne sont pas chargés. |
| Hors connexion | Saisie possible aux étapes 1 et 2 ; à l'étape 3, `Banner` `info` « Vous êtes hors connexion. La création du club nécessite un réseau. Vos saisies sont conservées tant que cette fenêtre reste ouverte. » ; « Créer mon club » désactivé, réactivé au retour du réseau. |
| Validation locale en échec | Erreurs sous les champs de l'étape courante (§4) ; focus sur le premier champ en erreur. |
| Email déjà utilisé (réponse de l'API) | Retour automatique à l'étape 2, erreur sous « Email » : « Cette adresse email est déjà utilisée. » ; les autres saisies sont conservées. Voir §8 pour le cas du joueur qui a déjà un compte. |
| Autre erreur de champ renvoyée par l'API | Retour à l'étape du champ, erreur sous le champ. |
| Version des CGU remplacée pendant la saisie | Étape 3 : case décochée, nouveau numéro de version affiché, bandeau `warning` « Les conditions générales ont été mises à jour. Lisez la nouvelle version et acceptez-la pour continuer. » |
| Limitation de requêtes (7.6) | Bandeau d'erreur du corps : « Trop de tentatives depuis cet appareil. Réessayez dans quelques minutes. » |
| Réseau ou serveur à l'envoi | Bandeau d'erreur en haut du corps de l'étape 3 : « La création n'a pas abouti. Aucune donnée n'a été enregistrée. Vérifiez votre réseau et réessayez. » ; toutes les saisies sont conservées ; « Créer mon club » redevient actif (même clé d'idempotence). |
| Envoi long (> 10 s) | Sous le bouton : « Le chargement prend plus de temps que prévu. » ; l'envoi continue, fermeture toujours impossible. |
| Succès | Écran de confirmation §5. |

**Fermeture** (croix, Échap, clic sur le voile, « Annuler », retour Android, glissement vers le bas) :
- Aucune saisie : fermeture immédiate, retour à la page de connexion.
- Au moins un champ saisi, à n'importe quelle étape : `ConfirmDialog` « Abandonner la création du club ? » — texte « Les informations saisies seront perdues. Rien n'a encore été enregistré. » — boutons « Continuer la saisie » (focus par défaut) / « Abandonner » (danger).
- Fermeture de l'onglet ou rechargement avec des saisies : avertissement natif du navigateur (`beforeunload`).
- Pendant l'envoi : fermeture impossible.
- Écran de succès : seule issue « Accéder à mon club ».

## 7. Mobile (360 px) et ordinateur

- **360 px** : plein écran. En-tête fixe de 56 px + ligne d'étape et barre de progression. Pied fixe de 56 px au-dessus du clavier : « Annuler » réduit à un lien-bouton `ghost` à gauche ; « Précédent » et l'action principale se partagent le reste (40 px de haut). À l'étape 1, « Annuler » et « Suivant » se partagent la largeur. Champs en une colonne ; le SegmentedControl « Poste » passe en grille 2 × 2 sous 400 px pour garder les libellés entiers ; l'aperçu des couleurs tient sur une ligne. Étape 3 : bloc licence, puis récapitulatif replié par défaut en deux lignes « Votre club — {nom} · Modifier » et « Votre fiche joueur — {prénom nom} · Modifier » (dépliables), puis la case des CGU juste au-dessus du pied, pour éviter un long défilement.
- **≥ 640 px** : fenêtre centrée de 960 px (`xl`), hauteur max. 90 vh. Champs courts appariés sur deux colonnes (§3). Étape 1 : colonne de gauche pour nom, logo, couleurs et aperçu ; colonne de droite pour ville, pays, devise, fuseau. Étape 3 : récapitulatif déplié, les deux sous-blocs côte à côte.
- Pied sur ordinateur : « Annuler » à gauche ; « Précédent » et action principale alignés à droite, largeur automatique.

## 8. Décisions par défaut et points ouverts

- **Décidé, 10.2 n° 1 et n° 20** : essai de 30 jours, grâce de 15 jours ; aucune formule ni tarif, l'étape 3 est une simple information (durées lues dans l'API).
- **Décidé, 10.2 n° 27** : acceptation des CGU obligatoire, version tracée (`TermsAcceptance`) dans la même transaction que la création.
- **Décidé, 10.2 n° 18 et n° 24** : seuil de quorum de 50 % et un titulaire par rôle du bureau, posés par défaut à la création (aucun champ dans l'assistant ; modifiables ensuite par le Président).
- **Source à préciser** : ville et pays sont obligatoires d'après le schéma de données du Lot 0 (`schema-donnees.md` §4.1), pas d'après une entrée numérotée du 10.2 ; le CDC 4.1 les liste sans préciser leur caractère obligatoire.
- **Choix de présentation (à valider sur maquette)** : trois étapes, calquées sur les trois étapes du CDC 4.1, l'acceptation des CGU et le récapitulatif étant intégrés à l'étape 3. Alternative possible : une 4e étape « Récapitulatif » (« Étape 4 sur 4 »).
- **Point ouvert — mot de passe du créateur** : application littérale du 7.1 (mot de passe initial = email, changement immédiatement exigé, §5). Alternative à soumettre au client : faire choisir le mot de passe directement à l'étape 2, ce qui éviterait un compte dont le mot de passe est l'email pendant quelques secondes. Non tranché ici.
- **Point ouvert — statut d'adhésion du créateur** : le cycle « En attente → Inscrit » exige adhésion payée et parrain signé (4.1, 4.3) ; le créateur n'a ni parrain ni type de cotisation. Proposition, par analogie avec les membres historiques importés (4.1) : adhésion directement « Inscrit ». À trancher par le client ; à confirmer avec `finance-engine` pour le solde d'un Président sans type de cotisation rattaché.
- **Point ouvert — email déjà inscrit sur Vesta** : le compte est global (6.3) et l'email unique sur la plateforme. Un joueur qui a déjà un compte (dans un autre club, ou parti) ne peut pas créer de club avec son email ; le cahier des charges ne dit pas s'il doit se connecter d'abord pour créer un club à partir de son compte existant. Comportement provisoire : erreur « Cette adresse email est déjà utilisée. » à l'étape 2. Décision du client nécessaire.
- **Point ouvert — adresse du club (`slug`)** : non listée parmi les champs du 4.1. Proposition : générée par l'API à partir du nom (minuscules, sans accents, tirets, suffixe numérique si déjà prise), affichée à l'écran de succès, modifiable ensuite par le Président seulement si le client le décide (un changement casserait les liens déjà partagés).
- **Point ouvert — licence fournie par le Superuser** : le 4.1 évoque « la licence d'essai (ou une licence fournie par le Superuser) ». Aucun mécanisme de code de licence n'est prévu au cahier des charges ; comportement provisoire : le club démarre toujours en essai et le support active ensuite la licence depuis son espace (`superuser-espace.md` §4.1, action « Activer »). Texte de l'étape 3 rédigé dans ce sens.
- **Point ouvert — devises** : seules USD et CDF sont proposées (4.1). Un club hors RDC n'a pas de devise adaptée ; à trancher avant l'ouverture à d'autres pays.
- **Point ouvert — couleurs** : facultatives ici (conforme au schéma §4.1, `primary_color` et `secondary_color` facultatifs, et à la règle de repli du design-system §2.4), alors que la modale « Identité du club » (`club-comite-bureau.md` §4.1) les marque obligatoires. Harmonisation proposée : facultatives dans les deux modales.
- **Point ouvert — une ou deux cases pour les CGU** : une seule case ici (CGU et politique de confidentialité), car le schéma ne trace qu'une `TermsVersion` ; `club-accueil.md` §3 parle de « cases obligatoires » au pluriel. À harmoniser.
- **Observation (hors de cet écran)** : `superuser-espace.md` §3.2 colore le badge de licence « Essai » en violet et « Suspendue » en rouge, alors que `design-system.md` §2.5 propose « Essai » vert et « Suspendue » violet. L'assistant n'affiche volontairement aucun badge de licence ; l'écart est à corriger dans l'une des deux specs.
- Pas de CAPTCHA ni de vérification de l'email : non prévus au cahier des charges. La protection repose sur la limitation de requêtes (7.6). À examiner par `security-auditor` (création de clubs en masse, création d'un compte avec l'email d'un tiers).
