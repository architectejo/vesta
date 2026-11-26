# Évolution — Logistique : registre de l'intendance (détenteurs, provenances, déclassement, import, registre imprimable)

> **Statut : lots 1, 3, 4 et 5 validés par le client le 17/11/2026 (CDC 10.3 n° 181) ; positions Q15, Q16, Q18 à Q23 appliquées à titre provisoire. Lots 6, 7, 9 non engagés.**
> Rédigée le 17/11/2026 à partir du registre d'intendance remis par le club pilote. Chaque élément absent du CDC 4.13 est marqué **[NOUVEAU]** ; ce qui découle directement du CDC ou de la fiche `logistique.md` est marqué **[CDC]**. Les numéros de décision (10.3 n° 181 et suivants) sont des propositions de numérotation, à attribuer à la validation.

Sources lues :
- Registre papier `data/Nouveaux/DLFC.pdf` (4 pages A4 paysage : vareuses, ballons, matériel, éléments à déclasser), lu directement.
- Classeur `data/Nouveaux/LC_Discovery_Intendance.xlsx` (feuilles Synthèse, Vareuses, Ballons, Matériel, Déclassement, Notes & sources), **lu au travers de l'analyse de session** (section B de `analyse-nouveaux-documents.md`) : aucun lecteur de classeur n'était disponible pour cette rédaction. Les écarts PDF / Excel cités au §1.3 viennent de cette analyse.
- CDC 4.13, matrice 2.4 (ligne « Matériel et inventaires »), chapitre 3 ; CLAUDE.md §2 ; `docs/ecrans/logistique.md` ; `backend/apps/logistics/models.py` et `services.py` ; `backend/apps/clubs/models.py` (`ImportBatch`) ; `frontend/src/routes/logistics/`.

Composants du design system utilisés : `PageHeader`, `Banner`, `Card`, `ListSection`, `DataTable`, `StatusBadge`, `Modal`, `ConfirmDialog`, `PlayerSearch`, `ArticleSearch`, `NumberField`, `SegmentedControl`, `DateField`, `EmptyState`, `Skeleton`, `Toast`. Deux variantes nouvelles du combobox de `PlayerSearch` : `HolderSearch` (§4.2) et `HolderPicker` (§4.3). Aucun autre composant nouveau.

---

## 1. Ce que dit le registre réel, et ce que Vesta ne sait pas représenter

### 1.1 Le registre papier (format que l'Intendant connaît)

En-tête de chaque page : « {NOM DU CLUB} INTENDANCE ». Colonnes : **Nature · Désignation · Quantité · Origine · Date d'acquisition · Localisation · État actuel**.

| Page | Contenu | Particularités |
| --- | --- | --- |
| 1 — Vareuses | 8 lignes par couleur (bleu-blanc ×4, rouge-blanc, jaune-noir, rouge-noir ×2) ; quantité en **trois colonnes V / C / B** (totaux 173 / 170 / 129) | Pied : « Total général : vareuse : **7J + 2V de gardien**, localisation : Détenteur A ». Deux dates « Voir le comité précédent ». État « Bon » partout. |
| 2 — Ballons | 13 lignes, 22 ballons, une ligne par don (donateur + date) | Pied : « Total général : ballons 22 — **Chez le détenteur A 14 — Chez le détenteur B 8** ». État renseigné sur la 1re ligne seulement. |
| 3 — Matériel | 13 articles (cartons, filet, pompes, sifflets, bottines ×2 lignes, chaises, maillot d'arbitre, gants, trousse, table de tennis, brassards, chargeurs, chasubles), **plusieurs provenances par article** | Origines « Caisse de l'équipe », « Frais de l'équipe » ; dates « - », « Voir le comité précédent », « 22/06/2025 Restitution » ; unité « paire » ; colonne État vide. |
| 4 — Éléments à déclasser | Vareuses rouges 18, bleues 19, ballons 7, bottines 9 paires | Ni motif, ni date, ni lieu. |

Lecture qui paraît la plus probable de V / C / B (**hypothèse à faire confirmer, question Q11**) : **V = vareuse, C = culotte, B = bas**. Elle est cohérente avec le pied de page : la ligne « rouge-noir 2 / - / - » ne contient que des vareuses (les « 2V de gardien ») et les 7 autres lignes sont les « 7J » (7 jeux complets ou presque). Un « jeu » serait donc **une ligne d'acquisition d'une tenue d'une couleur**, pas une unité de stock.

### 1.2 Écarts avec le modèle actuel

| # | Réalité du club | Modèle actuel (`apps/logistics`) | Proposition |
| --- | --- | --- | --- |
| a | Le matériel est **chez des personnes** (Détenteur A, Détenteur B) | Aucun champ de localisation ; `membership` d'un mouvement = joueur concerné, pas détenteur | **[NOUVEAU]** Détenteurs et stock par détenteur, transferts (§3) |
| b | **Plusieurs provenances** par article (donateur ou « frais de l'équipe », date d'acquisition) ; date parfois inconnue | Seul le motif libre d'un mouvement ; date obligatoire, jamais inconnue | **[NOUVEAU]** Champs de provenance sur les entrées ; date d'acquisition distincte de la date d'enregistrement (§5) |
| c | Unités « jeu » / « paire » ; colonnes V / C / B | Unité en texte libre ; aucune notion de tenue | Unité « paire » : déjà possible. **[NOUVEAU, conditionné à Q11]** regroupement V / C / B d'une tenue (§6) |
| d | **État par ligne** (« Bon », non renseigné) | État de référence porté par l'article ; pas de « non renseigné » | **[NOUVEAU]** état « Non renseigné » ; état à l'entrée sur chaque provenance ; l'état dégradé d'une partie du stock passe par le déclassement (§5.3) |
| e | **Éléments à déclasser** : restent comptés tant qu'ils ne sont pas sortis | Seules les sorties Usure / Perte existent | **[NOUVEAU]** Déclassement en deux temps : signalement, puis sortie physique (§7) |
| f | Chasubles, arbitrage, gardien, mobilier, accessoires… | 5 catégories (CDC 4.13 range plots, chasubles et trousse dans « Matériel divers ») | **[NOUVEAU]** catégories supplémentaires (§8) |
| g | Inventaire existant à reprendre (≈ 60 lignes) | Aucun import ; aucun type « stock initial » (point ouvert n° 7 de `logistique.md`) | **[NOUVEAU]** Import du registre avec aperçu (§9) et type d'entrée « Reprise du registre » |
| h | Le club veut **son registre papier** | Pas de vue registre, pas d'export | **[NOUVEAU]** Page « Registre de l'intendance » + PDF et CSV (§10) |
| i | Inventaire : on compte **chez chaque détenteur** | Comptage par article seulement | **[NOUVEAU]** Comptage par détenteur, écarts de localisation (§11) |

### 1.3 Écarts entre le PDF et le classeur (à faire trancher avant l'import)

D'après l'analyse : chasubles (24) absentes du classeur ; vareuses rouge-noir 20 chez le détenteur A (PDF) ou le détenteur B (classeur) ; trousse et table de tennis inversées entre les détenteurs A et B ; localisation du matériel vide dans le classeur ; orthographes divergentes de plusieurs noms de donateurs (cinq noms écrits avec une à trois lettres de différence d'un document à l'autre). **Le PDF est plus complet ; proposition : il fait foi, sauf avis contraire de l'Intendant** (Q14).

---

## 2. Rôles (matrice 2.4, inchangée)

| Rôle | Accès | Sur les nouveautés |
| --- | --- | --- |
| Intendant | É | Tout : détenteurs, transferts, provenances, déclassement, import, comptage par détenteur |
| Président, Vice-président, Trésorier, Coach | L | Consultation de la répartition par détenteur, du déclassement et du registre ; téléchargement du registre PDF / CSV (Q22). Le Coach garde la sortie et le retour d'équipements d'un match (4.8), avec le choix du détenteur source (§4.4). |
| Directeur sportif, Trésorier adjoint, Secrétaire, Capitaine, Médecin, Joueur | — | Aucun accès. **Être détenteur ne donne aucun accès** au module : un joueur détenteur sans rôle Intendant ne voit pas la page Matériel (Q19, proposition prudente). |

Les actions non autorisées sont masquées. Les droits viennent de l'API. Toutes les données sont filtrées par le club actif (règle 8).

---

## 3. Détenteurs et stock par détenteur [NOUVEAU] — constat (a)

### 3.1 Règle proposée

- Un **détenteur** est soit un **joueur du club** (choisi par recherche, jamais une liste déroulante), soit un **lieu** nommé (« Local du club », « Stade »…). Il appartient au club actif.
- Chaque mouvement porte un détenteur facultatif : pour une entrée, celui qui **reçoit** ; pour une sortie, celui **chez qui** le matériel sort.
- **Stock d'un article chez un détenteur** = somme signée des mouvements de cet article portant ce détenteur. Calculé, jamais stocké (même principe que le stock théorique, invariant J1).
- Les mouvements sans détenteur forment la ligne **« Non localisé »**. C'est là que se trouve tout le stock existant aujourd'hui (règle de compatibilité, §13).
- **Transfert** : déplacer du matériel d'un détenteur à un autre (ou de « Non localisé » vers un détenteur) crée **deux mouvements liés** — une sortie « Transfert » chez la source et une entrée « Transfert reçu » chez la destination. Le stock total de l'article ne change pas.
- Une sortie (distribution, prêt pour un match, usure, perte, déclassement, transfert) est **refusée si elle dépasse le stock de la source choisie** : « Quantité supérieure au stock de {détenteur} ({n}). » Le contrôle du stock total existant reste en place.
- **Détenteur obligatoire ou non (Q16)** : proposition par défaut, **facultatif** (« Non localisé » autorisé), pour ne pas bloquer la saisie au bord du terrain. Un bandeau signale le stock non localisé (§3.3).
- Un détenteur joueur qui **quitte le club** (transfert, fin d'adhésion) et détient encore du matériel : bandeau d'alerte « {nom} a quitté le club et détient encore {n} pièce(s). » visible par l'Intendant et le Président (Q20). Aucune sortie automatique.
- Un détenteur ne s'archive que si son stock est nul sur tous les articles.

### 3.2 Carte « Où est le matériel » (page `/materiel`)

Nouvelle carte, insérée en 2e position (après « Inventaire trimestriel », avant « Catalogue »).

- En-tête : « Où est le matériel » + compteur « {n} détenteurs ». Action de carte (Intendant) : « Ajouter un détenteur » (bouton `sm` secondaire).
- Lignes (toutes : un club a rarement plus de 5 détenteurs ; au-delà de 5, les 5 premiers puis « Voir plus ») :
  - 1re ligne : avatar 24 px (joueur) ou icône lieu, nom du détenteur ; à droite « {n} pièces » (tabular-nums, 14 px) ;
  - 2e ligne (13 px) : « {k} articles » ; `StatusBadge` « A quitté le club » (rouge) si c'est le cas.
  - Dernière ligne, toujours présente si son stock n'est pas nul : « Non localisé » (icône point d'interrogation), « {n} pièces », `StatusBadge` « À localiser » (gris).
- Tri : quantité décroissante, « Non localisé » en dernier.
- Clic → modale « Détenteur » (§4.1).
- « Pièces » additionne des unités différentes (pièces, paires) : c'est un ordre de grandeur, pas un total comptable. L'API renvoie le chiffre, l'interface ne calcule rien.
- État vide (aucun détenteur, tout est non localisé) : `EmptyState` « Aucun détenteur enregistré. » ; précision « Indiquez chez qui se trouve le matériel pour le retrouver et le compter plus vite. » ; (Intendant) « Ajouter un détenteur ».

### 3.3 Bandeau « Matériel non localisé » (Intendant seulement)

`Banner` `info` sous l'en-tête, si au moins un détenteur existe et que le stock « Non localisé » n'est pas nul : « {n} pièce(s) ne sont rattachées à aucun détenteur. » Action : « Localiser » → ouvre §4.3 avec « De : Non localisé » prérempli. Le bandeau n'apparaît pas tant qu'aucun détenteur n'a été créé (pas d'alerte au premier jour).

### 3.4 Catalogue : colonnes ajoutées

`DataTable` du catalogue (`logistique.md` §3.1) : ajout de deux colonnes après « En stock » :
- **Chez** : détenteur principal et reste, ex. « Détenteur A 14 · Détenteur B 8 » ; au-delà de deux détenteurs « Détenteur A 14 · +2 » ; « Non localisé » en gris.
- **À déclasser** : « {n} » ou « — » (§7).

Filtre ajouté : « Détenteur » (recherche `HolderSearch`, inclut « Non localisé »).

---

## 4. Modales liées aux détenteurs [NOUVEAU]

Toutes : design system §3.2 (croix, Échap, clic sur le voile ; « Abandonner les modifications ? » si saisie commencée ; pied fixe ; plein écran à moins de 640 px, panneau bas pour la taille `sm`).

### 4.1 « Détenteur » (détail) — taille `md`

- En-tête : nom ; sous-titre « Joueur du club » ou « Lieu » ; `StatusBadge` « A quitté le club » / « Archivé » s'il y a lieu.
- Corps : liste des articles détenus (nom, catégorie, « {n} {unité} », « dont {k} à déclasser » en 14 px si > 0) ; 10 premiers puis « Voir plus ». Clic sur un article → modale « Article » au niveau 2.
- « 5 derniers mouvements chez ce détenteur » puis « Voir plus » (ouvre le registre des mouvements filtré sur le détenteur).
- Pied : « Fermer » / (Intendant, stock non nul) « Déplacer du matériel » (§4.3, source préremplie).
- Menu « … » (Intendant) : « Renommer le lieu » (lieu seulement) ; « Archiver le détenteur » (refusé par l'API si stock non nul : « {nom} détient encore {n} pièce(s) : déplacez-les avant d'archiver. »).
- Vide : « Ce détenteur n'a aucun matériel. »

### 4.2 « Ajouter un détenteur » — taille `sm`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Type | SegmentedControl « Un joueur » / « Un lieu » | Oui, « Un joueur » par défaut | — |
| Joueur | `PlayerSearch` portée `club` (joueurs actifs et en attente) | Si « Un joueur » | « Choisissez un joueur. » ; déjà détenteur : grisé « Déjà détenteur » |
| Nom du lieu | TextField, 60 caractères max. | Si « Un lieu » | « Ce champ est obligatoire. » ; doublon : « Ce lieu existe déjà. » |

Pied : « Annuler » / « Ajouter ». Succès : « Détenteur ajouté. »

### 4.3 « Déplacer du matériel » — taille `md` (Intendant)

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Article | `ArticleSearch` mode sortie | Oui | « Choisissez un article. » |
| De | `HolderPicker` : puces des détenteurs qui ont cet article, avec la quantité (« Détenteur A · 14 », « Non localisé · 8 ») ; si plus de 5 sources, `HolderSearch` | Oui | « Choisissez d'où vient le matériel. » |
| Vers | `HolderSearch` (détenteurs actifs ; dernière suggestion « + Ajouter un détenteur », ouvre §4.2 au niveau 2) | Oui | « Choisissez le nouveau détenteur. » ; identique à la source : « Le détenteur d'arrivée doit être différent du détenteur de départ. » |
| Quantité | NumberField − / +, ≥ 1, suffixe unité | Oui | Erreur API : « Quantité supérieure au stock de {détenteur} ({n}). » |
| Date | DateField, aujourd'hui par défaut | Oui | « La date ne peut pas être dans le futur. » |
| Motif | TextArea, 500 caractères max. | Non | — |

Pied : « Annuler » / « Déplacer ». Succès : « Matériel déplacé : {n} {unité} de {article} chez {destination}. »

### 4.4 Champ « Chez » ajouté aux modales existantes

- **« Enregistrer un mouvement »** (`logistique.md` §4.4) : champ « Chez » après « Quantité ». Entrée : `HolderSearch` (« Qui reçoit le matériel ? »), facultatif. Sortie : `HolderPicker` (« D'où sort le matériel ? »), obligatoire dès que l'article a au moins un détenteur, prérempli avec le détenteur qui en a le plus. Nouveau type d'entrée « Reprise du registre » et champs de provenance : §5.2.
- **« Ajouter des équipements »** (feuille de match, `logistique.md` §4.5) : sur chaque ligne, sous la quantité, ligne 13 px « Chez {détenteur proposé} · Changer » ; « Changer » ouvre le `HolderPicker` en place. Le détenteur proposé est renvoyé par l'API (celui qui a le plus de stock). Le Coach n'a rien à saisir de plus dans le cas courant.
- **« Enregistrer le retour »** : le retour va par défaut au détenteur de la sortie, ligne 13 px « Retour chez {détenteur} · Changer ».

---

## 5. Provenances, date d'acquisition, état [NOUVEAU] — constats (b) et (d)

### 5.1 Règle proposée

- Une **provenance** est une entrée de stock (Achat, Dotation, Reprise du registre) avec : quantité, **origine** (« Don » + donateur, « Frais de l'équipe », « Inconnue »), **date d'acquisition**, détenteur, **état à l'entrée**.
- **Donateur** : recherche `PlayerSearch` parmi les joueurs du club, **ou** saisie libre si le donateur n'est pas (ou plus) membre (« un donateur extérieur », un ancien du comité…). Le nom libre est conservé tel quel.
- **Date d'acquisition** distincte de la **date d'enregistrement** (`movement_date`, celle qui compte pour le stock). Elle peut être **inconnue** : case « Date inconnue » + précision facultative (60 caractères, ex. « Voir le comité précédent »). Elle ne peut jamais être dans le futur.
- **Origine « Frais de l'équipe »** : type « Achat » sans dépense liée, ou rattaché à une dépense comme aujourd'hui (`logistique.md` §5.1). « Caisse de l'équipe » est lu comme « Frais de l'équipe » (Q13).
- **« Restitution »** (gants, Steve Pango, 22/06/2025) : sens à confirmer (Q13). Proposition : entrée « Retour » avec le joueur concerné.
- **État** : l'état de référence reste porté par l'article (CDC 4.13 « avec quantité et état ») ; ajout de la valeur **« Non renseigné »** (Q18). L'**état à l'entrée** d'une provenance est une information figée, affichée dans le registre. La partie du stock usée ou abîmée se signale par le déclassement (§7), qui garde la quantité, le motif et le détenteur.

### 5.2 Modale « Enregistrer un mouvement » : champs ajoutés (entrées seulement)

Type d'entrée ajouté : **« Reprise du registre »** (matériel déjà possédé avant Vesta ; répond au point ouvert n° 7 de `logistique.md`). Aide : « Pour le matériel que le club possédait avant d'utiliser Vesta. »

Bloc « Provenance » (sous « Chez », replié en une ligne « Provenance : non renseignée · Modifier » pour ne pas alourdir une saisie rapide ; déplié d'office pour « Dotation » et « Reprise du registre ») :

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Origine | SegmentedControl « Don » / « Frais de l'équipe » / « Inconnue » | Non (« Inconnue » par défaut) ; « Don » proposé d'office pour « Dotation » | — |
| Donateur | `PlayerSearch` portée `club` ; dernière suggestion « Utiliser « {saisie} » (hors club) » | Si « Don » | « Indiquez le donateur. » ; 120 caractères max. |
| Date d'acquisition | DateField + case « Date inconnue » | Non (vide = date d'enregistrement) | « La date ne peut pas être dans le futur. » |
| Précision sur la date | TextField 60 caractères, visible si « Date inconnue » | Non | Placeholder « Ex. : voir le comité précédent » |
| État à l'entrée | SegmentedControl « Neuf » / « Bon état » / « Usé » / « Abîmé » / « Non renseigné » (deux lignes à 360 px) | Non (« Non renseigné ») | — |

### 5.3 Modale « Article » : section « Provenances » ajoutée

Entre les valeurs clés et « Derniers mouvements » :
- Valeurs clés : « En stock », « À déclasser » (nouveau), « Sortis pour un match », « État ».
- **« Répartition »** : « Détenteur A · 14 », « Détenteur B · 8 », « Non localisé · 0 » (masqué si 0). Action (Intendant) « Déplacer ».
- **« Provenances »** : 5 dernières entrées (Achat, Dotation, Reprise du registre) puis « Voir plus » : « {quantité} {unité} · {Don de {nom} / Frais de l'équipe / Origine inconnue} », 2e ligne 13 px « Acquis le {date} » ou « Date inconnue — {précision} » · « chez {détenteur} ». Vide : « Aucune provenance enregistrée. »

---

## 6. Tenues : vareuse / culotte / bas [NOUVEAU, conditionné à Q11] — constat (c)

À réaliser **seulement si le client confirme V = vareuse, C = culotte, B = bas**. Sinon, cette section est réécrite après sa réponse.

- Une **tenue** regroupe jusqu'à trois articles d'une même couleur : « Vareuse bleu-blanc » (Maillots), « Culotte bleu-blanc » (Culottes, §8), « Bas bleu-blanc » (Bas). Chaque article garde son stock propre : on ne doit jamais additionner V + C + B.
- Champs d'article : « Tenue » (texte, ex. « Bleu-blanc ») et « Pièce » (« Vareuse », « Culotte », « Bas »), facultatifs.
- **Entrée d'un jeu** : depuis la modale « Enregistrer un mouvement », si l'article choisi appartient à une tenue, lien « Saisir un jeu complet (V / C / B) ». Il remplace « Quantité » par trois NumberField « Vareuses », « Culottes », « Bas » (0 autorisé, au moins un > 0). Une seule provenance pour les trois. L'API crée un mouvement par pièce, liés entre eux.
- Le registre (§10) affiche ces mouvements liés sur **une seule ligne** avec les colonnes V / C / B, comme le papier ; « - » quand la pièce vaut 0.
- « 7J + 2V de gardien » : l'API compte les **jeux** (entrées liées ayant une vareuse et au moins une autre pièce) et les **vareuses seules** ; le pied du registre affiche « {7} jeux + {2} vareuses seules ». Libellé exact (« de gardien ») : Q11.

---

## 7. Déclassement [NOUVEAU] — constat (e)

### 7.1 Règle proposée

Deux temps, pour coller au registre (« éléments **à** déclasser ») :

1. **Signaler à déclasser** : article, quantité, détenteur (s'il y en a), motif (« Usé », « Abîmé », « Hors d'usage », « Autre » + précision), date du constat. **Le stock ne change pas** : ces pièces restent comptées, au stock et à l'inventaire, tant qu'elles ne sont pas sorties.
2. **Sortir du stock** : à la sortie physique (don, destruction, recyclage), l'Intendant enregistre la date de sortie et la destination facultative. L'API crée une sortie de type **« Déclassement »** liée au signalement. Le signalement passe « Déclassé ».

- Un signalement peut être **annulé** (pièces finalement gardées), avec un motif ; il reste visible avec le statut « Annulé ».
- La quantité à déclasser d'un article ne peut pas dépasser son stock (ni le stock du détenteur choisi) : « Il ne reste que {n} {unité} chez {détenteur}. »
- **Pas de validation par le Président** : la matrice 2.4 donne l'écriture à l'Intendant seul. Le club parle de « patrimoine de l'équipe » : faut-il un accord du Président ou du bureau avant la sortie ? (Q15). Position provisoire : Intendant seul, avec modale de confirmation et journal.
- Les pièces à déclasser **restent proposées** pour une sortie de match : aucune règle nouvelle n'est inventée. L'affichage « dont {k} à déclasser » prévient l'utilisateur (Q21).

### 7.2 Carte « À déclasser » (page `/materiel`)

Insérée après « Catalogue ». Affichée seulement s'il existe au moins un signalement (actif ou historique).

- En-tête : « À déclasser » + « {n} pièces en attente de sortie ». Action de carte (Intendant) : « Signaler à déclasser ».
- 5 derniers signalements en attente, puis « Voir plus » (inclut les déclassés et annulés, filtre « Statut »). Ligne : « {article} · {quantité} {unité} », 2e ligne 13 px « {motif} · chez {détenteur} · signalé le {date} » ; `StatusBadge` « À déclasser » (orange), « Déclassé » (gris), « Annulé » (gris).
- Clic → modale « Déclassement » (§7.4).
- État vide (carte affichée par l'Intendant via le menu) : « Aucun élément à déclasser. »

### 7.3 « Signaler à déclasser » — taille `md` (Intendant)

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Article | `ArticleSearch` mode sortie | Oui | « Choisissez un article. » |
| Chez | `HolderPicker` (si l'article a des détenteurs) | Oui si l'article a des détenteurs | — |
| Quantité | NumberField ≥ 1 | Oui | Erreur API : « Il ne reste que {n} {unité} chez {détenteur}. » |
| Motif | SegmentedControl « Usé » / « Abîmé » / « Hors d'usage » / « Autre » | Oui | « Choisissez le motif. » |
| Précision | TextArea 500 caractères | Si « Autre » | « Précisez le motif. » |
| Date du constat | DateField, aujourd'hui | Oui | Pas dans le futur |

Aide : « Les pièces restent dans le stock jusqu'à leur sortie. » Pied : « Annuler » / « Signaler ». Succès : « {n} {unité} de {article} à déclasser. »

### 7.4 « Déclassement » (détail) — taille `md`

- Lecture : article, quantité, détenteur, motif, date du constat, « Signalé par {nom} » ; si déclassé : « Sorti le {date} · {destination} · par {nom} » ; si annulé : « Annulé le {date} par {nom} : {motif} ».
- Pied (Intendant, en attente) : « Fermer » / « Sortir du stock ». Menu « … » : « Annuler le signalement ».
- **« Sortir du stock »** → sous-modale `sm` : « Date de sortie » (DateField, obligatoire, pas dans le futur, pas avant le constat) ; « Destination (facultatif) » (TextField 120, ex. « Donné à l'école du quartier ») ; puis `ConfirmDialog` « Sortir {n} {unité} de {article} du stock ? » — « Cette sortie est définitive : elle ne pourra pas être supprimée. » — « Annuler » / « Sortir du stock ». Succès : « {n} {unité} sortis du stock. Stock de {article} : {m} {unité}. »
- **« Annuler le signalement »** → `ConfirmDialog` avec champ « Motif » obligatoire — « Annuler » / « Annuler le signalement ». Succès : « Signalement annulé. »

---

## 8. Catégories [NOUVEAU] — constat (f)

CDC 4.13 : « maillots, bas, bottines, ballons, matériel divers : plots, chasubles, trousse médicale ». Proposition (Q23) :

| Catégorie | Exemples du club | Statut |
| --- | --- | --- |
| Maillots | vareuses, maillot de gardien | [CDC] (libellé « Maillots (vareuses) » ? Q23) |
| Culottes | culottes des tenues | [NOUVEAU] |
| Bas | bas des tenues | [CDC] |
| Bottines | bottines | [CDC] |
| Ballons | ballons | [CDC] |
| Chasubles | 24 chasubles | [NOUVEAU] (le CDC les range en divers) |
| Arbitrage | cartons, sifflets, maillot d'arbitre | [NOUVEAU] |
| Accessoires | gants de gardien, brassards, pompes, filet à ballons, chargeurs | [NOUVEAU] |
| Mobilier | chaises plastiques, table de tennis | [NOUVEAU] |
| Matériel divers | trousse médicale, plots, autres | [CDC] |

Interface : 10 catégories ne tiennent plus dans un SegmentedControl à 360 px. Champ « Catégorie » : `<select>` natif à toutes les largeurs (autorisé : ce n'est pas un joueur). Filtres du catalogue et puces du comptage : puces sur une ligne défilante horizontalement, « Toutes » en premier.

---

## 9. Import du registre [NOUVEAU] — constat (g)

### 9.1 Règle proposée

- Modale « Importer le registre » sur le modèle de `tresorerie-import-cotisations.md` : **Fichier → Aperçu (aucune écriture) → Résultat**. Intendant seulement.
- Fichier **CSV UTF-8** (séparateur `;` ou `,`), 500 lignes et 10 Mo au plus. Le classeur Excel s'enregistre en CSV depuis Excel. Lecture directe du `.xlsx` : non proposée (Q24).
- **Une ligne = une provenance** (comme une ligne du registre papier). Chaque ligne réussie crée une entrée **« Reprise du registre »**, datée du jour de l'import (date d'enregistrement), avec la date d'acquisition de la ligne.
- Colonnes reconnues (en-tête, casse et accents ignorés) :

| Colonne | Obligatoire | Lecture |
| --- | --- | --- |
| `nature` | Oui | Catégorie (§8). « Vareuse » → Maillots ; « Chasubles » → Chasubles ; inconnu → échec de la ligne |
| `designation` | Oui | Nom de l'article. Article existant (même nom, comparaison faite par l'API en Python, insensible à la casse et aux espaces) ou **article à créer** (signalé dans l'aperçu) |
| `quantite` | Oui, sauf si `v`/`c`/`b` | Entier ≥ 1 ; « 2 paires » accepté (nombre + unité) |
| `v`, `c`, `b` | Non | Seulement si Q11 est confirmée (§6) : une ligne de tenue ; « - » ou vide = 0 |
| `unite` | Non | « pièce » par défaut ; « paire(s) » normalisé en « paire » |
| `origine` | Non | « Frais de l'équipe », « Caisse de l'équipe » → Frais de l'équipe ; vide → Inconnue ; autre texte → Don de {texte}. Donateur relié à un joueur si le nom correspond **exactement** à un joueur du club, sinon conservé en texte libre (signalé « hors club » dans l'aperçu) |
| `date_acquisition` | Non | `JJ/MM/AAAA` (préfixe « le » accepté) ; vide, « - » ou texte (« Voir le comité précédent ») → date inconnue, le texte est gardé comme précision ; date future → échec |
| `localisation` | Non | Nom d'un détenteur **existant** (joueur ou lieu). Inconnu → échec de la ligne : « Détenteur « {texte} » introuvable : ajoutez-le d'abord dans « Où est le matériel ». » Vide → Non localisé |
| `etat` | Non | Bon / Bon état, Neuf, Usé, Abîmé ; vide → Non renseigné |

- **Aucun rapprochement approximatif** des noms (comme l'import des cotisations). Les variantes d'orthographe sont listées dans l'aperçu pour que l'Intendant corrige le fichier.
- **Tout ou rien** : si une ligne est en échec, le bouton « Importer » reste désactivé. Proposition prudente, différente de l'import des cotisations : un registre à moitié repris fausserait le premier inventaire (Q25).
- **Ré-import** : une ligne identique à une reprise déjà importée (même article, quantité, origine, date d'acquisition, détenteur) est **ignorée** et comptée « Déjà importée ».
- **Inventaire ouvert** : import refusé tant qu'un inventaire est ouvert : « Clôturez l'inventaire du {trimestre} avant d'importer le registre. » (le stock théorique changerait pendant le comptage).
- **Éléments à déclasser** : non importés. Après l'import, l'Intendant les signale (§7.3), une fois le motif et la répartition connus (Q15).
- Le fichier source et le rapport sont conservés en stockage privé (`ImportBatch`, type « Registre de l'intendance »), servis seulement par une vue authentifiée (règle 10).

### 9.2 Entrée

Page `/materiel`, menu « … » de l'en-tête (Intendant) : « Importer le registre (CSV) ». Et dans l'état vide du catalogue : bouton secondaire « Importer le registre ».

### 9.3 Modale « Importer le registre » — taille `xl`, plein écran sous 640 px

Ligne d'étape 13 px : « Étape 1 sur 3 · Fichier » / « Étape 2 sur 3 · Aperçu » / « Étape 3 sur 3 · Résultat ». Fermeture protégée dès qu'un fichier est choisi : « Abandonner l'import ? Le fichier choisi et l'aperçu seront perdus. » — « Continuer l'import » / « Abandonner ». Fermeture impossible pendant l'import.

**Étape 1 — Fichier** : zone « Choisir un fichier CSV » (44 px) ; « {nom} · {taille} Ko » + « Changer ». Repliable « Format attendu » : « Une ligne par provenance, comme dans le registre papier. Colonnes : nature, designation, quantite, unite, origine, date_acquisition, localisation, etat. Une date inconnue peut rester vide ou contenir une précision (« Voir le comité précédent »). Les détenteurs doivent exister avant l'import. Fichier UTF-8, 500 lignes au plus. » Lien « Télécharger un modèle vide » (en-tête seul). Pied : « Annuler » / « Voir l'aperçu » (« Analyse du fichier… »). Erreurs de fichier : `Banner` `danger`, texte de l'API.

**Étape 2 — Aperçu** :
1. Résumé (2 colonnes à 360 px, 4 dès 768 px) : « Lignes lues », « Lignes prêtes » (vert), « Lignes en échec » (rouge si > 0), « Articles à créer », « Pièces à entrer », « Déjà importées (ignorées) » (si > 0).
2. `Banner` `warning` toujours : « Les entrées importées ne pourront pas être supprimées : une erreur se corrigera par une sortie. »
3. `Banner` `info` si besoin : « {n} donateur(s) hors club : {liste}. » ; « Noms proches à vérifier : Donateur X / Donateur X', … » (l'API signale les noms qui ne diffèrent que d'une ou deux lettres ; elle ne les fusionne jamais).
4. `SegmentedControl` « En échec ({n}) » · « Prêtes ({n}) » · « Par article ». Par défaut « En échec » s'il y en a.
   - En échec : 20 premières puis « Voir plus » ; « Ligne {n} · {désignation} », badge « Échec » (rouge), messages en 14 px.
   - Prêtes : 20 premières puis « Voir plus » ; « {désignation} · {quantité} {unité} », 13 px « {origine} · {date ou « Date inconnue »} · chez {détenteur} » ; badge « Prête » (vert) ou « Article créé » (violet).
   - Par article : `DataTable` « Article · Catégorie · Stock actuel · Entrées · Stock après import · Répartition après import ». Les valeurs viennent de l'API.
5. Pied : « Annuler » / « Importer {n} ligne(s) » (désactivé s'il reste un échec ; aide « Corrigez les lignes en échec dans le fichier, puis rechargez-le. »).
6. « Importer » → `ConfirmDialog` « Importer {n} lignes dans le registre ? » — « {a} articles seront créés et {p} pièces entrées en stock. » — « Annuler » / « Importer ».

**Étape 3 — Résultat** : `Banner` `success` « Registre importé : {n} lignes, {a} articles créés. » ; liens « Télécharger le rapport (CSV) » et « Voir le registre de l'intendance » (§10). Pied : « Fermer ». Le catalogue, la carte « Où est le matériel » et le registre se mettent à jour.

---

## 10. Registre de l'intendance (consultation, PDF, CSV) [NOUVEAU] — constat (h)

### 10.1 Accès

Route `/materiel/registre`. Entrées : bouton secondaire `sm` « Registre de l'intendance » dans l'en-tête de `/materiel` (tous les rôles qui ont accès ; ce n'est pas l'action principale) ; lien dans l'étape 3 de l'import.

### 10.2 Structure de la page

- **En-tête** : titre « Registre de l'intendance » ; contexte « {nom du club} · arrêté au {date du jour} » ; lien retour « ‹ Matériel ». Action principale : « Télécharger (PDF) » ; secondaire (menu « … ») : « Exporter (CSV) ».
- **Barre de filtres** (collante) : recherche « Rechercher un article, un donateur » ; puces de catégorie ; filtre « Détenteur » (`HolderSearch`) ; case « Afficher les sorties » (décochée : le registre montre ce qui est **en possession** du club).
- **Une carte par nature (catégorie)**, dans l'ordre du §8, comme les pages du papier :
  - **≥ 768 px** : `DataTable` aux colonnes du papier : **Désignation** (figée) · **Quantité** (une colonne, ou V / C / B pour les tenues) · **Origine** · **Date d'acquisition** · **Localisation** · **État actuel**. Une ligne = une provenance. Localisation = détenteur **à l'entrée** de cette provenance ; État = état à l'entrée, sinon état de l'article.
  - **360 px** : liste de lignes compactes (56 px) : « {désignation} · {quantité} » ; 13 px « {origine} · {date} » ; 13 px « chez {détenteur} · {état} ». Pas de tableau à 7 colonnes en défilement horizontal.
  - **Pied de carte** (comme le papier) : « Total : {n} {unité} » (V / C / B pour les tenues, et « {7} jeux + {2} vareuses seules ») ; « Répartition actuelle : Chez Détenteur A {14} · Chez Détenteur B {8} » — c'est le **stock actuel par détenteur** (après transferts et sorties), qui peut différer de la colonne Localisation à l'entrée. Aide 13 px : « La localisation de chaque ligne est celle de l'entrée en stock ; la répartition actuelle tient compte des déplacements. »
  - Plus de 30 lignes dans une carte : 30 premières puis « Voir plus ».
- **Carte « Éléments à déclasser »** (dernière, comme la page 4) : « {article} : {quantité} {unité} » + motif et détenteur ; vide : « Aucun élément à déclasser. »
- **Carte « Sorties de l'année »** (seulement si « Afficher les sorties ») : usure, perte, déclassement de l'année en cours.

Clic sur une ligne → modale « Mouvement » (`logistique.md` §4.3) enrichie de la provenance.

### 10.3 PDF (généré par l'API, jamais par le navigateur)

- A4 **paysage**, comme le papier. En-tête de chaque page : logo du club (s'il existe) + « {NOM DU CLUB} — INTENDANCE » (nom et logo venus des données du club : **aucun nom écrit en dur**, règle 18).
- Une section par nature, saut de page entre Maillots, Ballons et le reste (mise en page du papier : vareuses, ballons, matériel, à déclasser). Colonnes et pieds de section comme le §10.2.
- Dernière page : « Éléments à déclasser du patrimoine du club ».
- Pied de chaque page : « Arrêté au {date} · édité par {nom}, {fonction} · page {p}/{n} ». **Aucune mention d'IMARA TECH Group** dans le document (règle 19 : le footer de l'interface est le seul endroit).
- Les filtres actifs de la page s'appliquent au PDF ; le titre le précise alors : « Extrait : {filtre} ».
- Généré à la demande, servi par une vue authentifiée qui vérifie club et rôle ; aucun fichier stocké dans un dossier public (règle 10).
- Chargement : bouton en état `loading` « Préparation du PDF… » ; erreur : toast « Le registre n'a pas pu être généré. Réessayez. »

### 10.4 CSV

Mêmes colonnes que l'import (§9.1) : un registre exporté peut être ré-importé dans un autre club ou servir de sauvegarde. UTF-8 avec BOM pour Excel, séparateur `;`.

---

## 11. Inventaire trimestriel par détenteur [NOUVEAU] — constat (i)

### 11.1 Règle proposée

- Le comptage reste par article (CDC 4.13), mais **se saisit par détenteur** quand l'article a des détenteurs : l'Intendant compte chez le détenteur A, puis chez le détenteur B.
- Écart **par détenteur** = compté chez lui − stock théorique chez lui (figé au comptage). Écart de l'article = somme des écarts par détenteur (c'est lui qui se justifie : vol, usure, oubli, perte — CDC 4.13).
- **Écart de localisation** : écart nul pour l'article mais non nul chez deux détenteurs (ex. −2 chez le détenteur A, +2 chez le détenteur B). Ce n'est ni un vol ni une perte : l'interface propose « Enregistrer le déplacement », qui crée un transfert (§3.1) daté du comptage. Ce cas ne demande pas de cause. **[NOUVEAU]** (Q26).
- Article sans aucun détenteur : comptage global, comme aujourd'hui.
- Clôture : inchangée (tous les articles actifs comptés, chaque écart d'article justifié), plus : chaque écart de localisation enregistré ou expliqué (Q26).

### 11.2 Modale « Saisir le comptage » (`logistique.md` §4.10) : changements

- Barre haute : ajout de puces **« Chez »** : « Tous », « Détenteur A », « Détenteur B », …, « Non localisé ». Choisir un détenteur = ne voir que les articles qu'il est censé détenir (sans la quantité : comptage à l'aveugle conservé).
- Lien bas de liste (détenteur choisi) : « Un article trouvé ici n'est pas dans la liste ? Ajouter » (`ArticleSearch`) : ajoute une ligne de comptage chez ce détenteur.
- Ligne : nom, « {catégorie} · {unité} », champ « Compté chez {détenteur} ».
- Résumé : « {c} sur {m} comptés · chez {détenteur} : {c'} sur {m'} ».

### 11.3 Détail d'inventaire (§4.9) et justification (§4.7)

- `DataTable` : la ligne d'article se déplie en sous-lignes par détenteur (Théorique · Compté · Écart).
- Badge ajouté : « Écart de localisation » (orange) tant que le déplacement n'est pas enregistré ; « Déplacement enregistré » (vert).
- « Justifier l'écart » : rappel par détenteur dans la modale ; cause inchangée (liste fermée du CDC).

---

## 12. Backend proposé (noms indicatifs, à confirmer par `backend-dev`)

### 12.1 Modèles

Tous les nouveaux modèles sont des `TenantModel` avec `club` (FK PROTECT, indexé), managers tenant-aware et `clean()` qui vérifie que chaque objet lié porte le même club (règle 8). Toutes les migrations sont **additives et réversibles** (champs nullables ou avec défaut, aucun `RunPython` qui modifie un mouvement).

| Modèle | Champs proposés | Remarques |
| --- | --- | --- |
| `Holder` (nouveau) | `club`, `kind` (`member` / `place`), `membership` (FK `clubs.Membership`, null), `label` (60, blanc si joueur), `status` (`active` / `archived`), `archived_at`, `created_at`, `created_by` | Contraintes : `member` ⇒ `membership` non nul ; `place` ⇒ `label` non vide ; unicité (`club`, `membership`) et (`club`, `label`) gérée **dans le service** (contraintes conditionnelles non appliquées par MySQL, cf. avertissement Django W036) |
| `StockMovement` (champs ajoutés) | `holder` (FK `Holder`, null, PROTECT) ; `origin_kind` (`donation` / `club_funds` / `unknown`, blanc) ; `donor_membership` (FK null) ; `donor_name` (120, blanc) ; `acquisition_date` (date, null) ; `acquisition_date_note` (60, blanc) ; `condition_at_entry` (choix d'état, blanc) ; `transfer_group` (UUID, null, indexé) ; `entry_group` (UUID, null, indexé — jeux V/C/B) ; `decommission` (FK `Decommission`, null) ; `import_batch` (FK `clubs.ImportBatch`, null) | **Append-only préservé** : champs fixés à la création, jamais mis à jour. Nouveaux types : `in_opening` « Reprise du registre », `in_transfer` « Transfert reçu », `out_transfer` « Transfert », `out_decommission` « Déclassement ». Contraintes : `transfer_group` non nul ⇔ type de transfert ; `decommission` non nul ⇔ `out_decommission` ; champs de provenance seulement sur `in_purchase`, `in_donation`, `in_opening` ; `acquisition_date` ≤ date d'enregistrement |
| `Article` (champs modifiés / ajoutés) | `category` : `max_length` 10 → 20, choix ajoutés `shorts`, `bibs`, `referee`, `accessories`, `furniture` ; `reference_condition` : choix `unknown` « Non renseigné » ; `kit_name` (60, blanc), `kit_piece` (`jersey` / `shorts` / `socks`, blanc) — §6, seulement si Q11 confirmée | Migration réversible tant qu'aucun article n'utilise les nouveaux choix (le retour arrière échoue proprement sinon : documenté) |
| `Decommission` (nouveau) | `club`, `article`, `holder` (null), `quantity` (> 0), `reason` (`worn` / `damaged` / `unusable` / `other`), `reason_note` (500), `noted_on`, `noted_by`, `status` (`pending` / `done` / `cancelled`), `exit_date`, `exit_destination` (120), `exit_movement` (OneToOne `StockMovement`, null), `cancelled_at`, `cancelled_by`, `cancel_reason` | Transitions dans le service seulement ; aucune suppression (`delete()` lève une erreur) |
| `InventoryHolderCount` (nouveau) | `club`, `line` (FK `InventoryLine`), `holder` (FK null), `holder_key` (texte : id du détenteur ou `none`, unicité (`line`, `holder_key`)), `theoretical_quantity`, `physical_quantity`, `discrepancy`, `relocation_transfer_group` (UUID null), `counted_at`, `counted_by` | `holder_key` évite une contrainte unique sur colonne nullable (comportement différent SQLite / MySQL). `InventoryLine` reste le total par article ; ses valeurs deviennent la somme des sous-comptages |
| `clubs.ImportBatch` | choix `ImportType` ajouté : `logistics_register` « Registre de l'intendance » | `max_length` 30 suffisant |

### 12.2 Services (`apps/logistics/services.py`)

`holder_stock(article, holder)` ; `stock_by_holder(article)` ; `create_holder` / `archive_holder` ; `record_transfer(article, source, destination, quantity, date, reason)` (atomique, deux mouvements, verrou `select_for_update` sur l'article pour éviter deux sorties concurrentes — **à tester aussi sur MySQL**, SQLite ignore ce verrou) ; `record_movement(..., holder, provenance)` (contrôle du stock de la source) ; `record_kit_entry(...)` ; `flag_decommission` / `execute_decommission` / `cancel_decommission` ; `preview_register_import(file)` / `import_register(file)` (même lecture pour l'aperçu et l'import, transaction unique) ; `build_register(club, filters)` (données de la page, du PDF et du CSV) ; `render_register_pdf(club, filters, actor)` (reportlab, déjà dans `requirements.txt`) ; `record_counts(..., holder)` et `record_relocation(line)`.

Toutes les comparaisons de noms (articles, détenteurs, donateurs) sont faites **en Python après normalisation** (casse, accents, espaces), pas par `__iexact` : la casse se compare différemment sous SQLite et MySQL.

### 12.3 Endpoints (préfixe `/logistics/`)

| Méthode et route | Rôles | Rôle |
| --- | --- | --- |
| `GET/POST holders/` ; `GET/PATCH holders/{id}/` ; `POST holders/{id}/archive/` | L : Pdt, VP, Trés, Coach, Int · É : Int | Détenteurs, avec `stock_total`, `articles_count`, `has_left_club` |
| `GET articles/` et `articles/{id}/` (enrichis) | inchangés | `stock_by_holder`, `pending_decommission`, `provenances` (5 dernières) |
| `POST movements/` (enrichi) | Int | `holder_id`, bloc `provenance` |
| `POST transfers/` | Int | Transfert |
| `POST kit-entries/` | Int | Jeu V/C/B (§6) |
| `GET/POST decommissions/` ; `GET decommissions/{id}/` ; `POST decommissions/{id}/execute/` ; `POST decommissions/{id}/cancel/` | L : lecteurs · É : Int | Déclassement |
| `POST register-imports/preview/` ; `POST register-imports/` ; `GET register-imports/{id}/report/` | Int | Import (multipart), rapport servi par vue authentifiée |
| `GET register/` ; `GET register/pdf/` ; `GET register/csv/` | lecteurs (Q22) | Registre et exports, filtres en paramètres |
| `POST inventories/{id}/counts/` (enrichi) ; `POST inventories/{id}/lines/{line}/relocate/` | Int | Comptage par détenteur, déplacement constaté |
| `matches/{id}/equipment/out/` et `.../return/` (enrichis) | Coach, Int | `holder_id` par ligne, `suggested_holder` dans la réponse |

Chaque endpoint déclare ses permissions (matrice 2.4) et filtre par le club actif ; un identifiant d'un autre club renvoie 404.

### 12.4 Journal d'activité (règle 6)

`logistics.holder.created|updated|archived` ; `logistics.transfer.created` (un seul enregistrement pour les deux mouvements, avec `transfer_group`) ; `logistics.stock_movement.created` (avec provenance et détenteur dans l'instantané) ; `logistics.kit_entry.created` ; `logistics.decommission.flagged|executed|cancelled` ; `logistics.register_import.committed` (compteurs, pas le contenu du fichier) ; `logistics.inventory.counted` (avec détenteur) ; `logistics.inventory.relocated`. Proposition : `logistics.register.exported` pour chaque PDF / CSV téléchargé (le registre contient des noms de personnes) — Q22.

### 12.5 Étanchéité (tests à prévoir par `test-engineer`)

Pour chaque nouveau modèle et endpoint : un utilisateur du club A ne voit, ne transfère, ne déclasse, n'importe et n'exporte rien du club B (404) ; un `holder_id`, `article_id`, `donor_membership_id` ou `decommission_id` d'un autre club est refusé ; le PDF et le CSV ne contiennent que le club actif ; un détenteur joueur dont l'adhésion est close ne rend pas le matériel visible à son nouveau club.

---

## 13. Compatibilité avec les données existantes

1. **Mouvements existants** : aucun n'est modifié (append-only). Leur `holder` reste vide → stock « Non localisé » ; leur provenance est vide → « Origine non renseignée ». Pour les localiser : transfert « Non localisé → détenteur » (§4.3), qui laisse une trace datée.
2. **Articles existants** : catégorie et état inchangés ; le choix « Non renseigné » n'est appliqué à aucun article existant.
3. **Inventaires existants** (dont 2026-T3 clôturé) : affichés comme aujourd'hui ; une ligne sans sous-comptage par détenteur s'affiche « Comptage global ».
4. **Inventaire ouvert pendant la mise en service** : le comptage par détenteur ne s'applique qu'aux inventaires ouverts **après** la mise en service ; l'import du registre est refusé tant qu'un inventaire est ouvert.
5. **Feuille de match** : si l'article n'a aucun détenteur, la sortie se fait depuis « Non localisé » sans rien demander au Coach (comportement actuel).
6. **Articles de test du club pilote** (« Maillots équipe A » 20, « Ballons de match » 8, « Trousse de premiers secours » 3, inventaire 2026-T3 clôturé) : **rien n'est fait sans décision (Q17)**. Ils ne peuvent pas être supprimés (mouvements protégés, inventaire clôturé qui les référence). Options : (a) les garder ; (b) les sortir par un mouvement « Perte » motivé « Données de test » puis les archiver (archivage refusé tant que le stock n'est pas nul, point n° 6 de `logistique.md`) ; (c) les archiver après une sortie d'un type dédié à créer. Proposition : (b), **avant** l'import du registre, pour que le premier inventaire réel parte du registre seul.
7. **Rien n'est écrit dans les migrations** sur le club pilote (ni nom, ni détenteur, ni article) : la reprise passe par l'import (§9), exécuté par l'Intendant ou par `data-import` après validation.

---

## 14. États (complète `logistique.md` §7)

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Où est le matériel | 3 lignes squelettes | §3.2 | « Impossible de charger les détenteurs. » + « Réessayer » |
| À déclasser | 2 lignes | « Aucun élément à déclasser. » | Modèle standard |
| Registre de l'intendance | Barre de progression 3 px + squelette de 3 cartes | « Le registre est vide. » + (Intendant) « Importer le registre » ; avec filtre : « Aucun résultat pour « {recherche} ». » + « Effacer les filtres » | Chaque carte échoue seule, « Réessayer » |
| Import | « Analyse du fichier… », puis « Import en cours… » (fermeture bloquée) | « Aucune ligne n'est prête à être importée. » | Bandeau `danger`, texte de l'API ; fichier et choix conservés |
| PDF / CSV | Bouton `loading` | — | Toast « Le registre n'a pas pu être généré. Réessayez. » |
| Hors connexion | — | — | Transfert, déclassement, import, comptage : bouton désactivé, « Cette action nécessite une connexion. » ; PDF indisponible |

Succès : toasts listés dans chaque modale. Clés `StatusBadge` à ajouter : `holder_left` « A quitté le club » (rouge) ; `unlocated` « À localiser » (gris) ; `decommission_pending` « À déclasser » (orange) ; `decommission_done` « Déclassé » (gris) ; `decommission_cancelled` « Annulé » (gris) ; `article_created` « Article créé » (violet) ; `relocation_pending` « Écart de localisation » (orange) ; `relocation_done` « Déplacement enregistré » (vert). Existantes réutilisées : `failed` « Échec », `ready` « Prête ».

## 15. Mobile (360 px) et ordinateur

- 360 px : une colonne ; ordre des cartes de `/materiel` : Inventaire trimestriel, **Où est le matériel**, Catalogue, **À déclasser**, Sortis pour un match, Registre des mouvements, Inventaires passés. `HolderPicker` : puces sur deux lignes au plus, 36 px de haut, zone tactile 44 px. Registre : listes compactes, jamais de tableau à 7 colonnes. Import en plein écran, pied collant.
- ≥ 1024 px : colonne latérale de `/materiel` : Inventaire trimestriel, Où est le matériel, À déclasser, Sortis pour un match, Inventaires passés ; principale : Catalogue, Registre des mouvements. Registre de l'intendance : tableaux complets, largeur maximale 1200 px.
- Texte 14–16 px ; quantités, écarts et quantités à déclasser en 14 px au moins, tabular-nums ; titres ≤ 24 px ; trois thèmes par variables CSS ; badges aux couleurs fixes.

---

## 16. Questions au client

Reprises de l'analyse (n° 11 à 18) :

- **Q11** — Que signifient **V / C / B** ? Proposition : vareuse / culotte / bas. Qu'est-ce qu'un **« jeu »** (« 7J + 2V de gardien ») ? Proposition : une ligne d'acquisition d'une tenue complète ; « 2V » = les 2 vareuses rouge-noir de gardien. Le classeur parle de « 5 jeux intendance + 2 jeux V. Président » : qu'est-ce que « V. Président » ? Bloque le §6.
- **Q12** — Le chiffre « 24 » non libellé du classeur correspond-il aux **24 chasubles** du PDF (Simon Paluku, 18/10/2026) ?
- **Q13** — Bottines : **23 paires** (1 + 14 + 3, puis 5 le 18/10/2026) ? Gants : 5 paires, et que veut dire « Restitution » (22/06/2025, Steve Pango) ? « Caisse de l'équipe » = « Frais de l'équipe » ?
- **Q14** — Localisation réelle : le PDF fait-il foi sur le classeur ? Trousse médicale et table de tennis : chez qui ? Vareuses rouge-noir 20 : chez le détenteur A ou chez le détenteur B ? Orthographe des donateurs à retenir.
- **Q15** — Éléments à déclasser (18 rouges, 19 bleues, 7 ballons, 9 paires) : motif, chez qui, date de sortie prévue ; « rouges » = rouge-blanc ou rouge-noir, et dans quelles proportions ? La sortie demande-t-elle l'accord du Président ou du bureau ?
- **Q16** — Le **détenteur** doit-il être ajouté (circuit 9.4) ? Obligatoire ou facultatif ? Proposition : ajouté, facultatif, avec « Non localisé ».
- **Q17** — Articles de test déjà en base : garder, ou sortir puis archiver avant l'import (proposition (b), §13 point 6) ?
- **Q18** — État des articles non renseigné : accepter un état « Non renseigné » ? Proposition : oui.

Nouvelles questions nées de cette spécification :

- **Q19** — Un joueur détenteur sans rôle Intendant doit-il voir le matériel qu'il détient (par exemple sur son profil) ? Proposition : non (matrice 2.4 inchangée).
- **Q20** — Un détenteur qui quitte le club avec du matériel : simple alerte (proposition), ou blocage du départ / du quitus ? Le blocage serait une règle nouvelle liée au mercato (4.14).
- **Q21** — Les pièces à déclasser peuvent-elles encore sortir pour un match ? Proposition : oui, sans règle nouvelle, avec l'indication « dont {k} à déclasser ».
- **Q22** — Qui peut télécharger le registre PDF / CSV (proposition : tous les lecteurs de la matrice) ? Journaliser chaque téléchargement (proposition : oui) ?
- **Q23** — Liste des catégories du §8 ; libellé « Maillots » ou « Vareuses » ?
- **Q24** — Faut-il lire directement le classeur `.xlsx` (dépendance supplémentaire) ? Proposition : non, CSV seulement, comme les autres imports.
- **Q25** — Import « tout ou rien » (proposition) ou ligne par ligne comme les cotisations ?
- **Q26** — Écart de localisation constaté à l'inventaire : l'enregistrer comme déplacement, sans cause (proposition) ?
- Restent ouverts dans `logistique.md` §12 et liés à cette évolution : n° 3 (non-rendu après un match), n° 5 (correction d'un mouvement erroné : l'import rend la question plus pressante), n° 7 (stock initial : **résolu par le type « Reprise du registre » si validé**), n° 12 (ajustement du stock à la clôture).

---

## 17. Ordre de réalisation proposé

Prérequis : réponses du client à Q16, Q18, Q23 (lot 1) ; Q11 (lot 6) ; Q12 à Q15 et Q17 (lot 8).

| Lot | Contenu | Dépend de | Agents | Taille |
| --- | --- | --- | --- | --- |
| 1 | Détenteurs (`Holder`), `holder` sur les mouvements, stock par détenteur, transferts, catégories et état « Non renseigné », type « Reprise du registre » | Q16, Q18, Q23 | backend-dev, test-engineer | M |
| 2 | Interface : carte « Où est le matériel », modales §4.1 à §4.4, colonnes du catalogue, champ « Chez » dans les mouvements et la feuille de match | 1 | frontend-dev | M |
| 3 | Provenances (champs, modale §5.2, section « Provenances » de l'article) | 1 | backend-dev, frontend-dev | S |
| 4 | Déclassement (modèle, services, carte et modales §7) | 1 | backend-dev, frontend-dev, test-engineer | M |
| 5 | Registre de l'intendance : page, PDF, CSV | 1, 3, 4 | backend-dev (PDF), frontend-dev | M |
| 6 | Tenues V / C / B (§6) et leur affichage dans le registre | Q11, 3, 5 | backend-dev, frontend-dev | M |
| 7 | Import du registre (aperçu, import, rapport) | 1, 3 (et 6 si Q11 confirmée) | backend-dev, frontend-dev, test-engineer | L |
| 8 | Reprise réelle du club pilote : sort des articles de test, création des détenteurs, conversion PDF → CSV, aperçu validé par l'Intendant, import, signalement des éléments à déclasser | 7, Q12 à Q15, Q17 | data-import (avec l'Intendant) | S |
| 9 | Inventaire par détenteur et écarts de localisation | 1, 2 | backend-dev, frontend-dev, test-engineer | L |
| 10 | Revue `security-auditor` (exports, fichiers privés, étanchéité) puis `cdc-reviewer` ; vérification visuelle à 360 px | chaque lot | — | S |

Le lot 9 peut être livré après la reprise (lot 8). Attention au calendrier : nous sommes au 4e trimestre 2026. Si l'inventaire du 4e trimestre 2026 est ouvert avant le lot 8, l'import du registre sera refusé jusqu'à sa clôture (§9.1). Proposition : faire la reprise (lot 8) **avant** d'ouvrir cet inventaire, pour qu'il porte sur le registre réel ; il se fera en comptage global si le lot 9 n'est pas livré.
