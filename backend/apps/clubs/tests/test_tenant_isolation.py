"""Tests d'isolation multi-tenant de `Membership` (tache 1.2 / 1.2t).

Sources : CLAUDE.md regle n8 ; CDC 6.3 ; docs/lot0/plan-lots.md (1.2, 1.2t).
"""

from __future__ import annotations

import pytest

from apps.clubs.models import (
    ImportBatch,
    Membership,
    MembershipApplication,
    MembershipRole,
    PresidencyTransfer,
    Season,
)
from apps.clubs.tests.factories import (
    ClubFactory,
    ImportBatchFactory,
    MembershipApplicationFactory,
    MembershipFactory,
    MembershipRoleFactory,
    PresidencyTransferFactory,
    SeasonFactory,
)
from apps.core.tenant import NoActiveClubError, active_club


@pytest.mark.django_db
def test_requete_sans_club_actif_est_refusee():
    """CLAUDE.md regle n8 : "une requete sans club actif est refusee"."""

    MembershipFactory()

    with pytest.raises(NoActiveClubError):
        list(Membership.objects.all())


@pytest.mark.django_db
def test_membership_du_club_a_invisible_depuis_le_club_b():
    """Un `Membership` du club A n'apparait jamais dans une requete scopee au club B."""

    club_a = ClubFactory()
    club_b = ClubFactory()

    membership_a = MembershipFactory(club=club_a)
    membership_b = MembershipFactory(club=club_b)

    with active_club(club_a):
        visibles_a = list(Membership.objects.all())
        assert membership_a in visibles_a
        assert membership_b not in visibles_a
        assert all(m.club_id == club_a.id for m in visibles_a)

    with active_club(club_b):
        visibles_b = list(Membership.objects.all())
        assert membership_b in visibles_b
        assert membership_a not in visibles_b
        assert all(m.club_id == club_b.id for m in visibles_b)


@pytest.mark.django_db
def test_season_du_club_a_invisible_depuis_le_club_b():
    """Etancheite sur `Season` (schema §4.3), pas seulement `Membership`."""

    club_a = ClubFactory()
    club_b = ClubFactory()
    season_a = SeasonFactory(club=club_a)
    season_b = SeasonFactory(club=club_b)

    with active_club(club_a):
        visibles_a = list(Season.objects.all())
        assert season_a in visibles_a
        assert season_b not in visibles_a

    with active_club(club_b):
        visibles_b = list(Season.objects.all())
        assert season_b in visibles_b
        assert season_a not in visibles_b


@pytest.mark.django_db
def test_membership_role_du_club_a_invisible_depuis_le_club_b():
    """Etancheite sur `MembershipRole` (schema §3.4)."""

    club_a = ClubFactory()
    club_b = ClubFactory()
    role_a = MembershipRoleFactory(membership=MembershipFactory(club=club_a))
    role_b = MembershipRoleFactory(membership=MembershipFactory(club=club_b))

    with active_club(club_a):
        visibles_a = list(MembershipRole.objects.all())
        assert role_a in visibles_a
        assert role_b not in visibles_a

    with active_club(club_b):
        visibles_b = list(MembershipRole.objects.all())
        assert role_b in visibles_b
        assert role_a not in visibles_b


@pytest.mark.django_db
def test_membership_application_du_club_a_invisible_depuis_le_club_b():
    """Etancheite sur `MembershipApplication` (schema §3.3, parrainage CDC 4.3)."""

    club_a = ClubFactory()
    club_b = ClubFactory()
    application_a = MembershipApplicationFactory(membership=MembershipFactory(club=club_a))
    application_b = MembershipApplicationFactory(membership=MembershipFactory(club=club_b))

    with active_club(club_a):
        visibles_a = list(MembershipApplication.objects.all())
        assert application_a in visibles_a
        assert application_b not in visibles_a

    with active_club(club_b):
        visibles_b = list(MembershipApplication.objects.all())
        assert application_b in visibles_b
        assert application_a not in visibles_b


@pytest.mark.django_db
def test_presidency_transfer_du_club_a_invisible_depuis_le_club_b():
    """Etancheite sur `PresidencyTransfer` (schema §3.5)."""

    club_a = ClubFactory()
    club_b = ClubFactory()
    transfer_a = PresidencyTransferFactory(from_membership=MembershipFactory(club=club_a))
    transfer_b = PresidencyTransferFactory(from_membership=MembershipFactory(club=club_b))

    with active_club(club_a):
        visibles_a = list(PresidencyTransfer.objects.all())
        assert transfer_a in visibles_a
        assert transfer_b not in visibles_a

    with active_club(club_b):
        visibles_b = list(PresidencyTransfer.objects.all())
        assert transfer_b in visibles_b
        assert transfer_a not in visibles_b


@pytest.mark.django_db
def test_import_batch_du_club_a_invisible_depuis_le_club_b():
    """Etancheite sur `ImportBatch` (schema §4.7)."""

    club_a = ClubFactory()
    club_b = ClubFactory()
    batch_a = ImportBatchFactory(club=club_a)
    batch_b = ImportBatchFactory(club=club_b)

    with active_club(club_a):
        visibles_a = list(ImportBatch.objects.all())
        assert batch_a in visibles_a
        assert batch_b not in visibles_a

    with active_club(club_b):
        visibles_b = list(ImportBatch.objects.all())
        assert batch_b in visibles_b
        assert batch_a not in visibles_b


@pytest.mark.django_db
def test_all_objects_reste_non_filtre_pour_usage_plateforme_explicite():
    """`all_objects` est l'echappement documente (cron, imports, Superuser)."""

    club_a = ClubFactory()
    club_b = ClubFactory()
    membership_a = MembershipFactory(club=club_a)
    membership_b = MembershipFactory(club=club_b)

    tous = list(Membership.all_objects.all())
    assert membership_a in tous
    assert membership_b in tous

    seulement_a = list(Membership.all_objects.for_club(club_a))
    assert membership_a in seulement_a
    assert membership_b not in seulement_a
