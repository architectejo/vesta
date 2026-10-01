"""Tests du cycle de vie d'une licence (CDC 1.4, 2.5 ; 10.2 n19/n20/n26 ; tache 1.8).

Sources : docs/cahier-des-charges.md 1.4, 2.5, 4.18 ; 10.2 n19, n20, n26 ;
docs/lot0/schema-donnees.md §4.5, §4.6.
"""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.audit.models import AuditLog
from apps.clubs.models import Club
from apps.clubs.tests.factories import ClubFactory
from apps.licences.models import Licence, LicenceEvent
from apps.licences.services import (
    InvalidLicenceTransitionError,
    LicenceTerminationConfirmationError,
    activate_licence,
    extend_licence,
    resume_licence,
    suspend_licence,
    terminate_licence,
)
from apps.licences.tests.factories import LicenceFactory


@pytest.mark.django_db
class TestActivateLicence:
    def test_active_une_licence_en_essai(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.TRIAL)

        activate_licence(superuser=superuser, licence=licence, note="Passage a la formule active.")

        licence.refresh_from_db()
        assert licence.status == Licence.Status.ACTIVE
        assert LicenceEvent.objects.filter(licence=licence, event_type=LicenceEvent.EventType.ACTIVATED).exists()
        assert AuditLog.objects.filter(action_type="licence.activated", object_id=str(licence.pk)).exists()

    def test_une_licence_definie_uniquement_par_deux_dates(self):
        """Critere de fin de la tache 1.8 : « une licence sans formule
        s'attribue avec seulement deux dates »."""

        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.TRIAL)
        nouveau_debut = datetime.date.today()
        nouvelle_fin = nouveau_debut + datetime.timedelta(days=365)

        activate_licence(superuser=superuser, licence=licence, start_date=nouveau_debut, end_date=nouvelle_fin)

        licence.refresh_from_db()
        assert licence.start_date == nouveau_debut
        assert licence.end_date == nouvelle_fin
        assert not hasattr(licence, "plan")

    def test_reactive_une_licence_expiree_et_redonne_l_acces_au_club(self):
        superuser = SuperuserFactory()
        club = ClubFactory(status=Club.Status.READ_ONLY)
        licence = LicenceFactory(club=club, status=Licence.Status.EXPIRED)

        activate_licence(superuser=superuser, licence=licence, end_date=datetime.date.today() + datetime.timedelta(days=30))

        licence.refresh_from_db()
        club.refresh_from_db()
        assert licence.status == Licence.Status.ACTIVE
        assert club.status == Club.Status.ACTIVE

    def test_refuse_d_activer_une_licence_resiliee(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.TERMINATED)

        with pytest.raises(InvalidLicenceTransitionError):
            activate_licence(superuser=superuser, licence=licence)

    def test_refuse_d_activer_une_licence_suspendue(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.SUSPENDED)

        with pytest.raises(InvalidLicenceTransitionError):
            activate_licence(superuser=superuser, licence=licence)

    def test_refuse_un_non_superuser(self):
        joueur_normal = UserFactory(is_superuser=False)
        licence = LicenceFactory(status=Licence.Status.TRIAL)

        with pytest.raises(PermissionError):
            activate_licence(superuser=joueur_normal, licence=licence)


@pytest.mark.django_db
class TestExtendLicence:
    def test_prolonge_les_dates(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.ACTIVE)
        nouvelle_fin = licence.end_date + datetime.timedelta(days=30)

        extend_licence(superuser=superuser, licence=licence, end_date=nouvelle_fin)

        licence.refresh_from_db()
        assert licence.end_date == nouvelle_fin
        assert LicenceEvent.objects.filter(licence=licence, event_type=LicenceEvent.EventType.EXTENDED).exists()

    def test_refuse_une_date_de_fin_non_posterieure(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.ACTIVE)

        with pytest.raises(InvalidLicenceTransitionError):
            extend_licence(superuser=superuser, licence=licence, end_date=licence.end_date)

    def test_prolonger_une_licence_expiree_la_reactive(self):
        superuser = SuperuserFactory()
        club = ClubFactory(status=Club.Status.READ_ONLY)
        licence = LicenceFactory(club=club, status=Licence.Status.EXPIRED)
        nouvelle_fin = licence.end_date + datetime.timedelta(days=30)

        extend_licence(superuser=superuser, licence=licence, end_date=nouvelle_fin)

        licence.refresh_from_db()
        club.refresh_from_db()
        assert licence.status == Licence.Status.ACTIVE
        assert club.status == Club.Status.ACTIVE

    def test_refuse_de_prolonger_une_licence_suspendue(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.SUSPENDED)

        with pytest.raises(InvalidLicenceTransitionError):
            extend_licence(superuser=superuser, licence=licence, end_date=licence.end_date + datetime.timedelta(days=1))

    def test_refuse_de_prolonger_une_licence_resiliee(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.TERMINATED)

        with pytest.raises(InvalidLicenceTransitionError):
            extend_licence(superuser=superuser, licence=licence, end_date=licence.end_date + datetime.timedelta(days=1))


@pytest.mark.django_db
class TestSuspendResumeLicence:
    def test_suspend_ne_touche_jamais_club_status(self):
        """10.2 n19 : une licence suspendue bloque l'acces, mais NE
        modifie JAMAIS `Club.status`."""

        superuser = SuperuserFactory()
        club = ClubFactory(status=Club.Status.ACTIVE)
        licence = LicenceFactory(club=club, status=Licence.Status.ACTIVE)

        suspend_licence(superuser=superuser, licence=licence, reason="Impaye signale par le tresorier.")

        licence.refresh_from_db()
        club.refresh_from_db()
        assert licence.status == Licence.Status.SUSPENDED
        assert club.status == Club.Status.ACTIVE
        assert LicenceEvent.objects.filter(
            licence=licence, event_type=LicenceEvent.EventType.SUSPENDED, note="Impaye signale par le tresorier."
        ).exists()

    def test_motif_obligatoire_pour_suspendre(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.ACTIVE)

        with pytest.raises(InvalidLicenceTransitionError):
            suspend_licence(superuser=superuser, licence=licence, reason="   ")

    def test_refuse_de_suspendre_deux_fois(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.SUSPENDED)

        with pytest.raises(InvalidLicenceTransitionError):
            suspend_licence(superuser=superuser, licence=licence, reason="Nouveau motif.")

    def test_resume_redonne_le_statut_actif(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.SUSPENDED)

        resume_licence(superuser=superuser, licence=licence)

        licence.refresh_from_db()
        assert licence.status == Licence.Status.ACTIVE
        assert LicenceEvent.objects.filter(licence=licence, event_type=LicenceEvent.EventType.RESUMED).exists()

    def test_resume_refuse_si_pas_suspendue(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.ACTIVE)

        with pytest.raises(InvalidLicenceTransitionError):
            resume_licence(superuser=superuser, licence=licence)


@pytest.mark.django_db
class TestTerminateLicence:
    def test_resilie_avec_le_nom_exact_du_club(self):
        superuser = SuperuserFactory()
        club = ClubFactory(name="Loisirs Club Discovery Test")
        licence = LicenceFactory(club=club, status=Licence.Status.ACTIVE)

        terminate_licence(
            superuser=superuser,
            licence=licence,
            reason="Demande ecrite du club.",
            confirm_club_name="Loisirs Club Discovery Test",
        )

        licence.refresh_from_db()
        assert licence.status == Licence.Status.TERMINATED
        assert LicenceEvent.objects.filter(licence=licence, event_type=LicenceEvent.EventType.TERMINATED).exists()

    def test_refuse_et_ne_modifie_rien_si_le_nom_ne_correspond_pas(self):
        """10.2 n26 : rien n'est modifie en cas de non-correspondance."""

        superuser = SuperuserFactory()
        club = ClubFactory(name="Loisirs Club Discovery Test")
        licence = LicenceFactory(club=club, status=Licence.Status.ACTIVE)

        with pytest.raises(LicenceTerminationConfirmationError):
            terminate_licence(
                superuser=superuser,
                licence=licence,
                reason="Demande ecrite du club.",
                confirm_club_name="Nom incorrect",
            )

        licence.refresh_from_db()
        assert licence.status == Licence.Status.ACTIVE
        assert not LicenceEvent.objects.filter(licence=licence).exists()
        assert not AuditLog.objects.filter(action_type="licence.terminated").exists()

    def test_le_nom_saisi_n_est_jamais_stocke(self):
        """10.2 n26, schema §13.3 : le nom saisi n'est conserve nulle part."""

        superuser = SuperuserFactory()
        club = ClubFactory(name="Loisirs Club Discovery Test")
        licence = LicenceFactory(club=club, status=Licence.Status.ACTIVE)

        terminate_licence(
            superuser=superuser,
            licence=licence,
            reason="Demande ecrite du club.",
            confirm_club_name="Loisirs Club Discovery Test",
        )

        event = LicenceEvent.objects.get(licence=licence, event_type=LicenceEvent.EventType.TERMINATED)
        assert "Loisirs Club Discovery Test" not in event.note

        entry = AuditLog.objects.get(action_type="licence.terminated", object_id=str(licence.pk))
        assert "Loisirs Club Discovery Test" not in str(entry.before)
        assert "Loisirs Club Discovery Test" not in str(entry.after)

    def test_motif_obligatoire_pour_resilier(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.ACTIVE)

        with pytest.raises(InvalidLicenceTransitionError):
            terminate_licence(
                superuser=superuser,
                licence=licence,
                reason="   ",
                confirm_club_name=licence.club.name,
            )

    def test_refuse_de_resilier_deux_fois(self):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.TERMINATED)

        with pytest.raises(InvalidLicenceTransitionError):
            terminate_licence(
                superuser=superuser,
                licence=licence,
                reason="Motif.",
                confirm_club_name=licence.club.name,
            )
