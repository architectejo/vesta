"""Permissions DRF de l'app treasury (matrice CDC 2.4)."""

from apps.clubs.models import MembershipRole
from apps.core.roles import HasClubRole, has_any_role
from apps.treasury import services as _services
from apps.treasury.models import Payment, SocialAssistanceRequest


class CanReadContributionTypes(HasClubRole):
    required_roles = frozenset(
        {
            MembershipRole.Role.PRESIDENT,
            MembershipRole.Role.VICE_PRESIDENT,
            MembershipRole.Role.TREASURER,
            MembershipRole.Role.ASSISTANT_TREASURER,
        }
    )
    message = "Réservé aux membres du bureau autorisés à consulter la trésorerie."


class CanWriteContributionTypes(HasClubRole):
    required_roles = frozenset({MembershipRole.Role.PRESIDENT, MembershipRole.Role.TREASURER})
    message = "Réservé au Président ou au Trésorier."


# Matrice 2.4, ligne « Enregistrement des paiements » : L pour Pdt et VP,
# É pour Trés et Adj, P (ses propres données) pour le Joueur, aucun accès
# pour les autres fonctions (DS, Int, Coach, Cap, Méd).
PAYMENT_READER_ROLES = frozenset(
    {
        MembershipRole.Role.PRESIDENT,
        MembershipRole.Role.VICE_PRESIDENT,
        MembershipRole.Role.TREASURER,
        MembershipRole.Role.ASSISTANT_TREASURER,
    }
)


class CanRecordPayments(HasClubRole):
    """Ligne « Enregistrement des paiements » de la matrice 2.4, colonne É :
    Trésorier et Trésorier adjoint. Couvre la modale « Enregistrer un
    paiement » (CDC 4.4.4) et la Caisse Terrain Express (CDC 4.4.5 : la
    session de caisse est ouverte « par le Trésorier ou l'adjoint » ; le
    Président, en lecture seule sur cette ligne, n'y a pas accès)."""

    required_roles = _services.PAYMENT_RECORDERS
    message = "Seuls le Trésorier et le Trésorier adjoint enregistrent les paiements."


class CanReadContributionGrid(HasClubRole):
    """Ligne « Grille des cotisations (tous joueurs) » de la matrice 2.4 :
    L pour Pdt et VP, É pour Trés et Adj (l'écriture passe toujours par un
    paiement), aucun accès pour DS, Int, Coach, Cap, Méd. Le VP est inclus
    selon la matrice 2.4 bien que le 4.4.7 ne le cite pas (point ouvert de
    la fiche d'écran, défaut appliqué)."""

    required_roles = _services.GRID_READERS
    message = "Réservé au Président, au Vice-président, au Trésorier et à son adjoint."


class CanImportContributions(HasClubRole):
    """Import des cotisations historiques (CDC 4.4.8) : il enregistre des
    paiements validés, donc ligne « Enregistrement des paiements » de la
    matrice 2.4, colonne É (Trésorier et Trésorier adjoint)."""

    required_roles = _services.CONTRIBUTION_IMPORTERS
    message = "Seuls le Trésorier et le Trésorier adjoint importent des cotisations."


class CanReadTreasuryDashboard(HasClubRole):
    """Tableau de bord Trésorerie (CDC 4.4.6 ; fiche §2) : Pdt, VP, Trés, Adj."""

    required_roles = _services.DASHBOARD_READERS
    message = "Réservé au Président, au Vice-président, au Trésorier et à son adjoint."


class CanRequestPaymentReversal(HasClubRole):
    """« Demander l'annulation » (fiche tresorerie-tableau-de-bord §4.4) :
    Trésorier et Trésorier adjoint uniquement au niveau de l'API. Le service
    accepte aussi le Président (``REVERSAL_REQUESTERS``) ; l'endpoint suit
    la fiche d'écran, plus restrictive (point signalé)."""

    required_roles = _services.PAYMENT_RECORDERS
    message = "Seuls le Trésorier et le Trésorier adjoint demandent l'annulation d'un paiement."


class CanDecidePaymentReversal(HasClubRole):
    required_roles = _services.REVERSAL_DECIDERS
    message = "Seul le Président valide ou refuse une annulation de paiement."


def payments_visible_to(user):
    """Paiements du club actif que ``user`` peut consulter (fichiers compris).

    Toujours via ``Payment.objects`` (tenant-aware, CLAUDE.md règle n° 8) :
    un paiement d'un autre club n'est jamais renvoyé. Hors bureau habilité,
    seuls les paiements de l'utilisateur lui-même sont visibles (colonne
    « P » de la matrice 2.4) ; un paiement non visible est traité comme
    inexistant par la vue (404, jamais de fuite d'existence).
    """

    queryset = Payment.objects.select_related("membership")
    if has_any_role(user, PAYMENT_READER_ROLES):
        return queryset
    return queryset.filter(membership__user=user)


# ---------------------------------------------------------------------------
# Depenses et assistance sociale (tache 2.2 ; matrice 2.4, CDC 4.5)
# Les ensembles de roles viennent de ``apps.treasury.services`` (source
# unique, reutilisee par les services eux-memes et par l'endpoint des
# capacites) : aucune copie de la matrice ici.
# ---------------------------------------------------------------------------

class CanReadExpenses(HasClubRole):
    required_roles = _services.EXPENSE_READERS
    message = "Réservé au Président, au Vice-président, au Trésorier et à son adjoint."


class CanManageExpenseCategories(HasClubRole):
    required_roles = _services.EXPENSE_CATEGORY_MANAGERS
    message = "Seuls le Président et le Trésorier gèrent les catégories de dépense."


class CanSubmitExpenses(HasClubRole):
    required_roles = _services.EXPENSE_RECORDERS
    message = "Seuls le Trésorier et le Trésorier adjoint saisissent les dépenses."


class CanValidateExpenses(HasClubRole):
    required_roles = _services.EXPENSE_VALIDATORS
    message = "Seuls le Président et le Vice-président valident les dépenses."


class CanDerogateExpenses(HasClubRole):
    required_roles = _services.PRESIDENT_ONLY
    message = "Seul le Président peut libérer une dépense par dérogation."


class CanUploadExpenseReceipts(HasClubRole):
    required_roles = _services.EXPENSE_RECEIPT_UPLOADERS
    message = "Seuls le Trésorier et le Trésorier adjoint téléversent les justificatifs de dépense."


class CanManageAssistanceScales(HasClubRole):
    required_roles = _services.ASSISTANCE_SCALE_MANAGERS
    message = "Seuls le Président et le Trésorier gèrent le barème d'assistance sociale."


class CanProcessAssistanceRequests(HasClubRole):
    required_roles = _services.ASSISTANCE_PROCESSORS
    message = "Seuls le Président et le Vice-président traitent les demandes d'assistance sociale."


def assistance_requests_visible_to(user):
    """Demandes d'assistance du club actif visibles par ``user``.

    Matrice 2.4 « P » : chaque joueur voit ses propres demandes. Le
    Président et le Vice-président, qui les traitent (CDC 4.5.3), voient
    celles du club. Une demande non visible est traitée comme inexistante
    (404) par les vues.
    """

    queryset = SocialAssistanceRequest.objects.select_related("membership__user")
    if has_any_role(user, _services.ASSISTANCE_PROCESSORS):
        return queryset
    return queryset.filter(membership__user=user)
