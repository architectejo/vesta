"""Score d'un match verrouillé après minuit, mise à jour du résultat publié
(décisions du client du 16/11/2026 ; CDC 4.8, 10.3)."""

from __future__ import annotations

import datetime

import pytest
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.factories import SuperuserFactory
from apps.audit.models import AuditLog
from apps.social.models import Post
from apps.sport import services
from apps.sport.models import MatchSheet
from apps.sport.tests.conftest import client_for
from apps.sport.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


def _match(ctx, *, days_ago=0):
    day = services._club_today(ctx.club) - datetime.timedelta(days=days_ago)
    return MatchFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=day,
        kickoff_time=datetime.time(0, 0),
    )


def _score_url(match):
    return reverse("sport:match-score", args=[match.pk])


def test_score_accepte_le_jour_meme(ctx):
    match = _match(ctx)

    response = client_for(ctx.coach.user).post(_score_url(match), {"score_home": 2, "score_away": 1})

    assert response.status_code == status.HTTP_200_OK
    assert MatchSheet.all_objects.get(match=match).score_home == 2


def test_score_refuse_apres_minuit_avec_le_code_event_locked(ctx):
    match = _match(ctx, days_ago=1)

    response = client_for(ctx.coach.user).post(_score_url(match), {"score_home": 2, "score_away": 1})

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "event_locked"
    assert "verrouillé depuis minuit" in response.data["detail"]
    assert not MatchSheet.all_objects.filter(match=match).exists()


def test_score_existant_non_modifiable_apres_minuit(ctx):
    match = _match(ctx)
    services.set_match_score(match=match, score_home=1, score_away=0, filled_by=ctx.coach.user)
    match.event.event_date -= datetime.timedelta(days=1)
    match.event.save()

    with pytest.raises(services.EventLockedError):
        services.set_match_score(match=match, score_home=5, score_away=0, filled_by=ctx.coach.user)
    assert MatchSheet.all_objects.get(match=match).score_home == 1


def test_superuser_peut_corriger_le_score_verrouille(ctx):
    match = _match(ctx, days_ago=3)

    sheet = services.set_match_score(match=match, score_home=2, score_away=2, filled_by=SuperuserFactory())

    assert sheet.score_home == 2


def test_les_buts_restent_modifiables_apres_minuit(ctx):
    match = _match(ctx)
    sheet = services.set_match_score(match=match, score_home=1, score_away=0, filled_by=ctx.coach.user)
    match.event.event_date -= datetime.timedelta(days=1)
    match.event.save()

    goal = services.add_goal(match_sheet=sheet, created_by=ctx.coach.user, scorer_membership=ctx.player, minute=10)
    updated = services.update_goal(goal=goal, updated_by=ctx.coach.user, scorer_membership=ctx.player, minute=20)

    assert updated.minute == 20


# --- Résultat publié mis à jour --------------------------------------------


def _published(ctx):
    match = _match(ctx)
    services.set_match_score(match=match, score_home=1, score_away=0, filled_by=ctx.coach.user)
    services.publish_match_result(match=match, published_by=ctx.coach.user)
    return Match_reload(match)


def Match_reload(match):
    from apps.sport.models import Match

    return Match.all_objects.get(pk=match.pk)


def test_le_score_modifie_met_a_jour_le_meme_post(ctx):
    match = _published(ctx)
    post_id = match.result_post_id

    services.set_match_score(match=match, score_home=3, score_away=2, filled_by=ctx.coach.user)

    posts = Post.all_objects.filter(club=ctx.club, post_kind=Post.PostKind.AUTO_RESULT)
    assert posts.count() == 1
    post = posts.get()
    assert post.pk == post_id
    assert "3 - 2" in post.body
    assert post.visibility == Post.Visibility.CLUB_ONLY
    log = AuditLog.objects.get(club=ctx.club, action_type="sport.match_result_post_updated")
    assert log.actor_id == ctx.coach.user.pk
    assert log.before["score_home"] == 1 and log.after["score_home"] == 3


def test_un_score_inchange_ne_journalise_pas_de_mise_a_jour(ctx):
    match = _published(ctx)

    services.set_match_score(match=match, score_home=1, score_away=0, filled_by=ctx.coach.user)

    assert not AuditLog.objects.filter(club=ctx.club, action_type="sport.match_result_post_updated").exists()


def test_un_but_modifie_met_a_jour_le_texte_du_post(ctx):
    match = _published(ctx)
    sheet = MatchSheet.all_objects.get(match=match)

    goal = services.add_goal(match_sheet=sheet, created_by=ctx.coach.user, scorer_membership=ctx.player, minute=12)
    post = Post.all_objects.get(pk=match.result_post_id)
    assert "Buteurs" in post.body and "12'" in post.body

    services.update_goal(goal=goal, updated_by=ctx.coach.user, scorer_membership=ctx.player, minute=30)
    assert "30'" in Post.all_objects.get(pk=match.result_post_id).body

    services.delete_goal(goal=goal, deleted_by=ctx.coach.user)
    assert "Buteurs" not in Post.all_objects.get(pk=match.result_post_id).body
    assert Post.all_objects.filter(club=ctx.club, post_kind=Post.PostKind.AUTO_RESULT).count() == 1
    assert AuditLog.objects.filter(club=ctx.club, action_type="sport.match_result_post_updated").count() == 3


def test_sans_publication_aucun_post_n_est_cree(ctx):
    match = _match(ctx)
    sheet = services.set_match_score(match=match, score_home=1, score_away=0, filled_by=ctx.coach.user)
    services.add_goal(match_sheet=sheet, created_by=ctx.coach.user, scorer_membership=ctx.player, minute=1)
    services.set_match_score(match=match, score_home=2, score_away=0, filled_by=ctx.coach.user)

    assert not Post.all_objects.filter(club=ctx.club).exists()
