"""Idempotence du pointage groupé : un ``client_uuid`` n'est jamais rejoué
pour un autre joueur (séances et matchs)."""

from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from apps.sport import services
from apps.sport.models import Attendance
from apps.sport.tests.conftest import make_member
from apps.sport.tests.factories import MatchFactory, SessionFactory

pytestmark = pytest.mark.django_db

NOW = timezone.now()
MESSAGE = "Cet identifiant de pointage est déjà utilisé pour un autre joueur."


def _session_event(ctx):
    return SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season).event


def _match_event(ctx):
    return MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season).event


@pytest.mark.parametrize("make_event", [_session_event, _match_event])
def test_client_uuid_rejoue_pour_un_autre_joueur_est_refuse(ctx, make_event):
    event = make_event(ctx)
    other = make_member(ctx.club)
    key = uuid.uuid4()
    services.mark_arrivals_bulk(event=event, items=[{"membership_id": ctx.player.pk, "client_uuid": key, "client_recorded_at": NOW}], actor=ctx.coach.user)

    result = services.mark_arrivals_bulk(
        event=event, items=[{"membership_id": other.pk, "client_uuid": key, "client_recorded_at": NOW}], actor=ctx.coach.user
    )

    row = result["results"][0]
    assert row["outcome"] == "refused" and row["message"] == MESSAGE
    assert row["attendance"] is None
    assert not Attendance.all_objects.filter(event=event, membership=other).exists()


def test_meme_client_uuid_pour_deux_joueurs_du_meme_lot(ctx):
    event = _session_event(ctx)
    other = make_member(ctx.club)
    key = uuid.uuid4()

    result = services.mark_arrivals_bulk(
        event=event,
        items=[{"membership_id": ctx.player.pk, "client_uuid": key, "client_recorded_at": NOW}, {"membership_id": other.pk, "client_uuid": key, "client_recorded_at": NOW}],
        actor=ctx.coach.user,
    )

    outcomes = [r["outcome"] for r in result["results"]]
    assert outcomes == ["created", "refused"]
    assert result["results"][1]["message"] == MESSAGE
    assert not Attendance.all_objects.filter(event=event, membership=other).exists()


def test_rejeu_pour_le_meme_joueur_reste_skipped(ctx):
    event = _session_event(ctx)
    key = uuid.uuid4()
    item = {"membership_id": ctx.player.pk, "client_uuid": key, "client_recorded_at": NOW}
    services.mark_arrivals_bulk(event=event, items=[item], actor=ctx.coach.user)

    result = services.mark_arrivals_bulk(event=event, items=[item], actor=ctx.coach.user)

    row = result["results"][0]
    assert row["outcome"] == "skipped" and row["attendance"].membership_id == ctx.player.pk
    assert Attendance.all_objects.filter(client_uuid=key).count() == 1


def test_pointage_individuel_refuse_un_client_uuid_d_un_autre_joueur(ctx):
    event = _session_event(ctx)
    other = make_member(ctx.club)
    key = uuid.uuid4()
    services.mark_arrival(
        session=event.session, membership=ctx.player, arrived_at=timezone.now(), marked_by=ctx.coach.user,
        client_uuid=key, client_recorded_at=timezone.now(),
    )

    with pytest.raises(services.SportValidationError, match="déjà utilisé pour un autre joueur"):
        services.mark_arrival(
            session=event.session, membership=other, arrived_at=timezone.now(), marked_by=ctx.coach.user,
            client_uuid=key, client_recorded_at=timezone.now(),
        )
