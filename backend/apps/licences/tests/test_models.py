"""Tests des modeles de l'app licences (taches 1.2, 1.8).

Sources : CDC 1.4, 2.5, 4.18, 5.4 ; 10.2 n19/n20/n26 ;
docs/lot0/schema-donnees.md §4.5, §4.6, §13.1.
"""

from __future__ import annotations

import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.clubs.tests.factories import ClubFactory
from apps.licences.models import Licence, LicenceEvent, SupportSession
from apps.licences.tests.factories import LicenceEventFactory, LicenceFactory, SupportSessionFactory


@pytest.mark.django_db
class TestLicence:
    def test_licence_definie_uniquement_par_ses_dates(self):
        licence = LicenceFactory()
        assert licence.status == Licence.Status.TRIAL
        assert licence.end_date >= licence.start_date
        # Pas de formule ni de tarif (10.2 n20) : aucun champ `plan` sur ce modele.
        assert not hasattr(licence, "plan")

    def test_seul_un_superuser_peut_creer_une_licence(self):
        club = ClubFactory()
        joueur_normal = UserFactory(is_superuser=False)
        licence = Licence(
            club=club,
            start_date=datetime.date.today(),
            end_date=datetime.date.today() + datetime.timedelta(days=30),
            created_by=joueur_normal,
        )
        with pytest.raises(ValidationError):
            licence.full_clean()

    def test_end_date_avant_start_date_rejetee_par_contrainte_db(self):
        club = ClubFactory()
        with pytest.raises(IntegrityError), transaction.atomic():
            Licence.objects.create(
                club=club,
                start_date=datetime.date.today(),
                end_date=datetime.date.today() - datetime.timedelta(days=1),
                created_by=UserFactory(is_superuser=True),
            )

    def test_pas_de_gestionnaire_tenant_aware_cote_club(self):
        """Licence n'est pas un `TenantModel` : gestion reservee au Superuser (schema §4.5)."""

        assert not hasattr(Licence, "all_objects")


@pytest.mark.django_db
class TestLicenceEvent:
    """Schema §4.6 : historique metier d'une licence (CDC 2.5 « historique »)."""

    def test_evenement_lie_a_une_licence(self):
        event = LicenceEventFactory(event_type=LicenceEvent.EventType.ACTIVATED)
        assert event.licence is not None
        assert event.event_type == LicenceEvent.EventType.ACTIVATED

    def test_acteur_facultatif_pour_une_relance_automatique(self):
        """schema §4.6 : `actor` facultatif, vide pour une relance automatique."""

        event = LicenceEventFactory(actor=None, event_type=LicenceEvent.EventType.REMINDER_SENT)
        assert event.actor_id is None

    def test_acteur_doit_etre_un_superuser_si_renseigne(self):
        licence = LicenceFactory()
        joueur_normal = UserFactory(is_superuser=False)
        event = LicenceEvent(
            licence=licence,
            event_type=LicenceEvent.EventType.ACTIVATED,
            event_date=timezone.now(),
            actor=joueur_normal,
        )
        with pytest.raises(ValidationError):
            event.full_clean()

    def test_aucune_valeur_expiree_dans_l_enumeration(self):
        """schema §4.6 : l'enumeration ne contient PAS de valeur "expiree"
        -- lecture volontaire, voir docstring de
        `apps.licences.services.process_licence_expirations`."""

        values = {choice.value for choice in LicenceEvent.EventType}
        assert "expired" not in values
        assert values == {
            "created",
            "activated",
            "extended",
            "suspended",
            "resumed",
            "terminated",
            "reminder_sent",
        }


@pytest.mark.django_db
class TestSupportSession:
    """Schema §13.1 : session de support en Ghost Mode (CDC 4.18, 5.4)."""

    def test_expires_at_calcule_a_60_minutes(self):
        started_at = timezone.now()
        session = SupportSessionFactory(started_at=started_at)
        assert session.expires_at == started_at + datetime.timedelta(minutes=60)

    def test_expires_at_n_est_jamais_modifiable_directement(self):
        """schema §13.1 : `expires_at` est calcule, jamais une valeur de confiance."""

        session = SupportSessionFactory()
        original_expires_at = session.expires_at

        session.expires_at = original_expires_at + datetime.timedelta(days=1)
        session.save()

        session.refresh_from_db()
        assert session.expires_at == session.started_at + datetime.timedelta(minutes=60)
        assert session.expires_at != original_expires_at + datetime.timedelta(days=1)

    def test_superuser_est_obligatoire(self):
        club = ClubFactory()
        joueur_normal = UserFactory(is_superuser=False)
        with pytest.raises(ValidationError):
            SupportSession.objects.create(club=club, superuser=joueur_normal, reason="Motif de test.")

    def test_motif_obligatoire(self):
        club = ClubFactory()
        superuser = SuperuserFactory()
        with pytest.raises(ValidationError):
            SupportSession.objects.create(club=club, superuser=superuser, reason="   ")

    def test_fin_anticipee_ne_peut_pas_preceder_le_debut(self):
        started_at = timezone.now()
        session = SupportSessionFactory(started_at=started_at)
        session.ended_at = started_at - datetime.timedelta(minutes=5)
        with pytest.raises(ValidationError):
            session.save()
