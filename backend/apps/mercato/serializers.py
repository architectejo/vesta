"""Serializers DRF de l'app mercato (CDC 4.14 ; fiche d'écran mercato.md).

**Point de vigilance n° 1 (étanchéité, §2.1) : seuls les champs listés ici
sont exposés pour un joueur d'un AUTRE club.** Jamais le poids, la
taille, le téléphone, l'email, une donnée financière ou médicale, ni le
commentaire d'une évaluation. La date de naissance n'est jamais exposée,
seul l'âge calculé l'est.

Périmètre volontairement réduit de la « Fiche publique » (§4.1) à cette
tâche : seul l'onglet « Aperçu » (identité, poste, note moyenne) est
câblé. Les onglets Statistiques/Présences/Discipline/Carrière dépendent
d'agrégations déjà exposées ailleurs (apps.sport) et sont laissés en
point ouvert au compte rendu plutôt que dupliqués ou approximés ici. Pas
d'onglet « Aptitude » pour un joueur d'un autre club (point ouvert n° 1
de la fiche d'écran, déjà tranché à titre provisoire : aucune donnée de
santé n'est exposée entre clubs, 10.2 n° 16).
"""

from __future__ import annotations

import datetime

from rest_framework import serializers

from apps.mercato.models import MercatoMessage, MercatoThread, TransferOffer

__all__ = [
    "AvailabilityInputSerializer",
    "OfferCreateSerializer",
    "OfferResponseSerializer",
    "MessageCreateSerializer",
    "ThreadCreateSerializer",
    "serialize_public_player",
    "serialize_market_row",
    "serialize_offer",
    "serialize_thread",
    "serialize_message",
]


def _age(birth_date) -> int | None:
    if birth_date is None:
        return None
    today = datetime.date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def _club_brief(club) -> dict:
    return {
        "id": club.id,
        "name": club.name,
        "logo": club.logo.url if club.logo else None,
    }


def _average_rating(membership) -> str | None:
    from apps.sport.models import Evaluation

    scores = list(Evaluation.all_objects.filter(membership=membership).values_list("overall_score", flat=True))
    if not scores:
        return None
    return str(round(sum(scores) / len(scores), 1))


def serialize_public_player(membership, *, request=None) -> dict:
    """Champs publics autorisés entre clubs (§2.1 point 1). Jamais de champ
    financier, médical, ni la date de naissance elle-même."""

    user = membership.user
    photo_url = None
    if user.photo:
        photo_url = request.build_absolute_uri(user.photo.url) if request is not None else user.photo.url
    return {
        "membership_id": membership.pk,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "photo": photo_url,
        "position": membership.position,
        "position_label": membership.get_position_display() if membership.position else "",
        "jersey_number": membership.jersey_number,
        "age": _age(user.birth_date),
        "club": _club_brief(membership.club),
        "average_rating": _average_rating(membership),
        "is_on_transfer_market": membership.is_on_transfer_market,
    }


def serialize_market_row(membership, *, viewer_club) -> dict:
    data = serialize_public_player(membership)
    data["city"] = membership.club.city
    data["is_own_club"] = membership.club_id == getattr(viewer_club, "id", None)
    return data


# ---------------------------------------------------------------------------
# Formulaires
# ---------------------------------------------------------------------------


class AvailabilityInputSerializer(serializers.Serializer):
    is_on_transfer_market = serializers.BooleanField()


class OfferCreateSerializer(serializers.Serializer):
    target_membership_id = serializers.IntegerField()
    message = serializers.CharField(max_length=1000)
    conditions = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class OfferResponseSerializer(serializers.Serializer):
    accept = serializers.BooleanField()


class ThreadCreateSerializer(serializers.Serializer):
    club_id = serializers.IntegerField()
    subject = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    message = serializers.CharField(max_length=2000)
    transfer_offer_id = serializers.IntegerField(required=False, allow_null=True)


class MessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=2000)


# ---------------------------------------------------------------------------
# Représentations en lecture
# ---------------------------------------------------------------------------


def sees_transfer_debt(offer: TransferOffer, *, viewer, viewer_club) -> bool:
    """Le lecteur a-t-il droit à l'information financière d'une offre bloquée
    (statut « Bloquée (dette) », montant, date de relecture du solde) ?

    Oui seulement pour le joueur concerné et, côté club d'origine (A), pour
    les rôles qui ont accès aux finances dans la matrice 2.4 : Président, VP,
    Trésorier (rôles cumulables : un Coach qui est aussi Trésorier y a
    droit). Jamais le Directeur sportif, le Coach ni l'Assistant du Coach du
    club A (CDC 10.3 n° 188 ; fiche mercato §5.3, point ouvert n° 3), jamais
    le club B (§2.1 point 2, point ouvert n° 2)."""

    from apps.clubs.models import MembershipRole
    from apps.core.roles import has_any_role

    if offer.target_membership.user_id == getattr(viewer, "id", None):
        return True
    if getattr(viewer_club, "id", None) != offer.origin_club_id:
        return False
    finance_roles = {
        MembershipRole.Role.PRESIDENT,
        MembershipRole.Role.VICE_PRESIDENT,
        MembershipRole.Role.TREASURER,
    }
    return has_any_role(viewer, finance_roles, club=viewer_club)


def _offer_status_for_viewer(offer: TransferOffer, *, sees_debt: bool) -> str:
    """Un lecteur sans droit à l'information financière (club B, et DS /
    Coach / Assistant du club A) ne voit jamais « Bloquée (dette) » : il voit
    « Quitus en attente » (``awaiting_quitus``), sans montant ni mention de
    dette (§2.1 point 2, §5.3, §8 de la fiche d'écran ; CDC 10.3 n° 188 --
    l'API choisit la clé, jamais l'interface)."""

    if offer.status == TransferOffer.Status.BLOCKED_DEBT and not sees_debt:
        return "awaiting_quitus"
    return offer.status


def serialize_offer(offer: TransferOffer, *, viewer, viewer_club) -> dict:
    sees_debt = sees_transfer_debt(offer, viewer=viewer, viewer_club=viewer_club)
    blocked = offer.status == TransferOffer.Status.BLOCKED_DEBT
    # Montant et date de relecture du solde : seulement pour qui voit la
    # dette (joueur ; Pdt/VP/Trés du club A). Pour les autres, une offre
    # bloquée ne laisse filtrer aucune donnée financière.
    show_amount = blocked and sees_debt

    return {
        "id": offer.pk,
        "status": _offer_status_for_viewer(offer, sees_debt=sees_debt),
        "origin_club": _club_brief(offer.origin_club),
        "target_club": _club_brief(offer.target_club),
        "player": serialize_public_player(offer.target_membership),
        "message": offer.message,
        "conditions": offer.conditions,
        "membership_fee_due_at_target": offer.membership_fee_due_at_target,
        "debt_amount": str(offer.debt_amount) if (show_amount and offer.debt_amount is not None) else None,
        "debt_checked_at": offer.debt_checked_at if (sees_debt or not blocked) else None,
        "player_decision_at": offer.player_decision_at,
        "quitus_available": bool(offer.quitus_file),
        "completed_at": offer.completed_at,
        "created_at": offer.created_at,
    }


def serialize_thread(thread: MercatoThread, *, viewer_club_id: int) -> dict:
    other = thread.club_b if viewer_club_id == thread.club_a_id else thread.club_a
    unread = MercatoMessage.objects.filter(thread=thread, read_at__isnull=True).exclude(club_id=viewer_club_id).count()
    return {
        "id": thread.pk,
        "other_club": _club_brief(other),
        "subject": thread.subject,
        "transfer_offer_id": thread.transfer_offer_id,
        "unread_count": unread,
        "created_at": thread.created_at,
    }


def serialize_message(message: MercatoMessage) -> dict:
    return {
        "id": message.pk,
        "club_id": message.club_id,
        "sender": {"id": message.sender_id, "name": f"{message.sender.first_name} {message.sender.last_name}".strip()},
        "body": message.body,
        "sent_at": message.sent_at,
        "read_at": message.read_at,
    }
