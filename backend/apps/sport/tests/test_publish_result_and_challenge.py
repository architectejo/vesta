"""Publication du résultat sur le fil (CDC 4.8) et garde-fous des défis."""

from __future__ import annotations

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.audit.models import AuditLog
from apps.social.models import Post
from apps.sport.models import Match
from apps.sport.tests.conftest import client_for
from apps.sport.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


def _finished_match(ctx, *, with_score=True):
    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    match = MatchFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday
    )
    if with_score:
        # Score saisi le jour du match (avant minuit), puis la date passe :
        # le score est désormais verrouillé mais le résultat reste publiable.
        from apps.sport import services

        match.event.event_date = services._club_today(ctx.club)
        match.event.save()
        resp = client_for(ctx.coach.user).post(
            reverse("sport:match-score", args=[match.pk]), {"score_home": 3, "score_away": 1}
        )
        assert resp.status_code == status.HTTP_200_OK
        match.event.event_date = yesterday
        match.event.save()
    return match


def _url(match):
    return reverse("sport:match-publish-result", args=[match.pk])


def test_le_detail_expose_result_published_faux_par_defaut(ctx):
    match = _finished_match(ctx)

    detail = client_for(ctx.coach.user).get(reverse("sport:match-detail", args=[match.pk]))

    assert detail.data["result_published"] is False


def test_le_coach_publie_le_resultat_en_visibilite_club(ctx):
    match = _finished_match(ctx)

    response = client_for(ctx.coach.user).post(_url(match))

    assert response.status_code == status.HTTP_200_OK, response.data
    assert response.data["result_published"] is True
    post = Post.all_objects.get(club=ctx.club, post_kind=Post.PostKind.AUTO_RESULT)
    assert post.visibility == Post.Visibility.CLUB_ONLY
    assert "3" in post.body and "1" in post.body
    assert AuditLog.objects.filter(club=ctx.club, action_type="sport.match_result_published").exists()


def test_une_seule_publication_par_match(ctx):
    match = _finished_match(ctx)
    client_for(ctx.coach.user).post(_url(match))

    second = client_for(ctx.coach.user).post(_url(match))

    assert second.status_code == status.HTTP_400_BAD_REQUEST
    assert "déjà" in second.data["detail"]
    assert Post.all_objects.filter(club=ctx.club, post_kind=Post.PostKind.AUTO_RESULT).count() == 1


def test_refuse_sans_score(ctx):
    match = _finished_match(ctx, with_score=False)

    response = client_for(ctx.coach.user).post(_url(match))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "score" in response.data["detail"].lower()
    assert not Post.all_objects.filter(club=ctx.club).exists()


def test_refuse_si_le_match_n_est_pas_termine(ctx):
    tomorrow = timezone.now().date() + datetime.timedelta(days=1)
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=tomorrow)
    client_for(ctx.coach.user).post(reverse("sport:match-score", args=[match.pk]), {"score_home": 1, "score_away": 0})

    response = client_for(ctx.coach.user).post(_url(match))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "terminé" in response.data["detail"]


@pytest.mark.parametrize("who", ["president", "captain", "player", "doctor"])
def test_reserve_aux_roles_qui_saisissent_le_score(ctx, who):
    match = _finished_match(ctx)

    response = client_for(getattr(ctx, who).user).post(_url(match))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not Post.all_objects.filter(club=ctx.club).exists()


def test_etancheite_autre_club(ctx, other_ctx):
    match = _finished_match(ctx)

    response = client_for(other_ctx.coach.user).post(_url(match))

    assert response.status_code == status.HTTP_404_NOT_FOUND


# --- Défis -----------------------------------------------------------------


def _payload(**extra):
    return {
        "event_date": timezone.now().date().isoformat(),
        "kickoff_time": "15:00:00",
        "match_type": Match.MatchType.FRIENDLY,
        "venue": Match.Venue.HOME,
        **extra,
    }


def test_refuse_son_propre_club_comme_adversaire(ctx):
    response = client_for(ctx.coach.user).post(
        reverse("sport:match-list"), _payload(opponent_club_id=ctx.club.pk)
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "propre club" in response.data["detail"]


def test_refuse_de_se_defier_soi_meme(ctx):
    response = client_for(ctx.coach.user).post(
        reverse("sport:match-list"),
        _payload(opponent_name="X", challenge_status="proposed", challenge_to_club_id=ctx.club.pk),
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "propre club" in response.data["detail"]


@pytest.mark.parametrize("asked", ["accepted", "declined", "proposed"])
def test_un_defi_est_toujours_cree_propose(ctx, other_ctx, asked):
    response = client_for(ctx.coach.user).post(
        reverse("sport:match-list"),
        _payload(opponent_club_id=other_ctx.club.pk, challenge_status=asked, challenge_to_club_id=other_ctx.club.pk),
    )

    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert response.data["challenge_status"] == "proposed"
    assert Match.all_objects.get(pk=response.data["id"]).challenge_status == "proposed"


def test_un_match_ordinaire_reste_sans_objet(ctx):
    response = client_for(ctx.coach.user).post(reverse("sport:match-list"), _payload(opponent_name="FC Ext"))

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["challenge_status"] == "n_a"
