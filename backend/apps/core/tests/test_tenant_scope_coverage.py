"""Couverture systematique de la regle n8 sur tous les `TenantModel` (tache 1.2t).

Le test de 1.2 (`apps.clubs.tests.test_tenant_isolation`) ne verifiait
l'etancheite que sur `Membership`. Cette regle non negociable
(CLAUDE.md n8, CDC 6.3) s'applique a **toute** table privee de club, pas
seulement `Membership` : ce module verifie generiquement, pour chaque
sous-classe concrete de `TenantModel` existant a ce jour (Season,
Membership, MembershipRole, MembershipApplication, PresidencyTransfer,
ImportBatch -- docs/lot0/schema-donnees.md §3-§4), qu'une requete sans
club actif est refusee. Ecrit generiquement pour continuer a couvrir
automatiquement tout futur `TenantModel` ajoute par un lot suivant.

Verifie egalement l'exception documentee (schema-donnees.md §1.2) :
`Club` et `Licence` sont delibierement hors du perimetre `TenantModel`
(portee plateforme, Superuser) et restent donc interrogeables sans club
actif.

Audit de securite du Lot 1 (ecart bloquant B4) : les tests
`TestEcritureRefuseeSiClubDifferentDuClubActif` et
`TestEcritureNonRestreinteSansClubActif`, ci-dessous, completent cette
couverture **cote ecriture** -- le manager tenant-aware ne protegeait
jusqu'ici que les lectures.
"""

from __future__ import annotations

import pytest
from django.apps import apps as django_apps

from apps.clubs.models import Club
from apps.clubs.tests.factories import ClubFactory
from apps.core.models import TenantModel
from apps.core.tenant import NoActiveClubError, TenantMismatchError, active_club
from apps.licences.models import Licence
from apps.licences.tests.factories import LicenceFactory


def _concrete_tenant_models() -> list[type]:
    """Toutes les sous-classes concretes de `TenantModel` actuellement enregistrees."""

    return [
        model
        for model in django_apps.get_models()
        if issubclass(model, TenantModel) and not model._meta.abstract
    ]


@pytest.mark.django_db
def test_au_moins_les_modeles_attendus_de_la_tache_1_2_sont_couverts():
    """Garde-fou : si cette liste se vide un jour, le test generique ne teste plus rien."""

    noms = {model.__name__ for model in _concrete_tenant_models()}
    attendus = {
        "Season",
        "Membership",
        "MembershipRole",
        "MembershipApplication",
        "PresidencyTransfer",
        "ImportBatch",
    }
    assert attendus.issubset(noms), (
        f"Modeles TenantModel attendus manquants : {attendus - noms}. "
        "Ce test doit rester exhaustif (CLAUDE.md regle n8)."
    )


@pytest.mark.django_db
def test_toute_requete_sans_club_actif_est_refusee_pour_chaque_tenant_model():
    """CLAUDE.md regle n8, applique a chaque `TenantModel`, pas seulement `Membership`."""

    for model in _concrete_tenant_models():
        with pytest.raises(NoActiveClubError):
            list(model.objects.all())


@pytest.mark.django_db
def test_club_est_hors_perimetre_tenant_model_et_reste_interrogeable():
    """`Club` est une exception documentee (portee plateforme, schema §1.2)."""

    assert not issubclass(Club, TenantModel)
    assert not hasattr(Club, "all_objects")

    ClubFactory()
    # Aucune erreur attendue : Club n'est jamais filtre par club actif,
    # il EST le club (CDC 3.5, 7.3 -- lu avant connexion).
    assert list(Club.objects.all())


@pytest.mark.django_db
def test_licence_est_hors_perimetre_tenant_model_et_reste_interrogeable():
    """`Licence` est une exception documentee (portee plateforme, Superuser, schema §1.2)."""

    assert not issubclass(Licence, TenantModel)
    assert not hasattr(Licence, "all_objects")

    LicenceFactory()
    assert list(Licence.objects.all())


@pytest.mark.django_db
class TestEcritureRefuseeSiClubDifferentDuClubActif:
    """Preuve de fermeture de l'ecart bloquant B4 (audit de securite du Lot 1).

    Le controle de :meth:`TenantModel.save` intervient avant
    ``full_clean()`` : une instance minimale (seul ``club`` renseigne)
    suffit a le declencher, sans avoir a remplir les autres champs
    obligatoires de chaque sous-classe -- ce test reste donc generique et
    continue de couvrir automatiquement tout futur `TenantModel`.
    """

    def test_create_direct_avec_un_club_different_du_club_actif_est_refuse(self):
        club_actif = ClubFactory()
        autre_club = ClubFactory()

        for model in _concrete_tenant_models():
            with active_club(club_actif):
                with pytest.raises(TenantMismatchError):
                    model.all_objects.create(club=autre_club)

    def test_save_direct_avec_un_club_different_du_club_actif_est_refuse(self):
        club_actif = ClubFactory()
        autre_club = ClubFactory()

        for model in _concrete_tenant_models():
            instance = model(club=autre_club)
            with active_club(club_actif):
                with pytest.raises(TenantMismatchError):
                    instance.save()

    def test_save_avec_le_meme_club_que_le_club_actif_n_est_pas_bloque_par_ce_controle(self):
        """Contre-preuve : le controle ne bloque que le *mismatch*, jamais
        une ecriture legitime dans le club actif lui-meme (l'echec attendu
        ici, s'il y en a un, vient de `full_clean()` -- champs obligatoires
        manquants sur l'instance minimale -- jamais de `TenantMismatchError`)."""

        club_actif = ClubFactory()

        for model in _concrete_tenant_models():
            instance = model(club=club_actif)
            with active_club(club_actif):
                try:
                    instance.save()
                except TenantMismatchError:  # pragma: no cover - ne doit jamais arriver
                    pytest.fail(
                        f"{model.__name__} : TenantMismatchError leve alors que le "
                        "club de l'instance correspond au club actif."
                    )
                except Exception:
                    # Un autre echec (full_clean, champ obligatoire manquant
                    # sur cette instance volontairement minimale) est
                    # attendu et sans rapport avec ce controle.
                    pass


@pytest.mark.django_db
def test_ecriture_sans_club_actif_n_est_pas_restreinte_par_le_controle_de_club():
    """Sans club actif dans le contexte courant (import, commande de
    gestion, contexte Superuser), le controle de club de
    `TenantModel.save()` ne s'applique pas -- comportement deja voulu par
    `TenantManager` cote lecture (voir
    `test_all_objects_reste_non_filtre_pour_usage_plateforme_explicite`,
    `apps.clubs.tests.test_tenant_isolation`)."""

    from apps.clubs.tests.factories import MembershipFactory

    club_a = ClubFactory()
    # Aucun `with active_club(...)` ici : le contexte est neutre. La
    # creation reussit malgre un club "quelconque" du point de vue du
    # controle de club (aucune notion de club actif a comparer).
    membership = MembershipFactory(club=club_a)
    assert membership.club_id == club_a.id
