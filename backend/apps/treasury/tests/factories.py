"""Factories factory_boy de l'app treasury (tache 1.4b).

Ces factories creent les lignes **directement** (sans passer par les
services) : elles servent a preparer un contexte de test. Tout ce qui
concerne un paiement valide ou une transaction scellee passe au
contraire par les services (`apps.treasury.services`), seuls garants du
chainage (CDC 5.3) : aucune factory de `Transaction` scellee n'est
fournie volontairement.
"""

from __future__ import annotations

from decimal import Decimal

import factory
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.clubs.tests.factories import ClubFactory
from apps.core.tests.factories import TenantDjangoModelFactory
from apps.treasury.models import ContributionType


class ContributionTypeFactory(TenantDjangoModelFactory):
    class Meta:
        model = ContributionType

    club = factory.SubFactory(ClubFactory)
    name = factory.Sequence(lambda n: f"Type de cotisation {n}")
    nature = ContributionType.Nature.MANDATORY
    amount = Decimal("20.00")
    periodicity = ContributionType.Periodicity.MONTHLY
    due_day = 10
    scope = ContributionType.Scope.ALL
    created_by = factory.SubFactory(UserFactory)
    created_at = factory.LazyFunction(timezone.now)


class MembershipFeeTypeFactory(ContributionTypeFactory):
    """Type « adhesion » (CDC 4.3, 4.4.1) : ponctuel, montant fixe."""

    name = factory.Sequence(lambda n: f"Adhesion {n}")
    amount = Decimal("5.00")
    periodicity = ContributionType.Periodicity.ONE_OFF
    due_day = None
    is_membership_fee = True
