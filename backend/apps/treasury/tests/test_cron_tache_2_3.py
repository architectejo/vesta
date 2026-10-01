"""Commandes cron de la tresorerie (tache 2.3 ; CDC 4.4.2, 4.5.2, 5.3, 6.5).

- ``generate_monthly_dues`` : 1er du mois dans le fuseau du club,
  idempotence, rattrapage, exclusions (4.4.2), aucun blocage avant
  l'echeance, simulation, clubs bloques, isolation entre clubs.
- ``verify_ledger_chain`` : chaine saine sans effet ; rupture simulee par
  alteration directe en base (SQL brut, contourne l'ORM append-only) ->
  gel + alerte Superuser + aucun joueur penalise ; isolation entre clubs.
- ``mark_unjustified_expenses`` : passage « Non justifiee », alerte,
  idempotence, simulation.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone as django_timezone

from apps.accounts.tests.factories import SuperuserFactory
from apps.audit.models import AuditLog
from apps.clubs.models import ClubSettings, Membership
from apps.licences.models import Licence
from apps.licences.tests.factories import LicenceFactory
from apps.notifications.models import Notification
from apps.treasury import services
from apps.treasury.models import (
    ContributionType,
    Due,
    Expense,
    LedgerChainState,
    Payment,
    PaymentAllocation,
    Transaction,
)
from apps.treasury.tests.conftest import PIN, make_member, past_day
from apps.treasury.tests.expense_helpers import days_ago, make_category, make_expense, release

pytestmark = pytest.mark.django_db

UTC = datetime.timezone.utc
TABLE = Transaction._meta.db_table


# --- Outils ------------------------------------------------------------------


@pytest.fixture
def set_now(monkeypatch):
    """Fige ``django.utils.timezone.now`` (utilise par les services)."""

    def _set(value: datetime.datetime) -> None:
        monkeypatch.setattr(django_timezone, "now", lambda: value)

    return _set


def settle(ctx, joined_on=datetime.date(2025, 1, 1)) -> None:
    """Tous les membres du club sont entres bien avant les mois testes."""

    Membership.all_objects.filter(club=ctx.club).update(joined_on=joined_on)
    for membership in (ctx.president, ctx.vice_president, ctx.treasurer, ctx.assistant_treasurer, ctx.player):
        membership.refresh_from_db()


def monthly_type(ctx, *, name="Mensuelle 10", amount="10", scope=ContributionType.Scope.ALL):
    return services.create_contribution_type(
        club=ctx.club,
        created_by=ctx.president.user,
        name=name,
        nature=ContributionType.Nature.MANDATORY,
        periodicity=ContributionType.Periodicity.MONTHLY,
        amount=amount,
        scope=scope,
        now=datetime.datetime(2025, 12, 1, 12, tzinfo=UTC),
    )


ACTIVE_MEMBERS = 5  # President, VP, Tresorier, adjoint, joueur (le 6e est « En attente »)


def run(command: str, *args) -> tuple[str, str]:
    out, err = StringIO(), StringIO()
    call_command(command, *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def run_failing(command: str, *args) -> tuple[CommandError, str, str]:
    out, err = StringIO(), StringIO()
    with pytest.raises(CommandError) as excinfo:
        call_command(command, *args, stdout=out, stderr=err)
    return excinfo.value, out.getvalue(), err.getvalue()


def dues(ctx, period=None):
    queryset = Due.all_objects.filter(club=ctx.club)
    if period is not None:
        queryset = queryset.filter(period=period)
    return queryset


def raw_sql(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


# --- generate_monthly_dues ---------------------------------------------------


class TestGenerateMonthlyDues:
    def test_cree_les_dus_du_mois_pour_chaque_joueur_actif_et_est_idempotente(self, ctx, set_now):
        settle(ctx)
        ctype = monthly_type(ctx)
        set_now(datetime.datetime(2026, 3, 1, 7, 0, tzinfo=UTC))  # 08:00 a Kinshasa

        out, _ = run("generate_monthly_dues")
        again, _ = run("generate_monthly_dues")

        march = dues(ctx, datetime.date(2026, 3, 1))
        assert march.count() == ACTIVE_MEMBERS
        assert set(march.values_list("amount", flat=True)) == {Decimal("10.00")}
        assert set(march.values_list("due_date", flat=True)) == {datetime.date(2026, 3, 10)}
        assert set(march.values_list("source", flat=True)) == {Due.Source.SCHEDULER}
        assert set(march.values_list("contribution_type_id", flat=True)) == {ctype.pk}
        assert f"{ACTIVE_MEMBERS} montant(s) dû(s) créé(s)" in out
        assert "0 montant(s) dû(s) créé(s)" in again
        assert dues(ctx).count() == ACTIVE_MEMBERS
        # Convention cron (point ouvert) : aucun acteur reel, aucune entree de journal.
        assert not AuditLog.objects.filter(action_type="treasury.due.generated").exists()

    def test_aucun_blocage_le_1er_du_mois_avant_l_echeance(self, ctx, set_now):
        settle(ctx)
        monthly_type(ctx)
        set_now(datetime.datetime(2026, 3, 1, 7, 0, tzinfo=UTC))
        run("generate_monthly_dues")

        def standing(day):
            return services.is_in_good_standing(ctx.player, at_date=datetime.date(2026, 3, day))

        assert standing(1)[:2] == (True, Decimal("0.00"))
        assert standing(10)[:2] == (True, Decimal("0.00"))  # jour de l'echeance : pas encore une dette
        assert standing(11)[:2] == (False, Decimal("10.00"))

        ctx.club.settings.debt_tolerance_days = 3
        ctx.club.settings.save()
        assert standing(13)[0] is True
        assert standing(14)[:2] == (False, Decimal("10.00"))
        # Le passage en dette est calcule : aucune ecriture n'a eu lieu entre-temps.
        assert dues(ctx).count() == ACTIVE_MEMBERS

    def test_premier_du_mois_dans_le_fuseau_du_club_et_non_en_utc(self, ctx, other_ctx, set_now):
        settle(ctx)
        settle(other_ctx)
        monthly_type(ctx)
        monthly_type(other_ctx)
        other_ctx.club.settings.timezone = "Pacific/Auckland"  # UTC+13 en mars
        other_ctx.club.settings.save()

        # 31/03 20:00 UTC : 21:00 le 31/03 a Kinshasa, deja le 01/04 09:00 a Auckland.
        set_now(datetime.datetime(2026, 3, 31, 20, 0, tzinfo=UTC))
        run("generate_monthly_dues")

        assert set(dues(ctx).values_list("period", flat=True)) == {datetime.date(2026, 3, 1)}
        assert set(dues(other_ctx).values_list("period", flat=True)) == {datetime.date(2026, 4, 1)}

        # 31/03 23:30 UTC : deja le 01/04 00:30 a Kinshasa, alors que l'UTC est encore en mars.
        set_now(datetime.datetime(2026, 3, 31, 23, 30, tzinfo=UTC))
        run("generate_monthly_dues")
        assert dues(ctx, datetime.date(2026, 4, 1)).count() == ACTIVE_MEMBERS

    def test_rattrapage_d_un_mois_manque(self, ctx, set_now):
        settle(ctx)
        monthly_type(ctx)
        set_now(datetime.datetime(2026, 4, 15, 9, 0, tzinfo=UTC))

        run("generate_monthly_dues")
        assert not dues(ctx, datetime.date(2026, 3, 1)).exists()

        out, _ = run("generate_monthly_dues", "--period", "2026-03")
        run("generate_monthly_dues", "--period", "2026-03")

        assert dues(ctx, datetime.date(2026, 3, 1)).count() == ACTIVE_MEMBERS
        assert dues(ctx, datetime.date(2026, 4, 1)).count() == ACTIVE_MEMBERS
        assert "03/2026" in out

    def test_mois_futur_refuse(self, ctx, set_now):
        settle(ctx)
        monthly_type(ctx)
        set_now(datetime.datetime(2026, 4, 15, 9, 0, tzinfo=UTC))

        error, _, err = run_failing("generate_monthly_dues", "--period", "2026-05")

        assert error.returncode == 1
        assert "mois futur" in err
        assert not dues(ctx).exists()

    def test_periode_illisible_refusee(self, ctx):
        error, _, _ = run_failing("generate_monthly_dues", "--period", "mars")
        assert error.returncode == 1
        assert "AAAA-MM" in str(error)

    def test_club_sans_mensuelle(self, ctx, set_now):
        settle(ctx)
        set_now(datetime.datetime(2026, 3, 1, 7, 0, tzinfo=UTC))

        out, _ = run("generate_monthly_dues")

        assert not dues(ctx).exists()
        assert "0 montant(s) dû(s) créé(s)" in out

    def test_type_libre_ne_genere_aucun_montant_du(self, ctx, set_now):
        settle(ctx)
        services.create_contribution_type(
            club=ctx.club,
            created_by=ctx.president.user,
            name="Vestiaire",
            nature=ContributionType.Nature.FREE,
            periodicity=ContributionType.Periodicity.MONTHLY,
            amount="2",
            now=datetime.datetime(2025, 12, 1, 12, tzinfo=UTC),
        )
        set_now(datetime.datetime(2026, 3, 1, 7, 0, tzinfo=UTC))

        run("generate_monthly_dues")

        assert not dues(ctx).exists()

    def test_exclusions_en_attente_parti_suspendu_et_futur_mois_d_arrivee_du(self, ctx, set_now):
        settle(ctx)
        monthly_type(ctx)
        departed = make_member(ctx.club, status=Membership.Status.DEPARTED)
        departed.joined_on, departed.left_on = datetime.date(2025, 1, 1), datetime.date(2026, 2, 15)
        departed.left_reason = Membership.LeftReason.RESIGNATION
        departed.save()
        leaving_soon = make_member(ctx.club)  # sortie en cours de mois : le mois reste du
        leaving_soon.joined_on, leaving_soon.left_on = datetime.date(2025, 1, 1), datetime.date(2026, 3, 20)
        leaving_soon.left_reason = Membership.LeftReason.TRANSFER
        leaving_soon.save()
        arrival = make_member(ctx.club)
        arrival.joined_on = datetime.date(2026, 3, 1)
        arrival.save()
        future = make_member(ctx.club)
        future.joined_on = datetime.date(2026, 4, 2)
        future.save()
        services.create_contribution_suspension(
            membership=ctx.player,
            starts_on=datetime.date(2026, 3, 1),
            reason="Blessure longue durée",
            decided_by=ctx.president.user,
        )
        set_now(datetime.datetime(2026, 3, 1, 7, 0, tzinfo=UTC))

        out, _ = run("generate_monthly_dues")

        members = set(dues(ctx).values_list("membership_id", flat=True))
        assert ctx.pending_member.pk not in members  # « En attente »
        assert departed.pk not in members  # parti
        assert ctx.player.pk not in members  # cotisations suspendues par le President
        # Revue de conformite B7 : le mois d'arrivee est du en entier
        # (proposition par defaut 10.2 n° 5, non tranchee). Auparavant le
        # joueur etait ignore, ce qui contredisait le 10.2 n° 5.
        assert arrival.pk in members
        arrival_due = Due.all_objects.get(membership=arrival)
        assert arrival_due.source == Due.Source.ARRIVAL
        assert arrival_due.due_date == datetime.date(2026, 3, 10)  # arrive le 1er : echeance normale
        assert future.pk not in members  # entre apres le mois
        assert leaving_soon.pk in members
        assert members == {
            ctx.president.pk, ctx.vice_president.pk, ctx.treasurer.pk, ctx.assistant_treasurer.pk, leaving_soon.pk,
            arrival.pk,
        }
        assert "dont 1 montant(s) dû(s) de mois d'arrivée" in out
        assert "10.2 n° 5" in out

    def test_joueur_arrive_en_cours_de_mois_doit_son_mois_d_arrivee_avec_un_delai(self, ctx, set_now):
        """B7 (proposition par defaut 10.2 n° 5, non tranchee) : arrive le 20
        mars, apres l'echeance du 10, le joueur doit mars en entier avec le
        meme delai qu'un mois normal (9 jours) : echeance le 29 mars."""

        settle(ctx)
        monthly_type(ctx)
        arrival = make_member(ctx.club)
        arrival.joined_on = datetime.date(2026, 3, 20)
        arrival.save()

        set_now(datetime.datetime(2026, 3, 21, 7, 0, tzinfo=UTC))
        run("generate_monthly_dues")
        march = Due.all_objects.get(membership=arrival)
        assert (march.period, march.amount, march.due_date, march.source) == (
            datetime.date(2026, 3, 1), Decimal("10.00"), datetime.date(2026, 3, 29), Due.Source.ARRIVAL
        )
        # Personne n'est bloque des son arrivee.
        assert services.is_in_good_standing(arrival, at_date=datetime.date(2026, 3, 21))[0] is True
        assert services.is_in_good_standing(arrival, at_date=datetime.date(2026, 3, 29))[0] is True
        assert services.is_in_good_standing(arrival, at_date=datetime.date(2026, 3, 30))[:2] == (False, Decimal("10.00"))

        set_now(datetime.datetime(2026, 4, 1, 7, 0, tzinfo=UTC))
        run("generate_monthly_dues")
        assert list(Due.all_objects.filter(membership=arrival).order_by("period").values_list("period", flat=True)) == [
            datetime.date(2026, 3, 1), datetime.date(2026, 4, 1)
        ]

    def test_simulation_n_ecrit_rien(self, ctx, set_now):
        settle(ctx)
        monthly_type(ctx)
        set_now(datetime.datetime(2026, 3, 1, 7, 0, tzinfo=UTC))

        out, _ = run("generate_monthly_dues", "--dry-run")

        assert not dues(ctx).exists()
        assert "[simulation]" in out
        assert f"{ACTIVE_MEMBERS} montant(s) dû(s) créé(s)" in out

    @pytest.mark.parametrize("blocker", ["frozen", "read_only", "licence_suspended", "licence_terminated"])
    def test_club_bloque_ignore_sans_toucher_les_autres_clubs(self, ctx, other_ctx, set_now, blocker):
        settle(ctx)
        settle(other_ctx)
        monthly_type(ctx)
        monthly_type(other_ctx)
        if blocker == "frozen":
            services.freeze_ledger(club=ctx.club, reason="Rupture de test", actor=None)
        elif blocker == "read_only":
            ctx.club.status = ctx.club.Status.READ_ONLY
            ctx.club.save(update_fields=["status"])
        else:
            status = Licence.Status.SUSPENDED if blocker == "licence_suspended" else Licence.Status.TERMINATED
            LicenceFactory(club=ctx.club, status=status)
        set_now(datetime.datetime(2026, 3, 1, 7, 0, tzinfo=UTC))

        out, _ = run("generate_monthly_dues")

        assert not dues(ctx).exists()
        assert "ignoré" in out
        assert dues(other_ctx).count() == ACTIVE_MEMBERS

    def test_un_club_en_erreur_n_empeche_pas_les_autres(self, ctx, other_ctx, set_now):
        settle(ctx)
        settle(other_ctx)
        monthly_type(ctx)
        monthly_type(other_ctx)
        ClubSettings.objects.filter(club_id=ctx.club.pk).update(timezone="Mars/Olympus")
        set_now(datetime.datetime(2026, 3, 1, 7, 0, tzinfo=UTC))

        error, _, err = run_failing("generate_monthly_dues")

        assert error.returncode == 1
        assert "fuseau horaire du club est invalide" in err
        assert not dues(ctx).exists()
        assert dues(other_ctx).count() == ACTIVE_MEMBERS

    def test_option_club_limite_le_traitement(self, ctx, other_ctx, set_now):
        settle(ctx)
        settle(other_ctx)
        monthly_type(ctx)
        monthly_type(other_ctx)
        set_now(datetime.datetime(2026, 3, 1, 7, 0, tzinfo=UTC))

        run("generate_monthly_dues", "--club", str(other_ctx.club.pk))

        assert not dues(ctx).exists()
        assert dues(other_ctx).count() == ACTIVE_MEMBERS

    def test_club_inconnu_refuse(self, ctx):
        error, _, _ = run_failing("generate_monthly_dues", "--club", "999999")
        assert error.returncode == 1
        assert "Club introuvable" in str(error)


# --- verify_ledger_chain -----------------------------------------------------


def fee_payment(ctx):
    return services.record_membership_fee_payment(
        membership=make_member(ctx.club, status=Membership.Status.PENDING),
        amount="5",
        method="cash",
        paid_on=past_day(),
        validated_by=ctx.treasurer.user,
        pin=PIN,
    )


def mandatory_payment(ctx, membership, ctype, amount="10", paid_on=None):
    now = django_timezone.now()
    payment = Payment(
        club=ctx.club,
        membership=membership,
        contribution_type=ctype,
        amount=Decimal(amount),
        currency=ctx.club.settings.currency,
        method=Payment.Method.CASH,
        paid_on=paid_on or past_day(),
        source=Payment.Source.TREASURER_ENTRY,
        submitted_by=ctx.treasurer.user,
        submitted_at=now,
        validated_by=ctx.treasurer.user,
        validated_at=now,
    )
    payment.save()
    txn = services.open_payment_transaction(payment=payment, provider=Transaction.Provider.MANUAL)
    services.advance_transaction(transaction_obj=txn, status=Transaction.Status.SUCCEEDED)
    return payment


def financial_snapshot(ctx) -> dict:
    """Tout ce qui pourrait penaliser un joueur : soldes, statuts, dus,
    paiements, allocations."""

    today = services.get_club_today(ctx.club)
    memberships = Membership.all_objects.filter(club=ctx.club).order_by("pk")
    return {
        "balances": services.get_balances(ctx.club, at_date=today),
        "standing": {m.pk: services.is_in_good_standing(m, at_date=today) for m in memberships},
        "statuses": list(memberships.values_list("pk", "status")),
        "dues": list(Due.all_objects.filter(club=ctx.club).order_by("pk").values_list("pk", "amount", "due_date")),
        "payments": list(Payment.all_objects.filter(club=ctx.club).order_by("pk").values_list("pk", "amount")),
        "allocations": list(
            PaymentAllocation.all_objects.filter(club=ctx.club).order_by("pk").values_list("pk", "period", "amount")
        ),
    }


def chain_alerts():
    return Notification.objects.filter(event_type=Notification.EventType.LEDGER_CHAIN_BROKEN)


@pytest.fixture
def ledger_ctx(ctx, fee_type):
    """Un club avec des joueurs en ordre et en dette, et des transactions scellees."""

    settle(ctx)
    ctype = monthly_type(ctx)
    today = services.get_club_today(ctx.club)
    period = datetime.date(today.year, today.month, 1)
    for membership in (ctx.player, ctx.vice_president):
        Due(
            club=ctx.club,
            membership=membership,
            contribution_type=ctype,
            period=period,
            amount=Decimal("10.00"),
            due_date=today - datetime.timedelta(days=15),
            source=Due.Source.SCHEDULER,
            created_at=django_timezone.now(),
        ).save()
    mandatory_payment(ctx, ctx.player, ctype)  # joueur en ordre ; le VP reste en dette
    fee_payment(ctx)
    fee_payment(ctx)
    return ctx


class TestVerifyLedgerChain:
    def test_chaine_saine_ne_fait_rien(self, ledger_ctx):
        SuperuserFactory()
        before = financial_snapshot(ledger_ctx)

        out, err = run("verify_ledger_chain")

        state = LedgerChainState.all_objects.get(club=ledger_ctx.club)
        assert state.is_frozen is False
        assert not chain_alerts().exists()
        assert financial_snapshot(ledger_ctx) == before
        assert "chaîne intègre (3 transaction(s))" in out
        assert "ruptures : 0" in out
        assert err == ""

    def test_rupture_gele_le_club_alerte_le_superuser_sans_penaliser_aucun_joueur(self, ledger_ctx):
        ctx = ledger_ctx
        superuser = SuperuserFactory()
        inactive_superuser = SuperuserFactory(is_active=False)
        target = Transaction.all_objects.filter(club=ctx.club).order_by("sequence")[1]
        raw_sql(f"UPDATE {TABLE} SET amount = %s WHERE id = %s", ["500.00", target.pk])
        before = financial_snapshot(ctx)
        assert before["standing"][ctx.player.pk][0] is True
        assert before["standing"][ctx.vice_president.pk][0] is False

        error, _, err = run_failing("verify_ledger_chain")

        assert error.returncode == 2
        assert "RUPTURE DE CHAÎNE" in err
        assert "Aucun joueur n'est pénalisé" in err
        state = LedgerChainState.all_objects.get(club=ctx.club)
        assert state.is_frozen is True
        assert state.frozen_reason == f"Rupture de chaîne détectée à la séquence {target.sequence}"
        # Alerte aux Superusers actifs (CDC 5.3), a eux seuls, une fois chacun.
        alerts = chain_alerts()
        active_superusers = set(
            get_user_model().objects.filter(is_superuser=True, is_active=True).values_list("pk", flat=True)
        )
        recipients = list(alerts.values_list("recipient_id", flat=True))
        assert superuser.pk in active_superusers
        assert sorted(recipients) == sorted(active_superusers)
        assert inactive_superuser.pk not in recipients
        assert set(alerts.values_list("club_id", flat=True)) == {ctx.club.pk}
        assert Notification.objects.filter(recipient__is_superuser=False).count() == 0
        # Aucun joueur penalise : rien n'a bouge du cote des joueurs.
        assert financial_snapshot(ctx) == before
        # Convention cron : pas d'entree de journal sans acteur reel.
        assert not AuditLog.objects.filter(action_type="treasury.ledger.frozen").exists()
        # Les ecritures sont gelees, les lectures restent possibles.
        with pytest.raises(services.LedgerFrozenError):
            fee_payment(ctx)
        services.get_balance(ctx.player)

    def test_relance_apres_rupture_ne_realerte_pas(self, ledger_ctx):
        SuperuserFactory()
        target = Transaction.all_objects.filter(club=ledger_ctx.club).order_by("sequence").first()
        raw_sql(f"UPDATE {TABLE} SET amount = %s WHERE id = %s", ["1.00", target.pk])
        run_failing("verify_ledger_chain")
        frozen_at = LedgerChainState.all_objects.get(club=ledger_ctx.club).frozen_at
        first_alerts = chain_alerts().count()
        assert first_alerts >= 1

        error, _, err = run_failing("verify_ledger_chain")

        assert error.returncode == 2
        assert "club déjà gelé, aucune nouvelle alerte" in err
        assert chain_alerts().count() == first_alerts
        assert LedgerChainState.all_objects.get(club=ledger_ctx.club).frozen_at == frozen_at

    def test_la_rupture_du_club_a_ne_gele_pas_le_club_b(self, ledger_ctx, other_ctx, other_fee_type):
        SuperuserFactory()
        fee_payment(other_ctx)
        target = Transaction.all_objects.filter(club=ledger_ctx.club).order_by("sequence").last()
        raw_sql(f"UPDATE {TABLE} SET hash = %s WHERE id = %s", ["f" * 64, target.pk])

        error, out, err = run_failing("verify_ledger_chain")

        assert error.returncode == 2
        assert LedgerChainState.all_objects.get(club=ledger_ctx.club).is_frozen is True
        assert LedgerChainState.all_objects.get(club=other_ctx.club).is_frozen is False
        assert f"Club {other_ctx.club.pk} « {other_ctx.club.name} » : chaîne intègre" in out
        assert set(chain_alerts().values_list("club_id", flat=True)) == {ledger_ctx.club.pk}
        fee_payment(other_ctx)  # le club B continue d'ecrire

    def test_simulation_detecte_sans_geler_ni_alerter(self, ledger_ctx):
        SuperuserFactory()
        target = Transaction.all_objects.filter(club=ledger_ctx.club).order_by("sequence").first()
        raw_sql(f"UPDATE {TABLE} SET amount = %s WHERE id = %s", ["1.00", target.pk])

        error, _, err = run_failing("verify_ledger_chain", "--dry-run")

        assert error.returncode == 2
        assert "[simulation]" in err
        assert "le club serait gelé" in err
        assert LedgerChainState.all_objects.get(club=ledger_ctx.club).is_frozen is False
        assert not chain_alerts().exists()

    def test_cle_indisponible_signalee_sans_geler(self, ledger_ctx, settings):
        SuperuserFactory()
        settings.LEDGER_HMAC_KEYS = {}

        error, _, err = run_failing("verify_ledger_chain")

        assert error.returncode == 1
        assert "vérification impossible" in err
        assert LedgerChainState.all_objects.get(club=ledger_ctx.club).is_frozen is False
        assert not chain_alerts().exists()

    def test_club_sans_transaction_est_sain(self, ctx):
        out, _ = run("verify_ledger_chain")
        assert "chaîne intègre (0 transaction(s))" in out


# --- mark_unjustified_expenses -----------------------------------------------


class TestMarkUnjustifiedExpenses:
    def test_passe_non_justifiee_alerte_et_est_idempotente(self, ctx, other_ctx):
        on_time = release(ctx, make_expense(ctx, make_category(ctx, name="Autre")))
        late = release(ctx, make_expense(ctx), now=days_ago(10))

        out, _ = run("mark_unjustified_expenses")
        again, _ = run("mark_unjustified_expenses")

        assert Expense.all_objects.get(pk=late.pk).status == Expense.Status.UNJUSTIFIED
        assert Expense.all_objects.get(pk=on_time.pk).status == Expense.Status.RELEASED
        alerts = Notification.objects.filter(event_type=Notification.EventType.EXPENSE_BLOCKING)
        assert {n.recipient_id for n in alerts} == {
            ctx.treasurer.user_id,
            ctx.assistant_treasurer.user_id,
            ctx.president.user_id,
        }
        assert "1 dépense(s) passée(s) « Non justifiée »" in out
        assert "Dépenses passées « Non justifiée » : 0" in again
        assert alerts.count() == 3
        assert not services.can_release_expense(ctx.club).allowed
        assert services.can_release_expense(other_ctx.club).allowed

    def test_simulation_n_ecrit_rien(self, ctx):
        late = release(ctx, make_expense(ctx), now=days_ago(10))

        out, _ = run("mark_unjustified_expenses", "--dry-run")

        assert "[simulation]" in out
        assert "1 dépense(s)" in out
        assert Expense.all_objects.get(pk=late.pk).status == Expense.Status.RELEASED
        assert not Notification.objects.filter(event_type=Notification.EventType.EXPENSE_BLOCKING).exists()
        # Le blocage ne depend pas du cron : il est deja effectif.
        assert not services.can_release_expense(ctx.club).allowed
