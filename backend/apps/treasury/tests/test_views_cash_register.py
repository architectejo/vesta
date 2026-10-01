"""API de la Caisse Terrain Express (tâche 2.4 ; CDC 4.4.5, 6.6, 7.2 ;
10.2 n° 22 ; matrice 2.4, ligne « Enregistrement des paiements »).

Permissions explicites (Trésorier et adjoint), 401 sans jeton, 403 pour les
autres rôles, 404 pour une session d'un autre utilisateur ou d'un autre
club (aucune fuite d'existence), PIN à l'ouverture seulement, jamais
renvoyé ; synchronisation rejouée idempotente ; N+1 de la recherche.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.treasury import services
from apps.treasury.models import CashSession, Payment
from apps.treasury.tests.cash_helpers import club_today, local_dt, monthly_type, named_member, open_session, put_in_debt
from apps.treasury.tests.conftest import PIN, WRONG_PIN

pytestmark = pytest.mark.django_db

OTHER_ROLES = ["president", "vice_president", "player"]


def client_for(member) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member.user).access_token}")
    return client


def url(name, *args):
    return reverse(f"treasury:{name}", args=args)


def pay_body(membership, **extra):
    data = {
        "client_uuid": str(uuid.uuid4()),
        "client_recorded_at": timezone.now().isoformat(),
        "membership_id": membership.pk,
        "amount": "10",
    }
    data.update(extra)
    return data


def all_endpoints(session_id):
    return [
        ("post", url("cash-session-open"), {"pin": PIN}),
        ("get", url("cash-session-current"), None),
        ("post", url("cash-session-close", session_id), {}),
        ("get", url("cash-session-players", session_id) + "?q=a", None),
        ("post", url("cash-session-payments", session_id), {}),
        ("post", url("cash-session-payment-preview", session_id), {}),
    ]


class TestPermissions:
    def test_401_sans_authentification(self, ctx):
        for method, path, data in all_endpoints(uuid.uuid4()):
            response = getattr(APIClient(), method)(path, data, format="json") if data is not None else APIClient().get(path)
            assert response.status_code == 401, path

    @pytest.mark.parametrize("role", OTHER_ROLES)
    def test_403_hors_tresorier_et_adjoint(self, ctx, role):
        session = open_session(ctx)
        client = client_for(getattr(ctx, role))
        for method, path, data in all_endpoints(session.public_id):
            response = client.post(path, data, format="json") if method == "post" else client.get(path)
            assert response.status_code == 403, path
        assert CashSession.all_objects.count() == 1


class TestOpenAndCurrent:
    def test_ouverture_201_puis_200_sans_pin_dans_la_reponse(self, ctx):
        client = client_for(ctx.treasurer)
        response = client.post(url("cash-session-open"), {"pin": PIN}, format="json")
        assert response.status_code == 201, response.data
        session = response.data["session"]
        assert session["status"] == "open" and session["is_open"] is True
        assert session["club_timezone"] == "Africa/Kinshasa"
        assert (session["payments_count"], session["payments_total"], session["currency"]) == (0, "0.00", "USD")
        assert set(session) == {
            "id", "status", "is_open", "opened_at", "expires_at", "closed_at", "club_timezone",
            "payments_count", "payments_total", "currency",
        }
        assert PIN not in str(response.content)

        again = client.post(url("cash-session-open"), {"pin": PIN}, format="json")
        assert again.status_code == 200
        assert again.data["session"]["id"] == session["id"]

        current = client.get(url("cash-session-current"))
        assert current.status_code == 200
        assert current.data["session"]["id"] == session["id"]

    def test_session_courante_absente(self, ctx):
        response = client_for(ctx.assistant_treasurer).get(url("cash-session-current"))
        assert response.status_code == 200
        assert response.data == {"session": None}

    def test_session_courante_propre_a_l_utilisateur(self, ctx):
        open_session(ctx, ctx.treasurer)
        assert client_for(ctx.assistant_treasurer).get(url("cash-session-current")).data == {"session": None}

    def test_pin_faux_400_puis_verrouille_423(self, ctx):
        client = client_for(ctx.treasurer)
        response = client.post(url("cash-session-open"), {"pin": WRONG_PIN}, format="json")
        assert response.status_code == 400
        assert response.data["attempts_remaining"] == 2
        client.post(url("cash-session-open"), {"pin": WRONG_PIN}, format="json")
        locked = client.post(url("cash-session-open"), {"pin": WRONG_PIN}, format="json")
        assert locked.status_code == 423
        assert client.post(url("cash-session-open"), {"pin": PIN}, format="json").status_code == 423
        assert CashSession.all_objects.count() == 0

    def test_pin_absent_400(self, ctx):
        response = client_for(ctx.treasurer).post(url("cash-session-open"), {}, format="json")
        assert response.status_code == 400
        assert CashSession.all_objects.count() == 0

    def test_ecritures_gelees_409(self, ctx):
        services.freeze_ledger(club=ctx.club, reason="Rupture simulée", actor=None)
        response = client_for(ctx.treasurer).post(url("cash-session-open"), {"pin": PIN}, format="json")
        assert response.status_code == 409
        assert response.data["code"] == "ledger_frozen"


class TestPayments:
    def test_encaissement_201_puis_rejeu_200(self, ctx):
        ctype = monthly_type(ctx)
        put_in_debt(ctx, ctx.player, ctype)
        session = open_session(ctx)
        client = client_for(ctx.treasurer)
        body = pay_body(ctx.player)

        created = client.post(url("cash-session-payments", session.public_id), body, format="json")
        assert created.status_code == 201, created.data
        assert created.data["source"] == "field_cash"
        assert created.data["cash_session_id"] == str(session.public_id)
        assert created.data["contribution_type"]["id"] == ctype.pk
        assert created.data["receipt_number"] == 1
        assert created.data["player_status"]["is_in_good_standing"] is True

        replay = client.post(url("cash-session-payments", session.public_id), body, format="json")
        assert replay.status_code == 200
        assert replay.data["id"] == created.data["id"]
        assert Payment.all_objects.count() == 1

        summary = client.get(url("cash-session-current")).data["session"]
        assert (summary["payments_count"], summary["payments_total"]) == (1, "10.00")

    def test_cle_reutilisee_409(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        client = client_for(ctx.treasurer)
        body = pay_body(ctx.player)
        client.post(url("cash-session-payments", session.public_id), body, format="json")
        conflict = client.post(
            url("cash-session-payments", session.public_id), {**body, "amount": "20"}, format="json"
        )
        assert conflict.status_code == 409
        assert conflict.data["code"] == "client_uuid_conflict"

    def test_synchronisation_apres_minuit_d_une_saisie_d_avant_minuit(self, ctx):
        monthly_type(ctx)
        day = club_today(ctx) - datetime.timedelta(days=2)
        session = open_session(ctx, now=local_dt(ctx, day, 9))
        client = client_for(ctx.treasurer)

        before_midnight = client.post(
            url("cash-session-payments", session.public_id),
            pay_body(ctx.player, client_recorded_at=local_dt(ctx, day, 23, 30).isoformat()),
            format="json",
        )
        assert before_midnight.status_code == 201, before_midnight.data
        assert before_midnight.data["paid_on"] == day

        after_midnight = client.post(
            url("cash-session-payments", session.public_id),
            pay_body(ctx.player, client_recorded_at=local_dt(ctx, day + datetime.timedelta(days=1), 0, 1).isoformat()),
            format="json",
        )
        assert after_midnight.status_code == 400
        assert after_midnight.data["code"] == "cash_session_not_valid"
        assert Payment.all_objects.count() == 1

    def test_session_d_un_autre_utilisateur_404(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx, ctx.assistant_treasurer)
        client = client_for(ctx.treasurer)
        response = client.post(url("cash-session-payments", session.public_id), pay_body(ctx.player), format="json")
        assert response.status_code == 404
        assert response.data["code"] == "cash_session_not_found"
        assert client.post(url("cash-session-close", session.public_id), {}, format="json").status_code == 404
        assert client.get(url("cash-session-players", session.public_id) + "?q=a").status_code == 404
        assert Payment.all_objects.count() == 0

    @pytest.mark.parametrize("amount", ["0", "-3", "abc", ""])
    def test_montant_invalide_400(self, ctx, amount):
        monthly_type(ctx)
        session = open_session(ctx)
        response = client_for(ctx.treasurer).post(
            url("cash-session-payments", session.public_id), pay_body(ctx.player, amount=amount), format="json"
        )
        assert response.status_code == 400
        assert Payment.all_objects.count() == 0

    def test_champs_obligatoires(self, ctx):
        session = open_session(ctx)
        response = client_for(ctx.treasurer).post(
            url("cash-session-payments", session.public_id), {"membership_id": ctx.player.pk}, format="json"
        )
        assert response.status_code == 400
        assert {"client_uuid", "client_recorded_at", "amount"} <= set(response.data)

    def test_aucun_pin_demande_ni_accepte(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        response = client_for(ctx.treasurer).post(
            url("cash-session-payments", session.public_id), pay_body(ctx.player, pin=WRONG_PIN), format="json"
        )
        assert response.status_code == 201
        ctx.treasurer.user.refresh_from_db()
        assert ctx.treasurer.user.pin_failed_attempts == 0

    def test_apercu_avec_mensuelle_par_defaut(self, ctx):
        ctype = monthly_type(ctx)
        put_in_debt(ctx, ctx.player, ctype)
        session = open_session(ctx)
        response = client_for(ctx.treasurer).post(
            url("cash-session-payment-preview", session.public_id),
            {"membership_id": ctx.player.pk, "amount": "10"},
            format="json",
        )
        assert response.status_code == 200, response.data
        assert response.data["contribution_type"]["id"] == ctype.pk
        assert response.data["current"]["is_in_good_standing"] is False
        assert response.data["after"]["is_in_good_standing"] is True
        assert Payment.all_objects.count() == 0

    def test_fermeture_puis_encaissement_refuse(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx, now=timezone.now() - datetime.timedelta(minutes=1))
        client = client_for(ctx.treasurer)
        closed = client.post(url("cash-session-close", session.public_id), {}, format="json")
        assert closed.status_code == 200
        assert closed.data["session"]["status"] == "closed"
        response = client.post(url("cash-session-payments", session.public_id), pay_body(ctx.player), format="json")
        assert response.status_code == 400
        assert response.data["code"] == "cash_session_not_valid"
        assert client.get(url("cash-session-current")).data == {"session": None}


class TestSearchApi:
    def test_champs_limites_sans_email_ni_telephone(self, ctx):
        monthly_type(ctx)
        target = named_member(ctx, first_name="Photo", last_name="Mbuyamba", jersey_number=9)
        target.user.phone = "+243000000000"
        target.user.photo.name = "users/photos/mbuyamba.jpg"
        target.user.save(update_fields=["phone", "photo"])
        session = open_session(ctx)
        response = client_for(ctx.treasurer).get(url("cash-session-players", session.public_id) + "?q=Mbuyamba")
        assert response.status_code == 200
        assert response["Cache-Control"] == "no-store"
        [row] = response.data["results"]
        assert set(row) == {
            "membership_id", "first_name", "last_name", "jersey_number", "photo", "membership_status",
            "membership_status_label", "default_contribution_type_id", "balance", "amount_due",
            "is_in_good_standing", "reason", "currency",
        }
        # URL absolue : interface et API sont servies sur des hôtes distincts.
        assert row["photo"] == "http://testserver/media/users/photos/mbuyamba.jpg"
        assert "+243" not in str(response.content) and "@" not in str(response.content)

    def test_joueur_regularise_en_ordre_a_la_requete_suivante(self, ctx):
        ctype = monthly_type(ctx)
        target = named_member(ctx, first_name="Dimanche", last_name="Lukusa", jersey_number=11)
        put_in_debt(ctx, target, ctype)
        session = open_session(ctx)
        client = client_for(ctx.treasurer)
        search_url = url("cash-session-players", session.public_id) + "?q=11"

        before = [r for r in client.get(search_url).data["results"] if r["membership_id"] == target.pk][0]
        assert before["is_in_good_standing"] is False and before["amount_due"] == "10.00"

        client.post(url("cash-session-payments", session.public_id), pay_body(target, amount="10"), format="json")

        after = [r for r in client.get(search_url).data["results"] if r["membership_id"] == target.pk][0]
        assert after["is_in_good_standing"] is True and after["balance"] == "0.00"

    def test_recherche_vide_400(self, ctx):
        session = open_session(ctx)
        response = client_for(ctx.treasurer).get(url("cash-session-players", session.public_id))
        assert response.status_code == 400

    def test_nombre_de_requetes_constant_sur_20_joueurs(self, ctx):
        ctype = monthly_type(ctx)
        session = open_session(ctx)
        client = client_for(ctx.treasurer)
        search_url = url("cash-session-players", session.public_id) + "?q=Requetes"
        member = named_member(ctx, first_name="Un", last_name="Requetes")
        put_in_debt(ctx, member, ctype)
        client.get(search_url)  # chauffe (cache de contenu des types, etc.)
        # Compte lu aussitot : Django vide le journal des requetes SQL au debut
        # de chaque requete HTTP (signal ``request_started``).
        with CaptureQueriesContext(connection) as one:
            assert len(client.get(search_url).data["results"]) == 1
        one_count = len(one.captured_queries)
        for index in range(19):
            put_in_debt(ctx, named_member(ctx, first_name=f"N{index}", last_name="Requetes"), ctype)
        with CaptureQueriesContext(connection) as twenty:
            assert len(client.get(search_url).data["results"]) == 20
        twenty_count = len(twenty.captured_queries)
        assert twenty_count == one_count
        assert twenty_count <= 20  # mesure documentee dans le compte rendu de la tache 2.4


class TestIsolation:
    """CDC 6.3 : un utilisateur du club A n'obtient aucune donnée du club B."""

    def test_session_du_club_b_invisible_depuis_le_club_a(self, ctx, other_ctx):
        monthly_type(other_ctx)
        other_session = open_session(other_ctx)
        client = client_for(ctx.treasurer)
        assert client.get(url("cash-session-players", other_session.public_id) + "?q=a").status_code == 404
        assert client.post(url("cash-session-close", other_session.public_id), {}, format="json").status_code == 404
        response = client.post(
            url("cash-session-payments", other_session.public_id), pay_body(ctx.player), format="json"
        )
        assert response.status_code == 404
        preview = client.post(
            url("cash-session-payment-preview", other_session.public_id),
            {"membership_id": ctx.player.pk, "amount": "10"},
            format="json",
        )
        assert preview.status_code == 404
        assert client.get(url("cash-session-current")).data == {"session": None}
        other_session.refresh_from_db()
        assert other_session.closed_at is None

    def test_joueur_du_club_b_introuvable_404(self, ctx, other_ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        response = client_for(ctx.treasurer).post(
            url("cash-session-payments", session.public_id), pay_body(other_ctx.player), format="json"
        )
        assert response.status_code == 404
        assert Payment.all_objects.count() == 0

    def test_recherche_ne_renvoie_pas_les_joueurs_du_club_b(self, ctx, other_ctx):
        named_member(other_ctx, first_name="Etranger", last_name="Ailleursclub")
        session = open_session(ctx)
        response = client_for(ctx.treasurer).get(url("cash-session-players", session.public_id) + "?q=Ailleursclub")
        assert response.status_code == 200
        assert response.data["results"] == []

    def test_meme_cle_client_dans_deux_clubs_independante(self, ctx, other_ctx):
        monthly_type(ctx)
        monthly_type(other_ctx)
        key = str(uuid.uuid4())
        session_a = open_session(ctx)
        session_b = open_session(other_ctx)
        a = client_for(ctx.treasurer).post(
            url("cash-session-payments", session_a.public_id), pay_body(ctx.player, client_uuid=key), format="json"
        )
        b = client_for(other_ctx.treasurer).post(
            url("cash-session-payments", session_b.public_id), pay_body(other_ctx.player, client_uuid=key), format="json"
        )
        assert (a.status_code, b.status_code) == (201, 201)
        assert a.data["id"] != b.data["id"]
