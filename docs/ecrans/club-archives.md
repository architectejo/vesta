# Écran — Archive des documents

> **Statut : spec alignée sur le cahier des charges mis à jour (4.15.1 ; décisions du client du 11/10/2026, 10.3 n° 169 à 173).** Écran issu des retours des clubs partenaires après la démonstration (`inscriptions.md`) : rôle **Secrétaire** et archive des documents de réunion. La fonction est désormais inscrite au CDC (rôle aux 2.2 à 2.4, module au 4.15.1). Les droits ci-dessous correspondent au 10.3 n° 171 ; les points encore ouverts sont au §8.

Sources : CDC 3.1 à 3.4 (charte), 3.5 (marque blanche), 5 (journal), 6.7 (fichiers privés), 7.4 (session par onglet), 1.4 (lecture seule) ; CLAUDE.md §2 règles 6, 8, 10, 13 à 20 ; décision client du 11/10/2026. Composants : `Modal`, `ConfirmDialog`, `ListSection`, `StatusBadge`, `EmptyState`, `Skeleton`, `FileField`, `Banner`, `Toast` (`docs/lot0/design-system.md`) ; icônes via `design-system/icons.ts` (§9).

Écrans liés : `club-comite-bureau.md` (nomination du Secrétaire, révision 11/10), `club-accueil.md` et `fil-public-communication.md` (publication des communiqués par le Secrétaire), `assemblees-page-ag.md` (préparation de l'AG par le Secrétaire).

## 1. Objectif

Conserver dans Vesta, en un seul endroit privé, les documents officiels du club (procès-verbaux de réunion, lettres de convocation, autres documents) et les retrouver en quelques secondes depuis un téléphone : par catégorie, par année ou par titre. Rien n'est jamais supprimé : un document déposé par erreur est **retiré**, pas effacé.

## 2. Accès

Route `/club/archives`. Entrée de navigation « Club › Archives » (icône `IconNavArchives`), placée juste après « Communiqués ». L'entrée n'apparaît que pour les rôles autorisés en lecture ; c'est l'API qui renvoie les droits (`can_read_archives`, `can_upload`, `can_withdraw`), l'interface ne déduit jamais un droit du libellé d'un rôle.

| Action | Qui (position par défaut, à confirmer) |
| --- | --- |
| Voir la page, ouvrir un document, le télécharger | Membres du Bureau : Président, Vice-président, **Secrétaire**, Directeur sportif, Trésorier, Trésorier adjoint, Intendant |
| Déposer un document | Secrétaire, Président, Vice-président |
| Retirer un document | Secrétaire, Président, Vice-président |
| Voir les documents retirés | Membres du Bureau (mêmes rôles que la lecture, 10.3 n° 172) |

- Lecture « Bureau » alignée sur la composition du canal « Bureau » (CDC 10.2 n° 165 : sans Médecin, Coach ni Capitaine), plus le Secrétaire. Médecin, Coach, Capitaine et simples joueurs n'ont **aucun accès** (position la plus restrictive, §8 point 3).
- Un joueur sans droit qui ouvre `/club/archives` (lien collé, ancien favori) voit l'en-tête de page puis un `EmptyState` variante erreur : « Vous n'avez pas accès à cette page. » — précision « Les archives sont réservées aux membres du Bureau. » — sans bouton. Aucune donnée n'est chargée.
- Superuser : pas d'accès hors session de support (Ghost Mode, 5.4).

## 3. Structure de la page

**En-tête** (`PageHeader`) : titre « Archives » ; contexte « {nom du club} · {n} document(s) » ({n} = documents actifs, renvoyé par l'API). Action principale (Secrétaire, Président, VP) : « Déposer un document » (icône `IconUpload`) → modale §4.1. Menu « … » (mêmes rôles) : « Afficher les documents retirés » / « Masquer les documents retirés » (bascule, §3.3).

**Bandeaux** éventuels : lecture seule (licence expirée), hors connexion (`design-system.md` §3.1 `Banner`).

Une seule section en carte :

### 3.1 Carte « Documents »

En-tête de carte : titre « Documents » ; compteur « {affichés} sur {total} » (13 px, muted).

**Barre de filtres** (dans la carte, au-dessus de la liste ; seule exception tolérée de champs dans une page, `design-system.md` §1.1) :

1. **Recherche** : champ 36 px, icône `IconSearch`, placeholder « Rechercher un titre ». Recherche côté API, debounce 300 ms.
2. **Catégorie** :
   - ≥ 640 px : `SegmentedControl` « Toutes » / « PV de réunion » / « Convocations » / « Autres ».
   - < 640 px : `Select` natif 36 px, libellé visible « Catégorie », options identiques (liste courte non-joueur, autorisée par `design-system.md` §3.1).
3. **Année** : `Select` natif 36 px, libellé visible « Année » ; options « Toutes les années » puis les années **qui contiennent au moins un document** (renvoyées par l'API, de la plus récente à la plus ancienne). L'année est celle de la **date du document**, pas celle du dépôt.

Filtres actifs reflétés dans l'URL (`?categorie=pv&annee=2026&q=…`) pour survivre au retour arrière et au partage entre onglets de la même session. Lien « Effacer les filtres » (ghost, 13 px) visible dès qu'un filtre est actif. Ligne de résultat sous les filtres : « {n} document(s) » (13 px, muted).

**Liste** (`ListSection`) : **10 derniers** documents selon le filtre + bouton « Voir plus » (ajoute les 10 suivants en place ; « Chargement… » pendant la requête ; disparaît quand tout est affiché). Tri : date du document décroissante, puis date de dépôt décroissante.

**Ligne de document** (56 px min., entièrement cliquable, focusable, Entrée ouvre) :

- à gauche, carré 40 px fond `--color-surface-muted`, rayon 6 px, icône 20 px selon le type de fichier : `IconDocumentPdf` (PDF) ou `IconDocumentImage` (JPEG, PNG, WebP) ;
- titre 14 px/500, deux lignes au plus, retour à la ligne (pas de troncature en une ligne) ;
- dessous, 13 px muted : « {Catégorie} · {date du document courte} » (ex. « PV de réunion · dim. 4 oct. 2026 ») ;
- à droite, uniquement pour un document retiré : `StatusBadge` gris « Retiré » (§3.3).

Aucun bouton dans la ligne : toutes les actions sont dans la modale de détail (3.3). Clic → modale §4.2.

### 3.2 Libellés des catégories

| Clé API | Libellé (liste, détail, formulaire) | Libellé de filtre |
| --- | --- | --- |
| `meeting_minutes` | PV de réunion | PV de réunion |
| `convocation` | Convocation | Convocations |
| `other` | Autre document | Autres |

La catégorie est un texte simple, **pas un `StatusBadge`** (ce n'est pas un statut ; les couleurs de statut restent réservées aux statuts, 3.4).

### 3.3 Documents retirés

- Par défaut, la liste ne montre que les documents actifs.
- « Afficher les documents retirés » (menu « … » de l'en-tête, tous les membres du Bureau) ajoute les documents retirés à la liste, avec le badge gris « Retiré ». Le choix est mémorisé dans l'URL (`?retires=1`). Toast : aucun (changement d'affichage immédiat).
- Les documents retirés sont visibles et téléchargeables par le Bureau (10.3 n° 172) ; les autres rôles n'ont aucun accès à l'archive.

Footer.

## 4. Modales

### 4.1 « Déposer un document » — taille `md` (plein écran < 640 px)

Ouverte par « Déposer un document » (en-tête) ou par l'action de l'état vide. Sous-titre : aucun.

| Champ | Composant | Obligatoire | Règle | Erreur |
| --- | --- | --- | --- | --- |
| Titre | TextField | Oui | 150 caractères max., compteur à partir de 120 | « Ce champ est obligatoire. » ; « 150 caractères au maximum. » |
| Catégorie | SegmentedControl : « PV de réunion » / « Convocation » / « Autre » | Oui | Aucune valeur présélectionnée (évite un mauvais classement par inattention) | « Choisissez une catégorie. » |
| Date du document | DateField | Oui | Pré-remplie avec la date du jour (fuseau du club) ; pas dans le futur | « Ce champ est obligatoire. » ; « La date ne peut pas être dans le futur. » |
| Fichier | FileField : « Choisir un fichier » + « Prendre une photo » (mobile) | Oui | Un seul fichier ; PDF, JPEG, PNG ou WebP ; 10 Mo maximum (6.7) | « Ajoutez le fichier du document. » ; « Format non accepté : JPEG, PNG, WebP ou PDF. » ; « Fichier trop lourd : 10 Mo maximum. » |

- Aides :
  - sous « Titre » : « Exemple : PV de la réunion du bureau du 4 octobre 2026. »
  - sous « Date du document » : « Date de la réunion ou date inscrite sur le document. »
  - sous « Fichier » : « Un document de plusieurs pages : préférez un PDF. Une photo doit rester lisible : cadrez la page entière, sans reflet. »
- **Aperçu après choix du fichier** : image → vignette 96 px de haut avec nom du fichier et taille ; PDF → icône `IconDocumentPdf` + nom + taille (« 1,2 Mo ») ; bouton ghost « Changer de fichier ». Pas de rendu de PDF dans le navigateur.
- **Compression des photos** : la compression navigateur standard du `FileField` (6.7) s'applique, mais avec un plafond de **2 400 px** de côté au lieu de 1 600 px pour garder un texte lisible (proposition, §8 point 9).
- **Envoi** : barre de progression fine sous l'aperçu pendant le téléversement (« Envoi… {x} % ») — utile sur réseau faible ; bouton principal en état `loading` « Envoi… » ; fermeture bloquée pendant l'envoi (`design-system.md` §3.2).
- Hors connexion : bouton « Déposer » désactivé, aide « Cette action nécessite une connexion. » (le dépôt n'est pas une action hors connexion, 6.6).
- Fermeture avec saisie en cours (titre tapé ou fichier choisi) : `ConfirmDialog` standard « Abandonner les modifications ? ».
- Pied : « Annuler » / « Déposer ».
- Succès : fermeture, toast « Document déposé dans les archives. », le document apparaît en tête de liste s'il correspond aux filtres actifs ; sinon toast « Document déposé dans les archives. Il n'apparaît pas avec les filtres actuels. » avec action « Effacer les filtres ».
- Erreurs API : erreur de champ sous le champ ; erreur générale dans le bandeau du corps (« Une erreur est survenue de notre côté. Réessayez dans un instant. », « Connexion impossible. Vérifiez votre réseau et réessayez. »). Le fichier choisi est **conservé** après une erreur réseau pour pouvoir réessayer sans le rechoisir.

### 4.2 « Document » (détail) — taille `lg` (plein écran < 640 px)

- **En-tête** : titre = titre du document (deux lignes au plus) ; sous-titre « {Catégorie} · {date longue du document} ». Si retiré : `StatusBadge` gris « Retiré » à côté du sous-titre. Menu « … » (Secrétaire, Président, VP, document actif) : « Retirer le document » (icône `IconWithdraw`) → §4.3.
- **Corps**, dans l'ordre :
  1. **Aperçu** :
     - image : affichée à pleine largeur du corps (hauteur auto, 60 vh max.), chargée par la vue authentifiée (composant `AuthenticatedImage`) ; un appui l'ouvre en plein écran (zoom natif du navigateur) ;
     - PDF : bloc 72 px fond `--color-surface-muted` avec icône `IconDocumentPdf`, nom du fichier, taille, nombre de pages si l'API le fournit, et bouton secondaire `sm` « Ouvrir » (icône `IconOpenExternal`) qui récupère le fichier par la vue authentifiée puis l'ouvre dans la visionneuse du navigateur ou du téléphone. Pas d'aperçu intégré du PDF (non pris en charge de façon fiable sur Android, coûteux sur réseau faible).
  2. **Informations** (liste de définitions, 14 px) : « Catégorie » ; « Date du document » ; « Déposé par » (avatar 24 px + nom + fonction au moment du dépôt, ex. « Secrétaire ») ; « Déposé le » (date et heure) ; « Fichier » (format et taille).
  3. **Retrait** (document retiré seulement) : bandeau neutre « Retiré le {date} par {nom} — Motif : {motif} ».
- **Pied** : « Fermer » / action principale « Télécharger » (icône `IconDownload`), état `loading` « Téléchargement… ». Disponible aussi pour un document retiré (consultation conservée).
- **Accès au fichier** : uniquement par une vue authentifiée de l'API qui vérifie le club actif et le rôle (CDC 6.7, CLAUDE.md règle 10) ; aucun lien public, aucune adresse de fichier affichée ni copiable. Le fichier est récupéré avec le jeton de session puis remis au navigateur (objet `blob`) ; la session étant propre à l'onglet (7.4), aucun lien direct n'est ouvert sans authentification.
- **Chargement** : titre affiché dès l'ouverture s'il est connu, squelette dans le corps (bloc aperçu + 4 lignes).
- **Erreurs** : document introuvable → « Cet élément n'existe plus. » + « Fermer » ; fichier indisponible → dans le bloc aperçu « Le fichier n'a pas pu être chargé. » + « Réessayer » ; téléchargement échoué → toast « Le téléchargement a échoué. Vérifiez votre réseau et réessayez. »

### 4.3 « Retirer le document » — taille `sm` (panneau bas < 640 px), niveau 2 au-dessus du détail

Formulaire de confirmation court (pas un `ConfirmDialog` simple, car il porte un motif) :

- Titre : « Retirer « {titre} » des archives ? »
- Texte : « Le document ne sera plus affiché dans la liste. Il n'est pas supprimé : il reste conservé et consultable par le Secrétaire, le Président et le Vice-président. »
- Champ « Motif du retrait » (TextArea, 3 lignes, obligatoire, 300 caractères max.) ; aide « Exemple : doublon, mauvais fichier, document remplacé. » ; erreur « Ce champ est obligatoire. »
- Pied : « Annuler » (focus par défaut) / « Retirer » (variante `danger`), état `loading` « Retrait… ».
- Succès : fermeture des deux niveaux, toast « Document retiré des archives. », la ligne disparaît de la liste (ou passe en « Retiré » si l'affichage des retirés est actif).
- Aucune action « Supprimer » n'existe, ni dans l'interface ni dans l'API (pas de suppression dure).

## 5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Page | Barre de progression 3 px + squelette (titre, contexte, carte) | — | Droit absent : « Vous n'avez pas accès à cette page. » (§2) |
| Liste « Documents » | 5 lignes squelettes `row` (carré 40 px + 2 lignes) | Sans filtre : icône `IconNavArchives`, « Aucun document archivé pour l'instant. » ; précision « Déposez ici les PV de réunion, les lettres de convocation et les autres documents officiels du club. » ; action (Secrétaire, Pdt, VP) « Déposer un document ». Pour les autres membres du Bureau : message seul, précision « Le Secrétaire dépose les documents officiels du club. » | « Impossible de charger les archives. » + « Réessayer » (`EmptyState` erreur) |
| Liste filtrée | Idem | « Aucun document ne correspond à ces filtres. » + bouton « Effacer les filtres » ; avec recherche : « Aucun document ne correspond à « {saisie} ». » | Idem |
| « Voir plus » | Bouton « Chargement… » | — | Toast « Connexion impossible. Vérifiez votre réseau et réessayez. », bouton revenu à « Voir plus » |
| Liste des années | `Select` désactivé avec « Chargement… » | Aucune année : `Select` masqué | `Select` limité à « Toutes les années » |
| Modale détail | Squelette dans le corps | — | Voir §4.2 |
| Hors connexion | — | — | Bandeau `info` ; liste déjà chargée lisible ; « Déposer un document », « Retirer » et « Télécharger » désactivés, aide « Cette action nécessite une connexion. » |
| Licence expirée | — | — | Bandeau `readonly` ; « Déposer un document » et « Retirer le document » masqués ; consultation et téléchargement conservés (`design-system.md` §5) |

Toasts de succès : « Document déposé dans les archives. » ; « Document retiré des archives. »

## 6. Mobile (360 px) et ordinateur

- **360 px** : marges 12 px ; « Déposer un document » sous la ligne de contexte, largeur automatique (40 px de haut) ; barre de filtres sur deux rangées : recherche pleine largeur de la carte, puis « Catégorie » et « Année » côte à côte (deux `Select` de 36 px, 50/50, libellés au-dessus en 13 px). Lignes de 56 px min., titre sur deux lignes. Modales `md` et `lg` en plein écran, pied « Annuler » / « Déposer » collé en bas même clavier ouvert ; « Retirer » en panneau bas.
- **≥ 640 px** : barre de filtres sur une rangée : recherche (flexible, 240 px min.), `SegmentedControl` catégorie, `Select` année.
- **≥ 1024 px** : colonne unique de 800 px max., centrée (consultation de documents, comme la page Communiqués). Modale de détail `lg` centrée ; l'aperçu d'image limité à 60 vh.
- Vérifications obligatoires à 360 px : titre de 150 caractères sans débordement ; nom de déposant long ; trois thèmes (Classic, Clair, Sombre) ; badge « Retiré » sur une ligne au titre long ; photo de document en portrait et en paysage dans le détail.

## 7. Journal et notifications

Aucun élément d'interface ; rappel pour `backend-dev` et `test-engineer`.

| Événement | Journal (CLAUDE.md règle 6) | Notification |
| --- | --- | --- |
| Dépôt d'un document | Oui (titre, catégorie, date du document ; jamais le contenu du fichier) | Aucune (proposition, §8 point 8) |
| Retrait d'un document | Oui (avec motif) | Aucune |
| Consultation / téléchargement | Non exigé par le CDC (aucune donnée modifiée) ; proposition de le journaliser, comme les documents médicaux (§8 point 10) | Aucune |

Le stockage est celui des fichiers privés du club (hors `public_html`, CDC 6.7). Le type réel du fichier est vérifié côté serveur (7.6). Toutes les requêtes passent par les querysets filtrés par club (CLAUDE.md règle 8).

## 8. Décisions par défaut et points ouverts

1. **Inscription au CDC (réglée)** : le rôle Secrétaire et l'archive figurent au CDC (4.15.1, 10.3 n° 169 à 173). Reste à vérifier, à chaque révision du CDC, que cet écran suit toujours ces sections.
2. **Droits d'écriture** : dépôt et retrait par Secrétaire, Président, VP (10.3 n° 171). Alternative plus stricte : Secrétaire seul (le Président et le VP n'interviendraient qu'en cas de poste vacant).
3. **Droits de lecture** : Bureau = Pdt, VP, Secrétaire, DS, Trésorier, adjoint, Intendant, aligné sur le canal « Bureau » (10.2 n° 165), **sans Médecin, Coach ni Capitaine**. À confirmer, notamment pour le Médecin (que `club-comite-bureau.md` range visuellement dans la carte « Bureau ») et pour les simples joueurs : certains documents (convocations d'AG, PV d'AG) concernent tous les joueurs. Proposition d'évolution si le client le souhaite : un réglage « Visible par tous les joueurs » par document — **non spécifié ici** tant qu'il n'est pas décidé.
4. **Volume et règle des listes (3.3)** : sur plusieurs saisons, l'archive peut dépasser 30 documents ; le 3.3 prévoit alors « un tableau avec recherche, filtres et pagination ». L'écran suit la demande (« N derniers + Voir plus ») **en y ajoutant** recherche et filtres ; « Voir plus » tient lieu de pagination. Écart de forme à valider par le client ; si refusé, bascule sur `DataTable` (colonnes Titre figée · Catégorie · Date du document · Déposé par ; tri par défaut : date du document décroissante), sans autre changement.
5. **Modification d'un document** (titre, catégorie, date mal saisis) : non demandée, non spécifiée. Défaut : retirer puis redéposer. À confirmer.
6. **Visibilité des documents retirés** : les documents retirés restent masqués par défaut mais sont visibles et téléchargeables par le Bureau (10.3 n° 172) ; **restauration** d'un document retiré non prévue. À confirmer.
7. *(Sans objet : le code PIN est supprimé de l'application, décision du 11/10/2026.)*
8. **Notification au dépôt** : aucune (le 4.17 n'en prévoit pas). Proposition possible : notifier le Bureau au dépôt d'un PV de réunion. À décider.
9. **Lisibilité des photos de documents** : plafond de compression porté à 2 400 px (au lieu de 1 600 px pour les images du fil), pour que le texte d'un PV photographié reste lisible. Écart au 6.7 qui ne fixe pas de taille pour ce cas : à valider avec `backend-dev`. Un document photographié de plusieurs pages = un seul fichier : il faut un PDF (pas de dépôt multi-photos au MVP). À confirmer.
10. **Journalisation des consultations** : non exigée ; proposée par analogie avec les documents médicaux. À décider (impact sur le volume du journal).
11. **PV d'AG signés** : ils restent sur la page « Assemblées générales » et ne sont **pas** copiés automatiquement dans l'archive. Proposition d'évolution : les y faire apparaître en lecture seule sous une 4e catégorie « PV d'AG ». À décider.
12. **Date du document dans le futur** : question ouverte. Le CDC (10.3 n° 172) ne refuse pas de date future ; la spec initiale la refusait. À trancher par le client.
13. **Durée de conservation** : aucune purge ; conservation illimitée au MVP (cohérent avec l'esprit du 10.2 n° 35). À confirmer.

## 9. Ajouts au design system à faire (proposition pour `frontend-dev`)

**Icônes** (`frontend/src/design-system/icons.ts`, tableau §3.4 de `design-system-icones-animations.md`) :

| Nom métier | Icône Lucide | `aria-label` / libellé | Usage |
| --- | --- | --- | --- |
| `IconNavArchives` | `Archive` | — | Entrée de navigation « Archives », état vide de la liste |
| `IconDocumentPdf` | `FileText` | — | Ligne et aperçu d'un document PDF |
| `IconDocumentImage` | `FileImage` | — | Ligne et aperçu d'un document image |
| `IconWithdraw` | `ArchiveX` | « Retirer le document » | Menu « … » de la modale de détail |
| `IconOpenExternal` | `ExternalLink` | « Ouvrir » (libellé visible) | Ouvrir un PDF dans la visionneuse |

`Archive` n'est utilisée par aucune autre entrée de navigation (règle « une icône par entrée »).

**Statut** (`design-system.md` §2.5, ligne de proposition) : clé `withdrawn`, libellé « Retiré », famille **gris** (même famille que « Archivé » au 3.4). Le libellé « Archivé » n'est pas réutilisé ici : sur une page « Archives », il serait ambigu.

**Navigation** (`design-system.md` §3.9) : groupe « Club », entrée « Archives » après « Communiqués », visible par Pdt, VP, Secrétaire, DS, Trés, Adj, Int (selon les droits renvoyés par l'API).
