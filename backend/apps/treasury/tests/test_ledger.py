"""Grand livre chaine (CDC 4.6, 5.3 ; schema-treasury.md §6 ; invariants 5, 6, 11).

La commande cron de verification quotidienne et l'alerte Superuser sont
hors perimetre de la tache 1.4b : on teste ici la fonction de service
reutilisable `verify_chain` qu'elles appelleront.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone

from apps.treasury import services
from apps.treasury.models import (
    LedgerChainState,
    LedgerImmutableError,
    Payment,
    Transaction,
)
from apps.treasury.tests.conftest import PIN, make_member, past_day
from apps.clubs.models import Membership

from apps.accounts.tests.factories import SuperuserFactory  # noqa: E402

pytestmark = pytest.mark.django_db


def pay(ctx, membership=None, amount="5"):
    return services.record_membership_fee_payment(
        membership=membership or make_member(ctx.club, status=Membership.Status.PENDING),
        amount=amount,
        method="cash",
        paid_on=past_day(),
        validated_by=ctx.treasurer.user,
        pin=PIN,
    )


def raw_sql(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


TABLE = Transaction._meta.db_table
PAYMENT_TABLE = Payment._meta.db_table

# Cles du format canonique v1 (format d'origine, fige a jamais).
V1_KEYS = {
    "club", "sequence", "kind", "payment", "reversal", "expense", "membership",
    "contribution_type", "amount", "currency", "value_date", "provider",
    "external_ref", "status", "sealed_at", "key_id",
}


class TestChainage:
    def test_premiere_ligne_chainee_sur_la_genese_puis_chaque_ligne_sur_la_precedente(self, ctx, fee_type):
        t1 = pay(ctx).transaction
        t2 = pay(ctx).transaction
        t3 = pay(ctx).transaction

        assert services.LEDGER_GENESIS_HASH == "0" * 64
        assert [t.sequence for t in (t1, t2, t3)] == [1, 2, 3]
        assert t1.previous_hash == services.LEDGER_GENESIS_HASH
        assert t2.previous_hash == t1.hash
        assert t3.previous_hash == t2.hash
        assert len({t1.hash, t2.hash, t3.hash}) == 3

    def test_chaines_independantes_par_club(self, ctx, fee_type, other_ctx, other_fee_type):
        a1 = pay(ctx).transaction
        b1 = pay(other_ctx).transaction
        a2 = pay(ctx).transaction
        assert (a1.sequence, a2.sequence, b1.sequence) == (1, 2, 1)
        assert b1.previous_hash == services.LEDGER_GENESIS_HASH
        assert a2.previous_hash == a1.hash

    def test_empreinte_hmac_sha256_du_contenu_canonique_et_de_l_empreinte_precedente(self, ctx, fee_type, settings):
        # Format v2 (audit securite A2) : le format v1 d'origine, plus la
        # version et les champs du paiement lie. Le format v1 lui-meme reste
        # verifie par TestFormatVersionne.
        txn = pay(ctx).transaction
        assert txn.payload_version == services.LEDGER_PAYLOAD_VERSION == 2
        payload = services.transaction_canonical_payload(txn)

        expected_keys = V1_KEYS | {
            "v", "payment_method", "payment_reference", "payment_source",
            "payment_receipt_number", "payment_validated_by", "payment_attachment",
        }
        assert set(json.loads(payload)) == expected_keys
        assert json.loads(payload)["v"] == 2
        assert json.loads(payload)["payment_receipt_number"] == txn.payment.receipt_number
        assert json.loads(payload)["payment_validated_by"] == ctx.treasurer.user.pk
        # Aucune donnee personnelle, uniquement des identifiants.
        assert ctx.treasurer.user.email not in payload
        assert json.loads(payload)["amount"] == "5.00"

        key = settings.LEDGER_HMAC_KEYS["test-v1"].encode()
        expected = hmac.new(key, (payload + txn.previous_hash).encode(), hashlib.sha256).hexdigest()
        assert txn.hash == expected

    def test_cle_absente_de_la_base(self, ctx, fee_type, settings):
        txn = pay(ctx).transaction
        secret = settings.LEDGER_HMAC_KEYS["test-v1"]
        for field in Transaction._meta.concrete_fields:
            assert secret not in str(getattr(txn, field.attname))
        assert txn.key_id == "test-v1"


class TestCleDeChainageMalFormee:
    """CLAUDE.md regle n12 ; schema-treasury.md §6.4 : aucune ecriture ne
    doit passer si la cle de l'environnement est absente ou visiblement un
    reglage par defaut oublie (« changeme... ») ou trop courte."""

    @pytest.mark.parametrize(
        "key",
        [
            "changeme-cle-non-configuree-en-production-000",
            "CHANGEME-CLE-NON-CONFIGUREE-EN-PRODUCTION-000",
            "ChangeMe" + "x" * 40,
        ],
    )
    def test_cle_changeme_refusee_quelle_que_soit_la_casse(self, ctx, fee_type, settings, key):
        assert len(key) >= services.MIN_LEDGER_KEY_LENGTH
        settings.LEDGER_HMAC_KEYS = {"test-v1": key}
        with pytest.raises(services.LedgerKeyError):
            pay(ctx)
        assert not Payment.all_objects.exists()
        assert not Transaction.all_objects.exists()

    def test_identifiant_de_cle_active_absent_refuse(self, ctx, fee_type, settings):
        settings.LEDGER_HMAC_ACTIVE_KEY_ID = ""
        with pytest.raises(services.LedgerKeyError):
            pay(ctx)
        assert not Payment.all_objects.exists()

    def test_identifiant_de_cle_active_sans_entree_correspondante_refuse(self, ctx, fee_type, settings):
        # `LEDGER_HMAC_ACTIVE_KEY_ID` pointe vers une cle qui n'existe pas
        # dans `LEDGER_HMAC_KEYS` : erreur claire, pas de `KeyError` Python.
        settings.LEDGER_HMAC_ACTIVE_KEY_ID = "inconnue"
        with pytest.raises(services.LedgerKeyError):
            pay(ctx)
        assert not Payment.all_objects.exists()


class TestVerification:
    def test_chaine_intacte(self, ctx, fee_type):
        for _ in range(3):
            pay(ctx)
        result = services.verify_chain(ctx.club)
        assert result.ok is True
        assert result.checked_count == 3
        assert result.first_broken_sequence is None

    def test_chaine_vide_est_intacte(self, ctx):
        result = services.verify_chain(ctx.club)
        assert result.ok is True
        assert result.checked_count == 0

    def test_montant_modifie_directement_en_base_detecte(self, ctx, fee_type):
        pay(ctx)
        t2 = pay(ctx).transaction
        pay(ctx)
        raw_sql(f"UPDATE {TABLE} SET amount = %s WHERE id = %s", ["500.00", t2.pk])

        result = services.verify_chain(ctx.club)
        assert result.ok is False
        assert result.first_broken_sequence == 2
        assert result.details

    def test_empreinte_recalculee_par_un_fraudeur_sans_la_cle_casse_la_ligne_suivante(self, ctx, fee_type):
        t1 = pay(ctx).transaction
        pay(ctx)
        # Le fraudeur remplace l'empreinte de la ligne 1 : la ligne 2 ne
        # pointe plus sur elle.
        raw_sql(f"UPDATE {TABLE} SET hash = %s WHERE id = %s", ["f" * 64, t1.pk])
        result = services.verify_chain(ctx.club)
        assert result.ok is False
        assert result.first_broken_sequence == 1

    def test_suppression_d_une_ligne_intermediaire_detectee(self, ctx, fee_type):
        pay(ctx)
        t2 = pay(ctx).transaction
        pay(ctx)
        raw_sql(f"DELETE FROM {TABLE} WHERE id = %s", [t2.pk])
        result = services.verify_chain(ctx.club)
        assert result.ok is False
        assert result.first_broken_sequence == 2

    def test_suppression_de_la_derniere_ligne_detectee_par_la_tete_de_chaine(self, ctx, fee_type):
        pay(ctx)
        t2 = pay(ctx).transaction
        raw_sql(f"DELETE FROM {TABLE} WHERE id = %s", [t2.pk])
        result = services.verify_chain(ctx.club)
        assert result.ok is False
        assert result.first_broken_sequence == 2

    def test_statut_reussi_sans_scellement_refuse_par_la_base(self, ctx, fee_type):
        """Contrainte CHECK `transaction_sealed_iff_terminal` : la base elle-meme
        refuse une transaction « reussie » depouillee de son scellement.
        `verify_chain` controle aussi ce cas (moteurs sans CHECK effectif)."""

        from django.db import IntegrityError, transaction

        txn = pay(ctx).transaction
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                raw_sql(
                    f"UPDATE {TABLE} SET sequence = NULL, hash = NULL, previous_hash = NULL, "
                    "sealed_at = NULL, key_id = '' WHERE id = %s",
                    [txn.pk],
                )
        assert services.verify_chain(ctx.club).ok is True

    def test_ancienne_cle_conservee_permet_la_verification_apres_rotation(self, ctx, fee_type, settings):
        pay(ctx)
        settings.LEDGER_HMAC_KEYS = {
            "test-v1": settings.LEDGER_HMAC_KEYS["test-v1"],
            "test-v2": "nouvelle-cle-factice-de-test-" + "1" * 40,
        }
        settings.LEDGER_HMAC_ACTIVE_KEY_ID = "test-v2"
        t2 = pay(ctx).transaction
        assert t2.key_id == "test-v2"
        assert services.verify_chain(ctx.club).ok is True

    def test_cle_retiree_rend_la_verification_impossible(self, ctx, fee_type, settings):
        pay(ctx)
        settings.LEDGER_HMAC_KEYS = {"autre": "x" * 64}
        settings.LEDGER_HMAC_ACTIVE_KEY_ID = "autre"
        result = services.verify_chain(ctx.club)
        assert result.ok is False
        assert result.first_broken_sequence == 1
        # Audit securite A1 : une cle valide existe, la ligne porte un
        # `key_id` inconnu -> rupture (les anciennes cles ne sont jamais
        # retirees), et non simple « cle indisponible » sans gel.
        assert result.key_unavailable is False

    def test_mauvaise_cle_detectee(self, ctx, fee_type, settings):
        pay(ctx)
        settings.LEDGER_HMAC_KEYS = {"test-v1": "une-autre-valeur-de-cle-" + "9" * 40}
        assert services.verify_chain(ctx.club).ok is False

    def test_la_verification_ne_modifie_rien_et_ne_penalise_aucun_joueur(self, ctx, fee_type):
        member = make_member(ctx.club, status=Membership.Status.PENDING)
        t1 = pay(ctx, membership=member).transaction
        raw_sql(f"UPDATE {TABLE} SET amount = %s WHERE id = %s", ["1.00", t1.pk])
        services.verify_chain(ctx.club)
        member.refresh_from_db()
        assert member.status == Membership.Status.PENDING
        assert Transaction.all_objects.count() == 1

    def test_rupture_dans_le_club_a_n_affecte_jamais_la_verification_du_club_b(
        self, ctx, fee_type, other_ctx, other_fee_type
    ):
        """Etancheite (CLAUDE.md regle n8) appliquee a `verify_chain` : la
        chaine est propre a chaque club (schema-treasury.md §6.1), donc une
        fraude cote club A ne doit jamais rendre le club B « broken »."""

        pay(ctx)
        t_a2 = pay(ctx).transaction
        t_b1 = pay(other_ctx).transaction
        pay(other_ctx)

        raw_sql(f"UPDATE {TABLE} SET amount = %s WHERE id = %s", ["999.00", t_a2.pk])

        result_a = services.verify_chain(ctx.club)
        assert result_a.ok is False
        assert result_a.first_broken_sequence == 2

        result_b = services.verify_chain(other_ctx.club)
        assert result_b.ok is True
        assert result_b.checked_count == 2
        assert result_b.first_broken_sequence is None
        # Le fraudeur n'a pas touche a la ligne 1 du club B.
        assert t_b1.hash == Transaction.all_objects.get(pk=t_b1.pk).hash


class TestImmuabilite:
    def test_transaction_scellee_ne_peut_etre_modifiee(self, ctx, fee_type):
        txn = pay(ctx).transaction
        txn.amount = Decimal("50.00")
        with pytest.raises(LedgerImmutableError):
            txn.save()

    def test_transaction_scellee_ne_peut_etre_supprimee(self, ctx, fee_type):
        txn = pay(ctx).transaction
        with pytest.raises(LedgerImmutableError):
            txn.delete()

    def test_update_et_delete_en_masse_bloques(self, ctx, fee_type):
        pay(ctx)
        with pytest.raises(LedgerImmutableError):
            Transaction.all_objects.all().update(amount=Decimal("1.00"))
        with pytest.raises(LedgerImmutableError):
            Transaction.all_objects.all().delete()
        with pytest.raises(LedgerImmutableError):
            Payment.all_objects.all().update(amount=Decimal("1.00"))
        with pytest.raises(LedgerImmutableError):
            Payment.all_objects.all().delete()

    def test_invariant_5_paiement_valide_jamais_supprime(self, ctx, fee_type):
        payment = pay(ctx)
        with pytest.raises(LedgerImmutableError):
            payment.delete()

    @pytest.mark.parametrize(
        "field, value",
        [
            ("amount", Decimal("50.00")),
            ("reference", "autre"),
            ("method", Payment.Method.MOBILE_MONEY),
            ("currency", "CDF"),
        ],
    )
    def test_invariant_5_champs_financiers_d_un_paiement_valide_non_modifiables(self, ctx, fee_type, field, value):
        payment = pay(ctx)
        setattr(payment, field, value)
        with pytest.raises(LedgerImmutableError):
            payment.save()

    def test_seuls_les_champs_du_recu_restent_completables(self, ctx, fee_type):
        payment = pay(ctx)
        payment.receipt_issued_at = timezone.now()
        payment.save()
        payment.refresh_from_db()
        assert payment.receipt_issued_at is not None


class TestCycleDeVie:
    """Transactions non encore scellees (declaration « J'ai paye », passerelle
    FlexPaie : Lot 2). Seule la primitive du grand livre est exercee ici."""

    def _declared_payment(self, ctx, fee_type, **extra):
        payment = Payment(
            club=ctx.club,
            membership=ctx.pending_member,
            contribution_type=fee_type,
            amount=Decimal("5.00"),
            currency="USD",
            method=Payment.Method.PAYMENT_LINK,
            paid_on=past_day(),
            source=Payment.Source.PLAYER_DECLARATION,
            submitted_by=ctx.pending_member.user,
            submitted_at=timezone.now(),
            **extra,
        )
        payment.save()
        return payment

    def test_transaction_en_attente_non_scellee_et_hors_calcul(self, ctx, fee_type):
        payment = self._declared_payment(ctx, fee_type)
        txn = services.open_payment_transaction(
            payment=payment, provider=Transaction.Provider.LINK, external_ref="LAX-1"
        )
        assert txn.status == Transaction.Status.PENDING
        assert txn.sequence is None and txn.hash is None and txn.sealed_at is None
        assert services.has_paid_membership_fee(ctx.pending_member) is False
        assert services.verify_chain(ctx.club).ok is True

    def test_scellement_au_passage_a_reussi(self, ctx, fee_type):
        payment = self._declared_payment(ctx, fee_type)
        txn = services.open_payment_transaction(payment=payment, provider=Transaction.Provider.LINK)
        payment.validated_by = ctx.treasurer.user
        payment.validated_at = timezone.now()
        payment.save()

        services.advance_transaction(transaction_obj=txn, status=Transaction.Status.SUCCEEDED)
        txn.refresh_from_db()
        assert txn.sequence == 1
        assert txn.previous_hash == services.LEDGER_GENESIS_HASH
        assert services.has_paid_membership_fee(ctx.pending_member) is True
        assert services.verify_chain(ctx.club).ok is True

    def test_scellement_au_passage_a_echoue_sans_effet_sur_les_frais(self, ctx, fee_type):
        payment = self._declared_payment(ctx, fee_type)
        txn = services.open_payment_transaction(payment=payment, provider=Transaction.Provider.LINK)
        services.advance_transaction(transaction_obj=txn, status=Transaction.Status.FAILED)
        txn.refresh_from_db()
        assert txn.sequence == 1
        assert txn.hash
        assert services.has_paid_membership_fee(ctx.pending_member) is False
        assert services.verify_chain(ctx.club).ok is True

    def test_reussite_exige_un_valideur_hors_passerelle(self, ctx, fee_type):
        payment = self._declared_payment(ctx, fee_type)
        txn = services.open_payment_transaction(payment=payment, provider=Transaction.Provider.LINK)
        with pytest.raises(services.TreasuryValidationError):
            services.advance_transaction(transaction_obj=txn, status=Transaction.Status.SUCCEEDED)

    @pytest.mark.parametrize(
        "start, target",
        [
            ("pending", "initiated"),
            ("pending", "pending"),
        ],
    )
    def test_transitions_interdites(self, ctx, fee_type, start, target):
        payment = self._declared_payment(ctx, fee_type)
        txn = services.open_payment_transaction(payment=payment, provider=Transaction.Provider.LINK, status=start)
        with pytest.raises(services.TreasuryValidationError):
            services.advance_transaction(transaction_obj=txn, status=target)

    def test_aucune_transition_apres_scellement(self, ctx, fee_type):
        txn = pay(ctx).transaction
        with pytest.raises((services.TreasuryValidationError, LedgerImmutableError)):
            services.advance_transaction(transaction_obj=txn, status=Transaction.Status.FAILED)

    def test_initie_puis_en_attente_puis_reussi(self, ctx, fee_type):
        payment = self._declared_payment(
            ctx, fee_type, validated_by=ctx.treasurer.user, validated_at=timezone.now()
        )
        txn = services.open_payment_transaction(
            payment=payment, provider=Transaction.Provider.LINK, status=Transaction.Status.INITIATED
        )
        services.advance_transaction(transaction_obj=txn, status=Transaction.Status.PENDING, external_ref="LAX-9")
        txn.refresh_from_db()
        assert txn.status == Transaction.Status.PENDING and txn.external_ref == "LAX-9"
        services.advance_transaction(transaction_obj=txn, status=Transaction.Status.SUCCEEDED)
        txn.refresh_from_db()
        assert txn.hash and txn.external_ref == "LAX-9"

    def test_reference_externe_unique_par_club_et_fournisseur(self, ctx, fee_type):
        p1 = self._declared_payment(ctx, fee_type)
        p2 = self._declared_payment(ctx, fee_type)
        services.open_payment_transaction(payment=p1, provider=Transaction.Provider.LINK, external_ref="LAX-1")
        with pytest.raises(services.TreasuryValidationError):
            services.open_payment_transaction(payment=p2, provider=Transaction.Provider.LINK, external_ref="LAX-1")

    def test_une_seule_transaction_par_paiement(self, ctx, fee_type):
        payment = pay(ctx)
        with pytest.raises(services.TreasuryValidationError):
            services.open_payment_transaction(payment=payment, provider=Transaction.Provider.MANUAL)

    def test_gel_bloque_le_scellement_d_une_transaction_en_attente(self, ctx, fee_type):
        payment = self._declared_payment(
            ctx, fee_type, validated_by=ctx.treasurer.user, validated_at=timezone.now()
        )
        txn = services.open_payment_transaction(payment=payment, provider=Transaction.Provider.LINK)
        services.freeze_ledger(club=ctx.club, reason="Analyse en cours", actor=SuperuserFactory())
        with pytest.raises(services.LedgerFrozenError):
            services.advance_transaction(transaction_obj=txn, status=Transaction.Status.SUCCEEDED)
        txn.refresh_from_db()
        assert txn.status == Transaction.Status.PENDING
        assert LedgerChainState.all_objects.get(club=ctx.club).is_frozen is True
