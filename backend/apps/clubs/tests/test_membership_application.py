"""Adhesion et parrainage (CDC 4.3 ; tache 1.4b).

Couvre l'ajout d'un joueur « En attente » avec parrain obligatoire, le
paiement des frais d'adhesion enchaine avec la generation de la fiche
PDF et la notification du parrain, la signature/le refus du parrain, le
passage « Inscrit » (peu importe l'ordre paiement/signature), et les
trois cas limites du CDC 4.3 (refus, non-reponse a 3/7 jours,
non-paiement).
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog
from apps.clubs import services as clubs_services
from apps.clubs.models import Membership, MembershipApplication, MembershipRole
from apps.clubs.tests.factories import ClubSettingsFactory, MembershipFactory
from apps.treasury import services as treasury_services
from apps.treasury.tests.conftest import make_member, past_day
from apps.treasury.tests.factories import MembershipFeeTypeFactory

pytestmark = pytest.mark.django_db


def build_context(currency="USD"):
    club = ClubSettingsFactory(currency=currency, timezone="Africa/Kinshasa").club
    president = make_member(club, roles=[MembershipRole.Role.PRESIDENT])
    treasurer = make_member(club, roles=[MembershipRole.Role.TREASURER])
    assistant = make_member(club, roles=[MembershipRole.Role.ASSISTANT_TREASURER])
    coach = make_member(club, roles=[MembershipRole.Role.COACH])
    sponsor = make_member(club)
    fee_type = MembershipFeeTypeFactory(club=club, created_by=president.user)
    return SimpleNamespace(
        club=club,
        president=president,
        treasurer=treasurer,
        assistant=assistant,
        coach=coach,
        sponsor=sponsor,
        fee_type=fee_type,
    )


@pytest.fixture
def ctx():
    return build_context()


_SPONSOR_NOT_PROVIDED = object()


def add_player(
    ctx,
    *,
    email=None,
    sponsor=_SPONSOR_NOT_PROVIDED,
    position=Membership.Position.MIDFIELDER,
    **extra,
):
    # Un compte déjà membre d'un autre club n'est plus enrôlable (D-A1) :
    # adresse distincte par club pour les tests multi-clubs.
    if email is None:
        email = f"recrue-{ctx.club.id}@example.com"
    return clubs_services.add_player_with_sponsor(
        club=ctx.club,
        email=email,
        first_name="Recrue",
        last_name="Test",
        added_by=ctx.president.user,
        sponsor=ctx.sponsor if sponsor is _SPONSOR_NOT_PROVIDED else sponsor,
        position=position,
        **extra,
    )


def pay(ctx, application, *, amount="5", method="cash", validated_by=None, **extra):
    return clubs_services.record_membership_fee_payment_for_application(
        application=application,
        amount=amount,
        method=method,
        paid_on=past_day(),
        validated_by=(validated_by or ctx.treasurer).user,
        **extra,
    )


class TestAjoutDuJoueur:
    def test_ajout_reussi_cree_membership_pending_et_application(self, ctx):
        membership, application = add_player(ctx)

        assert membership.status == Membership.Status.PENDING
        assert membership.sponsor_id == ctx.sponsor.id
        assert membership.position == Membership.Position.MIDFIELDER
        assert isinstance(application, MembershipApplication)
        assert application.membership_id == membership.id
        assert application.sponsor_decision == MembershipApplication.SponsorDecision.PENDING
        assert application.generated_at is None

    def test_journalise_l_ajout(self, ctx):
        membership, _application = add_player(ctx)
        log = AuditLog.objects.get(action_type="membership.created", object_id=str(membership.pk))
        assert log.actor_id == ctx.president.user_id
        assert log.after["status"] == Membership.Status.PENDING
        assert log.after["sponsor_id"] == ctx.sponsor.id

    def test_parrain_obligatoire(self, ctx):
        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, sponsor=None)

    def test_parrain_dun_autre_club_refuse(self, ctx):
        other = build_context()
        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, sponsor=other.sponsor)

    def test_parrain_non_inscrit_refuse(self, ctx):
        pending_sponsor = make_member(ctx.club, status=Membership.Status.PENDING)
        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, sponsor=pending_sponsor)

    def test_poste_obligatoire_a_la_creation_manuelle(self, ctx):
        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, position="")

    def test_joueur_deja_membre_du_club_refuse(self, ctx):
        membership, _application = add_player(ctx, email="deja@example.com")
        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, email="deja@example.com")


class TestPaiementFicheEtNotification:
    def test_paiement_complet_genere_la_fiche_et_notifie_le_parrain(self, ctx):
        _membership, application = add_player(ctx)

        application = pay(ctx, application)

        assert application.membership_fee_payment_id is not None
        assert application.generated_at is not None
        assert application.application_pdf_file
        assert application.sponsor_notified_at is not None

        application.application_pdf_file.open("rb")
        try:
            content = application.application_pdf_file.read()
        finally:
            application.application_pdf_file.close()
        assert content.startswith(b"%PDF")

    def test_fiche_utilise_l_en_tete_commun_et_des_libelles_accentues(self, ctx):
        _membership, application = add_player(ctx)

        application = pay(ctx, application)

        application.application_pdf_file.open("rb")
        try:
            text = application.application_pdf_file.read().decode("latin-1")
        finally:
            application.application_pdf_file.close()
        # En-tête commun (nom du club, type de document, référence) et libellés accentués.
        assert ctx.club.name in text
        # ReportLab écrit les caractères accentués en échappement octal : é = \351.
        assert "Fiche d'adh\\351sion" in text
        assert "Montant pay\\351" in text
        assert "R\\351f. A-" in text
        # Aucune référence technique ni mention de l'éditeur ou de la plateforme.
        assert "CDC" not in text
        assert "IMARA" not in text
        assert "Vesta" not in text
        assert "VESTA" not in text

    def test_paiement_partiel_ne_genere_pas_la_fiche(self, ctx):
        _membership, application = add_player(ctx)

        application = pay(ctx, application, amount="3")

        assert application.generated_at is None
        assert application.sponsor_notified_at is None

    def test_deux_paiements_partiels_cumules_generent_la_fiche(self, ctx):
        _membership, application = add_player(ctx)

        application = pay(ctx, application, amount="3")
        application = pay(ctx, application, amount="2")

        assert application.generated_at is not None
        assert treasury_services.has_paid_membership_fee(application.membership) is True

    def test_deuxieme_paiement_ne_regenere_pas_la_fiche(self, ctx):
        """Idempotence : un paiement complementaire apres coup (montant
        superieur au du, cf. point ouvert `finance-engine`) ne doit jamais
        regenerer/re-attacher une seconde fiche."""

        _membership, application = add_player(ctx)
        application = pay(ctx, application, amount="5")
        first_pdf_name = application.application_pdf_file.name

        application = pay(ctx, application, amount="1")

        assert application.application_pdf_file.name == first_pdf_name

    def test_journalise_le_paiement_lie_au_dossier(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application)

        log = AuditLog.objects.get(
            action_type="clubs.membership_application.fee_payment_recorded", object_id=str(application.pk)
        )
        assert log.actor_id == ctx.treasurer.user_id
        assert log.after["membership_fee_payment_id"] == application.membership_fee_payment_id

    def test_journalise_la_generation_de_la_fiche(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application)

        log = AuditLog.objects.get(
            action_type="clubs.membership_application.pdf_generated", object_id=str(application.pk)
        )
        assert log.actor_id == ctx.treasurer.user_id
        assert log.before["generated_at"] is None
        assert log.after["generated_at"] is not None

    def test_tresorier_adjoint_peut_enregistrer(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application, validated_by=ctx.assistant)
        assert application.membership_fee_payment.validated_by_id == ctx.assistant.user_id

    def test_erreurs_treasury_se_propagent_sans_rien_ecrire(self, ctx):
        """L'interface `finance-engine` n'est pas modifiee : un role invalide
        (ex. le Coach) leve `TreasuryPermissionError`, propagee telle
        quelle, sans ecriture cote dossier d'adhesion."""

        _membership, application = add_player(ctx)
        with pytest.raises(treasury_services.TreasuryPermissionError):
            pay(ctx, application, validated_by=ctx.coach)
        application.refresh_from_db()
        assert application.membership_fee_payment_id is None
        assert application.generated_at is None

    def test_reussit_sans_pin_auteur_dans_le_journal(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        assert application.membership_fee_payment_id is not None
        log = AuditLog.objects.get(
            action_type="clubs.membership_application.fee_payment_recorded", object_id=str(application.pk)
        )
        assert log.actor_id == ctx.treasurer.user_id


class TestSignatureDuParrain:
    def _prepared_application(self, ctx):
        _membership, application = add_player(ctx)
        return pay(ctx, application)

    def test_signature_reussie(self, ctx):
        application = self._prepared_application(ctx)

        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user
        )

        assert application.sponsor_decision == MembershipApplication.SponsorDecision.SIGNED
        assert application.sponsor_signed_by_id == ctx.sponsor.user_id
        assert application.sponsor_signed_at is not None
        assert application.resolved_at is not None

    def test_signature_fait_passer_inscrit_si_deja_paye(self, ctx):
        application = self._prepared_application(ctx)

        clubs_services.sign_sponsor_application(application=application, sponsor_user=ctx.sponsor.user)

        application.membership.refresh_from_db()
        assert application.membership.status == Membership.Status.ACTIVE

    def test_journalise_la_signature(self, ctx):
        application = self._prepared_application(ctx)
        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user
        )
        log = AuditLog.objects.get(
            action_type="clubs.membership_application.sponsor_signed", object_id=str(application.pk)
        )
        assert log.actor_id == ctx.sponsor.user_id
        assert log.after["sponsor_decision"] == MembershipApplication.SponsorDecision.SIGNED

    def test_quelqu_un_d_autre_que_le_parrain_ne_peut_pas_signer(self, ctx):
        application = self._prepared_application(ctx)
        with pytest.raises(PermissionError):
            clubs_services.sign_sponsor_application(
                application=application, sponsor_user=ctx.president.user
            )

    def test_signature_avant_generation_de_la_fiche_refusee(self, ctx):
        _membership, application = add_player(ctx)
        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.sign_sponsor_application(
                application=application, sponsor_user=ctx.sponsor.user
            )

    def test_second_envoi_avec_objet_perime_rejete_et_une_seule_signature_journalisee(self, ctx):
        application = self._prepared_application(ctx)
        stale_copy = MembershipApplication.all_objects.get(pk=application.pk)
        clubs_services.sign_sponsor_application(application=application, sponsor_user=ctx.sponsor.user)

        with pytest.raises(clubs_services.MembershipApplicationError, match="déjà signé"):
            clubs_services.sign_sponsor_application(application=stale_copy, sponsor_user=ctx.sponsor.user)

        assert AuditLog.objects.filter(action_type="clubs.membership_application.sponsor_signed").count() == 1

    def test_double_signature_refusee(self, ctx):
        application = self._prepared_application(ctx)
        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user
        )
        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.sign_sponsor_application(
                application=application, sponsor_user=ctx.sponsor.user
            )

    def test_signature_apres_son_propre_refus_est_refusee(self, ctx):
        """BUG trouve en revue independante (tache 1.4bt) : CDC 4.3, cas
        limite « le parrain refuse » -- une fois le refus enregistre (motif
        pris, President notifie), c'est au PRESIDENT de decider la suite
        (reassigner un nouveau parrain ou annuler), jamais au parrain
        refusant de revenir seul sur sa decision. Or
        :func:`sign_sponsor_application` ne verifie QUE
        ``sponsor_decision == SIGNED`` (deja signe) pour bloquer une
        signature -- pas ``== REFUSED`` : le meme parrain, ayant refuse,
        peut aujourd'hui signer quand meme et faire passer le
        joueur « Inscrit » de son seul chef, en contournant entierement le
        President. Ce test DOIT lever une erreur metier ; il echoue
        actuellement (DID NOT RAISE), ce qui confirme le bug -- ne pas
        affaiblir ce test pour le faire passer (CLAUDE.md, regle du
        test-engineer) : le signaler a `backend-dev`."""

        application = self._prepared_application(ctx)
        application = clubs_services.refuse_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user, reason="Je ne le connais pas"
        )
        assert application.sponsor_decision == MembershipApplication.SponsorDecision.REFUSED

        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.sign_sponsor_application(
                application=application, sponsor_user=ctx.sponsor.user
            )
        application.refresh_from_db()
        assert application.sponsor_decision == MembershipApplication.SponsorDecision.REFUSED
        application.membership.refresh_from_db()
        assert application.membership.status != Membership.Status.ACTIVE

    def test_reussit_sans_pin_auteur_dans_le_journal(self, ctx):
        application = self._prepared_application(ctx)
        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user
        )
        assert application.sponsor_decision == MembershipApplication.SponsorDecision.SIGNED
        log = AuditLog.objects.get(
            action_type="clubs.membership_application.sponsor_signed", object_id=str(application.pk)
        )
        assert log.actor_id == ctx.sponsor.user_id

    def test_parrain_sans_pin_defini_peut_signer(self, ctx):
        _membership, application = add_player(ctx)
        no_pin_sponsor = make_member(ctx.club)
        application.membership.sponsor = no_pin_sponsor
        application.membership.save()
        application = pay(ctx, application)
        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=no_pin_sponsor.user
        )
        assert application.sponsor_decision == MembershipApplication.SponsorDecision.SIGNED


class TestOrdrePaiementEtSignatureIndifferent:
    def test_signature_avant_paiement_puis_paiement_active(self, ctx):
        """CDC 4.3 etape 5 : peu importe l'ordre paiement/signature -- ici la
        fiche doit avoir ete generee pour signer (pas de paiement encore),
        donc ce test verifie plutot que signer AVANT que le paiement soit
        complet ne peut pas se produire tant que la fiche n'existe pas, et
        que la completion du paiement APRES un paiement partiel + signature
        active bien l'adhesion au moment ou le solde devient suffisant."""

        _membership, application = add_player(ctx)
        application = pay(ctx, application, amount="3")  # partiel : pas encore de fiche
        assert application.membership.status == Membership.Status.PENDING

        # Un second versement complementaire complete le paiement, genere la
        # fiche, notifie le parrain -- la signature peut alors intervenir.
        application = pay(ctx, application, amount="2")
        assert application.generated_at is not None

        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user
        )
        application.membership.refresh_from_db()
        assert application.membership.status == Membership.Status.ACTIVE

    def test_paiement_complete_apres_signature_active_a_ce_moment(self, ctx):
        """Signature en premier (une fois la fiche generee par un paiement
        partiel complet -- impossible ici puisque la fiche n'existe qu'une
        fois le total atteint) : on verifie donc le cas symmetrique reel
        avec deux versements, signature intercalee entre les deux."""

        _membership, application = add_player(ctx)
        application = pay(ctx, application, amount="5")  # paiement complet direct -> fiche generee
        assert application.generated_at is not None
        assert application.membership.status == Membership.Status.PENDING

        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user
        )
        application.membership.refresh_from_db()
        assert application.membership.status == Membership.Status.ACTIVE


class TestCasLimiteNonPaiement:
    def test_joueur_qui_ne_paie_pas_reste_en_attente(self, ctx):
        """CDC 4.3, cas limite « le joueur ne paie pas » : il reste « En
        attente » indefiniment -- aucune fiche ne peut etre generee et le
        parrain ne peut donc pas signer tant que le paiement n'est pas
        complet (voir aussi test_signature_avant_generation_de_la_fiche_refusee)."""

        membership, application = add_player(ctx)
        assert membership.status == Membership.Status.PENDING
        assert treasury_services.has_paid_membership_fee(membership) is False
        assert application.generated_at is None

    def test_paiement_partiel_ne_fait_jamais_passer_inscrit(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application, amount="3")
        assert application.membership.status == Membership.Status.PENDING


class TestRefusDuParrain:
    def _prepared_application(self, ctx):
        _membership, application = add_player(ctx)
        return pay(ctx, application)

    def test_refus_motif_obligatoire(self, ctx):
        application = self._prepared_application(ctx)
        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.refuse_sponsor_application(
                application=application, sponsor_user=ctx.sponsor.user, reason="   "
            )

    def test_refus_reussi(self, ctx):
        application = self._prepared_application(ctx)
        application = clubs_services.refuse_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user, reason="Ne connait pas ce joueur"
        )
        assert application.sponsor_decision == MembershipApplication.SponsorDecision.REFUSED
        assert application.sponsor_refused_reason == "Ne connait pas ce joueur"

    def test_journalise_le_refus(self, ctx):
        application = self._prepared_application(ctx)
        application = clubs_services.refuse_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user, reason="Motif"
        )
        log = AuditLog.objects.get(
            action_type="clubs.membership_application.sponsor_refused", object_id=str(application.pk)
        )
        assert log.actor_id == ctx.sponsor.user_id
        assert log.after["sponsor_refused_reason"] == "Motif"

    def test_quelqu_un_d_autre_que_le_parrain_ne_peut_pas_refuser(self, ctx):
        application = self._prepared_application(ctx)
        with pytest.raises(PermissionError):
            clubs_services.refuse_sponsor_application(
                application=application, sponsor_user=ctx.president.user, reason="Motif"
            )

    def test_refus_dun_dossier_deja_signe_refuse(self, ctx):
        application = self._prepared_application(ctx)
        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user
        )
        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.refuse_sponsor_application(
                application=application, sponsor_user=ctx.sponsor.user, reason="Motif"
            )


class TestReassignationDuParrain:
    def _refused_application(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        return clubs_services.refuse_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user, reason="Motif du refus"
        )

    def test_reassignation_reussie(self, ctx):
        application = self._refused_application(ctx)
        new_sponsor = make_member(ctx.club)

        application = clubs_services.reassign_sponsor(
            application=application, president_user=ctx.president.user, new_sponsor=new_sponsor
        )

        application.membership.refresh_from_db()
        assert application.membership.sponsor_id == new_sponsor.id
        assert application.sponsor_decision == MembershipApplication.SponsorDecision.PENDING
        assert application.sponsor_refused_reason == ""
        assert application.sponsor_notified_at is not None  # nouvelle notification (redemarre le compteur)

    def test_journalise_la_reassignation(self, ctx):
        application = self._refused_application(ctx)
        new_sponsor = make_member(ctx.club)
        application = clubs_services.reassign_sponsor(
            application=application, president_user=ctx.president.user, new_sponsor=new_sponsor
        )
        log = AuditLog.objects.get(
            action_type="clubs.membership_application.sponsor_reassigned", object_id=str(application.pk)
        )
        assert log.actor_id == ctx.president.user_id

    def test_reservee_au_president(self, ctx):
        application = self._refused_application(ctx)
        new_sponsor = make_member(ctx.club)
        with pytest.raises(PermissionError):
            clubs_services.reassign_sponsor(
                application=application, president_user=ctx.treasurer.user, new_sponsor=new_sponsor
            )

    def test_uniquement_apres_un_refus(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        new_sponsor = make_member(ctx.club)
        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.reassign_sponsor(
                application=application, president_user=ctx.president.user, new_sponsor=new_sponsor
            )

    def test_nouveau_parrain_doit_etre_inscrit(self, ctx):
        application = self._refused_application(ctx)
        pending_sponsor = make_member(ctx.club, status=Membership.Status.PENDING)
        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.reassign_sponsor(
                application=application, president_user=ctx.president.user, new_sponsor=pending_sponsor
            )

    def test_nouveau_parrain_ne_peut_pas_etre_le_joueur_lui_meme(self, ctx):
        application = self._refused_application(ctx)
        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.reassign_sponsor(
                application=application, president_user=ctx.president.user, new_sponsor=application.membership
            )

    def test_apres_reassignation_signature_du_nouveau_parrain_active(self, ctx):
        application = self._refused_application(ctx)
        new_sponsor = make_member(ctx.club)
        application = clubs_services.reassign_sponsor(
            application=application, president_user=ctx.president.user, new_sponsor=new_sponsor
        )

        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=new_sponsor.user
        )
        application.membership.refresh_from_db()
        assert application.membership.status == Membership.Status.ACTIVE

    def test_nouveau_parrain_dun_autre_club_refuse(self, ctx):
        """Complement demande en revue independante (tache 1.4bt) : le
        garde-fou « meme club » (CDC 4.3, ``Membership.clean()``) est deja
        verifie a la CREATION du dossier (test_parrain_dun_autre_club_refuse)
        mais pas explicitement a la REASSIGNATION -- meme regle, chemin de
        code distinct (:func:`reassign_sponsor`)."""

        application = self._refused_application(ctx)
        other = build_context()
        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.reassign_sponsor(
                application=application, president_user=ctx.president.user, new_sponsor=other.sponsor
            )

    def test_reassignation_redemarre_bien_le_rappel_et_l_alerte(self, ctx):
        """Complement demande en revue independante (tache 1.4bt) : la
        docstring de :func:`reassign_sponsor` affirme « redemarre le
        compteur de rappel/alerte » -- ce test verifie explicitement que
        ``sponsor_reminder_sent_at`` et ``president_alerted_at`` (pas
        seulement ``sponsor_decision``) sont bien remis a ``None``. Sans
        cette remise a zero, :func:`process_sponsor_reminders_and_alerts` ne
        renverrait plus jamais de rappel/alerte pour ce dossier (son filtre
        exige ``..._isnull=True``)."""

        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        # Simule un premier cycle complet de rappel + alerte avant le refus.
        application.sponsor_reminder_sent_at = timezone.now()
        application.president_alerted_at = timezone.now()
        application.save()
        application = clubs_services.refuse_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user, reason="Motif du refus"
        )
        assert application.sponsor_reminder_sent_at is not None
        assert application.president_alerted_at is not None

        new_sponsor = make_member(ctx.club)
        application = clubs_services.reassign_sponsor(
            application=application, president_user=ctx.president.user, new_sponsor=new_sponsor
        )

        assert application.sponsor_reminder_sent_at is None
        assert application.president_alerted_at is None


class TestAnnulationDeLAdhesion:
    def _refused_application(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        return clubs_services.refuse_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user, reason="Motif du refus"
        )

    def test_annulation_avec_remboursement(self, ctx):
        application = self._refused_application(ctx)
        membership = application.membership
        assert treasury_services.has_paid_membership_fee(membership) is True

        application = clubs_services.cancel_membership_application(
            application=application,
            president_user=ctx.president.user,
            reason="Aucun autre parrain disponible",
            disposition=MembershipApplication.FeeDisposition.REFUNDED,
        )

        membership.refresh_from_db()
        assert membership.status == Membership.Status.DEPARTED
        assert membership.left_reason == Membership.LeftReason.CANCELLED
        assert membership.left_by_id == ctx.president.user_id
        assert application.membership_fee_disposition == MembershipApplication.FeeDisposition.REFUNDED
        assert application.cancelled_by_id == ctx.president.user_id
        assert application.resolved_at is not None
        assert treasury_services.has_paid_membership_fee(membership) is False

    def test_annulation_avec_conservation_ne_touche_pas_la_tresorerie(self, ctx):
        application = self._refused_application(ctx)
        membership = application.membership

        clubs_services.cancel_membership_application(
            application=application,
            president_user=ctx.president.user,
            reason="Motif",
            disposition=MembershipApplication.FeeDisposition.KEPT,
        )

        membership.refresh_from_db()
        assert membership.status == Membership.Status.DEPARTED
        # Le paiement reste acquis (aucune ecriture financiere) : la lecture
        # renvoie encore "paye" pour cette adhesion (meme si elle est
        # desormais Partie -- la fonction ne regarde jamais le statut).
        assert treasury_services.has_paid_membership_fee(membership) is True

    def test_journalise_l_annulation_et_le_depart(self, ctx):
        application = self._refused_application(ctx)
        membership = application.membership

        application = clubs_services.cancel_membership_application(
            application=application,
            president_user=ctx.president.user,
            reason="Motif",
            disposition=MembershipApplication.FeeDisposition.KEPT,
        )

        AuditLog.objects.get(
            action_type="clubs.membership_application.cancelled", object_id=str(application.pk)
        )
        AuditLog.objects.get(action_type="membership.departed", object_id=str(membership.pk))

    def test_second_appel_refuse_et_ne_reecrit_rien(self, ctx):
        """Une annulation rejouee (meme avec un objet `application` perime et
        une autre disposition du paiement) est refusee : un seul depart, une
        seule annulation journalises, aucun remboursement supplementaire."""

        application = self._refused_application(ctx)
        stale_copy = MembershipApplication.all_objects.get(pk=application.pk)
        membership = application.membership

        clubs_services.cancel_membership_application(
            application=application,
            president_user=ctx.president.user,
            reason="Premier motif",
            disposition=MembershipApplication.FeeDisposition.KEPT,
        )
        with pytest.raises(clubs_services.MembershipApplicationError, match="déjà été annulée"):
            clubs_services.cancel_membership_application(
                application=stale_copy,
                president_user=ctx.president.user,
                reason="Second motif",
                disposition=MembershipApplication.FeeDisposition.REFUNDED,
            )

        stored = MembershipApplication.all_objects.get(pk=application.pk)
        assert stored.cancelled_reason == "Premier motif"
        assert stored.membership_fee_disposition == MembershipApplication.FeeDisposition.KEPT
        assert treasury_services.has_paid_membership_fee(membership) is True
        assert AuditLog.objects.filter(action_type="clubs.membership_application.cancelled").count() == 1
        assert AuditLog.objects.filter(action_type="membership.departed", object_id=str(membership.pk)).count() == 1

    def test_reservee_au_president(self, ctx):
        application = self._refused_application(ctx)
        with pytest.raises(PermissionError):
            clubs_services.cancel_membership_application(
                application=application,
                president_user=ctx.treasurer.user,
                reason="Motif",
                disposition=MembershipApplication.FeeDisposition.KEPT,
            )

    def test_uniquement_apres_un_refus(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.cancel_membership_application(
                application=application,
                president_user=ctx.president.user,
                reason="Motif",
                disposition=MembershipApplication.FeeDisposition.KEPT,
            )

    def test_motif_obligatoire(self, ctx):
        application = self._refused_application(ctx)
        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.cancel_membership_application(
                application=application,
                president_user=ctx.president.user,
                reason="   ",
                disposition=MembershipApplication.FeeDisposition.KEPT,
            )

    def test_disposition_invalide_refusee(self, ctx):
        application = self._refused_application(ctx)
        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.cancel_membership_application(
                application=application,
                president_user=ctx.president.user,
                reason="Motif",
                disposition="autre_chose",
            )

    def test_remboursement_sans_paiement_refuse(self, ctx):
        """Refus du parrain avant tout paiement (dossier jamais notifie,
        jamais de fiche) : la disposition « remboursement » n'a alors aucun
        sens (rien a rembourser)."""

        membership, application = add_player(ctx)
        # Refus force manuellement (aucune fiche generee, sponsor_decision
        # encore PENDING par construction -- on simule directement l'etat
        # "refuse" attendu par cette fonction sans passer par le paiement).
        application.sponsor_decision = MembershipApplication.SponsorDecision.REFUSED
        application.sponsor_refused_reason = "Motif"
        application.save()

        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.cancel_membership_application(
                application=application,
                president_user=ctx.president.user,
                reason="Motif",
                disposition=MembershipApplication.FeeDisposition.REFUNDED,
            )

    @pytest.mark.parametrize(
        "disposition",
        [MembershipApplication.FeeDisposition.KEPT, MembershipApplication.FeeDisposition.REFUNDED],
    )
    def test_reussit_sans_pin_auteur_dans_le_journal(self, ctx, disposition):
        application = self._refused_application(ctx)
        application = clubs_services.cancel_membership_application(
            application=application,
            president_user=ctx.president.user,
            reason="Motif",
            disposition=disposition,
        )
        assert application.cancelled_by_id == ctx.president.user_id
        application.membership.refresh_from_db()
        assert application.membership.status == Membership.Status.DEPARTED
        log = AuditLog.objects.get(
            action_type="clubs.membership_application.cancelled", object_id=str(application.pk)
        )
        assert log.actor_id == ctx.president.user_id

    def test_annulation_refusee_si_l_adhesion_est_deja_inscrite(self, ctx):
        """Complement demande en revue independante (tache 1.4bt) : une
        adhesion deja « Inscrite » ne peut pas etre annulee par ce chemin.
        Verifie ici le garde-fou en simulant le seul chemin structurellement
        possible pour arriver a ce cas (Inscrit ET refuse ne devrait jamais
        coexister -- ``sign_sponsor_application``/``refuse_sponsor_application``
        l'empechent tous les deux par construction, voir
        ``test_double_signature_refusee``/``test_refus_dun_dossier_deja_signe_refuse``) :
        ce test isole ce garde-fou en forcant directement l'etat en base,
        au cas ou une donnee incoherente existerait malgre tout (defense en
        profondeur du service, pas seulement du chemin normal)."""

        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user
        )
        application.membership.refresh_from_db()
        assert application.membership.status == Membership.Status.ACTIVE

        # Force une incoherence deliberee (refuse malgre l'inscription
        # deja actee) pour isoler le garde-fou de `cancel_membership_application`
        # lui-meme, independamment de savoir si cet etat est atteignable en
        # temps normal.
        application.sponsor_decision = MembershipApplication.SponsorDecision.REFUSED
        application.save()

        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.cancel_membership_application(
                application=application,
                president_user=ctx.president.user,
                reason="Motif",
                disposition=MembershipApplication.FeeDisposition.KEPT,
            )
        application.membership.refresh_from_db()
        assert application.membership.status == Membership.Status.ACTIVE


class TestIdempotenceActivation:
    """Complement demande en revue independante (tache 1.4bt), point 1 :
    ordre des evenements et idempotence de :func:`_maybe_activate_membership`."""

    def test_paiement_complementaire_apres_activation_ne_double_active_pas(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application, amount="3")
        application = pay(ctx, application, amount="2")
        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user
        )
        application.membership.refresh_from_db()
        assert application.membership.status == Membership.Status.ACTIVE

        activation_logs_before = AuditLog.objects.filter(
            action_type="membership.updated", object_id=str(application.membership_id)
        ).count()

        # Versement complementaire (sur-paiement) une fois l'adhesion deja
        # active : ne doit surtout pas re-declencher une seconde ecriture
        # « passage Inscrit » (idempotence de `_maybe_activate_membership`).
        application = pay(ctx, application, amount="1")

        application.membership.refresh_from_db()
        assert application.membership.status == Membership.Status.ACTIVE
        activation_logs_after = AuditLog.objects.filter(
            action_type="membership.updated", object_id=str(application.membership_id)
        ).count()
        assert activation_logs_after == activation_logs_before

    def test_maybe_activate_membership_est_un_no_op_silencieux_si_deja_actif(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user
        )
        application.membership.refresh_from_db()
        assert application.membership.status == Membership.Status.ACTIVE

        logs_before = AuditLog.objects.count()

        # Deuxieme appel direct : ne doit lever aucune erreur et n'ecrire
        # aucune nouvelle entree de journal (deja Inscrit, retour immediat).
        result = clubs_services._maybe_activate_membership(
            application=application, actor=ctx.treasurer.user
        )

        assert result.status == Membership.Status.ACTIVE
        assert AuditLog.objects.count() == logs_before


class TestRappelsEtAlertesDeParrainage:
    def _notified_application(self, ctx, *, notified_at):
        _membership, application = add_player(ctx)
        application.sponsor_notified_at = notified_at
        application.save()
        return application

    def test_pas_de_rappel_avant_3_jours(self, ctx):
        now = timezone.now()
        application = self._notified_application(ctx, notified_at=now - datetime.timedelta(days=2))

        result = clubs_services.process_sponsor_reminders_and_alerts(now=now)

        application.refresh_from_db()
        assert application.sponsor_reminder_sent_at is None
        assert result["reminders_sent"] == 0

    def test_rappel_envoye_apres_3_jours(self, ctx):
        now = timezone.now()
        application = self._notified_application(ctx, notified_at=now - datetime.timedelta(days=3, minutes=1))

        result = clubs_services.process_sponsor_reminders_and_alerts(now=now)

        application.refresh_from_db()
        assert application.sponsor_reminder_sent_at == now
        assert application.president_alerted_at is None
        assert result["reminders_sent"] == 1
        assert result["alerts_sent"] == 0

    def test_alerte_envoyee_apres_7_jours(self, ctx):
        now = timezone.now()
        application = self._notified_application(ctx, notified_at=now - datetime.timedelta(days=7, minutes=1))

        result = clubs_services.process_sponsor_reminders_and_alerts(now=now)

        application.refresh_from_db()
        assert application.sponsor_reminder_sent_at == now
        assert application.president_alerted_at == now
        assert result == {"reminders_sent": 1, "alerts_sent": 1}

    def test_idempotent_ne_renvoie_jamais_deux_fois(self, ctx):
        now = timezone.now()
        application = self._notified_application(ctx, notified_at=now - datetime.timedelta(days=10))

        clubs_services.process_sponsor_reminders_and_alerts(now=now)
        first_reminder = MembershipApplication.all_objects.get(pk=application.pk).sponsor_reminder_sent_at
        first_alert = MembershipApplication.all_objects.get(pk=application.pk).president_alerted_at

        later = now + datetime.timedelta(days=1)
        result = clubs_services.process_sponsor_reminders_and_alerts(now=later)

        assert result == {"reminders_sent": 0, "alerts_sent": 0}
        refreshed = MembershipApplication.all_objects.get(pk=application.pk)
        assert refreshed.sponsor_reminder_sent_at == first_reminder
        assert refreshed.president_alerted_at == first_alert

    def test_ignore_les_dossiers_jamais_notifies(self, ctx):
        _membership, application = add_player(ctx)
        now = timezone.now() + datetime.timedelta(days=10)

        result = clubs_services.process_sponsor_reminders_and_alerts(now=now)

        application.refresh_from_db()
        assert application.sponsor_reminder_sent_at is None
        assert application.president_alerted_at is None
        assert result == {"reminders_sent": 0, "alerts_sent": 0}

    def test_ignore_les_dossiers_deja_signes(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user
        )
        now = application.sponsor_notified_at + datetime.timedelta(days=10)

        result = clubs_services.process_sponsor_reminders_and_alerts(now=now)

        assert result == {"reminders_sent": 0, "alerts_sent": 0}

    def test_ignore_les_dossiers_deja_refuses(self, ctx):
        """Complement demande en revue independante (tache 1.4bt) : le CDC
        4.3 dit que le rappel/l'alerte ne concernent que le parrain qui n'a
        « pas repondu » -- un dossier deja REFUSE a bien repondu (par la
        negative) et ne doit donc plus jamais etre rappele/alerte, meme si
        `sponsor_notified_at` reste ancien (seul `test_ignore_les_dossiers_deja_signes`
        etait couvert avant ce complement, pas la branche REFUSED)."""

        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        application = clubs_services.refuse_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user, reason="Motif du refus"
        )
        now = application.sponsor_notified_at + datetime.timedelta(days=10)

        result = clubs_services.process_sponsor_reminders_and_alerts(now=now)

        assert result == {"reminders_sent": 0, "alerts_sent": 0}
        application.refresh_from_db()
        assert application.sponsor_reminder_sent_at is None
        assert application.president_alerted_at is None

    def test_ne_journalise_aucune_entree_coherent_avec_l_absence_d_acteur_reel(self, ctx):
        """Complement demande en revue independante (tache 1.4bt), point 4 :
        le rapport de `backend-dev` signale que cette fonction ne
        journalise pas ses horodatages, faute d'acteur reel -- ce test ne
        corrige pas ce point ouvert (signale au compte rendu), il verifie
        seulement que ce choix ne provoque aucun crash (ex. tentative de
        journaliser avec ``actor=None``) et qu'aucune entree n'est
        effectivement ecrite."""

        now = timezone.now()
        application = self._notified_application(ctx, notified_at=now - datetime.timedelta(days=10))
        logs_before = AuditLog.objects.count()

        clubs_services.process_sponsor_reminders_and_alerts(now=now)

        assert AuditLog.objects.count() == logs_before

    def test_etancheite_entre_clubs(self, ctx):
        """CLAUDE.md regle n8 : la commande parcourt tous les clubs, mais un
        dossier d'un autre club ne doit jamais interferer avec le calcul de
        celui-ci."""

        other = build_context()
        now = timezone.now()
        application_a = self._notified_application(ctx, notified_at=now - datetime.timedelta(days=4))
        _membership_b, application_b = add_player(other, sponsor=other.sponsor)
        application_b.sponsor_notified_at = now - datetime.timedelta(days=4)
        application_b.save()

        result = clubs_services.process_sponsor_reminders_and_alerts(now=now)

        assert result["reminders_sent"] == 2
        application_a.refresh_from_db()
        application_b.refresh_from_db()
        assert application_a.sponsor_reminder_sent_at == now
        assert application_b.sponsor_reminder_sent_at == now


class TestGenerationDuPdfAvecCaracteresSpeciaux:
    """Complement demande en revue independante (tache 1.4bt), point 8 :
    reportlab (police standard Helvetica, encodage WinAnsi) peut etre
    sensible a l'encodage -- ce test verifie qu'un nom de joueur, de
    parrain ou de club contenant des caracteres accentues/speciaux ne fait
    jamais planter :func:`generate_membership_application_pdf`."""

    def test_pdf_genere_avec_noms_accentues(self, ctx):
        accented_club = ClubSettingsFactory(
            currency="USD",
            timezone="Africa/Kinshasa",
        ).club
        accented_club.name = "Étoile du Congo — Club éphémère & Cie"
        accented_club.save()
        president = make_member(accented_club, roles=[MembershipRole.Role.PRESIDENT])
        treasurer = make_member(accented_club, roles=[MembershipRole.Role.TREASURER])
        MembershipFeeTypeFactory(club=accented_club, created_by=president.user)

        sponsor_user = UserFactory(
            first_name="Émilie", last_name="N'Doyé-Müller"
        )
        sponsor = MembershipFactory(club=accented_club, user=sponsor_user, status=Membership.Status.ACTIVE)

        membership, application = clubs_services.add_player_with_sponsor(
            club=accented_club,
            email="joueur.accents@example.com",
            first_name="François",
            last_name="Çelik",
            added_by=president.user,
            sponsor=sponsor,
            position=Membership.Position.FORWARD,
        )

        application = clubs_services.record_membership_fee_payment_for_application(
            application=application,
            amount="5",
            method="cash",
            paid_on=past_day(),
            validated_by=treasurer.user,
        )

        assert application.generated_at is not None
        application.application_pdf_file.open("rb")
        try:
            content = application.application_pdf_file.read()
        finally:
            application.application_pdf_file.close()
        assert content.startswith(b"%PDF")

        application = clubs_services.sign_sponsor_application(
            application=application, sponsor_user=sponsor_user
        )
        assert application.sponsor_decision == MembershipApplication.SponsorDecision.SIGNED
        membership.refresh_from_db()
        assert membership.status == Membership.Status.ACTIVE


class TestRejeuApresEchecDeLaSuite:
    """Reaudit 12/10/2026 : un echec apres la validation du paiement ne doit
    pas laisser le dossier bloque ; un rejeu (meme client_uuid) le complete."""

    def test_echec_du_pdf_puis_rejeu_complete_le_dossier(self, ctx, monkeypatch):
        import uuid

        from apps.notifications.models import Notification
        from apps.treasury.models import Payment

        _membership, application = add_player(ctx)
        key = uuid.uuid4()
        real_generate = clubs_services.generate_membership_application_pdf

        def boom(**kwargs):
            raise RuntimeError("panne PDF")

        monkeypatch.setattr(clubs_services, "generate_membership_application_pdf", boom)
        first = pay(ctx, application, client_uuid=key)
        assert first.generated_at is None
        assert first.membership_fee_payment_id is not None

        monkeypatch.setattr(clubs_services, "generate_membership_application_pdf", real_generate)
        replay = pay(ctx, first, client_uuid=key)

        assert replay.generated_at is not None
        assert replay.sponsor_notified_at is not None
        assert Payment.all_objects.filter(club=ctx.club, membership=application.membership).count() == 1
        assert (
            AuditLog.objects.filter(
                action_type="clubs.membership_application.fee_payment_recorded",
                object_id=str(application.pk),
            ).count()
            == 1
        )
        assert Notification.objects.filter(recipient=ctx.sponsor.user).count() == 1

        # Troisieme rejeu : plus rien a rattraper, aucun doublon.
        pay(ctx, replay, client_uuid=key)
        assert Notification.objects.filter(recipient=ctx.sponsor.user).count() == 1


class TestVerrousEtReverification:
    def test_refus_avec_objet_perime_apres_signature_est_rejete(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        stale = MembershipApplication.all_objects.get(pk=application.pk)
        clubs_services.sign_sponsor_application(application=application, sponsor_user=ctx.sponsor.user)

        with pytest.raises(clubs_services.MembershipApplicationError):
            clubs_services.refuse_sponsor_application(
                application=stale, sponsor_user=ctx.sponsor.user, reason="Motif"
            )
        fresh = MembershipApplication.all_objects.get(pk=application.pk)
        assert fresh.sponsor_decision == MembershipApplication.SponsorDecision.SIGNED
        assert not AuditLog.objects.filter(action_type="clubs.membership_application.sponsor_refused").exists()

    def test_activation_avec_adhesion_perimee_n_ecrit_qu_un_journal(self, ctx):
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        stale_application = MembershipApplication.all_objects.select_related("membership").get(pk=application.pk)
        clubs_services.sign_sponsor_application(application=application, sponsor_user=ctx.sponsor.user)
        assert stale_application.membership.status == Membership.Status.PENDING  # objet perime
        stale_application.sponsor_decision = MembershipApplication.SponsorDecision.SIGNED

        before = AuditLog.objects.filter(
            action_type="membership.updated", object_id=str(application.membership_id)
        ).count()
        result = clubs_services._maybe_activate_membership(application=stale_application, actor=ctx.treasurer.user)
        after = AuditLog.objects.filter(
            action_type="membership.updated", object_id=str(application.membership_id)
        ).count()

        assert result.status == Membership.Status.ACTIVE
        assert after == before
