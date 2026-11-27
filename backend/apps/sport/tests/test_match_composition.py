"""Matchs, composition et publication (CDC 4.8 ; CLAUDE.md règle n° 5)."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.clubs.models import Membership
from apps.sport import services
from apps.sport.models import Match, MatchComposition, MatchGoal
from apps.sport.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


def _create_match(ctx):
    return services.create_match(
        club=ctx.club, season=ctx.season, event_date=timezone.now().date(), kickoff_time=datetime.time(15, 0),
        match_type=Match.MatchType.FRIENDLY, venue=Match.Venue.HOME, created_by=ctx.coach.user, opponent_name="FC Test",
    )


def test_add_eligible_player_to_composition(ctx):
    match = _create_match(ctx)
    composition = services.add_to_composition(
        match=match, membership=ctx.player, role=MatchComposition.Role.STARTER, position=Membership.Position.MIDFIELDER,
        jersey_number=10, added_by=ctx.coach.user,
    )
    assert composition.pk is not None


def test_debtor_cannot_be_composed(ctx):
    match = _create_match(ctx)
    with pytest.raises(services.PlayerNotEligibleError) as exc:
        services.add_to_composition(
            match=match, membership=ctx.debtor, role=MatchComposition.Role.STARTER, position=Membership.Position.MIDFIELDER,
            jersey_number=9, added_by=ctx.coach.user,
        )
    # 10.3 n° 188 : l'auteur (Coach) ne lit que « Non éligible. ».
    assert str(exc.value) == "Non éligible."
    assert "dette" not in str(exc.value).lower()


def test_debt_reason_in_composition_error_matches_eligibility_text_for_president(ctx):
    """Même texte, au même format monétaire, que GET /sport/eligibility/ pour
    un rôle qui voit la dette (un seul point de mise en forme)."""

    match = _create_match(ctx)
    with pytest.raises(services.PlayerNotEligibleError) as exc:
        services.add_to_composition(
            match=match, membership=ctx.debtor, role=MatchComposition.Role.STARTER, position=Membership.Position.MIDFIELDER,
            jersey_number=9, added_by=ctx.president.user,
        )
    assert str(exc.value) == "En dette : 10 $."
    assert str(exc.value) == services.get_playabilities(ctx.club, [ctx.debtor])[ctx.debtor.pk].detail


def test_regularization_allows_composition(ctx, monkeypatch):
    match = _create_match(ctx)
    with pytest.raises(services.PlayerNotEligibleError):
        services.add_to_composition(
            match=match, membership=ctx.debtor, role=MatchComposition.Role.STARTER, position=Membership.Position.MIDFIELDER,
            jersey_number=9, added_by=ctx.coach.user,
        )

    # Régularisation simulée (voir test_attendance_and_teams.py, même
    # principe) : on ne recrée pas le mécanisme de paiement de
    # `finance-engine` ici, seulement son effet observable.
    import apps.treasury.services as treasury_services

    monkeypatch.setattr(
        treasury_services, "is_in_good_standing", lambda membership, at_date=None: (True, 0, "Le joueur est en ordre.")
    )

    composition = services.add_to_composition(
        match=match, membership=ctx.debtor, role=MatchComposition.Role.STARTER, position=Membership.Position.MIDFIELDER,
        jersey_number=9, added_by=ctx.coach.user,
    )
    assert composition.pk is not None


def test_duplicate_jersey_number_is_rejected_at_db_level(ctx):
    match = _create_match(ctx)
    from apps.sport.tests.conftest import make_member

    second_player = make_member(ctx.club)
    services.add_to_composition(
        match=match, membership=ctx.player, role=MatchComposition.Role.STARTER, position=Membership.Position.MIDFIELDER,
        jersey_number=7, added_by=ctx.coach.user,
    )
    # Refusé par le service avec un message français (D6b), avant même
    # `full_clean()` et la contrainte DB ``composition_unique_jersey_per_match``.
    with pytest.raises(services.SportValidationError, match="déjà attribué"):
        services.add_to_composition(
            match=match, membership=second_player, role=MatchComposition.Role.STARTER, position=Membership.Position.FORWARD,
            jersey_number=7, added_by=ctx.coach.user,
        )


def test_publish_composition_blocked_while_ineligible_player_present(ctx):
    match = _create_match(ctx)
    services.add_to_composition(
        match=match, membership=ctx.player, role=MatchComposition.Role.STARTER, position=Membership.Position.MIDFIELDER,
        jersey_number=10, added_by=ctx.coach.user,
    )
    # Le joueur devient en dette APRES avoir été composé (dette constatée après coup).
    from apps.sport.tests.conftest import make_debtor

    make_debtor(ctx.club, ctx.player)

    with pytest.raises(services.SportValidationError):
        services.publish_composition(match=match, published_by=ctx.coach.user)


def test_publish_composition_succeeds_when_all_eligible(ctx):
    match = _create_match(ctx)
    services.add_to_composition(
        match=match, membership=ctx.player, role=MatchComposition.Role.STARTER, position=Membership.Position.MIDFIELDER,
        jersey_number=10, added_by=ctx.coach.user,
    )
    published = services.publish_composition(match=match, published_by=ctx.coach.user)
    assert published.is_composition_published is True
    assert published.composition_published_at is not None


def test_set_score_and_goals_not_locked_after_event_date(ctx):
    """CDC 4.8 : les buts et passes restent modifiables après coup, à la
    différence du pointage/de la répartition/des incidents."""

    match = _create_match(ctx)
    sheet = services.set_match_score(match=match, score_home=2, score_away=1, filled_by=ctx.coach.user)
    match.event.event_date = services._club_today(ctx.club) - datetime.timedelta(days=1)
    match.event.save()
    goal = services.add_goal(match_sheet=sheet, created_by=ctx.coach.user, scorer_membership=ctx.player, minute=12)
    assert goal.pk is not None

    updated = services.update_goal(goal=goal, updated_by=ctx.coach.user, scorer_membership=ctx.player, minute=45)
    assert updated.minute == 45
    assert updated.updated_at is not None

    goal_pk = updated.pk
    services.delete_goal(goal=updated, deleted_by=ctx.coach.user)
    assert not MatchGoal.all_objects.filter(pk=goal_pk).exists()
