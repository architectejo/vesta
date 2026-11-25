"""Classes de permission DRF de l'app clubs (CDC 2.2-2.4 ; tache 1.5).

Chaque classe correspond a une colonne precise de la matrice 2.4 pour les
endpoints de nomination/revocation de roles, changement de Capitaine,
passation de presidence et parametres du bureau. S'appuie sur le
mecanisme generique d'``apps.core.roles`` (cumul de roles, CDC 2.2),
reutilisable par les futures apps metier (treasury, sport, medical...),
qui declareront leurs propres classes par-dessus ce meme mecanisme
(CLAUDE.md section 7).

``apps.core.permissions.IsSuperuser`` (deja pose tache 1.3) reste la
classe utilisee pour l'intervention Superuser (passation de presidence
forcee) : aucune duplication ici.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.clubs.models import COACHING_STAFF_ROLES, MembershipRole
from apps.core.roles import HasClubRole, has_any_role, is_ghost_read_access
from apps.core.services import resolve_active_membership
from apps.core.tenant import NoActiveClubError


class IsActiveClubMember(BasePermission):
    """Lecture ouverte a tout membre actif du club (matrice 2.4, colonnes
    « L » -- de Pdt a Joueur -- sur la nomination du bureau/Medecin, le
    Coach, le Capitaine et les parametres de titulaires par role)."""

    message = "Une adhésion active dans un club est requise pour consulter cette ressource."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        if is_ghost_read_access(request):
            return True
        try:
            resolve_active_membership(user)
        except NoActiveClubError:
            return False
        return True


class IsClubPresident(BasePermission):
    """Reserve au President du club actif (matrice 2.4 : « É » sur la
    nomination du bureau/Medecin, l'ajout/retrait du Coach, la
    designation des recruteurs et les parametres de titulaires par role ;
    CDC 2.3)."""

    message = "Réservé au Président du club."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        return has_any_role(user, {MembershipRole.Role.PRESIDENT})


class CanAddOrImportPlayers(BasePermission):
    """Reserve au President ou a un joueur recruteur designe du club actif
    (matrice 2.4 : « Ajout et import de joueurs » -- « É » pour le
    President, « D » pour un joueur designe ; CDC 4.1, 2.3). Le role
    ``MembershipRole.Role.PLAYER_RECRUITER`` est exactement ce mecanisme de
    designation (« joueur autorise a ajouter des joueurs », nomme par le
    President -- voir ``apps.clubs.services.appoint_president_nominated_role``)."""

    message = "Réservé au Président ou à un joueur autorisé à ajouter des joueurs."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        return has_any_role(
            user, {MembershipRole.Role.PRESIDENT, MembershipRole.Role.PLAYER_RECRUITER}
        )


class CanRecordMembershipFeePayment(BasePermission):
    """Reserve au Tresorier ou au Tresorier adjoint (matrice 2.4 :
    « Enregistrement des paiements » -- « É » Tres/Adj uniquement, y
    compris le President qui n'a que « L » sur cette ligne ; CDC 4.3
    etape 2, 4.4.4). Confirme par `finance-engine` (revue independante,
    tache 1.4b) contre une consigne initiale erronee qui incluait le
    President."""

    message = "Réservé au Trésorier ou au Trésorier adjoint."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        return has_any_role(
            user, {MembershipRole.Role.TREASURER, MembershipRole.Role.ASSISTANT_TREASURER}
        )


def can_access_membership_application_file(*, user, application) -> bool:
    """Qui peut telecharger la fiche d'adhesion PDF d'un dossier (CDC 6.7,
    7.6 ; ecart bloquant B10, revue de conformite fin de Lot 1) : le
    President du club, l'adherent concerne lui-meme, et le parrain du
    dossier -- EXACTEMENT les trois identites deja reconnues par ce
    dossier pour signer/refuser (voir
    ``apps.clubs.services.sign_sponsor_application``/
    ``refuse_sponsor_application``, qui verifient deja « le parrain de ce
    dossier precis »). Aucune nouvelle matrice de permission inventee ici.

    Utilisee par la vue apres avoir recupere l'objet via le manager
    tenant-aware (``MembershipApplication.objects``, deja scope au club
    actif) : une valeur ``False`` renvoyee ici pour un dossier D'UN AUTRE
    CLUB ne se produit jamais en pratique (``DoesNotExist`` avant meme
    d'atteindre cette fonction, CLAUDE.md regle n8) -- la vue distingue
    donc « dossier introuvable dans ce club » (404) de « dossier existant,
    mais cet utilisateur n'y a pas droit » (403)."""

    if has_any_role(user, {MembershipRole.Role.PRESIDENT}):
        return True
    membership = application.membership
    user_id = getattr(user, "id", None)
    if membership.user_id == user_id:
        return True
    sponsor = membership.sponsor
    return sponsor is not None and sponsor.user_id == user_id


class IsClubCoach(BasePermission):
    """Reserve au staff technique du club actif : le Coach ET l'Assistant du
    Coach (memes droits, CDC 10.3 n179). Matrice 2.4 : « É » sur le choix du
    Capitaine ; CDC 2.3."""

    message = "Réservé au Coach du club ou à son assistant."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        return has_any_role(user, COACHING_STAFF_ROLES)


class IsClubHeadCoach(BasePermission):
    """Reserve au Coach lui-meme, jamais a son assistant : nommer ou retirer
    l'Assistant du Coach (CDC 10.3 n179, decision b)."""

    message = "Seul le Coach du club peut nommer ou retirer un assistant."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        return has_any_role(user, {MembershipRole.Role.COACH})


class IsPresidentOrVicePresident(HasClubRole):
    """Reserve au President et au Vice-president du club actif (matrice 2.4 :
    lecture des paiements, de la grille, des depenses, du materiel, evaluations ;
    sante : aptitude seulement). Roles cumulables (union, CDC 2.2) : un joueur
    qui porte aussi un autre role garde l'acces ; un Vice-president revoque, ou
    un poste vacant, n'ouvre rien (seuls les roles ACTIFS comptent). Le
    Superuser en session de support (Ghost Mode) lit comme le President
    (fiche tableau-de-bord-bureau §2) ; hors session, il n'a aucun acces."""

    required_roles = frozenset({MembershipRole.Role.PRESIDENT, MembershipRole.Role.VICE_PRESIDENT})
    message = "Cette page est réservée au Président et au Vice-président."
