"""Cycle de vie d'une blessure (CDC 4.12 etapes 1-5 ; medical.md §4.1,
§4.4, §4.7-§4.9)."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.medical import services
from apps.medical.models import HealthRecord, Injury

pytestmark = pytest.mark.django_db


def test_only_coach_captain_or_doctor_can_report(ctx):
    with pytest.raises(services.MedicalPermissionError):
        services.report_injury(membership=ctx.player, actor=ctx.president.user, circumstances="Chute.")


def test_report_injury_requires_circumstances(ctx):
    with pytest.raises(services.MedicalValidationError):
        services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="   ")


def test_report_injury_makes_player_unfit_immediately(ctx):
    """Point ouvert 3, position retenue : inapte DES la declaration, avant
    meme le bilan du Medecin (schema §6.2)."""

    services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Choc a l'entrainement.")
    record = services.get_health_record(ctx.player)
    assert record.fitness_status == HealthRecord.FitnessStatus.UNFIT
    assert services.get_unfitness_reason(ctx.player) is not None


def test_a_second_injury_creates_a_distinct_record(ctx):
    injury_1 = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Premiere blessure.")
    injury_2 = services.report_injury(membership=ctx.player, actor=ctx.captain.user, circumstances="Deuxieme blessure.")
    assert injury_1.pk != injury_2.pk
    assert Injury.all_objects.filter(club_id=ctx.club.id, membership_id=ctx.player.pk).count() == 2


def test_declaration_missing_consent_is_still_accepted(ctx):
    """Point ouvert 4 : la declaration reste possible sans consentement au
    traitement -- l'auteur n'en est pas informe."""

    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Sans consentement.")
    assert injury.pk is not None


def test_complete_injury_report_blocked_without_processing_consent(ctx):
    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Entorse.")
    with pytest.raises(services.ConsentMissingError):
        services.complete_injury_report(injury=injury, actor=ctx.doctor.user, location_on_body="Cheville")


def test_complete_injury_report_only_for_doctor(ctx):
    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Entorse.")
    services.give_processing_consent(membership=ctx.player, actor=ctx.player.user)
    with pytest.raises(services.MedicalPermissionError):
        services.complete_injury_report(injury=injury, actor=ctx.coach.user, location_on_body="Cheville")


def test_complete_injury_report_succeeds_with_consent(ctx):
    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Entorse.")
    services.give_processing_consent(membership=ctx.player, actor=ctx.player.user)

    injury = services.complete_injury_report(
        injury=injury,
        actor=ctx.doctor.user,
        location_on_body="Cheville droite",
        severity=Injury.Severity.MODERATE,
        referral=Injury.Referral.CONSULTATION,
        estimated_days_out=10,
    )
    assert injury.doctor_completed_by_id == ctx.doctor.user_id
    assert injury.doctor_completed_at is not None


def test_add_followup_requires_consent_and_doctor_role(ctx):
    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Entorse.")
    with pytest.raises(services.ConsentMissingError):
        services.add_injury_followup(injury=injury, actor=ctx.doctor.user, entry_date=timezone.localdate(), note="RAS")

    services.give_processing_consent(membership=ctx.player, actor=ctx.player.user)
    with pytest.raises(services.MedicalPermissionError):
        services.add_injury_followup(injury=injury, actor=ctx.coach.user, entry_date=timezone.localdate(), note="RAS")

    followup = services.add_injury_followup(
        injury=injury, actor=ctx.doctor.user, entry_date=timezone.localdate(), note="Evolution favorable."
    )
    assert followup.pk is not None


def test_followup_service_has_no_update_or_delete(ctx):
    """Point ouvert 7, position retenue : une entree de suivi n'est jamais
    modifiee ni supprimee."""

    assert not hasattr(services, "update_injury_followup")
    assert not hasattr(services, "delete_injury_followup")


def test_declare_return_makes_player_fit_again(ctx):
    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Entorse.")
    services.declare_injury_return(injury=injury, actor=ctx.doctor.user, return_date=timezone.localdate())

    record = services.get_health_record(ctx.player)
    assert record.fitness_status == HealthRecord.FitnessStatus.FIT
    assert record.fitness_return_date is None
    assert services.get_unfitness_reason(ctx.player) is None


def test_declare_return_keeps_player_unfit_if_another_injury_open(ctx):
    injury_1 = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Premiere.")
    services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Deuxieme.")

    services.declare_injury_return(injury=injury_1, actor=ctx.doctor.user, return_date=timezone.localdate())

    record = services.get_health_record(ctx.player)
    assert record.fitness_status == HealthRecord.FitnessStatus.UNFIT


def test_update_fitness_blocked_to_fit_while_injury_open(ctx):
    services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Entorse.")
    with pytest.raises(services.MedicalValidationError):
        services.update_fitness(membership=ctx.player, actor=ctx.doctor.user, status=HealthRecord.FitnessStatus.FIT)


def test_update_fitness_by_non_doctor_forbidden(ctx):
    with pytest.raises(services.MedicalPermissionError):
        services.update_fitness(membership=ctx.player, actor=ctx.coach.user, status=HealthRecord.FitnessStatus.UNFIT)


def test_update_fitness_unfit_requires_future_or_no_return_date(ctx):
    past_date = timezone.localdate() - datetime.timedelta(days=1)
    with pytest.raises(services.MedicalValidationError):
        services.update_fitness(
            membership=ctx.player, actor=ctx.doctor.user, status=HealthRecord.FitnessStatus.UNFIT, return_date=past_date
        )
