"""Caisse Terrain Express — services (tâche 2.4 ; CDC 4.4.5, 6.6 ;
10.2 n° 22 ; schema-treasury.md §5.4, invariant I15).

Session ouverte en ligne par le Trésorier ou l'adjoint (plus de PIN depuis
la décision client du 11/10/2026, CLAUDE.md règle 7 : l'auteur est
journalisé), valable jusqu'à minuit dans le fuseau du club ;
encaissements sans PIN, y compris saisis hors connexion et synchronisés
après minuit ; refus d'un encaissement saisi après minuit ; idempotence ;
étanchéité ; recherche sans N+1 et statut recalculé à la lecture.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.clubs.models import Membership, MembershipRole
from apps.treasury import services
from apps.treasury.models import CashSession, ContributionType, LedgerImmutableError, Payment, Transaction
from apps.treasury.tests.cash_helpers import (
    cash_pay,
    club_today,
    local_dt,
    monthly_type,
    named_member,
    open_session,
    put_in_debt,
)
from apps.treasury.tests.conftest import PIN, assert_logged_by, make_member

pytestmark = pytest.mark.django_db

UTC = datetime.timezone.utc


def set_timezone(ctx, tz_name):
    settings_obj = ctx.club.settings
    settings_obj.timezone = tz_name
    settings_obj.save()


def days_ago_local(ctx, days):
    return club_today(ctx) - datetime.timedelta(days=days)


# ---------------------------------------------------------------------------
# Ouverture
# ---------------------------------------------------------------------------


class TestOpening:
    @pytest.mark.parametrize("role", ["treasurer", "assistant_treasurer"])
    def test_tresorier_ou_adjoint_ouvre_une_session(self, ctx, role):
        member = getattr(ctx, role)
        now = timezone.now()
        session, created = services.open_cash_session(club=ctx.club, user=member.user, now=now)
        assert created is True
        assert session.opened_by_id == member.pk
        assert session.opened_at == now
        assert session.status == CashSession.Status.OPEN
        assert isinstance(session.public_id, uuid.UUID)
        assert services.get_current_cash_session(club=ctx.club, user=member.user, now=now) == session

    @pytest.mark.parametrize("role", ["president", "vice_president", "player"])
    def test_autres_roles_refuses(self, ctx, role):
        # CDC 4.4.5 et matrice 2.4 : « par le Trésorier ou l'adjoint » ; le
        # Président n'est qu'en lecture sur l'enregistrement des paiements.
        member = getattr(ctx, role)
        with pytest.raises(services.TreasuryPermissionError):
            services.open_cash_session(club=ctx.club, user=member.user)
        assert CashSession.all_objects.count() == 0

    def test_ouverture_sans_pin_auteur_journalise(self, ctx):
        """Décision client du 11/10/2026 : aucun PIN, l'auteur est journalisé."""

        session, created = services.open_cash_session(club=ctx.club, user=ctx.assistant_treasurer.user)
        assert created is True
        assert session.opened_by_id == ctx.assistant_treasurer.pk
        assert_logged_by("treasury.cash_session.opened", ctx.assistant_treasurer.user, club=ctx.club)
        ctx.assistant_treasurer.user.refresh_from_db()

    def test_tresorier_sans_pin_defini_ouvre_une_session(self, ctx):
        """Un compte qui n'a jamais défini de PIN n'est plus bloqué."""

        treasurer = make_member(ctx.club)
        MembershipRole.all_objects.filter(membership=ctx.treasurer).update(
            revoked_at=timezone.now(), revoked_by=ctx.president.user, revoked_reason="Remplacement"
        )
        MembershipRole(
            club=ctx.club, membership=treasurer, role=MembershipRole.Role.TREASURER,
            appointed_by=ctx.president.user, appointed_at=timezone.now(),
        ).save()
        session, created = services.open_cash_session(club=ctx.club, user=treasurer.user)
        assert created is True and session.opened_by_id == treasurer.pk

    def test_ecritures_gelees_refus(self, ctx):
        services.freeze_ledger(club=ctx.club, reason="Rupture simulée", actor=None)
        with pytest.raises(services.LedgerFrozenError):
            services.open_cash_session(club=ctx.club, user=ctx.treasurer.user)
        assert CashSession.all_objects.count() == 0

    def test_journal_sans_pin(self, ctx):
        session = open_session(ctx)
        log = AuditLog.objects.get(action_type="treasury.cash_session.opened")
        assert log.actor_id == ctx.treasurer.user_id
        assert log.club_id == ctx.club.id
        assert log.after["cash_session_id"] == str(session.public_id)
        assert "pin" not in {key.lower() for key in log.after}
        assert PIN not in str(log.after) and PIN not in str(log.before)

    def test_aucun_champ_pin_sur_le_modele(self):
        names = {field.name for field in CashSession._meta.get_fields()}
        assert not {name for name in names if "pin" in name}

    def test_reouverture_renvoie_la_session_valide(self, ctx):
        now = timezone.now()
        first = open_session(ctx, now=now)
        second, created = services.open_cash_session(
            club=ctx.club, user=ctx.treasurer.user, now=now + datetime.timedelta(minutes=5)
        )
        assert created is False and second.pk == first.pk
        assert CashSession.all_objects.count() == 1

    def test_nouvelle_session_apres_expiration(self, ctx):
        day = days_ago_local(ctx, 3)
        first = open_session(ctx, now=local_dt(ctx, day, 9))
        second = open_session(ctx, now=local_dt(ctx, day + datetime.timedelta(days=1), 9))
        assert second.pk != first.pk
        assert services.cash_session_state(first) == CashSession.Status.EXPIRED

    def test_une_session_par_tresorier_chacun_la_sienne(self, ctx):
        now = timezone.now()
        a = open_session(ctx, ctx.treasurer, now=now)
        b = open_session(ctx, ctx.assistant_treasurer, now=now)
        assert a.pk != b.pk

    def test_session_immuable_et_jamais_supprimee(self, ctx):
        session = open_session(ctx)
        session.expires_at = session.expires_at + datetime.timedelta(days=1)
        with pytest.raises(LedgerImmutableError):
            session.save()
        with pytest.raises(LedgerImmutableError):
            CashSession.all_objects.get(pk=session.pk).delete()


# ---------------------------------------------------------------------------
# Expiration à minuit (fuseau du club)
# ---------------------------------------------------------------------------


class TestMidnightExpiry:
    @pytest.mark.parametrize(
        ("tz_name", "opened_utc", "expected_utc"),
        [
            # Kinshasa (UTC+1) : dimanche 08:30 -> lundi 00:00 locale = dimanche 23:00 UTC.
            ("Africa/Kinshasa", datetime.datetime(2026, 9, 27, 7, 30, tzinfo=UTC),
             datetime.datetime(2026, 9, 27, 23, 0, tzinfo=UTC)),
            # Ouverture à 23:30 locale : la session ne dure que 30 minutes.
            ("Africa/Kinshasa", datetime.datetime(2026, 9, 27, 22, 30, tzinfo=UTC),
             datetime.datetime(2026, 9, 27, 23, 0, tzinfo=UTC)),
            # Los Angeles (UTC-7 en septembre) : 28/09 03:00 UTC = 27/09 20:00 locale ;
            # le jour local n'est pas le jour UTC.
            ("America/Los_Angeles", datetime.datetime(2026, 9, 28, 3, 0, tzinfo=UTC),
             datetime.datetime(2026, 9, 28, 7, 0, tzinfo=UTC)),
            # Tokyo (UTC+9) : 27/09 01:00 UTC = 27/09 10:00 locale -> 28/09 00:00 JST.
            ("Asia/Tokyo", datetime.datetime(2026, 9, 27, 1, 0, tzinfo=UTC),
             datetime.datetime(2026, 9, 27, 15, 0, tzinfo=UTC)),
        ],
    )
    def test_expire_a_minuit_du_fuseau_du_club(self, ctx, tz_name, opened_utc, expected_utc):
        set_timezone(ctx, tz_name)
        session = open_session(ctx, now=opened_utc)
        assert session.expires_at == expected_utc
        assert session.is_valid_at(expected_utc - datetime.timedelta(seconds=1))
        assert not session.is_valid_at(expected_utc)
        assert services.get_current_cash_session(club=ctx.club, user=ctx.treasurer.user, now=expected_utc) is None

    def test_minuit_selon_le_fuseau_et_non_utc(self, ctx):
        # 23:30 UTC le 27/09 = 00:30 le 28/09 à Kinshasa : nouvelle journée locale.
        opened = datetime.datetime(2026, 9, 27, 23, 30, tzinfo=UTC)
        session = open_session(ctx, now=opened)
        assert session.expires_at == datetime.datetime(2026, 9, 28, 23, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Encaissements
# ---------------------------------------------------------------------------


class TestCashPayment:
    def test_encaissement_sans_pin_meme_chemin_chaine(self, ctx):
        ctype = monthly_type(ctx)
        session = open_session(ctx)
        payment, created = cash_pay(ctx, session, ctx.player, amount="10")

        assert created is True
        assert payment.source == Payment.Source.FIELD_CASH
        assert payment.method == Payment.Method.CASH
        assert payment.cash_session_id == session.pk
        assert payment.contribution_type_id == ctype.pk  # mensuelle par défaut
        assert payment.validated_by_id == ctx.treasurer.user_id
        assert payment.receipt_number == 1
        assert payment.paid_on == club_today(ctx)
        txn = payment.transaction
        assert (txn.status, txn.provider) == (Transaction.Status.SUCCEEDED, Transaction.Provider.MANUAL)
        assert txn.sealed_at is not None
        assert payment.allocations.exists()
        assert services.verify_chain(ctx.club).ok
        ctx.treasurer.user.refresh_from_db()
        # Auteur de l'encaissement journalisé (CLAUDE.md règles 6 et 7).
        assert_logged_by("treasury.payment.validated", ctx.treasurer.user, club=ctx.club)

    def test_journal_avec_identifiant_de_session_sans_pin(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        client_uuid = uuid.uuid4()
        payment, _ = cash_pay(ctx, session, ctx.player, client_uuid=client_uuid)
        log = AuditLog.objects.get(action_type="treasury.payment.validated", object_id=str(payment.pk))
        assert log.after["cash_session_id"] == str(session.public_id)
        assert log.after["client_uuid"] == str(client_uuid)
        assert log.after["source"] == "field_cash"
        for entry in AuditLog.objects.all():
            assert PIN not in str(entry.after) and PIN not in str(entry.before)

    def test_repartition_4_4_3_paiement_anticipe(self, ctx):
        ctype = monthly_type(ctx)
        player = named_member(ctx, first_name="Anticipe", last_name="Quatremois", joined_on=club_today(ctx).replace(day=1))
        session = open_session(ctx)
        payment, _ = cash_pay(ctx, session, player, amount="40")
        periods = list(payment.allocations.order_by("period").values_list("period", "amount"))
        start = club_today(ctx).replace(day=1)
        expected = []
        for _ in range(4):
            expected.append((start, Decimal("10.00")))
            start = (start + datetime.timedelta(days=32)).replace(day=1)
        assert periods == expected
        assert payment.contribution_type_id == ctype.pk

    def test_type_explicite(self, ctx):
        monthly_type(ctx)
        other = monthly_type(ctx, name="Mensuelle 20", amount="20")
        session = open_session(ctx)
        payment, _ = cash_pay(ctx, session, ctx.player, amount="20", contribution_type=other)
        assert payment.contribution_type_id == other.pk

    def test_sans_mensuelle_par_defaut_le_type_est_demande(self, ctx):
        monthly_type(ctx)
        monthly_type(ctx, name="Mensuelle 20", amount="20")  # deux types « Tous » : aucun défaut inventé
        session = open_session(ctx)
        with pytest.raises(services.TreasuryValidationError, match="choisissez le type"):
            cash_pay(ctx, session, ctx.player)
        assert Payment.all_objects.count() == 0

    def test_mensuelle_rattachee_prioritaire(self, ctx):
        monthly_type(ctx)
        attached = monthly_type(ctx, name="Mensuelle 5", amount="5", scope=ContributionType.Scope.SELECTED)
        services.create_contribution_assignment(
            membership=ctx.player, contribution_type=attached,
            starts_on=datetime.date(2025, 1, 1), created_by=ctx.president.user,
        )
        assert services.get_default_contribution_type(ctx.player) == attached
        session = open_session(ctx)
        payment, _ = cash_pay(ctx, session, ctx.player, amount="5")
        assert payment.contribution_type_id == attached.pk

    def test_joueur_regularise_redevient_en_ordre(self, ctx):
        ctype = monthly_type(ctx)
        put_in_debt(ctx, ctx.player, ctype)
        assert services.is_in_good_standing(ctx.player) == (
            False, Decimal("10.00"), "Le joueur est en dette : 10.00 USD à régulariser."
        )
        session = open_session(ctx)
        cash_pay(ctx, session, ctx.player, amount="10")
        assert services.is_in_good_standing(ctx.player)[0] is True

    @pytest.mark.parametrize("amount", ["0", "-1", "abc", "", "1e30", 5.5, None])
    def test_montants_invalides(self, ctx, amount):
        monthly_type(ctx)
        session = open_session(ctx)
        with pytest.raises(services.InvalidAmountError):
            cash_pay(ctx, session, ctx.player, amount=amount)
        assert Payment.all_objects.count() == 0

    def test_ecritures_gelees(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        services.freeze_ledger(club=ctx.club, reason="Rupture simulée", actor=None)
        with pytest.raises(services.LedgerFrozenError):
            cash_pay(ctx, session, ctx.player)
        assert Payment.all_objects.count() == 0

    def test_joueur_d_un_autre_club_refuse(self, ctx, other_ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        with pytest.raises(services.TreasuryValidationError):
            cash_pay(ctx, session, other_ctx.player)


class TestOfflineSync:
    """Hors connexion : la validité porte sur l'HEURE DE SAISIE (6.6 ; 10.2 n° 22)."""

    def test_saisi_avant_minuit_synchronise_apres_minuit_accepte(self, ctx):
        monthly_type(ctx)
        day = days_ago_local(ctx, 2)
        session = open_session(ctx, now=local_dt(ctx, day, 9))
        recorded = local_dt(ctx, day, 23, 45)
        sync_time = local_dt(ctx, day + datetime.timedelta(days=1), 8)  # lendemain matin

        payment, created = cash_pay(ctx, session, ctx.player, recorded_at=recorded, now=sync_time)

        assert created is True
        assert payment.cash_session_id == session.pk
        assert payment.client_recorded_at == recorded
        assert payment.paid_on == day  # jour de la saisie, fuseau du club
        assert payment.validated_at == sync_time

    def test_saisi_apres_minuit_sans_nouvelle_session_refuse(self, ctx):
        monthly_type(ctx)
        day = days_ago_local(ctx, 2)
        session = open_session(ctx, now=local_dt(ctx, day, 9))
        after_midnight = local_dt(ctx, day + datetime.timedelta(days=1), 0, 5)
        with pytest.raises(services.CashSessionNotValidError, match="après minuit"):
            cash_pay(ctx, session, ctx.player, recorded_at=after_midnight, now=after_midnight)
        assert Payment.all_objects.count() == 0

    def test_minuit_pile_refuse(self, ctx):
        monthly_type(ctx)
        day = days_ago_local(ctx, 2)
        session = open_session(ctx, now=local_dt(ctx, day, 9))
        with pytest.raises(services.CashSessionNotValidError):
            cash_pay(ctx, session, ctx.player, recorded_at=session.expires_at, now=session.expires_at)

    def test_apres_minuit_avec_nouvelle_session_accepte(self, ctx):
        monthly_type(ctx)
        day = days_ago_local(ctx, 2)
        open_session(ctx, now=local_dt(ctx, day, 9))
        next_day_morning = local_dt(ctx, day + datetime.timedelta(days=1), 8)
        new_session = open_session(ctx, now=next_day_morning)
        payment, _ = cash_pay(ctx, new_session, ctx.player, recorded_at=next_day_morning, now=next_day_morning)
        assert payment.cash_session_id == new_session.pk

    def test_expiration_dans_un_fuseau_different_d_utc(self, ctx):
        set_timezone(ctx, "America/Los_Angeles")
        monthly_type(ctx)
        day = days_ago_local(ctx, 2)
        session = open_session(ctx, now=local_dt(ctx, day, 20))
        # 23:59 à Los Angeles = lendemain 06:59 UTC : encore valide.
        ok_time = local_dt(ctx, day, 23, 59)
        assert ok_time.astimezone(UTC).date() != day
        payment, _ = cash_pay(ctx, session, ctx.player, recorded_at=ok_time, now=ok_time + datetime.timedelta(hours=10))
        assert payment.paid_on == day
        with pytest.raises(services.CashSessionNotValidError):
            cash_pay(ctx, session, ctx.player, recorded_at=local_dt(ctx, day + datetime.timedelta(days=1), 0, 1))

    def test_heure_de_saisie_anterieure_a_l_ouverture_refusee(self, ctx):
        monthly_type(ctx)
        now = timezone.now()
        session = open_session(ctx, now=now)
        with pytest.raises(services.CashSessionNotValidError, match="précède"):
            cash_pay(ctx, session, ctx.player, recorded_at=now - datetime.timedelta(minutes=1), now=now)

    def test_heure_de_saisie_dans_le_futur_refusee(self, ctx):
        monthly_type(ctx)
        now = timezone.now()
        session = open_session(ctx, now=now - datetime.timedelta(minutes=10))
        with pytest.raises(services.CashSessionNotValidError, match="futur"):
            cash_pay(ctx, session, ctx.player, recorded_at=now + datetime.timedelta(minutes=10), now=now)

    def test_heure_de_saisie_naive_refusee(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        with pytest.raises(services.TreasuryValidationError, match="heure de saisie"):
            cash_pay(ctx, session, ctx.player, recorded_at=datetime.datetime.now())

    def test_saisie_apres_fermeture_refusee_avant_acceptee(self, ctx):
        monthly_type(ctx)
        now = timezone.now()
        session = open_session(ctx, now=now - datetime.timedelta(minutes=30))
        closed = services.close_cash_session(
            club=ctx.club, user=ctx.treasurer.user, public_id=session.public_id, now=now - datetime.timedelta(minutes=10)
        )
        assert closed.status == CashSession.Status.CLOSED
        payment, _ = cash_pay(ctx, closed, ctx.player, recorded_at=now - datetime.timedelta(minutes=20), now=now)
        assert payment.cash_session_id == session.pk
        with pytest.raises(services.CashSessionNotValidError, match="fermeture"):
            cash_pay(ctx, closed, ctx.player, recorded_at=now - datetime.timedelta(minutes=5), now=now)

    def test_synchronisation_rejouee_idempotente(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        key = uuid.uuid4()
        recorded = timezone.now()
        first, created_first = cash_pay(ctx, session, ctx.player, client_uuid=key, recorded_at=recorded)
        again, created_again = cash_pay(ctx, session, ctx.player, client_uuid=str(key), recorded_at=recorded)
        assert (created_first, created_again) == (True, False)
        assert again.pk == first.pk
        assert Payment.all_objects.filter(client_uuid=key).count() == 1
        assert Transaction.all_objects.filter(kind="payment").count() == 1

    def test_rejeu_apres_minuit_toujours_idempotent(self, ctx):
        monthly_type(ctx)
        day = days_ago_local(ctx, 2)
        session = open_session(ctx, now=local_dt(ctx, day, 9))
        key = uuid.uuid4()
        recorded = local_dt(ctx, day, 18)
        first, _ = cash_pay(ctx, session, ctx.player, client_uuid=key, recorded_at=recorded, now=recorded)
        again, created = cash_pay(ctx, session, ctx.player, client_uuid=key, recorded_at=recorded)
        assert again.pk == first.pk and created is False

    def test_cle_reutilisee_pour_un_autre_encaissement(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        key = uuid.uuid4()
        cash_pay(ctx, session, ctx.player, client_uuid=key, amount="10")
        with pytest.raises(services.ClientUuidConflictError):
            cash_pay(ctx, session, ctx.player, client_uuid=key, amount="20")
        assert Payment.all_objects.count() == 1

    def test_cle_invalide(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        with pytest.raises(services.TreasuryValidationError, match="Identifiant"):
            cash_pay(ctx, session, ctx.player, client_uuid="pas-un-uuid")


class TestSessionOwnership:
    def test_session_d_un_autre_utilisateur_refusee(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx, ctx.assistant_treasurer)
        with pytest.raises(services.CashSessionNotFoundError):
            cash_pay(ctx, session, ctx.player, user=ctx.treasurer)

    def test_session_d_un_autre_club_refusee(self, ctx, other_ctx):
        monthly_type(ctx)
        other_session = open_session(other_ctx)
        with pytest.raises(services.CashSessionNotFoundError):
            services.record_cash_payment(
                club=ctx.club, user=ctx.treasurer.user, public_id=other_session.public_id,
                membership=ctx.player, amount="10", client_uuid=uuid.uuid4(), client_recorded_at=timezone.now(),
            )
        with pytest.raises(services.CashSessionNotFoundError):
            services.close_cash_session(club=ctx.club, user=ctx.treasurer.user, public_id=other_session.public_id)

    def test_identifiant_inconnu(self, ctx):
        monthly_type(ctx)
        with pytest.raises(services.CashSessionNotFoundError):
            services.get_owned_cash_session(club=ctx.club, user=ctx.treasurer.user, public_id=uuid.uuid4())

    def test_role_retire_encaissement_refuse(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        MembershipRole.all_objects.filter(membership=ctx.treasurer).update(
            revoked_at=timezone.now(), revoked_by=ctx.president.user, revoked_reason="Fin de mandat"
        )
        with pytest.raises(services.TreasuryPermissionError):
            cash_pay(ctx, session, ctx.player)


class TestClosing:
    def test_fermeture_journalisee_et_idempotente(self, ctx):
        session = open_session(ctx)
        closed = services.close_cash_session(club=ctx.club, user=ctx.treasurer.user, public_id=session.public_id)
        again = services.close_cash_session(club=ctx.club, user=ctx.treasurer.user, public_id=session.public_id)
        assert closed.closed_at is not None and again.closed_at == closed.closed_at
        assert AuditLog.objects.filter(action_type="treasury.cash_session.closed").count() == 1
        assert services.get_current_cash_session(club=ctx.club, user=ctx.treasurer.user) is None

    def test_fermeture_apres_expiration_sans_effet(self, ctx):
        day = days_ago_local(ctx, 2)
        session = open_session(ctx, now=local_dt(ctx, day, 9))
        result = services.close_cash_session(club=ctx.club, user=ctx.treasurer.user, public_id=session.public_id)
        assert result.closed_at is None
        assert services.cash_session_state(result) == CashSession.Status.EXPIRED

    def test_totaux_de_la_session(self, ctx):
        monthly_type(ctx)
        session = open_session(ctx)
        cash_pay(ctx, session, ctx.player, amount="10")
        cash_pay(ctx, session, ctx.president, amount="5.50")
        assert services.cash_session_totals(session) == (2, Decimal("15.50"))


# ---------------------------------------------------------------------------
# Recherche
# ---------------------------------------------------------------------------


def search(ctx, session, query, **kwargs):
    # Utilisateur deja charge : seules les requetes du service sont mesurees.
    return services.search_cash_session_players(
        club=ctx.club, user=ctx.treasurer.user, public_id=session.public_id, query=query, **kwargs
    )


class TestSearch:
    def test_par_nom_et_par_numero(self, ctx):
        monthly_type(ctx)
        target = named_member(ctx, first_name="Didier", last_name="Zokwanga", jersey_number=7)
        session = open_session(ctx)
        assert [r.membership.pk for r in search(ctx, session, "zokwa")] == [target.pk]
        assert [r.membership.pk for r in search(ctx, session, "Didier Zok")] == [target.pk]
        assert target.pk in [r.membership.pk for r in search(ctx, session, "7")]

    def test_joueurs_partis_exclus_en_attente_inclus(self, ctx):
        session = open_session(ctx)
        pending = named_member(ctx, first_name="Attente", last_name="Qxyzon", status=Membership.Status.PENDING)
        gone = named_member(ctx, first_name="Parti", last_name="Qxyzon")
        gone.status = Membership.Status.DEPARTED
        gone.left_on = club_today(ctx)
        gone.left_reason = Membership.LeftReason.OTHER
        gone.left_by = ctx.president.user
        gone.save()
        assert [r.membership.pk for r in search(ctx, session, "Qxyzon")] == [pending.pk]

    def test_au_plus_20_resultats(self, ctx):
        session = open_session(ctx)
        for index in range(25):
            named_member(ctx, first_name=f"J{index}", last_name="Masuwa")
        assert len(search(ctx, session, "Masuwa")) == 20

    def test_statut_recalcule_a_la_lecture(self, ctx):
        ctype = monthly_type(ctx)
        target = named_member(ctx, first_name="Regul", last_name="Kinkela")
        put_in_debt(ctx, target, ctype)
        session = open_session(ctx)
        before = search(ctx, session, "Kinkela")[0]
        assert before.summary.is_in_good_standing is False
        assert before.summary.balance == Decimal("-10.00")
        cash_pay(ctx, session, target, amount="10")
        after = search(ctx, session, "Kinkela")[0]
        assert after.summary.is_in_good_standing is True
        assert after.summary.balance == Decimal("0.00")
        assert after.default_contribution_type_id == ctype.pk

    def test_session_expiree_ou_d_un_autre_refusee(self, ctx):
        day = days_ago_local(ctx, 2)
        expired = open_session(ctx, now=local_dt(ctx, day, 9))
        with pytest.raises(services.CashSessionNotValidError):
            search(ctx, expired, "a")
        other = open_session(ctx, ctx.assistant_treasurer)
        with pytest.raises(services.CashSessionNotFoundError):
            services.search_cash_session_players(
                club=ctx.club, user=ctx.treasurer.user, public_id=other.public_id, query="a"
            )

    def test_recherche_vide_refusee(self, ctx):
        session = open_session(ctx)
        with pytest.raises(services.TreasuryValidationError):
            search(ctx, session, "   ")

    def test_aucun_n_plus_1_sur_20_joueurs(self, ctx):
        """Le nombre de requêtes ne dépend pas du nombre de joueurs trouvés."""

        ctype = monthly_type(ctx)
        session = open_session(ctx)
        first = named_member(ctx, first_name="Solo", last_name="Nplusun")
        put_in_debt(ctx, first, ctype)
        with CaptureQueriesContext(connection) as one:
            assert len(search(ctx, session, "Nplusun")) == 1
        for index in range(19):
            member = named_member(ctx, first_name=f"Multi{index}", last_name="Nplusun", jersey_number=index + 1)
            put_in_debt(ctx, member, ctype)
            cash_pay(ctx, session, member, amount="3")
        with CaptureQueriesContext(connection) as twenty:
            results = search(ctx, session, "Nplusun")
        assert len(results) == 20
        assert len(twenty.captured_queries) == len(one.captured_queries)
        # Mesure documentée (compte rendu) : borne haute stable.
        assert len(twenty.captured_queries) <= 15
