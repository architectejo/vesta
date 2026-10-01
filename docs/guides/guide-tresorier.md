# Guide utilisateur — Trésorier (et Trésorier adjoint)

> Ce guide décrit les écrans réels de Vesta tels qu'implémentés à ce jour (vérifié dans le code et les specs `docs/ecrans/`). Aucune capture d'écran : les étapes sont décrites en clair. Le Trésorier adjoint a les mêmes écrans que le Trésorier, sauf mention contraire.

Le menu « Trésorerie » n'apparaît dans la barre latérale que pour le Président, le Vice-président, le Trésorier et le Trésorier adjoint.

## Tableau de bord (Trésorerie → Tableau de bord)

Vue d'ensemble : soldes, dettes en cours, dernières écritures. Le solde d'un joueur n'est jamais stocké : toujours recalculé (paiements validés moins montants dus échus).

## Grille des cotisations (Trésorerie → Grille des cotisations)

- Un tableau : une ligne par joueur, une colonne par mois, pour un type de cotisation et une année donnés.
- Cliquer sur une cellule ouvre le détail du mois pour ce joueur (payé, dû, en retard).
- **Enregistrer un paiement** : recherche du joueur (jamais une liste déroulante), montant, répartition automatique sur les échéances les plus anciennes d'abord.
- **Caisse Terrain Express** : encaissement rapide en espèces pendant une séance ou un match, pour plusieurs joueurs à la suite, sans revenir à l'accueil entre chacun.
- **Importer (CSV)** : importer un historique de cotisations depuis un fichier (une ligne par joueur, une colonne par mois). Trois étapes : choisir le fichier, vérifier l'aperçu (lignes acceptées / en échec), confirmer avec votre code PIN. Un rapport est proposé au téléchargement après l'import.
- **Exporter (CSV)** : la même grille, en fichier.

## Dépenses (Trésorerie → Dépenses)

- Le Trésorier (et son adjoint) **saisit** une dépense avec un justificatif ; seuls le Président et le Vice-président la **valident**, avec leur PIN.
- Catégories de dépenses configurables par le Président/Trésorier.
- Une dépense validée n'est jamais supprimée : seule une écriture d'annulation existe.

## Assistance sociale

Le Trésorier suit ses propres demandes depuis « Mon profil » ; le traitement des demandes des autres joueurs revient au Président et au Vice-président (menu séparé, « Assistance sociale »), pas au Trésorier.

## Parcours type pour la présentation

1. Ouvrez la Grille des cotisations, montrez une cellule payée et une en retard.
2. Enregistrez un paiement pour un joueur via la recherche de joueur.
3. Montrez la Caisse Terrain Express (plusieurs encaissements à la suite).
4. Saisissez une dépense avec un justificatif.
5. Si le Président est disponible, faites-la valider avec son PIN.

## Point ouvert

Le format exact attendu du fichier CSV d'import des cotisations n'est pas encore documenté dans une annexe formelle (`docs/annexes/formats-csv.md` §4) — l'écran affiche une aide dérivée du code en attendant cette annexe.
