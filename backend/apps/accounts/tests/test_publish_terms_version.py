"""Publication des CGU par un Superuser (CDC 2.5, 7.5 ; 10.2 n27).

Couvre le service `apps.accounts.services.publish_terms_version` et la
commande `manage.py publish_terms_version`, ainsi que leur lien avec la
creation de club : sans CGU publiee, aucun club ne peut etre cree ; apres
publication, l'assistant recoit la version courante et la creation aboutit.

Dates explicites (pas de freezegun dans le projet) : les numeros de version
sont deterministes (`2026-1`, `2026-2`...).
"""

from __future__ import annotations

import datetime
import json
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts import services as accounts_services
from apps.accounts.models import TermsAcceptance, TermsVersion
from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.audit.models import AuditLog
from apps.clubs import club_creation
from apps.clubs.models import Club, ClubSettings, Membership

pytestmark = pytest.mark.django_db

ACTION = "accounts.terms.published"
PUBLISHED_AT = datetime.datetime(2026, 10, 1, 8, 0, tzinfo=datetime.timezone.utc)
CGU_TEXT = "Article 1. Les présentes conditions régissent l'usage de Vesta. É è à."


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def superuser():
    return SuperuserFactory(email="admin@example.org")


def _run(*args) -> str:
    out = StringIO()
    call_command("publish_terms_version", *args, stdout=out)
    return out.getvalue()


def _creation_payload(terms_version_id, **overrides) -> dict:
    data = {
        "idempotency_key": "cgu-key-1",
        "name": "Club Recette CGU",
        "city": "Kinshasa",
        "country": "RD Congo",
        "currency": ClubSettings.Currency.USD,
        "timezone_name": "Africa/Kinshasa",
        "email": "fondateur.cgu@example.com",
        "first_name": "Jean",
        "last_name": "Fondateur",
        "position": Membership.Position.MIDFIELDER,
        "terms_version_id": terms_version_id,
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TestPublishTermsVersionService:
    def test_superuser_publishes_a_version_with_number_date_and_author(self, superuser):
        version = accounts_services.publish_terms_version(
            published_by=superuser, content=CGU_TEXT, published_at=PUBLISHED_AT
        )

        version.refresh_from_db()
        assert version.version_number == "2026-1"
        assert version.published_at == PUBLISHED_AT
        assert version.content == CGU_TEXT
        assert version.created_by == superuser
        assert TermsVersion.objects.count() == 1

    def test_default_publication_date_is_now(self, superuser):
        before = timezone.now()

        version = accounts_services.publish_terms_version(published_by=superuser, content=CGU_TEXT)

        assert before <= version.published_at <= timezone.now()

    def test_second_publication_of_the_same_year_gets_the_next_number(self, superuser):
        first = accounts_services.publish_terms_version(
            published_by=superuser, content="Première version", published_at=PUBLISHED_AT
        )
        second = accounts_services.publish_terms_version(
            published_by=superuser, content="Deuxième version", published_at=PUBLISHED_AT + datetime.timedelta(days=30)
        )

        assert first.version_number == "2026-1"
        assert second.version_number == "2026-2"

    def test_first_publication_of_a_new_year_restarts_at_one(self, superuser):
        accounts_services.publish_terms_version(published_by=superuser, content="v1", published_at=PUBLISHED_AT)

        next_year = accounts_services.publish_terms_version(
            published_by=superuser, content="v2", published_at=PUBLISHED_AT.replace(year=2027)
        )

        assert next_year.version_number == "2027-1"

    def test_content_is_stripped(self, superuser):
        version = accounts_services.publish_terms_version(
            published_by=superuser, content="  \n\tTexte des CGU  \n\n", published_at=PUBLISHED_AT
        )

        version.refresh_from_db()
        assert version.content == "Texte des CGU"

    def test_publication_writes_one_audit_entry_for_the_acting_superuser_without_club(self, superuser):
        version = accounts_services.publish_terms_version(
            published_by=superuser, content=CGU_TEXT, published_at=PUBLISHED_AT
        )

        entry = AuditLog.objects.get(action_type=ACTION)
        assert entry.actor_id == superuser.pk
        assert entry.club_id is None
        assert entry.object_id == str(version.pk)
        assert entry.after["version_number"] == "2026-1"
        assert entry.after["content_length"] == len(CGU_TEXT)
        assert entry.after["published_at"] is not None

    def test_audit_entry_never_contains_the_terms_text(self, superuser):
        accounts_services.publish_terms_version(
            published_by=superuser, content=CGU_TEXT, published_at=PUBLISHED_AT
        )

        entry = AuditLog.objects.get(action_type=ACTION)
        serialized = json.dumps({"before": entry.before, "after": entry.after}, ensure_ascii=False, default=str)
        assert "Article 1" not in serialized
        assert CGU_TEXT not in serialized
        assert set(entry.after) == {"version_number", "published_at", "content_length"}

    def test_non_superuser_cannot_publish_and_nothing_is_written(self):
        player = UserFactory(email="joueur@example.org")

        with pytest.raises(accounts_services.TermsPublicationError):
            accounts_services.publish_terms_version(published_by=player, content=CGU_TEXT)

        assert TermsVersion.objects.count() == 0
        assert not AuditLog.objects.filter(action_type=ACTION).exists()

    def test_missing_publisher_is_refused(self):
        with pytest.raises(accounts_services.TermsPublicationError):
            accounts_services.publish_terms_version(published_by=None, content=CGU_TEXT)

        assert TermsVersion.objects.count() == 0

    @pytest.mark.parametrize("content", ["", "   ", "\n\t \n", None])
    def test_empty_or_blank_content_is_refused_and_nothing_is_written(self, superuser, content):
        with pytest.raises(accounts_services.TermsPublicationError):
            accounts_services.publish_terms_version(published_by=superuser, content=content)

        assert TermsVersion.objects.count() == 0
        assert not AuditLog.objects.filter(action_type=ACTION).exists()


# ---------------------------------------------------------------------------
# Commande de gestion
# ---------------------------------------------------------------------------


class TestPublishTermsVersionCommand:
    def test_publishes_from_a_utf8_file_with_a_date_and_prints_the_number(self, superuser, tmp_path):
        content_file = tmp_path / "cgu.txt"
        content_file.write_text(CGU_TEXT, encoding="utf-8")

        output = _run(
            "--superuser-email", "admin@example.org",
            "--content-file", str(content_file),
            "--published-at", "2026-10-01T08:00:00+00:00",
        )

        version = TermsVersion.objects.get()
        assert "Version des CGU publiée : 2026-1" in output
        assert version.content == CGU_TEXT
        assert version.published_at == PUBLISHED_AT
        assert version.created_by == superuser

    def test_publishes_from_the_content_option(self, superuser):
        output = _run("--superuser-email", "admin@example.org", "--content", "Texte direct", "--published-at", "2026-10-01")

        assert "Version des CGU publiée : 2026-1" in output
        assert TermsVersion.objects.get().content == "Texte direct"

    def test_superuser_email_is_matched_case_insensitively(self, superuser):
        _run("--superuser-email", "ADMIN@EXAMPLE.ORG", "--content", "Texte", "--published-at", "2026-10-01")

        version = TermsVersion.objects.get()
        assert version.created_by == superuser

    def test_superuser_email_is_trimmed(self, superuser):
        _run("--superuser-email", "  admin@example.org  ", "--content", "Texte", "--published-at", "2026-10-01")

        assert TermsVersion.objects.count() == 1

    def test_second_run_gets_the_next_number(self, superuser):
        _run("--superuser-email", "admin@example.org", "--content", "v1", "--published-at", "2026-10-01")
        output = _run("--superuser-email", "admin@example.org", "--content", "v2", "--published-at", "2026-11-01")

        assert "Version des CGU publiée : 2026-2" in output
        assert list(TermsVersion.objects.order_by("id").values_list("version_number", flat=True)) == [
            "2026-1",
            "2026-2",
        ]

    def test_content_is_stripped(self, superuser, tmp_path):
        content_file = tmp_path / "cgu.txt"
        content_file.write_text("\n\n  Texte des CGU  \n\n", encoding="utf-8")

        _run("--superuser-email", "admin@example.org", "--content-file", str(content_file), "--published-at", "2026-10-01")

        assert TermsVersion.objects.get().content == "Texte des CGU"

    def test_naive_date_is_interpreted_as_utc(self, superuser):
        _run("--superuser-email", "admin@example.org", "--content", "Texte", "--published-at", "2026-10-01T08:00:00")

        assert TermsVersion.objects.get().published_at == PUBLISHED_AT

    def test_date_with_offset_is_converted_correctly(self, superuser):
        _run("--superuser-email", "admin@example.org", "--content", "Texte", "--published-at", "2026-10-01T10:00:00+02:00")

        assert TermsVersion.objects.get().published_at == PUBLISHED_AT

    def test_default_date_is_now(self, superuser):
        before = timezone.now()

        _run("--superuser-email", "admin@example.org", "--content", "Texte")

        assert before <= TermsVersion.objects.get().published_at <= timezone.now()

    def test_command_writes_the_audit_entry_for_the_superuser_without_club_and_without_text(self, superuser, tmp_path):
        content_file = tmp_path / "cgu.txt"
        content_file.write_text(CGU_TEXT, encoding="utf-8")

        _run("--superuser-email", "admin@example.org", "--content-file", str(content_file), "--published-at", "2026-10-01")

        entry = AuditLog.objects.get(action_type=ACTION)
        assert entry.actor_id == superuser.pk
        assert entry.club_id is None
        assert entry.after["version_number"] == "2026-1"
        assert entry.after["content_length"] == len(CGU_TEXT)
        assert CGU_TEXT not in json.dumps({"before": entry.before, "after": entry.after}, ensure_ascii=False, default=str)

    def test_unknown_account_is_refused_in_french(self):
        with pytest.raises(CommandError) as exc_info:
            _run("--superuser-email", "inconnu@example.org", "--content", "Texte")

        assert "Aucun compte ne correspond" in str(exc_info.value)
        assert TermsVersion.objects.count() == 0

    def test_non_superuser_account_is_refused_in_french(self):
        UserFactory(email="joueur@example.org")

        with pytest.raises(CommandError) as exc_info:
            _run("--superuser-email", "joueur@example.org", "--content", "Texte")

        assert "n'est pas un Superuser" in str(exc_info.value)
        assert TermsVersion.objects.count() == 0
        assert not AuditLog.objects.filter(action_type=ACTION).exists()

    @pytest.mark.parametrize("content", ["", "   ", "\n\t"])
    def test_empty_or_blank_content_option_is_refused(self, superuser, content):
        with pytest.raises(CommandError) as exc_info:
            _run("--superuser-email", "admin@example.org", "--content", content)

        assert "vide" in str(exc_info.value)
        assert TermsVersion.objects.count() == 0

    def test_blank_content_file_is_refused(self, superuser, tmp_path):
        content_file = tmp_path / "vide.txt"
        content_file.write_text("  \n \n", encoding="utf-8")

        with pytest.raises(CommandError) as exc_info:
            _run("--superuser-email", "admin@example.org", "--content-file", str(content_file))

        assert "vide" in str(exc_info.value)
        assert TermsVersion.objects.count() == 0

    def test_missing_file_is_refused_in_french(self, superuser, tmp_path):
        with pytest.raises(CommandError) as exc_info:
            _run("--superuser-email", "admin@example.org", "--content-file", str(tmp_path / "absent.txt"))

        assert "Impossible de lire le fichier" in str(exc_info.value)
        assert TermsVersion.objects.count() == 0

    def test_non_utf8_file_is_refused_in_french(self, superuser, tmp_path):
        content_file = tmp_path / "latin1.txt"
        content_file.write_bytes("Conditions générales é à".encode("latin-1"))

        with pytest.raises(CommandError) as exc_info:
            _run("--superuser-email", "admin@example.org", "--content-file", str(content_file))

        assert "UTF-8" in str(exc_info.value)
        assert TermsVersion.objects.count() == 0

    def test_invalid_date_is_refused_in_french(self, superuser):
        with pytest.raises(CommandError) as exc_info:
            _run("--superuser-email", "admin@example.org", "--content", "Texte", "--published-at", "hier")

        assert "Date invalide" in str(exc_info.value)
        assert TermsVersion.objects.count() == 0

    def test_neither_content_nor_content_file_is_refused(self, superuser):
        with pytest.raises(CommandError):
            _run("--superuser-email", "admin@example.org")

        assert TermsVersion.objects.count() == 0

    def test_content_and_content_file_together_are_refused(self, superuser, tmp_path):
        content_file = tmp_path / "cgu.txt"
        content_file.write_text("Texte fichier", encoding="utf-8")

        with pytest.raises(CommandError):
            _run(
                "--superuser-email", "admin@example.org",
                "--content", "Texte direct",
                "--content-file", str(content_file),
            )

        assert TermsVersion.objects.count() == 0

    def test_superuser_email_is_required(self):
        with pytest.raises(CommandError):
            _run("--content", "Texte")

        assert TermsVersion.objects.count() == 0

    def test_every_refusal_leaves_no_audit_entry(self, superuser, tmp_path):
        UserFactory(email="joueur@example.org")
        attempts = [
            ("--superuser-email", "inconnu@example.org", "--content", "Texte"),
            ("--superuser-email", "joueur@example.org", "--content", "Texte"),
            ("--superuser-email", "admin@example.org", "--content", "  "),
            ("--superuser-email", "admin@example.org", "--content-file", str(tmp_path / "absent.txt")),
            ("--superuser-email", "admin@example.org", "--content", "Texte", "--published-at", "hier"),
        ]

        for args in attempts:
            with pytest.raises(CommandError):
                _run(*args)

        assert not AuditLog.objects.filter(action_type=ACTION).exists()
        assert TermsVersion.objects.count() == 0


# ---------------------------------------------------------------------------
# Lien avec la creation de club (remarque du client)
# ---------------------------------------------------------------------------


class TestPublishedTermsAreExposedToClubCreation:
    def test_public_settings_return_null_terms_version_before_any_publication(self):
        response = APIClient().get(reverse("clubs:public-creation-settings"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["terms_version"] is None

    def test_public_settings_return_the_published_version_number_and_text_after_command(self, superuser):
        _run("--superuser-email", "admin@example.org", "--content", CGU_TEXT, "--published-at", "2026-10-01")

        response = APIClient().get(reverse("clubs:public-creation-settings"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["terms_version"] is not None
        assert response.data["terms_version"]["version_number"] == "2026-1"
        assert response.data["terms_version"]["content"] == CGU_TEXT
        assert response.data["terms_version"]["id"] == TermsVersion.objects.get().id

    def test_public_settings_return_the_latest_version_after_two_publications(self, superuser):
        accounts_services.publish_terms_version(published_by=superuser, content="v1", published_at=PUBLISHED_AT)
        accounts_services.publish_terms_version(
            published_by=superuser, content="v2", published_at=PUBLISHED_AT + datetime.timedelta(days=30)
        )

        response = APIClient().get(reverse("clubs:public-creation-settings"))

        assert response.data["terms_version"]["version_number"] == "2026-2"
        assert response.data["terms_version"]["content"] == "v2"

    def test_club_creation_service_is_refused_without_any_published_terms(self):
        with pytest.raises(club_creation.TermsVersionOutdatedError) as exc_info:
            club_creation.create_club_with_founder(**_creation_payload(terms_version_id=1))

        assert exc_info.value.latest_terms_version is None
        assert not Club.objects.filter(name="Club Recette CGU").exists()

    def test_club_creation_api_is_refused_with_409_without_any_published_terms(self):
        response = APIClient().post(
            reverse("clubs:create"), {**_creation_payload(1), "accept_terms": True}, format="json"
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["code"] == "terms_version_outdated"
        assert response.data["terms_version"] is None
        assert not Club.objects.filter(name="Club Recette CGU").exists()

    def test_club_creation_service_succeeds_after_publication_with_the_published_version(self, superuser):
        version = accounts_services.publish_terms_version(
            published_by=superuser, content=CGU_TEXT, published_at=PUBLISHED_AT
        )

        result = club_creation.create_club_with_founder(**_creation_payload(version.id))

        assert Club.objects.filter(name="Club Recette CGU").exists()
        assert result.club.name == "Club Recette CGU"
        acceptance = TermsAcceptance.objects.get(terms_version=version)
        assert acceptance.user.email == "fondateur.cgu@example.com"

    def test_club_creation_api_succeeds_after_command_publication_using_the_exposed_version(self, superuser):
        _run("--superuser-email", "admin@example.org", "--content", CGU_TEXT, "--published-at", "2026-10-01")
        client = APIClient()
        settings_response = client.get(reverse("clubs:public-creation-settings"))
        exposed_id = settings_response.data["terms_version"]["id"]

        response = client.post(
            reverse("clubs:create"), {**_creation_payload(exposed_id), "accept_terms": True}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Club.objects.filter(name="Club Recette CGU").exists()
        assert TermsAcceptance.objects.filter(
            terms_version_id=exposed_id, user__email="fondateur.cgu@example.com"
        ).exists()

    def test_club_creation_is_refused_with_the_stale_id_once_a_newer_version_is_published(self, superuser):
        old = accounts_services.publish_terms_version(
            published_by=superuser, content="v1", published_at=PUBLISHED_AT
        )
        new = accounts_services.publish_terms_version(
            published_by=superuser, content="v2", published_at=PUBLISHED_AT + datetime.timedelta(days=30)
        )

        with pytest.raises(club_creation.TermsVersionOutdatedError) as exc_info:
            club_creation.create_club_with_founder(**_creation_payload(old.id))

        assert exc_info.value.latest_terms_version == new
        assert not Club.objects.filter(name="Club Recette CGU").exists()
