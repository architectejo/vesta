"""Tests de performance (docs/ecrans/sport-statistiques-seance.md, partie C ;
circuit 9.4, validé par le client les 15-16/11/2026 « tels que spécifiés »).

Règles portées ici (jamais par les vues ni l'interface) :

- Quatre types : chrono sur distance, distance en temps donné, répétitions,
  saisie libre. Unités en liste fermée ; aucune donnée de santé, aucune
  estimation physiologique ; aucun lien avec le radar ni la note globale.
- Le client envoie la durée mesurée en millisecondes entières et un
  ``client_uuid`` (idempotence hors connexion) ; le serveur calcule la
  vitesse = distance ÷ temps en ``Decimal`` (jamais ``float``).
- Un résultat n'est jamais supprimé : une correction crée une ligne
  ``PerformanceResultCorrection`` (motif et auteur obligatoires), un retrait
  passe le résultat à « Retiré ».
- Journal d'activité (règle 6) : création, modification et archivage d'un
  test ; une entrée par résultat enregistré (avec l'identifiant de
  l'épreuve) ; chaque correction et chaque retrait (valeurs avant/après,
  motif). Aucune consultation n'est journalisée.

Positions provisoires de la spec appliquées (questions au client) :

- C-Q3 : seuls le Coach et l'Assistant mesurent (ni Capitaine, ni
  Président, ni Vice-président).
- C-Q4 : seule l'inaptitude bloque une mesure ; dette, suspension et
  attente d'adhésion n'empêchent pas de mesurer. Seuls les joueurs pointés
  (présents ou en retard) sont mesurables.
- C-Q5 : plusieurs essais par séance : le résultat retenu est le meilleur
  essai.
- C-Q6 : résultats internes au club (ni fil public, ni comparaison).
- C-Q7 : aucun lien avec le radar.
- C-Q8 : mesure et correction possibles pendant la fenêtre des évaluations
  du club (48 h par défaut) ; ensuite, seul le Superuser peut écrire.
- C-Q9 : notification « Vos mesures sont disponibles » : une par joueur et
  par séance, 1 h après la dernière mesure (commande cron).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.clubs.models import Membership
from apps.core.services import log_action
from apps.sport.models import (
    Attendance,
    Event,
    PerformanceResult,
    PerformanceResultCorrection,
    PerformanceRun,
    PerformanceTest,
)
from apps.sport.services import (
    SportError,
    SportPermissionError,
    SportValidationError,
    _club_settings,
    _get_medical_unfitness,
    _is_coaching_staff,
    is_evaluation_locked,
)

logger = logging.getLogger(__name__)

Kind = PerformanceTest.Kind
Unit = PerformanceTest.Unit

BULK_MAX_ITEMS = 100
NOTIFICATION_DELAY = timedelta(hours=1)
NOTIFICATION_LOOKBACK_DAYS = 14
IMPLAUSIBLE_SPEED_KMH = Decimal("45")
MAX_TIME_MS = 4 * 3600 * 1000
MAX_DISTANCE_M = Decimal("10000")
MAX_FREE_VALUE = Decimal("9999999")

_NBSP = " "
_UNIT_SYMBOLS = {
    Unit.SECONDS: "s",
    Unit.METERS: "m",
    Unit.KMH: "km/h",
    Unit.REPETITIONS: "",
    Unit.POINTS: "pts",
    Unit.PERCENT: "%",
}

#: Modèles proposés (liste de référence servie par l'API, jamais en base : ni
#: migration, ni donnée de démonstration). Choisir un modèle préremplit la
#: modale ; rien n'est créé sans « Enregistrer ».
TEMPLATES = (
    {"code": "sprint_30", "name": "Sprint 30 m", "kind": Kind.TIMED_DISTANCE, "distance_m": "30",
     "description": "Départ arrêté, ligne de but à ligne des 30 m."},
    {"code": "sprint_10", "name": "Sprint 10 m", "kind": Kind.TIMED_DISTANCE, "distance_m": "10",
     "description": "Départ arrêté, ligne de but à ligne des 10 m."},
    {"code": "shuttle_5x10", "name": "Navette 5 × 10 m", "kind": Kind.TIMED_DISTANCE, "distance_m": "50",
     "description": "Cinq allers-retours de 10 m (distance totale 50 m)."},
    {"code": "cooper_12", "name": "Test de Cooper (12 min)", "kind": Kind.DISTANCE_IN_TIME, "duration_s": 720,
     "description": "Distance parcourue en 12 minutes."},
    {"code": "shots_on_target_10", "name": "Tirs cadrés sur 10", "kind": Kind.REPETITIONS, "attempts": 10,
     "description": "Nombre de tirs cadrés sur 10 tentatives."},
    {"code": "juggling_1min", "name": "Jongles en 1 minute", "kind": Kind.REPETITIONS, "time_limit_s": 60,
     "description": "Nombre de jongles enchaînés en 1 minute."},
)

HEALTH_HELP = (
    "Les tests mesurent une performance sportive. N'y enregistrez aucune donnée de santé "
    "(poids, taille, fréquence cardiaque) : elles relèvent du Médecin."
)


def list_templates() -> list[dict]:
    base = {"distance_m": None, "duration_s": None, "attempts": None, "time_limit_s": None,
            "unit": "", "decimals": 0, "higher_is_better": True}
    return [{**base, **template, "kind": str(template["kind"])} for template in TEMPLATES]


# ---------------------------------------------------------------------------
# Formatage (français) et calculs dérivés : tout en Decimal
# ---------------------------------------------------------------------------


def _fmt_number(value: Decimal, places: int) -> str:
    quantum = Decimal(1).scaleb(-places)
    text = f"{value.quantize(quantum, rounding=ROUND_HALF_UP):,.{places}f}"
    return text.replace(",", _NBSP).replace(".", ",")


def format_time_ms(time_ms: int) -> str:
    """4,52 s ; au-delà de 60 s : 1 min 05,30 s (au centième, arrondi)."""

    centis = (time_ms + 5) // 10
    if centis >= 6000:
        minutes, rest = divmod(centis, 6000)
        return f"{minutes} min {rest // 100:02d},{rest % 100:02d} s"
    return f"{centis // 100},{centis % 100:02d} s"


def _speed(distance_m: Decimal, seconds: Decimal) -> Optional[tuple[Decimal, Decimal]]:
    if seconds <= 0:
        return None
    ms = distance_m / seconds
    kmh = distance_m * Decimal("3.6") / seconds
    return ms.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), kmh.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def speed_kmh_for_time(distance_m: Decimal, time_ms: int) -> Decimal:
    """Vitesse moyenne en km/h = distance ÷ temps, calculée en Decimal."""

    return (distance_m * Decimal(3600) / Decimal(time_ms)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def sort_value(test: PerformanceTest, result) -> Optional[Decimal]:
    """Valeur brute comparable d'un résultat (classement, meilleur essai)."""

    if result.outcome != PerformanceResult.Outcome.DONE:
        return None
    if test.kind == Kind.TIMED_DISTANCE:
        return Decimal(result.time_ms) if result.time_ms is not None else None
    if test.kind == Kind.DISTANCE_IN_TIME:
        return result.distance_m
    if test.kind == Kind.REPETITIONS:
        return Decimal(result.count) if result.count is not None else None
    return result.value


def display_value(test: PerformanceTest, result) -> str:
    if result.outcome == PerformanceResult.Outcome.DNF:
        return "Abandon"
    if test.kind == Kind.TIMED_DISTANCE:
        return format_time_ms(result.time_ms)
    if test.kind == Kind.DISTANCE_IN_TIME:
        places = 0 if result.distance_m == result.distance_m.to_integral_value() else 2
        return f"{_fmt_number(result.distance_m, places)}{_NBSP}m"
    if test.kind == Kind.REPETITIONS:
        return f"{result.count} sur {test.attempts}" if test.attempts else str(result.count)
    symbol = _UNIT_SYMBOLS.get(test.unit, "")
    number = _fmt_number(result.value, test.decimals)
    return f"{number}{_NBSP}{symbol}".strip()


def derived_values(test: PerformanceTest, result) -> dict:
    """Valeurs dérivées calculées par l'API (vitesse, taux de réussite)."""

    derived: dict[str, Any] = {}
    if result.outcome != PerformanceResult.Outcome.DONE:
        return derived
    if test.kind == Kind.TIMED_DISTANCE and result.time_ms:
        speeds = _speed(test.distance_m, Decimal(result.time_ms) / Decimal(1000))
    elif test.kind == Kind.DISTANCE_IN_TIME and result.distance_m is not None and test.duration_s:
        speeds = _speed(result.distance_m, Decimal(test.duration_s))
    else:
        speeds = None
    if speeds is not None:
        derived["speed_ms"] = str(speeds[0])
        derived["speed_kmh"] = str(speeds[1])
        derived["speed_display"] = f"{_fmt_number(speeds[1], 1)}{_NBSP}km/h"
        derived["speed_ms_display"] = f"{_fmt_number(speeds[0], 2)}{_NBSP}m/s"
    if test.kind == Kind.REPETITIONS and test.attempts and result.count is not None:
        rate = (Decimal(result.count) * 100 / Decimal(test.attempts)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        derived["success_rate"] = int(rate)
        derived["success_rate_display"] = f"{int(rate)}{_NBSP}%"
    return derived


def format_delta(test: PerformanceTest, delta: Decimal) -> str:
    """Écart absolu lisible (« 0,12 s », « 3 m », « 2 »)."""

    delta = abs(delta)
    if test.kind == Kind.TIMED_DISTANCE:
        return f"{_fmt_number(delta / Decimal(1000), 2)}{_NBSP}s"
    if test.kind == Kind.DISTANCE_IN_TIME:
        return f"{_fmt_number(delta, 0 if delta == delta.to_integral_value() else 2)}{_NBSP}m"
    if test.kind == Kind.REPETITIONS:
        return _fmt_number(delta, 0)
    symbol = _UNIT_SYMBOLS.get(test.unit, "")
    return f"{_fmt_number(delta, test.decimals)}{_NBSP}{symbol}".strip()


def _direction(test: PerformanceTest, delta: Decimal) -> str:
    if delta == 0:
        return "stable"
    improved = delta > 0 if test.higher_is_better else delta < 0
    return "progress" if improved else "regress"


def _is_better(test: PerformanceTest, candidate: Decimal, reference: Decimal) -> bool:
    return candidate > reference if test.higher_is_better else candidate < reference


def serialize_result_value(test: PerformanceTest, result) -> dict:
    return {
        "outcome": result.outcome,
        "time_ms": result.time_ms,
        "distance_m": str(result.distance_m) if result.distance_m is not None else None,
        "count": result.count,
        "value": str(result.value) if result.value is not None else None,
        "display": display_value(test, result),
        "derived": derived_values(test, result),
    }


# ---------------------------------------------------------------------------
# Tests (catalogue du club)
# ---------------------------------------------------------------------------


def _ensure_manager(actor, club) -> None:
    if not _is_coaching_staff(actor, club):
        raise SportPermissionError("Seuls le Coach et son assistant gèrent les tests de performance.")


def _as_decimal(value, message: str) -> Decimal:
    """Décimal exact à partir de la saisie : un nombre JSON (``4.52``) est
    relu depuis son écriture, jamais calculé en virgule flottante."""

    if isinstance(value, bool):
        raise SportValidationError(message)
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise SportValidationError(message) from None
    if not number.is_finite():
        raise SportValidationError(message)
    return number


def _as_int(value, message: str) -> int:
    if isinstance(value, bool):
        raise SportValidationError(message)
    number = _as_decimal(value, message)
    if number != number.to_integral_value():
        raise SportValidationError(message)
    return int(number)


def _clean_test_fields(data: dict) -> dict:
    name = (data.get("name") or "").strip()
    if not name:
        raise SportValidationError("Saisissez un nom pour le test.")
    if len(name) > 60:
        raise SportValidationError("Le nom ne doit pas dépasser 60 caractères.")
    description = (data.get("description") or "").strip()
    if len(description) > 300:
        raise SportValidationError("La description ne doit pas dépasser 300 caractères.")
    kind = data.get("kind")
    if kind not in Kind.values:
        raise SportValidationError("Choisissez un type de test.")

    fields: dict[str, Any] = {
        "name": name,
        "description": description,
        "kind": kind,
        "distance_m": None,
        "duration_s": None,
        "attempts": None,
        "time_limit_s": None,
        "unit": "",
        "decimals": 0,
        "higher_is_better": True,
    }
    if kind == Kind.TIMED_DISTANCE:
        message = "Saisissez une distance entre 1 et 5 000 m."
        if data.get("distance_m") in (None, ""):
            raise SportValidationError(message)
        distance = _as_decimal(data["distance_m"], message)
        if not (Decimal(1) <= distance <= Decimal(5000)):
            raise SportValidationError(message)
        fields.update(distance_m=distance.quantize(Decimal("0.01")), unit=Unit.SECONDS, decimals=2,
                      higher_is_better=False)
    elif kind == Kind.DISTANCE_IN_TIME:
        message = "Saisissez une durée entre 10 secondes et 60 minutes."
        if data.get("duration_s") in (None, ""):
            raise SportValidationError(message)
        duration = _as_int(data["duration_s"], message)
        if not (10 <= duration <= 3600):
            raise SportValidationError(message)
        fields.update(duration_s=duration, unit=Unit.METERS)
    elif kind == Kind.REPETITIONS:
        if data.get("attempts") not in (None, ""):
            attempts = _as_int(data["attempts"], "Le nombre de tentatives doit être compris entre 1 et 100.")
            if not (1 <= attempts <= 100):
                raise SportValidationError("Le nombre de tentatives doit être compris entre 1 et 100.")
            fields["attempts"] = attempts
        if data.get("time_limit_s") not in (None, ""):
            limit = _as_int(data["time_limit_s"], "La durée limite doit être supérieure à 0.")
            if not (0 < limit <= 3600):
                raise SportValidationError("La durée limite doit être supérieure à 0 et ne pas dépasser 60 minutes.")
            fields["time_limit_s"] = limit
        fields["unit"] = Unit.REPETITIONS
    else:
        unit = data.get("unit")
        if unit not in Unit.values:
            raise SportValidationError("Choisissez une unité dans la liste.")
        decimals = _as_int(data.get("decimals", 0), "Choisissez 0, 1 ou 2 décimales.")
        if decimals not in (0, 1, 2):
            raise SportValidationError("Choisissez 0, 1 ou 2 décimales.")
        higher = data.get("higher_is_better")
        if not isinstance(higher, bool):
            raise SportValidationError("Choisissez le sens du classement.")
        fields.update(unit=unit, decimals=decimals, higher_is_better=higher)
    return fields


def _ensure_unique_name(club, name: str, *, exclude_pk=None) -> None:
    queryset = PerformanceTest.all_objects.filter(club=club, archived_at__isnull=True, name__iexact=name)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    if queryset.exists():
        raise SportValidationError("Un test porte déjà ce nom.")


def _test_snapshot(test: PerformanceTest) -> dict:
    return {
        "name": test.name,
        "kind": test.kind,
        "distance_m": str(test.distance_m) if test.distance_m is not None else None,
        "duration_s": test.duration_s,
        "attempts": test.attempts,
        "time_limit_s": test.time_limit_s,
        "unit": test.unit,
        "decimals": test.decimals,
        "higher_is_better": test.higher_is_better,
        "description": test.description,
        "archived": test.archived_at is not None,
    }


def create_performance_test(*, club, actor, data: dict) -> PerformanceTest:
    _ensure_manager(actor, club)
    fields = _clean_test_fields(data)
    _ensure_unique_name(club, fields["name"])
    with transaction.atomic():
        test = PerformanceTest(club=club, created_by=actor, **fields)
        test.save()
        log_action(actor=actor, club=club, action_type="sport.performance_test_created", obj=test,
                   after=_test_snapshot(test))
    return test


def test_has_results(test: PerformanceTest) -> bool:
    return PerformanceResult.all_objects.filter(club=test.club_id, run__test=test).exists()


def update_performance_test(*, test: PerformanceTest, actor, data: dict) -> PerformanceTest:
    """Nom et description toujours modifiables ; type et paramètres seulement
    tant qu'aucun résultat n'existe (sinon les résultats ne seraient plus
    comparables : on archive et on crée un nouveau test)."""

    _ensure_manager(actor, test.club)
    if test.archived_at is not None:
        raise SportValidationError("Ce test est archivé : il ne peut plus être modifié.")
    merged = {**_test_snapshot(test), **data}
    if test.distance_m is not None and "distance_m" not in data:
        merged["distance_m"] = test.distance_m
    fields = _clean_test_fields(merged)
    _ensure_unique_name(test.club, fields["name"], exclude_pk=test.pk)
    before = _test_snapshot(test)
    structural = ("kind", "distance_m", "duration_s", "attempts", "time_limit_s", "unit", "decimals", "higher_is_better")
    changed_structure = any(getattr(test, key) != fields[key] for key in structural)
    if changed_structure and test_has_results(test):
        raise SportValidationError(
            "Le type et les paramètres ne peuvent plus changer : des résultats existent. "
            "Archivez ce test et créez-en un nouveau."
        )
    with transaction.atomic():
        for key, value in fields.items():
            setattr(test, key, value)
        test.save()
        log_action(actor=actor, club=test.club, action_type="sport.performance_test_updated", obj=test,
                   before=before, after=_test_snapshot(test))
    return test


def archive_performance_test(*, test: PerformanceTest, actor) -> PerformanceTest:
    _ensure_manager(actor, test.club)
    if test.archived_at is not None:
        raise SportValidationError("Ce test est déjà archivé.")
    before = _test_snapshot(test)
    with transaction.atomic():
        test.archived_at = timezone.now()
        test.save()
        log_action(actor=actor, club=test.club, action_type="sport.performance_test_archived", obj=test,
                   before=before, after=_test_snapshot(test))
    return test


def describe_test(test: PerformanceTest, has_results: Optional[bool] = None) -> dict:
    """Définition d'un test, avec le libellé du type en clair (« Chrono sur 30 m »)."""

    if test.kind == Kind.TIMED_DISTANCE:
        distance = _fmt_number(test.distance_m, 0 if test.distance_m == test.distance_m.to_integral_value() else 2)
        kind_text = f"Chrono sur {distance}{_NBSP}m"
    elif test.kind == Kind.DISTANCE_IN_TIME:
        minutes, seconds = divmod(test.duration_s, 60)
        kind_text = f"Distance en {minutes} min" + (f" {seconds:02d} s" if seconds else "")
    else:
        kind_text = test.get_kind_display()
    return {
        "id": test.pk,
        "name": test.name,
        "kind": test.kind,
        "kind_label": test.get_kind_display(),
        "kind_text": kind_text,
        "distance_m": str(test.distance_m) if test.distance_m is not None else None,
        "duration_s": test.duration_s,
        "attempts": test.attempts,
        "time_limit_s": test.time_limit_s,
        "unit": test.unit,
        "unit_label": test.get_unit_display() if test.unit else "",
        "decimals": test.decimals,
        "higher_is_better": test.higher_is_better,
        "description": test.description,
        "archived": test.archived_at is not None,
        "archived_at": test.archived_at,
        "stopwatch_available": test.kind in (Kind.TIMED_DISTANCE, Kind.DISTANCE_IN_TIME),
        "has_results": test_has_results(test) if has_results is None else has_results,
    }


# ---------------------------------------------------------------------------
# Enregistrement des résultats
# ---------------------------------------------------------------------------


def _validate_values(test: PerformanceTest, item: dict) -> dict:
    """Valeurs normalisées d'un résultat selon le type du test, ou erreur."""

    outcome = item.get("outcome") or PerformanceResult.Outcome.DONE
    if outcome not in PerformanceResult.Outcome.values:
        raise SportValidationError("Résultat invalide.")
    values = {"time_ms": None, "distance_m": None, "count": None, "value": None, "outcome": outcome}
    provided = {key: item.get(key) for key in ("time_ms", "distance_m", "count", "value") if item.get(key) is not None}
    if outcome == PerformanceResult.Outcome.DNF:
        if provided:
            raise SportValidationError("Un abandon ne porte aucune valeur.")
        return values

    expected_key = {
        Kind.TIMED_DISTANCE: "time_ms",
        Kind.DISTANCE_IN_TIME: "distance_m",
        Kind.REPETITIONS: "count",
        Kind.FREE: "value",
    }[test.kind]
    if expected_key not in provided:
        messages = {
            "time_ms": "Saisissez un temps supérieur à 0.",
            "distance_m": "La distance doit être comprise entre 0 et 10 000 m.",
            "count": "Saisissez le nombre réussi.",
            "value": "Saisissez une valeur positive.",
        }
        raise SportValidationError(messages[expected_key])
    if set(provided) - {expected_key}:
        raise SportValidationError("Cette valeur ne correspond pas au type de ce test.")

    if expected_key == "time_ms":
        time_ms = _as_int(provided["time_ms"], "Saisissez un temps supérieur à 0.")
        if time_ms <= 0:
            raise SportValidationError("Saisissez un temps supérieur à 0.")
        if time_ms > MAX_TIME_MS:
            raise SportValidationError("Ce temps est trop long : vérifiez-le.")
        values["time_ms"] = time_ms
    elif expected_key == "distance_m":
        message = "La distance doit être comprise entre 0 et 10 000 m."
        distance = _as_decimal(provided["distance_m"], message)
        if not (Decimal(0) < distance <= MAX_DISTANCE_M):
            raise SportValidationError(message)
        values["distance_m"] = distance.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif expected_key == "count":
        count = _as_int(provided["count"], "Saisissez le nombre réussi.")
        if count < 0:
            raise SportValidationError("Saisissez le nombre réussi.")
        if test.attempts and count > test.attempts:
            raise SportValidationError(f"Le nombre ne peut pas dépasser {test.attempts} tentatives.")
        values["count"] = count
    else:
        message = "Saisissez une valeur positive."
        number = _as_decimal(provided["value"], message)
        if number < 0 or number > MAX_FREE_VALUE:
            raise SportValidationError(message)
        if test.unit == Unit.PERCENT and number > 100:
            raise SportValidationError("Le pourcentage doit être compris entre 0 et 100.")
        values["value"] = number.quantize(Decimal(1).scaleb(-test.decimals), rounding=ROUND_HALF_UP)
    return values


def _implausible_warning(test: PerformanceTest, values: dict) -> str:
    if test.kind == Kind.TIMED_DISTANCE and values["time_ms"]:
        if speed_kmh_for_time(test.distance_m, values["time_ms"]) > IMPLAUSIBLE_SPEED_KMH:
            minimum = (test.distance_m * Decimal(3600) / IMPLAUSIBLE_SPEED_KMH / Decimal(1000)).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
            return (
                f"Ce temps paraît trop court pour {_fmt_number(test.distance_m, 0)}{_NBSP}m "
                f"(moins de {_fmt_number(minimum, 1)}{_NBSP}s) : vérifiez-le."
            )
    return ""


def _fullname(membership: Membership) -> str:
    return f"{membership.user.first_name} {membership.user.last_name}".strip()


def _ensure_measurable(event: Event, membership: Membership, pointed_ids: set[int]) -> None:
    if membership.club_id != event.club_id:
        raise SportValidationError("Ce joueur n'existe pas dans ce club.")
    if membership.pk not in pointed_ids:
        raise SportValidationError(f"{_fullname(membership)} n'est pas pointé à cette séance.")
    # C-Q4 : seule l'inaptitude bloque (dette, suspension, attente d'adhésion : mesurables).
    if _get_medical_unfitness(membership, at_date=event.event_date) is not None:
        raise SportValidationError(f"{_fullname(membership)} est inapte : il ne peut pas être mesuré.")


def _result_snapshot(result) -> dict:
    return {
        "outcome": result.outcome,
        "status": result.status,
        "time_ms": result.time_ms,
        "distance_m": str(result.distance_m) if result.distance_m is not None else None,
        "count": result.count,
        "value": str(result.value) if result.value is not None else None,
    }


def _bulk_item(membership_id, outcome: str, message: str, result=None, warning: str = "") -> dict:
    return {"membership_id": membership_id, "outcome": outcome, "message": message, "warning": warning,
            "result": result}


def _ensure_measure_window(event: Event, actor) -> None:
    if getattr(actor, "is_superuser", False):
        return
    if is_evaluation_locked(event):
        hours = _club_settings(event.club).evaluation_window_hours
        raise SportValidationError(
            f"La période de saisie des mesures ({hours} h après le début de la séance) est terminée."
        )


def record_results(
    *, event: Event, test: PerformanceTest, method: str, items, actor, start_mode: str = "", client_uuid=None
) -> dict:
    """Enregistre des mesures pour des joueurs pointés d'une séance (Coach,
    Assistant). Chaque joueur est traité dans sa propre transaction : un
    refus n'arrête pas les autres. Idempotent par ``client_uuid`` (celui de
    l'envoi et celui de chaque mesure) : un renvoi après coupure réseau
    renvoie « skipped » sans rien dupliquer.

    Refus du lot entier (exceptions) : SportPermissionError, SportValidationError."""

    club = event.club
    _ensure_manager(actor, club)
    if event.kind != Event.Kind.SESSION:
        raise SportValidationError("Les mesures se font pendant une séance d'entraînement.")
    if test.club_id != event.club_id:
        raise SportValidationError("Ce test n'existe pas dans ce club.")
    if test.archived_at is not None:
        raise SportValidationError("Ce test est archivé : il n'est plus proposé pour de nouvelles mesures.")
    if method not in PerformanceRun.Method.values:
        raise SportValidationError("Choisissez une méthode : chronomètre ou saisie manuelle.")
    if method == PerformanceRun.Method.STOPWATCH and test.kind not in (Kind.TIMED_DISTANCE, Kind.DISTANCE_IN_TIME):
        raise SportValidationError("Le chronomètre n'est pas disponible pour ce type de test.")
    if start_mode and start_mode not in PerformanceRun.StartMode.values:
        raise SportValidationError("Choisissez un départ groupé ou un départ un par un.")
    stored_start_mode = ""
    if method == PerformanceRun.Method.STOPWATCH and test.kind == Kind.TIMED_DISTANCE:
        stored_start_mode = start_mode or PerformanceRun.StartMode.GROUP

    items = list(items or [])
    if not items:
        raise SportValidationError("Cochez au moins un joueur.")
    if len(items) > BULK_MAX_ITEMS:
        raise SportValidationError(
            f"Un envoi ne peut pas dépasser {BULK_MAX_ITEMS} joueurs. Envoyez plusieurs lots."
        )
    window_error = None
    try:
        _ensure_measure_window(event, actor)
    except SportValidationError as exc:
        window_error = str(exc)

    run = None
    if client_uuid is not None:
        run = PerformanceRun.all_objects.filter(club=club, client_uuid=client_uuid).first()
        if run is not None and (run.event_id != event.pk or run.test_id != test.pk):
            raise SportValidationError("Cet identifiant d'envoi est déjà utilisé pour une autre mesure.")

    run_preexisting = run is not None
    member_ids = {item["membership_id"] for item in items}
    members = {
        m.pk: m for m in Membership.all_objects.filter(club=club, pk__in=member_ids).select_related("user")
    }
    pointed_ids = set(
        Attendance.all_objects.filter(
            club=club,
            event=event,
            status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE_ABSENT],
        ).values_list("membership_id", flat=True)
    )

    results = []
    for item in items:
        membership_id = item["membership_id"]
        membership = members.get(membership_id)
        item_uuid = item.get("client_uuid")
        if item_uuid is not None:
            existing = PerformanceResult.all_objects.filter(club=club, client_uuid=item_uuid).select_related(
                "run"
            ).first()
            if existing is not None:
                if existing.membership_id != membership_id or existing.run.test_id != test.pk:
                    results.append(_bulk_item(
                        membership_id, "refused", "Cet identifiant de mesure est déjà utilisé pour un autre joueur."
                    ))
                else:
                    results.append(_bulk_item(membership_id, "skipped", "Mesure déjà enregistrée.", existing))
                continue
        if membership is None:
            results.append(_bulk_item(membership_id, "refused", "Ce joueur n'existe pas dans ce club."))
            continue
        if window_error is not None:
            results.append(_bulk_item(membership_id, "refused", window_error))
            continue
        try:
            _ensure_measurable(event, membership, pointed_ids)
            values = _validate_values(test, item)
        except SportError as exc:
            results.append(_bulk_item(membership_id, "refused", str(exc)))
            continue
        run_before = run
        try:
            with transaction.atomic():
                if run is None:
                    run = PerformanceRun(
                        club=club, event=event, test=test, method=method, start_mode=stored_start_mode,
                        recorded_by=actor, client_uuid=client_uuid,
                    )
                    run.save()
                used = dict(
                    PerformanceResult.all_objects.filter(
                        club=club, run__event=event, run__test=test, membership=membership
                    ).values_list("attempt_no", "run_id")
                )
                requested = item.get("attempt_no")
                if requested and not (requested in used and used[requested] == run.pk):
                    attempt_no = requested if requested not in used else max(used) + 1
                elif requested:
                    results.append(_bulk_item(membership_id, "skipped", "Mesure déjà enregistrée."))
                    continue
                elif run_preexisting and run.pk in used.values():
                    # Renvoi d'un envoi déjà reçu : ce joueur a déjà sa mesure dans cette épreuve.
                    results.append(_bulk_item(membership_id, "skipped", "Mesure déjà enregistrée."))
                    continue
                else:
                    attempt_no = (max(used) + 1) if used else 1
                result = PerformanceResult(
                    club=club, run=run, membership=membership, attempt_no=attempt_no,
                    client_uuid=item_uuid, **values,
                )
                result.save()
                log_action(
                    actor=actor, club=club, action_type="sport.performance_result_recorded", obj=result,
                    after={
                        **_result_snapshot(result),
                        "test_id": test.pk,
                        "event_id": event.pk,
                        "membership_id": membership.pk,
                        "attempt_no": attempt_no,
                        "method": method,
                        "run_id": run.pk,
                        "batch_size": len(items),
                    },
                )
        except (IntegrityError, ValidationError) as exc:
            run = run_before
            if isinstance(exc, ValidationError):
                results.append(_bulk_item(membership_id, "refused", "Mesure non enregistrée : valeur invalide."))
                continue
            existing = (
                PerformanceResult.all_objects.filter(club=club, client_uuid=item_uuid).first() if item_uuid else None
            )
            if existing is not None:
                results.append(_bulk_item(membership_id, "skipped", "Mesure déjà enregistrée.", existing))
            else:
                results.append(_bulk_item(membership_id, "refused", "Mesure non enregistrée. Réessayez."))
            continue
        results.append(_bulk_item(
            membership_id, "created", "Mesure enregistrée.", result, warning=_implausible_warning(test, values)
        ))
    counts = {key: sum(1 for r in results if r["outcome"] == key) for key in ("created", "skipped", "refused")}
    return {"run_id": run.pk if run is not None else None, "results": results, "counts": counts}


# ---------------------------------------------------------------------------
# Correction et retrait
# ---------------------------------------------------------------------------


def _ensure_correctable(result: PerformanceResult, actor) -> None:
    _ensure_manager(actor, result.club)
    if result.status == PerformanceResult.Status.VOIDED:
        raise SportValidationError("Ce résultat a été retiré : il ne peut plus être corrigé.")
    if not getattr(actor, "is_superuser", False) and is_evaluation_locked(result.run.event):
        raise SportValidationError("Résultat verrouillé (plus de 48 heures).")


def _clean_reason(reason) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise SportValidationError("Indiquez le motif.")
    if len(reason) > 500:
        raise SportValidationError("Le motif ne doit pas dépasser 500 caractères.")
    return reason


def correct_result(*, result: PerformanceResult, actor, reason: str, data: dict) -> PerformanceResult:
    """Corrige la valeur d'un résultat (Coach, Assistant, pendant la fenêtre
    des évaluations). Crée une ligne de correction (anciennes et nouvelles
    valeurs, motif, auteur) et écrit au journal. Le résultat n'est jamais
    supprimé."""

    with transaction.atomic():
        result = (
            PerformanceResult.all_objects.select_for_update().select_related("run__event", "run__test", "club")
            .get(pk=result.pk)
        )
        _ensure_correctable(result, actor)
        reason = _clean_reason(reason)
        test = result.run.test
        new_values = _validate_values(test, data)
        before = _result_snapshot(result)
        if all(getattr(result, key) == new_values[key] for key in new_values):
            raise SportValidationError("Aucun changement : la valeur est identique.")
        correction = PerformanceResultCorrection(
            club=result.club, result=result, reason=reason, actor=actor,
            old_time_ms=result.time_ms, old_distance_m=result.distance_m, old_count=result.count,
            old_value=result.value, old_outcome=result.outcome, old_status=result.status,
            new_time_ms=new_values["time_ms"], new_distance_m=new_values["distance_m"],
            new_count=new_values["count"], new_value=new_values["value"], new_outcome=new_values["outcome"],
            new_status=result.status,
        )
        correction.save()
        for key, value in new_values.items():
            setattr(result, key, value)
        result.save()
        log_action(
            actor=actor, club=result.club, action_type="sport.performance_result_corrected", obj=result,
            before=before, after={**_result_snapshot(result), "reason": reason, "correction_id": correction.pk},
        )
    return result


def void_result(*, result: PerformanceResult, actor, reason: str) -> PerformanceResult:
    """Retire un résultat (il ne sera plus compté) : statut « Retiré », motif
    obligatoire, historique conservé. Jamais de suppression physique."""

    with transaction.atomic():
        result = (
            PerformanceResult.all_objects.select_for_update().select_related("run__event", "run__test", "club")
            .get(pk=result.pk)
        )
        _ensure_correctable(result, actor)
        reason = _clean_reason(reason)
        before = _result_snapshot(result)
        correction = PerformanceResultCorrection(
            club=result.club, result=result, reason=reason, actor=actor,
            old_time_ms=result.time_ms, old_distance_m=result.distance_m, old_count=result.count,
            old_value=result.value, old_outcome=result.outcome, old_status=result.status,
            new_time_ms=result.time_ms, new_distance_m=result.distance_m, new_count=result.count,
            new_value=result.value, new_outcome=result.outcome, new_status=PerformanceResult.Status.VOIDED,
        )
        correction.save()
        result.status = PerformanceResult.Status.VOIDED
        result.save()
        log_action(
            actor=actor, club=result.club, action_type="sport.performance_result_voided", obj=result,
            before=before, after={**_result_snapshot(result), "reason": reason, "correction_id": correction.pk},
        )
    return result


# ---------------------------------------------------------------------------
# Lecture : résultats d'une séance, classement, évolution, « mes mesures »
# ---------------------------------------------------------------------------


def _active_done(club, **filters):
    return PerformanceResult.all_objects.filter(
        club=club, status=PerformanceResult.Status.ACTIVE, outcome=PerformanceResult.Outcome.DONE, **filters
    )


def _best(test: PerformanceTest, results):
    """Meilleur essai (C-Q5) ; à valeur égale, le plus ancien."""

    best, best_value = None, None
    for result in sorted(results, key=lambda r: (r.created_at, r.pk)):
        value = sort_value(test, result)
        if value is None:
            continue
        if best is None or _is_better(test, value, best_value):
            best, best_value = result, value
    return best


def _rank(test: PerformanceTest, entries):
    """``entries`` : liste de (objet, valeur brute). Rang « compétition »."""

    ordered = sorted(entries, key=lambda pair: pair[1], reverse=test.higher_is_better)
    ranked, previous, rank = [], None, 0
    for index, (obj, value) in enumerate(ordered, start=1):
        if value != previous:
            rank, previous = index, value
        ranked.append((rank, obj, value))
    return ranked


def _brief(membership, request):
    from apps.sport.serializers import serialize_membership_brief

    return serialize_membership_brief(membership, request=request)


def _actor_name(user, viewer) -> dict:
    from apps.sport.serializers import _actor

    return _actor(user, viewer=viewer)


def get_event_results(*, event: Event, test: PerformanceTest, viewer, viewer_membership, sees_all: bool, request=None) -> dict:
    """Résultats d'un test pour une séance (C6.4). Le staff voit le classement ;
    tout autre joueur ne voit que sa propre ligne et son meilleur résultat."""

    club = event.club
    queryset = PerformanceResult.all_objects.filter(
        club=club, run__event=event, run__test=test, status=PerformanceResult.Status.ACTIVE
    ).select_related("run", "membership__user", "run__recorded_by")
    if not sees_all:
        queryset = queryset.filter(membership=viewer_membership) if viewer_membership else queryset.none()
    rows = list(queryset.order_by("created_at", "pk"))

    by_member: dict[int, list] = defaultdict(list)
    for result in rows:
        by_member[result.membership_id].append(result)

    scored = []
    for membership_id, member_results in by_member.items():
        best = _best(test, member_results)
        if best is not None:
            scored.append((best, sort_value(test, best)))
    ranked = _rank(test, scored)
    historic_best = _historic_best_by_member(club, test, set(by_member))

    entries = []
    for rank, best, _value in ranked:
        attempts = by_member[best.membership_id]
        record = historic_best.get(best.membership_id)
        entries.append(
            {
                "id": best.pk,
                "rank": rank,
                "player": _brief(best.membership, request),
                "attempt_no": best.attempt_no,
                "attempts_count": len(attempts),
                "attempts": [
                    {"id": a.pk, "attempt_no": a.attempt_no, **serialize_result_value(test, a)}
                    for a in sorted(attempts, key=lambda a: a.attempt_no)
                ],
                "method": best.run.method,
                "method_label": best.run.get_method_display(),
                "personal_record": record is not None and record.pk == best.pk,
                "recorded_by": _actor_name(best.run.recorded_by, viewer),
                "recorded_at": best.created_at,
                **serialize_result_value(test, best),
            }
        )
    dnf = [
        {
            "id": result.pk,
            "player": _brief(result.membership, request),
            "attempt_no": result.attempt_no,
            "method": result.run.method,
            **serialize_result_value(test, result),
        }
        for result in rows
        if result.outcome == PerformanceResult.Outcome.DNF
        and not any(r.outcome == PerformanceResult.Outcome.DONE for r in by_member[result.membership_id])
    ]
    values = [value for _rank_, _best_, value in ranked]
    summary = {"measured_count": len(entries), "best": None, "average": None}
    if entries:
        summary["best"] = entries[0]["display"]
        if test.kind == Kind.TIMED_DISTANCE:
            average = sum(values, Decimal(0)) / Decimal(len(values))
            summary["average"] = format_time_ms(int(average.quantize(Decimal(1), rounding=ROUND_HALF_UP)))
        elif test.kind == Kind.DISTANCE_IN_TIME:
            average = sum(values, Decimal(0)) / Decimal(len(values))
            summary["average"] = f"{_fmt_number(average, 0)}{_NBSP}m"
        elif test.kind == Kind.REPETITIONS:
            summary["average"] = _fmt_number(sum(values, Decimal(0)) / Decimal(len(values)), 1)
        else:
            average = sum(values, Decimal(0)) / Decimal(len(values))
            summary["average"] = f"{_fmt_number(average, test.decimals)}{_NBSP}{_UNIT_SYMBOLS.get(test.unit, '')}".strip()
    payload = {
        "event_id": event.pk,
        "date": event.event_date,
        "test": describe_test(test),
        "scope": "all" if sees_all else "mine",
        "summary": summary,
        "results": entries,
        "dnf": dnf,
        "window_open": not is_evaluation_locked(event),
    }
    if not sees_all and viewer_membership is not None:
        mine_best = _historic_best_by_member(club, test, {viewer_membership.pk}).get(viewer_membership.pk)
        payload["my_best_overall"] = (
            {
                "display": display_value(test, mine_best),
                "date": mine_best.run.event.event_date,
                **serialize_result_value(test, mine_best),
            }
            if mine_best is not None
            else None
        )
    return payload


def _historic_best_by_member(club, test: PerformanceTest, membership_ids) -> dict[int, PerformanceResult]:
    results = _active_done(club, run__test=test, membership_id__in=list(membership_ids)).select_related(
        "run__event", "run__test"
    )
    grouped: dict[int, list] = defaultdict(list)
    for result in results:
        grouped[result.membership_id].append(result)
    return {mid: _best(test, items) for mid, items in grouped.items()}


def _chronological(results):
    return sorted(results, key=lambda r: (r.run.event.event_date, r.created_at, r.pk))


def _trend(test: PerformanceTest, results) -> Optional[dict]:
    ordered = _chronological(results)
    if len(ordered) < 2:
        return None
    delta = sort_value(test, ordered[-1]) - sort_value(test, ordered[-2])
    direction = _direction(test, delta)
    amount = format_delta(test, delta)
    text = {"progress": f"en progrès de {amount}", "regress": f"en recul de {amount}", "stable": "stable"}[direction]
    return {"direction": direction, "delta": str(delta), "delta_display": amount, "text": text}


def get_leaderboard(*, club, test: PerformanceTest, period: str, request=None) -> dict:
    """Classement d'un test (C6.5) : « last » = dernière séance où le test a été
    mesuré ; « season » = meilleur résultat de chaque joueur sur la saison
    courante. Meilleur essai de chaque joueur (C-Q5)."""

    if period not in ("last", "season"):
        raise SportValidationError("Période invalide : choisissez « Dernière séance » ou « Saison ».")
    results = list(_active_done(club, run__test=test).select_related("run__event", "membership__user"))
    event_ref = None
    if period == "last":
        if results:
            event_ref = max((r.run.event for r in results), key=lambda e: (e.event_date, e.pk))
            scope = [r for r in results if r.run.event_id == event_ref.pk]
        else:
            scope = []
    else:
        from apps.sport.session_stats import _current_season

        season = _current_season(club)
        scope = [r for r in results if season is not None and r.run.event.season_id == season.pk]
    by_member_scope: dict[int, list] = defaultdict(list)
    for result in scope:
        by_member_scope[result.membership_id].append(result)
    by_member_all: dict[int, list] = defaultdict(list)
    for result in results:
        by_member_all[result.membership_id].append(result)
    all_best = {mid: _best(test, items) for mid, items in by_member_all.items()}

    scored = []
    for mid, items in by_member_scope.items():
        best = _best(test, items)
        scored.append((best, sort_value(test, best)))
    rows = []
    for rank, best, _value in _rank(test, scored):
        mid = best.membership_id
        rows.append(
            {
                "rank": rank,
                "player": _brief(best.membership, request),
                "result_id": best.pk,
                "event_id": best.run.event_id,
                "date": best.run.event.event_date,
                "measures_count": len(by_member_scope[mid]),
                "trend": _trend(test, by_member_all[mid]),
                "personal_record": all_best[mid].pk == best.pk,
                **serialize_result_value(test, best),
            }
        )
    return {
        "test": describe_test(test),
        "period": period,
        "event": {"id": event_ref.pk, "date": event_ref.event_date} if event_ref else None,
        "results": rows,
    }


def get_player_evolution(*, membership: Membership, test: PerformanceTest, request=None) -> dict:
    """Évolution d'un joueur sur un test (C6.7) : meilleur, dernier, progression
    depuis la première mesure, courbe (meilleur essai de chaque séance), liste
    des mesures."""

    results = list(
        _active_done(membership.club_id, run__test=test, membership=membership).select_related(
            "run__event", "run__recorded_by"
        )
    )
    ordered = _chronological(results)
    best_overall = _best(test, results)
    by_event: dict[int, list] = defaultdict(list)
    for result in ordered:
        by_event[result.run.event_id].append(result)
    points = []
    for event_id, items in by_event.items():
        best = _best(test, items)
        points.append(
            {
                "event_id": event_id,
                "date": best.run.event.event_date,
                "result_id": best.pk,
                "sort_value": str(sort_value(test, best)),
                **serialize_result_value(test, best),
            }
        )
    points.sort(key=lambda p: (p["date"], p["event_id"]))
    progression = None
    if len(points) >= 2:
        delta = Decimal(points[-1]["sort_value"]) - Decimal(points[0]["sort_value"])
        direction = _direction(test, delta)
        amount = format_delta(test, delta)
        word = {"progress": f"en progrès de {amount}", "regress": f"en recul de {amount}", "stable": "stable"}[direction]
        progression = {
            "direction": direction,
            "delta": str(delta),
            "delta_display": amount,
            "text": f"{word} depuis la première mesure" if direction != "stable" else "stable depuis la première mesure",
            "legend": "Plus bas = plus rapide" if test.kind == Kind.TIMED_DISTANCE else "",
        }
    last = ordered[-1] if ordered else None
    return {
        "membership": _brief(membership, request),
        "test": describe_test(test),
        "best": (
            {"date": best_overall.run.event.event_date, "result_id": best_overall.pk,
             **serialize_result_value(test, best_overall)} if best_overall else None
        ),
        "last": (
            {"date": last.run.event.event_date, "result_id": last.pk, **serialize_result_value(test, last)}
            if last else None
        ),
        "progression": progression,
        "points": points,
        "results": [
            {
                "id": r.pk,
                "event_id": r.run.event_id,
                "date": r.run.event.event_date,
                "attempt_no": r.attempt_no,
                "method": r.run.method,
                "method_label": r.run.get_method_display(),
                "personal_record": best_overall is not None and best_overall.pk == r.pk,
                **serialize_result_value(test, r),
            }
            for r in reversed(ordered)
        ],
    }


def get_player_overview(*, membership: Membership, request=None) -> dict:
    """« Mes tests » : une ligne par test où le joueur a au moins un résultat
    (meilleur, dernier). Jamais de donnée des autres joueurs."""

    results = list(
        _active_done(membership.club_id, membership=membership).select_related("run__event", "run__test")
    )
    by_test: dict[int, list] = defaultdict(list)
    for result in results:
        by_test[result.run.test_id].append(result)
    tests = []
    for items in by_test.values():
        test = items[0].run.test
        best = _best(test, items)
        last = _chronological(items)[-1]
        tests.append(
            {
                "test": describe_test(test, has_results=True),
                "best": {"date": best.run.event.event_date, **serialize_result_value(test, best)},
                "last": {"date": last.run.event.event_date, **serialize_result_value(test, last)},
                "results_count": len(items),
            }
        )
    tests.sort(key=lambda row: row["test"]["name"].lower())
    return {"membership": _brief(membership, request), "tests": tests}


def get_tests_overview(*, club, include_archived: bool = False) -> list[dict]:
    """Carte « Tests de performance » (C5, staff) : une ligne par test, dernière
    mesure et meilleur résultat de la saison."""

    queryset = PerformanceTest.all_objects.filter(club=club)
    queryset = queryset.exclude(archived_at__isnull=True) if include_archived == "only" else (
        queryset if include_archived else queryset.filter(archived_at__isnull=True)
    )
    tests = list(queryset.order_by("name"))
    if not tests:
        return []
    from apps.sport.session_stats import _current_season

    season = _current_season(club)
    results = list(
        _active_done(club, run__test__in=tests).select_related("run__event", "membership__user")
    )
    by_test: dict[int, list] = defaultdict(list)
    for result in results:
        by_test[result.run.test_id].append(result)
    rows = []
    for test in tests:
        items = by_test.get(test.pk, [])
        last_event = max((r.run.event for r in items), key=lambda e: (e.event_date, e.pk), default=None)
        season_items = [r for r in items if season is not None and r.run.event.season_id == season.pk]
        best = _best(test, season_items)
        rows.append(
            {
                **describe_test(test, has_results=bool(items)),
                "last_measured_on": last_event.event_date if last_event else None,
                "last_measured_count": (
                    len({r.membership_id for r in items if r.run.event_id == last_event.pk}) if last_event else 0
                ),
                "season_best": (
                    {
                        "player": {
                            "membership_id": best.membership_id,
                            "name": _fullname(best.membership),
                        },
                        **serialize_result_value(test, best),
                    }
                    if best
                    else None
                ),
            }
        )
    return rows


def get_result_detail(*, result: PerformanceResult, viewer, request=None) -> dict:
    test = result.run.test
    corrections = list(result.corrections.select_related("actor").order_by("created_at", "pk"))

    def snapshot(prefix: str, correction) -> dict:
        proxy = type("Proxy", (), {})()
        proxy.outcome = getattr(correction, f"{prefix}_outcome")
        proxy.time_ms = getattr(correction, f"{prefix}_time_ms")
        proxy.distance_m = getattr(correction, f"{prefix}_distance_m")
        proxy.count = getattr(correction, f"{prefix}_count")
        proxy.value = getattr(correction, f"{prefix}_value")
        return {"status": getattr(correction, f"{prefix}_status"), **serialize_result_value(test, proxy)}

    return {
        "id": result.pk,
        "event_id": result.run.event_id,
        "date": result.run.event.event_date,
        "test": describe_test(test),
        "player": _brief(result.membership, request),
        "attempt_no": result.attempt_no,
        "method": result.run.method,
        "method_label": result.run.get_method_display(),
        "status": result.status,
        "recorded_by": _actor_name(result.run.recorded_by, viewer),
        "recorded_at": result.created_at,
        "locked": is_evaluation_locked(result.run.event),
        **serialize_result_value(test, result),
        "corrections": [
            {
                "id": c.pk,
                "actor": _actor_name(c.actor, viewer),
                "created_at": c.created_at,
                "reason": c.reason,
                "before": snapshot("old", c),
                "after": snapshot("new", c),
            }
            for c in corrections
        ],
    }


def session_measures_summary(event: Event, *, sees_all: bool, viewer_membership: Optional[Membership]) -> list[dict]:
    """Carte « Mesures de la séance » (A4.3) : une ligne par test mesuré. Le
    staff voit le nombre de joueurs mesurés et le meilleur résultat ; tout
    autre joueur ne voit que ses propres mesures (résultats non publics)."""

    queryset = _active_done(event.club_id, run__event=event).select_related("run__test", "membership__user")
    if not sees_all:
        if viewer_membership is None:
            return []
        queryset = queryset.filter(membership=viewer_membership)
    by_test: dict[int, list] = defaultdict(list)
    for result in queryset:
        by_test[result.run.test_id].append(result)
    summary = []
    for items in by_test.values():
        test = items[0].run.test
        best = _best(test, items)
        summary.append(
            {
                "test_id": test.pk,
                "name": test.name,
                "kind": test.kind,
                "measured_count": len({r.membership_id for r in items}),
                "best": (
                    {
                        "player": {"membership_id": best.membership_id, "name": _fullname(best.membership)},
                        **serialize_result_value(test, best),
                    }
                    if best
                    else None
                ),
            }
        )
    summary.sort(key=lambda row: row["name"].lower())
    return summary


# ---------------------------------------------------------------------------
# Notification « Vos mesures sont disponibles » (C-Q9, provisoire)
# ---------------------------------------------------------------------------


def notify_performance_results(*, club, now=None) -> int:
    """Une notification in-app par joueur et par séance, 1 h après la dernière
    mesure de la séance (commande cron ``notify_performance_results``).
    Idempotente : un joueur déjà notifié pour une séance ne l'est plus."""

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification
    from apps.sport.services import get_club_today

    now = now or timezone.now()
    since = get_club_today(club, now=now) - timedelta(days=NOTIFICATION_LOOKBACK_DAYS)
    runs = (
        PerformanceResult.all_objects.filter(
            club=club, status=PerformanceResult.Status.ACTIVE, outcome=PerformanceResult.Outcome.DONE,
            run__event__event_date__gte=since,
        )
        .select_related("run__event", "membership__user")
        .order_by("created_at")
    )
    by_event: dict[int, list] = defaultdict(list)
    events: dict[int, Event] = {}
    for result in runs:
        by_event[result.run.event_id].append(result)
        events[result.run.event_id] = result.run.event
    sent = 0
    for event_id, results in by_event.items():
        if max(r.created_at for r in results) > now - NOTIFICATION_DELAY:
            continue
        event = events[event_id]
        message = f"Vos mesures de la séance du {event.event_date.strftime('%d/%m/%Y')} sont disponibles."
        for membership_id in {r.membership_id for r in results}:
            membership = next(r.membership for r in results if r.membership_id == membership_id)
            if membership.status != Membership.Status.ACTIVE:
                continue
            already = Notification.objects.filter(
                recipient=membership.user,
                event_type=Notification.EventType.PERFORMANCE_RESULTS_AVAILABLE,
                link_object_type="Event",
                link_object_id=event.pk,
            ).exists()
            if already:
                continue
            create_notification(
                recipient=membership.user,
                event_type=Notification.EventType.PERFORMANCE_RESULTS_AVAILABLE,
                message=message,
                club=club,
                target=event,
                now=now,
            )
            sent += 1
    return sent
