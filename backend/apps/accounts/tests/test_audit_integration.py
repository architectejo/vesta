"""Tests de la journalisation de l'acceptation des CGU (tache 1.6, 1.6t).

Sources : CLAUDE.md regle n6 ; 10.2 n27, CDC 7.5.
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import TermsAcceptanceFactory
from apps.audit.models import AuditLog


@pytest.mark.django_db
def test_acceptation_des_cgu_cree_une_entree_de_portee_plateforme():
    acceptance = TermsAcceptanceFactory()

    entry = AuditLog.objects.get(
        action_type="accounts.terms.accepted", object_id=str(acceptance.pk)
    )
    assert entry.actor_id == acceptance.user_id
    assert entry.club_id is None
    assert entry.after["terms_version_id"] == acceptance.terms_version_id
