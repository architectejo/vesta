"""Messages d'erreur affichés à l'utilisateur : français clair, accentué,
sans référence technique (CLAUDE.md règle 20)."""

from __future__ import annotations

import inspect

import pytest

from apps.clubs import permissions as clubs_permissions
from apps.clubs import services as clubs_services
from apps.clubs.tests.test_membership_application import add_player, build_context, pay


def test_permission_messages_have_no_technical_reference():
    messages = [
        cls.message
        for _name, cls in inspect.getmembers(clubs_permissions, inspect.isclass)
        if cls.__module__ == clubs_permissions.__name__ and isinstance(getattr(cls, "message", None), str)
    ]
    assert messages
    for message in messages:
        assert "CDC" not in message
        assert "Reserve" not in message
        assert "President" not in message


@pytest.mark.django_db
class TestSponsorMessages:
    def test_non_sponsor_cannot_sign_with_clear_message(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)

        with pytest.raises(PermissionError) as exc_info:
            clubs_services.sign_sponsor_application(
                application=application, sponsor_user=ctx.president.user
            )

        assert str(exc_info.value) == "Seul le parrain désigné pour ce dossier peut le signer."

    def test_refusal_without_reason_has_clear_message(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)

        with pytest.raises(clubs_services.MembershipApplicationError) as exc_info:
            clubs_services.refuse_sponsor_application(
                application=application, sponsor_user=ctx.sponsor.user, reason="  "
            )

        message = str(exc_info.value)
        assert message == "Un motif est obligatoire pour refuser de parrainer un joueur."
        assert "CDC" not in message
