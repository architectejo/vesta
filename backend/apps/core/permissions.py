"""Classes de permission DRF communes (CLAUDE.md section 5, apps.core).

Deux garde-fous poses en ``DEFAULT_PERMISSION_CLASSES`` (tache 1.3) : ils
s'appliquent a **tout** endpoint qui ne les exclut pas explicitement
(``permission_classes`` sur la vue). C'est volontairement le mecanisme
inverse d'une liste blanche : un endpoint nouveau, cree sans y penser,
reste bloque tant que son mot de passe/ses CGU ne sont pas a jour, plutot
que de l'oublier silencieusement (CDC 4.1, 7.5, critere d'acceptation).

La matrice de permissions par role (CDC 2.4) est hors perimetre de cette
tache (1.5) : ces classes ne verifient que l'etat du compte, jamais un
role de club.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission


class HasCompletedPasswordSetup(BasePermission):
    """Refuse tant que ``User.must_change_password`` est vrai (CDC 4.1).

    « Tant qu'il ne l'a pas change, il n'accede a aucune donnee. » Les
    deux seules issues pendant cet etat sont le changement de mot de
    passe force et la deconnexion : les vues correspondantes excluent
    explicitement cette permission de leur ``permission_classes``.
    """

    message = "Vous devez changer votre mot de passe avant de continuer (CDC 4.1)."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        return not getattr(user, "must_change_password", False)


class HasAcceptedLatestTerms(BasePermission):
    """Refuse tant que la derniere version des CGU n'est pas acceptee (CDC 7.5, 10.2 n27).

    schema-donnees.md §3.6 : « Le blocage d'acces tant qu'une version plus
    recente n'est pas acceptee est un controle de service (comparable a
    ``must_change_password``) ». Point ouvert applique par defaut
    (signale au compte rendu de la tache 1.3) : un Superuser n'a pas de
    parcours « premiere connexion joueur » (CDC 7.5 parle explicitement
    de « chaque joueur ») et n'est donc pas soumis a ce blocage ici.
    """

    message = "Vous devez accepter la derniere version des CGU avant de continuer (CDC 7.5)."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True

        # Import tardif : evite tout import circulaire (apps.core est
        # charge avant apps.accounts).
        from apps.accounts.services import get_pending_terms_version

        return get_pending_terms_version(user) is None


class IsSuperuser(BasePermission):
    """Reserve aux comptes Superuser (CDC 2.5, 4.18)."""

    message = "Reserve au Superuser (CDC 2.5)."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False)
        )


class HasUsableLicence(BasePermission):
    """Bloque l'acces selon l'etat de la licence du club actif (CDC 1.4 ; 10.2 n19 ; tache 1.8).

    Distingue explicitement DEUX regimes, jamais melanges (10.2 n19) :

    - licence ``suspended`` -> **bloque tout acces, y compris en lecture**
      (« elle bloque l'acces du club », PAS une lecture seule -- a la
      difference d'une licence expiree) ;
    - ``Club.status == READ_ONLY`` (licence EXPIREE au-dela de la periode
      de grace, voir ``apps.licences.services.process_licence_expirations``)
      -> **autorise la lecture** (``GET``/``HEAD``/``OPTIONS``), **refuse
      toute methode de mutation** (``POST``/``PUT``/``PATCH``/``DELETE``)
      -- « les donnees sont conservees et restent exportables » (CDC 1.4).

    Un Superuser n'appartient structurellement a aucun club (CLAUDE.md
    regle n1) : **jamais concerne par ce controle**, y compris pendant une
    session de support en Ghost Mode (CDC 2.5 : « le Superuser a acces a
    tout » -- le controle d'acces lie a la licence ne s'applique qu'aux
    joueurs d'un club, jamais au Superuser lui-meme, quel que soit le club
    sur lequel porte son intervention).

    Traitement de ``terminated`` (decision par defaut APPLIQUEE ICI, non
    explicitement tranchee par le CDC/10.2 n19, qui ne detaille QUE
    ``suspended`` vs ``expired`` + periode de grace) : traite exactement
    comme ``suspended`` (bloque tout), jamais moins restrictif qu'une
    simple suspension -- voir la meme note dans
    ``apps.licences.services.terminate_licence``. Point ouvert a confirmer
    par le client (voir compte rendu de la tache 1.8).

    Si aucune ``Licence`` n'existe pour le club actif (cas theorique, ne
    devrait pas se produire en usage normal -- CDC 2.3 : une licence est
    creee au meme moment qu'un club), cette classe n'ajoute aucun blocage
    supplementaire : ce n'est pas a ce garde-fou de compenser une donnee
    manquante.
    """

    message_blocked = "Cette licence est suspendue ou resiliee : l'acces a ce club est bloque (CDC 1.4, 10.2 n19)."
    message_read_only = "Ce club est en lecture seule (licence expiree au-dela de la periode de grace, CDC 1.4)."

    SAFE_METHODS = ("GET", "HEAD", "OPTIONS")

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True

        # Imports tardifs : evitent tout import circulaire au chargement
        # des apps (apps.core est charge avant apps.clubs/apps.licences).
        from apps.core.tenant import get_active_club
        from apps.licences.models import Licence

        club = get_active_club()
        if club is None:
            # Aucun club actif : hors du perimetre de ce garde-fou -- une
            # autre couche (les managers tenant-aware, CLAUDE.md regle n8)
            # refuse deja l'acces aux donnees privees sans club actif.
            return True

        licence = Licence.objects.filter(club=club).order_by("-created_at").first()
        if licence is not None and licence.status in (
            Licence.Status.SUSPENDED,
            Licence.Status.TERMINATED,
        ):
            self.message = self.message_blocked
            return False

        if club.status == club.Status.READ_ONLY and request.method not in self.SAFE_METHODS:
            self.message = self.message_read_only
            return False

        return True
