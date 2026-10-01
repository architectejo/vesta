"""Complements de couverture de `TenantModel.save()` (audit de securite du
Lot 1, ecart bloquant B4), au-dela de `apps.core.tests.test_tenant_scope_coverage`.

Trois questions posees par la revue independante de test-engineer, non
couvertes par les tests existants (qui n'exercent que des instances
fraiches, jamais encore enregistrees) :

1. Le controle de club (`TenantMismatchError`) fonctionne-t-il aussi pour
   la MISE A JOUR d'un enregistrement DEJA existant, pas seulement sa
   creation ?
2. Que se passe-t-il quand `self.club_id` est `None` au moment du `save()`
   (nouvel enregistrement pas encore associe a un club) ?
3. `full_clean()` declenche sur CHAQUE `save()` casse-t-il des mises a
   jour partielles legitimes (`update_fields`) qui ne touchent pas la
   validation en cause ?

Sources : CLAUDE.md regle n8 ; `apps.core.models.TenantModel.save()`.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.tests.factories import SuperuserFactory
from apps.clubs.models import Membership, Season
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.core.tenant import TenantMismatchError, active_club


@pytest.mark.django_db
class TestControleDeClubSurUneMiseAJourExistante:
    """Question 1 : jusqu'ici (`test_tenant_scope_coverage`), seules des
    instances jamais enregistrees (`model(club=...)`, pk=None) etaient
    testees -- ce qui teste en realite toujours un chemin de CREATION,
    meme via `.save()`. Ces tests portent sur un enregistrement DEJA
    persiste, recupere avant tout changement de contexte."""

    def test_mise_a_jour_d_un_enregistrement_existant_d_un_autre_club_est_refusee(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        membership_de_b = MembershipFactory(club=club_b)

        with active_club(club_a):
            membership_de_b.position = Membership.Position.FORWARD
            with pytest.raises(TenantMismatchError):
                membership_de_b.save(update_fields=["position"])

        # Le contournement est bien refuse avant toute ecriture en base.
        membership_de_b.refresh_from_db()
        assert membership_de_b.position != Membership.Position.FORWARD

    def test_mise_a_jour_d_un_enregistrement_existant_du_club_actif_reussit(self):
        club_a = ClubFactory()
        membership_de_a = MembershipFactory(club=club_a)

        with active_club(club_a):
            membership_de_a.position = Membership.Position.FORWARD
            membership_de_a.save(update_fields=["position"])

        membership_de_a.refresh_from_db()
        assert membership_de_a.position == Membership.Position.FORWARD


@pytest.mark.django_db
class TestClubIdNoneAuMomentDuSave:
    """Question 2 : le controle de club ne s'applique que si `self.club_id`
    est renseigne (`self.club_id is not None` dans `TenantModel.save()`).
    Sans `club` du tout, l'echec attendu vient du champ obligatoire
    (`ValidationError` de `full_clean()`), jamais de `TenantMismatchError`
    -- ce sont deux causes d'echec distinctes, la vue/l'appelant ne doit
    pas les confondre."""

    def test_save_sans_club_renseigne_leve_validation_error_et_pas_tenant_mismatch(self):
        season = Season(
            label="2099",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            created_by=SuperuserFactory(),
        )

        with active_club(ClubFactory()):
            with pytest.raises(ValidationError) as exc_info:
                season.save()

        assert not isinstance(exc_info.value, TenantMismatchError)


@pytest.mark.django_db
class TestFullCleanEtMisesAJourPartielles:
    """Question 3 : `full_clean()` valide l'INTEGRALITE de l'instance en
    memoire, pas seulement les champs listes dans `update_fields` -- mais
    puisque l'instance est deja complete et valide avant la modification,
    ceci ne casse aucune mise a jour partielle legitime sur un champ non
    lie a une regle de coherence. A l'inverse, une mise a jour partielle
    qui rend l'instance transitoirement invalide EST a juste titre
    refusee (ce n'est pas un faux positif : l'etat est reellement invalide
    a cet instant precis du point de vue metier)."""

    def test_update_fields_sur_un_champ_sans_lien_avec_une_contrainte_reussit(self):
        membership = MembershipFactory(position=Membership.Position.MIDFIELDER)

        membership.position = Membership.Position.FORWARD
        membership.save(update_fields=["position"])  # ne doit lever aucune exception

        membership.refresh_from_db()
        assert membership.position == Membership.Position.FORWARD

    def test_update_fields_qui_rend_l_instance_transitoirement_invalide_est_refuse(self):
        """Poser `left_on` sans `left_reason` dans le meme appel viole
        `membership_left_reason_required_if_left_on` : `full_clean()` le
        detecte meme via `update_fields=["left_on"]` seul -- comportement
        VOULU (CLAUDE.md regle n8 ; contrainte deja en place avant B4),
        pas une regression introduite par le forçage de `full_clean()`."""

        membership = MembershipFactory(left_on=None, left_reason="")

        membership.left_on = timezone.now().date()
        with pytest.raises(ValidationError):
            membership.save(update_fields=["left_on"])

        membership.refresh_from_db()
        assert membership.left_on is None
