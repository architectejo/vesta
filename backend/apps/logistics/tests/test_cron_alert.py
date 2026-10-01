"""Test de la commande cron d'alerte hebdomadaire (CDC 4.13, schema §17)."""

from __future__ import annotations

import datetime

import pytest
from django.core.management import call_command

from apps.core.tenant import active_club
from apps.logistics import services
from apps.logistics.models import Article
from apps.logistics.tests.conftest import LogisticsClubContext
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def test_send_inventory_open_alerts_command(ctx: LogisticsClubContext):
    with active_club(ctx.club):
        services.create_article(club=ctx.club, actor=ctx.steward.user, name="Ballon", category=Article.Category.BALLS)
        q1 = datetime.datetime(2026, 2, 15, 12, 0, tzinfo=datetime.timezone.utc)
        services.open_inventory(club=ctx.club, actor=ctx.steward.user, now=q1)

    # L'inventaire a été ouvert pour le 1er trimestre 2026 (point ouvert
    # n° 11 : le blocage/l'alerte ne s'appliquent qu'une fois SON propre
    # trimestre terminé) ; la date réelle du test est postérieure à ce
    # trimestre, donc l'alerte est due.
    call_command("send_inventory_open_alerts", f"--club={ctx.club.pk}")
    assert Notification.objects.filter(
        event_type=Notification.EventType.INVENTORY_OPEN_ALERT, recipient=ctx.president.user
    ).count() == 1

    # Rejouée immédiatement : aucun doublon dans la même semaine.
    call_command("send_inventory_open_alerts", f"--club={ctx.club.pk}")
    assert Notification.objects.filter(
        event_type=Notification.EventType.INVENTORY_OPEN_ALERT, recipient=ctx.president.user
    ).count() == 1
