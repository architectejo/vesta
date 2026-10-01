# Écran — Assemblées générales

Sources : CDC 3.2 (assistant pas à pas pour la création d'une AG), 3.5 (nom et logo du club sur les PDF), 4.15, 4.5.2 (dérogations signalées à la prochaine AG), 4.17 (convocation), 5.2 (journal : « AG »), 7.2 (signature du PV par PIN), 9.2 (critère du Lot 4 : « un PV d'AG est signé et généré en PDF »), 9.3 étape 8, 10.1 annexe D, matrice 2.4, 10.2 n° 18, 24 et 28. Composants : `Modal` variante assistant et à onglets, `PinPrompt`, `ConfirmDialog`, `Banner`, `docs/lot0/design-system.md`.

> **Révision du 29/09/2026 (tâche 4.1 du Lot 4)** : compléments sans changement de structure — PDF et accès au fichier (§4.6), journal et notifications (§4.7), filtre des présences, comportement si le quorum n'est pas atteint, contrôle du total des votes rendu non bloquant, date d'appréciation de la vacance du VP alignée sur `schema-donnees.md` §9.5, plusieurs titulaires du poste de VP (10.2 n° 24), hors connexion et lecture seule, textes ajoutés (§8). Les ajouts sont signalés « (révision 29/09) ».

## 1. Objectif

Convoquer, tenir et clore une assemblée générale dans Vesta : ordre du jour, présences et quorum, votes, procès-verbal signé et PDF.

## 2. Accès

Route `/club/assemblees`. Entrée « Club › Assemblées générales ».

| Action | Qui |
| --- | --- |
| Consulter la page, les AG, les décisions, le PV signé | Tous les joueurs (L) |
| Convoquer (assistant), pointer les présences, saisir les votes, rédiger le PV | Président, Vice-président |
| Signer le PV (PIN) | Président et Vice-président, chacun pour sa signature ; Président seul si le poste de VP est vacant (Q10) |
| Définir le seuil de quorum du club | Président, Vice-président (matrice 2.4, « Assemblées générales » : É) |
| Télécharger le PV signé (PDF) (révision 29/09) | Tous les joueurs du club (L), par une vue authentifiée de l'API qui vérifie le club (§4.6) |

Les droits sont renvoyés par l'API avec chaque AG (`can_edit`, `can_sign`, etc.) ; l'interface n'affiche un bouton que si le droit correspondant est présent, elle ne déduit jamais un droit du libellé d'un rôle. Un joueur qui cumule Président et un autre rôle signe **une seule fois**, au titre de Président. Superuser : pas d'accès à cette page hors session de support (Ghost Mode) ; toute action qu'il y fait s'affiche « Action effectuée par le Système Vesta » (5.4).

## 3. Structure de la page

**En-tête** : titre « Assemblées générales » ; contexte « {nom du club} · Saison {saison} ». Action principale (Président, VP) : « Convoquer une AG ». Menu « … » (Président, VP) : « Seuil de quorum » → modale §4.5.

1. **À venir** — cartes (4.15) : date longue et heure, type (« Ordinaire » / « Extraordinaire »), lieu, `StatusBadge` « Convoquée », nombre de points à l'ordre du jour. Clic → modale « Assemblée générale ».
2. **Passées** — 5 dernières cartes (3.3), « Voir plus » : date, type, badge « PV à signer » ou « Clôturée », décisions clés (2 premières, une ligne chacune). Clic → même modale.

Footer.

## 4. Modales

### 4.1 « Convoquer une assemblée générale » — assistant `xl`, 3 étapes (3.2)

**Étape 1 sur 3 — Informations**

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Type | SegmentedControl : Ordinaire / Extraordinaire | Oui | — |
| Date | DateField | Oui | « La date doit être dans le futur. » |
| Heure | TimeField | Oui | — |
| Lieu | TextField | Oui | — |

**Étape 2 sur 3 — Ordre du jour**

- Liste de points ; chaque point : « Intitulé » (TextField, obligatoire), « Description » (TextArea, facultatif). Boutons par point : « Monter », « Descendre », « Retirer » (icônes 40 px avec `aria-label`). Bouton « Ajouter un point ».
- **Proposition de confort `ui-designer`, pas une exigence du cahier des charges** : si l'API signale des dérogations depuis la dernière AG (4.5.2 dit seulement qu'elles sont « signalées à la prochaine assemblée générale », sans imposer de point d'ordre du jour), un point « Dérogations accordées depuis la dernière AG » est ajouté d'office, non supprimable, avec la liste en lecture. À valider par le client (circuit 9.4) ; s'il la rejette, les dérogations restent simplement listées en lecture dans la modale de l'AG.
- Erreur : « Ajoutez au moins un point à l'ordre du jour. »

**Étape 3 sur 3 — Récapitulatif**

Résumé des étapes 1 et 2 ; texte : « Tous les joueurs ({n}) recevront la convocation par notification et par email. Un rappel sera envoyé la veille. » Boutons : « Précédent » / « Convoquer ». Succès : « Assemblée convoquée. Les joueurs ont été prévenus. »

### 4.2 « Assemblée générale » (détail) — taille `lg`, à onglets

En-tête : « AG {ordinaire / extraordinaire} du {date} » ; sous-titre « {heure} · {lieu} » ; `StatusBadge`. Pied : « Fermer » (+ action principale selon l'onglet). Onglets :

**« Ordre du jour »** — points numérotés, descriptions. Lecture pour tous.

**« Présences »** (4.15) — ouvert le jour de l'AG pour Président et VP ; sinon lecture.
- Bandeau quorum : « {n} présents sur {total} joueurs actifs ({x} %) · Quorum requis : {seuil} % — atteint » (vert) / « — non atteint » (orange). Le seuil est le **paramètre de quorum configurable par club** (pourcentage des joueurs actifs à la date de l'AG, **50 % par défaut**, décidé, cahier des charges 10.2 n° 18) ; il est toujours défini. Le calcul « atteint / non atteint » est fait par l'API, jamais par l'interface.
- Recherche « Nom ou numéro » ; liste de joueurs avec bouton « Présent » (même comportement que le pointage de séance, sans notion de retard). Correction par appui sur la ligne → « Retirer la présence » (ConfirmDialog).
- (révision 29/09) Sous la recherche, `SegmentedControl` « Tous » / « Non pointés » / « Présents », avec le compteur de chaque vue (« Non pointés (12) »). Défaut : « Non pointés », pour que la liste raccourcisse au fil des arrivées. La liste ne montre **aucun badge de statut** (ni dette, ni suspension, ni aptitude) : la présence à l'AG ne dépend pas de ces statuts dans le cahier des charges, et un badge exposerait des situations que les coéquipiers ne doivent pas voir (10.2 n° 16). Les joueurs listés sont ceux que l'API compte comme « actifs à la date de l'AG » (dénominateur du quorum) ; l'interface ne filtre rien elle-même.
- (révision 29/09) Chaque appui sur « Présent » est enregistré immédiatement (mise à jour optimiste, indicateur 16 px sur la ligne, `design-system.md` §3.5) ; le bandeau quorum se met à jour à la réponse de l'API. Le pointage d'AG **ne fait pas partie des actions hors connexion** (6.6) : sans réseau, les boutons « Présent » sont désactivés et le bandeau `info` affiche « Cette action nécessite une connexion. »
- (révision 29/09) **Quorum non atteint** : le cahier des charges demande le calcul du quorum (4.15) mais ne dit pas ce qu'il empêche. L'interface **ne bloque rien** d'elle-même : le bandeau reste orange et, dans l'onglet « Décisions », un `Banner warning` rappelle « Quorum non atteint : {n} présents sur {total} ({x} %), seuil {seuil} %. » Si l'API refuse la saisie d'un vote pour cette raison, son message est affiché dans le bandeau d'erreur de la modale. Voir point ouvert §7.

**« Décisions »** (4.15) — un bloc par point : votes « Pour {n} · Contre {n} · Abstention {n} », décision retenue, action liée éventuelle. Action (Président, VP) sur chaque point : « Saisir le vote » → modale §4.3.

**« Procès-verbal »** (4.15) —
- Texte du PV (lecture, 16 px).
- Signatures : « Président : {nom} — signé le {date} » ou « en attente » ; idem « Vice-président ».
- **Poste de Vice-président vacant** (décision Q10 de `docs/lot0/analyse.md`) : la ligne Vice-président affiche `StatusBadge` gris « Poste vacant » ; le Président signe seul et sa signature suffit à clôturer le PV. La vacance est actée dans le PV : mention insérée automatiquement par l'API dans le texte et le PDF. **Correction (révision 29/09)** : la version précédente écrivait « vacant à la date de l'assemblée », alors que `schema-donnees.md` §9.5 apprécie la vacance **au moment de la signature** (`vp_vacant_at_signature`). Le 10.2 n° 28 ne fixe pas la date. Texte aligné provisoirement sur le schéma : « Le poste de Vice-président étant vacant à la date de la signature, le procès-verbal est signé par le Président seul. » L'interface affiche la mention **renvoyée par l'API**, jamais un texte à elle. Point ouvert §7. Aide au-dessus du bouton « Signer le PV » : « Poste de Vice-président vacant : votre signature suffit à clôturer le procès-verbal. »
- (révision 29/09) **Plusieurs Vice-présidents** (10.2 n° 24 : nombre de titulaires par rôle configurable par club) : la ligne affiche « Vice-président : {nom} — signé le {date} » dès qu'**un** VP a signé, sinon « en attente » suivi des noms des titulaires. Le nombre de signatures de VP exigé n'est pas tranché (point ouvert §7) : l'interface affiche l'état « PV complet » renvoyé par l'API et ne le calcule pas.
- Actions : (Président, VP, avant toute signature) « Rédiger le PV » / « Modifier le PV » → modale §4.4 ; (Président ou VP, si sa signature manque) action principale « Signer le PV » → `PinPrompt` (« Signer le procès-verbal de l'AG du {date} ») ; succès : « PV signé. » Quand les deux signatures sont présentes (ou la seule signature du Président si le poste de VP est vacant) : action principale « Télécharger le PV (PDF) », badge « Clôturée ».
- Après la première signature : texte « Le PV ne peut plus être modifié après une signature. »

### 4.3 « Saisir le vote — {intitulé du point} » — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Pour | NumberField − / + | Oui | ≥ 0 |
| Contre | NumberField − / + | Oui | ≥ 0 |
| Abstention | NumberField − / + | Oui | ≥ 0 |
| Décision retenue | TextArea | Oui | « Ce champ est obligatoire. » |
| Action liée dans Vesta | Select : Aucune / Types de cotisation / Autre | Non | Si choisie, lien « Ouvrir » vers l'écran concerné |

(révision 29/09) Sous les trois compteurs, ligne de contrôle 13 px : « Total : {n} votes · {m} présents ». Si le total dépasse le nombre de présents, la ligne passe en `warning` : « Le total des votes ({n}) dépasse le nombre de présents ({m}). Vérifiez la saisie. » **Avertissement non bloquant** : le cahier des charges ne fixe pas cette règle (4.15), la version précédente de cette spec l'avait rendue bloquante sans source. Si l'API la refuse, son message s'affiche sous le champ « Abstention ». Point ouvert §7.

Pied : « Annuler » / « Enregistrer ». Succès : « Décision enregistrée. »

### 4.4 « Rédiger le procès-verbal » — taille `lg`

- « Texte du procès-verbal » (TextArea de grande hauteur, mise en forme minimale : paragraphes, listes). Bouton secondaire « Insérer les décisions » (reprend les décisions et votes saisis).
- Pied : « Annuler » / « Enregistrer ». Succès : « Procès-verbal enregistré. »

### 4.5 « Seuil de quorum » — taille `sm`, Président et VP

- Champ « Seuil de quorum (%) » (NumberField avec suffixe « % », **obligatoire**, entier de 1 à 100). Valeur affichée : le seuil actuel du club, **pré-rempli à 50 à la création du club** par l'API (10.2 n° 18) ; l'interface n'écrit jamais 50 en dur, elle affiche la valeur renvoyée. Erreurs : « Ce champ est obligatoire. » ; « Saisissez une valeur entre 1 et 100. »
- Aide : « Pourcentage des joueurs actifs à la date de l'AG qui doivent être présents. Valeur par défaut : 50 %. »
- Lien secondaire « Revenir à 50 % » (visible seulement si la valeur actuelle est différente ; remplit le champ, n'enregistre pas).
- Pied : « Annuler » / « Enregistrer ». Succès : « Seuil de quorum enregistré : {seuil} %. » Le nouveau seuil s'applique aux AG non encore clôturées.

### 4.6 PV en PDF (révision 29/09)

- **Génération** : par l'API, dès que le PV est complet (deux signatures, ou Président seul si le poste de VP est vacant, 10.2 n° 28). L'interface ne génère aucun PDF.
- **Contenu minimal** (gabarit détaillé : annexe D, tâche 4.9 du plan) : logo et nom du club venant des données du club (3.5, marque blanche, jamais en dur) ; « Procès-verbal de l'assemblée générale {ordinaire / extraordinaire} du {date longue} » ; heure et lieu ; présences et quorum (« {n} présents sur {total} joueurs actifs — quorum de {seuil} % {atteint / non atteint} ») ; ordre du jour ; pour chaque point, votes et décision retenue ; texte du PV ; mention de vacance le cas échéant ; bloc de signatures (« Signé par code PIN par {nom}, {fonction}, le {date heure} »). **Aucune mention de l'Éditeur** dans le PDF (CLAUDE.md règle 19) ; aucune donnée financière individuelle ni médicale.
- **Accès au fichier** : lien « Télécharger le PV (PDF) » servi par une **vue authentifiée** de l'API (vérification du club et de l'adhésion active), jamais par une adresse publique ; le fichier est rangé avec les documents privés du club (6.7, CLAUDE.md règle 10, par prudence : le PV n'est pas cité au 6.7 mais c'est un document interne du club). Sur mobile, le PDF s'ouvre dans la visionneuse du téléphone (téléchargement standard).
- **États** : « Génération… » (bouton `loading`) tant que l'API n'a pas renvoyé `generated_at` ; erreur « Le PDF n'a pas pu être généré. Réessayez. » (déjà en §5).

### 4.7 Journal et notifications (révision 29/09)

Aucun élément d'interface : rappel pour `backend-dev` et `test-engineer`.

| Événement | Journal (5.2 « AG ») | Notification (4.17) |
| --- | --- | --- |
| Convocation | Oui | Tous les joueurs, in-app et email : « Assemblée générale {ordinaire / extraordinaire} le {date} à {heure}, {lieu}. » |
| Rappel la veille (cron) | Non (aucune donnée modifiée) | Tous les joueurs, in-app : « Rappel : assemblée générale demain à {heure}, {lieu}. » |
| Présence pointée ou retirée | Oui | Aucune |
| Vote saisi ou modifié | Oui | Aucune |
| PV rédigé ou modifié | Oui | Aucune |
| Signature du PV (PIN) | Oui | Proposition : le second signataire attendu, in-app « Le PV de l'AG du {date} attend votre signature. » (absente du tableau 4.17, à valider) |
| Seuil de quorum modifié | Oui (avant / après) | Aucune |

Un clic sur une notification ouvre la page et la modale « Assemblée générale » de l'AG concernée (onglet « Procès-verbal » pour la demande de signature).

## 5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| À venir | 1 carte squelette | « Aucune assemblée prévue. » + (Pdt, VP) « Convoquer une AG » | Modèle standard |
| Passées | 3 cartes squelettes | « Aucune assemblée tenue pour l'instant. » | Modèle standard |
| Modale détail | Squelette dans le corps | Décisions : « Aucune décision saisie. » ; PV : « Le procès-verbal n'est pas encore rédigé. » | « Impossible de charger l'assemblée. » + « Réessayer » |
| Signature | — | — | Erreurs PIN standard (design-system `PinPrompt`) |
| Génération PDF | Bouton en état `loading` « Génération… » | — | « Le PDF n'a pas pu être généré. Réessayez. » |
| Présences (révision 29/09) | 5 lignes squelettes | Vue « Non pointés » vide : « Tous les joueurs ont été pointés. » ; vue « Présents » vide : « Aucun présent pour l'instant. » ; recherche sans résultat : « Aucun joueur ne correspond à « {saisie} ». » | Échec d'un pointage : la ligne revient à son état, toast « La présence de {nom} n'a pas été enregistrée. Réessayez. » |
| Hors connexion (révision 29/09) | — | — | Actions désactivées, bandeau `info` « Cette action nécessite une connexion. » ; la consultation reste possible si les données sont en cache |
| Licence en lecture seule (révision 29/09) | — | — | Bandeau `readonly` standard ; « Convoquer une AG », pointage, votes, rédaction et signature masqués ; PDF téléchargeable (`design-system.md` §5) |

Succès (révision 29/09, toasts) : « Assemblée convoquée. Les joueurs ont été prévenus. » ; « Décision enregistrée. » ; « Procès-verbal enregistré. » ; « PV signé. » ; « PV signé. Le procès-verbal est complet et le PDF est disponible. » (dernière signature) ; « Seuil de quorum enregistré : {seuil} %. »

## 6. Mobile (360 px) et ordinateur

- **360 px** : cartes pleine largeur, une par ligne. Modale de détail plein écran, onglets défilants. Onglet « Présences » : liste de 56 px avec bouton « Présent » à droite.
- **≥ 1024 px** : cartes en grille de 3 colonnes ; modale `lg` centrée.
- (révision 29/09) **360 px, détails** : l'assistant `xl` est plein écran, pied « Annuler » / « Suivant » collé en bas même clavier ouvert ; à l'étape 2, les boutons « Monter », « Descendre », « Retirer » sont des `IconButton` de 40 px alignés à droite de l'intitulé (zone 44 px), jamais sous forme de gros boutons pleine largeur. Onglet « Décisions » : un bloc par point, votes sur une ligne « Pour {n} · Contre {n} · Abstention {n} » (retour à la ligne autorisé), bouton `sm` « Saisir le vote » aligné à droite. Onglet « Procès-verbal » : texte à 16 px, une seule action principale dans le pied (« Signer le PV » ou « Télécharger le PV (PDF) »), « Modifier le PV » en bouton secondaire dans le corps. `PinPrompt` en panneau bas.
- (révision 29/09) Vérifications obligatoires à 360 px : intitulé de point de 160 caractères sans débordement ; lieu long ; AG sans VP (badge « Poste vacant ») ; bandeau quorum sur 2 lignes sans troncature ; thèmes Classic, Clair, Sombre.

## 7. Décisions par défaut et points ouverts

- **Décidé, cahier des charges 10.2 n° 18 (Q9 + Q20)** : seuil de quorum en pourcentage des joueurs actifs à la date de l'AG, configurable par club, **50 % par défaut** (pré-rempli à la création du club). Réglage : modale §4.5.
- **Point ouvert** : un club peut-il se passer de quorum (champ vide) ? Le 10.2 n° 18 ne le prévoit pas ; l'écran rend donc le champ obligatoire (1 à 100). À confirmer.
- **Point ouvert** : effet d'un changement de seuil sur une AG déjà convoquée mais non clôturée. Proposition de l'écran : le seuil en vigueur au moment de la tenue s'applique ; le seuil est figé à la clôture. À confirmer avec `backend-dev`.
- **Décidé, cahier des charges 10.2 n° 28 (Q10)** : si le poste de Vice-président est vacant, le Président signe seul et la vacance est actée dans le PV (§4.2, onglet « Procès-verbal »).
- **Point ouvert** : modification ou annulation d'une AG après convocation — non décrite au 4.15, non spécifiée ici.
- **Point ouvert** : nature exacte de l'« action liée » (4.15 cite « une nouvelle grille de cotisations ») ; spécifiée comme simple lien vers l'écran concerné.
- **Proposition de confort (pas une exigence du cahier des charges, à valider selon le circuit 9.4)** : point « Dérogations accordées depuis la dernière AG » ajouté d'office à l'ordre du jour (interprétation du 4.5.2 « signalée à la prochaine AG »).
- **Proposition** : PV non modifiable après la première signature.
- (révision 29/09) **Point ouvert — effet d'un quorum non atteint** : 4.15 impose le calcul, pas la conséquence (votes interdits ? AG reportée ? simple mention au PV ?). Écran : aucun blocage côté interface, bandeau d'avertissement, mention « quorum non atteint » dans le PDF ; si l'API bloque, son message s'affiche. À trancher par le client.
- (révision 29/09) **Point ouvert — total des votes supérieur au nombre de présents** : non réglé par le CDC. La version précédente de l'écran bloquait l'enregistrement (règle inventée) ; elle affiche désormais un avertissement non bloquant. À trancher (et, s'il y a blocage, il est fait par l'API).
- (révision 29/09) **Point ouvert — date d'appréciation de la vacance du VP** (10.2 n° 28) : date de l'AG ou date de la signature ? Écart constaté entre la version précédente de cette spec (« à la date de l'assemblée ») et `schema-donnees.md` §9.5 (`vp_vacant_at_signature`). Position provisoire : celle du schéma (date de la signature), texte de la mention servi par l'API. Cas concret à soumettre au client : un VP nommé entre l'AG et la signature doit-il signer un PV d'une AG à laquelle il n'était pas en poste ?
- (révision 29/09) **Point ouvert — plusieurs titulaires du poste de VP** (10.2 n° 24) : une seule signature de VP suffit-elle, ou faut-il celle de chaque titulaire ? Le CDC dit « le Président et le VP ». Position provisoire la plus prudente : c'est l'API qui déclare le PV complet ; `backend-dev` doit trancher avec le client avant d'implémenter (la plus restrictive serait « tous les VP en poste »).
- (révision 29/09) **Proposition — notification de signature attendue** : absente du tableau 4.17 ; proposée en §4.7 pour que le second signataire soit prévenu. À valider (circuit 9.4 si refusée : la modale reste accessible depuis la page).
- (révision 29/09) **Proposition — libellé « PV à rédiger »** : une AG passée sans PV rédigé affiche aujourd'hui « PV à signer », ce qui est inexact. Proposition : badge orange « PV à rédiger » (à ajouter au tableau 2.5 de `design-system.md`, ligne AG). À valider.

## 8. Textes ajoutés (révision 29/09)

« Tous », « Non pointés ({n}) », « Présents ({n}) », « Tous les joueurs ont été pointés. », « Aucun présent pour l'instant. », « La présence de {nom} n'a pas été enregistrée. Réessayez. », « Quorum non atteint : {n} présents sur {total} ({x} %), seuil {seuil} %. », « Total : {n} votes · {m} présents », « Le total des votes ({n}) dépasse le nombre de présents ({m}). Vérifiez la saisie. », « Le poste de Vice-président étant vacant à la date de la signature, le procès-verbal est signé par le Président seul. » (texte servi par l'API), « PV signé. Le procès-verbal est complet et le PDF est disponible. », « Télécharger le PV (PDF) », « Cette action nécessite une connexion. », « PV à rédiger » (proposition).
