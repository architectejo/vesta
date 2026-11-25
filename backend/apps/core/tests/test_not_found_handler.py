"""404 génériques de Django/DRF : toujours en français (troisième série de tests, 15/11/2026)."""

from __future__ import annotations

import pytest
from django.http import Http404
from rest_framework.exceptions import NotFound
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Club
from apps.logistics.models import Article
from apps.notifications.models import Notification
from apps.sport.models import Match
from apps.treasury.models import Expense

pytestmark = pytest.mark.django_db

GENERIC = "Cet élément n'existe pas."


def _view_raising(exc_factory):
    class _View(APIView):
        permission_classes: list = []
        authentication_classes: list = []

        def get(self, request):
            raise exc_factory()

    return _View.as_view()


def _call(view):
    response = view(APIRequestFactory().get("/x/"))
    response.render()
    return response


@pytest.mark.parametrize("model", [Notification, Club, Article, Match, Expense])
def test_get_object_or_404_drf_sans_message_renvoie_le_message_generique_francais(model):
    response = _call(_view_raising(lambda: Http404(f"No {model.__name__} matches the given query.")))

    assert response.status_code == 404
    assert response.data["detail"] == GENERIC
    assert "matches" not in response.content.decode()


def test_get_object_or_404_reel_sur_plusieurs_modules():
    for model in (Notification, Club, Article, Match, Expense):

        class _View(APIView):
            permission_classes: list = []
            authentication_classes: list = []
            target = model

            def get(self, request):
                manager = getattr(self.target, "all_objects", self.target._default_manager)
                get_object_or_404(manager.all(), pk=987654)
                return Response({})

        response = _call(_View.as_view())
        assert response.status_code == 404, model
        assert response.data["detail"] == GENERIC, model


def test_not_found_drf_par_defaut_est_traduit():
    response = _call(_view_raising(NotFound))

    assert response.status_code == 404
    assert response.data["detail"] == GENERIC


def test_un_message_francais_precis_n_est_jamais_ecrase():
    http404 = _call(_view_raising(lambda: Http404("Cette assemblée n'existe pas dans ce club.")))
    not_found = _call(_view_raising(lambda: NotFound("Ce joueur n'existe pas dans ce club.")))

    assert http404.data["detail"] == "Cette assemblée n'existe pas dans ce club."
    assert not_found.data["detail"] == "Ce joueur n'existe pas dans ce club."


def test_endpoint_reel_notification_inexistante():
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    from django.urls import reverse

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(UserFactory()).access_token}")

    response = client.post(reverse("notifications:mark-read", kwargs={"notification_id": 424242}))

    assert response.status_code == 404
    assert response.data["detail"] == "Cette notification n'existe pas."
