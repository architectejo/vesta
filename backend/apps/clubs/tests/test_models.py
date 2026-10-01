"""Tests des modeles de l'app clubs (tache 1.2).

Sources : CDC 2.1-2.5, 4.1, 4.3 ; CLAUDE.md regle n1 ;
docs/lot0/schema-donnees.md §3, §4.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.clubs.models import Club, Membership, MembershipApplication, MembershipRole, PresidencyTransfer, Season
from apps.clubs.tests.factories import (
    ClubFactory,
    ClubSettingsFactory,
    ImportBatchFactory,
    MembershipApplicationFactory,
    MembershipFactory,
    MembershipRoleFactory,
    PresidencyTransferFactory,
    SeasonFactory,
)
from apps.core.tenant import active_club


@pytest.mark.django_db
class TestClubEtParametres:
    def test_club_et_settings_se_creent(self):
        club = ClubFactory()
        settings_obj = ClubSettingsFactory(club=club)
        assert settings_obj.club_id == club.id
        assert settings_obj.currency == "USD"

    def test_season_a_une_borne_de_fin_apres_le_debut(self):
        season = SeasonFactory()
        assert season.end_date >= season.start_date

    def test_season_end_date_avant_start_date_rejetee_par_contrainte_db(self):
        """Symetrique du test equivalent sur `Licence` (schema §4.3, §4.5).

        Depuis l'audit de securite du Lot 1 (ecart bloquant B4),
        `TenantModel.save()` appelle `full_clean()` avant tout
        enregistrement : la meme contrainte (`CheckConstraint`
        `season_end_after_start`) est donc desormais detectee par
        `validate_constraints()` en Python (`ValidationError`) avant
        meme d'atteindre la base -- la contrainte SQL elle-meme reste en
        place (defense en profondeur, ex. `queryset.update()` qui
        contournerait `save()`), mais n'est plus ce qui declenche
        l'echec dans ce chemin d'appel precis.
        """

        club = ClubFactory()
        with pytest.raises(ValidationError):
            Season.all_objects.create(
                club=club,
                label="2027",
                start_date=timezone.now().date(),
                end_date=timezone.now().date() - timezone.timedelta(days=1),
                created_by=SuperuserFactory(),
            )

    def test_club_founder_membership_doit_appartenir_au_meme_club(self):
        """ECART (voir compte rendu) : `Club` ne valide pas que son `founder_membership`
        appartient bien a ce club. CDC 2.3 : « Le joueur qui cree le club devient
        President. Il cree en meme temps sa propre fiche joueur » -- implique que
        `founder_membership` designe necessairement une adhesion du club concerne,
        jamais celle d'un autre club. Ce test echoue tant que `Club` n'implemente
        pas ce controle (aucune `clean()` sur ce modele a ce jour), a la difference
        du meme controle deja applique par `Membership.clean()` (parrain) et
        `MembershipRole.clean()` (role/adhesion)."""

        club_a = ClubFactory()
        club_b = ClubFactory()
        membership_dans_club_b = MembershipFactory(club=club_b)

        club_a.founder_membership = membership_dans_club_b
        with pytest.raises(ValidationError):
            club_a.full_clean()


@pytest.mark.django_db
class TestMembershipValidation:
    def test_superuser_ne_peut_pas_avoir_de_fiche_joueur(self):
        """CLAUDE.md regle n1 : seuls les Superusers ne sont pas joueurs."""

        club = ClubFactory()
        superuser = SuperuserFactory()
        membership = Membership(
            club=club,
            user=superuser,
            joined_on=timezone.now().date(),
            added_by=superuser,
        )
        with pytest.raises(ValidationError):
            membership.full_clean()

    def test_parrain_doit_appartenir_au_meme_club(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        sponsor_b = MembershipFactory(club=club_b)
        membership = Membership(
            club=club_a,
            user=UserFactory(),
            sponsor=sponsor_b,
            joined_on=timezone.now().date(),
            added_by=SuperuserFactory(),
        )
        with pytest.raises(ValidationError):
            membership.full_clean()

    def test_left_reason_requis_si_left_on_renseigne(self):
        """Contrainte DB (portable SQLite/MySQL recents, voir compte rendu).

        Depuis l'audit de securite du Lot 1 (ecart bloquant B4),
        `TenantModel.save()` appelle `full_clean()` avant tout
        enregistrement : cette meme contrainte
        (`membership_left_reason_required_if_left_on`) est donc
        desormais detectee en Python (`ValidationError`) avant meme
        d'atteindre la base -- la contrainte SQL reste en place (defense
        en profondeur), mais n'est plus ce qui declenche l'echec ici.
        """

        club = ClubFactory()
        with pytest.raises(ValidationError):
            Membership.all_objects.create(
                club=club,
                user=UserFactory(),
                joined_on=timezone.now().date(),
                left_on=timezone.now().date(),
                added_by=SuperuserFactory(),
            )

    def test_jersey_number_hors_plage_rejete(self):
        """Meme constat que `test_left_reason_requis_si_left_on_renseigne`
        ci-dessus (audit de securite du Lot 1, ecart bloquant B4) :
        `full_clean()`, appele automatiquement par `save()`, detecte
        desormais la violation de `membership_jersey_number_range` avant
        la base (`ValidationError`, plus `IntegrityError`)."""

        club = ClubFactory()
        with pytest.raises(ValidationError):
            Membership.all_objects.create(
                club=club,
                user=UserFactory(),
                joined_on=timezone.now().date(),
                jersey_number=100,
                added_by=SuperuserFactory(),
            )

    def test_membership_est_directement_la_fiche_joueur(self):
        """CLAUDE.md regle n1 : « Tout utilisateur d'un club est un joueur,
        President compris [...] Seuls les Superusers ne sont pas joueurs. »

        Il n'existe pas de modele `Player` distinct : `Membership` porte
        directement les champs de la fiche joueur (poste, numero, date
        d'entree). Un utilisateur normal qui rejoint un club a donc
        necessairement une fiche joueur des la creation de son adhesion --
        il ne peut pas exister d'adhesion "sans joueur"."""

        membership = MembershipFactory(position=Membership.Position.FORWARD, jersey_number=9)
        assert membership.position == Membership.Position.FORWARD
        assert membership.jersey_number == 9
        assert membership.joined_on is not None
        assert not getattr(membership.user, "is_superuser", False)

    def test_le_president_est_aussi_une_adhesion_donc_un_joueur(self):
        """CDC 2.1 : « Le President [...] figurent donc dans le vestiaire,
        cotisent et peuvent etre alignes. » -- un role President est
        toujours porte par une `Membership` (fiche joueur), jamais par un
        `User` directement (le role n'existe qu'attache a une adhesion)."""

        president_membership = MembershipFactory()
        role = MembershipRoleFactory(
            membership=president_membership, role=MembershipRole.Role.PRESIDENT
        )
        assert role.membership_id == president_membership.id
        assert role.membership.position  # la fiche joueur existe bien


@pytest.mark.django_db
class TestMembershipRoleEtApplication:
    def test_role_se_cree_avec_le_meme_club_que_l_adhesion(self):
        role = MembershipRoleFactory()
        assert role.club_id == role.membership.club_id

    def test_role_rejete_si_club_different_de_l_adhesion(self):
        membership = MembershipFactory()
        autre_club = ClubFactory()
        role = MembershipRole(
            club=autre_club,
            membership=membership,
            role="captain",
            appointed_by=SuperuserFactory(),
            appointed_at=timezone.now(),
        )
        with pytest.raises(ValidationError):
            role.full_clean()

    def test_application_unique_par_adhesion(self):
        """Depuis l'audit de securite du Lot 1 (ecart bloquant B4),
        `TenantModel.save()` appelle `full_clean()` avant tout
        enregistrement : la violation d'unicite sur `membership`
        (`OneToOneField`) est donc desormais detectee par
        `validate_unique()` en Python (`ValidationError`) avant meme
        d'atteindre la base -- la contrainte d'unicite SQL reste en
        place (defense en profondeur), mais n'est plus ce qui declenche
        l'echec ici."""

        application = MembershipApplicationFactory()
        with pytest.raises(ValidationError):
            MembershipApplication.all_objects.create(
                club=application.club, membership=application.membership
            )

    def test_application_rejetee_si_club_different_de_l_adhesion(self):
        """ECART (voir compte rendu) : contrairement a `MembershipRole.clean()`
        (meme controle pour son couple role/adhesion), `MembershipApplication`
        n'a aucune `clean()` verifiant que `self.club` correspond au club de
        `self.membership`. Ce test echoue tant que ce controle n'existe pas
        (schema-donnees.md §1.2 : « quand une entite reference une autre
        entite privee [...], les deux doivent appartenir au meme club »)."""

        club_a = ClubFactory()
        club_b = ClubFactory()
        membership_dans_club_a = MembershipFactory(club=club_a)

        application = MembershipApplication(club=club_b, membership=membership_dans_club_a)
        with active_club(club_b):
            with pytest.raises(ValidationError):
                application.full_clean()


@pytest.mark.django_db
class TestPresidencyTransfer:
    def test_from_et_to_membership_doivent_differer(self):
        """Depuis l'audit de securite du Lot 1 (ecart bloquant B4),
        `TenantModel.save()` appelle `full_clean()` avant tout
        enregistrement : la violation de
        `presidency_transfer_distinct_memberships` est donc desormais
        detectee en Python (`ValidationError`) avant meme d'atteindre la
        base -- la contrainte SQL reste en place (defense en
        profondeur), mais n'est plus ce qui declenche l'echec ici."""

        club = ClubFactory()
        membership = MembershipFactory(club=club)
        with pytest.raises(ValidationError):
            PresidencyTransfer.all_objects.create(
                club=club,
                from_membership=membership,
                to_membership=membership,
                method=PresidencyTransfer.Method.HANDOVER,
                transferred_at=timezone.now(),
            )

    def test_intervention_superuser_exige_l_identite_reelle(self):
        club = ClubFactory()
        membership_sortant = MembershipFactory(club=club)
        membership_entrant = MembershipFactory(club=club)
        transfer = PresidencyTransfer(
            club=club,
            from_membership=membership_sortant,
            to_membership=membership_entrant,
            method=PresidencyTransfer.Method.SUPERUSER_OVERRIDE,
            transferred_at=timezone.now(),
        )
        with pytest.raises(ValidationError):
            transfer.full_clean()

    def test_passation_directe_valide(self):
        transfer = PresidencyTransferFactory()
        transfer.full_clean()  # ne doit lever aucune exception
        assert transfer.from_membership.club_id == transfer.to_membership.club_id

    def test_rejete_si_son_propre_club_differe_des_adhesions(self):
        """ECART (voir compte rendu) : `PresidencyTransfer.clean()` verifie
        que `from_membership` et `to_membership` partagent le meme club,
        mais jamais que le champ `club` du `PresidencyTransfer` lui-meme
        (obligatoire, `TenantModel`) correspond a ce club -- a la difference
        de `MembershipRole.clean()`, qui applique ce controle pour son
        propre champ `club`. Ce test echoue tant que ce controle n'existe
        pas (schema-donnees.md §1.2)."""

        club_a = ClubFactory()
        club_b = ClubFactory()
        membership_sortant = MembershipFactory(club=club_a)
        membership_entrant = MembershipFactory(club=club_a)

        transfer = PresidencyTransfer(
            club=club_b,
            from_membership=membership_sortant,
            to_membership=membership_entrant,
            method=PresidencyTransfer.Method.HANDOVER,
            transferred_at=timezone.now(),
        )
        with active_club(club_b):
            with pytest.raises(ValidationError):
                transfer.full_clean()


@pytest.mark.django_db
def test_import_batch_conserve_le_fichier_source_et_le_rapport():
    batch = ImportBatchFactory()
    assert batch.source_file.name
    assert batch.row_count_success == 0
    assert batch.row_count_failed == 0


@pytest.mark.django_db
class TestFullCleanAppliqueAutomatiquementALEcriture:
    """Audit de securite du Lot 1 (ecart bloquant B4) : les controles de
    coherence testes ci-dessus (``TestMembershipValidation``,
    ``TestMembershipRoleEtApplication``) n'etaient jusqu'ici appliques que
    si l'appelant invoquait explicitement ``full_clean()`` -- un simple
    ``Model(...).save()`` les contournait entierement. Ces tests prouvent
    qu'ils s'appliquent desormais automatiquement, sans appel explicite a
    ``full_clean()``."""

    def test_membership_save_direct_refuse_un_superuser(self):
        club = ClubFactory()
        superuser = SuperuserFactory()
        membership = Membership(
            club=club,
            user=superuser,
            joined_on=timezone.now().date(),
            added_by=superuser,
        )

        with pytest.raises(ValidationError):
            membership.save()

        assert not Membership.all_objects.filter(club=club, user=superuser).exists()

    def test_membership_role_save_direct_refuse_un_club_different_de_l_adhesion(self):
        membership = MembershipFactory()
        autre_club = ClubFactory()
        role = MembershipRole(
            club=autre_club,
            membership=membership,
            role="captain",
            appointed_by=SuperuserFactory(),
            appointed_at=timezone.now(),
        )

        with pytest.raises(ValidationError):
            role.save()

        assert not MembershipRole.all_objects.filter(club=autre_club, membership=membership).exists()

    def test_presidency_transfer_save_direct_refuse_un_club_different_des_adhesions(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        membership_sortant = MembershipFactory(club=club_a)
        membership_entrant = MembershipFactory(club=club_a)
        transfer = PresidencyTransfer(
            club=club_b,
            from_membership=membership_sortant,
            to_membership=membership_entrant,
            method=PresidencyTransfer.Method.HANDOVER,
            transferred_at=timezone.now(),
        )

        with pytest.raises(ValidationError):
            transfer.save()

    def test_club_save_direct_refuse_un_founder_membership_d_un_autre_club(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        membership_dans_club_b = MembershipFactory(club=club_b)

        club_a.founder_membership = membership_dans_club_b

        with pytest.raises(ValidationError):
            club_a.save()
