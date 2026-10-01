# Annexe C — Formats CSV

Cahier des charges 10.1 : « Modèles d'import des joueurs et des cotisations, avec
exemples » — produite au Lot 1 (import des joueurs) **et** au Lot 2 (import des
cotisations historiques).

**État à ce jour (Lot 1) : seule la partie « import des joueurs » est
documentée ci-dessous.** Le module `treasury` (cotisations, types de
cotisation, paiements) est encore une coquille vide côté backend au Lot 1 ; la
modale d'import des cotisations historiques (CDC 4.4.8) s'appuiera sur le
service `finance-engine` `allocate_payment`, qui n'existe pas encore. Documenter
un format de fichier contre une API qui n'existe pas reviendrait à l'inventer :
**la partie « cotisations » de cette annexe est donc reportée au Lot 2**, dès
que `treasury` et `allocate_payment` seront construits. Ce document sera
complété à ce moment-là, sans changer la partie « joueurs ».

## 1. Import des joueurs (CDC 4.1)

Modale « Importer des joueurs » (`club-comite-bureau.md` §4.6). Implémentation
de référence : `backend/apps/clubs/services.py`, fonction
`import_players_from_csv` (et les fonctions de parsing qu'elle appelle :
`_import_single_row`, `_parse_position`, `_parse_optional_date`,
`_parse_optional_jersey_number`, `_parse_optional_decimal`). Ce document
reflète le comportement réellement codé et testé
(`backend/apps/clubs/tests/test_services_player_import.py`) : en cas d'écart
constaté entre ce document et le code, **le code fait foi** et ce document doit
être corrigé.

### 1.1 Fichier attendu

- Format CSV, séparateur virgule `,`, une ligne d'en-têtes suivie d'une ligne
  par joueur.
- Encodage **UTF-8** (avec ou sans BOM — `utf-8-sig` est accepté). Un fichier
  dans un autre encodage est rejeté avec le message : « Le fichier n'est pas
  encodé en UTF-8. Réenregistrez-le en UTF-8 avant de l'importer. »
  (`import_players_from_csv`).
- La ligne 1 est l'en-tête ; la première ligne de données est donc la ligne 2
  du fichier, et c'est ce numéro de ligne (celui du fichier, pas celui des
  données) qui apparaît dans le rapport (« Ligne 12 : … », conforme à
  l'exemple du CDC 4.1).
- Chaque ligne est traitée indépendamment : une ligne en échec n'empêche
  jamais l'import des lignes suivantes (`import_players_from_csv`, boucle sur
  `csv.DictReader`).

### 1.2 Colonnes, dans cet ordre exact

```
email,prenom,nom,telephone,poste,numero,date_naissance,poids,taille,type_cotisation
```

| # | Colonne | Obligatoire | Format / valeurs acceptées | Message d'erreur si invalide | Référence code |
| --- | --- | --- | --- | --- | --- |
| 1 | `email` | **Oui** | Adresse email valide (`django.core.validators.validate_email`). Si l'email existe déjà sur la plateforme dans **ce club**, la ligne met à jour la fiche existante (aucun doublon créé). Si l'email existe dans un **autre** club et que le compte n'y a **aucune adhésion active**, une nouvelle adhésion est créée dans ce club sans recréer le compte utilisateur (interprétation par défaut, non détaillée par le CDC 4.1 pour ce cas précis — voir §2 ci-dessous). Si le compte a déjà une adhésion **active** dans un autre club, la ligne échoue (garde de sécurité, tâche 1.13 : une seconde adhésion active rendrait le club actif ambigu pour ce compte et lui ferait perdre l'accès à ses clubs). | « email manquant. » / « email invalide. » / « cette ligne n'a pas pu être importée. » (compte déjà actif ailleurs, message volontairement neutre pour ne pas révéler l'existence du compte) | `_import_single_row`, `create_or_update_player` |
| 2 | `prenom` | **Oui** | Texte libre. | « prenom manquant. » | `_import_single_row` |
| 3 | `nom` | **Oui** | Texte libre. | « nom manquant. » | `_import_single_row` |
| 4 | `telephone` | Non | Texte libre (WhatsApp, CDC 4.1). Aucune validation de format. | — | `_import_single_row` |
| 5 | `poste` | Non | Vide accepté. Sinon, un des libellés français **ou** codes internes suivants, insensible à la casse et aux accents : `Gardien`/`goalkeeper`, `Defenseur` (ou `Défenseur`)/`defender`, `Milieu`/`midfielder`, `Attaquant`/`forward`. **Seules ces huit graphies sont reconnues** — un libellé non listé (ex. abréviation `GK`, ou variante non prévue) fait échouer la ligne, y compris pour un vrai poste, tant que la valeur exacte n'est pas dans cette liste. | « poste inconnu : « … » (attendu Gardien, Defenseur, Milieu ou Attaquant, ou vide). » | `_parse_position` |
| 6 | `numero` | Non | Entier entre 1 et 99. Un numéro déjà porté par un autre joueur **actif** du club fait échouer la ligne. | « numero de maillot invalide : « … ». » / « … (doit être entre 1 et 99). » / « le numero *N* est déjà porté par *Prénom Nom*. » | `_parse_optional_jersey_number`, `create_or_update_player` |
| 7 | `date_naissance` | Non | `JJ/MM/AAAA` **ou** `AAAA-MM-JJ`. Aucun autre format. | « date de naissance invalide : « … » (attendu JJ/MM/AAAA ou AAAA-MM-JJ). » | `_parse_optional_date` |
| 8 | `poids` | Non | Décimal en kilogrammes. Séparateur décimal `,` ou `.` accepté. | « poids invalide : « … ». » | `_parse_optional_decimal` |
| 9 | `taille` | Non | Décimal en centimètres. Séparateur décimal `,` ou `.` accepté. | « taille invalide : « … ». » | `_parse_optional_decimal` |
| 10 | `type_cotisation` | Non | **Texte libre à ce stade — point ouvert.** Voir §3. | Ne bloque jamais la ligne, quelle que soit la valeur (y compris vide ou incohérente). | `_import_single_row` |

**Colonne absente vs cellule vide** : une colonne facultative totalement
absente du fichier est traitée exactement comme une cellule vide — jamais un
échec pour un poste ou une date manquants (critère d'acceptation CDC 4.1 :
« un club importé de 40 joueurs sans poste ni date passe sans échec »).

### 1.3 Comportement à l'import

- Les joueurs importés sont considérés comme **membres historiques** : ils
  passent directement au statut « Inscrit » (`Membership.Status.ACTIVE`),
  **sans parrainage** (`sponsor=None`).
- Un email déjà présent **dans ce club** met à jour la fiche existante : seuls
  les champs fournis (non vides) sur la ligne écrasent la valeur existante ;
  un champ absent de la ligne n'efface jamais une donnée déjà renseignée, et
  le statut d'une adhésion existante n'est **jamais** modifié par une
  réimportation.
- Le mot de passe initial d'un compte nouvellement créé est l'email, avec
  changement obligatoire à la première connexion (CDC 4.1) ; tant qu'il n'est
  pas changé, le joueur n'accède à aucune donnée.
- À la fin de l'import, un rapport (`rapport_import.csv`, colonnes `ligne,
  resultat, message`) liste chaque ligne importée ou en échec, avec son
  numéro de ligne et un message en français (`_build_import_report_file`).

### 1.4 Exemples

Le fichier `docs/annexes/modele-import-joueurs.csv` (même contenu que le
modèle téléchargeable depuis la modale) contient les exemples suivants — noms,
emails et numéros de téléphone sont **entièrement fictifs** :

```csv
email,prenom,nom,telephone,poste,numero,date_naissance,poids,taille,type_cotisation
jean.mbala@example.com,Jean,Mbala,+243811111111,Gardien,1,14/03/1990,78.5,182,Mensuelle 20$
alice.tshimanga@example.com,Alice,Tshimanga,,,,,,,
patrick.kalala@example.com,Patrick,Kalala,,midfielder,8,1988-07-22,74,178,Mensuelle 10$
sarah.ilunga@example.com,Sarah,Ilunga,0899999999,Attaquant,9,05/11/1995,"62,3",167,Mensuelle 5$
```

| Ligne | Ce qu'elle illustre |
| --- | --- |
| `jean.mbala@example.com` | Ligne complète, toutes colonnes remplies ; poste en libellé français (« Gardien ») ; date au format `JJ/MM/AAAA` ; poids avec séparateur décimal point. |
| `alice.tshimanga@example.com` | Seuls les 3 champs obligatoires (`email`, `prenom`, `nom`) sont renseignés ; poste et date de naissance vides, comme toutes les autres colonnes facultatives — la ligne est importée sans échec. |
| `patrick.kalala@example.com` | Poste saisi avec le code interne (`midfielder`) plutôt que le libellé français ; date au format `AAAA-MM-JJ`. |
| `sarah.ilunga@example.com` | Poids avec virgule décimale (`62,3`) — **la valeur doit être mise entre guillemets** dans le fichier CSV, sinon la virgule est interprétée comme le séparateur de colonnes et la ligne échoue ou se décale (voir §1.5). |

### 1.5 Remarque pratique : virgule décimale et virgule séparatrice de colonnes

Le fichier utilise la virgule `,` comme séparateur de colonnes (dialecte CSV
par défaut de `csv.DictReader`, aucune configuration régionale). Si `poids` ou
`taille` est saisi avec une virgule comme séparateur décimal (ex. `62,3`), la
cellule doit être entourée de guillemets doubles (`"62,3"`) pour rester une
seule colonne. Un tableur en locale française (Excel, LibreOffice) exporte
parfois en CSV avec un point-virgule `;` comme séparateur de colonnes : un tel
fichier ne serait pas reconnu tel quel par cet import (colonnes non
détectées) — recommander l'export « CSV UTF-8 (délimité par des virgules) ».
Ce point n'est pas un format alternatif supporté par le code, seulement une
mise en garde ; en cas de doute, utiliser le point comme séparateur décimal.

## 2. Point ouvert signalé (CLAUDE.md §9.4)

Le cas « email déjà présent sur la plateforme, mais dans un club différent »
n'est pas détaillé par le CDC 4.1 pour l'import CSV. Le code applique par
défaut, à titre provisoire (voir le commentaire de
`create_or_update_player` dans `backend/apps/clubs/services.py`) :

- si le compte n'a **aucune adhésion active** dans un autre club, il n'est pas
  recréé ni modifié au-delà de ses champs personnels usuels, et une nouvelle
  adhésion est créée dans le club important ;
- si le compte a **déjà une adhésion active** dans un autre club, la ligne
  échoue purement et simplement (garde de sécurité ajoutée à la tâche 1.13,
  message neutre « cette ligne n'a pas pu être importée. », voir tableau §1.2) —
  ce correctif ferme une faille (n'importe qui pouvait couper l'accès d'un
  Président d'un autre club à son propre club), mais **la question métier
  reste ouverte** : ce refus est-il le comportement définitif souhaité, ou
  faut-il à terme un vrai mécanisme de transfert entre clubs (Mercato) qui
  gérerait ce cas autrement qu'en le bloquant ?

**À confirmer par le client.**

## 3. Point ouvert signalé — colonne `type_cotisation` (Lot 1)

Le CDC 4.1 documente la colonne `type_cotisation` dans le modèle CSV, mais le
module `treasury` (qui porterait un vrai modèle `ContributionType`) n'existe
pas encore au Lot 1. Décision par défaut appliquée en attendant (voir le
commentaire du champ `Membership.requested_contribution_type_label` dans
`backend/apps/clubs/models.py`) :

- la valeur de la colonne est conservée **telle quelle**, comme texte libre
  (`Membership.requested_contribution_type_label`), sans validation ni
  rattachement à un type existant ;
- une valeur vide, incohérente ou inventée **ne bloque jamais** l'import de la
  ligne (`test_type_cotisation_invalide_ou_vide_ne_bloque_jamais_la_ligne`) ;
- cette information sera rattachée au véritable type de cotisation
  (`ContributionType`, `finance-engine`) par une migration additive au Lot 2,
  sans perte de donnée dans l'intervalle.

Ce n'est donc **pas** un format définitif : à revoir avec `finance-engine` dès
que `treasury` existe.

## 4. Import des cotisations historiques — reporté au Lot 2

Non traité dans cette version de l'annexe (voir l'avertissement en tête de
document). Reviendra avec :

- la colonne fournie par la modale (type de cotisation et année, CDC 4.4.8),
  pas par le fichier lui-même ;
- une colonne par mois dans le fichier, une ligne par joueur ;
- la cellule `ok` signifiant « mois payé au montant plein du type » ;
- la répartition du montant confiée au service `finance-engine`
  (`allocate_payment`), jamais recalculée par le module d'import ;
- un aperçu de la grille résultante avant validation, import en transaction
  (tout ou rien par ligne).
