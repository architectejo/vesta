"""Contrat ``get_unfitness_reason`` attendu par ``apps.sport`` (medical.md §2.4 ;
compte rendu tache 3.2). Verifie aussi, avec un test d'integration simple
(sans dupliquer la suite ``apps.sport``), que le Lot 3 recoit desormais un
resultat reel."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.medical import services
from apps.medical.models import HealthRecord

pytestmark = pytest.mark.django_db


def _set_fitness(membership, *, status, return_date=None, actor=None, now=None):
    record = services.get_or_create_health_record(membership)
    record.fitness_status = status
    record.fitness_return_date = return_date
    record.fitness_set_by = actor
    record.fitness_set_at = now or timezone.now()
    record.save()
    return record


def test_no_health_record_means_apte_and_selectable(ctx):
    assert services.get_unfitness_reason(ctx.player) is None


def test_fit_is_selectable(ctx):
    _set_fitness(ctx.player, status=HealthRecord.FitnessStatus.FIT)
    assert services.get_unfitness_reason(ctx.player) is None


def test_fit_with_restriction_is_selectable(ctx):
    """CLAUDE.md §2.5 ne bloque que l'inaptitude (point ouvert 5)."""

    _set_fitness(ctx.player, status=HealthRecord.FitnessStatus.FIT_WITH_RESTRICTION)
    assert services.get_unfitness_reason(ctx.player) is None


def test_unfit_with_return_date_exact_format(ctx):
    return_date = datetime.date(2026, 10, 12)  # un lundi -- verifie surtout le format, pas le jour
    _set_fitness(ctx.player, status=HealthRecord.FitnessStatus.UNFIT, return_date=return_date)

    result = services.get_unfitness_reason(ctx.player)

    assert result is not None
    text, date_returned = result
    assert text == f"Inapte · retour prévu le {services.format_date_fr(return_date)}"
    assert date_returned == return_date
    assert "Blessé" not in text
    assert "blessure" not in text.lower()


def test_unfit_without_return_date(ctx):
    _set_fitness(ctx.player, status=HealthRecord.FitnessStatus.UNFIT, return_date=None)

    result = services.get_unfitness_reason(ctx.player)

    assert result == ("Inapte · date de retour non fixée", None)


def test_overdue_return_date_does_not_make_player_fit(ctx):
    """§2.4 : « Une date de retour depassee ne rend pas le joueur apte ». """

    past_date = timezone.localdate() - datetime.timedelta(days=10)
    _set_fitness(ctx.player, status=HealthRecord.FitnessStatus.UNFIT, return_date=past_date)

    result = services.get_unfitness_reason(ctx.player)

    assert result is not None
    text, date_returned = result
    assert date_returned == past_date
    assert "dépassé" not in text  # ce complement est un choix d'affichage cote Medecin (§3.2), pas du texte API


# ---------------------------------------------------------------------------
# Integration avec apps.sport (Lot 3), sans dupliquer sa suite de tests.
# ---------------------------------------------------------------------------


def test_sport_integration_receives_real_unfitness(ctx):
    from apps.sport import services as sport_services

    return_date = timezone.localdate() + datetime.timedelta(days=14)
    _set_fitness(ctx.player, status=HealthRecord.FitnessStatus.UNFIT, return_date=return_date, actor=ctx.doctor.user)

    # Le point d'integration en attente (apps.sport.services._get_medical_unfitness)
    # delegue maintenant reellement a apps.medical.services.get_unfitness_reason.
    assert sport_services._get_medical_unfitness(ctx.player) == services.get_unfitness_reason(ctx.player)

    playability = sport_services.get_playability(ctx.player)
    assert playability.eligible is False
    assert playability.reason_code == "unfit"
    assert playability.fitness_return_date == return_date
    assert playability.detail == f"Inapte · retour prévu le {services.format_date_fr(return_date)}"


def test_sport_integration_apte_player_is_eligible(ctx):
    from apps.sport import services as sport_services

    _set_fitness(ctx.player, status=HealthRecord.FitnessStatus.FIT, actor=ctx.doctor.user)

    playability = sport_services.get_playability(ctx.player)
    assert playability.eligible is True
    assert playability.reason_code == ""
