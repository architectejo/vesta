"""Tests des transitions automatiques (CDC 1.4 ; 10.2 n19 ; tache 1.8).

Sources : docs/cahier-des-charges.md 1.4 ; 10.2 n19 ;
docs/lot0/schema-donnees.md §4.5, §4.6.
"""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.clubs.models import Club, MembershipRole
from apps.clubs.tests.factories import ClubFactory, MembershipFactory, MembershipRoleFactory
from apps.licences.models import Licence, LicenceEvent
from apps.licences.services import process_licence_expirations, process_licence_reminders
from apps.licences.tests.factories import LicenceFactory
from apps.notifications.models import Notification


@pytest.mark.django_db
class TestProcessLicenceExpirations:
    def test_licence_active_expiree_au_dela_de_la_grace_passe_expiree(self):
        now = timezone.now()
        club = ClubFactory(status=Club.Status.ACTIVE)
        licence = LicenceFactory(
            club=club,
            status=Licence.Status.ACTIVE,
            start_date=now.date() - datetime.timedelta(days=400),
            end_date=now.date() - datetime.timedelta(days=20),
            grace_period_days=15,
        )

        result = process_licence_expirations(now=now)

        licence.refresh_from_db()
        club.refresh_from_db()
        assert licence.status == Licence.Status.EXPIRED
        assert club.status == Club.Status.READ_ONLY
        assert result == {"expired": 1, "clubs_set_read_only": 1}

    def test_licence_encore_dans_la_periode_de_grace_n_est_pas_touchee(self):
        now = timezone.now()
        club = ClubFactory(status=Club.Status.ACTIVE)
        licence = LicenceFactory(
            club=club,
            status=Licence.Status.ACTIVE,
            start_date=now.date() - datetime.timedelta(days=400),
            end_date=now.date() - datetime.timedelta(days=5),
            grace_period_days=15,
        )

        process_licence_expirations(now=now)

        licence.refresh_from_db()
        club.refresh_from_db()
        assert licence.status == Licence.Status.ACTIVE
        assert club.status == Club.Status.ACTIVE

    def test_idempotent_ne_retraite_pas_une_licence_deja_expiree(self):
        now = timezone.now()
        club = ClubFactory(status=Club.Status.READ_ONLY)
        LicenceFactory(
            club=club,
            status=Licence.Status.EXPIRED,
            start_date=now.date() - datetime.timedelta(days=400),
            end_date=now.date() - datetime.timedelta(days=20),
            grace_period_days=15,
        )

        result = process_licence_expirations(now=now)

        assert result == {"expired": 0, "clubs_set_read_only": 0}

    def test_deux_executions_successives_ne_creent_aucun_doublon(self):
        now = timezone.now()
        club = ClubFactory(status=Club.Status.ACTIVE)
        licence = LicenceFactory(
            club=club,
            status=Licence.Status.ACTIVE,
            start_date=now.date() - datetime.timedelta(days=400),
            end_date=now.date() - datetime.timedelta(days=20),
            grace_period_days=15,
        )

        first = process_licence_expirations(now=now)
        second = process_licence_expirations(now=now)

        assert first == {"expired": 1, "clubs_set_read_only": 1}
        assert second == {"expired": 0, "clubs_set_read_only": 0}
        licence.refresh_from_db()
        assert licence.status == Licence.Status.EXPIRED

    def test_aucune_licenceevent_ni_auditlog_pour_cette_transition(self):
        """Lecture volontaire du schema §4.6 (pas de valeur "expiree") et
        absence d'acteur reel (meme choix que
        `process_sponsor_reminders_and_alerts`)."""

        now = timezone.now()
        club = ClubFactory(status=Club.Status.ACTIVE)
        licence = LicenceFactory(
            club=club,
            status=Licence.Status.ACTIVE,
            start_date=now.date() - datetime.timedelta(days=400),
            end_date=now.date() - datetime.timedelta(days=20),
            grace_period_days=15,
        )

        process_licence_expirations(now=now)

        assert not LicenceEvent.objects.filter(licence=licence).exists()
        assert not AuditLog.objects.filter(object_type="Licence", object_id=str(licence.pk)).exists()

    def test_frontiere_exacte_le_dernier_jour_de_grace_n_expire_pas_encore(self):
        """Priorite n1/n2 de la revue : inegalite stricte/large exacte sur
        la periode de grace. Exactement `grace_period_days` jours apres
        `end_date` (aujourd'hui == cutoff), le club doit encore avoir
        acces -- l'expiration ne doit intervenir qu'APRES ce jour, jamais
        pile ce jour-la."""

        now = timezone.now()
        club = ClubFactory(status=Club.Status.ACTIVE)
        licence = LicenceFactory(
            club=club,
            status=Licence.Status.ACTIVE,
            start_date=now.date() - datetime.timedelta(days=400),
            end_date=now.date() - datetime.timedelta(days=15),
            grace_period_days=15,
        )

        result = process_licence_expirations(now=now)

        licence.refresh_from_db()
        club.refresh_from_db()
        assert result == {"expired": 0, "clubs_set_read_only": 0}
        assert licence.status == Licence.Status.ACTIVE
        assert club.status == Club.Status.ACTIVE

    def test_frontiere_exacte_le_jour_suivant_la_periode_de_grace_expire(self):
        """Contre-preuve du test precedent : UN jour de plus (aujourd'hui
        == cutoff + 1) doit, lui, expirer la licence."""

        now = timezone.now()
        club = ClubFactory(status=Club.Status.ACTIVE)
        licence = LicenceFactory(
            club=club,
            status=Licence.Status.ACTIVE,
            start_date=now.date() - datetime.timedelta(days=400),
            end_date=now.date() - datetime.timedelta(days=16),
            grace_period_days=15,
        )

        result = process_licence_expirations(now=now)

        licence.refresh_from_db()
        club.refresh_from_db()
        assert result == {"expired": 1, "clubs_set_read_only": 1}
        assert licence.status == Licence.Status.EXPIRED
        assert club.status == Club.Status.READ_ONLY

    def test_licence_suspendue_n_est_jamais_touchee(self):
        """Une licence suspendue n'est pas dans le perimetre de cette
        transition (elle bloque deja l'acces independamment des dates)."""

        now = timezone.now()
        club = ClubFactory(status=Club.Status.ACTIVE)
        licence = LicenceFactory(
            club=club,
            status=Licence.Status.SUSPENDED,
            start_date=now.date() - datetime.timedelta(days=400),
            end_date=now.date() - datetime.timedelta(days=20),
            grace_period_days=15,
        )

        process_licence_expirations(now=now)

        licence.refresh_from_db()
        club.refresh_from_db()
        assert licence.status == Licence.Status.SUSPENDED
        assert club.status == Club.Status.ACTIVE


@pytest.mark.django_db
class TestProcessLicenceReminders:
    def _make_president(self, club):
        membership = MembershipFactory(club=club, status="active")
        MembershipRoleFactory(membership=membership, club=club, role=MembershipRole.Role.PRESIDENT)
        return membership

    @pytest.mark.parametrize("days_remaining", [30, 7, 1])
    def test_relance_le_president_au_bon_palier(self, days_remaining):
        now = timezone.now()
        club = ClubFactory()
        president = self._make_president(club)
        licence = LicenceFactory(
            club=club,
            status=Licence.Status.ACTIVE,
            end_date=now.date() + datetime.timedelta(days=days_remaining),
        )

        result = process_licence_reminders(now=now)

        assert result == {"reminders_sent": 1}
        assert Notification.objects.filter(
            recipient=president.user, event_type=Notification.EventType.LICENCE_EXPIRING
        ).exists()
        assert LicenceEvent.objects.filter(
            licence=licence, event_type=LicenceEvent.EventType.REMINDER_SENT, note=f"reminder:{days_remaining}"
        ).exists()

    def test_aucune_relance_hors_palier(self):
        now = timezone.now()
        club = ClubFactory()
        self._make_president(club)
        LicenceFactory(club=club, status=Licence.Status.ACTIVE, end_date=now.date() + datetime.timedelta(days=15))

        result = process_licence_reminders(now=now)

        assert result == {"reminders_sent": 0}

    def test_idempotent_une_seule_relance_par_palier(self):
        now = timezone.now()
        club = ClubFactory()
        president = self._make_president(club)
        LicenceFactory(club=club, status=Licence.Status.ACTIVE, end_date=now.date() + datetime.timedelta(days=30))

        first = process_licence_reminders(now=now)
        second = process_licence_reminders(now=now)

        assert first == {"reminders_sent": 1}
        assert second == {"reminders_sent": 0}
        assert Notification.objects.filter(
            recipient=president.user, event_type=Notification.EventType.LICENCE_EXPIRING
        ).count() == 1

    def test_omet_silencieusement_sans_president_en_poste(self):
        now = timezone.now()
        club = ClubFactory()
        LicenceFactory(club=club, status=Licence.Status.ACTIVE, end_date=now.date() + datetime.timedelta(days=7))

        result = process_licence_reminders(now=now)

        assert result == {"reminders_sent": 1}
        assert Notification.objects.count() == 0

    def test_aucun_auditlog_pour_une_relance_automatique(self):
        now = timezone.now()
        club = ClubFactory()
        self._make_president(club)
        licence = LicenceFactory(club=club, status=Licence.Status.ACTIVE, end_date=now.date() + datetime.timedelta(days=1))

        process_licence_reminders(now=now)

        assert not AuditLog.objects.filter(object_type="Licence", object_id=str(licence.pk)).exists()
