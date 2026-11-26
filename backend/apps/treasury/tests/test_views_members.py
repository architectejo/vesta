"""Tableau « Membres du club » du tableau de bord Trésorerie et modale
« Situation financière » d'un membre (CDC 4.4.2, 4.4.6 ; fiche
docs/ecrans/tresorerie-tableau-de-bord.md §3 point 3 et §4.3 ; matrice 2.4).

Couvre : solde calculé (jamais stocké, identique à ``services.get_balance``),
statuts En ordre / En dette / En attente / Suspendu / Parti, filtres
(statut, type de cotisation, recherche), tris, pagination ``limit``/
``offset``, rôles (Pdt, VP, Trés, Adj seulement), étanchéité entre clubs,
absence de toute donnée médicale, nombre de requêtes SQL constant, détail
financier (impayés, prochaine échéance, cotisations libres), ligne de
grille d'un membre et filtre « paiements d'un membre » de la liste des
paiements.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import MembershipRoleFactory, SeasonFactory
from apps.sport.models import Suspension
from apps.sport.tests.factories import EventFactory
from apps.treasury import services
from apps.treasury.models import ContributionType, Due
from apps.treasury.tests.cash_helpers import club_today, free_type, monthly_type, named_member, put_in_debt
from apps.treasury.tests.conftest import make_member

pytestmark = pytest.mark.django_db

READERS = ["president", "vice_president", "treasurer", "assistant_treasurer"]
FORBIDDEN_ROLES = [
    MembershipRole.Role.SPORTS_DIRECTOR,
    MembershipRole.Role.STEWARD,
    MembershipRole.Role.COACH,
    MembershipRole.Role.CAPTAIN,
    MembershipRole.Role.DOCTOR,
    MembershipRole.Role.PLAYER_RECRUITER,
]
LIST_URL = reverse("treasury:member-list")
PAYMENTS_URL = reverse("treasury:payment-create")

ROW_KEYS = {
    "membership_id",
    "first_name",
    "last_name",
    "name",
    "jersey_number",
    "photo",
    "membership_status",
    "membership_status_label",
    "financial_status",
    "financial_status_label",
    "statuses",
    "is_suspended",
    "suspension_matches_remaining",
    "balance",
    "amount_due",
    "is_in_good_standing",
    "reason",
    "currency",
    "monthly_type",
    "last_payment_on",
}
DETAIL_EXTRA_KEYS = {"today", "next_due", "unpaid_months", "free_contributions", "can_record_payment"}
# Aucune donnée médicale ni coordonnée personnelle dans ces réponses (CLAUDE.md
# règle n° 11 ; matrice 2.4 « Fiches de santé » : — pour Trés, Adj, VP).
FORBIDDEN_KEYS = {"fitness", "aptitude", "diagnosis", "health", "medical", "injury", "email", "phone", "return_date"}


def client_for(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def member_with_role(ctx, role):
    """Joueur portant ``role`` ; la nomination du Médecin exige le choix
    explicite « qualifié ou non » (CDC 4.12)."""

    member = make_member(ctx.club)
    MembershipRoleFactory(
        membership=member,
        club=ctx.club,
        role=role,
        appointed_at=timezone.now(),
        is_qualified_professional=True if role == MembershipRole.Role.DOCTOR else None,
    )
    return member


def detail_url(membership) -> str:
    return reverse("treasury:member-detail", args=[membership.pk])


def grid_url(membership, year: int) -> str:
    return reverse("treasury:member-grid", args=[membership.pk, year])


def months_ago(ctx, count: int) -> datetime.date:
    period = club_today(ctx).replace(day=1)
    for _ in range(count):
        period = (period - datetime.timedelta(days=1)).replace(day=1)
    return period


def pay(ctx, membership, ctype, *, amount, paid_on, method="cash", reference=""):
    return services.record_payment(
        membership=membership,
        contribution_type=ctype,
        amount=amount,
        method=method,
        reference=reference,
        paid_on=paid_on,
        recorded_by=ctx.treasurer.user,
    )


def suspend(ctx, membership, *, matches_total=2, matches_served=0, lifted=False):
    season = SeasonFactory(club=ctx.club)
    event = EventFactory(club=ctx.club, season=season)
    return Suspension.all_objects.create(
        club=ctx.club,
        membership=membership,
        reason=Suspension.Reason.RED_CARD,
        season=season,
        matches_total=matches_total,
        matches_served=matches_served,
        lifted_at=timezone.now() if lifted else None,
        starts_event=event,
    )


def all_rows(client, **params):
    params.setdefault("limit", 100)
    response = client.get(LIST_URL, params)
    assert response.status_code == 200, response.content
    return response.json()["results"]


def ids_of(rows) -> list[int]:
    return [row["membership_id"] for row in rows]


@pytest.fixture
def scenario(ctx):
    """Il y a deux mois (mois M) : Alain, Bruno, Cédric et Paul (parti)
    doivent 10 $ chacun (montant dû échu). Alain paie 10 (solde 0) et verse
    3 $ sur un type libre ; Bruno paie 4 (solde -6) ; Cédric ne paie rien
    (-10) ; Denis, sans montant dû, paie 30 d'avance (+30) ; Paul est parti
    avec sa dette (-10)."""

    ctype = monthly_type(ctx)
    free = free_type(ctx)
    month = months_ago(ctx, 2)
    paid_on = month.replace(day=15)
    alain = named_member(ctx, first_name="Alain", last_name="Aa", jersey_number=7)
    bruno = named_member(ctx, first_name="Bruno", last_name="Bb", jersey_number=9)
    cedric = named_member(ctx, first_name="Cédric", last_name="Cc")
    denis = named_member(ctx, first_name="Denis", last_name="Dd")
    paul = named_member(ctx, first_name="Paul", last_name="Pp", status=Membership.Status.DEPARTED)
    for member in (alain, bruno, cedric, paul):
        put_in_debt(ctx, member, ctype, amount="10", months_ago=2)
    pay_alain = pay(ctx, alain, ctype, amount="10", paid_on=paid_on)
    pay_free = pay(ctx, alain, free, amount="3", paid_on=paid_on + datetime.timedelta(days=1))
    pay_bruno = pay(ctx, bruno, ctype, amount="4", paid_on=paid_on, method="mobile_money", reference="MM-1")
    pay_denis = pay(ctx, denis, ctype, amount="30", paid_on=club_today(ctx) - datetime.timedelta(days=2))
    return {
        "ctype": ctype, "free": free, "month": month, "paid_on": paid_on,
        "alain": alain, "bruno": bruno, "cedric": cedric, "denis": denis, "paul": paul,
        "pay_alain": pay_alain, "pay_free": pay_free, "pay_bruno": pay_bruno, "pay_denis": pay_denis,
    }


# ---------------------------------------------------------------------------
# Liste « Membres du club »
# ---------------------------------------------------------------------------


class TestMemberList:
    def test_tri_par_defaut_solde_croissant_dettes_en_premier(self, ctx, scenario):
        response = client_for(ctx.treasurer.user).get(LIST_URL)
        assert response.status_code == 200
        data = response.json()
        assert data["currency"] == "USD"
        assert data["ordering"] == "balance"
        # 6 membres du contexte (bureau compris : tout utilisateur est un
        # joueur) + Alain, Bruno, Cédric, Denis ; Paul (parti) exclu par défaut.
        assert data["count"] == 10
        assert data["limit"] == 20
        assert data["offset"] == 0
        assert data["next_offset"] is None
        ids = ids_of(data["results"])
        assert ids[:2] == [scenario["cedric"].pk, scenario["bruno"].pk]
        assert ids[-1] == scenario["denis"].pk
        assert scenario["paul"].pk not in ids
        balances = [Decimal(row["balance"]) for row in data["results"]]
        assert balances == sorted(balances)

    def test_forme_exacte_d_une_ligne(self, ctx, scenario):
        rows = {row["membership_id"]: row for row in all_rows(client_for(ctx.treasurer.user))}
        bruno = rows[scenario["bruno"].pk]
        assert set(bruno) == ROW_KEYS
        assert bruno["first_name"] == "Bruno"
        assert bruno["last_name"] == "Bb"
        assert bruno["name"] == "Bruno Bb"
        assert bruno["jersey_number"] == 9
        assert bruno["photo"] is None
        assert bruno["membership_status"] == "active"
        assert bruno["membership_status_label"] == "Inscrit"
        assert bruno["financial_status"] == "in_debt"
        assert bruno["financial_status_label"] == "En dette"
        assert bruno["statuses"] == [{"key": "in_debt", "label": "En dette"}]
        assert bruno["is_suspended"] is False
        assert bruno["suspension_matches_remaining"] is None
        assert bruno["balance"] == "-6.00"
        assert bruno["amount_due"] == "6.00"
        assert bruno["is_in_good_standing"] is False
        assert bruno["reason"] == "Le joueur est en dette : 6.00 USD à régulariser."
        assert bruno["currency"] == "USD"
        assert bruno["monthly_type"] == {"id": scenario["ctype"].pk, "name": "Mensuelle 10"}
        assert bruno["last_payment_on"] == scenario["paid_on"].isoformat()

        denis = rows[scenario["denis"].pk]
        assert denis["balance"] == "30.00"
        assert denis["amount_due"] == "0.00"
        assert denis["financial_status"] == "in_good_standing"
        assert denis["statuses"] == [{"key": "in_good_standing", "label": "En ordre"}]
        # Dernier paiement : tous types confondus (le versement libre d'Alain compte).
        assert rows[scenario["alain"].pk]["last_payment_on"] == (scenario["paid_on"] + datetime.timedelta(days=1)).isoformat()
        assert rows[scenario["cedric"].pk]["last_payment_on"] is None

    def test_solde_identique_au_service_jamais_stocke(self, ctx, scenario):
        for row in all_rows(client_for(ctx.president.user)):
            membership = Membership.all_objects.get(pk=row["membership_id"])
            assert Decimal(row["balance"]) == services.get_balance(membership)

    def test_type_libre_hors_solde(self, ctx, scenario):
        """Le versement libre de 3 $ d'Alain n'entre pas dans son solde."""

        rows = {row["membership_id"]: row for row in all_rows(client_for(ctx.treasurer.user))}
        assert rows[scenario["alain"].pk]["balance"] == "0.00"
        assert rows[scenario["alain"].pk]["financial_status"] == "in_good_standing"

    def test_montant_du_non_echu_ne_cree_pas_de_dette(self, ctx, scenario):
        """Échéance + tolérance pas encore passées : pas de dette (CDC 4.4.2)."""

        today = club_today(ctx)
        Due(
            club=ctx.club, membership=scenario["denis"], contribution_type=scenario["ctype"],
            period=today.replace(day=1), amount=Decimal("50.00"), due_date=today + datetime.timedelta(days=5),
            source=Due.Source.SCHEDULER, created_at=timezone.now(),
        ).save()
        rows = {row["membership_id"]: row for row in all_rows(client_for(ctx.treasurer.user))}
        assert rows[scenario["denis"].pk]["balance"] == "30.00"
        assert rows[scenario["denis"].pk]["financial_status"] == "in_good_standing"

    def test_annulation_recalcule_le_statut_immediatement(self, ctx, scenario):
        reversal = services.request_payment_reversal(
            payment=scenario["pay_alain"], reason="Saisie en double", requested_by=ctx.treasurer.user
        )
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user)
        rows = {row["membership_id"]: row for row in all_rows(client_for(ctx.treasurer.user))}
        assert rows[scenario["alain"].pk]["balance"] == "-10.00"
        assert rows[scenario["alain"].pk]["financial_status"] == "in_debt"
        # Le dernier paiement validé restant est le versement libre.
        assert rows[scenario["alain"].pk]["last_payment_on"] == (scenario["paid_on"] + datetime.timedelta(days=1)).isoformat()

    def test_filtre_statut_en_dette_et_en_ordre(self, ctx, scenario):
        client = client_for(ctx.treasurer.user)
        in_debt = all_rows(client, status="in_debt")
        assert ids_of(in_debt) == [scenario["cedric"].pk, scenario["bruno"].pk]
        good = ids_of(all_rows(client, status="in_good_standing"))
        assert scenario["bruno"].pk not in good
        assert scenario["cedric"].pk not in good
        assert scenario["paul"].pk not in good
        assert {scenario["alain"].pk, scenario["denis"].pk, ctx.president.pk} <= set(good)
        # Décision du client du 17/11/2026 (10.3 n° 100) : une adhésion non
        # validée est « En attente », classement exclusif -- ni « En ordre »,
        # ni « En dette » (CDC 4.3).
        assert ctx.pending_member.pk not in good
        assert ctx.pending_member.pk not in ids_of(in_debt)

    def test_filtre_statut_en_attente_et_parti(self, ctx, scenario):
        client = client_for(ctx.treasurer.user)
        assert ids_of(all_rows(client, status="pending")) == [ctx.pending_member.pk]
        pending = all_rows(client, status="pending")[0]
        assert {"key": "pending", "label": "En attente"} in pending["statuses"]
        left = all_rows(client, status="left")
        assert ids_of(left) == [scenario["paul"].pk]
        assert left[0]["balance"] == "-10.00"
        assert left[0]["statuses"] == [{"key": "in_debt", "label": "En dette"}, {"key": "left", "label": "Parti"}]
        # Choix multiple : union des statuts choisis.
        union = ids_of(all_rows(client, status="in_debt,left"))
        assert set(union) == {scenario["cedric"].pk, scenario["bruno"].pk, scenario["paul"].pk}

    def test_filtre_suspendu(self, ctx, scenario):
        suspend(ctx, scenario["alain"], matches_total=3, matches_served=1)
        suspend(ctx, scenario["bruno"], matches_total=1, matches_served=1)  # purgée
        suspend(ctx, scenario["cedric"], lifted=True)  # levée
        client = client_for(ctx.treasurer.user)
        rows = all_rows(client, status="suspended")
        assert ids_of(rows) == [scenario["alain"].pk]
        alain = rows[0]
        assert alain["is_suspended"] is True
        assert alain["suspension_matches_remaining"] == 2
        # Ordre des badges : financier puis discipline (design-system §2.5).
        assert alain["statuses"] == [{"key": "in_good_standing", "label": "En ordre"}, {"key": "suspended", "label": "Suspendu"}]
        others = {row["membership_id"]: row for row in all_rows(client)}
        assert others[scenario["bruno"].pk]["is_suspended"] is False
        assert others[scenario["cedric"].pk]["is_suspended"] is False

    def test_statut_inconnu_400(self, ctx, scenario):
        response = client_for(ctx.treasurer.user).get(LIST_URL, {"status": "injured"})
        assert response.status_code == 400
        assert "Statut inconnu" in response.json()["detail"]

    def test_recherche_nom_sans_accent_ni_casse_et_numero(self, ctx, scenario):
        client = client_for(ctx.treasurer.user)
        # Termes combinés (prénom + nom) : les noms Faker des autres membres
        # ne peuvent pas correspondre par hasard.
        assert ids_of(all_rows(client, q="BRU bb")) == [scenario["bruno"].pk]
        assert ids_of(all_rows(client, q="CEDRIC CC")) == [scenario["cedric"].pk]
        assert ids_of(all_rows(client, q="cédric cc")) == [scenario["cedric"].pk]
        assert ids_of(all_rows(client, q="7")) == [scenario["alain"].pk]
        assert all_rows(client, q="zzqx") == []
        assert client.get(LIST_URL, {"q": "x" * 61}).status_code == 400

    def test_filtre_type_de_cotisation(self, ctx, scenario):
        client = client_for(ctx.treasurer.user)
        attached = monthly_type(ctx, name="Mensuelle 20", amount="20", scope=ContributionType.Scope.ATTACHED)
        services.create_contribution_assignment(
            membership=scenario["bruno"], contribution_type=attached,
            starts_on=months_ago(ctx, 3), created_by=ctx.president.user,
        )
        assert ids_of(all_rows(client, contribution_type=str(attached.pk))) == [scenario["bruno"].pk]
        # Type « Tous » : tous les Inscrits (les « En attente » n'ont pas de montant dû).
        everyone = ids_of(all_rows(client, contribution_type=str(scenario["ctype"].pk)))
        assert scenario["bruno"].pk in everyone
        assert ctx.pending_member.pk not in everyone
        # Choix multiple : union.
        both = ids_of(all_rows(client, contribution_type=f"{attached.pk},{scenario['ctype'].pk}"))
        assert set(both) == set(everyone)

    def test_filtre_type_inconnu_ou_d_un_autre_club_400(self, ctx, other_ctx, scenario):
        client = client_for(ctx.treasurer.user)
        foreign = monthly_type(other_ctx)
        assert client.get(LIST_URL, {"contribution_type": str(foreign.pk)}).status_code == 400
        assert client.get(LIST_URL, {"contribution_type": "abc"}).status_code == 400
        assert client.get(LIST_URL, {"contribution_type": "999999"}).status_code == 400

    def test_tris(self, ctx, scenario):
        client = client_for(ctx.treasurer.user)
        desc = all_rows(client, ordering="-balance")
        assert desc[0]["membership_id"] == scenario["denis"].pk
        assert ids_of(desc[-2:]) == [scenario["bruno"].pk, scenario["cedric"].pk]

        by_name = all_rows(client, ordering="name")
        keys = [(services._fold(row["last_name"]), services._fold(row["first_name"])) for row in by_name]
        assert keys == sorted(keys)
        assert ids_of(all_rows(client, ordering="-name")) == list(reversed(ids_of(by_name)))

        recent = all_rows(client, ordering="-last_payment")
        assert recent[0]["membership_id"] == scenario["denis"].pk
        assert recent[-1]["last_payment_on"] is None
        oldest = all_rows(client, ordering="last_payment")
        assert oldest[0]["last_payment_on"] is None
        assert oldest[-1]["membership_id"] == scenario["denis"].pk

        assert client.get(LIST_URL, {"ordering": "salary"}).status_code == 400

    def test_pagination_limit_offset(self, ctx, scenario):
        client = client_for(ctx.treasurer.user)
        first = client.get(LIST_URL, {"limit": 4}).json()
        assert first["count"] == 10
        assert len(first["results"]) == 4
        assert first["next_offset"] == 4
        rest = client.get(LIST_URL, {"limit": 4, "offset": 8}).json()
        assert len(rest["results"]) == 2
        assert rest["next_offset"] is None
        seen = []
        for offset in (0, 4, 8):
            seen += ids_of(client.get(LIST_URL, {"limit": 4, "offset": offset}).json()["results"])
        assert len(seen) == len(set(seen)) == 10
        assert client.get(LIST_URL, {"limit": "x"}).status_code == 400
        assert client.get(LIST_URL, {"limit": 1000}).json()["limit"] == 100

    def test_photo_en_url_absolue(self, ctx, scenario):
        user = scenario["bruno"].user
        user.photo.name = "users/photos/bruno.jpg"
        user.save(update_fields=["photo"])
        rows = {row["membership_id"]: row for row in all_rows(client_for(ctx.treasurer.user))}
        assert rows[scenario["bruno"].pk]["photo"] == "http://testserver/media/users/photos/bruno.jpg"

    def test_aucune_donnee_medicale_ni_coordonnee(self, ctx, scenario):
        rows = all_rows(client_for(ctx.treasurer.user))
        for row in rows:
            assert not (set(row) & FORBIDDEN_KEYS)

    def test_club_sans_parametres_400_en_francais(self, ctx):
        ctx.club.settings.delete()
        response = client_for(ctx.treasurer.user).get(LIST_URL)
        assert response.status_code == 400
        assert "paramètres du club" in response.json()["detail"]

    @pytest.mark.parametrize("role", READERS)
    def test_lecteurs_autorises(self, ctx, scenario, role):
        assert client_for(getattr(ctx, role).user).get(LIST_URL).status_code == 200

    @pytest.mark.parametrize("role", FORBIDDEN_ROLES)
    def test_autres_roles_refuses(self, ctx, role):
        member = member_with_role(ctx, role)
        assert client_for(member.user).get(LIST_URL).status_code == 403

    def test_joueur_et_anonyme_refuses(self, ctx):
        assert client_for(ctx.player.user).get(LIST_URL).status_code == 403
        assert APIClient().get(LIST_URL).status_code == 401

    def test_etancheite_entre_clubs(self, ctx, other_ctx, scenario):
        mine = set(ids_of(all_rows(client_for(ctx.treasurer.user))))
        theirs_rows = all_rows(client_for(other_ctx.treasurer.user))
        theirs = set(ids_of(theirs_rows))
        assert theirs == {
            m.pk for m in (other_ctx.president, other_ctx.vice_president, other_ctx.treasurer,
                           other_ctx.assistant_treasurer, other_ctx.player, other_ctx.pending_member)
        }
        assert not (mine & theirs)
        assert all(row["currency"] == "CDF" for row in theirs_rows)

    def test_service_refuse_un_role_non_autorise(self, ctx, scenario):
        with pytest.raises(services.TreasuryPermissionError):
            services.list_member_finances(club=ctx.club, requested_by=ctx.player.user)

    def test_nombre_de_requetes_constant(self, ctx, scenario):
        """Agrégations SQL : aucune requête par joueur (CDC performance, 500 joueurs)."""

        client = client_for(ctx.treasurer.user)
        client.get(LIST_URL)  # échauffement (caches de contenu, licence…)
        with CaptureQueriesContext(connection) as small:
            assert client.get(LIST_URL, {"limit": 100}).status_code == 200
        for index in range(25):
            member = named_member(ctx, first_name=f"Extra{index}", last_name="Xx")
            put_in_debt(ctx, member, scenario["ctype"], amount="10", months_ago=1)
            pay(ctx, member, scenario["ctype"], amount="3", paid_on=scenario["paid_on"])
        suspend(ctx, member)
        with CaptureQueriesContext(connection) as large:
            response = client.get(LIST_URL, {"limit": 100})
        assert response.status_code == 200
        assert response.json()["count"] == 35
        assert len(large.captured_queries) <= len(small.captured_queries)


# ---------------------------------------------------------------------------
# Modale « Situation financière »
# ---------------------------------------------------------------------------


class TestMemberDetail:
    def test_contenu_de_la_situation(self, ctx, scenario):
        response = client_for(ctx.treasurer.user).get(detail_url(scenario["bruno"]))
        assert response.status_code == 200
        data = response.json()
        assert set(data) == ROW_KEYS | DETAIL_EXTRA_KEYS
        assert data["balance"] == "-6.00"
        assert data["amount_due"] == "6.00"
        assert data["financial_status"] == "in_debt"
        assert data["today"] == club_today(ctx).isoformat()
        month = scenario["month"]
        assert data["unpaid_months"] == [
            {
                "contribution_type": {"id": scenario["ctype"].pk, "name": "Mensuelle 10"},
                "period": month.isoformat(),
                "period_label": services.french_month_label(month),
                "due_date": month.replace(day=10).isoformat(),
                "amount_due": "10.00",
                "allocated": "4.00",
                "remaining": "6.00",
            }
        ]
        assert data["next_due"] is None
        assert data["free_contributions"] == []
        assert data["can_record_payment"] is True

    def test_cotisations_libres_suivies_hors_solde(self, ctx, scenario):
        data = client_for(ctx.treasurer.user).get(detail_url(scenario["alain"])).json()
        assert data["balance"] == "0.00"
        assert data["unpaid_months"] == []
        assert data["free_contributions"] == [
            {
                "contribution_type": {"id": scenario["free"].pk, "name": "Vestiaire"},
                "total": "3.00",
                "payments_count": 1,
                "last_paid_on": (scenario["paid_on"] + datetime.timedelta(days=1)).isoformat(),
            }
        ]

    def test_prochaine_echeance_non_echue(self, ctx, scenario):
        today = club_today(ctx)
        due_date = today + datetime.timedelta(days=5)
        Due(
            club=ctx.club, membership=scenario["cedric"], contribution_type=scenario["ctype"],
            period=today.replace(day=1), amount=Decimal("10.00"), due_date=due_date,
            source=Due.Source.SCHEDULER, created_at=timezone.now(),
        ).save()
        data = client_for(ctx.treasurer.user).get(detail_url(scenario["cedric"])).json()
        # La dette reste celle du mois M ; le montant à venir n'est pas une dette.
        assert data["balance"] == "-10.00"
        assert len(data["unpaid_months"]) == 1
        assert data["next_due"] == {
            "contribution_type": {"id": scenario["ctype"].pk, "name": "Mensuelle 10"},
            "period": today.replace(day=1).isoformat(),
            "period_label": services.french_month_label(today.replace(day=1)),
            "due_date": due_date.isoformat(),
            "amount": "10.00",
        }

    def test_paiement_anticipe_couvre_la_prochaine_echeance(self, ctx, scenario):
        today = club_today(ctx)
        Due(
            club=ctx.club, membership=scenario["denis"], contribution_type=scenario["ctype"],
            period=today.replace(day=1), amount=Decimal("10.00"), due_date=today + datetime.timedelta(days=5),
            source=Due.Source.SCHEDULER, created_at=timezone.now(),
        ).save()
        services.refresh_member_allocations(scenario["denis"], actor=ctx.treasurer.user)
        data = client_for(ctx.treasurer.user).get(detail_url(scenario["denis"])).json()
        assert data["next_due"] is None
        assert data["balance"] == "30.00"

    @pytest.mark.parametrize("role", ["president", "vice_president"])
    def test_lecture_seule_pour_president_et_vp(self, ctx, scenario, role):
        data = client_for(getattr(ctx, role).user).get(detail_url(scenario["bruno"])).json()
        assert data["can_record_payment"] is False

    def test_joueur_parti_consultable_sans_encaissement(self, ctx, scenario):
        data = client_for(ctx.treasurer.user).get(detail_url(scenario["paul"])).json()
        assert data["balance"] == "-10.00"
        assert data["membership_status"] == "departed"
        assert data["can_record_payment"] is False

    def test_aucune_donnee_medicale(self, ctx, scenario):
        data = client_for(ctx.treasurer.user).get(detail_url(scenario["bruno"])).json()
        assert not (set(data) & FORBIDDEN_KEYS)

    def test_inconnu_et_autre_club_404(self, ctx, other_ctx, scenario):
        client = client_for(other_ctx.treasurer.user)
        response = client.get(detail_url(scenario["bruno"]))
        assert response.status_code == 404
        assert response.json()["detail"] == "Ce joueur n'existe pas dans ce club."
        assert client_for(ctx.treasurer.user).get(reverse("treasury:member-detail", args=[999999])).status_code == 404

    @pytest.mark.parametrize("role", FORBIDDEN_ROLES)
    def test_autres_roles_refuses(self, ctx, scenario, role):
        member = member_with_role(ctx, role)
        assert client_for(member.user).get(detail_url(scenario["bruno"])).status_code == 403

    def test_joueur_refuse_meme_pour_lui_meme(self, ctx, scenario):
        """Le joueur consulte sa situation dans « Mon profil », pas ici."""

        assert client_for(scenario["bruno"].user).get(detail_url(scenario["bruno"])).status_code == 403


# ---------------------------------------------------------------------------
# Onglet « Grille {année} » de la modale
# ---------------------------------------------------------------------------


class TestMemberGrid:
    def test_ligne_du_joueur_identique_a_la_grille_du_bureau(self, ctx, scenario):
        year = scenario["month"].year
        response = client_for(ctx.vice_president.user).get(grid_url(scenario["bruno"], year))
        assert response.status_code == 200
        data = response.json()
        assert data["year"] == year
        assert data["player"]["membership_id"] == scenario["bruno"].pk
        assert data["player_status"]["balance"] == "-6.00"
        lines = {line["contribution_type"]["id"]: line for line in data["lines"]}
        line = lines[scenario["ctype"].pk]
        cell = line["cells"][scenario["month"].month - 1]
        assert cell["state"] == services.GRID_STATE_PARTIAL
        assert cell["allocated"] == "4.00"
        grid = services.build_contribution_grid(
            contribution_type=scenario["ctype"], year=year, requested_by=ctx.treasurer.user
        )
        row = next(r for r in grid.rows if r.membership.pk == scenario["bruno"].pk)
        assert [c["allocated"] for c in line["cells"]] == [f"{c.allocated:.2f}" for c in row.cells]

    def test_annee_invalide_400(self, ctx, scenario):
        assert client_for(ctx.treasurer.user).get(grid_url(scenario["bruno"], 1990)).status_code == 400

    def test_autre_club_404_et_roles(self, ctx, other_ctx, scenario):
        year = scenario["month"].year
        assert client_for(other_ctx.treasurer.user).get(grid_url(scenario["bruno"], year)).status_code == 404
        assert client_for(ctx.player.user).get(grid_url(scenario["bruno"], year)).status_code == 403
        coach = member_with_role(ctx, MembershipRole.Role.COACH)
        assert client_for(coach.user).get(grid_url(scenario["bruno"], year)).status_code == 403


# ---------------------------------------------------------------------------
# Onglets « Paiements » et « Cotisations libres » : filtres de la liste des
# paiements existante (réutilisée, pas de doublon)
# ---------------------------------------------------------------------------


class TestPaymentListMemberFilter:
    def test_paiements_d_un_membre(self, ctx, scenario):
        client = client_for(ctx.treasurer.user)
        data = client.get(PAYMENTS_URL, {"membership_id": scenario["alain"].pk}).json()
        assert data["count"] == 2
        assert {item["id"] for item in data["results"]} == {scenario["pay_alain"].pk, scenario["pay_free"].pk}

    def test_filtre_nature(self, ctx, scenario):
        client = client_for(ctx.treasurer.user)
        free = client.get(PAYMENTS_URL, {"membership_id": scenario["alain"].pk, "nature": "free"}).json()
        assert [item["id"] for item in free["results"]] == [scenario["pay_free"].pk]
        mandatory = client.get(PAYMENTS_URL, {"membership_id": scenario["alain"].pk, "nature": "mandatory"}).json()
        assert [item["id"] for item in mandatory["results"]] == [scenario["pay_alain"].pk]
        assert client.get(PAYMENTS_URL, {"nature": "autre"}).status_code == 400

    def test_identifiant_invalide_400(self, ctx, scenario):
        assert client_for(ctx.treasurer.user).get(PAYMENTS_URL, {"membership_id": "abc"}).status_code == 400

    def test_membre_d_un_autre_club_liste_vide(self, ctx, other_ctx, scenario):
        data = client_for(other_ctx.treasurer.user).get(PAYMENTS_URL, {"membership_id": scenario["alain"].pk}).json()
        assert data["count"] == 0
        assert data["results"] == []
