"""Types de cotisation (CDC 4.4.1 ; schema-treasury.md §4.1 ; invariant 7 ; D6)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.audit.models import AuditLog
from apps.core.tenant import active_club
from apps.treasury import services
from apps.treasury.models import ContributionType, ContributionTypeRate
from apps.treasury.tests.conftest import PIN, past_day
from apps.treasury.tests.factories import ContributionTypeFactory, MembershipFeeTypeFactory

pytestmark = pytest.mark.django_db


def _create_fee_type(ctx, actor=None, **overrides):
    kwargs = dict(
        club=ctx.club,
        created_by=(actor or ctx.president).user,
        name="Adhesion",
        nature=ContributionType.Nature.MANDATORY,
        periodicity=ContributionType.Periodicity.ONE_OFF,
        amount="5",
        is_membership_fee=True,
    )
    kwargs.update(overrides)
    return services.create_contribution_type(**kwargs)


class TestCreation:
    def test_president_cree_le_type_adhesion_et_journalise(self, ctx):
        ctype = _create_fee_type(ctx)

        assert ctype.club_id == ctx.club.id
        assert ctype.amount == Decimal("5.00")
        assert ctype.is_membership_fee is True
        assert ctype.status == ContributionType.Status.ACTIVE
        assert ctype.created_by_id == ctx.president.user_id
        log = AuditLog.objects.get(action_type="treasury.contribution_type.created")
        assert log.club_id == ctx.club.id
        assert log.actor_id == ctx.president.user_id
        assert log.object_id == str(ctype.pk)
        assert log.after["amount"] == "5.00"

    def test_tresorier_peut_creer_un_type(self, ctx):
        ctype = _create_fee_type(ctx, actor=ctx.treasurer)
        assert ctype.pk is not None

    def test_creation_obligatoire_enregistre_le_tarif_du_mois_courant(self, ctx):
        created_at = datetime.datetime(2026, 9, 27, 12, tzinfo=datetime.timezone.utc)
        ctype = _create_fee_type(ctx, now=created_at)

        rate = ContributionTypeRate.all_objects.get(contribution_type=ctype)
        assert rate.club_id == ctx.club.id
        assert rate.amount == Decimal("5.00")
        assert rate.effective_from == datetime.date(2026, 9, 1)
        assert rate.created_by_id == ctx.president.user_id
        assert rate.created_at == created_at

    def test_creation_utilise_le_mois_local_du_club(self, ctx):
        created_at = datetime.datetime(2026, 8, 31, 23, 30, tzinfo=datetime.timezone.utc)
        ctype = _create_fee_type(ctx, now=created_at)

        rate = ContributionTypeRate.all_objects.get(contribution_type=ctype)
        assert rate.effective_from == datetime.date(2026, 9, 1)

    @pytest.mark.parametrize("who", ["assistant_treasurer", "vice_president", "player"])
    def test_autres_roles_refuses_matrice_2_4(self, ctx, who):
        with pytest.raises(services.TreasuryPermissionError):
            _create_fee_type(ctx, actor=getattr(ctx, who))
        assert not ContributionType.all_objects.exists()

    def test_joueur_d_un_autre_club_refuse(self, ctx, other_ctx):
        with pytest.raises(services.TreasuryPermissionError):
            _create_fee_type(ctx, actor=other_ctx.president)

    def test_un_seul_type_adhesion_actif_par_club(self, ctx, other_ctx):
        _create_fee_type(ctx)
        with pytest.raises(services.TreasuryValidationError):
            _create_fee_type(ctx, name="Adhesion bis")
        # Un autre club garde son propre type adhesion.
        _create_fee_type(other_ctx)

    def test_nom_unique_par_club(self, ctx):
        monthly = dict(is_membership_fee=False, name="Mensuelle 20", periodicity=ContributionType.Periodicity.MONTHLY)
        _create_fee_type(ctx, **monthly)
        with pytest.raises(services.TreasuryValidationError):
            _create_fee_type(ctx, **monthly)

    def test_type_obligatoire_exige_un_montant_strictement_positif(self, ctx):
        with pytest.raises(services.TreasuryValidationError):
            _create_fee_type(ctx, amount="0")
        with pytest.raises(services.TreasuryValidationError):
            _create_fee_type(ctx, amount=None)

    def test_type_adhesion_exige_un_montant_fixe_meme_si_libre(self, ctx):
        with pytest.raises(services.TreasuryValidationError):
            _create_fee_type(ctx, nature=ContributionType.Nature.FREE, amount=None)

    def test_type_libre_sans_montant_accepte(self, ctx):
        ctype = _create_fee_type(
            ctx,
            is_membership_fee=False,
            name="Vestiaire",
            nature=ContributionType.Nature.FREE,
            amount=None,
            periodicity=ContributionType.Periodicity.MONTHLY,
        )
        assert ctype.amount is None

    def test_montant_float_refuse(self, ctx):
        with pytest.raises(services.InvalidAmountError):
            _create_fee_type(ctx, amount=5.0)


    def test_nature_ne_peut_plus_etre_modifiee_apres_un_paiement(self, ctx):
        ctype = _create_fee_type(ctx)
        services.record_membership_fee_payment(
            membership=ctx.pending_member,
            amount="5",
            method="cash",
            paid_on=past_day(),
            validated_by=ctx.treasurer.user,
            pin=PIN,
        )

        with pytest.raises(services.TreasuryValidationError, match="nature.*modifiée après un paiement"):
            services.update_contribution_type(
                contribution_type=ctype,
                updated_by=ctx.president.user,
                nature=ContributionType.Nature.FREE,
            )

        ctype.refresh_from_db()
        assert ctype.nature == ContributionType.Nature.MANDATORY
    def test_mensuelle_echeance_par_defaut_le_10_et_bornee_1_28(self, ctx):
        base = dict(is_membership_fee=False, periodicity=ContributionType.Periodicity.MONTHLY)
        with pytest.raises(services.TreasuryValidationError):
            _create_fee_type(ctx, **base, name="Mensuelle 31", due_day=31)
        # 10.2 n° 4 : echeance le 10 par defaut.
        assert _create_fee_type(ctx, **base, name="Mensuelle defaut").due_day == 10
        assert _create_fee_type(ctx, **base, name="Mensuelle 5", due_day=5).due_day == 5

    def test_ponctuelle_hors_adhesion_exige_une_date_limite(self, ctx):
        base = dict(is_membership_fee=False, name="Speciale", nature=ContributionType.Nature.FREE, amount=None)
        with pytest.raises(services.TreasuryValidationError):
            _create_fee_type(ctx, **base)
        ctype = _create_fee_type(ctx, **base, deadline=datetime.date(2026, 12, 31))
        assert ctype.deadline == datetime.date(2026, 12, 31)

    def test_annuelle_exige_le_mois_d_echeance(self, ctx):
        base = dict(is_membership_fee=False, name="Annuelle", periodicity=ContributionType.Periodicity.ANNUAL)
        with pytest.raises(services.TreasuryValidationError):
            _create_fee_type(ctx, **base, due_day=10)
        assert _create_fee_type(ctx, **base, due_month=1).due_month == 1


class TestArchivageEtSuppression:
    def test_archivage_journalise_et_retire_le_type_des_types_actifs(self, ctx):
        ctype = _create_fee_type(ctx)
        services.archive_contribution_type(contribution_type=ctype, archived_by=ctx.treasurer.user)

        ctype.refresh_from_db()
        assert ctype.status == ContributionType.Status.ARCHIVED
        assert ctype.archived_by_id == ctx.treasurer.user_id
        assert ctype.archived_at is not None
        assert services.get_active_membership_fee_type(ctx.club) is None
        assert AuditLog.objects.filter(action_type="treasury.contribution_type.archived").count() == 1

    def test_archivage_libere_la_place_d_un_nouveau_type_adhesion(self, ctx):
        old = _create_fee_type(ctx)
        services.archive_contribution_type(contribution_type=old, archived_by=ctx.president.user)
        new = _create_fee_type(ctx, name="Adhesion 2027", amount="7")
        assert services.get_active_membership_fee_type(ctx.club) == new

    def test_archivage_reserve_president_et_tresorier(self, ctx):
        ctype = _create_fee_type(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            services.archive_contribution_type(contribution_type=ctype, archived_by=ctx.assistant_treasurer.user)

    def test_suppression_d_un_type_jamais_utilise_est_permise_et_journalisee(self, ctx):
        ctype = _create_fee_type(ctx)
        pk = ctype.pk
        with active_club(ctx.club):
            services.delete_contribution_type(contribution_type=ctype, deleted_by=ctx.president.user)
        assert not ContributionType.all_objects.filter(pk=pk).exists()
        log = AuditLog.objects.get(action_type="treasury.contribution_type.deleted")
        assert log.before["name"] == "Adhesion"

    def test_suppression_type_inutilise_supprime_tous_ses_tarifs(self, ctx):
        ctype = _create_fee_type(ctx, now=datetime.datetime(2026, 8, 15, tzinfo=datetime.timezone.utc))
        contribution_type_id = ctype.pk
        services.update_contribution_type(
            contribution_type=ctype,
            updated_by=ctx.treasurer.user,
            now=datetime.datetime(2026, 9, 10, tzinfo=datetime.timezone.utc),
            amount="7",
        )
        services.update_contribution_type(
            contribution_type=ctype,
            updated_by=ctx.treasurer.user,
            now=datetime.datetime(2026, 10, 10, tzinfo=datetime.timezone.utc),
            amount="8",
        )

        with active_club(ctx.club):
            services.delete_contribution_type(contribution_type=ctype, deleted_by=ctx.president.user)

        assert not ContributionTypeRate.all_objects.filter(
            contribution_type_id=contribution_type_id
        ).exists()

    def test_invariant_7_type_ayant_recu_un_paiement_ne_peut_qu_etre_archive(self, ctx):
        ctype = _create_fee_type(ctx)
        services.record_membership_fee_payment(
            membership=ctx.pending_member,
            amount="5",
            method="cash",
            paid_on=past_day(),
            validated_by=ctx.treasurer.user,
            pin=PIN,
        )
        with active_club(ctx.club):
            with pytest.raises(services.TreasuryValidationError) as exc:
                services.delete_contribution_type(contribution_type=ctype, deleted_by=ctx.president.user)
        assert "archiv" in str(exc.value)
        assert ContributionType.all_objects.filter(pk=ctype.pk).exists()
        # L'archivage reste possible.
        services.archive_contribution_type(contribution_type=ctype, archived_by=ctx.president.user)

    def test_suppression_refusee_sans_club_actif(self, ctx):
        ctype = _create_fee_type(ctx)

        with pytest.raises(services.TreasuryValidationError, match="Aucun club actif"):
            services.delete_contribution_type(contribution_type=ctype, deleted_by=ctx.president.user)

        assert ContributionType.all_objects.filter(pk=ctype.pk).exists()


class TestHistoriqueTarifs:
    def test_migration_reconstruit_le_tarif_initial_des_types_existants(self, ctx):
        from importlib import import_module
        from types import SimpleNamespace

        from django.apps import apps as django_apps
        from django.db import connection

        created_at = datetime.datetime(2026, 8, 31, 23, 30, tzinfo=datetime.timezone.utc)
        ctype = _create_fee_type(ctx, now=created_at)
        ContributionTypeRate.all_objects.filter(contribution_type=ctype).delete()

        migration = import_module("apps.treasury.migrations.0002_contributiontyperate")
        migration.backfill_initial_rates(django_apps, SimpleNamespace(connection=connection))

        rate = ContributionTypeRate.all_objects.get(contribution_type=ctype)
        assert rate.amount == Decimal("5.00")
        assert rate.effective_from == datetime.date(2026, 9, 1)
        assert rate.created_at == created_at
        assert rate.created_by_id == ctx.president.user_id

    def test_migration_refuse_un_rollback_qui_perdrait_l_historique(self, ctx):
        from importlib import import_module
        from types import SimpleNamespace

        from django.apps import apps as django_apps
        from django.db import connection
        from django.db.migrations.exceptions import IrreversibleError

        _create_fee_type(ctx)
        migration = import_module("apps.treasury.migrations.0002_contributiontyperate")

        with pytest.raises(IrreversibleError, match="historique des tarifs"):
            migration.refuse_lossy_reverse(django_apps, SimpleNamespace(connection=connection))

    def test_changement_cree_tarif_du_mois_suivant_sans_modifier_l_ancien(self, ctx):
        ctype = _create_fee_type(ctx, now=datetime.datetime(2026, 8, 15, tzinfo=datetime.timezone.utc))
        updated_at = datetime.datetime(2026, 9, 27, 12, tzinfo=datetime.timezone.utc)

        services.update_contribution_type(
            contribution_type=ctype, updated_by=ctx.treasurer.user, now=updated_at, amount="7.50"
        )

        rates = list(
            ContributionTypeRate.all_objects.filter(contribution_type=ctype).order_by("effective_from")
        )
        assert [(rate.amount, rate.effective_from) for rate in rates] == [
            (Decimal("5.00"), datetime.date(2026, 8, 1)),
            (Decimal("7.50"), datetime.date(2026, 10, 1)),
        ]
        assert rates[1].created_by_id == ctx.treasurer.user_id
        assert rates[1].created_at == updated_at
        assert ctype.amount == Decimal("7.50")
        assert AuditLog.objects.filter(action_type="treasury.contribution_type.updated").count() == 1

    def test_changements_repetes_dans_le_meme_mois_remplacent_le_tarif_futur(self, ctx):
        ctype = _create_fee_type(ctx, now=datetime.datetime(2026, 8, 15, tzinfo=datetime.timezone.utc))
        first_change = datetime.datetime(2026, 9, 10, 12, tzinfo=datetime.timezone.utc)
        second_change = datetime.datetime(2026, 9, 27, 12, tzinfo=datetime.timezone.utc)

        services.update_contribution_type(
            contribution_type=ctype, updated_by=ctx.treasurer.user, now=first_change, amount="7"
        )
        services.update_contribution_type(
            contribution_type=ctype, updated_by=ctx.president.user, now=second_change, amount="8"
        )

        future_rate = ContributionTypeRate.all_objects.get(
            contribution_type=ctype, effective_from=datetime.date(2026, 10, 1)
        )
        assert future_rate.amount == Decimal("8.00")
        assert future_rate.created_by_id == ctx.president.user_id
        assert future_rate.created_at == second_change
        assert ContributionTypeRate.all_objects.filter(contribution_type=ctype).count() == 2

    def test_changement_utilise_le_mois_local_du_club(self, ctx):
        ctype = _create_fee_type(ctx, now=datetime.datetime(2026, 8, 15, tzinfo=datetime.timezone.utc))
        updated_at = datetime.datetime(2026, 9, 30, 23, 30, tzinfo=datetime.timezone.utc)

        services.update_contribution_type(
            contribution_type=ctype, updated_by=ctx.treasurer.user, now=updated_at, amount="7.50"
        )

        future_rate = ContributionTypeRate.all_objects.get(
            contribution_type=ctype, effective_from=datetime.date(2026, 11, 1)
        )
        assert future_rate.amount == Decimal("7.50")

    def test_meme_montant_ne_cree_pas_de_tarif_et_les_autres_champs_restent_modifiables(self, ctx):
        ctype = _create_fee_type(ctx, now=datetime.datetime(2026, 8, 15, tzinfo=datetime.timezone.utc))

        services.update_contribution_type(
            contribution_type=ctype,
            updated_by=ctx.treasurer.user,
            now=datetime.datetime(2026, 9, 27, 12, tzinfo=datetime.timezone.utc),
            amount="5.00",
            name="Adhesion modifiee",
        )

        ctype.refresh_from_db()
        assert ctype.name == "Adhesion modifiee"
        assert ctype.amount == Decimal("5.00")
        assert ContributionTypeRate.all_objects.filter(contribution_type=ctype).count() == 1
        assert AuditLog.objects.filter(action_type="treasury.contribution_type.updated").count() == 1


class TestContraintesDuModele:
    def test_type_d_un_club_ne_peut_etre_rattache_a_un_autre_club_par_la_factory(self, ctx):
        ctype = ContributionTypeFactory(club=ctx.club)
        assert ctype.club_id == ctx.club.id

    def test_deux_types_adhesion_actifs_refuses_meme_hors_service(self, ctx):
        MembershipFeeTypeFactory(club=ctx.club)
        with pytest.raises(ValidationError):
            MembershipFeeTypeFactory(club=ctx.club)
