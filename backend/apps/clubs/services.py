"""Regles metier de l'app clubs.

Tache 1.6 : journalisation (CLAUDE.md regle n6 ; CDC 5.2 « Club et
roles » -- « modification du club, nomination, revocation, ajout et
depart de joueur, import »). Ces fonctions calculent le contenu
``before``/``after`` a journaliser et appellent
``apps.core.services.log_action`` ; les signaux de
``apps.clubs.signals`` se contentent de detecter l'evenement (creation,
transition d'etat) et de leur deleguer le travail (CLAUDE.md section 5 :
la regle metier ne vit jamais dans un signal brut).
"""

from __future__ import annotations

import csv
import io
import logging
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, NamedTuple, Optional

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from apps.accounts import services as accounts_services
from apps.clubs.models import (
    COACHING_STAFF_ROLES,
    ClubSettings,
    ImportBatch,
    Membership,
    MembershipApplication,
    MembershipRole,
    PresidencyTransfer,
)
from apps.core.roles import has_any_role
from apps.core.services import log_action

logger = logging.getLogger(__name__)

# Import tardif (dans chaque fonction, pas ici) pour `apps.treasury.services` :
# ce module importe deja `apps.clubs.models` au niveau module -- l'importer
# ICI au niveau module creerait un aller-retour clubs<->treasury au chargement
# des apps. Sans risque reel documente (treasury n'importe jamais
# `apps.clubs.services`), mais le meme prudence que le reste de ce fichier
# pour les autres apps (voir `apps.accounts.services`, qui utilise
# `apps.get_model` plutot qu'un import direct de `apps.clubs.models`).


def role_snapshot(role) -> dict[str, Any]:
    return {
        "membership_id": role.membership_id,
        "role": role.role,
        "appointed_by_id": role.appointed_by_id,
        "appointed_at": role.appointed_at,
        "revoked_by_id": role.revoked_by_id,
        "revoked_at": role.revoked_at,
        "revoked_reason": role.revoked_reason,
    }


def log_membership_role_appointed(role) -> None:
    """Journalise la nomination d'un role (CDC 5.2 « nomination »)."""

    log_action(
        actor=role.appointed_by,
        club=role.club,
        action_type="role.appointed",
        obj=role,
        before=None,
        after=role_snapshot(role),
    )


def log_membership_role_revoked(role, before_snapshot: dict[str, Any]) -> None:
    """Journalise la revocation d'un role (CDC 5.2 « revocation »)."""

    log_action(
        actor=role.revoked_by or role.appointed_by,
        club=role.club,
        action_type="role.revoked",
        obj=role,
        before=before_snapshot,
        after=role_snapshot(role),
    )


def membership_snapshot(membership) -> dict[str, Any]:
    return {
        "user_id": membership.user_id,
        "status": membership.status,
        "sponsor_id": membership.sponsor_id,
        "position": membership.position,
        "position_detail": membership.position_detail,
        "jersey_number": membership.jersey_number,
        "requested_contribution_type_label": membership.requested_contribution_type_label,
        "joined_on": membership.joined_on,
        "left_on": membership.left_on,
        "left_reason": membership.left_reason,
    }


def log_membership_created(membership) -> None:
    """Journalise l'ajout d'un joueur (CDC 5.2 « ajout [...] de joueur »)."""

    log_action(
        actor=membership.added_by,
        club=membership.club,
        action_type="membership.created",
        obj=membership,
        before=None,
        after=membership_snapshot(membership),
    )


def log_membership_departed(membership, before_snapshot: dict[str, Any], *, actor) -> None:
    """Journalise le depart d'un joueur (CDC 5.2 « [...] depart de joueur »).

    ``actor`` doit etre l'acteur reel ayant traite le depart
    (``Membership.left_by``). Correction d'un bug remonte par
    test-engineer pendant le Lot 1 : le journal attribuait auparavant ce
    depart a ``membership.added_by`` (le recruteur d'origine), quel que
    soit qui traitait reellement le depart -- une fausse attribution
    positive contraire a CDC 5.1 (« Acteur : identifiant reel de
    l'utilisateur a l'origine de l'action »). Aucune valeur par defaut
    silencieuse n'est appliquee ici : un appelant qui ne fournit pas
    d'acteur explicite (``Membership.left_by`` non renseigne avant la
    transition) est une erreur de programmation, jamais compensee par un
    repli sur ``added_by``.
    """

    if actor is None:
        raise ValueError(
            "Le passage d'une adhesion en depart (DEPARTED) exige un "
            "acteur reel explicite : renseignez `Membership.left_by` "
            "avant d'enregistrer cette transition (CDC 5.1). Aucun repli "
            "silencieux sur `added_by` n'est applique."
        )

    log_action(
        actor=actor,
        club=membership.club,
        action_type="membership.departed",
        obj=membership,
        before=before_snapshot,
        after=membership_snapshot(membership),
    )


def log_membership_updated(membership, before_snapshot: dict[str, Any], *, actor) -> None:
    """Journalise la mise a jour d'une fiche joueur existante (tache 1.4 ;
    CDC 5.2 « import » ; CLAUDE.md regle n6 : toute modification s'ecrit au
    journal).

    Distincte de :func:`log_membership_departed` (qui ne couvre que la
    transition vers DEPARTED, deja journalisee automatiquement par le
    signal ``post_save`` de ``apps.clubs.signals``, tache 1.6) : ce cas --
    une mise a jour de fiche par email deja present dans le club (import
    CSV, CDC 4.1), qui ne change pas le statut -- n'avait jusqu'ici aucune
    fonction de journalisation dediee, ni de signal generique (un signal
    generique sur *tout* changement de ``Membership`` risquerait de
    dupliquer ou de mal attribuer l'acteur reel pour des transitions deja
    traitees specifiquement ailleurs, comme le depart). Appelee
    explicitement par :func:`create_or_update_player` : l'acteur reel
    (President ou joueur recruteur qui importe/met a jour la fiche) n'est
    pas deductible de ``Membership`` seul -- pas de champ generique
    « modifie par » sur ce modele, a la difference de ``added_by``/
    ``left_by``.
    """

    log_action(
        actor=actor,
        club=membership.club,
        action_type="membership.updated",
        obj=membership,
        before=before_snapshot,
        after=membership_snapshot(membership),
    )


def log_platform_user_updated(
    user, before_snapshot: dict[str, Any], after_snapshot: dict[str, Any], *, actor, club
) -> None:
    """Journalise la mise a jour des champs personnels usuels (telephone,
    date de naissance, poids, taille) d'un compte `User` **deja existant**,
    declenchee par l'ajout ou l'import d'un joueur dans ``club``
    (CLAUDE.md regle n6 ; CDC 5.2 « import », 4.1 -- audit tache 1.14, ecart
    bloquant B4).

    ``apps.accounts.services.get_or_create_platform_user`` est
    volontairement club-agnostique (reutilisee par ``apps.clubs.
    club_creation``, hors contexte de club) : elle ne journalise jamais
    elle-meme, seulement ``before``/``after`` en retour
    (``PlatformUserResult``). C'est donc a l'appelant qui a le contexte
    club/acteur -- ici :func:`create_or_update_player` -- d'ecrire
    l'entree, exactement comme :func:`log_membership_updated` le fait deja
    pour ``Membership``.

    ``club`` est le club qui a declenche la modification (celui qui
    importe/ajoute la fiche), pas necessairement un club auquel ``user``
    appartient deja au sens strict (cas 2 de :func:`create_or_update_player` :
    compte deja connu de la plateforme, dans un AUTRE club) -- coherent avec
    le reste de ce module, qui journalise toujours sur le club de l'action
    en cours, jamais sur un club deduit de l'objet modifie.

    N'est appelee que lorsqu'au moins un champ a reellement change
    (``before_snapshot``/``after_snapshot`` non ``None``, verifie par
    l'appelant) : jamais d'entree pour une mise a jour « no-op ».
    """

    log_action(
        actor=actor,
        club=club,
        action_type="accounts.user.updated_via_import",
        obj=user,
        before=before_snapshot,
        after=after_snapshot,
    )


def _import_batch_snapshot(batch) -> dict[str, Any]:
    return {
        "import_type": batch.import_type,
        "imported_by_id": batch.imported_by_id,
        "imported_at": batch.imported_at,
        "row_count_success": batch.row_count_success,
        "row_count_failed": batch.row_count_failed,
    }


def log_import_batch_created(batch) -> None:
    """Journalise un lot d'import (CDC 5.2 « import »)."""

    log_action(
        actor=batch.imported_by,
        club=batch.club,
        action_type="clubs.import.created",
        obj=batch,
        before=None,
        after=_import_batch_snapshot(batch),
    )


def _presidency_transfer_snapshot(transfer) -> dict[str, Any]:
    return {
        "from_membership_id": transfer.from_membership_id,
        "to_membership_id": transfer.to_membership_id,
        "method": transfer.method,
        "superuser_id": transfer.superuser_id,
        "transferred_at": transfer.transferred_at,
    }


def log_presidency_transfer_created(transfer) -> None:
    """Journalise une passation de presidence (CDC 5.2 « modification du club »).

    Acteur : le Superuser en cas d'intervention (Ghost Mode -- ``acted_as_ghost``,
    CDC 5.4), sinon le titulaire sortant (qui initie la passation directe).
    """

    is_superuser_override = transfer.method == transfer.Method.SUPERUSER_OVERRIDE
    actor = transfer.superuser if is_superuser_override else transfer.from_membership.user

    log_action(
        actor=actor,
        club=transfer.club,
        action_type="clubs.presidency_transfer.completed",
        obj=transfer,
        before=None,
        after=_presidency_transfer_snapshot(transfer),
        acted_as_ghost=is_superuser_override,
    )


# ---------------------------------------------------------------------------
# Nomination et revocation des roles (tache 1.5 ; CDC 2.2-2.4, 10.2 n17/n24)
# ---------------------------------------------------------------------------
#
# Journalisation : deja assuree automatiquement par les signaux de
# ``apps.clubs.signals`` (``_log_membership_role``, ``_log_presidency_transfer``,
# tache 1.6) a chaque ``save()`` de ``MembershipRole``/``PresidencyTransfer`` --
# les fonctions ci-dessous n'appellent donc jamais ``log_action`` elles-memes
# pour ces deux modeles (ce serait dupliquer l'entree). Seule
# :func:`update_board_seats_per_role` journalise explicitement : elle modifie
# ``ClubSettings``, qui n'a pas de signal de journalisation dedie a ce jour.
#
# CDC 2.3 « Toute nomination ou revocation genere un log et une
# notification au joueur concerne ». Le log est deja assure (ci-dessus).
# La notification (tache 1.7) est cablee dans :func:`notify_role_change`,
# point d'accroche unique appele par les fonctions ci-dessous -- voir son
# corps pour le detail (``apps.notifications.services.create_notification``).


class RoleManagementError(Exception):
    """Erreur metier de nomination/revocation de role (message en francais,
    CDC 2.3-2.4). Distincte d'une simple ``ValidationError`` de modele : ces
    fonctions l'utilisent pour toute regle qui n'est pas une simple
    coherence de champs (ex. « ce role ne se nomme pas par cette fonction »).
    """


# Roles nommes par le President parmi les joueurs du club (CDC 2.3 : « Le
# President nomme les membres du bureau et le Medecin [...] Il ajoute ou
# retire le Coach [...] designe les joueurs autorises a ajouter de nouveaux
# joueurs »). Le President lui-meme n'y figure jamais (passation dediee,
# voir ``transfer_presidency_by_handover``/``transfer_presidency_by_superuser``) ;
# le Capitaine non plus (nomme par le Coach, voir ``appoint_captain``).
PRESIDENT_NOMINATED_ROLES = frozenset(
    {
        MembershipRole.Role.VICE_PRESIDENT,
        MembershipRole.Role.SPORTS_DIRECTOR,
        MembershipRole.Role.TREASURER,
        MembershipRole.Role.ASSISTANT_TREASURER,
        MembershipRole.Role.STEWARD,
        MembershipRole.Role.SECRETARY,
        MembershipRole.Role.DOCTOR,
        MembershipRole.Role.COACH,
        MembershipRole.Role.PLAYER_RECRUITER,
    }
)


def notify_role_change(*, role_instance: "MembershipRole", event: str) -> None:
    """Notification au joueur concerne par une nomination/revocation (CDC
    2.3 : « Toute nomination ou revocation genere un log et une
    notification au joueur concerne »). Le journal, lui, est deja ecrit
    ailleurs (signaux de ``apps.clubs.signals``, tache 1.6) : cette
    fonction ne couvre que la partie « notification » de la regle du CDC
    2.3, pas le journal.

    Cablee tache 1.7 sur ``apps.notifications.services.create_notification``
    (in-app seulement, CDC 4.17 : « Nomination ou revocation -- Joueur
    concerne -- In-app »). Textes valides Annexe E §4/§8 (tache 1.12) :
    ``{role}`` vient du libelle **effectif** du role
    (:func:`get_effective_role_label`, CDC 10.2 n17 -- distingue le
    Medecin non qualifie professionnellement), jamais du libelle brut de
    ``MembershipRole.Role`` -- c'est pourquoi cette fonction recoit
    desormais l'instance ``MembershipRole`` elle-meme (et non plus son
    seul code), pour pouvoir consulter
    ``role_instance.is_qualified_professional``.

    Parametres : ``role_instance`` (l'instance ``MembershipRole``
    concernee, y compris deja revoquee pour l'evenement ``"revoked"``),
    ``event`` (``"appointed"`` ou ``"revoked"``).
    """

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    membership = role_instance.membership
    role_label = get_effective_role_label(role_instance)
    if event == "appointed":
        title = "Nouveau rôle"
        message = f"Vous avez désormais le rôle « {role_label} » au sein de {membership.club.name}."
    else:
        title = "Fin de rôle"
        message = f"Vous n'avez plus le rôle « {role_label} » au sein de {membership.club.name}."

    create_notification(
        recipient=membership.user,
        event_type=Notification.EventType.ROLE_APPOINTED_OR_REVOKED,
        title=title,
        message=message,
        target=membership,
    )


def get_effective_role_label(role: "MembershipRole") -> str:
    """Libelle a afficher pour ce role (CDC 10.2 n17).

    Seul le role Medecin peut porter un libelle different de son libelle
    standard : « Médecin / référent santé » si le titulaire n'est pas
    qualifie professionnellement (``is_qualified_professional`` faux).
    Les autres roles gardent toujours leur libelle standard
    (``MembershipRole.Role.choices``) -- ce libelle special n'est **jamais**
    fabrique pour un role autre que Medecin.
    """

    if role.role == MembershipRole.Role.DOCTOR and role.is_qualified_professional is False:
        return "Médecin / référent santé"
    return MembershipRole.Role(role.role).label


# Roles autorises a voir qu'une adhesion est « En attente » (parrainage en
# cours) sur la fiche/liste des joueurs (CDC 10.2 n16, matrice 2.4, 4.2 ;
# CDC 4.12 : « un joueur [...] en attente d'adhesion leur apparait
# simplement « Indisponible », sans distinction » pour tout autre
# coequipier). Le joueur concerne lui-meme voit toujours son propre statut
# (voir :func:`can_view_pending_membership_status`).
PENDING_STATUS_VISIBLE_ROLES = frozenset(
    {
        MembershipRole.Role.PRESIDENT,
        MembershipRole.Role.VICE_PRESIDENT,
        MembershipRole.Role.SPORTS_DIRECTOR,
        *COACHING_STAFF_ROLES,
        MembershipRole.Role.DOCTOR,
    }
)

#: Statut neutre renvoye a la place de « En attente » a un coequipier non
#: autorise (CDC 10.2 n16). Code technique volontairement absent de
#: ``Membership.Status`` (champ de sortie de serializer uniquement, jamais
#: stocke ni relu) : signale sans ambiguite au client que ce champ est
#: masque, plutot que de renvoyer un des trois statuts reels et donc faux.
PLAYER_CARD_NEUTRAL_STATUS_CODE = "unavailable"
PLAYER_CARD_NEUTRAL_STATUS_LABEL = "Indisponible"


def can_view_pending_membership_status(*, viewer_user, target_membership: "Membership") -> bool:
    """CDC 10.2 n16 (matrice 2.4, 4.2 ; precise en 4.12) : seuls le
    President, le Vice-president, le Directeur sportif, le Coach, le
    Medecin et le joueur concerne lui-meme voient qu'une adhesion est « En
    attente » (parrainage en cours) ; tout autre coequipier ne doit
    recevoir qu'un statut neutre pour cette adhesion.

    Point d'entree unique pour cette decision (CLAUDE.md section 5 : la
    regle metier ne vit jamais dans le serializer) -- seul appelant a ce
    jour : ``apps.clubs.serializers.PlayerPublicCardSerializer``.
    """

    if getattr(viewer_user, "id", None) == target_membership.user_id:
        return True
    return has_any_role(viewer_user, PENDING_STATUS_VISIBLE_ROLES, club=target_membership.club)


def appoint_president_nominated_role(
    *,
    president_user,
    target_membership: "Membership",
    role: str,
    is_qualified_professional: Optional[bool] = None,
    now=None,
) -> "MembershipRole":
    """Nomme un membre du bureau, le Medecin, le Coach ou un recruteur
    (CDC 2.3). Reserve au President du club de ``target_membership``.

    Controle de role verifie ici en defense en profondeur (le controle
    principal reste la classe de permission
    ``apps.clubs.permissions.IsClubPresident`` sur la vue, CDC 2.4 --
    meme principe que ``apps.accounts.services.reset_password_by_superuser``,
    qui revalide ``is_superuser`` malgre ``IsSuperuser`` sur sa vue).
    """

    if role not in PRESIDENT_NOMINATED_ROLES:
        raise RoleManagementError(
            "Ce rôle ne se nomme pas ici : le Président nomme le bureau, le "
            "Médecin, le Coach et les recruteurs. Le Capitaine est choisi par "
            "le Coach, et la présidence se transmet par une passation."
        )

    if not has_any_role(president_user, {MembershipRole.Role.PRESIDENT}, club=target_membership.club):
        raise PermissionError("Seul le Président du club peut nommer ce rôle.")

    if target_membership.status != Membership.Status.ACTIVE:
        raise RoleManagementError(
            "Ce joueur n'est plus inscrit au club : la nomination n'est pas possible."
        )

    if role == MembershipRole.Role.DOCTOR and is_qualified_professional is None:
        raise RoleManagementError(
            "La nomination au rôle de Médecin exige de préciser si le joueur est "
            "qualifié professionnellement, pour afficher le bon libellé "
            "(« Médecin » ou « Médecin / référent santé »)."
        )
    if role != MembershipRole.Role.DOCTOR and is_qualified_professional is not None:
        raise RoleManagementError(
            "Le choix de qualification professionnelle ne s'applique qu'au "
            "rôle de Médecin."
        )

    now = now or timezone.now()
    new_role = MembershipRole(
        club=target_membership.club,
        membership=target_membership,
        role=role,
        is_qualified_professional=(
            is_qualified_professional if role == MembershipRole.Role.DOCTOR else None
        ),
        appointed_by=president_user,
        appointed_at=now,
    )
    new_role.save()  # full_clean() (cardinalite, coherence) + journal (signal, tache 1.6)

    notify_role_change(role_instance=new_role, event="appointed")

    return new_role


def revoke_president_nominated_role(
    *, president_user, role: "MembershipRole", reason: str = "", now=None
) -> "MembershipRole":
    """Revoque un role nomme par le President (CDC 2.3). Symmetrique de
    :func:`appoint_president_nominated_role`."""

    if role.role not in PRESIDENT_NOMINATED_ROLES:
        raise RoleManagementError(
            "Ce rôle ne se révoque pas ici : le Capitaine est retiré par le "
            "Coach, l'Assistant du Coach est retiré par le Coach, et la "
            "présidence se transmet par une passation."
        )
    if role.revoked_at is not None:
        raise RoleManagementError("Ce rôle est déjà révoqué.")
    if not has_any_role(president_user, {MembershipRole.Role.PRESIDENT}, club=role.club):
        raise PermissionError("Seul le Président du club peut révoquer ce rôle.")

    now = now or timezone.now()
    role.revoked_by = president_user
    role.revoked_at = now
    role.revoked_reason = reason
    role.save()  # journal (signal, tache 1.6)

    notify_role_change(role_instance=role, event="revoked")

    return role


def appoint_captain(*, coach_user, target_membership: "Membership", now=None) -> "MembershipRole":
    """Choisit le Capitaine parmi les joueurs (CDC 2.3). Reserve au Coach.

    Ne revoque pas automatiquement un Capitaine existant : si le nombre
    de titulaires actifs du role est deja atteint (``ClubSettings.
    board_seats_per_role``, 1 par defaut), la nomination echoue avec un
    message clair (``MembershipRole.clean()``) -- « changer » le
    Capitaine s'effectue alors en revoquant l'ancien
    (:func:`revoke_captain`) avant d'en nommer un nouveau, exactement
    comme pour tout autre role plafonne.
    """

    if not has_any_role(coach_user, COACHING_STAFF_ROLES, club=target_membership.club):
        raise PermissionError("Seul le Coach du club (ou son assistant) peut choisir le Capitaine.")

    if target_membership.status != Membership.Status.ACTIVE:
        raise RoleManagementError(
            "Ce joueur n'est plus inscrit au club : la nomination du Capitaine n'est pas possible."
        )

    if MembershipRole.all_objects.filter(
        club_id=target_membership.club_id,
        membership=target_membership,
        role=MembershipRole.Role.CAPTAIN,
        revoked_at__isnull=True,
    ).exists():
        raise RoleManagementError("Ce joueur est déjà Capitaine du club.")

    now = now or timezone.now()
    new_role = MembershipRole(
        club=target_membership.club,
        membership=target_membership,
        role=MembershipRole.Role.CAPTAIN,
        appointed_by=coach_user,
        appointed_at=now,
    )
    new_role.save()

    notify_role_change(role_instance=new_role, event="appointed")

    return new_role


def revoke_captain(*, coach_user, role: "MembershipRole", reason: str = "", now=None) -> "MembershipRole":
    """Retire le Capitaine (CDC 2.3 : « Il peut le changer »). Reserve au Coach."""

    if role.role != MembershipRole.Role.CAPTAIN:
        raise RoleManagementError("Ce rôle n'est pas celui de Capitaine.")
    if role.revoked_at is not None:
        raise RoleManagementError("Ce rôle est déjà révoqué.")
    if not has_any_role(coach_user, COACHING_STAFF_ROLES, club=role.club):
        raise PermissionError("Seul le Coach du club (ou son assistant) peut retirer le Capitaine.")

    now = now or timezone.now()
    role.revoked_by = coach_user
    role.revoked_at = now
    role.revoked_reason = reason
    role.save()

    notify_role_change(role_instance=role, event="revoked")

    return role


# ---------------------------------------------------------------------------
# Assistant du Coach (CDC 10.3 n179, decision client du 13/11/2026)
# ---------------------------------------------------------------------------
#
# (a) memes droits que le Coach (voir ``COACHING_STAFF_ROLES``), sauf
#     nommer/retirer un assistant ;
# (b) nomme et retire par le Coach SEUL (jamais le President, jamais un
#     assistant) ; journal (signal) + notification a l'interesse ;
# (c) UN SEUL assistant par Coach : en nommer un remplace le precedent ;
# (d) si le Coach change ou perd son role, l'assistant GARDE son poste
#     (aucune revocation automatique) ; un assistant dont le nominateur n'est
#     plus Coach est « orphelin » : tout Coach actif du club peut le retirer
#     ou le remplacer.


def _is_assistant_of(coach_user, role: "MembershipRole") -> bool:
    """Vrai si ``role`` (Assistant actif) releve de ``coach_user`` : nomme
    par lui, ou orphelin (son nominateur n'est plus Coach actif du club)."""

    if role.appointed_by_id == getattr(coach_user, "id", None):
        return True
    return not has_any_role(role.appointed_by, {MembershipRole.Role.COACH}, club=role.club)


def appoint_assistant_coach(*, coach_user, target_membership: "Membership", now=None) -> "MembershipRole":
    """Nomme l'Assistant du Coach (reserve au Coach). Remplace l'assistant
    precedent du Coach s'il y en a un (le retrait est journalise et notifie)."""

    club = target_membership.club
    if not has_any_role(coach_user, {MembershipRole.Role.COACH}, club=club):
        raise PermissionError("Seul le Coach du club peut nommer son assistant.")

    if target_membership.status != Membership.Status.ACTIVE:
        raise RoleManagementError(
            "Ce joueur n'est plus inscrit au club : la nomination de l'assistant n'est pas possible."
        )
    if target_membership.user_id == coach_user.id:
        raise RoleManagementError("Vous ne pouvez pas être votre propre assistant.")
    if has_any_role(target_membership.user, {MembershipRole.Role.COACH}, club=club):
        raise RoleManagementError("Ce joueur est déjà Coach du club : il ne peut pas être assistant.")

    now = now or timezone.now()
    with transaction.atomic():
        # Verrou sur l'adhesion du Coach : serialise deux nominations
        # simultanees du meme Coach (aucun assistant a verrouiller si aucun
        # n'existe encore).
        Membership.all_objects.select_for_update().filter(club=club, user=coach_user).first()
        active = list(
            MembershipRole.all_objects.select_for_update()
            .select_related("membership", "appointed_by")
            .filter(club=club, role=MembershipRole.Role.ASSISTANT_COACH, revoked_at__isnull=True)
        )
        mine = [r for r in active if _is_assistant_of(coach_user, r)]
        if any(r.membership_id == target_membership.id and r.appointed_by_id == coach_user.id for r in mine):
            raise RoleManagementError("Ce joueur est déjà votre assistant.")

        replaced = []
        for old in mine:
            old.revoked_by = coach_user
            old.revoked_at = now
            old.revoked_reason = "Remplacé par un nouvel assistant"
            old.save()  # journal (signal)
            replaced.append(old)

        new_role = MembershipRole(
            club=club,
            membership=target_membership,
            role=MembershipRole.Role.ASSISTANT_COACH,
            appointed_by=coach_user,
            appointed_at=now,
        )
        new_role.save()

    for old in replaced:
        notify_role_change(role_instance=old, event="revoked")
    notify_role_change(role_instance=new_role, event="appointed")
    return new_role


def remove_assistant_coach(*, coach_user, role: "MembershipRole", reason: str = "", now=None) -> "MembershipRole":
    """Retire l'Assistant du Coach (reserve au Coach ; le sien, ou un
    assistant orphelin -- decision (d))."""

    if role.role != MembershipRole.Role.ASSISTANT_COACH:
        raise RoleManagementError("Ce rôle n'est pas celui d'Assistant du Coach.")
    if not has_any_role(coach_user, {MembershipRole.Role.COACH}, club=role.club):
        raise PermissionError("Seul le Coach du club peut retirer son assistant.")

    now = now or timezone.now()
    with transaction.atomic():
        locked = (
            MembershipRole.all_objects.select_for_update()
            .select_related("appointed_by")
            .get(pk=role.pk)
        )
        if locked.revoked_at is not None:
            raise RoleManagementError("Ce rôle est déjà révoqué.")
        if not _is_assistant_of(coach_user, locked):
            raise PermissionError("Cet assistant a été nommé par un autre Coach du club.")
        locked.revoked_by = coach_user
        locked.revoked_at = now
        locked.revoked_reason = reason
        locked.save()

    notify_role_change(role_instance=locked, event="revoked")
    return locked


def transfer_presidency_by_handover(
    *, outgoing_user, to_membership: "Membership", reason: str = "", now=None
) -> "PresidencyTransfer":
    """Passation directe (CDC 2.3 : « le President sortant designe son
    successeur »).

    Atomique (``transaction.atomic`` + ``select_for_update`` sur le role
    President courant) : revoque le titulaire sortant et nomme l'entrant
    dans la meme transaction -- jamais d'etat intermediaire a zero ou
    deux Presidents (voir docstring de ``MembershipRole`` pour la
    cardinalite).
    """

    club = to_membership.club
    now = now or timezone.now()

    with transaction.atomic():
        current_role = (
            MembershipRole.all_objects.select_for_update()
            .filter(club=club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True)
            .first()
        )
        if current_role is None:
            raise RoleManagementError(
                "Aucun Président actif dans ce club : la passation directe est impossible."
            )
        if current_role.membership.user_id != getattr(outgoing_user, "id", None):
            raise PermissionError(
                "Seul le Président sortant peut désigner son successeur."
            )
        if to_membership.club_id != club.id:
            raise RoleManagementError("Le successeur doit appartenir au même club que le Président sortant.")
        if current_role.membership_id == to_membership.id:
            raise RoleManagementError(
                "Le successeur doit être un joueur différent du Président sortant."
            )
        if to_membership.status != Membership.Status.ACTIVE:
            raise RoleManagementError(
                "Le successeur n'est plus inscrit au club : la passation de présidence n'est pas possible."
            )

        from_membership = current_role.membership

        current_role.revoked_by = outgoing_user
        current_role.revoked_at = now
        current_role.revoked_reason = reason or "Passation de presidence"
        current_role.save()

        new_role = MembershipRole(
            club=club,
            membership=to_membership,
            role=MembershipRole.Role.PRESIDENT,
            appointed_by=outgoing_user,
            appointed_at=now,
        )
        new_role.save()

        transfer = PresidencyTransfer(
            club=club,
            from_membership=from_membership,
            to_membership=to_membership,
            method=PresidencyTransfer.Method.HANDOVER,
            reason=reason,
            transferred_at=now,
        )
        transfer.save()

    notify_role_change(role_instance=new_role, event="appointed")
    notify_role_change(role_instance=current_role, event="revoked")

    return transfer


def transfer_presidency_by_superuser(
    *, superuser, from_membership: "Membership", to_membership: "Membership", reason: str, now=None
) -> "PresidencyTransfer":
    """Intervention Superuser (CDC 2.3 : « en cas de blocage [...] par le
    Superuser sur demande ecrite du club, apres une assemblee generale »).

    Un motif ecrit est obligatoire, comme toute intervention Ghost Mode
    (CDC 2.5 : « bouton Intervenir sur ce club avec un motif obligatoire »).
    ``assembly`` (lien vers l'assemblee generale qui a mandate cette
    intervention) n'existe pas encore comme modele (Lot 4, tache 4.5) :
    non traite ici -- voir la docstring de ``PresidencyTransfer``.

    Meme atomicite que :func:`transfer_presidency_by_handover`.
    """

    if not getattr(superuser, "is_superuser", False):
        raise PermissionError("Seul un Superuser peut forcer une passation de présidence.")
    if not (reason or "").strip():
        raise RoleManagementError(
            "Un motif écrit est obligatoire pour une intervention du Superuser."
        )

    club = from_membership.club
    if to_membership.club_id != club.id:
        raise RoleManagementError("Le successeur doit appartenir au même club que le Président sortant.")
    if to_membership.status != Membership.Status.ACTIVE:
        raise RoleManagementError(
            "Le successeur n'est plus inscrit au club : la passation de présidence n'est pas possible."
        )

    now = now or timezone.now()

    with transaction.atomic():
        current_role = (
            MembershipRole.all_objects.select_for_update()
            .filter(club=club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True)
            .first()
        )
        if current_role is None or current_role.membership_id != from_membership.id:
            raise RoleManagementError(
                "L'adhésion indiquée comme sortante ne détient pas actuellement le rôle de Président."
            )

        current_role.revoked_by = superuser
        current_role.revoked_at = now
        current_role.revoked_reason = reason
        current_role.save()

        new_role = MembershipRole(
            club=club,
            membership=to_membership,
            role=MembershipRole.Role.PRESIDENT,
            appointed_by=superuser,
            appointed_at=now,
        )
        new_role.save()

        transfer = PresidencyTransfer(
            club=club,
            from_membership=from_membership,
            to_membership=to_membership,
            method=PresidencyTransfer.Method.SUPERUSER_OVERRIDE,
            superuser=superuser,
            reason=reason,
            transferred_at=now,
        )
        transfer.save()

    notify_role_change(role_instance=new_role, event="appointed")
    notify_role_change(role_instance=current_role, event="revoked")

    return transfer


def update_board_seats_per_role(
    *, president_user, club_settings: "ClubSettings", seats: int, now=None
) -> "ClubSettings":
    """Modifie le nombre de titulaires actifs autorises par role du bureau
    (10.2 n24). Reserve au President -- meme principe que la ligne
    « Identite du club » de la matrice 2.4 (« É » pour le President, « L »
    pour les autres).

    Journalise explicitement (pas de signal dedie sur ``ClubSettings`` a
    ce jour, a la difference de ``MembershipRole``/``PresidencyTransfer``).
    """

    if not has_any_role(president_user, {MembershipRole.Role.PRESIDENT}, club=club_settings.club):
        raise PermissionError(
            "Seul le Président peut modifier le nombre de titulaires par rôle."
        )

    before = {"board_seats_per_role": club_settings.board_seats_per_role}
    club_settings.board_seats_per_role = seats
    club_settings.updated_by = president_user
    club_settings.full_clean()
    club_settings.save()
    after = {"board_seats_per_role": club_settings.board_seats_per_role}

    log_action(
        actor=president_user,
        club=club_settings.club,
        action_type="clubs.settings.board_seats_updated",
        obj=club_settings,
        before=before,
        after=after,
    )

    return club_settings


# ---------------------------------------------------------------------------
# Ajout et import de joueurs (tache 1.4 ; CDC 4.1, matrice 2.4)
# ---------------------------------------------------------------------------
#
# Controle de permission (President ou joueur recruteur designe, matrice 2.4
# colonne « Ajout et import de joueurs » -- É Pdt, D pour les autres) : fait
# par ``apps.clubs.permissions.CanAddOrImportPlayers`` sur la vue, comme le
# reste de ce module -- pas de defense en profondeur ici : ces fonctions ne
# lisent/n'ecrivent que sur ``club``, un parametre explicite fourni par
# l'appelant (jamais un club transmis tel quel par le client, CLAUDE.md
# regle n9 -- c'est la vue qui le fixe au club actif du contexte courant).


class PlayerImportError(Exception):
    """Erreur metier lors de l'ajout/mise a jour d'une fiche joueur (CDC 4.1),
    message en francais destine au rapport de ligne de l'import CSV (ou a une
    reponse HTTP pour un futur ajout manuel d'un seul joueur)."""


class PlayerImportResult(NamedTuple):
    membership: "Membership"
    outcome: str  # "created" | "updated" | "created_new_club_membership"
    user_created: bool


class ImportRowReport(NamedTuple):
    line_number: int
    outcome: str  # "created" | "updated" | "created_new_club_membership" | "failed"
    message: str


class ImportSummary(NamedTuple):
    batch: "ImportBatch"
    rows: list[ImportRowReport]


_POSITION_ALIASES: dict[str, str] = {
    "gardien": Membership.Position.GOALKEEPER,
    "goalkeeper": Membership.Position.GOALKEEPER,
    "defenseur": Membership.Position.DEFENDER,
    "defender": Membership.Position.DEFENDER,
    "milieu": Membership.Position.MIDFIELDER,
    "midfielder": Membership.Position.MIDFIELDER,
    "attaquant": Membership.Position.FORWARD,
    "forward": Membership.Position.FORWARD,
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _parse_position(raw: str) -> str:
    """Normalise la colonne ``poste`` du CSV (CDC 4.1 : facultative a
    l'import, a la difference de la creation manuelle). Accepte les libelles
    francais affiches par la modale d'ajout manuel ou les codes internes
    (``Membership.Position``), insensible a la casse et aux accents.

    Leve :class:`PlayerImportError` (message en francais) pour toute valeur
    non reconnue -- jamais le message anglais par defaut d'un ``ChoiceField``
    Django (« Value '...' is not a valid choice »).
    """

    value = (raw or "").strip()
    if not value:
        return ""
    normalized = _strip_accents(value).lower()
    try:
        return _POSITION_ALIASES[normalized]
    except KeyError:
        raise PlayerImportError(
            f"poste inconnu : « {raw} » (attendu : Gardien, Défenseur, Milieu ou Attaquant, ou vide)."
        ) from None


def _parse_optional_date(raw: str) -> Optional["date"]:
    """Accepte JJ/MM/AAAA et AAAA-MM-JJ (CDC 4.1), vide autorise (facultatif a l'import)."""

    value = (raw or "").strip()
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise PlayerImportError(f"date de naissance invalide : « {raw} » (attendu JJ/MM/AAAA ou AAAA-MM-JJ).")


def _parse_optional_jersey_number(raw: str) -> Optional[int]:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        number = int(value)
    except ValueError:
        raise PlayerImportError(f"numéro de maillot invalide : « {raw} ».") from None
    if not (1 <= number <= 99):
        raise PlayerImportError(f"numéro de maillot invalide : « {raw} » (doit être entre 1 et 99).")
    return number


def _parse_optional_decimal(raw: str, field_label: str) -> Optional[Decimal]:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        raise PlayerImportError(f"{field_label} invalide : « {raw} ».") from None


def create_or_update_player(
    *,
    club: "Club",
    email: str,
    first_name: str,
    last_name: str,
    added_by,
    phone: str = "",
    position: str = "",
    position_detail: str = "",
    jersey_number: Optional[int] = None,
    birth_date=None,
    weight_kg: Optional[Decimal] = None,
    height_cm: Optional[Decimal] = None,
    sponsor: Optional["Membership"] = None,
    status: str = Membership.Status.ACTIVE,
    joined_on=None,
    requested_contribution_type_label: str = "",
    now=None,
) -> PlayerImportResult:
    """Cree ou met a jour la fiche joueur (`User` + `Membership`) correspondant
    a cet email, pour ``club`` (CDC 4.1). Fonction de service **unique et
    reutilisable**, appelee ligne a ligne par l'import CSV
    (:func:`import_players_from_csv`, tache 1.4) ; a reutiliser telle quelle
    par un futur ajout manuel d'un seul joueur (hors perimetre de cette
    tache, CDC 4.1 tableau « Ajout d'un joueur ») -- ne verifie donc **pas**
    elle-meme le caractere obligatoire du poste ou du parrain a la creation
    manuelle : ce sont des regles propres a chaque appelant, pas a ce
    service partage (l'import, lui, les rend explicitement facultatifs en ne
    les imposant jamais ici).

    Ne verifie pas les permissions (President/recruteur, CDC 2.4) : deja
    fait par la vue (``apps.clubs.permissions.CanAddOrImportPlayers``).

    Trois cas, sur la base de l'unicite de l'email sur toute la plateforme
    (CDC 4.1) :

    1. **Email deja present dans ``club``** : met a jour l'adhesion
       existante (``outcome="updated"``) -- seuls les champs fournis
       (non vides/non ``None``) ecrasent la valeur existante ; un champ
       absent de cette ligne ne vient jamais effacer une donnee deja
       renseignee. Le ``status`` n'est **jamais** touche par une mise a
       jour (seule la creation fixe le statut, CDC 4.1) : une adhesion
       existante garde le statut issu de son propre parcours (parrainage,
       transfert...), jamais reecrase silencieusement par une reimportation.
    2. **Email connu sur la plateforme, mais dans un AUTRE club (jamais dans
       ``club``)** : le compte `User` existant n'est jamais recree ni
       modifie au-dela de ses champs personnels usuels (voir
       ``apps.accounts.services.get_or_create_platform_user``) ; une
       **nouvelle** adhesion est creee pour ce club (``outcome=
       "created_new_club_membership"``). Interpretation par defaut retenue
       a titre provisoire pour ce cas precis, non detaille par le CDC 4.1
       pour l'import (CLAUDE.md, circuit 9.4) -- signalee au compte rendu
       de la tache 1.4, a confirmer par le client.

       Garde de securite (audit tache 1.13, ecart bloquant B2) : si ce
       compte a deja une adhesion ``ACTIVE`` dans un club different de
       ``club`` et que la nouvelle adhesion serait elle-meme ``ACTIVE``,
       cette fonction refuse (:class:`PlayerImportError`, message neutre)
       plutot que de creer une seconde adhesion active -- deux adhesions
       actives simultanees rendent le club actif ambigu pour
       ``apps.core.services.resolve_active_membership``, ce qui coupe
       silencieusement l'acces du proprietaire legitime a tous ses clubs
       (``apps.core.authentication.TenantJWTAuthentication`` avale alors
       ``NoActiveClubError`` sans fixer de club actif). Ne tranche pas la
       question metier ouverte ci-dessus (que faire de ce cas) : bloque
       seulement le deni de service, position la plus prudente par defaut
       tant que le client n'a pas tranche (CLAUDE.md section 1).
    3. **Email totalement nouveau** : nouveau `User` (mot de passe initial =
       email, changement obligatoire, CDC 4.1) et nouvelle adhesion
       (``outcome="created"``).

    Leve :class:`PlayerImportError` (message en francais) si le numéro de
    maillot fourni est déjà porté par un autre joueur ACTIF de ``club``
    (CDC 4.1 : « Numero de maillot [...] Unique dans le club » ; controle de
    service, pas de contrainte DB -- voir le commentaire de
    ``Membership.jersey_number``), ou si le compte a deja une adhesion
    ``ACTIVE`` dans un autre club (voir cas 2 ci-dessus). Laisse se
    propager ``django.core.exceptions.ValidationError`` pour toute autre
    regle de coherence de ``Membership.clean()`` (ex. parrain d'un autre
    club).
    """

    now = now or timezone.now()
    normalized_email = (email or "").strip().lower()

    if jersey_number is not None:
        conflict = (
            Membership.all_objects.filter(
                club=club, status=Membership.Status.ACTIVE, jersey_number=jersey_number
            )
            .exclude(user__email=normalized_email)
            .select_related("user")
            .first()
        )
        if conflict is not None:
            raise PlayerImportError(
                f"le numéro {jersey_number} est déjà porté par "
                f"{conflict.user.first_name} {conflict.user.last_name}."
            )

    # Garde (D-A1, position prudente provisoire, question client Q1) : un
    # compte déjà membre ACTIF ou EN ATTENTE d'un AUTRE club n'est ni enrôlé
    # ni modifié ici -- une seconde adhésion rendrait le club actif ambigu
    # (``resolve_active_membership``) et couperait l'accès du propriétaire
    # légitime à tous ses clubs. Contrôle fait AVANT toute écriture sur le
    # compte. Message neutre : ne révèle ni l'existence du compte ni
    # l'autre club. Un compte « parti » (DEPARTED) reste repris normalement.
    already_member_here = Membership.all_objects.filter(club=club, user__email=normalized_email).exists()
    if not already_member_here and Membership.all_objects.filter(
        user__email=normalized_email,
        status__in=(Membership.Status.ACTIVE, Membership.Status.PENDING),
    ).exclude(club=club).exists():
        raise PlayerImportError("Ce compte ne peut pas être ajouté à ce club pour le moment.")

    platform_user_result = accounts_services.get_or_create_platform_user(
        email=normalized_email,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        birth_date=birth_date,
        weight_kg=weight_kg,
        height_cm=height_cm,
    )
    user = platform_user_result.user
    user_created = platform_user_result.created

    # Journalisation des champs personnels d'un compte `User` DEJA existant
    # (audit tache 1.14, ecart bloquant B4) -- s'applique aussi bien au cas
    # 1 (email deja dans `club`) qu'au cas 2 (email connu ailleurs sur la
    # plateforme) : du point de vue du seul compte `User`,
    # ``get_or_create_platform_user`` ne distingue pas ces deux cas (voir
    # sa docstring). Rien n'est journalise ici pour un compte tout juste
    # cree (``platform_user_result.created`` vrai) : la creation du compte
    # est deja couverte par ``membership.created`` (signal, tache 1.6) plus
    # bas dans cette fonction -- et rien non plus pour une mise a jour
    # « no-op » (aucun champ reellement modifie).
    if platform_user_result.updated_fields_before is not None:
        log_platform_user_updated(
            user,
            platform_user_result.updated_fields_before,
            platform_user_result.updated_fields_after,
            actor=added_by,
            club=club,
        )

    existing_membership = Membership.all_objects.filter(club=club, user=user).first()

    if existing_membership is not None:
        before = membership_snapshot(existing_membership)
        changed_fields: list[str] = []
        if position:
            existing_membership.position = position
            changed_fields.append("position")
        if position_detail:
            existing_membership.position_detail = position_detail
            changed_fields.append("position_detail")
        if jersey_number is not None:
            existing_membership.jersey_number = jersey_number
            changed_fields.append("jersey_number")
        if requested_contribution_type_label:
            existing_membership.requested_contribution_type_label = requested_contribution_type_label
            changed_fields.append("requested_contribution_type_label")

        if changed_fields:
            existing_membership.save()
            log_membership_updated(existing_membership, before, actor=added_by)

        return PlayerImportResult(existing_membership, "updated", user_created)

    membership = Membership(
        club=club,
        user=user,
        status=status,
        sponsor=sponsor,
        position=position,
        position_detail=position_detail,
        jersey_number=jersey_number,
        requested_contribution_type_label=requested_contribution_type_label,
        joined_on=joined_on or now.date(),
        added_by=added_by,
    )
    membership.save()  # full_clean() (coherence) + journal (signal, tache 1.6)

    outcome = "created" if user_created else "created_new_club_membership"
    return PlayerImportResult(membership, outcome, user_created)


_ROW_OUTCOME_MESSAGES = {
    "created": "joueur créé.",
    "updated": "fiche mise à jour.",
    # Message neutre : ne révèle pas si l'email existait déjà ailleurs (CDC 7.6).
    "created_new_club_membership": "adhésion créée.",
}


# En-tetes acceptees a l'import CSV (CDC 4.1 / annexe C, modele francais --
# ET en-tetes anglaises des exports reels du club pilote, voir
# ``data/cotisations_membres_categorie_*.csv`` : ``email,first_name,
# last_name,position,jersey_number,birth_date``, constate en investigation
# directe, aucune ligne de ces fichiers ne passait avec les seules en-tetes
# francaises). Cles ci-dessous deja normalisees (minuscules, sans accent) --
# voir :func:`_normalize_csv_row_keys`. Le premier alias present dans la
# ligne l'emporte ; l'ordre francais-puis-anglais n'a d'effet que si un
# fichier melange improbablement les deux jeux d'en-tetes pour un meme
# champ.
_ROW_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "email": ("email",),
    "prenom": ("prenom", "first_name", "firstname"),
    "nom": ("nom", "last_name", "lastname"),
    "telephone": ("telephone", "phone"),
    "poste": ("poste", "position"),
    "numero": ("numero", "jersey_number"),
    "date_naissance": ("date_naissance", "birth_date"),
    "poids": ("poids", "weight", "weight_kg"),
    "taille": ("taille", "height", "height_cm"),
    "type_cotisation": ("type_cotisation", "contribution_type"),
}


def _normalize_csv_row_keys(raw_row: dict[str, Any]) -> dict[str, Any]:
    """Normalise les en-tetes (cles) d'une ligne ``csv.DictReader`` :
    insensible a la casse et aux accents (``Prenom``, ``PRENOM``,
    ``prénom`` sont equivalents). La cle ``None`` (colonnes en trop par
    rapport a l'en-tete, regroupees par ``csv.DictReader`` sous cette cle)
    est ignoree ici -- comportement deja tolere avant cette fonction."""

    normalized: dict[str, Any] = {}
    for raw_key, value in raw_row.items():
        if raw_key is None:
            continue
        key = _strip_accents(raw_key).strip().lower()
        normalized[key] = value
    return normalized


def _get_row_value(normalized_row: dict[str, Any], canonical_field: str) -> Any:
    """Renvoie la valeur du premier en-tete alias present (francais ou
    anglais, voir :data:`_ROW_FIELD_ALIASES`) pour ``canonical_field``, ou
    ``None`` si aucun des deux jeux d'en-tetes n'est present dans le
    fichier."""

    for alias in _ROW_FIELD_ALIASES[canonical_field]:
        if alias in normalized_row:
            return normalized_row[alias]
    return None


def _import_single_row(*, club, added_by, raw_row: dict[str, Any], now) -> PlayerImportResult:
    """Traite une ligne du CSV (CDC 4.1). Leve :class:`PlayerImportError`
    pour toute erreur de cette ligne uniquement -- l'appelant
    (:func:`import_players_from_csv`) continue avec les lignes suivantes.

    Accepte indifferemment les en-tetes francaises du modele CDC 4.1
    (``email, prenom, nom, telephone, poste, numero, date_naissance,
    poids, taille, type_cotisation``) ou les en-tetes anglaises des
    exports reels du club pilote (``email, first_name, last_name, phone,
    position, jersey_number, birth_date, weight/weight_kg,
    height/height_cm, contribution_type``), insensible a la casse et aux
    accents -- voir :data:`_ROW_FIELD_ALIASES`. Seuls ``email``,
    ``prenom``/``first_name`` et ``nom``/``last_name`` restent obligatoires,
    le reste reste facultatif exactement comme avant."""

    normalized_row = _normalize_csv_row_keys(raw_row)

    email = (_get_row_value(normalized_row, "email") or "").strip()
    first_name = (_get_row_value(normalized_row, "prenom") or "").strip()
    last_name = (_get_row_value(normalized_row, "nom") or "").strip()

    if not email:
        raise PlayerImportError("email manquant.")
    if not first_name:
        raise PlayerImportError("prénom manquant.")
    if not last_name:
        raise PlayerImportError("nom manquant.")

    try:
        validate_email(email)
    except DjangoValidationError:
        raise PlayerImportError("email invalide.") from None

    phone = (_get_row_value(normalized_row, "telephone") or "").strip()
    position = _parse_position(_get_row_value(normalized_row, "poste") or "")
    jersey_number = _parse_optional_jersey_number(_get_row_value(normalized_row, "numero") or "")
    birth_date = _parse_optional_date(_get_row_value(normalized_row, "date_naissance") or "")
    weight_kg = _parse_optional_decimal(_get_row_value(normalized_row, "poids") or "", "poids")
    height_cm = _parse_optional_decimal(_get_row_value(normalized_row, "taille") or "", "taille")
    requested_contribution_type_label = (_get_row_value(normalized_row, "type_cotisation") or "").strip()

    return create_or_update_player(
        club=club,
        email=email,
        first_name=first_name,
        last_name=last_name,
        added_by=added_by,
        phone=phone,
        position=position,
        jersey_number=jersey_number,
        birth_date=birth_date,
        weight_kg=weight_kg,
        height_cm=height_cm,
        sponsor=None,
        status=Membership.Status.ACTIVE,
        joined_on=now.date(),
        requested_contribution_type_label=requested_contribution_type_label,
        now=now,
    )


def _build_import_report_file(rows: list[ImportRowReport]) -> ContentFile:
    """Rapport CSV joint au lot d'import (CDC 4.1 : « Le rapport liste les
    lignes importees et les lignes en echec, avec le numéro de ligne et un
    message en francais »). Pas de PDF stylise : hors perimetre de cette
    tache (voir tache 1.11, modeles/annexes)."""

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ligne", "resultat", "message"])
    for row in rows:
        writer.writerow([row.line_number, row.outcome, row.message])
    return ContentFile(buffer.getvalue().encode("utf-8"), name="rapport_import.csv")


def import_players_from_csv(*, club: "Club", imported_by, csv_file, now=None) -> ImportSummary:
    """Importe des joueurs depuis un fichier CSV (CDC 4.1, tache 1.4).

    Colonnes attendues (CDC 4.1 / annexe C) : ``email, prenom, nom,
    telephone, poste, numero, date_naissance, poids, taille,
    type_cotisation``. **Egalement acceptees, indifferemment et insensible
    a la casse/aux accents** (bug remonte en remarques.md : les exports
    reels du club pilote dans ``data/`` utilisent ces en-tetes anglaises,
    pas les en-tetes francaises du CDC) : ``first_name``/``firstname``
    (-> prenom), ``last_name``/``lastname`` (-> nom), ``phone`` (->
    telephone), ``position`` (-> poste), ``jersey_number`` (-> numero),
    ``birth_date`` (-> date_naissance), ``weight``/``weight_kg`` (->
    poids), ``height``/``height_cm`` (-> taille), ``contribution_type``
    (-> type_cotisation) -- voir :data:`_ROW_FIELD_ALIASES`. Seuls
    ``email``, ``prenom``/``first_name`` et ``nom``/``last_name`` sont
    obligatoires (CDC 4.1) -- une colonne absente du fichier ou une
    cellule vide sont traitees de la meme facon (jamais un echec pour un
    poste ou une date manquants, critere de fin de la tache 1.4 : « Import
    de 40 joueurs sans poste ni date reussit sans echec »).

    Chaque ligne est traitee **independamment** : une ligne en echec
    n'interrompt jamais l'import des lignes suivantes (CDC 4.1). Les joueurs
    importes passent directement « Inscrit » (``Membership.Status.ACTIVE``),
    sans parrainage (``sponsor=None``) -- CDC 4.1 : « Les joueurs importes
    sont membres historiques : ils passent directement Inscrit, sans
    parrainage. »

    Chaque ligne s'execute dans sa propre transaction (``transaction.atomic()``
    imbriquee -- savepoint -- autour de :func:`_import_single_row`, audit
    tache 1.14 ecart bloquant B4) : une ligne rejetee (garde de securite B2,
    numero de maillot en conflit, ``Membership.clean()``...) annule TOUTES
    les ecritures qu'elle a deja faites, y compris une mise a jour de
    compte `User` deja existant (cas 2 de :func:`create_or_update_player` --
    potentiellement le compte d'un joueur d'un AUTRE club) faite par
    ``get_or_create_platform_user`` avant que l'erreur ne soit detectee plus
    loin dans la meme ligne. Sans ce point de rollback, cette mutation
    restait persistee en base sans aucune trace ni annulation, alors meme
    que la ligne etait rapportee comme « echouee ». Ce projet ne tourne pas
    sous ``ATOMIC_REQUESTS`` (CLAUDE.md, ``config/settings/base.py``) :
    ``transaction.atomic()`` demarre ici sa propre transaction (ou un
    savepoint imbrique si un appelant de test entoure deja l'appel d'une
    transaction) -- ne change rien au comportement « une ligne en echec
    n'interrompt jamais les suivantes » ci-dessus, seulement la portee de ce
    qui est annule pour la ligne elle-meme.

    Ne verifie pas les permissions (President/recruteur designe, CDC 2.4) :
    deja fait par la vue (``apps.clubs.permissions.CanAddOrImportPlayers``).

    Renvoie un :class:`ImportSummary` (le ``ImportBatch`` cree, deja
    journalise -- signal de ``apps.clubs.signals``, tache 1.6 -- et le
    detail ligne par ligne, pour que la vue puisse renvoyer la liste des
    echecs sans devoir relire le fichier de rapport).
    """

    now = now or timezone.now()

    raw_bytes = csv_file.read()
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise PlayerImportError(
            "Le fichier n'est pas encodé en UTF-8. Réenregistrez-le en UTF-8 avant de l'importer."
        ) from None
    reader = csv.DictReader(io.StringIO(text))

    rows: list[ImportRowReport] = []
    success_count = 0
    failed_count = 0

    # Ligne 1 = en-tetes (CDC 4.1, modele CSV) : la premiere ligne de donnees
    # est donc la ligne 2, coherent avec l'exemple du CDC (« Ligne 12 »).
    for line_number, raw_row in enumerate(reader, start=2):
        try:
            # Savepoint par ligne (audit tache 1.14, ecart bloquant B4) :
            # toute exception levee par `_import_single_row` annule ici
            # TOUTES les ecritures de cette ligne (y compris une mutation
            # de `User` deja existant faite avant que l'erreur ne soit
            # detectee), sans affecter les lignes deja validees avant elle
            # -- voir la docstring de cette fonction.
            with transaction.atomic():
                result = _import_single_row(club=club, added_by=imported_by, raw_row=raw_row, now=now)
        except PlayerImportError as exc:
            rows.append(ImportRowReport(line_number, "failed", f"Ligne {line_number} : {exc}"))
            failed_count += 1
            continue
        except DjangoValidationError as exc:
            message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            rows.append(ImportRowReport(line_number, "failed", f"Ligne {line_number} : {message}"))
            failed_count += 1
            continue

        message = f"Ligne {line_number} : {_ROW_OUTCOME_MESSAGES[result.outcome]}"
        rows.append(ImportRowReport(line_number, result.outcome, message))
        success_count += 1

    batch = ImportBatch(
        club=club,
        import_type=ImportBatch.ImportType.PLAYERS,
        source_file=ContentFile(raw_bytes, name="import.csv"),
        report_file=_build_import_report_file(rows),
        imported_by=imported_by,
        imported_at=now,
        row_count_success=success_count,
        row_count_failed=failed_count,
    )
    batch.save()  # full_clean() + journal (signal, tache 1.6)

    return ImportSummary(batch=batch, rows=rows)


# ---------------------------------------------------------------------------
# Adhesion et parrainage (tache 1.4b ; CDC 4.3, 3.7 etape 3, 5.3)
# ---------------------------------------------------------------------------
#
# Consomme telle quelle l'interface exposee par `finance-engine`
# (`apps.treasury.services.record_membership_fee_payment`/
# `has_paid_membership_fee`/`refund_membership_fee`/
# `get_active_membership_fee_type`) : elle n'est pas modifiee ici. Les permissions de vue restent dans
# `apps.clubs.permissions` (President/recruteur pour l'ajout, Tresorier/
# adjoint pour le paiement -- matrice 2.4, confirme par `finance-engine`) ;
# les fonctions ci-dessous revalident neanmoins le role President pour les
# decisions qui lui sont reservees (reassignation de parrain, annulation),
# meme defense en profondeur que le reste de ce module.

SPONSOR_REMINDER_DELAY = timedelta(days=3)
PRESIDENT_ALERT_DELAY = timedelta(days=7)


class MembershipApplicationError(Exception):
    """Erreur metier du dossier d'adhesion et de parrainage (CDC 4.3),
    message en francais clair destine a une reponse HTTP."""


def _application_snapshot(application: "MembershipApplication") -> dict[str, Any]:
    return {
        "membership_id": application.membership_id,
        "generated_at": application.generated_at,
        "sponsor_notified_at": application.sponsor_notified_at,
        "sponsor_decision": application.sponsor_decision,
        "sponsor_signed_by_id": application.sponsor_signed_by_id,
        "sponsor_signed_at": application.sponsor_signed_at,
        "sponsor_refused_reason": application.sponsor_refused_reason,
        "sponsor_reminder_sent_at": application.sponsor_reminder_sent_at,
        "president_alerted_at": application.president_alerted_at,
        "resolved_at": application.resolved_at,
        "cancelled_by_id": application.cancelled_by_id,
        "cancelled_reason": application.cancelled_reason,
        "membership_fee_payment_id": application.membership_fee_payment_id,
        "membership_fee_disposition": application.membership_fee_disposition,
    }


def _recruit_full_name(application: "MembershipApplication") -> str:
    user = application.membership.user
    return f"{user.first_name} {user.last_name}".strip()


def _active_president_membership(club: "Club") -> Optional["Membership"]:
    """Adhesion du President actif de ``club``, ou ``None`` si aucun
    President n'est actuellement en poste (cas limite -- ne doit pas
    faire echouer le flux de parrainage : sans President a notifier, la
    notification est simplement omise)."""

    role = (
        MembershipRole.all_objects.select_related("membership__user")
        .filter(club=club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True)
        .first()
    )
    return role.membership if role is not None else None


def notify_sponsor(*, application: "MembershipApplication") -> None:
    """Notification au parrain (CDC 4.3 etape 4 : « Le parrain recoit une
    notification et signe »), reutilisee pour le rappel a
    3 jours.

    Cablee tache 1.7. Distingue les deux evenements CDC 4.17 (« Fiche
    d'adhesion a signer » vs « Rappel au parrain sans reponse [3 jours] »)
    sans changer la signature ni les points d'appel existants (contrainte
    deja documentee a la tache 1.4b) : ``application.sponsor_reminder_sent_at``
    est deja renseigne (par l'appelant, avant cet appel) si et seulement
    si c'est un rappel -- jamais encore renseigne pour la toute premiere
    notification (voir :func:`notify_sponsor_for_signature` et
    :func:`process_sponsor_reminders_and_alerts`)."""

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    recruit_name = _recruit_full_name(application)
    is_reminder = application.sponsor_reminder_sent_at is not None

    if is_reminder:
        event_type = Notification.EventType.SPONSOR_REMINDER
        title = "Rappel : fiche d'adhésion à signer"
        message = (
            f"La fiche d'adhésion de {recruit_name} attend votre réponse "
            "depuis 3 jours. Signez-la, ou refusez en "
            "indiquant un motif."
        )
    else:
        event_type = Notification.EventType.MEMBERSHIP_SIGNATURE_PENDING
        title = "Fiche d'adhésion à signer"
        message = (
            f"{recruit_name} attend votre parrainage. Ouvrez sa fiche "
            "d'adhésion pour la signer, ou pour refuser "
            "en indiquant un motif."
        )

    create_notification(
        recipient=application.membership.sponsor.user,
        event_type=event_type,
        title=title,
        message=message,
        target=application,
    )


def notify_president_of_sponsor_refusal(*, application: "MembershipApplication") -> None:
    """« Le President est notifie » (CDC 4.3, cas limite « le parrain
    refuse »). Cablee tache 1.7 -- CDC 4.17 : « Refus du parrain [...] --
    President -- In-app »."""

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    president_membership = _active_president_membership(application.club)
    if president_membership is None:
        return None

    recruit_name = _recruit_full_name(application)
    sponsor_name = f"{application.membership.sponsor.user.first_name} {application.membership.sponsor.user.last_name}".strip()
    message = (
        f"{sponsor_name} a refusé de parrainer {recruit_name}. Motif : "
        f"« {application.sponsor_refused_reason} ». Désignez un autre "
        "parrain ou annulez l'adhésion."
    )

    create_notification(
        recipient=president_membership.user,
        event_type=Notification.EventType.SPONSOR_REFUSED,
        title="Parrainage refusé",
        message=message,
        target=application,
    )


def notify_president_of_no_response(*, application: "MembershipApplication") -> None:
    """« Alerte au President apres 7 jours » (CDC 4.3, cas limite « le
    parrain ne repond pas »). Cablee tache 1.7 -- CDC 4.17 : « [...] ou
    silence apres 7 jours -- President -- In-app »."""

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    president_membership = _active_president_membership(application.club)
    if president_membership is None:
        return None

    recruit_name = _recruit_full_name(application)
    sponsor_name = f"{application.membership.sponsor.user.first_name} {application.membership.sponsor.user.last_name}".strip()
    message = (
        f"{sponsor_name} n'a toujours pas signé la fiche d'adhésion de "
        f"{recruit_name}, 7 jours après l'avoir reçue. Un rappel lui a "
        "déjà été envoyé."
    )

    create_notification(
        recipient=president_membership.user,
        event_type=Notification.EventType.SPONSOR_ALERT_PRESIDENT,
        title="Parrain sans réponse",
        message=message,
        target=application,
    )


def add_player_with_sponsor(
    *,
    club: "Club",
    email: str,
    first_name: str,
    last_name: str,
    added_by,
    sponsor: "Membership",
    position: str,
    position_detail: str = "",
    jersey_number: Optional[int] = None,
    birth_date=None,
    weight_kg: Optional[Decimal] = None,
    height_cm: Optional[Decimal] = None,
    phone: str = "",
    requested_contribution_type_label: str = "",
    now=None,
) -> tuple["Membership", "MembershipApplication"]:
    """Ajoute manuellement un nouveau joueur « En attente », avec parrain
    obligatoire (CDC 4.3 etape 1 ; 4.1, colonne « Ajout d'un joueur » :
    « Poste : Oui a la creation manuelle », « Parrain : Oui pour un nouveau
    joueur »).

    Reutilise :func:`create_or_update_player` (tache 1.4) pour la partie
    « compte + adhesion » -- **sans** en assouplir les regles pour
    l'import CSV (le parrain et le poste restent facultatifs a l'import,
    seule cette fonction les rend obligatoires pour l'ajout manuel).

    Cree dans la meme operation le dossier d'adhesion
    (:class:`MembershipApplication`) qui portera le paiement, la fiche PDF
    et la decision du parrain (etapes 2 a 5 -- voir
    :func:`record_membership_fee_payment_for_application`,
    :func:`sign_sponsor_application`, :func:`refuse_sponsor_application`).

    Ne verifie pas les permissions (President/recruteur designe, CDC 2.4) :
    deja fait par la vue (``apps.clubs.permissions.CanAddOrImportPlayers``,
    reutilisee telle quelle -- meme colonne de la matrice 2.4).

    Leve :class:`MembershipApplicationError` (message en francais) si :

    - aucun parrain n'est fourni ;
    - le parrain n'appartient pas a ``club`` ou n'est pas Inscrit
      (CDC 4.3 : « un parrain choisi parmi les joueurs inscrits ») ;
    - le poste est absent (obligatoire a la creation manuelle, CDC 4.1) ;
    - l'email correspond a un joueur deja membre de CE club (cette
      fonction est reservee a un **nouveau** joueur du club -- une mise a
      jour de fiche existante reste le rôle de l'import CSV/
      :func:`create_or_update_player` directement, pas de ce parcours de
      parrainage).
    """

    now = now or timezone.now()

    if sponsor is None:
        raise MembershipApplicationError(
            "Un parrain est obligatoire pour ajouter un nouveau joueur."
        )
    if sponsor.club_id != club.id:
        raise MembershipApplicationError("Le parrain doit appartenir au même club que le nouveau joueur.")
    if sponsor.status != Membership.Status.ACTIVE:
        raise MembershipApplicationError(
            "Le parrain doit être un joueur inscrit du club."
        )
    if not (position or "").strip():
        raise MembershipApplicationError(
            "Le poste est obligatoire pour ajouter un joueur manuellement."
        )

    # Tout-ou-rien : `create_or_update_player` ecrit le `User`, le
    # `Membership`, le journal et les notifications AVANT que l'on sache si
    # l'email etait deja membre du club (`outcome == "updated"`, erreur
    # levee plus bas). Sans transaction, cette erreur laisserait les
    # modifications en base (pas d'`ATOMIC_REQUESTS`). Meme principe que
    # `import_players_from_csv` (audit tache 1.14, ecart B4).
    with transaction.atomic():
        result = create_or_update_player(
            club=club,
            email=email,
            first_name=first_name,
            last_name=last_name,
            added_by=added_by,
            phone=phone,
            position=position,
            position_detail=position_detail,
            jersey_number=jersey_number,
            birth_date=birth_date,
            weight_kg=weight_kg,
            height_cm=height_cm,
            sponsor=sponsor,
            status=Membership.Status.PENDING,
            joined_on=now.date(),
            requested_contribution_type_label=requested_contribution_type_label,
            now=now,
        )
        if result.outcome == "updated":
            raise MembershipApplicationError(
                "Ce joueur est déjà membre de ce club : utilisez sa fiche existante plutôt que d'en ajouter une nouvelle."
            )

        application = MembershipApplication(club=club, membership=result.membership)
        application.save()  # full_clean() (coherence de club)

        # Decision du client du 17/11/2026 (CDC 4.3, 4.4.2 ; 10.3 n° 100) :
        # les frais d'adhesion sont une somme a payer -- montant du unique
        # cree avec l'adhesion, dans la meme transaction (idempotent ; aucun
        # du si le club n'a pas de type « adhesion » actif).
        from apps.treasury import services as treasury_services

        treasury_services.ensure_membership_fee_due(result.membership, actor=added_by, now=now)

        return result.membership, application


APPLICATION_DOC_TYPE_LABEL = "Fiche d'adhésion"


def _build_membership_application_pdf(application: "MembershipApplication") -> bytes:
    """Construit la fiche d'adhésion en PDF (CDC 4.3 étape 3), avec
    l'en-tête commun ``apps.core.pdf.draw_header`` (logo et couleurs du club,
    comme le reçu de trésorerie). Aucune mention de l'éditeur ni de la
    plateforme sur le document. Un logo absent ou illisible ne fait jamais
    échouer la génération (géré par ``draw_header``).
    """

    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from apps.core.pdf import (
        DARK_TEXT_RGB,
        MARGIN,
        MUTED_TEXT_RGB,
        NumberedDocumentCanvas,
        draw_header,
        make_footer_drawer,
        wrap_text,
    )

    membership = application.membership
    club = membership.club
    sponsor = membership.sponsor
    payment = application.membership_fee_payment

    tz = ZoneInfo("UTC")
    club_settings = getattr(club, "settings", None)
    try:
        tz = ZoneInfo(club_settings.timezone) if club_settings is not None else tz
    except (ZoneInfoNotFoundError, ValueError):
        pass
    generated_local = timezone.now().astimezone(tz)

    doc_type_label = APPLICATION_DOC_TYPE_LABEL
    reference = f"A-{application.pk}"
    width, height = A4
    content_width = width - 2 * MARGIN

    buffer = io.BytesIO()
    footer_fn = make_footer_drawer(
        club_name=club.name,
        doc_type_label=doc_type_label,
        reference=reference,
        generated_at_text=f"{generated_local.strftime('%d/%m/%Y')} à {generated_local.strftime('%H:%M')}",
        width=width,
    )
    pdf = NumberedDocumentCanvas(buffer, pagesize=A4, pageCompression=0, footer_fn=footer_fn)
    pdf.setTitle(doc_type_label)
    pdf.setAuthor(club.name)
    pdf.setCreator(club.name)
    pdf.setSubject(doc_type_label)

    y = draw_header(
        pdf, club=club, doc_type_label=doc_type_label, reference=f"Réf. {reference}", width=width, height=height
    )

    pdf.setFillColorRGB(*DARK_TEXT_RGB)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(MARGIN, y, doc_type_label)
    y -= 12 * mm

    label_col = 48 * mm

    def field_row(label: str, value: str) -> None:
        nonlocal y
        pdf.setFillColorRGB(*MUTED_TEXT_RGB)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(MARGIN, y, label)
        pdf.setFillColorRGB(*DARK_TEXT_RGB)
        for line in wrap_text(value, font="Helvetica", size=10, max_width=content_width - label_col):
            pdf.setFont("Helvetica", 10)
            pdf.drawString(MARGIN + label_col, y, line)
            y -= 10 * 1.35
        y -= 2 * mm

    field_row("Joueur", f"{membership.user.first_name} {membership.user.last_name}")
    field_row("Parrain", f"{sponsor.user.first_name} {sponsor.user.last_name}" if sponsor else "-")
    if payment is not None:
        field_row("Montant payé", f"{payment.amount} {payment.currency}")
        field_row("Date de paiement", payment.paid_on.strftime("%d/%m/%Y"))
    field_row("Date de génération", generated_local.strftime("%d/%m/%Y %H:%M"))

    y -= 4 * mm
    pdf.setFillColorRGB(*MUTED_TEXT_RGB)
    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawString(MARGIN, y, "Cette fiche est valable une fois signée par le parrain.")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def generate_membership_application_pdf(
    *, application: "MembershipApplication", actor, now=None
) -> "MembershipApplication":
    """Genere la fiche d'adhesion en PDF et l'attache au dossier (CDC 4.3
    etape 3). Reserve a un usage interne, apres paiement complet -- voir
    :func:`record_membership_fee_payment_for_application`, seul point
    d'entree normal (idempotent : ne regenere jamais une fiche deja
    generee).

    Journalise ``clubs.membership_application.pdf_generated``.
    """

    if application.generated_at is not None:
        return application

    now = now or timezone.now()
    pdf_bytes = _build_membership_application_pdf(application)
    before = _application_snapshot(application)
    application.application_pdf_file.save(
        f"adhesion-{application.membership_id}.pdf", ContentFile(pdf_bytes), save=False
    )
    application.generated_at = now
    application.save()
    log_action(
        actor=actor,
        club=application.club,
        action_type="clubs.membership_application.pdf_generated",
        obj=application,
        before=before,
        after=_application_snapshot(application),
    )
    return application


def notify_sponsor_for_signature(*, application: "MembershipApplication", now=None) -> "MembershipApplication":
    """Notifie le parrain qu'il doit signer (CDC 4.3 etape 4). Idempotent :
    ne renvoie jamais deux notifications « premiere demande » pour le meme
    dossier (le rappel a 3 jours est une fonction distincte, voir
    :func:`process_sponsor_reminders_and_alerts`)."""

    if application.sponsor_notified_at is not None:
        return application

    now = now or timezone.now()
    with transaction.atomic():
        # Marquage et notification ensemble : un echec de la notification
        # n'enregistre pas « notifie », le rejeu pourra donc la renvoyer.
        application.sponsor_notified_at = now
        application.save()
        notify_sponsor(application=application)
    return application


def _maybe_activate_membership(*, application: "MembershipApplication", actor, now=None) -> "Membership":
    """Fait passer l'adhesion « Inscrit » des que les deux conditions du
    CDC 4.3 etape 5 sont reunies (« adhesion payee + parrain signe »),
    quel que soit l'ordre dans lequel elles surviennent. A appeler a
    chaque evenement pertinent (paiement valide, signature recue).

    Ne fait rien (silencieusement) si l'une des deux conditions manque
    encore, ou si l'adhesion est deja Inscrite -- jamais d'erreur : c'est
    une verification de routine, pas une action demandee explicitement.
    """

    from apps.treasury import services as treasury_services

    now = now or timezone.now()
    membership = application.membership
    if membership.status == Membership.Status.ACTIVE:
        return membership
    if not treasury_services.has_paid_membership_fee(membership):
        return membership
    if application.sponsor_decision != MembershipApplication.SponsorDecision.SIGNED:
        return membership

    with transaction.atomic():
        # Verrou puis re-verification du statut : deux evenements simultanes
        # (paiement + signature) n'ecrivent qu'un seul passage « Inscrit ».
        locked = Membership.all_objects.select_for_update().get(pk=membership.pk, club_id=membership.club_id)
        if locked.status == Membership.Status.ACTIVE:
            membership.status = locked.status
            return membership
        before = membership_snapshot(locked)
        locked.status = Membership.Status.ACTIVE
        locked.save()
        log_membership_updated(locked, before, actor=actor)
    membership.status = locked.status
    return locked


def record_membership_fee_payment_for_application(
    *,
    application: "MembershipApplication",
    amount: Any,
    method: str,
    paid_on: date,
    validated_by,
    reference: str = "",
    attachment=None,
    now=None,
    client_uuid=None,
) -> "MembershipApplication":
    """Enregistre le paiement des frais d'adhesion d'un dossier de
    parrainage (CDC 4.3 etape 2), puis enchaine automatiquement les etapes
    3-4 (generation de la fiche PDF, notification du parrain) des que le
    montant total est atteint, et verifie le passage « Inscrit » (etape 5).

    Delegue integralement la partie tresorerie a
    ``apps.treasury.services.record_membership_fee_payment`` (interface
    livree par `finance-engine`, non modifiee ici : memes exceptions,
    meme chainage). Cette fonction ne fait qu'orchestrer la
    suite propre au dossier d'adhesion :

    1. Relie le `Payment` cree a ``application.membership_fee_payment``
       (seulement s'il n'y en avait pas encore -- un paiement partiel
       complementaire ne remplace jamais la reference du premier).
    2. Si les frais sont desormais entierement payes
       (``has_paid_membership_fee``) et que la fiche n'a pas encore ete
       generee, genere la fiche PDF puis notifie le parrain (etapes 3-4).
    3. Verifie le passage « Inscrit » (etape 5, :func:`_maybe_activate_membership`).

    Rien n'est ecrit cote dossier d'adhesion si
    ``record_membership_fee_payment`` leve une exception (memes garanties
    que ce service : role verifie avant toute ecriture).
    """

    from apps.treasury import services as treasury_services

    now = now or timezone.now()
    membership = application.membership

    # Partie atomique : dossier verrouille (filtre par club) + paiement
    # tresorerie + rattachement + journal + passage « Inscrit ». Si l'une de
    # ces etapes echoue, rien n'est ecrit (pas de paiement orphelin).
    with transaction.atomic():
        locked = MembershipApplication.all_objects.select_for_update().get(
            pk=application.pk, club_id=application.club_id
        )
        locked.membership = membership
        payment = treasury_services.record_membership_fee_payment(
            membership=membership,
            amount=amount,
            method=method,
            paid_on=paid_on,
            validated_by=validated_by,
            reference=reference,
            attachment=attachment,
            now=now,
            client_uuid=client_uuid,
        )
        is_replay = bool(getattr(payment, "idempotent_replay", False))

        # Creation : toujours journaliser. Rejeu : rattrapage seulement si le
        # paiement n'est pas encore rattache (reprise d'un etat partiel), sans
        # second journal sinon.
        if not is_replay or locked.membership_fee_payment_id is None:
            before = _application_snapshot(locked)
            if locked.membership_fee_payment_id is None:
                locked.membership_fee_payment = payment
            locked.save()
            log_action(
                actor=validated_by,
                club=locked.club,
                action_type="clubs.membership_application.fee_payment_recorded",
                obj=locked,
                before=before,
                after=_application_snapshot(locked),
            )

        application = locked
        _maybe_activate_membership(application=application, actor=validated_by, now=now)

    if is_replay:
        application.idempotent_replay = True

    # Etapes 3-4 apres validation de la transaction, tolerantes : un echec
    # (PDF, notification) ne remet pas en cause le paiement ; un rejeu avec la
    # meme cle les relance (idempotentes : fiche deja generee et parrain deja
    # notifie ne sont jamais refaits).
    if treasury_services.has_paid_membership_fee(application.membership):
        try:
            if application.generated_at is None:
                application = generate_membership_application_pdf(
                    application=application, actor=validated_by, now=now
                )
            application = notify_sponsor_for_signature(application=application, now=now)
        except Exception:  # noqa: BLE001 - rattrapable par rejeu
            logger.exception(
                "Echec apres paiement des frais d'adhesion (dossier %s) : a relancer par rejeu.",
                application.pk,
            )
    return application


def sign_sponsor_application(*, application: "MembershipApplication", sponsor_user, now=None) -> "MembershipApplication":
    """Signature du parrain (CDC 4.3 etape 4). Reserve
    au parrain reellement designe pour ce dossier -- verifie ici en plus
    du controle de vue (``IsActiveClubMember`` seulement : c'est cette
    fonction qui verifie l'identite precise, comme une action « P » de la
    matrice 2.4 -- propres donnees uniquement).

    Fait passer immediatement l'adhesion « Inscrit » si le paiement est
    deja complet (:func:`_maybe_activate_membership`). Journalise
    ``clubs.membership_application.sponsor_signed``.

    Bloque aussi bien une re-signature (``sponsor_decision == SIGNED``)
    qu'une signature apres un refus du meme parrain
    (``sponsor_decision == REFUSED``) : une fois refuse, seule une
    reassignation par le President (:func:`reassign_sponsor`) peut rouvrir
    la signature -- la decision apres un refus appartient au President,
    jamais au parrain seul (CDC 4.3, corrige en revue independante tache
    1.4bt).

    """

    membership = application.membership
    sponsor = membership.sponsor
    if sponsor is None or sponsor.user_id != getattr(sponsor_user, "id", None):
        raise PermissionError("Seul le parrain désigné pour ce dossier peut le signer.")
    if application.sponsor_decision == MembershipApplication.SponsorDecision.SIGNED:
        raise MembershipApplicationError("Ce dossier d'adhésion est déjà signé.")
    if application.sponsor_decision == MembershipApplication.SponsorDecision.REFUSED:
        raise MembershipApplicationError(
            "Ce dossier a déjà été refusé par ce parrain ; seul le Président peut "
            "désigner un autre parrain pour rouvrir la signature."
        )
    if application.generated_at is None:
        raise MembershipApplicationError(
            "La fiche d'adhésion n'a pas encore été générée : les frais d'adhésion doivent d'abord être payés."
        )

    now = now or timezone.now()
    with transaction.atomic():
        # Verrou puis re-verification : un second envoi concurrent ou rejoue
        # est rejete, une seule signature est journalisee.
        application = MembershipApplication.all_objects.select_for_update().get(
            pk=application.pk, club_id=application.club_id
        )
        if application.sponsor_decision != MembershipApplication.SponsorDecision.PENDING:
            raise MembershipApplicationError(
                "Ce dossier d'adhésion est déjà signé."
                if application.sponsor_decision == MembershipApplication.SponsorDecision.SIGNED
                else "Ce dossier a déjà été refusé par ce parrain ; seul le Président peut "
                "désigner un autre parrain pour rouvrir la signature."
            )
        before = _application_snapshot(application)
        application.sponsor_decision = MembershipApplication.SponsorDecision.SIGNED
        application.sponsor_signed_by = sponsor_user
        application.sponsor_signed_at = now
        application.resolved_at = now
        application.save()
        log_action(
            actor=sponsor_user,
            club=application.club,
            action_type="clubs.membership_application.sponsor_signed",
            obj=application,
            before=before,
            after=_application_snapshot(application),
        )

        _maybe_activate_membership(application=application, actor=sponsor_user, now=now)
    return application


def refuse_sponsor_application(
    *, application: "MembershipApplication", sponsor_user, reason: str, now=None
) -> "MembershipApplication":
    """Refus du parrain, motif obligatoire (CDC 4.3, cas limite « le
    parrain refuse »). Le President est notifie (voir
    :func:`notify_president_of_sponsor_refusal`) ; c'est ensuite a lui de
    reassigner un parrain (:func:`reassign_sponsor`) ou d'annuler
    l'adhesion (:func:`cancel_membership_application`).

    Meme controle d'identite que :func:`sign_sponsor_application`.
    Journalise ``clubs.membership_application.sponsor_refused``.
    """

    membership = application.membership
    sponsor = membership.sponsor
    if sponsor is None or sponsor.user_id != getattr(sponsor_user, "id", None):
        raise PermissionError("Seul le parrain désigné pour ce dossier peut le refuser.")
    if application.sponsor_decision != MembershipApplication.SponsorDecision.PENDING:
        raise MembershipApplicationError("Ce dossier n'est plus en attente de décision du parrain.")

    cleaned_reason = (reason or "").strip()
    if not cleaned_reason:
        raise MembershipApplicationError(
            "Un motif est obligatoire pour refuser de parrainer un joueur."
        )

    with transaction.atomic():
        # Verrou puis re-verification : signature et refus simultanes ne
        # s'ecrasent pas, une seule decision est enregistree.
        application = MembershipApplication.all_objects.select_for_update().get(
            pk=application.pk, club_id=application.club_id
        )
        if application.sponsor_decision != MembershipApplication.SponsorDecision.PENDING:
            raise MembershipApplicationError("Ce dossier n'est plus en attente de décision du parrain.")
        before = _application_snapshot(application)
        application.sponsor_decision = MembershipApplication.SponsorDecision.REFUSED
        application.sponsor_refused_reason = cleaned_reason
        application.save()
        log_action(
            actor=sponsor_user,
            club=application.club,
            action_type="clubs.membership_application.sponsor_refused",
            obj=application,
            before=before,
            after=_application_snapshot(application),
        )

    notify_president_of_sponsor_refusal(application=application)
    return application


def reassign_sponsor(
    *, application: "MembershipApplication", president_user, new_sponsor: "Membership", now=None
) -> "MembershipApplication":
    """Le President designe un nouveau parrain apres un refus (CDC 4.3,
    cas limite « le parrain refuse » : « decide de designer un autre
    parrain [...] »). Remet le dossier en attente de signature et
    redemarre le compteur de rappel/alerte (nouvelle notification, CDC
    4.3 etape 4).

    Reserve au President du club (matrice 2.4, revalide ici en defense en
    profondeur -- la vue porte deja ``IsClubPresident``).
    """

    club = application.club
    if not has_any_role(president_user, {MembershipRole.Role.PRESIDENT}, club=club):
        raise PermissionError("Seul le Président peut désigner un nouveau parrain.")
    if application.sponsor_decision != MembershipApplication.SponsorDecision.REFUSED:
        raise MembershipApplicationError(
            "Un nouveau parrain ne peut être désigné qu'après un refus du parrain actuel."
        )
    if new_sponsor.club_id != club.id:
        raise MembershipApplicationError("Le nouveau parrain doit appartenir à ce club.")
    if new_sponsor.status != Membership.Status.ACTIVE:
        raise MembershipApplicationError("Le nouveau parrain doit être un joueur inscrit du club.")

    membership = application.membership
    if new_sponsor.id == membership.id:
        raise MembershipApplicationError("Un joueur ne peut pas être son propre parrain.")

    now = now or timezone.now()

    before_membership = membership_snapshot(membership)
    membership.sponsor = new_sponsor
    membership.save()
    log_membership_updated(membership, before_membership, actor=president_user)

    before = _application_snapshot(application)
    application.sponsor_decision = MembershipApplication.SponsorDecision.PENDING
    application.sponsor_refused_reason = ""
    application.sponsor_notified_at = None
    application.sponsor_reminder_sent_at = None
    application.president_alerted_at = None
    application.save()
    log_action(
        actor=president_user,
        club=club,
        action_type="clubs.membership_application.sponsor_reassigned",
        obj=application,
        before=before,
        after=_application_snapshot(application),
    )

    notify_sponsor_for_signature(application=application, now=now)
    return application


def cancel_membership_application(
    *,
    application: "MembershipApplication",
    president_user,
    reason: str,
    disposition: str,
    now=None,
) -> "MembershipApplication":
    """Le President annule l'adhesion apres un refus du parrain (CDC 4.3,
    cas limite « le parrain refuse » : « [...] ou d'annuler l'adhesion »).

    ``Membership.status`` passe a ``DEPARTED`` (raison
    ``LeftReason.CANCELLED``) -- voir la docstring de
    ``MembershipApplication`` pour la justification de ce choix plutot
    qu'un 4e statut. Le sort du paiement (``disposition``, D9 -- a
    confirmer par le client) est un choix explicite du President a
    chaque cas, jamais une regle automatique :

    - ``FeeDisposition.REFUNDED`` : appelle
      ``apps.treasury.services.refund_membership_fee`` -- leve :class:`MembershipApplicationError` s'il
      n'y a en realite aucun paiement a rembourser ;
    - ``FeeDisposition.KEPT`` : aucune ecriture financiere.

    Reserve au President (matrice 2.4, revalide en defense en profondeur).
    Revalide aussi, en defense en profondeur, l'invariant que ce chemin
    presuppose : une adhesion deja ``Membership.Status.ACTIVE`` (« Inscrit »)
    ne peut pas etre annulee ici, meme si ``sponsor_decision`` valait
    ``REFUSED`` (etat normalement impossible via l'API reelle, mais
    revalide quand meme -- signale en revue independante tache 1.4bt).
    Journalise ``clubs.membership_application.cancelled`` (et, via le
    signal existant sur ``Membership``, ``membership.departed``).
    """

    from apps.treasury import services as treasury_services

    club = application.club
    if not has_any_role(president_user, {MembershipRole.Role.PRESIDENT}, club=club):
        raise PermissionError("Seul le Président peut annuler une adhésion.")
    cleaned_reason = (reason or "").strip()
    if not cleaned_reason:
        raise MembershipApplicationError("Un motif est obligatoire pour annuler une adhésion.")
    if disposition not in MembershipApplication.FeeDisposition.values:
        raise MembershipApplicationError(
            "Précisez le sort du paiement : remboursé ou conservé."
        )

    now = now or timezone.now()

    with transaction.atomic():
        # Verrou sur le dossier : deux annulations concurrentes (ou rejouees)
        # ne peuvent pas rembourser/journaliser deux fois. Toutes les
        # verifications d'etat sont refaites APRES le verrou.
        application = MembershipApplication.all_objects.select_for_update().get(
            pk=application.pk, club_id=club.id
        )
        if application.cancelled_by_id is not None:
            raise MembershipApplicationError("Cette adhésion a déjà été annulée.")
        if application.sponsor_decision != MembershipApplication.SponsorDecision.REFUSED:
            raise MembershipApplicationError(
                "Une adhésion ne peut être annulée ici qu'après un refus du parrain."
            )
        membership = Membership.all_objects.get(pk=application.membership_id, club_id=club.id)
        if membership.status == Membership.Status.ACTIVE:
            raise MembershipApplicationError(
                "Une adhésion déjà validée (joueur inscrit) ne peut pas être annulée ici."
            )

        fee_paid = treasury_services.has_paid_membership_fee(membership)
        if disposition == MembershipApplication.FeeDisposition.REFUNDED:
            if not fee_paid:
                raise MembershipApplicationError("Aucun paiement de frais d'adhésion à rembourser pour ce joueur.")
            treasury_services.refund_membership_fee(
                membership=membership, reason=cleaned_reason, president=president_user, now=now
            )
        # Decision du client du 17/11/2026 : le du d'adhesion d'une adhesion
        # annulee est neutralise par une ecriture d'annulation (jamais
        # supprime), sauf si les frais entierement payes sont conserves par
        # le club (le du reste alors couvert par le paiement, solde a 0).
        if disposition == MembershipApplication.FeeDisposition.REFUNDED or not fee_paid:
            treasury_services.cancel_membership_fee_due(
                membership=membership,
                reason=f"Adhésion annulée : {cleaned_reason}",
                cancelled_by=president_user,
                now=now,
            )

        membership.status = Membership.Status.DEPARTED
        membership.left_on = now.date()
        membership.left_reason = Membership.LeftReason.CANCELLED
        membership.left_by = president_user
        membership.save()  # journalise automatiquement (signal, tache 1.6 -- log_membership_departed)

        before = _application_snapshot(application)
        application.cancelled_by = president_user
        application.cancelled_reason = cleaned_reason
        application.membership_fee_disposition = disposition
        application.resolved_at = now
        application.save()
        log_action(
            actor=president_user,
            club=club,
            action_type="clubs.membership_application.cancelled",
            obj=application,
            before=before,
            after=_application_snapshot(application),
        )

    return application


def process_sponsor_reminders_and_alerts(*, now=None) -> dict[str, int]:
    """Rappel a 3 jours, alerte au President a 7 jours (CDC 4.3, cas limite
    « le parrain ne repond pas »). Idempotente : ne pose chaque
    horodatage qu'une seule fois par dossier, quel que soit le nombre
    d'appels (a rappeler par une commande de gestion, elle-meme appelee
    par le cron -- CLAUDE.md : pas de tache longue dans une requete, pas
    de processus permanent).

    Parcourt tous les clubs (``all_objects`` : usage explicitement
    multi-clubs, legitime pour une commande de gestion -- CLAUDE.md
    regle n8).

    Ne journalise pas ces deux horodatages : il n'y a ici aucun acteur
    reel (CDC 5.1 exige une identite reelle, y compris en Ghost Mode) --
    seulement une echeance de temps ecoulee, declenchee par le cron. Point
    ouvert signale au compte rendu, meme principe que les autres taches
    automatisees sans acteur humain (ex. verification quotidienne de la
    chaine financiere, laissee ouverte par `finance-engine`).
    """

    now = now or timezone.now()
    reminder_threshold = now - SPONSOR_REMINDER_DELAY
    alert_threshold = now - PRESIDENT_ALERT_DELAY

    pending_qs = MembershipApplication.all_objects.filter(
        sponsor_decision=MembershipApplication.SponsorDecision.PENDING,
        sponsor_notified_at__isnull=False,
    )

    reminders_sent = 0
    for application in pending_qs.filter(
        sponsor_notified_at__lte=reminder_threshold, sponsor_reminder_sent_at__isnull=True
    ):
        application.sponsor_reminder_sent_at = now
        application.save()
        notify_sponsor(application=application)
        reminders_sent += 1

    alerts_sent = 0
    for application in pending_qs.filter(
        sponsor_notified_at__lte=alert_threshold, president_alerted_at__isnull=True
    ):
        application.president_alerted_at = now
        application.save()
        notify_president_of_no_response(application=application)
        alerts_sent += 1

    return {"reminders_sent": reminders_sent, "alerts_sent": alerts_sent}


# ---------------------------------------------------------------------------
# Identite du club (CDC 3.5 ; club-comite-bureau.md §4.1 ; tache 1.9)
# ---------------------------------------------------------------------------
#
# Seule piece manquante identifiee par la tache 1.9 pour cet ecran : la
# nomination des roles, le transfert de presidence, le reglage des sieges
# du bureau et l'ajout/import de joueurs existent deja plus haut dans ce
# fichier (taches 1.4-1.5). Import tardif de `apps.treasury.models.Payment`
# (meme prudence que le reste de ce module pour `finance-engine`, voir le
# commentaire en tete de fichier) : seul point de couplage avec la
# tresorerie, une simple lecture d'existence, jamais une regle financiere.


def club_has_payments(club: "Club") -> bool:
    """Vrai si au moins un paiement existe pour ce club, tous statuts
    confondus (CDC 4.1 : la devise ne peut plus etre changee une fois des
    paiements enregistres -- point ouvert de club-comite-bureau.md §7,
    defaut d'interface applique ici, a confirmer avec `finance-engine`).

    ``all_objects`` (non filtre) : usage legitime, ce controle ne depend
    jamais d'un « club actif » de la requete courante -- il porte
    explicitement sur ``club``, quel qu'il soit (CLAUDE.md regle n8).
    """

    from apps.treasury.models import Payment

    return Payment.all_objects.filter(club=club).exists()


class ClubIdentityError(Exception):
    """Erreur metier de la modale « Identite du club » (club-comite-bureau.md
    §4.1), message en francais clair destine a une reponse HTTP."""


_NOT_PROVIDED = object()


def _club_identity_snapshot(club: "Club", club_settings: "ClubSettings") -> dict[str, Any]:
    return {
        "name": club.name,
        "city": club.city,
        "country": club.country,
        "primary_color": club.primary_color,
        "secondary_color": club.secondary_color,
        "currency": club_settings.currency,
        "timezone": club_settings.timezone,
        "payment_link_url": club_settings.payment_link_url,
        "debt_tolerance_days": club_settings.debt_tolerance_days,
    }


#: Bornes de la tolérance de dette (jours) configurable par le club (CDC 4.4.2).
DEBT_TOLERANCE_MIN_DAYS = 0
DEBT_TOLERANCE_MAX_DAYS = 90


def update_club_identity(
    *,
    president_user,
    club: "Club",
    name=_NOT_PROVIDED,
    logo=_NOT_PROVIDED,
    primary_color=_NOT_PROVIDED,
    secondary_color=_NOT_PROVIDED,
    city=_NOT_PROVIDED,
    country=_NOT_PROVIDED,
    currency=_NOT_PROVIDED,
    timezone=_NOT_PROVIDED,
    payment_link_url=_NOT_PROVIDED,
    debt_tolerance_days=_NOT_PROVIDED,
) -> "Club":
    """Modifie l'identite du club (nom, logo, couleurs, ville, pays,
    devise, fuseau, lien de paiement -- club-comite-bureau.md §4.1).
    Reserve au President (matrice 2.4, colonne « Identite du club » : « É »
    Pdt, « L » pour les autres).

    Mise a jour partielle : seuls les parametres explicitement fournis
    (differents du sentinel ``_NOT_PROVIDED``) sont modifies -- un champ
    omis du corps de la requete PATCH n'efface jamais une valeur
    existante.

    Leve :class:`ClubIdentityError` si ``currency`` est fourni et differe
    de la devise actuelle alors que des paiements existent deja pour ce
    club (CDC 4.1, point ouvert applique par defaut : lecture seule des
    que des paiements existent -- voir :func:`club_has_payments`).
    """

    if not has_any_role(president_user, {MembershipRole.Role.PRESIDENT}, club=club):
        raise PermissionError("Réservé au Président du club.")

    club_settings = club.settings
    before = {**_club_identity_snapshot(club, club_settings), "logo": bool(club.logo)}

    if currency is not _NOT_PROVIDED and currency != club_settings.currency and club_has_payments(club):
        raise ClubIdentityError(
            "La devise ne peut plus être changée : des paiements existent déjà pour ce club."
        )

    if debt_tolerance_days is not _NOT_PROVIDED and not (
        DEBT_TOLERANCE_MIN_DAYS <= debt_tolerance_days <= DEBT_TOLERANCE_MAX_DAYS
    ):
        raise ClubIdentityError(
            f"La tolérance de dette doit être comprise entre {DEBT_TOLERANCE_MIN_DAYS} "
            f"et {DEBT_TOLERANCE_MAX_DAYS} jours."
        )

    if name is not _NOT_PROVIDED:
        club.name = name
    if logo is not _NOT_PROVIDED:
        club.logo = logo
    if primary_color is not _NOT_PROVIDED:
        club.primary_color = primary_color
    if secondary_color is not _NOT_PROVIDED:
        club.secondary_color = secondary_color
    if city is not _NOT_PROVIDED:
        club.city = city
    if country is not _NOT_PROVIDED:
        club.country = country
    club.save()  # full_clean() (Club.save() l'appelle toujours)

    if currency is not _NOT_PROVIDED:
        club_settings.currency = currency
    if timezone is not _NOT_PROVIDED:
        club_settings.timezone = timezone
    if payment_link_url is not _NOT_PROVIDED:
        club_settings.payment_link_url = payment_link_url
    if debt_tolerance_days is not _NOT_PROVIDED:
        club_settings.debt_tolerance_days = debt_tolerance_days
    club_settings.updated_by = president_user
    club_settings.full_clean()
    club_settings.save()

    after = {**_club_identity_snapshot(club, club_settings), "logo": bool(club.logo)}
    log_action(
        actor=president_user,
        club=club,
        action_type="clubs.identity.updated",
        obj=club,
        before=before,
        after=after,
    )

    return club
