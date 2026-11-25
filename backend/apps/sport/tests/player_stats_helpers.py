"""Jeu de données construit à la main pour les tests des cartes de joueurs
(``apps.sport.player_stats``) : chaque chiffre attendu se lit dans le code."""

from __future__ import annotations

import datetime

from django.utils import timezone

from apps.clubs.models import Season
from apps.sport import services
from apps.sport.models import Event, Incident, MatchComposition, MatchGoal, MatchSheet
from apps.sport.tests.factories import MatchFactory
from apps.sport.tests.stats_helpers import club_today, evaluate, make_session, point


def make_match(ctx, *, days_ago: int = 0, sheet: bool = True, season=None, on_date=None):
    event_date = on_date or club_today(ctx) - datetime.timedelta(days=days_ago)
    match = MatchFactory(
        club=ctx.club, event__club=ctx.club, event__season=season or ctx.season, event__event_date=event_date
    )
    if sheet:
        MatchSheet.all_objects.create(
            club=ctx.club, match=match, score_home=1, score_away=0, filled_by=ctx.coach.user, filled_at=timezone.now()
        )
    return match


def compose(ctx, match, membership, *, jersey: int, role=MatchComposition.Role.STARTER):
    return MatchComposition.all_objects.create(
        club=ctx.club, match=match, membership=membership, role=role, position=membership.position or "midfielder",
        jersey_number=jersey, added_by=ctx.coach.user,
    )


def goal(ctx, match, scorer, assist=None):
    return MatchGoal.all_objects.create(
        club=ctx.club, match_sheet=match.sheet, scorer_membership=scorer, assist_membership=assist,
        created_by=ctx.coach.user,
    )


def card(ctx, event, membership, incident_type, *, cause=Incident.Cause.CONTESTATION, detail=""):
    return Incident.all_objects.create(
        club=ctx.club, event=event, membership=membership, incident_type=incident_type, cause=cause,
        cause_detail=detail, issued_by="Arbitre secret", recorded_by=ctx.coach.user, recorded_at=timezone.now(),
    )


def other_season(ctx):
    today = club_today(ctx)
    return Season.all_objects.create(
        club=ctx.club, label="Ancienne", start_date=today.replace(year=today.year - 3, month=1, day=1),
        end_date=today.replace(year=today.year - 3, month=12, day=31), created_by=ctx.coach.user,
    )


def build_dataset(ctx, p2):
    """Joueur ``ctx.player`` (p1) et ``p2`` sur la saison ``ctx.season``.

    p1 : matchs m1, m2 (m3 sans score : non joué) -> 2 matchs ; buts 2 ; passes 1.
    p2 : m1 (remplaçant) et m2 (buteur hors composition) -> 2 matchs ; buts 1 ; passes 1.
    Cartons p1 : 2 jaunes + 1 rouge (+ 1 jaune d'une autre saison et une
    sanction interne, jamais comptés).
    Séances pointées s1..s4 (s5 sans pointage, ignorée) : p1 présent s1 s2,
    absent s3, excusé s4 -> 2/4 = 50 % ; p2 présent s1 s3 s4, en retard s2
    (compté absent) -> 3/4 = 75 %.
    Notes de p1 : séance s1 = (7 + 8) / 2 = 7,5 ; match m1 = 6,0 -> moyenne 6,8.
    """

    from apps.sport.models import Attendance

    m1 = make_match(ctx, days_ago=5)
    m2 = make_match(ctx, days_ago=4)
    m3 = make_match(ctx, days_ago=3, sheet=False)
    compose(ctx, m1, ctx.player, jersey=10)
    compose(ctx, m1, p2, jersey=11, role="substitute")
    compose(ctx, m2, ctx.player, jersey=10)
    compose(ctx, m3, ctx.player, jersey=10)
    goal(ctx, m1, ctx.player, p2)
    goal(ctx, m1, ctx.player)
    goal(ctx, m2, p2, ctx.player)
    # p2 n'est pas dans la composition de m2 : le but suffit à compter le match.

    old = other_season(ctx)
    old_match = make_match(ctx, season=old, on_date=old.start_date + datetime.timedelta(days=10))
    card(ctx, m1.event, ctx.player, Incident.IncidentType.YELLOW_CARD)
    card(ctx, m2.event, ctx.player, Incident.IncidentType.YELLOW_CARD, cause=Incident.Cause.SERIOUS_FOUL)
    card(ctx, m2.event, ctx.player, Incident.IncidentType.RED_CARD, detail="Insulte à l'arbitre (détail libre)")
    card(ctx, old_match.event, ctx.player, Incident.IncidentType.YELLOW_CARD)
    card(ctx, m1.event, ctx.player, Incident.IncidentType.INTERNAL_SANCTION)

    s1 = make_session(ctx, days_ago=4)
    s2 = make_session(ctx, days_ago=3)
    s3 = make_session(ctx, days_ago=2)
    s4 = make_session(ctx, days_ago=1)
    make_session(ctx, days_ago=0)  # s5 : aucun pointage
    point(ctx, s1, ctx.player)
    point(ctx, s1, p2)
    point(ctx, s2, ctx.player)
    point(ctx, s2, p2, status=Attendance.Status.LATE_ABSENT)
    point(ctx, s3, p2)
    point(ctx, s3, ctx.player, status=Attendance.Status.ABSENT)
    point(ctx, s4, ctx.player, status=Attendance.Status.EXCUSED_ABSENT, reason="Voyage")
    point(ctx, s4, p2)

    evaluate(ctx, s1, ctx.player, 7, technical_score="8", physical_score="9", comment="COMMENTAIRE-PRIVE-1")
    evaluate(
        ctx, s1, ctx.player, 8, evaluator=ctx.president.user, technical_score="6", physical_score="9",
        comment="COMMENTAIRE-VISIBLE", visible=True,
    )
    evaluate(ctx, m1, ctx.player, 6, technical_score="5")  # un match a aussi un ``.event``
    return {"m1": m1, "m2": m2, "m3": m3, "s1": s1, "s2": s2, "s3": s3, "s4": s4, "old": old}
