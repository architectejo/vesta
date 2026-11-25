"""Notification « Dette constatée à l'échéance » (CDC 4.17 : joueur,
Trésorier, adjoint, in-app ; CDC 4.4.2 : un montant dû ne devient dette
qu'après l'échéance du type + la tolérance du club ; 10.2 n° 4 ; 10.2
n° 108 : aucune dette constatée tant que les joueurs ne peuvent pas payer).

Service ``run_debt_due_notifications`` appelé par la commande cron
``notify_debt_due`` : idempotent (jamais deux notifications pour la même
échéance, garanti en base par ``DebtDueNotice.due`` unique), journalisé
(règle 6, acteur « Système »), étanche entre clubs.
"""

from __future__ import annotations

import datetime
import io
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.clubs.models import Membership
from apps.core.tenant import TenantMismatchError, active_club
from apps.notifications.models import Notification
from apps.treasury import services
from apps.treasury.models import DebtDueNotice, Due, LedgerImmutableError, Payment
from apps.treasury.tests.cash_helpers import club_today, monthly_type, named_member
from apps.treasury.tests.conftest import make_member

pytestmark = pytest.mark.django_db

EVENT = Notification.EventType.DEBT_DUE
# 15 mars 2026, 10:00 à Kinshasa (UTC+1).
NOW = datetime.datetime(2026, 3, 15, 9, 0, tzinfo=datetime.timezone.utc)
MARCH = datetime.date(2026, 3, 1)


def at(day: int, month: int = 3) -> datetime.datetime:
    """Instant du jour ``day`` (10:00 à Kinshasa)."""

    return datetime.datetime(2026, month, day, 9, 0, tzinfo=datetime.timezone.utc)


def make_due(ctx, membership, ctype, *, period=MARCH, due_date=None, amount="10", source=Due.Source.SCHEDULER):
    due = Due(
        club=ctx.club,
        membership=membership,
        contribution_type=ctype,
        period=period,
        amount=Decimal(amount),
        due_date=due_date or period.replace(day=10),
        source=source,
        created_at=timezone.now(),
    )
    due.save()
    return due


def run(ctx, now=NOW, **kwargs):
    return services.run_debt_due_notifications(ctx.club, now=now, **kwargs)


def debt_notifications(user=None, club=None):
    queryset = Notification.objects.filter(event_type=EVENT)
    if user is not None:
        queryset = queryset.filter(recipient=user)
    if club is not None:
        queryset = queryset.filter(club=club)
    return queryset


def pay(ctx, membership, ctype, amount, *, paid_on=datetime.date(2026, 3, 5), now=at(5)):
    return services.record_payment(
        membership=membership,
        contribution_type=ctype,
        amount=amount,
        method=Payment.Method.CASH,
        paid_on=paid_on,
        recorded_by=ctx.treasurer.user,
        now=now,
    )


@pytest.fixture
def ctype(ctx):
    return monthly_type(ctx)


@pytest.fixture
def debtor(ctx):
    return named_member(ctx, first_name="Gédéon", last_name="Débiteur")


# ---------------------------------------------------------------------------
# Destinataires et contenu (CDC 4.17)
# ---------------------------------------------------------------------------


class TestDestinatairesEtContenu:
    def test_joueur_tresorier_et_adjoint_notifies(self, ctx, ctype, debtor):
        due = make_due(ctx, debtor, ctype)

        outcome = run(ctx)

        assert outcome.notified_count == 1
        recipients = set(debt_notifications().values_list("recipient_id", flat=True))
        assert recipients == {debtor.user_id, ctx.treasurer.user_id, ctx.assistant_treasurer.user_id}
        for member in (ctx.president, ctx.vice_president, ctx.player, ctx.pending_member):
            assert not debt_notifications(member.user).exists()
        for notification in debt_notifications():
            assert notification.club_id == ctx.club.pk
            assert notification.title == "Dette constatée à l'échéance"
            assert (notification.link_object_type, notification.link_object_id) == ("Due", due.pk)
            # In-app seulement (CDC 4.17).
            assert notification.email_requested is False

    def test_texte_du_joueur(self, ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        run(ctx)
        assert debt_notifications(debtor.user).get().body == (
            "Votre cotisation « Mensuelle 10 » de mars 2026 (10 $) n'a pas été réglée à l'échéance "
            "du 10/03/2026. Montant à régulariser : 10 $."
        )

    def test_texte_du_tresorier(self, ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        run(ctx)
        assert debt_notifications(ctx.treasurer.user).get().body == (
            "Dette constatée : Gédéon Débiteur, cotisation « Mensuelle 10 » de mars 2026 (10 $) "
            "non réglée à l'échéance du 10/03/2026. Montant à régulariser : 10 $."
        )

    def test_paiement_partiel_montant_restant(self, ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        pay(ctx, debtor, ctype, "4")
        run(ctx)
        assert debt_notifications(debtor.user).get().body.endswith("Montant à régulariser : 6 $.")

    def test_joueur_tresorier_une_seule_notification(self, ctx, ctype):
        make_due(ctx, ctx.treasurer, ctype)
        run(ctx)
        assert debt_notifications(ctx.treasurer.user).count() == 1
        assert debt_notifications(ctx.treasurer.user).get().body.startswith("Votre cotisation")
        assert debt_notifications(ctx.assistant_treasurer.user).count() == 1

    def test_devise_du_club(self, other_ctx):
        ctype = monthly_type(other_ctx, amount="25000")
        make_due(other_ctx, other_ctx.player, ctype, amount="25000")
        services.run_debt_due_notifications(other_ctx.club, now=NOW)
        assert "Montant à régulariser : 25 000 FC." in debt_notifications(other_ctx.player.user).get().body


# ---------------------------------------------------------------------------
# Quand : échéance + tolérance du club (CDC 4.4.2 ; 10.2 n° 4)
# ---------------------------------------------------------------------------


class TestDeclencheur:
    def test_pas_avant_l_echeance(self, ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        for day in (1, 9, 10):
            assert run(ctx, now=at(day)).notified_count == 0
        assert not debt_notifications().exists()
        assert not DebtDueNotice.all_objects.exists()
        assert run(ctx, now=at(11)).notified_count == 1

    def test_tolerance_du_club(self, ctx, ctype, debtor):
        settings_obj = ctx.club.settings
        settings_obj.debt_tolerance_days = 3
        settings_obj.save()
        make_due(ctx, debtor, ctype)

        assert run(ctx, now=at(13)).notified_count == 0
        assert not debt_notifications().exists()
        assert run(ctx, now=at(14)).notified_count == 1

    def test_mois_paye_aucune_notification(self, ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        pay(ctx, debtor, ctype, "10")
        assert run(ctx).notified_count == 0
        assert not debt_notifications().exists()
        # Échéance traitée une fois pour toutes, jamais réévaluée.
        notice = DebtDueNotice.all_objects.get()
        assert notice.outcome == DebtDueNotice.Outcome.NOT_IN_DEBT

    def test_paiement_anticipe_couvre_le_mois(self, ctx, ctype, debtor):
        pay(ctx, debtor, ctype, "40", paid_on=datetime.date(2026, 2, 20), now=at(20, month=2))
        make_due(ctx, debtor, ctype)
        services.refresh_member_allocations(debtor)
        assert run(ctx).notified_count == 0

    def test_joueur_en_ordre_grace_a_un_autre_type(self, ctx, ctype, debtor):
        # Le solde (CDC 4.4.2) porte sur tous les types obligatoires : un
        # joueur au solde positif est « En ordre », aucune dette constatée.
        other_type = monthly_type(ctx, name="Mensuelle 20", amount="20")
        pay(ctx, debtor, other_type, "50")
        make_due(ctx, debtor, ctype)
        assert services.get_balance(debtor, at_date=datetime.date(2026, 3, 15)) >= 0
        assert run(ctx).notified_count == 0

    def test_echeance_ancienne_jamais_notifiee_apres_coup(self, ctx, ctype, debtor):
        # Pas d'avalanche de notifications sur des échéances anciennes
        # (mise en service, rattrapage) : fenêtre de rattrapage limitée.
        make_due(ctx, debtor, ctype, period=datetime.date(2026, 1, 1))
        assert run(ctx).notified_count == 0
        assert not debt_notifications().exists()

    def test_fenetre_de_rattrapage_si_le_cron_a_manque_des_jours(self, ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        lookback = services.DEBT_NOTICE_LOOKBACK_DAYS
        assert run(ctx, now=at(10 + lookback)).notified_count == 1

    def test_joueur_parti_ignore(self, ctx, ctype):
        departed = named_member(ctx, first_name="Parti", last_name="Ailleurs", status=Membership.Status.DEPARTED)
        make_due(ctx, departed, ctype)
        assert run(ctx).notified_count == 0
        assert not debt_notifications().exists()

    def test_import_historique_jamais_notifie(self, ctx):
        from apps.treasury.tests.grid_helpers import NOW as IMPORT_NOW
        from apps.treasury.tests.grid_helpers import YEAR, attach, attached_type, csv_file, csv_line, player

        imported_type = attached_type(ctx)
        member = player(ctx, "Adolphe", "Akeba", email="adolphe.akeba@example.com")
        attach(ctx, member, imported_type)
        services.import_contributions(
            contribution_type=imported_type,
            year=YEAR,
            csv_file=csv_file([csv_line("Adolphe Akeba", "60", "", "", "", "", "", "", "10")]),
            imported_by=ctx.treasurer.user,
            now=IMPORT_NOW,
        )
        assert Due.all_objects.filter(membership=member, source=Due.Source.IMPORT).exists()
        assert services.get_balance(member, at_date=IMPORT_NOW.date()) < 0

        assert services.run_debt_due_notifications(ctx.club, now=IMPORT_NOW).notified_count == 0
        assert not debt_notifications().exists()

    def test_registre_gele_aucune_dette_constatee(self, ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        services.freeze_ledger(club=ctx.club, reason="Test de gel", actor=ctx.president.user)

        outcome = run(ctx)

        assert outcome.skipped and "gelées" in outcome.skipped_reason
        assert not debt_notifications().exists()
        assert not DebtDueNotice.all_objects.exists()


# ---------------------------------------------------------------------------
# Idempotence, simulation, journal
# ---------------------------------------------------------------------------


class TestIdempotence:
    def test_jamais_deux_notifications_pour_la_meme_echeance(self, ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        assert run(ctx).notified_count == 1
        assert run(ctx).notified_count == 0
        assert run(ctx, now=at(16)).notified_count == 0
        assert debt_notifications(debtor.user).count() == 1
        assert debt_notifications().count() == 3
        assert DebtDueNotice.all_objects.count() == 1

    def test_une_notification_par_echeance(self, ctx, ctype, debtor):
        other_type = monthly_type(ctx, name="Mensuelle 5", amount="5")
        make_due(ctx, debtor, ctype)
        make_due(ctx, debtor, other_type, amount="5")
        assert run(ctx).notified_count == 2
        assert debt_notifications(debtor.user).count() == 2

    def test_unicite_garantie_en_base(self, ctx, ctype, debtor):
        due = make_due(ctx, debtor, ctype)
        run(ctx)
        duplicate = DebtDueNotice(
            club=ctx.club, due=due, outcome=DebtDueNotice.Outcome.NOTIFIED, amount_due=Decimal("10"), processed_at=NOW
        )
        with pytest.raises((IntegrityError, DjangoValidationError)):
            with transaction.atomic():
                duplicate.save()
        # Contrainte de base elle-même (hors validation du modèle).
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                DebtDueNotice.all_objects.bulk_create([duplicate])

    def test_avis_immuable(self, ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        run(ctx)
        notice = DebtDueNotice.all_objects.get()
        notice.outcome = DebtDueNotice.Outcome.NOT_IN_DEBT
        with pytest.raises(LedgerImmutableError):
            notice.save()
        with pytest.raises(LedgerImmutableError):
            notice.delete()

    def test_simulation_n_ecrit_rien(self, ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        outcome = run(ctx, dry_run=True)
        assert outcome.notified_count == 1
        assert not debt_notifications().exists()
        assert not DebtDueNotice.all_objects.exists()
        assert run(ctx).notified_count == 1

    def test_journal_avec_acteur_systeme(self, ctx, ctype, debtor):
        due = make_due(ctx, debtor, ctype)
        run(ctx)
        log = AuditLog.objects.get(action_type="treasury.debt_due.noticed")
        assert log.club_id == ctx.club.pk
        assert log.actor.email == services.SYSTEM_ACTOR_EMAIL
        assert log.after["due_id"] == due.pk
        assert log.after["outcome"] == "notified"
        assert log.after["amount_due"] == "10.00"

    def test_echec_du_journal_rien_n_est_ecrit(self, ctx, ctype, debtor, monkeypatch):
        make_due(ctx, debtor, ctype)

        def boom(**kwargs):
            raise RuntimeError("journal indisponible")

        monkeypatch.setattr(services, "log_action", boom)
        with pytest.raises(RuntimeError):
            run(ctx)
        assert not debt_notifications().exists()
        assert not DebtDueNotice.all_objects.exists()


# ---------------------------------------------------------------------------
# Étanchéité entre clubs
# ---------------------------------------------------------------------------


class TestEtancheite:
    def test_un_club_ne_traite_que_ses_echeances(self, ctx, other_ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        other_type = monthly_type(other_ctx, amount="25000")
        make_due(other_ctx, other_ctx.player, other_type, amount="25000")

        assert run(ctx).notified_count == 1

        assert not debt_notifications(club=other_ctx.club).exists()
        for member in (other_ctx.player, other_ctx.treasurer, other_ctx.assistant_treasurer):
            assert not Notification.objects.filter(recipient=member.user).exists()
        assert set(debt_notifications().values_list("club_id", flat=True)) == {ctx.club.pk}
        assert not DebtDueNotice.all_objects.filter(club=other_ctx.club).exists()

    def test_tresorier_d_un_autre_club_jamais_destinataire(self, ctx, other_ctx, ctype, debtor):
        # Le Trésorier et l'adjoint de l'autre club ne sont jamais
        # destinataires, même quand leur propre club a aussi des dettes.
        make_due(ctx, debtor, ctype)
        other_type = monthly_type(other_ctx, amount="25000")
        make_due(other_ctx, other_ctx.player, other_type, amount="25000")
        run(ctx)
        services.run_debt_due_notifications(other_ctx.club, now=NOW)
        for member in (other_ctx.treasurer, other_ctx.assistant_treasurer):
            bodies = list(debt_notifications(member.user).values_list("body", flat=True))
            assert len(bodies) == 1 and "Gédéon" not in bodies[0]
            assert debt_notifications(member.user).get().club_id == other_ctx.club.pk
        for member in (ctx.treasurer, ctx.assistant_treasurer):
            assert debt_notifications(member.user).get().club_id == ctx.club.pk
        # Un joueur hors bureau d'un rôle de trésorerie n'est jamais destinataire.
        bystander = make_member(other_ctx.club)
        assert not debt_notifications(bystander.user).exists()

    def test_contexte_d_un_autre_club_refuse(self, ctx, other_ctx, ctype, debtor):
        make_due(ctx, debtor, ctype)
        with active_club(other_ctx.club), pytest.raises(TenantMismatchError):
            run(ctx)
        assert not debt_notifications().exists()


# ---------------------------------------------------------------------------
# Commande cron
# ---------------------------------------------------------------------------


def due_yesterday(ctx, membership, ctype):
    """Échéance d'hier dans le fuseau du club (horloge réelle de la commande)."""

    yesterday = club_today(ctx) - datetime.timedelta(days=1)
    return make_due(ctx, membership, ctype, period=yesterday.replace(day=1), due_date=yesterday)


class TestCommande:
    def test_commande_idempotente(self, ctx, ctype, debtor):
        due_yesterday(ctx, debtor, ctype)
        out = io.StringIO()
        call_command("notify_debt_due", stdout=out)
        assert "1 dette(s) constatée(s)" in out.getvalue()
        out = io.StringIO()
        call_command("notify_debt_due", stdout=out)
        assert "0 dette(s) constatée(s)" in out.getvalue()
        assert debt_notifications(debtor.user).count() == 1

    def test_commande_limitee_a_un_club(self, ctx, other_ctx, ctype, debtor):
        due_yesterday(ctx, debtor, ctype)
        due_yesterday(other_ctx, other_ctx.player, monthly_type(other_ctx, amount="25000"))
        call_command("notify_debt_due", "--club", str(other_ctx.club.pk), stdout=io.StringIO())
        assert debt_notifications(club=other_ctx.club).exists()
        assert not debt_notifications(club=ctx.club).exists()

    def test_commande_simulation(self, ctx, ctype, debtor):
        due_yesterday(ctx, debtor, ctype)
        out = io.StringIO()
        call_command("notify_debt_due", "--dry-run", stdout=out)
        assert "[simulation]" in out.getvalue()
        assert not debt_notifications().exists()

    def test_commande_sortie_sans_donnee_personnelle(self, ctx, ctype, debtor):
        due_yesterday(ctx, debtor, ctype)
        out = io.StringIO()
        call_command("notify_debt_due", stdout=out)
        assert "Débiteur" not in out.getvalue() and debtor.user.email not in out.getvalue()

    def test_commande_club_inconnu(self, ctx):
        with pytest.raises(CommandError):
            call_command("notify_debt_due", "--club", "999999", stdout=io.StringIO())
