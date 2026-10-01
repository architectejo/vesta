"""Tests de `apps.audit.serializers.AuditLogSerializer` (CDC 5.4 ; tache 1.8t).

Revue independante de test-engineer : ce fichier n'existait pas encore
(aucun test ne couvrait ce serializer). Le point verifie ici est
directement issu de la docstring meme du serializer, qui presente
explicitement ``AuditLogSerializer`` comme « prete a etre reutilisee [...]
par tout autre module qui exposerait un jour l'acteur d'une action a un
club » (voir `apps/audit/serializers.py`) -- c'est-a-dire un lecteur qui
n'est PAS un Superuser.
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.audit.serializers import AuditLogSerializer
from apps.audit.services import GHOST_ACTOR_DISPLAY_NAME, create_audit_log
from apps.clubs.tests.factories import ClubFactory


class _FakeRequest:
    def __init__(self, user):
        self.user = user


@pytest.mark.django_db
class TestAuditLogSerializerGhostModeLeak:
    """BUG REEL (a signaler a backend-dev) : `AuditLogSerializer` expose
    `actor_id` (l'identifiant REEL du Superuser) EN CLAIR dans son
    payload, sans le moindre masquage, alors meme que sa propre
    docstring la presente comme reutilisable par « tout module qui
    exposerait un jour l'acteur d'une action a un club » -- c'est-a-dire
    exactement le scenario que le masquage Ghost Mode (CDC 5.4 : «
    l'identite reelle du Superuser ne doit jamais transpirer cote club »)
    est cense empecher.

    `actor_display` est bien masque (« Systeme Vesta ») pour un lecteur
    non-Superuser, mais `actor_id` reste present et EXPLOITABLE dans le
    MEME payload JSON : un simple appel a l'API de recherche de comptes
    (deja Superuser-only, mais rien dans CE serializer lui-meme ne
    l'empeche d'etre branche un jour sur un ecran cote club, comme sa
    docstring le suggere) suffit alors a retrouver l'identite reelle
    malgre le masquage cote affichage.

    Ce test echoue AUJOURD'HUI : il prouve que le payload serialise
    contient encore l'identifiant reel, contrairement a ce qu'annonce la
    docstring du serializer (« lisible seulement par un Superuser de
    toute facon ») -- affirmation qui n'est vraie que si CHAQUE futur
    appelant s'en souvient et ajoute lui-meme un filtre, ce que rien dans
    ce module ne garantit ni ne verifie.
    """

    def test_actor_id_reste_expose_en_clair_malgre_le_masquage_ghost_mode(self):
        superuser = SuperuserFactory()
        club = ClubFactory()
        entry = create_audit_log(
            actor=superuser,
            club=club,
            action_type="treasury.payment.corrected",
            object_type="Payment",
            object_id=1,
            acted_as_ghost=True,
            support_session_id="42",
        )

        club_member = UserFactory()
        payload = AuditLogSerializer(entry, context={"request": _FakeRequest(club_member)}).data

        assert payload["actor_display"] == GHOST_ACTOR_DISPLAY_NAME

        # BUG : `actor_id` reste l'identifiant REEL du Superuser dans le
        # MEME payload que celui destine a un lecteur non-Superuser --
        # le masquage de `actor_display` ne protege rien puisque
        # `actor_id` permet de retrouver la meme identite en clair.
        assert payload["actor_id"] != superuser.id, (
            "BUG REEL (CDC 5.4) : AuditLogSerializer expose `actor_id` "
            f"({payload['actor_id']!r}) EN CLAIR pour un lecteur "
            "non-Superuser, alors que `actor_display` est correctement "
            "masque en 'Systeme Vesta' -- l'identite reelle du Superuser "
            "transpire donc quand meme dans le meme payload, exactement "
            "le scenario que CDC 5.4 interdit. Ce serializer ne doit "
            "jamais exposer `actor_id` sans le meme masquage que "
            "`actor_display`, ou doit explicitement retirer ce champ "
            "avant d'etre reutilise par un ecran cote club (voir sa "
            "propre docstring, qui promeut justement cette reutilisation)."
        )
