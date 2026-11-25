"""Vues DRF de l'app notifications (CDC 3.4, 4.17 ; tache 1.7).

Orchestrent uniquement : permission -> service -> serializer (CLAUDE.md
section 5). Prepare l'ecran de la tache 1.9 (icone cloche, onglet
« Informations » de la modale Mon profil) -- l'ecran lui-meme est hors
perimetre de cette tache.

Isolation (consigne explicite de la tache 1.7) : la lecture d'une
notification par son destinataire ne fuite JAMAIS vers un autre
utilisateur. Chaque vue filtre systematiquement sur
``recipient=request.user`` -- jamais par club actif, jamais par un autre
mecanisme (``Notification`` n'est pas un ``TenantModel``, voir sa
docstring).
"""

from __future__ import annotations

from rest_framework import status
from django.http import Http404
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import HasAcceptedLatestTerms, HasCompletedPasswordSetup, HasUsableLicence
from apps.notifications import services as notification_services
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationPreferenceSerializer, NotificationSerializer

_GATE = [IsAuthenticated, HasCompletedPasswordSetup, HasAcceptedLatestTerms, HasUsableLicence]


class NotificationPagination(PageNumberPagination):
    """« 10 dernieres + Voir plus » (CDC 3.4, 4.17)."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class NotificationListView(ListAPIView):
    """Liste des notifications du joueur connecte, les plus recentes
    d'abord (CDC 4.17). Jamais affichee sur la page d'accueil (CDC 4.17) :
    reserve a la modale de l'icone cloche, hors perimetre de cette tache."""

    permission_classes = _GATE
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)


class NotificationUnreadCountView(APIView):
    """Compteur de non-lues affiche sur l'icone cloche (CDC 4.17)."""

    permission_classes = _GATE

    def get(self, request):
        return Response({"unread_count": notification_services.unread_count(user=request.user)})


class NotificationMarkReadView(APIView):
    """Marque une notification comme lue (clic dans la liste, CDC 4.17).

    Ne recherche que parmi les notifications DU DEMANDEUR : une
    notification d'un autre utilisateur repond 404, jamais 403 (aucune
    fuite d'existence d'une notification d'un tiers)."""

    permission_classes = _GATE

    def post(self, request, notification_id: int):
        try:
            notification = get_object_or_404(
                Notification, pk=notification_id, recipient=request.user
            )
        except Http404:
            return Response(
                {"detail": "Cette notification n'existe pas."}, status=status.HTTP_404_NOT_FOUND
            )
        notification_services.mark_notification_read(notification=notification, user=request.user)
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadView(APIView):
    """« Tout marquer comme lu » (CDC 4.17)."""

    permission_classes = _GATE

    def post(self, request):
        updated = notification_services.mark_all_notifications_read(user=request.user)
        return Response({"updated": updated}, status=status.HTTP_200_OK)


class NotificationPreferenceView(APIView):
    """Lecture/modification de la preference email globale (CDC 4.17 :
    « Chaque utilisateur choisit s'il recoit aussi les notifications par
    email »). Consommee par l'onglet « Informations » de la modale Mon
    profil (tache 1.9)."""

    permission_classes = _GATE

    def get(self, request):
        preference = notification_services.get_or_create_preference(request.user)
        return Response(NotificationPreferenceSerializer(preference).data)

    def patch(self, request):
        serializer = NotificationPreferenceSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        preference = notification_services.set_email_preference(
            user=request.user,
            email_enabled=serializer.validated_data.get(
                "email_enabled",
                notification_services.get_or_create_preference(request.user).email_enabled,
            ),
        )
        return Response(NotificationPreferenceSerializer(preference).data)
