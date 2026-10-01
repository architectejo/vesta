"""Vues DRF de l'app mercato (CDC 4.14 ; fiche d'écran mercato.md).

Orchestration uniquement (permission -> service -> serializer, CLAUDE.md
section 5). **Étanchéité entre clubs (§2.1, point de vigilance n° 1)** :
toute lecture qui traverse deux clubs passe par
``apps.mercato.serializers.serialize_public_player``/``serialize_offer``,
jamais par un serializer interne au club qui exposerait des champs
privés.
"""

from __future__ import annotations

import os

from django.http import FileResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clubs.models import Club, Membership, MembershipRole
from apps.clubs.permissions import IsActiveClubMember
from apps.core.permissions import HasAcceptedLatestTerms, HasCompletedPasswordSetup, HasUsableLicence
from apps.core.roles import has_any_role
from apps.core.services import resolve_active_membership
from apps.core.tenant import NoActiveClubError, get_active_club
from apps.mercato import serializers as ser
from apps.mercato import services
from apps.mercato.models import MercatoMessage, MercatoThread, TransferOffer
from apps.mercato.permissions import CanMakeOfferOrMessage, CanReadMarket, MARKET_READER_ROLES

_GATE = [IsAuthenticated, HasCompletedPasswordSetup, HasAcceptedLatestTerms, HasUsableLicence]


def _error(exc) -> Response:
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _active_membership(request):
    try:
        return resolve_active_membership(request.user, club=get_active_club())
    except NoActiveClubError:
        return None


# ---------------------------------------------------------------------------
# Ma disponibilité
# ---------------------------------------------------------------------------


class AvailabilityView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        membership = _active_membership(request)
        return Response({"is_on_transfer_market": membership.is_on_transfer_market})

    def patch(self, request):
        membership = _active_membership(request)
        serializer = ser.AvailabilityInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            membership = services.set_market_availability(
                membership=membership, actor=request.user, is_on_market=serializer.validated_data["is_on_transfer_market"]
            )
        except services.MercatoError as exc:
            return _error(exc)
        return Response({"is_on_transfer_market": membership.is_on_transfer_market})


# ---------------------------------------------------------------------------
# Marché (tous les clubs Vesta)
# ---------------------------------------------------------------------------


class MarketListView(APIView):
    permission_classes = _GATE + [CanReadMarket]

    def get(self, request):
        club = get_active_club()
        queryset = Membership.all_objects.filter(
            is_on_transfer_market=True, status=Membership.Status.ACTIVE
        ).select_related("user", "club")

        position = request.query_params.get("position")
        if position:
            queryset = queryset.filter(position=position)
        club_id = request.query_params.get("club")
        if club_id:
            queryset = queryset.filter(club_id=club_id)
        search = request.query_params.get("search")
        if search:
            from django.db.models import Q

            queryset = queryset.filter(Q(user__first_name__icontains=search) | Q(user__last_name__icontains=search))

        data = [ser.serialize_market_row(m, viewer_club=club) for m in queryset.order_by("user__last_name")[:200]]
        return Response({"count": len(data), "results": data})


class PublicPlayerDetailView(APIView):
    permission_classes = _GATE + [CanReadMarket]

    def get(self, request, membership_id: int):
        club = get_active_club()
        membership = Membership.all_objects.select_related("user", "club").filter(pk=membership_id).first()
        if membership is None:
            return Response({"detail": "Ce joueur n'existe pas."}, status=status.HTTP_404_NOT_FOUND)
        if not membership.is_on_transfer_market and membership.club_id != club.id:
            return Response({"detail": "Ce joueur n'existe pas."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ser.serialize_public_player(membership, request=request))


# ---------------------------------------------------------------------------
# Offres de transfert
# ---------------------------------------------------------------------------


class OfferCreateView(APIView):
    permission_classes = _GATE + [CanMakeOfferOrMessage]

    def post(self, request):
        serializer = ser.OfferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_membership = Membership.all_objects.select_related("user", "club").filter(
            pk=serializer.validated_data["target_membership_id"]
        ).first()
        if target_membership is None:
            return Response({"detail": "Choisissez un joueur."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            offer = services.create_transfer_offer(
                initiated_by=request.user,
                target_club=get_active_club(),
                target_membership=target_membership,
                message=serializer.validated_data["message"],
                conditions=serializer.validated_data.get("conditions", ""),
            )
        except services.MercatoError as exc:
            return _error(exc)
        return Response(
            ser.serialize_offer(offer, viewer=request.user, viewer_club=get_active_club()), status=status.HTTP_201_CREATED
        )


class MyOffersView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        membership = _active_membership(request)
        offers = TransferOffer.objects.filter(target_membership=membership).order_by("-created_at")
        data = [ser.serialize_offer(o, viewer=request.user, viewer_club=get_active_club()) for o in offers]
        return Response({"count": len(data), "results": data})


class ClubOffersView(APIView):
    permission_classes = _GATE + [CanReadMarket]

    def get(self, request):
        club = get_active_club()
        direction = request.query_params.get("direction", "sent")
        if direction == "received":
            offers = TransferOffer.objects.filter(origin_club=club)
        else:
            offers = TransferOffer.objects.filter(target_club=club)
        status_filter = request.query_params.get("status")
        if status_filter:
            offers = offers.filter(status=status_filter)
        offers = offers.order_by("-created_at")
        data = [ser.serialize_offer(o, viewer=request.user, viewer_club=club) for o in offers]
        return Response({"count": len(data), "results": data})


def _offer_visible_to(user, club, offer: TransferOffer) -> bool:
    if offer.target_membership.user_id == getattr(user, "id", None):
        return True
    return has_any_role(user, MARKET_READER_ROLES, club=offer.origin_club) or has_any_role(
        user, MARKET_READER_ROLES, club=offer.target_club
    )


class OfferDetailView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk: int):
        offer = TransferOffer.objects.select_related(
            "origin_club", "target_club", "target_membership__user", "initiated_by"
        ).filter(pk=pk).first()
        if offer is None or not _offer_visible_to(request.user, get_active_club(), offer):
            return Response({"detail": "Cet élément n'existe plus."}, status=status.HTTP_404_NOT_FOUND)
        # §5.1 : relecture à chaque ouverture de la modale -- débloque
        # automatiquement si le solde est redevenu bon (10.2 n° 30).
        if offer.status == TransferOffer.Status.BLOCKED_DEBT:
            offer = services.recheck_transfer_offer(offer)
        return Response(ser.serialize_offer(offer, viewer=request.user, viewer_club=get_active_club()))


class OfferRespondView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def post(self, request, pk: int):
        offer = TransferOffer.objects.select_related("target_membership__user", "origin_club", "target_club").filter(pk=pk).first()
        if offer is None:
            return Response({"detail": "Cet élément n'existe plus."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ser.OfferResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            offer = services.respond_to_offer(offer=offer, actor=request.user, accept=serializer.validated_data["accept"])
        except services.MercatoError as exc:
            return _error(exc)
        return Response(ser.serialize_offer(offer, viewer=request.user, viewer_club=get_active_club()))


class OfferQuitusDownloadView(APIView):
    """Téléchargement authentifié du quitus (CDC 6.7 ; point ouvert n° 7,
    proposition : le joueur, le Président et le Trésorier du club A, le
    Président et le DS du club B)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk: int):
        offer = TransferOffer.objects.select_related("origin_club", "target_club", "target_membership__user").filter(pk=pk).first()
        if offer is None or not offer.quitus_file:
            return Response({"detail": "Ce quitus n'est pas disponible."}, status=status.HTTP_404_NOT_FOUND)
        user = request.user
        allowed = offer.target_membership.user_id == user.id
        allowed = allowed or has_any_role(
            user, {MembershipRole.Role.PRESIDENT, MembershipRole.Role.TREASURER}, club=offer.origin_club
        )
        allowed = allowed or has_any_role(
            user, {MembershipRole.Role.PRESIDENT, MembershipRole.Role.SPORTS_DIRECTOR}, club=offer.target_club
        )
        if not allowed:
            return Response({"detail": "Vous n'avez pas accès à cette action."}, status=status.HTTP_403_FORBIDDEN)
        # Reprend le nom de fichier reellement stocke a la generation
        # (`apps.mercato.services.complete_transfer`, gabarit §2.1 : ASCII,
        # sans accents ni espaces) plutot que d'en recalculer un ici --
        # une seule source pour ce format, jamais deux qui pourraient
        # diverger.
        filename = os.path.basename(offer.quitus_file.name) or f"quitus-{offer.pk}.pdf"
        return FileResponse(offer.quitus_file.open("rb"), as_attachment=True, filename=filename)


# ---------------------------------------------------------------------------
# Messagerie entre clubs (Président/DS seulement, voir apps.mercato.models)
# ---------------------------------------------------------------------------


class ThreadListCreateView(APIView):
    permission_classes = _GATE + [CanMakeOfferOrMessage]

    def get(self, request):
        club = get_active_club()
        threads = services.threads_visible_to(request.user, club)
        data = [ser.serialize_thread(t, viewer_club_id=club.id) for t in threads]
        return Response({"count": len(data), "results": data})

    def post(self, request):
        serializer = ser.ThreadCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        club = get_active_club()
        other_club = Club.objects.filter(pk=serializer.validated_data["club_id"]).exclude(pk=club.id).first()
        if other_club is None:
            return Response({"detail": "Choisissez un club."}, status=status.HTTP_400_BAD_REQUEST)
        transfer_offer = None
        offer_id = serializer.validated_data.get("transfer_offer_id")
        if offer_id:
            transfer_offer = TransferOffer.objects.filter(pk=offer_id).first()
        thread = services.get_or_create_thread(club_a=club, club_b=other_club, subject=serializer.validated_data.get("subject", ""), transfer_offer=transfer_offer)
        try:
            services.send_message(thread=thread, actor=request.user, club=club, body=serializer.validated_data["message"])
        except services.MercatoError as exc:
            return _error(exc)
        return Response(ser.serialize_thread(thread, viewer_club_id=club.id), status=status.HTTP_201_CREATED)


class ThreadMessagesView(APIView):
    permission_classes = _GATE + [CanMakeOfferOrMessage]

    def _get_thread(self, pk, club):
        thread = MercatoThread.objects.filter(pk=pk).first()
        if thread is None or club.id not in (thread.club_a_id, thread.club_b_id):
            return None
        return thread

    def get(self, request, pk: int):
        club = get_active_club()
        thread = self._get_thread(pk, club)
        if thread is None:
            return Response({"detail": "Ce fil n'existe pas."}, status=status.HTTP_404_NOT_FOUND)
        services.mark_thread_read(thread=thread, user=request.user, club=club)
        messages = MercatoMessage.objects.filter(thread=thread).select_related("sender").order_by("sent_at")
        return Response({"results": [ser.serialize_message(m) for m in messages]})

    def post(self, request, pk: int):
        club = get_active_club()
        thread = self._get_thread(pk, club)
        if thread is None:
            return Response({"detail": "Ce fil n'existe pas."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ser.MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            message = services.send_message(thread=thread, actor=request.user, club=club, body=serializer.validated_data["body"])
        except services.MercatoError as exc:
            return _error(exc)
        return Response(ser.serialize_message(message), status=status.HTTP_201_CREATED)
