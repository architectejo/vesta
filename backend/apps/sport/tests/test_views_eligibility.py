"""Éligibilité groupée pour la modale « Composer l'équipe »
(``sport:eligibility-list`` ; sport-feuille-de-match.md §4.1 et §4.1 bis ;
CDC 4.8 ; CLAUDE.md règle n° 5 ; 10.2 n° 16).

Points critiques : réservée aux rôles qui composent (Coach, Assistant du
Coach), motifs identiques à ceux du contrôle de composition
(``services.get_playability``), aucune donnée médicale, étanchéité entre
clubs, nombre de requêtes indépendant de l'effectif.
"""

from __future__ import annotations

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.tests.factories import SuperuserFactory
from apps.clubs.models import Membership, MembershipRole
from apps.medical.models import HealthRecord
from apps.sport import services
from apps.sport.models import Suspension
from apps.sport.tests.conftest import client_for, make_debtor, make_member
from apps.sport.tests.factories import EventFactory

pytestmark = pytest.mark.django_db

URL = "sport:eligibility-list"


def _arrival(session):
    from apps.sport.services import _club_settings, _club_tz

    tz = _club_tz(_club_settings(session.club))
    return datetime.datetime.combine(session.event.event_date, datetime.time(7, 40), tzinfo=tz)


def _get(user):
    return client_for(user).get(reverse(URL))


def _rows(user) -> dict[int, dict]:
    response = _get(user)
    assert response.status_code == 200, response.data
    body = response.json()
    assert body["count"] == len(body["results"])
    return {row["membership_id"]: row for row in body["results"]}


@pytest.fixture
def blocked(ctx):
    suspended = make_member(ctx.club)
    unfit = make_member(ctx.club)
    event = EventFactory(club=ctx.club, season=ctx.season)
    Suspension.all_objects.create(
        club=ctx.club, membership=suspended, reason=Suspension.Reason.RED_CARD, season=ctx.season,
        matches_total=2, matches_served=1, starts_event=event,
    )
    HealthRecord.all_objects.create(
        club=ctx.club, membership=unfit, fitness_status=HealthRecord.FitnessStatus.UNFIT,
        fitness_return_date=datetime.date(2027, 3, 1), medical_history="MEDHIST-SECRET",
    )
    return {"suspended": suspended, "unfit": unfit}


@pytest.fixture
def assistant(ctx):
    return make_member(ctx.club, roles=[MembershipRole.Role.ASSISTANT_COACH])


# ---------------------------------------------------------------------------
# Motifs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["coach", "assistant"])
def test_le_coach_voit_chaque_motif_lisible(ctx, blocked, assistant, who):
    viewer = ctx.coach if who == "coach" else assistant
    rows = _rows(viewer.user)

    assert rows[ctx.player.pk] == {"membership_id": ctx.player.pk, "eligible": True, "reason_code": "", "reason": ""}
    # 10.3 n° 188 : le Coach et l'Assistant ne savent rien de la dette.
    assert rows[ctx.debtor.pk] == {
        "membership_id": ctx.debtor.pk, "eligible": False, "reason_code": "unavailable", "reason": "Non éligible.",
    }
    assert rows[blocked["suspended"].pk]["reason"] == "Suspendu : encore 1 match(s)."
    assert rows[blocked["suspended"].pk]["reason_code"] == "suspension"
    assert rows[blocked["unfit"].pk]["reason"].startswith("Inapte · retour prévu le ")
    assert rows[blocked["unfit"].pk]["reason_code"] == "unfit"
    assert rows[ctx.pending_member.pk] == {
        "membership_id": ctx.pending_member.pk,
        "eligible": False,
        "reason_code": "pending_membership",
        "reason": "En attente d'adhésion.",
    }


def test_motifs_identiques_au_controle_de_composition(ctx, blocked):
    """Aucune règle dupliquée : chaque ligne reprend exactement le motif que
    ``add_to_composition`` opposerait au Coach (``ensure_playable``, filtré
    par ``describe_reason_for_viewer``)."""

    rows = _rows(ctx.coach.user)
    targets = [ctx.player, ctx.debtor, ctx.pending_member, blocked["suspended"], blocked["unfit"], ctx.coach]
    for membership in targets:
        playability = services.get_playability(membership)
        assert rows[membership.pk]["eligible"] is playability.eligible, membership
        if playability.eligible:
            assert rows[membership.pk]["reason"] == "", membership
            continue
        with pytest.raises(services.PlayerNotEligibleError) as exc:
            services.ensure_playable(membership, actor=ctx.coach.user)
        assert rows[membership.pk]["reason"] == str(exc.value), membership
        if membership.pk != ctx.debtor.pk:
            assert rows[membership.pk]["reason_code"] == playability.reason_code, membership


@pytest.mark.parametrize("who", ["coach", "assistant"])
def test_le_coach_ne_recoit_jamais_montant_devise_ni_dette(ctx, blocked, assistant, who):
    """10.3 n° 188 : aucune réponse vue par le Coach ou l'Assistant (liste
    d'éligibilité, refus de composition, de répartition et de placement,
    zone « Ne peuvent pas jouer ») ne contient le montant, la devise ou
    « dette »."""

    from apps.sport.tests.factories import MatchFactory, SessionFactory

    viewer = ctx.coach if who == "coach" else assistant
    client = client_for(viewer.user)
    texts = [client.get(reverse(URL)).content.decode()]

    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    refused = client.post(
        reverse("sport:match-composition-add", args=[match.pk]),
        {"membership_id": ctx.debtor.pk, "role": "starter", "position": "midfielder", "jersey_number": 9},
    )
    assert refused.status_code == 400 and refused.data["detail"] == "Non éligible."
    texts.append(refused.content.decode())

    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(
        session=session, membership=ctx.debtor, arrived_at=_arrival(session), marked_by=ctx.coach.user
    )
    texts.append(client.get(reverse("sport:session-unassigned", args=[session.pk])).content.decode())

    for text in texts:
        lowered = text.lower()
        for forbidden in ("dette", "debt", "10 $", "10.00", "usd", "amount_due", "balance"):
            assert forbidden not in lowered, (forbidden, text)


def test_get_playabilities_egale_get_playability_pour_chaque_joueur(ctx, blocked):
    memberships = [ctx.player, ctx.debtor, ctx.pending_member, blocked["suspended"], blocked["unfit"]]
    grouped = services.get_playabilities(ctx.club, memberships)
    for membership in memberships:
        assert grouped[membership.pk] == services.get_playability(membership), membership


def test_aucun_diagnostic_ni_donnee_medicale(ctx, blocked):
    text = _get(ctx.coach.user).content.decode()
    assert "MEDHIST-SECRET" not in text
    for forbidden in ("diagnosis", "medical_history", "amount_due", "balance"):
        assert forbidden not in text


def test_les_joueurs_partis_ne_sont_pas_renvoyes(ctx):
    gone = make_member(ctx.club, status=Membership.Status.DEPARTED)
    assert gone.pk not in _rows(ctx.coach.user)


def test_regularisation_sur_place(ctx, monkeypatch):
    """Un paiement qui solde la dette rend le joueur sélectionnable au
    prochain rafraîchissement (CDC 4.8) : aucun cache. Régularisation
    simulée par son effet observable côté trésorerie (même principe que
    ``test_match_composition.test_regularization_allows_composition``)."""

    import apps.treasury.services as treasury_services

    assert _rows(ctx.coach.user)[ctx.debtor.pk]["eligible"] is False
    real = treasury_services.get_balance_summaries

    def all_settled(club, membership_ids, at_date=None):
        return {
            pk: treasury_services.BalanceSummary(
                balance=summary.balance, amount_due=summary.amount_due * 0, is_in_good_standing=True,
                reason="Le joueur est en ordre.", currency=summary.currency,
            )
            for pk, summary in real(club, membership_ids, at_date=at_date).items()
        }

    monkeypatch.setattr(treasury_services, "get_balance_summaries", all_settled)
    assert _rows(ctx.coach.user)[ctx.debtor.pk] == {
        "membership_id": ctx.debtor.pk, "eligible": True, "reason_code": "", "reason": "",
    }


# ---------------------------------------------------------------------------
# Permissions (matrice 2.4 : « Feuille de match et composition », É Coach seul)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role",
    [
        MembershipRole.Role.PRESIDENT,
        MembershipRole.Role.VICE_PRESIDENT,
        MembershipRole.Role.SPORTS_DIRECTOR,
        MembershipRole.Role.TREASURER,
        MembershipRole.Role.ASSISTANT_TREASURER,
        MembershipRole.Role.STEWARD,
        MembershipRole.Role.SECRETARY,
        MembershipRole.Role.CAPTAIN,
        MembershipRole.Role.DOCTOR,
        None,
    ],
)
def test_les_roles_qui_ne_composent_pas_sont_refuses(ctx, role):
    if role is None:
        viewer = ctx.player
    else:
        kwargs = {"role_kwargs": {"is_qualified_professional": True}} if role == MembershipRole.Role.DOCTOR else {}
        viewer = make_member(ctx.club, roles=[role], **kwargs) if role not in (
            MembershipRole.Role.PRESIDENT,
            MembershipRole.Role.VICE_PRESIDENT,
            MembershipRole.Role.SPORTS_DIRECTOR,
            MembershipRole.Role.CAPTAIN,
            MembershipRole.Role.DOCTOR,
        ) else {
            MembershipRole.Role.PRESIDENT: ctx.president,
            MembershipRole.Role.VICE_PRESIDENT: ctx.vice_president,
            MembershipRole.Role.SPORTS_DIRECTOR: ctx.sports_director,
            MembershipRole.Role.CAPTAIN: ctx.captain,
            MembershipRole.Role.DOCTOR: ctx.doctor,
        }[role]
    response = _get(viewer.user)
    assert response.status_code == 403
    assert "results" not in response.data


def test_anonyme_refuse():
    assert APIClient().get(reverse(URL)).status_code == 401


def test_superuser_sans_session_de_support_refuse(ctx):
    assert _get(SuperuserFactory()).status_code == 403


def test_superuser_en_session_de_support_ne_voit_qu_indisponible(ctx, blocked):
    """Lecture autorisée en session de support (``ghost_readable``), mais le
    Superuser n'a aucun rôle du club : ni montant de dette, ni suspension, ni
    inaptitude, ni attente d'adhésion (10.2 n° 16 ; CLAUDE.md règle n° 11)."""

    from rest_framework_simplejwt.tokens import RefreshToken

    from apps.licences.tests.factories import SupportSessionFactory

    superuser = SuperuserFactory()
    support_session = SupportSessionFactory(superuser=superuser, club=ctx.club)
    response = APIClient().get(
        reverse(URL),
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(superuser).access_token}",
        HTTP_X_SUPPORT_SESSION=str(support_session.pk),
    )
    assert response.status_code == 200, response.data
    rows = {row["membership_id"]: row for row in response.json()["results"]}

    assert rows[ctx.player.pk] == {"membership_id": ctx.player.pk, "eligible": True, "reason_code": "", "reason": ""}
    for blocked_member in (ctx.debtor, ctx.pending_member, blocked["suspended"], blocked["unfit"]):
        assert rows[blocked_member.pk] == {
            "membership_id": blocked_member.pk,
            "eligible": False,
            "reason_code": "unavailable",
            "reason": "Indisponible",
        }, blocked_member

    text = response.content.decode()
    for forbidden in ("En dette", "10 $", "USD", "Inapte", "retour prévu", "Suspendu", "MEDHIST-SECRET", "amount_due"):
        assert forbidden not in text, forbidden


def test_coach_revoque_refuse(ctx):
    from django.utils import timezone

    MembershipRole.all_objects.filter(membership=ctx.coach, role=MembershipRole.Role.COACH).update(
        revoked_at=timezone.now()
    )
    assert _get(ctx.coach.user).status_code == 403


def test_le_motif_de_dette_reste_filtre_par_le_point_unique(ctx):
    """Défense en profondeur : même si un rôle non autorisé à voir la dette
    recevait la liste, le filtrage (10.2 n° 16) masquerait le motif."""

    from apps.sport import serializers as sport_serializers

    rows = {
        row["membership_id"]: row
        for row in sport_serializers.serialize_eligibility_list(
            [ctx.debtor, ctx.pending_member], viewer=ctx.captain.user, club=ctx.club
        )
    }
    assert rows[ctx.debtor.pk] == {
        "membership_id": ctx.debtor.pk, "eligible": False, "reason_code": "unavailable", "reason": "Indisponible",
    }
    assert rows[ctx.pending_member.pk]["reason"] == "Indisponible"


# ---------------------------------------------------------------------------
# Étanchéité et performance
# ---------------------------------------------------------------------------


def test_etancheite_entre_clubs(ctx, other_ctx):
    rows = _rows(ctx.coach.user)
    other_ids = {
        m.pk
        for m in (
            other_ctx.player, other_ctx.debtor, other_ctx.pending_member, other_ctx.coach, other_ctx.president,
        )
    }
    assert not (set(rows) & other_ids)
    assert {ctx.player.pk, ctx.debtor.pk, ctx.pending_member.pk, ctx.coach.pk} <= set(rows)
    # Le Coach de l'autre club ne voit que les siens.
    assert not (set(_rows(other_ctx.coach.user)) & set(rows))


def test_un_coach_d_un_autre_club_ne_voit_pas_les_motifs_de_ce_club(ctx, other_ctx):
    """Le club actif vient de l'adhésion (CLAUDE.md règle n° 9) : aucun
    paramètre ne permet de viser un autre club."""

    response = client_for(other_ctx.coach.user).get(reverse(URL), {"club": ctx.club.pk})
    assert response.status_code == 200
    assert ctx.debtor.pk not in {row["membership_id"] for row in response.json()["results"]}


def _count(user) -> int:
    client = client_for(user)
    with CaptureQueriesContext(connection) as ctx_queries:
        assert client.get(reverse(URL)).status_code == 200
    return len(ctx_queries.captured_queries)


def test_nombre_de_requetes_independant_de_l_effectif(ctx, blocked):
    small = _count(ctx.coach.user)
    for _ in range(30):
        make_member(ctx.club)
    for _ in range(5):
        make_debtor(ctx.club, make_member(ctx.club))
    big = _count(ctx.coach.user)
    assert big <= small + 2, (small, big)
