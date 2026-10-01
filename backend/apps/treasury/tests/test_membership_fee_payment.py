"""Paiement des frais d'adhesion (CDC 4.3 etape 2, 4.4.4, 4.6, 7.2 ; tache 1.4b).

Interface exposee a `backend-dev` : `record_membership_fee_payment` et
`has_paid_membership_fee` (invariant 10, cote tresorerie).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.services import InvalidPinError, PinLockedError, PinNotSetError
from apps.audit.models import AuditLog
from apps.clubs.models import Membership
from apps.treasury import services
from apps.treasury.models import LedgerChainState, Payment, Transaction
from apps.treasury.tests.conftest import PIN, WRONG_PIN, make_member, past_day
from apps.treasury.tests.factories import ContributionTypeFactory

from apps.accounts.tests.factories import SuperuserFactory  # noqa: E402

pytestmark = pytest.mark.django_db


def pay(ctx, *, membership=None, amount="5", method="cash", paid_on=None, validated_by=None, pin=PIN, **extra):
    return services.record_membership_fee_payment(
        membership=membership or ctx.pending_member,
        amount=amount,
        method=method,
        paid_on=paid_on or past_day(),
        validated_by=(validated_by or ctx.treasurer).user,
        pin=pin,
        **extra,
    )


class TestEnregistrement:
    def test_paiement_complet_cree_payment_et_transaction_scellee(self, ctx, fee_type):
        payment = pay(ctx, reference="MM-123")

        assert payment.club_id == ctx.club.id
        assert payment.membership_id == ctx.pending_member.id
        assert payment.contribution_type_id == fee_type.id
        assert payment.amount == Decimal("5.00")
        assert payment.currency == "USD"
        assert payment.method == Payment.Method.CASH
        assert payment.source == Payment.Source.TREASURER_ENTRY
        assert payment.reference == "MM-123"
        assert payment.submitted_by_id == ctx.treasurer.user_id
        assert payment.validated_by_id == ctx.treasurer.user_id
        assert payment.validated_at is not None
        assert payment.receipt_number == 1

        txn = payment.transaction
        assert txn.kind == Transaction.Kind.PAYMENT
        assert txn.status == Transaction.Status.SUCCEEDED
        # Invariant 11 : fournisseur, reference externe et statut des le MVP.
        assert txn.provider == Transaction.Provider.MANUAL
        assert txn.external_ref is None
        assert txn.amount == Decimal("5.00")
        assert txn.currency == "USD"
        assert txn.value_date == payment.paid_on
        assert txn.membership_id == ctx.pending_member.id
        assert txn.contribution_type_id == fee_type.id
        assert txn.sequence == 1
        assert txn.previous_hash == services.LEDGER_GENESIS_HASH
        assert len(txn.hash) == 64
        assert txn.key_id == "test-v1"
        assert txn.sealed_at is not None

        assert services.has_paid_membership_fee(ctx.pending_member) is True

    def test_tresorier_adjoint_peut_enregistrer(self, ctx, fee_type):
        payment = pay(ctx, validated_by=ctx.assistant_treasurer)
        assert payment.validated_by_id == ctx.assistant_treasurer.user_id

    def test_devise_du_club_recopiee(self, other_ctx, other_fee_type):
        payment = pay(other_ctx)
        assert payment.currency == "CDF"
        assert payment.transaction.currency == "CDF"

    def test_journalise_le_paiement(self, ctx, fee_type):
        payment = pay(ctx)
        log = AuditLog.objects.get(action_type="treasury.payment.validated")
        assert log.club_id == ctx.club.id
        assert log.actor_id == ctx.treasurer.user_id
        assert log.object_type == "Payment"
        assert log.object_id == str(payment.pk)
        assert log.after["amount"] == "5.00"
        assert log.after["transaction_sequence"] == 1
        assert log.after["transaction_hash"] == payment.transaction.hash
        # Jamais de PIN dans le journal (CLAUDE.md regle n6/n7).
        assert PIN not in str(log.after)

    def test_numeros_de_recu_continus_par_club(self, ctx, fee_type, other_ctx, other_fee_type):
        second_member = make_member(ctx.club, status=Membership.Status.PENDING)
        p1 = pay(ctx)
        p2 = pay(ctx, membership=second_member)
        p_other = pay(other_ctx)
        assert (p1.receipt_number, p2.receipt_number) == (1, 2)
        assert p_other.receipt_number == 1

    def test_joueur_deja_inscrit_peut_payer_ses_frais(self, ctx, fee_type):
        payment = pay(ctx, membership=ctx.player)
        assert payment.pk is not None

    @pytest.mark.parametrize("method", ["cash", "mobile_money", "payment_link"])
    def test_modes_de_paiement_de_la_modale(self, ctx, fee_type, method):
        assert pay(ctx, method=method).method == method


class TestPaiementPartielEtCumul:
    def test_paiement_partiel_ne_suffit_pas(self, ctx, fee_type):
        pay(ctx, amount="3")
        assert services.has_paid_membership_fee(ctx.pending_member) is False

    def test_deux_paiements_partiels_cumules_suffisent(self, ctx, fee_type):
        pay(ctx, amount="3")
        pay(ctx, amount="2")
        assert services.has_paid_membership_fee(ctx.pending_member) is True

    def test_sans_paiement(self, ctx, fee_type):
        assert services.has_paid_membership_fee(ctx.pending_member) is False

    def test_paiement_sur_un_autre_type_ne_compte_pas(self, ctx, fee_type):
        # Transaction reussie sur un type non « adhesion » : creee via la
        # primitive du grand livre (le chemin complet des autres types est
        # du Lot 2).
        monthly = ContributionTypeFactory(club=ctx.club, amount=Decimal("5.00"))
        other = Payment(
            club=ctx.club,
            membership=ctx.pending_member,
            contribution_type=monthly,
            amount=Decimal("5.00"),
            currency="USD",
            method=Payment.Method.CASH,
            paid_on=past_day(),
            source=Payment.Source.TREASURER_ENTRY,
            submitted_by=ctx.treasurer.user,
            submitted_at=timezone.now(),
            validated_by=ctx.treasurer.user,
            validated_at=timezone.now(),
        )
        other.save()
        txn = services.open_payment_transaction(payment=other, provider=Transaction.Provider.MANUAL)
        services.advance_transaction(transaction_obj=txn, status=Transaction.Status.SUCCEEDED)
        assert services.has_paid_membership_fee(ctx.pending_member) is False

    def test_frais_payes_sous_un_ancien_type_archive_restent_acquis(self, ctx, fee_type):
        pay(ctx)
        services.archive_contribution_type(contribution_type=fee_type, archived_by=ctx.president.user)
        assert services.has_paid_membership_fee(ctx.pending_member) is True


class TestRefus:
    def _assert_nothing_written(self):
        assert not Payment.all_objects.exists()
        assert not Transaction.all_objects.exists()

    def test_pin_incorrect_refuse_et_compteur_d_echecs_conserve(self, ctx, fee_type):
        with pytest.raises(InvalidPinError):
            pay(ctx, pin=WRONG_PIN)
        self._assert_nothing_written()
        ctx.treasurer.user.refresh_from_db()
        # L'echec PIN n'est pas annule par un rollback de transaction.
        assert ctx.treasurer.user.pin_failed_attempts == 1

    def test_pin_bloque_apres_trois_echecs(self, ctx, fee_type):
        for _ in range(2):
            with pytest.raises(InvalidPinError):
                pay(ctx, pin=WRONG_PIN)
        with pytest.raises(PinLockedError):
            pay(ctx, pin=WRONG_PIN)
        with pytest.raises(PinLockedError):
            pay(ctx, pin=PIN)
        self._assert_nothing_written()

    def test_pin_non_defini(self, ctx, fee_type):
        from apps.clubs.models import MembershipRole

        ctx.club.settings.board_seats_per_role = 2
        ctx.club.settings.save()
        no_pin = make_member(ctx.club, roles=[MembershipRole.Role.ASSISTANT_TREASURER], pin=None)
        with pytest.raises(PinNotSetError):
            pay(ctx, validated_by=no_pin)
        self._assert_nothing_written()

    @pytest.mark.parametrize("who", ["president", "vice_president", "player", "pending_member"])
    def test_seuls_tresorier_et_adjoint_valident_matrice_2_4(self, ctx, fee_type, who):
        with pytest.raises(services.TreasuryPermissionError):
            pay(ctx, validated_by=getattr(ctx, who))
        self._assert_nothing_written()

    def test_coach_ne_valide_jamais_un_paiement_matrice_2_4(self, ctx, fee_type):
        from apps.clubs.models import MembershipRole

        coach = make_member(ctx.club, roles=[MembershipRole.Role.COACH])
        with pytest.raises(services.TreasuryPermissionError):
            pay(ctx, validated_by=coach)
        self._assert_nothing_written()

    def test_cumul_de_roles_non_tresorier_toujours_refuse(self, ctx, fee_type):
        """CDC 2.2/2.4 : les droits d'un joueur sont l'union de ses roles ;
        cumuler deux roles hors tresorerie ne donne jamais le droit
        d'enregistrer un paiement."""

        from apps.clubs.models import MembershipRole

        coach_captain = make_member(
            ctx.club, roles=[MembershipRole.Role.COACH, MembershipRole.Role.CAPTAIN]
        )
        with pytest.raises(services.TreasuryPermissionError):
            pay(ctx, validated_by=coach_captain)
        self._assert_nothing_written()

    def test_cumul_de_roles_avec_tresorier_reste_autorise(self, ctx, fee_type):
        """L'union des droits (CDC 2.2) doit rester valable pour l'enregistrement
        d'un paiement quand le role Tresorier est cumule avec un autre role,
        sur la meme adhesion (le Tresorier de `ctx` est aussi nomme Coach)."""

        from apps.clubs.models import MembershipRole
        from apps.clubs.tests.factories import MembershipRoleFactory

        MembershipRoleFactory(
            membership=ctx.treasurer,
            club=ctx.club,
            role=MembershipRole.Role.COACH,
            appointed_at=timezone.now(),
        )
        payment = pay(ctx, validated_by=ctx.treasurer)
        assert payment.validated_by_id == ctx.treasurer.user_id

    def test_refus_role_avant_toute_verification_du_pin(self, ctx, fee_type):
        with pytest.raises(services.TreasuryPermissionError):
            pay(ctx, validated_by=ctx.player, pin=WRONG_PIN)
        ctx.player.user.refresh_from_db()
        assert ctx.player.user.pin_failed_attempts == 0

    def test_tresorier_d_un_autre_club_refuse(self, ctx, fee_type, other_ctx, other_fee_type):
        with pytest.raises(services.TreasuryPermissionError):
            pay(ctx, validated_by=other_ctx.treasurer)
        self._assert_nothing_written()

    def test_sans_type_adhesion_actif(self, ctx):
        with pytest.raises(services.TreasuryValidationError) as exc:
            pay(ctx)
        assert "adhésion" in str(exc.value).lower()

    def test_type_adhesion_archive_n_est_plus_propose(self, ctx, fee_type):
        services.archive_contribution_type(contribution_type=fee_type, archived_by=ctx.president.user)
        with pytest.raises(services.TreasuryValidationError):
            pay(ctx)

    def test_joueur_parti_refuse(self, ctx, fee_type):
        departed = make_member(ctx.club, status=Membership.Status.DEPARTED)
        departed.left_on = past_day()
        departed.left_reason = Membership.LeftReason.OTHER
        departed.save()
        with pytest.raises(services.TreasuryValidationError):
            pay(ctx, membership=departed)

    @pytest.mark.parametrize("amount", ["0", "-5", 5.0, "abc"])
    def test_montant_invalide(self, ctx, fee_type, amount):
        with pytest.raises(services.TreasuryError):
            pay(ctx, amount=amount)
        self._assert_nothing_written()

    def test_date_de_paiement_future_refusee(self, ctx, fee_type):
        with pytest.raises(services.TreasuryValidationError):
            pay(ctx, paid_on=timezone.now().date() + datetime.timedelta(days=3))

    def test_mode_carte_reserve_a_la_phase_2(self, ctx, fee_type):
        with pytest.raises(services.TreasuryValidationError):
            pay(ctx, method="card")

    def test_mode_inconnu(self, ctx, fee_type):
        with pytest.raises(services.TreasuryValidationError):
            pay(ctx, method="cheque")

    def test_club_gele_refuse_toute_ecriture(self, ctx, fee_type):
        services.freeze_ledger(club=ctx.club, reason="Rupture de chaine detectee (test)", actor=SuperuserFactory())
        with pytest.raises(services.LedgerFrozenError):
            pay(ctx)
        self._assert_nothing_written()
        # Aucun joueur n'est penalise : la lecture reste possible.
        assert services.has_paid_membership_fee(ctx.pending_member) is False

    def test_gel_du_club_a_n_affecte_jamais_les_ecritures_du_club_b(
        self, ctx, fee_type, other_ctx, other_fee_type
    ):
        """Etancheite (CLAUDE.md regle n8) : `LedgerChainState` est une ligne
        par club (schema-treasury.md §6.2) ; geler le club A ne doit jamais
        bloquer un paiement ou un remboursement du club B."""

        services.freeze_ledger(club=ctx.club, reason="Rupture de chaine detectee (test)", actor=SuperuserFactory())
        with pytest.raises(services.LedgerFrozenError):
            pay(ctx)

        payment = pay(other_ctx)
        assert payment.pk is not None
        assert services.has_paid_membership_fee(other_ctx.pending_member) is True

        reversals = services.refund_membership_fee(
            membership=other_ctx.pending_member,
            reason="Refus du parrain",
            president=other_ctx.president.user,
            pin=PIN,
        )
        assert len(reversals) == 1
        assert services.has_paid_membership_fee(other_ctx.pending_member) is False

    def test_cle_de_chainage_absente_refuse_l_ecriture(self, ctx, fee_type, settings):
        settings.LEDGER_HMAC_KEYS = {}
        with pytest.raises(services.LedgerKeyError):
            pay(ctx)
        self._assert_nothing_written()

    def test_cle_de_chainage_trop_courte_refusee(self, ctx, fee_type, settings):
        settings.LEDGER_HMAC_KEYS = {"test-v1": "court"}
        with pytest.raises(services.LedgerKeyError):
            pay(ctx)
        self._assert_nothing_written()

    def test_club_sans_parametres_refuse(self, fee_type, ctx):
        ctx.club.settings.delete()
        ctx.club.refresh_from_db()
        with pytest.raises(services.TreasuryValidationError):
            pay(ctx)


def test_etat_de_chaine_cree_a_la_premiere_ecriture(ctx, fee_type):
    assert not LedgerChainState.all_objects.filter(club=ctx.club).exists()
    payment = pay(ctx)
    state = LedgerChainState.all_objects.get(club=ctx.club)
    assert state.last_sequence == 1
    assert state.last_hash == payment.transaction.hash
    assert state.last_receipt_number == 1


class TestMontantSuperieurAuDu:
    """Point ouvert signale par `finance-engine` : le CDC ne tranche pas le
    sort d'un montant superieur aux frais d'adhesion (pas de plafond dans
    `record_membership_fee_payment`). On verifie ici seulement l'absence de
    plantage et la coherence du calcul -- **comportement observe, pas
    corrige** (a trancher par le client, circuit 9.4)."""

    def test_montant_superieur_au_du_accepte_sans_plafond(self, ctx, fee_type):
        payment = pay(ctx, amount="50")
        assert payment.amount == Decimal("50.00")
        assert services.has_paid_membership_fee(ctx.pending_member) is True
        assert services.verify_chain(ctx.club).ok is True


class TestGarantiesPin:
    """Le PIN est verifie a nouveau a **chaque** appel (CDC 7.2) : aucun etat
    de verification ne doit pouvoir « fuiter » d'un paiement au suivant."""

    def test_pin_est_un_parametre_obligatoire_de_chaque_appel(self, ctx, fee_type):
        # Garantie structurelle : `pin` n'a pas de valeur par defaut dans la
        # signature du service, donc aucun appel ne peut « omettre » le PIN
        # pour reutiliser implicitement une verification precedente.
        import inspect

        signature = inspect.signature(services.record_membership_fee_payment)
        assert signature.parameters["pin"].default is inspect.Parameter.empty

    def test_reussite_d_un_premier_paiement_ne_dispense_pas_le_pin_du_second(self, ctx, fee_type):
        first = pay(ctx, amount="2")
        assert first.pk is not None
        # Un deuxieme paiement avec un mauvais PIN echoue independamment du
        # premier paiement reussi : aucune verification n'est memorisee.
        with pytest.raises(InvalidPinError):
            pay(ctx, amount="3", pin=WRONG_PIN)
        assert services.has_paid_membership_fee(ctx.pending_member) is False
        ctx.treasurer.user.refresh_from_db()
        assert ctx.treasurer.user.pin_failed_attempts == 1
        # Avec le bon PIN, le second paiement passe normalement.
        second = pay(ctx, amount="3")
        assert second.pk is not None
        assert services.has_paid_membership_fee(ctx.pending_member) is True
