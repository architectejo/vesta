"""Journal et atomicite par ligne de l'import CSV des joueurs (CDC 4.1, 5.2 ;
CLAUDE.md regle n6 ; audit tache 1.14, ecart bloquant B4).

- ``accounts.user.updated_via_import`` : journalise la mise a jour reelle des
  champs personnels (telephone, date de naissance, poids, taille) d'un compte
  ``User`` DEJA existant, avec l'importeur comme acteur et le club qui importe
  comme club ;
- chaque ligne s'execute dans un savepoint : une ligne rejetee apres que
  ``get_or_create_platform_user`` a deja modifie un ``User`` existant annule
  cette modification ET son entree de journal (garde de securite B2).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.accounts.services import PlatformUserResult, get_or_create_platform_user
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog
from apps.clubs import services as clubs_services
from apps.clubs.models import Membership
from apps.clubs.tests.factories import ClubFactory, MembershipFactory

ACTION = "accounts.user.updated_via_import"

pytestmark = pytest.mark.django_db


def _csv_upload(content: str, name: str = "import.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


def _entries(user) -> list[AuditLog]:
    return list(AuditLog.objects.filter(action_type=ACTION, object_id=str(user.pk)))


def _departed_membership(club, user) -> Membership:
    return MembershipFactory(
        club=club,
        user=user,
        status=Membership.Status.DEPARTED,
        left_on=date(2026, 1, 1),
        left_reason=Membership.LeftReason.RESIGNATION,
    )


def _snapshot(user) -> dict:
    user.refresh_from_db()
    return {
        "phone": user.phone,
        "birth_date": user.birth_date,
        "weight_kg": user.weight_kg,
        "height_cm": user.height_cm,
    }


# ---------------------------------------------------------------------------
# 1. Mise a jour reelle d'un compte existant : une entree de journal
# ---------------------------------------------------------------------------


class TestUserUpdateIsAuditedThroughImport:
    def test_updating_phone_of_a_member_already_in_the_club_writes_one_audit_entry(self):
        club = ClubFactory()
        importer = MembershipFactory(club=club)
        existing = MembershipFactory(club=club, user=UserFactory(phone="0811111111"))

        summary = clubs_services.import_players_from_csv(
            club=club,
            imported_by=importer.user,
            csv_file=_csv_upload(
                f"email,prenom,nom,telephone\n{existing.user.email},X,Y,0822222222\n"
            ),
        )

        assert summary.batch.row_count_success == 1
        existing.user.refresh_from_db()
        assert existing.user.phone == "0822222222"
        entries = _entries(existing.user)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.actor_id == importer.user_id
        assert entry.club_id == club.id
        assert entry.object_type == "User"
        assert entry.before["phone"] == "0811111111"
        assert entry.after["phone"] == "0822222222"

    def test_updating_a_user_known_in_another_club_without_active_membership_writes_one_audit_entry(self):
        other_club = ClubFactory()
        importing_club = ClubFactory()
        importer = MembershipFactory(club=importing_club)
        known_user = UserFactory(phone="0811111111", birth_date=date(1990, 1, 1))
        _departed_membership(other_club, known_user)

        summary = clubs_services.import_players_from_csv(
            club=importing_club,
            imported_by=importer.user,
            csv_file=_csv_upload(
                f"email,prenom,nom,telephone,date_naissance\n{known_user.email},X,Y,0833333333,1985-05-17\n"
            ),
        )

        assert summary.rows[0].outcome == "created_new_club_membership"
        # Message neutre : ne révèle pas que l'email existait dans un autre club.
        assert summary.rows[0].message == "Ligne 2 : adhésion créée."
        known_user.refresh_from_db()
        assert known_user.phone == "0833333333"
        assert known_user.birth_date == date(1985, 5, 17)
        entries = _entries(known_user)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.actor_id == importer.user_id
        # Le club du journal est celui qui IMPORTE, pas l'ancien club du compte.
        assert entry.club_id == importing_club.id
        assert entry.before["phone"] == "0811111111"
        assert entry.after["phone"] == "0833333333"
        assert entry.before["birth_date"] == "1990-01-01"
        assert entry.after["birth_date"] == "1985-05-17"

    def test_user_without_any_membership_is_updated_and_audited_too(self):
        club = ClubFactory()
        importer = MembershipFactory(club=club)
        orphan_user = UserFactory(phone="0811111111")

        clubs_services.import_players_from_csv(
            club=club,
            imported_by=importer.user,
            csv_file=_csv_upload(f"email,prenom,nom,telephone\n{orphan_user.email},X,Y,0844444444\n"),
        )

        assert len(_entries(orphan_user)) == 1

    def test_audit_entry_before_and_after_contain_only_the_fields_that_really_changed(self):
        """Contrat annonce par ``PlatformUserResult`` : ``before``/``after``
        sont le sous-ensemble des champs REELLEMENT modifies."""

        club = ClubFactory()
        importer = MembershipFactory(club=club)
        existing = MembershipFactory(
            club=club,
            user=UserFactory(
                phone="0811111111",
                birth_date=date(1990, 1, 1),
                weight_kg=Decimal("75.0"),
                height_cm=Decimal("180.0"),
            ),
        )

        clubs_services.import_players_from_csv(
            club=club,
            imported_by=importer.user,
            # Seul le poids change ; telephone/date/taille sont identiques ou absents.
            csv_file=_csv_upload(
                "email,prenom,nom,telephone,date_naissance,poids\n"
                f"{existing.user.email},X,Y,0811111111,1990-01-01,82\n"
            ),
        )

        entry = _entries(existing.user)[0]
        assert set(entry.before) == {"weight_kg"}
        assert set(entry.after) == {"weight_kg"}
        assert Decimal(str(entry.before["weight_kg"])) == Decimal("75.0")
        assert Decimal(str(entry.after["weight_kg"])) == Decimal("82")

    def test_changing_several_fields_lists_each_changed_field_once(self):
        club = ClubFactory()
        importer = MembershipFactory(club=club)
        existing = MembershipFactory(
            club=club, user=UserFactory(phone="0811111111", weight_kg=Decimal("75.0"), height_cm=Decimal("180.0"))
        )

        clubs_services.import_players_from_csv(
            club=club,
            imported_by=importer.user,
            csv_file=_csv_upload(
                "email,prenom,nom,telephone,taille\n"
                f"{existing.user.email},X,Y,0855555555,185\n"
            ),
        )

        entry = _entries(existing.user)[0]
        assert set(entry.before) == {"phone", "height_cm"}
        assert set(entry.after) == {"phone", "height_cm"}

    def test_audit_entry_never_contains_password_or_identity_fields(self):
        club = ClubFactory()
        importer = MembershipFactory(club=club)
        existing = MembershipFactory(club=club, user=UserFactory(phone="0811111111"))

        clubs_services.import_players_from_csv(
            club=club,
            imported_by=importer.user,
            csv_file=_csv_upload(f"email,prenom,nom,telephone\n{existing.user.email},Autre,Nom,0866666666\n"),
        )

        entry = _entries(existing.user)[0]
        serialized = str(entry.before) + str(entry.after)
        assert "password" not in serialized
        assert existing.user.email not in serialized
        # Le prenom/nom d'un compte existant n'est jamais modifie par l'import.
        existing.user.refresh_from_db()
        assert existing.user.first_name != "Autre"

    def test_audit_entry_is_append_only(self):
        from apps.audit.models import AuditLogImmutableError

        club = ClubFactory()
        importer = MembershipFactory(club=club)
        existing = MembershipFactory(club=club, user=UserFactory(phone="0811111111"))
        clubs_services.import_players_from_csv(
            club=club,
            imported_by=importer.user,
            csv_file=_csv_upload(f"email,prenom,nom,telephone\n{existing.user.email},X,Y,0877777777\n"),
        )
        entry = _entries(existing.user)[0]

        with pytest.raises(AuditLogImmutableError):
            entry.delete()
        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.filter(pk=entry.pk).update(action_type="autre")

    def test_create_or_update_player_called_directly_also_writes_the_entry(self):
        club = ClubFactory()
        importer = MembershipFactory(club=club)
        existing = MembershipFactory(club=club, user=UserFactory(phone="0811111111"))

        clubs_services.create_or_update_player(
            club=club,
            email=existing.user.email,
            first_name="X",
            last_name="Y",
            added_by=importer.user,
            phone="0888888888",
        )

        entries = _entries(existing.user)
        assert len(entries) == 1
        assert entries[0].actor_id == importer.user_id
        assert entries[0].club_id == club.id


# ---------------------------------------------------------------------------
# 2. Mise a jour sans changement reel : aucune entree
# ---------------------------------------------------------------------------


class TestNoAuditEntryWithoutRealChange:
    def test_reimporting_identical_personal_fields_writes_no_entry(self):
        club = ClubFactory()
        importer = MembershipFactory(club=club)
        existing = MembershipFactory(
            club=club, user=UserFactory(phone="0811111111", birth_date=date(1990, 1, 1))
        )

        clubs_services.import_players_from_csv(
            club=club,
            imported_by=importer.user,
            csv_file=_csv_upload(
                "email,prenom,nom,telephone,date_naissance\n"
                f"{existing.user.email},X,Y,0811111111,1990-01-01\n"
            ),
        )

        assert _entries(existing.user) == []
        assert not AuditLog.objects.filter(action_type=ACTION).exists()

    def test_row_without_any_personal_field_writes_no_entry_and_keeps_existing_values(self):
        club = ClubFactory()
        importer = MembershipFactory(club=club)
        existing = MembershipFactory(club=club, user=UserFactory(phone="0811111111"))

        clubs_services.import_players_from_csv(
            club=club,
            imported_by=importer.user,
            csv_file=_csv_upload(f"email,prenom,nom\n{existing.user.email},X,Y\n"),
        )

        assert _entries(existing.user) == []
        existing.user.refresh_from_db()
        assert existing.user.phone == "0811111111"

    def test_updating_only_the_membership_position_writes_no_user_entry(self):
        club = ClubFactory()
        importer = MembershipFactory(club=club)
        existing = MembershipFactory(club=club, position=Membership.Position.DEFENDER)

        clubs_services.import_players_from_csv(
            club=club,
            imported_by=importer.user,
            csv_file=_csv_upload(f"email,prenom,nom,poste\n{existing.user.email},X,Y,attaquant\n"),
        )

        assert _entries(existing.user) == []
        # ... mais la mise a jour de l'adhesion reste journalisee (comportement existant).
        assert AuditLog.objects.filter(action_type="membership.updated", object_id=str(existing.pk)).exists()

    def test_platform_user_result_carries_none_when_nothing_changed(self):
        user = UserFactory(phone="0811111111")

        result = get_or_create_platform_user(
            email=user.email, first_name="X", last_name="Y", phone="0811111111"
        )

        assert isinstance(result, PlatformUserResult)
        assert result.created is False
        assert result.updated_fields_before is None
        assert result.updated_fields_after is None


# ---------------------------------------------------------------------------
# 3. Compte cree par l'import : pas d'entree de ce type
# ---------------------------------------------------------------------------


class TestNoAuditEntryForAccountsCreatedByTheImport:
    def test_new_email_creates_the_account_without_a_user_updated_entry(self):
        club = ClubFactory()
        importer = MembershipFactory(club=club)

        summary = clubs_services.import_players_from_csv(
            club=club,
            imported_by=importer.user,
            csv_file=_csv_upload("email,prenom,nom,telephone\nnouveau@example.com,Aline,Kabila,0899999999\n"),
        )

        assert summary.rows[0].outcome == "created"
        created_user = User.objects.get(email="nouveau@example.com")
        assert _entries(created_user) == []
        assert not AuditLog.objects.filter(action_type=ACTION).exists()
        # La creation reste couverte par `membership.created`.
        membership = Membership.all_objects.get(club=club, user=created_user)
        assert AuditLog.objects.filter(action_type="membership.created", object_id=str(membership.pk)).exists()

    def test_platform_user_result_carries_none_for_a_created_account(self):
        result = get_or_create_platform_user(
            email="tout-neuf@example.com", first_name="X", last_name="Y", phone="0811111111"
        )

        assert result.created is True
        assert result.updated_fields_before is None
        assert result.updated_fields_after is None


# ---------------------------------------------------------------------------
# 4. Atomicite par ligne : ligne rejetee apres modification d'un User existant
# ---------------------------------------------------------------------------


class TestRejectedRowRollsBackUserMutation:
    def _setup(self):
        first_club = ClubFactory()
        importing_club = ClubFactory()
        importer = MembershipFactory(club=importing_club)
        # Compte avec une adhesion ACTIVE dans un AUTRE club : la ligne sera
        # rejetee par le garde de securite B2, apres que
        # `get_or_create_platform_user` a deja modifie le compte.
        protected_user = UserFactory(
            phone="0811111111",
            birth_date=date(1990, 1, 1),
            weight_kg=Decimal("75.0"),
            height_cm=Decimal("180.0"),
        )
        MembershipFactory(club=first_club, user=protected_user, status=Membership.Status.ACTIVE)
        return importing_club, importer, protected_user

    def test_rejected_row_leaves_the_existing_user_unchanged_and_writes_no_audit_entry(self):
        importing_club, importer, protected_user = self._setup()
        before = _snapshot(protected_user)

        summary = clubs_services.import_players_from_csv(
            club=importing_club,
            imported_by=importer.user,
            csv_file=_csv_upload(
                "email,prenom,nom,telephone,date_naissance\n"
                f"{protected_user.email},X,Y,0899999999,1970-12-31\n"
            ),
        )

        assert summary.batch.row_count_failed == 1
        assert summary.batch.row_count_success == 0
        assert _snapshot(protected_user) == before
        assert _entries(protected_user) == []
        assert not AuditLog.objects.filter(action_type=ACTION).exists()
        assert not Membership.all_objects.filter(club=importing_club, user=protected_user).exists()

    def test_rejected_row_also_rolls_back_weight_and_height_changes(self):
        importing_club, importer, protected_user = self._setup()
        before = _snapshot(protected_user)

        clubs_services.import_players_from_csv(
            club=importing_club,
            imported_by=importer.user,
            csv_file=_csv_upload(
                "email,prenom,nom,poids,taille\n" f"{protected_user.email},X,Y,99,199\n"
            ),
        )

        assert _snapshot(protected_user) == before
        assert _entries(protected_user) == []

    def test_valid_rows_before_and_after_the_rejected_one_are_still_imported(self):
        importing_club, importer, protected_user = self._setup()
        before = _snapshot(protected_user)

        summary = clubs_services.import_players_from_csv(
            club=importing_club,
            imported_by=importer.user,
            csv_file=_csv_upload(
                "email,prenom,nom,telephone\n"
                "avant@example.com,Avant,Joueur,0801010101\n"
                f"{protected_user.email},X,Y,0899999999\n"
                "apres@example.com,Apres,Joueur,0802020202\n"
            ),
        )

        assert summary.batch.row_count_success == 2
        assert summary.batch.row_count_failed == 1
        assert [row.outcome for row in summary.rows] == ["created", "failed", "created"]
        assert [row.line_number for row in summary.rows] == [2, 3, 4]
        assert Membership.all_objects.filter(club=importing_club, user__email="avant@example.com").exists()
        assert Membership.all_objects.filter(club=importing_club, user__email="apres@example.com").exists()
        assert _snapshot(protected_user) == before
        assert _entries(protected_user) == []
        # Les comptes crees par les lignes valides sont bien conserves.
        assert User.objects.get(email="avant@example.com").phone == "0801010101"
        assert User.objects.get(email="apres@example.com").phone == "0802020202"

    def test_valid_update_before_the_rejected_row_keeps_its_own_audit_entry(self):
        """Le rollback est PAR LIGNE : la mise a jour reussie d'une ligne
        precedente (et son entree de journal) n'est pas annulee par
        l'echec d'une ligne suivante."""

        importing_club, importer, protected_user = self._setup()
        before = _snapshot(protected_user)
        member_in_club = MembershipFactory(club=importing_club, user=UserFactory(phone="0811111111"))

        summary = clubs_services.import_players_from_csv(
            club=importing_club,
            imported_by=importer.user,
            csv_file=_csv_upload(
                "email,prenom,nom,telephone\n"
                f"{member_in_club.user.email},X,Y,0822222222\n"
                f"{protected_user.email},X,Y,0899999999\n"
            ),
        )

        assert summary.batch.row_count_success == 1
        assert summary.batch.row_count_failed == 1
        member_in_club.user.refresh_from_db()
        assert member_in_club.user.phone == "0822222222"
        assert len(_entries(member_in_club.user)) == 1
        assert _snapshot(protected_user) == before
        assert _entries(protected_user) == []

    def test_rejected_row_message_stays_neutral_and_does_not_reveal_the_account(self):
        importing_club, importer, protected_user = self._setup()

        summary = clubs_services.import_players_from_csv(
            club=importing_club,
            imported_by=importer.user,
            csv_file=_csv_upload(f"email,prenom,nom,telephone\n{protected_user.email},X,Y,0899999999\n"),
        )

        message = summary.rows[0].message
        assert message.startswith("Ligne 2")
        assert "autre club" not in message
        assert "0811111111" not in message

    def test_two_consecutive_imports_of_the_same_rejected_row_never_change_the_user(self):
        importing_club, importer, protected_user = self._setup()
        before = _snapshot(protected_user)
        content = f"email,prenom,nom,telephone\n{protected_user.email},X,Y,0899999999\n"

        for _ in range(2):
            clubs_services.import_players_from_csv(
                club=importing_club, imported_by=importer.user, csv_file=_csv_upload(content)
            )

        assert _snapshot(protected_user) == before
        assert _entries(protected_user) == []
        assert AuditLog.objects.filter(action_type="clubs.import.created").count() == 2
