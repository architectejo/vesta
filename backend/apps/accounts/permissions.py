"""Classes de permission DRF de l'app accounts.

La matrice complete de permissions par role (CDC 2.4) est hors perimetre
de cette tache (1.5). ``apps.core.permissions`` fournit les garde-fous
generiques reutilises ici (``IsSuperuser``, ``HasCompletedPasswordSetup``,
``HasAcceptedLatestTerms``) : rien de specifique a ajouter pour l'instant
dans ce module.
"""
