"""Tests HTTP de l'app assemblies (CDC 4.15 ; tache 4.5)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.assemblies.models import Assembly, Minutes
from apps.assemblies.tests.factories import AgendaItemFactory, AssemblyFactory
from apps.audit.models import AuditLog
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import ClubFactory, ClubSettingsFactory, MembershipFactory, MembershipRoleFactory

pytestmark = pytest.mark.django_db


def _authenticated_client(user) -> APIClient:
    client = APIClient()
    access_token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return client


def _club():
    return ClubSettingsFactory(timezone="Africa/Kinshasa").club


def _president(club):
    membership = MembershipFactory(club=club)
    MembershipRoleFactory(membership=membership, role=MembershipRole.Role.PRESIDENT)
    return membership


def _vp(club):
    membership = MembershipFactory(club=club)
    MembershipRoleFactory(membership=membership, role=MembershipRole.Role.VICE_PRESIDENT)
    return membership


class TestConveneEndpoint:
    def test_president_convenes_an_assembly(self):
        club = _club()
        president = _president(club)
        payload = {
            "assembly_type": "ordinary",
            "scheduled_date": str((timezone.now() + timedelta(days=5)).date()),
            "scheduled_time": "18:00:00",
            "location": "Terrain",
            "agenda_items": [{"title": "Bilan"}],
        }

        response = _authenticated_client(president.user).post(reverse("assemblies:assembly-list"), payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["can_manage"] is True
        assert response.data["quorum"]["threshold"] == "50.00"

    def test_plain_player_cannot_convene(self):
        club = _club()
        _president(club)
        player = MembershipFactory(club=club)
        payload = {
            "assembly_type": "ordinary",
            "scheduled_date": str((timezone.now() + timedelta(days=5)).date()),
            "scheduled_time": "18:00:00",
            "agenda_items": [{"title": "Bilan"}],
        }

        response = _authenticated_client(player.user).post(reverse("assemblies:assembly-list"), payload, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_another_clubs_assembly_is_not_visible(self):
        club_a = _club()
        club_b = _club()
        president_a = _president(club_a)
        assembly_b = AssemblyFactory(club=club_b)

        response = _authenticated_client(president_a.user).get(
            reverse("assemblies:assembly-detail", kwargs={"pk": assembly_b.pk})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["detail"] == "Cette assemblée n'existe pas dans ce club."


class TestAttendanceEndpoint:
    def test_president_marks_a_presence_the_day_of_the_assembly(self):
        club = _club()
        president = _president(club)
        member = MembershipFactory(club=club)
        assembly = AssemblyFactory(club=club, scheduled_date=timezone.now().date())

        response = _authenticated_client(president.user).post(
            reverse("assemblies:assembly-attendance", kwargs={"pk": assembly.pk}),
            {"membership_id": member.id},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.data

    def test_marking_a_presence_outside_the_assembly_day_is_refused(self):
        club = _club()
        president = _president(club)
        member = MembershipFactory(club=club)
        assembly = AssemblyFactory(club=club, scheduled_date=(timezone.now() + timedelta(days=3)).date())

        response = _authenticated_client(president.user).post(
            reverse("assemblies:assembly-attendance", kwargs={"pk": assembly.pk}),
            {"membership_id": member.id},
            format="json",
        )

        assert response.status_code == status.HTTP_409_CONFLICT

    def test_attendance_list_never_exposes_a_status_badge_field(self):
        """10.2 n° 16 : aucun statut de joueur (dette, suspension, aptitude)."""

        club = _club()
        president = _president(club)
        MembershipFactory(club=club)
        assembly = AssemblyFactory(club=club, scheduled_date=timezone.now().date())

        response = _authenticated_client(president.user).get(
            reverse("assemblies:assembly-attendance", kwargs={"pk": assembly.pk})
        )

        assert response.status_code == status.HTTP_200_OK
        for row in response.data["results"]:
            assert "status" not in row
            assert "debt" not in row


class TestDecisionEndpoint:
    def test_recording_a_vote_never_blocks_even_if_quorum_not_reached(self):
        club = _club()
        president = _president(club)
        assembly = AssemblyFactory(club=club)
        agenda_item = AgendaItemFactory(assembly=assembly, club=club, order=1)
        for _ in range(10):
            MembershipFactory(club=club)  # aucun ne sera pointe present

        response = _authenticated_client(president.user).put(
            reverse("assemblies:assembly-decision", kwargs={"pk": assembly.pk, "agenda_item_id": agenda_item.pk}),
            {"votes_for": 3, "votes_against": 0, "votes_abstain": 0, "outcome": "Adopte"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data


class TestMinutesSignAndPdf:
    def test_full_signature_flow_and_authenticated_pdf_download(self):
        club = _club()
        president = _president(club)
        vp = _vp(club)
        assembly = AssemblyFactory(club=club)

        pres_client = _authenticated_client(president.user)
        vp_client = _authenticated_client(vp.user)

        draft_response = pres_client.put(
            reverse("assemblies:assembly-minutes", kwargs={"pk": assembly.pk}), {"content": "Texte du PV."}, format="json"
        )
        assert draft_response.status_code == status.HTTP_200_OK

        sign1 = pres_client.post(
            reverse("assemblies:assembly-minutes-sign", kwargs={"pk": assembly.pk}), {}, format="json"
        )
        assert sign1.status_code == status.HTTP_200_OK
        assert sign1.data["is_complete"] is False

        sign2 = vp_client.post(
            reverse("assemblies:assembly-minutes-sign", kwargs={"pk": assembly.pk}), {}, format="json"
        )
        assert sign2.status_code == status.HTTP_200_OK
        assert sign2.data["is_complete"] is True
        assert sign2.data["pdf_url"] == reverse("assemblies:minutes-pdf-download", kwargs={"pk": assembly.pk})

        download = pres_client.get(sign2.data["pdf_url"])
        assert download.status_code == status.HTTP_200_OK
        assert download["Content-Type"] == "application/pdf"
        assert download["Content-Disposition"].startswith("attachment")

    def test_pdf_not_reachable_for_another_club(self):
        club_a = _club()
        club_b = _club()
        president_a = _president(club_a)
        president_b = _president(club_b)
        assembly_b = AssemblyFactory(club=club_b)

        b_client = _authenticated_client(president_b.user)
        b_client.put(
            reverse("assemblies:assembly-minutes", kwargs={"pk": assembly_b.pk}), {"content": "Texte"}, format="json"
        )
        b_client.post(
            reverse("assemblies:assembly-minutes-sign", kwargs={"pk": assembly_b.pk}), {}, format="json"
        )

        response = _authenticated_client(president_a.user).get(
            reverse("assemblies:minutes-pdf-download", kwargs={"pk": assembly_b.pk})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_signature_succeeds_without_pin_and_a_sent_pin_is_ignored(self):
        club = _club()
        president = _president(club)
        vp = _vp(club)
        assembly = AssemblyFactory(club=club)
        pres_client = _authenticated_client(president.user)
        vp_client = _authenticated_client(vp.user)
        pres_client.put(reverse("assemblies:assembly-minutes", kwargs={"pk": assembly.pk}), {"content": "Texte"}, format="json")
        url = reverse("assemblies:assembly-minutes-sign", kwargs={"pk": assembly.pk})

        without_pin = pres_client.post(url, {}, format="json")
        with_garbage_pin = vp_client.post(url, {"pin": "0000"}, format="json")

        assert without_pin.status_code == status.HTTP_200_OK
        assert with_garbage_pin.status_code == status.HTTP_200_OK
        assert with_garbage_pin.data["is_complete"] is True
        entry = AuditLog.objects.filter(action_type="assemblies.minutes.signed").order_by("id")
        assert [e.actor_id for e in entry] == [president.user.id, vp.user.id]

    def test_unauthorized_role_is_still_refused_without_pin(self):
        club = _club()
        president = _president(club)
        player = MembershipFactory(club=club)
        assembly = AssemblyFactory(club=club)
        _authenticated_client(president.user).put(
            reverse("assemblies:assembly-minutes", kwargs={"pk": assembly.pk}), {"content": "Texte"}, format="json"
        )

        response = _authenticated_client(player.user).post(
            reverse("assemblies:assembly-minutes-sign", kwargs={"pk": assembly.pk}), {}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestQuorumThresholdEndpoint:
    def test_president_updates_the_threshold(self):
        club = _club()
        president = _president(club)

        response = _authenticated_client(president.user).put(
            reverse("assemblies:quorum-threshold"), {"percentage": 75}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["percentage"] == "75.00"

    def test_plain_player_cannot_update_the_threshold(self):
        club = _club()
        _president(club)
        player = MembershipFactory(club=club)

        response = _authenticated_client(player.user).put(
            reverse("assemblies:quorum-threshold"), {"percentage": 75}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_out_of_range_value_is_rejected(self):
        club = _club()
        president = _president(club)

        response = _authenticated_client(president.user).put(
            reverse("assemblies:quorum-threshold"), {"percentage": 0}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
