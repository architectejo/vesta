"""Preuve que la defense en base (contraintes SQL) reste active meme quand
`full_clean()` est contourne (audit de securite du Lot 1, ecart bloquant
B4).

Les 5 tests pre-existants modifies par backend-dev
(`apps.clubs.tests.test_models` : `test_season_end_date_avant_start_date_rejetee_par_contrainte_db`,
`test_left_reason_requis_si_left_on_renseigne`, `test_jersey_number_hors_plage_rejete`,
`test_application_unique_par_adhesion`, `test_from_et_to_membership_doivent_differer`)
affirment tous, dans leur docstring, que « la contrainte SQL elle-meme reste
en place (defense en profondeur, ex. ``queryset.update()`` qui
contournerait ``save()``) » -- mais aucun test existant n'exerce reellement
ce chemin de contournement : ils passent tous desormais par
``full_clean()`` (``Model.save()``/``Model.objects.create()``), qui
intercepte l'erreur AVANT la base. Vu de la suite de tests seule, la
defense SQL etait devenue invisible (elle pourrait avoir ete supprimee par
erreur d'une migration sans qu'aucun test n'echoue).

Ce module ferme cette question explicitement : chaque test ci-dessous
contourne volontairement ``save()``/``full_clean()`` (``queryset.update()``
ou ``bulk_create()``, qui n'appellent ni l'un ni l'autre) et verifie que la
base de donnees elle-meme rejette toujours la violation
(``django.db.utils.IntegrityError``). Verifie sur SQLite (moteur de
developpement) : a revalider sur MySQL/MariaDB avant fin de lot (CLAUDE.md
§9, « Definition de termine »), les deux moteurs supportant les
``CheckConstraint``/contraintes d'unicite utilisees ici.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone

from apps.clubs.models import Membership, MembershipApplication, PresidencyTransfer, Season
from apps.clubs.tests.factories import (
    MembershipApplicationFactory,
    MembershipFactory,
    PresidencyTransferFactory,
    SeasonFactory,
)


@pytest.mark.django_db
class TestContraintesCheckToujoursActivesEnBaseMalgreLeContournementDeFullClean:
    def test_season_end_after_start_toujours_applique_par_la_base(self):
        season = SeasonFactory()

        with pytest.raises(IntegrityError):
            Season.all_objects.filter(pk=season.pk).update(
                end_date=season.start_date - timezone.timedelta(days=1)
            )

    def test_membership_left_reason_required_if_left_on_toujours_applique_par_la_base(self):
        membership = MembershipFactory(left_on=None, left_reason="")

        with pytest.raises(IntegrityError):
            Membership.all_objects.filter(pk=membership.pk).update(left_on=timezone.now().date())

    def test_membership_jersey_number_range_toujours_applique_par_la_base(self):
        membership = MembershipFactory(jersey_number=10)

        with pytest.raises(IntegrityError):
            Membership.all_objects.filter(pk=membership.pk).update(jersey_number=150)

    def test_presidency_transfer_distinct_memberships_toujours_applique_par_la_base(self):
        transfer = PresidencyTransferFactory()

        with pytest.raises(IntegrityError):
            PresidencyTransfer.all_objects.filter(pk=transfer.pk).update(
                to_membership=F("from_membership")
            )


@pytest.mark.django_db
class TestContrainteUniciteToujoursActiveEnBaseMalgreLeContournementDeFullClean:
    def test_membership_application_unique_par_membership_toujours_applique_par_la_base(self):
        application = MembershipApplicationFactory()

        with pytest.raises(IntegrityError):
            MembershipApplication.all_objects.bulk_create(
                [MembershipApplication(club=application.club, membership=application.membership)]
            )
