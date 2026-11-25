"""Tests de `apps.clubs.club_creation` (assistant de creation de club en
libre-service, tache 1.9).

Sources : docs/ecrans/clubs-creation.md ; CDC 1.4, 2.1, 2.3, 4.1, 5.2, 7.1,
7.5, 7.6 ; 10.2 n1, 18, 20, 24, 27 ; CLAUDE.md regles 2, 6, 8, 9.

Priorites de ce module (mission test-engineer) :
- idempotence reelle (meme cle -> un seul club, replay identique) ;
- concurrence simulee (course sur la meme cle d'idempotence, et course
  sur l'email entre deux cles differentes) ;
- atomicite (aucune trace en base si une seule ecriture echoue, tot ou
  tard dans la transaction) ;
- erreurs metier documentees (email deja utilise, CGU perimees) ;
- generation du slug (accents, suffixe, troncature) ;
- contenu exact des objets crees (statuts, dates, journal).
"""

from __future__ import annotations

import datetime

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone as dj_timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import TermsVersionFactory, UserFactory
from apps.audit.models import AuditLog
from apps.clubs import club_creation
from apps.clubs.models import Club, ClubCreationRequest, ClubSettings, Membership, MembershipRole
from apps.licences.models import Licence
from apps.licences.services import TRIAL_DURATION_DAYS

pytestmark = pytest.mark.django_db


def _payload(*, terms_version=None, **overrides) -> dict:
    if terms_version is None:
        terms_version = TermsVersionFactory()
    data = {
        "idempotency_key": "idem-key-1",
        "name": "Discovery FC",
        "city": "Kinshasa",
        "country": "RD Congo",
        "currency": ClubSettings.Currency.USD,
        "timezone_name": "Africa/Kinshasa",
        "email": "fondateur@example.com",
        "first_name": "Jean",
        "last_name": "Fondateur",
        "position": Membership.Position.MIDFIELDER,
        "terms_version_id": terms_version.id,
    }
    data.update(overrides)
    return data


class TestGenerateUniqueSlug:
    def test_strips_accents_and_lowercases(self):
        assert club_creation.generate_unique_slug("Étoile Élan Éclair") == "etoile-elan-eclair"

    def test_adds_numeric_suffix_when_base_slug_already_taken(self):
        Club.objects.create(name="Existant", slug="mon-club", city="Kinshasa", country="RD Congo")

        assert club_creation.generate_unique_slug("Mon Club") == "mon-club-2"

        Club.objects.create(name="Existant 2", slug="mon-club-2", city="Kinshasa", country="RD Congo")

        assert club_creation.generate_unique_slug("Mon Club") == "mon-club-3"

    def test_truncates_to_the_slug_field_max_length(self):
        max_length = Club._meta.get_field("slug").max_length
        long_name = "a" * (max_length + 40)

        slug = club_creation.generate_unique_slug(long_name)

        assert len(slug) == max_length
        assert slug == "a" * max_length

    def test_truncates_correctly_when_a_numeric_suffix_is_also_needed(self):
        max_length = Club._meta.get_field("slug").max_length
        long_name = "b" * (max_length + 40)
        base_slug = "b" * max_length
        Club.objects.create(name="Existant", slug=base_slug, city="Kinshasa", country="RD Congo")

        slug = club_creation.generate_unique_slug(long_name)

        assert len(slug) == max_length
        assert slug == ("b" * (max_length - 2)) + "-2"

    def test_empty_or_purely_symbolic_name_falls_back_to_club(self):
        assert club_creation.generate_unique_slug("!!!") == "club"


class TestEmailAlreadyUsedError:
    def test_raises_immediately_without_touching_the_database(self):
        UserFactory(email="deja-utilise@example.com")
        data = _payload(email="deja-utilise@example.com")

        with pytest.raises(club_creation.EmailAlreadyUsedError):
            club_creation.create_club_with_founder(**data)

        assert not Club.objects.filter(name=data["name"]).exists()
        assert not ClubCreationRequest.objects.filter(idempotency_key=data["idempotency_key"]).exists()


class TestReservedEmail:
    def test_refuses_the_reserved_system_email(self):
        from django.core.exceptions import ValidationError

        data = _payload(email="systeme@vesta.invalid")

        with pytest.raises(ValidationError) as exc_info:
            club_creation.create_club_with_founder(**data)

        assert "réservée" in exc_info.value.messages[0]
        assert not Club.objects.filter(name=data["name"]).exists()


class TestTermsVersionOutdatedError:
    def test_raises_when_terms_version_id_is_stale(self):
        old_version = TermsVersionFactory(published_at=dj_timezone.now() - datetime.timedelta(days=10))
        new_version = TermsVersionFactory(published_at=dj_timezone.now())
        data = _payload(terms_version=old_version, email="cgu-perimees@example.com")

        with pytest.raises(club_creation.TermsVersionOutdatedError) as exc_info:
            club_creation.create_club_with_founder(**data)

        assert exc_info.value.latest_terms_version == new_version
        assert not Club.objects.filter(name=data["name"]).exists()

    def test_raises_when_no_terms_version_exists_at_all(self):
        data = {
            "idempotency_key": "key-no-terms",
            "name": "Sans CGU FC",
            "city": "Kinshasa",
            "country": "RD Congo",
            "currency": ClubSettings.Currency.USD,
            "timezone_name": "Africa/Kinshasa",
            "email": "sans-cgu@example.com",
            "first_name": "Jean",
            "last_name": "Fondateur",
            "position": Membership.Position.MIDFIELDER,
            "terms_version_id": 999999,
        }

        with pytest.raises(club_creation.TermsVersionOutdatedError) as exc_info:
            club_creation.create_club_with_founder(**data)

        assert exc_info.value.latest_terms_version is None


class TestCreateClubWithFounderHappyPath:
    def test_creates_all_expected_objects_with_the_right_statuses_and_dates(self):
        fixed_now = dj_timezone.make_aware(datetime.datetime(2026, 3, 1, 9, 0, 0))
        data = _payload(idempotency_key="key-happy", email="fondateur-happy@example.com")

        result = club_creation.create_club_with_founder(now=fixed_now, **data)

        assert result.idempotent_replay is False

        # Club (CDC 2.1, 2.3 : le createur devient President).
        assert result.club.status == Club.Status.ACTIVE
        assert result.club.founder_membership_id == result.membership.id

        # Licence d'essai (CDC 1.4, 10.2 n1/n20).
        assert result.licence.status == Licence.Status.TRIAL
        assert result.licence.start_date == fixed_now.date()
        assert result.licence.end_date == fixed_now.date() + datetime.timedelta(days=TRIAL_DURATION_DAYS)
        assert result.licence.created_by is None

        # Membership "Inscrit" directement (point ouvert applique par defaut).
        assert result.membership.status == Membership.Status.ACTIVE
        assert result.membership.get_status_display() == "Inscrit"

        # Role President actif.
        assert result.role.role == MembershipRole.Role.PRESIDENT
        assert result.role.revoked_at is None
        assert MembershipRole.all_objects.filter(
            club=result.club,
            membership=result.membership,
            role=MembershipRole.Role.PRESIDENT,
            revoked_at__isnull=True,
        ).count() == 1

        # Compte fondateur (CDC 7.1 : mot de passe initial = email).
        assert result.user.email == "fondateur-happy@example.com"
        assert result.user.must_change_password is True

        # Journal (CDC 5.2, CLAUDE.md regle n6) : deux entrees, bon acteur, bon club.
        created_log = AuditLog.objects.get(club=result.club, action_type="clubs.created")
        assert created_log.actor_id == result.user.id
        assert created_log.before is None
        assert created_log.after["name"] == "Discovery FC"

        licence_log = AuditLog.objects.get(club=result.club, action_type="licence.created")
        assert licence_log.actor_id == result.user.id
        assert licence_log.after["status"] == Licence.Status.TRIAL


class TestIdempotence:
    def test_second_call_with_the_same_key_is_a_pure_replay(self):
        data = _payload(idempotency_key="idem-key-x", email="idem@example.com")

        first = club_creation.create_club_with_founder(**data)
        assert first.idempotent_replay is False
        assert Club.objects.count() == 1

        second = club_creation.create_club_with_founder(**data)

        assert second.idempotent_replay is True
        assert second.club.pk == first.club.pk
        assert second.user.pk == first.user.pk
        assert second.membership.pk == first.membership.pk
        assert second.licence.pk == first.licence.pk
        assert second.role.pk == first.role.pk
        assert Club.objects.count() == 1

    def test_second_call_with_a_different_payload_still_returns_the_first_result(self):
        """Un double appui/une nouvelle tentative apres coupure reseau peut
        renvoyer des donnees legerement differentes (ex. reconstruites cote
        client) : la cle d'idempotence doit primer, jamais le nouveau corps
        de requete (docs/ecrans/clubs-creation.md §6)."""

        data = _payload(idempotency_key="idem-key-y", email="idem-y@example.com", name="Premier Nom")
        first = club_creation.create_club_with_founder(**data)

        second_data = dict(data)
        second_data["name"] = "Deuxieme Nom"
        second_data["email"] = "autre-email@example.com"
        second = club_creation.create_club_with_founder(**second_data)

        assert second.club.pk == first.club.pk
        assert second.club.name == "Premier Nom"
        assert Club.objects.count() == 1
        assert not User.objects.filter(email="autre-email@example.com").exists()


class TestAtomicity:
    def test_rolls_back_everything_when_full_clean_fails(self):
        """Couleur invalide (trop longue pour le champ) : `Club.save()`
        appelle toujours `full_clean()` -- la ValidationError doit annuler
        integralement la transaction, y compris si elle survient tot."""

        data = _payload(idempotency_key="key-fail-clean", email="fail-clean@example.com")
        data["primary_color"] = "#TROP-LONG-POUR-CE-CHAMP-DE-7-CARACTERES"

        with pytest.raises(DjangoValidationError):
            club_creation.create_club_with_founder(**data)

        assert not Club.objects.filter(name=data["name"]).exists()
        assert not User.objects.filter(email="fail-clean@example.com").exists()
        assert not ClubSettings.objects.exists()
        assert not Licence.objects.exists()
        assert not Membership.all_objects.filter(user__email="fail-clean@example.com").exists()

    def test_rolls_back_everything_on_an_unexpected_failure_deep_in_the_transaction(self, monkeypatch):
        """Panne simulee APRES que Club/ClubSettings/Licence/User/Membership/
        MembershipRole ont deja ete ecrits (mais pas encore commit) dans la
        transaction : rien de tout cela ne doit survivre (CLAUDE.md regle
        « si une seule ecriture echoue, rien n'est cree »)."""

        def _boom(**kwargs):
            raise RuntimeError("panne simulee")

        monkeypatch.setattr(club_creation, "notify_role_change", _boom)

        data = _payload(idempotency_key="key-deep-fail", email="deep-fail@example.com")

        with pytest.raises(RuntimeError):
            club_creation.create_club_with_founder(**data)

        assert not Club.objects.filter(name=data["name"]).exists()
        assert not User.objects.filter(email="deep-fail@example.com").exists()
        assert not ClubSettings.objects.exists()
        assert not Licence.objects.exists()
        assert not Membership.all_objects.filter(user__email="deep-fail@example.com").exists()
        assert not MembershipRole.all_objects.filter(role=MembershipRole.Role.PRESIDENT).exists()
        assert not ClubCreationRequest.objects.filter(idempotency_key="key-deep-fail").exists()
        assert not AuditLog.objects.filter(action_type="clubs.created").exists()

    def test_concurrent_call_with_the_same_idempotency_key_receives_the_winners_result(self, monkeypatch):
        """Simule la course : deux appels avec la MEME cle d'idempotence,
        le "perdant" ne voit pas encore la ligne `ClubCreationRequest` du
        "gagnant" au moment de son propre controle initial (fenetre de
        course), mais la contrainte d'unicite l'arrete a l'ecriture finale.
        Un seul club doit exister, et le perdant doit recevoir le resultat
        du gagnant plutot qu'une erreur ou un deuxieme club."""

        race_key = "race-key-same-idem"
        terms_version = TermsVersionFactory()
        winner_data = _payload(
            idempotency_key=race_key, email="winner@example.com", name="Club Gagnant", terms_version=terms_version
        )
        winner = club_creation.create_club_with_founder(**winner_data)

        bypass_state = {"used": False}
        original_filter = ClubCreationRequest.objects.filter

        def fake_filter(*args, **kwargs):
            if not bypass_state["used"] and kwargs.get("idempotency_key") == race_key:
                bypass_state["used"] = True
                return original_filter(pk=-1)  # simule : la ligne du gagnant n'est pas encore visible
            return original_filter(*args, **kwargs)

        monkeypatch.setattr(ClubCreationRequest.objects, "filter", fake_filter)

        loser_data = _payload(
            idempotency_key=race_key, email="loser@example.com", name="Club Perdant", terms_version=terms_version
        )

        loser_result = club_creation.create_club_with_founder(**loser_data)

        assert bypass_state["used"] is True
        assert loser_result.idempotent_replay is True
        assert loser_result.club.pk == winner.club.pk
        assert loser_result.user.pk == winner.user.pk
        assert Club.objects.count() == 1
        assert not Club.objects.filter(name="Club Perdant").exists()
        assert not User.objects.filter(email="loser@example.com").exists()

    def test_email_uniqueness_race_after_the_initial_check_rolls_back_and_raises(self, monkeypatch):
        """Deuxieme cause de course documentee par le module (cles
        d'idempotence DIFFERENTES, meme email soumis en meme temps) : le
        controle initial de `create_club_with_founder` et celui, interne,
        de `get_or_create_platform_user` voient tous deux "email libre"
        (fenetre de course), mais l'ecriture finale du compte percute la
        contrainte d'unicite reelle sur `User.email`. Tout doit etre
        annule, et l'erreur metier attendue doit remonter."""

        target_email = "course-email@example.com"
        rival = UserFactory(email=target_email)

        bypass_state = {"count": 0}
        original_filter = User.objects.filter

        def fake_filter(*args, **kwargs):
            if kwargs.get("email") == target_email and bypass_state["count"] < 2:
                bypass_state["count"] += 1
                return original_filter(pk=-1)  # simule : le rival n'est pas encore visible
            return original_filter(*args, **kwargs)

        monkeypatch.setattr(User.objects, "filter", fake_filter)

        data = _payload(idempotency_key="key-email-race", email=target_email, name="Club Course Email")

        with pytest.raises(club_creation.EmailAlreadyUsedError):
            club_creation.create_club_with_founder(**data)

        assert bypass_state["count"] == 2
        assert not Club.objects.filter(name="Club Course Email").exists()
        assert User.objects.filter(email=target_email).count() == 1
        assert User.objects.get(email=target_email).pk == rival.pk
        assert not ClubSettings.objects.exists()
        assert not Licence.objects.exists()
