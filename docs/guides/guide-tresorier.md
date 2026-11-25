# Guide utilisateur — Trésorier (et Trésorier adjoint)

> Ce guide décrit les écrans réels de Vesta tels qu'implémentés à ce jour (vérifié dans le code et les specs `docs/ecrans/`). Aucune capture d'écran : les étapes sont décrites en clair. Le Trésorier adjoint a les mêmes écrans que le Trésorier, sauf mention contraire.

Le menu « Trésorerie » n'apparaît dans la barre latérale que pour le Président, le Vice-président, le Trésorier et le Trésorier adjoint.

## Tableau de bord (Trésorerie → Tableau de bord)

Vue d'ensemble : soldes, dettes en cours, dernières écritures. Le solde d'un joueur n'est jamais stocké : toujours recalculé (paiements validés moins montants dus échus).

## Grille des cotisations (Trésorerie → Grille des cotisations)

- Un tableau : une ligne par joueur, une colonne par mois, pour un type de cotisation et une année donnés.
- Cliquer sur une cellule ouvre le détail du mois pour ce joueur (payé, dû, en retard).
- **Enregistrer un paiement** : recherche du joueur (jamais une liste déroulante), montant, répartition automatique sur les échéances les plus anciennes d'abord. Si vous confirmez deux fois par erreur (double clic, réseau lent), un seul paiement est enregistré, avec un seul reçu. Si l'application affiche « Cet identifiant de saisie a déjà été utilisé pour un autre paiement : il n'a pas été enregistré une seconde fois. », le paiement n'a pas été doublé : vérifiez dans « Derniers paiements » et recommencez la saisie depuis le début si besoin.
- **Caisse Terrain Express** : encaissement rapide en espèces pendant une séance ou un match, pour plusieurs joueurs à la suite, sans revenir à l'accueil entre chacun.
- **Importer (CSV)** : importer un historique de cotisations depuis un fichier (une ligne par joueur, une colonne par mois). Trois étapes : choisir le fichier, vérifier l'aperçu (lignes acceptées / en échec), confirmer dans la fenêtre de confirmation. Un rapport est proposé au téléchargement après l'import. **Attention : une case vide du fichier = un mois dû non payé, donc une dette réelle** (décidé le 17/11/2026). Vérifiez la grille de l'aperçu avant de confirmer l'import définitif.
- **Exporter (CSV)** : la même grille, en fichier.

## Frais d'adhésion d'un nouveau joueur

Décidé le 17/11/2026 : les frais d'adhésion sont **une somme à payer**, comme une cotisation.

- Quand le Président (ou le recruteur) ajoute un nouveau joueur, Vesta crée automatiquement un montant dû unique pour ses frais d'adhésion (le tarif « adhésion » du club à sa date d'entrée, par exemple 5 $), exigible dès sa date d'entrée. Si le club n'a pas encore de type de cotisation « adhésion », aucun montant n'est créé et l'enregistrement des frais est refusé avec un message clair : créez d'abord ce type.
- Tant qu'il n'a pas réglé ses frais, le joueur apparaît « En attente » (jamais « En dette ») et son solde affiche le montant à régler (par exemple −5 $).
- Quand vous enregistrez ses frais, le paiement couvre ce montant dû : son solde revient à 0 $ et ses mensualités ne sont pas touchées. Un paiement partiel (3 $ puis 2 $) est accepté ; un paiement supérieur (8 $) laisse un crédit de 3 $.
- Si l'adhésion est annulée après un refus du parrain, le montant dû est neutralisé par une écriture d'annulation (rien n'est supprimé) ; si les frais sont remboursés, le joueur ne doit plus rien.
- Les joueurs importés (membres historiques) n'ont pas de frais d'adhésion à payer.

## Dépenses (Trésorerie → Dépenses)

- Le Trésorier (et son adjoint) **saisit** une dépense avec un justificatif ; seuls le Président et le Vice-président la **valident**, après une confirmation explicite dans l'application.
- Catégories de dépenses configurables par le Président/Trésorier.
- Une dépense validée n'est jamais supprimée : seule une écriture d'annulation existe.

## Assistance sociale

Le Trésorier suit ses propres demandes depuis « Mon profil » ; le traitement des demandes des autres joueurs revient au Président et au Vice-président (menu séparé, « Assistance sociale »), pas au Trésorier.

## Parcours type pour la présentation

1. Ouvrez la Grille des cotisations, montrez une cellule payée et une en retard.
2. Enregistrez un paiement pour un joueur via la recherche de joueur.
3. Montrez la Caisse Terrain Express (plusieurs encaissements à la suite).
4. Saisissez une dépense avec un justificatif.
5. Si le Président est disponible, faites-la valider par lui dans l'application.

## Point ouvert

Le format exact attendu du fichier CSV d'import des cotisations n'est pas encore documenté dans une annexe formelle (`docs/annexes/formats-csv.md` §4) — l'écran affiche une aide dérivée du code en attendant cette annexe.
