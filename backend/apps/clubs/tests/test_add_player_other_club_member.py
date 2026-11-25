"""D-A1 : un compte déjà membre (actif ou en attente) d'un AUTRE club n'est pas enrôlé.

Position prudente provisoire (question client) : refus avec message neutre,
sans rien écrire ni révéler l'autre club. La reprise d'un compte « parti » reste possible.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from apps.clubs import services as clubs_services
from apps.clubs.models import Membership
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.clubs.tests.test_add_player_atomicity import _authenticated_client, _counts
from apps.clubs.tests.test_membership_application import build_context

pytestmark = pytest.mark.django_db


def _payload(ctx, email):
    return {
        "email": email,
        "first_name": "Déjà",
        "last_name": "Membre",
        "position": Membership.Position.MIDFIELDER,
        "sponsor_membership_id": ctx.sponsor.id,
    }


@pytest.mark.parametrize("other_status", [Membership.Status.ACTIVE, Membership.Status.PENDING])
def test_api_add_refuses_account_member_of_another_club(other_status):
    ctx = build_context()
    other = MembershipFactory(club=ClubFactory(), status=other_status)
    before = _counts()

    response = _authenticated_client(ctx.president.user).post(
        reverse("clubs:players-add"), _payload(ctx, other.user.email)
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "ne peut pas être ajouté" in response.data["detail"]
    assert _counts() == before
    assert Membership.all_objects.filter(user=other.user).count() == 1
    other.refresh_from_db()
    assert other.status == other_status


def test_api_add_still_accepts_departed_account_and_new_email():
    ctx = build_context()
    departed = MembershipFactory(club=ClubFactory(), status=Membership.Status.DEPARTED)
    client = _authenticated_client(ctx.president.user)

    assert client.post(
        reverse("clubs:players-add"), _payload(ctx, departed.user.email)
    ).status_code == status.HTTP_201_CREATED


def test_csv_import_row_fails_with_message_and_other_club_untouched():
    club = ClubFactory()
    recruiter = MembershipFactory(club=club)
    other = MembershipFactory(club=ClubFactory(), status=Membership.Status.ACTIVE)
    content = f"email,prenom,nom\n{other.user.email},Un,Autre\nnouveau@example.com,Neuf,Joueur\n"

    summary = clubs_services.import_players_from_csv(
        club=club,
        imported_by=recruiter.user,
        csv_file=SimpleUploadedFile("i.csv", content.encode("utf-8"), content_type="text/csv"),
    )

    assert Membership.all_objects.filter(club=club, user__email="nouveau@example.com").exists()
    assert not Membership.all_objects.filter(club=club, user=other.user).exists()
    failed = [row for row in summary.rows if row.outcome == "failed"]
    assert len(failed) == 1 and "ne peut pas être ajouté" in failed[0].message
    assert Membership.all_objects.filter(user=other.user).count() == 1
