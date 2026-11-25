"""Tests des services d'ajout/import de joueurs (tache 1.4 ; CDC 4.1).

Sources : CDC 4.1 (« Ajout d'un joueur », « Import CSV des joueurs
existants », statuts du joueur) ; matrice 2.4 (« Ajout et import de
joueurs ») ; CLAUDE.md regles n1, n6, n8, n9.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.clubs import services as clubs_services
from apps.clubs.models import Membership
from apps.clubs.tests.factories import ClubFactory, MembershipFactory


def _csv_upload(content: str, name: str = "import.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


@pytest.mark.django_db
class TestCreateOrUpdatePlayer:
    def test_email_totalement_nouveau_cree_un_compte_et_une_adhesion(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)

        result = clubs_services.create_or_update_player(
            club=club,
            email="Nouveau.Joueur@Example.com",
            first_name="Nouveau",
            last_name="Joueur",
            added_by=recruteur.user,
        )

        assert result.outcome == "created"
        assert result.user_created is True
        user = result.membership.user
        assert user.email == "nouveau.joueur@example.com"  # normalise en minuscules
        assert user.check_password("nouveau.joueur@example.com")  # CDC 4.1 : mdp initial = email
        assert user.must_change_password is True
        assert result.membership.status == Membership.Status.ACTIVE
        assert result.membership.sponsor_id is None
        assert result.membership.club_id == club.id

    def test_email_deja_present_dans_le_club_met_a_jour_la_fiche(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        existant = MembershipFactory(
            club=club,
            status=Membership.Status.ACTIVE,
            position=Membership.Position.DEFENDER,
            jersey_number=7,
        )

        result = clubs_services.create_or_update_player(
            club=club,
            email=existant.user.email,
            first_name=existant.user.first_name,
            last_name=existant.user.last_name,
            added_by=recruteur.user,
            position=Membership.Position.FORWARD,
        )

        assert result.outcome == "updated"
        existant.refresh_from_db()
        assert existant.position == Membership.Position.FORWARD
        # Le numero non fourni dans cette mise a jour n'est pas efface :
        assert existant.jersey_number == 7
        # Une mise a jour ne modifie jamais le statut (CDC 4.1) :
        assert existant.status == Membership.Status.ACTIVE

    def test_mise_a_jour_ne_cree_aucun_doublon_de_membership(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        existant = MembershipFactory(club=club, status=Membership.Status.ACTIVE)

        clubs_services.create_or_update_player(
            club=club,
            email=existant.user.email,
            first_name=existant.user.first_name,
            last_name=existant.user.last_name,
            added_by=recruteur.user,
            phone="0900000000",
        )

        assert Membership.all_objects.filter(club=club, user=existant.user).count() == 1

    def test_email_avec_adhesion_active_dans_un_autre_club_refuse_la_creation(self):
        """Garde de securite (audit tache 1.13, ecart bloquant B2) : ce test
        remplace ``test_email_connu_dans_un_autre_club_cree_une_nouvelle_
        adhesion_sans_recreer_le_compte``, qui encodait l'ANCIEN
        comportement (aujourd'hui vulnerable) ou une seconde adhesion
        ``ACTIVE`` etait creee pour le meme compte dans un second club.

        Deux adhesions ``ACTIVE`` simultanees pour le meme ``User`` rendent
        le club actif ambigu pour
        ``apps.core.services.resolve_active_membership`` (leve
        ``NoActiveClubError``), exception avalee silencieusement par
        ``apps.core.authentication.TenantJWTAuthentication`` : le
        proprietaire legitime du compte perdrait alors tout acces, y
        compris a son premier club. ``create_or_update_player`` doit donc
        refuser cette ligne (:class:`PlayerImportError`) plutot que de
        creer la seconde adhesion -- voir apps/clubs/services.py
        (docstring cas 2 de ``create_or_update_player``)."""

        premier_club = ClubFactory()
        second_club = ClubFactory()
        recruteur_second_club = MembershipFactory(club=second_club)
        membre_premier_club = MembershipFactory(club=premier_club, status=Membership.Status.ACTIVE)
        original_user_id = membre_premier_club.user_id

        with pytest.raises(clubs_services.PlayerImportError):
            clubs_services.create_or_update_player(
                club=second_club,
                email=membre_premier_club.user.email,
                first_name=membre_premier_club.user.first_name,
                last_name=membre_premier_club.user.last_name,
                added_by=recruteur_second_club.user,
            )

        # Le compte n'est pas duplique : un seul `User` pour cet email.
        assert User.objects.filter(email=membre_premier_club.user.email).count() == 1
        # Aucune seconde adhesion n'a ete creee : le proprietaire du compte
        # garde une adhesion unique, dans son club d'origine uniquement.
        assert Membership.all_objects.filter(user_id=original_user_id).count() == 1
        assert not Membership.all_objects.filter(club=second_club, user_id=original_user_id).exists()

    def test_numero_de_maillot_deja_porte_par_un_joueur_actif_echoue(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        MembershipFactory(club=club, status=Membership.Status.ACTIVE, jersey_number=10)

        with pytest.raises(clubs_services.PlayerImportError):
            clubs_services.create_or_update_player(
                club=club,
                email="autre.joueur@example.com",
                first_name="Autre",
                last_name="Joueur",
                added_by=recruteur.user,
                jersey_number=10,
            )

    def test_numero_de_maillot_libre_par_un_joueur_parti_est_accepte(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        MembershipFactory(
            club=club,
            status=Membership.Status.DEPARTED,
            jersey_number=10,
            left_on=date(2026, 1, 1),
            left_reason=Membership.LeftReason.RESIGNATION,
        )

        result = clubs_services.create_or_update_player(
            club=club,
            email="nouveau.dix@example.com",
            first_name="Nouveau",
            last_name="Dix",
            added_by=recruteur.user,
            jersey_number=10,
        )

        assert result.outcome == "created"
        assert result.membership.jersey_number == 10

    def test_parrain_dun_autre_club_est_refuse_par_la_coherence_du_modele(self):
        club = ClubFactory()
        autre_club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        parrain_autre_club = MembershipFactory(club=autre_club)

        with pytest.raises(ValidationError):
            clubs_services.create_or_update_player(
                club=club,
                email="filleul@example.com",
                first_name="Filleul",
                last_name="Test",
                added_by=recruteur.user,
                sponsor=parrain_autre_club,
                status=Membership.Status.PENDING,
            )

    def test_mise_a_jour_journalise_une_entree_membership_updated(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        existant = MembershipFactory(club=club, status=Membership.Status.ACTIVE)

        clubs_services.create_or_update_player(
            club=club,
            email=existant.user.email,
            first_name=existant.user.first_name,
            last_name=existant.user.last_name,
            added_by=recruteur.user,
            position=Membership.Position.GOALKEEPER,
        )

        entry = AuditLog.objects.get(action_type="membership.updated", object_id=str(existant.pk))
        assert entry.actor_id == recruteur.user_id
        assert entry.after["position"] == Membership.Position.GOALKEEPER

    def test_mise_a_jour_sans_changement_ne_journalise_rien(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        existant = MembershipFactory(club=club, status=Membership.Status.ACTIVE)

        clubs_services.create_or_update_player(
            club=club,
            email=existant.user.email,
            first_name=existant.user.first_name,
            last_name=existant.user.last_name,
            added_by=recruteur.user,
        )

        assert not AuditLog.objects.filter(
            action_type="membership.updated", object_id=str(existant.pk)
        ).exists()


@pytest.mark.django_db
class TestImportPlayersFromCsv:
    def test_import_de_40_joueurs_sans_poste_ni_date_reussit_sans_echec(self):
        """Critere de fin exact de la tache 1.4 (plan-lots.md, CDC 4.1)."""

        club = ClubFactory()
        recruteur = MembershipFactory(club=club)

        # Prefixe "quarante" (pas "joueur") : evite toute collision avec la
        # sequence d'emails `UserFactory`/`SuperuserFactory`
        # (`joueur{n}@example.com`, partagee par `MembershipFactory.added_by`
        # -- un compte Superuser genere par le fixture `recruteur` ci-dessus
        # pourrait sinon porter le meme email qu'une ligne CSV, et
        # provoquer un echec de ligne legitime mais non desire par ce test
        # (CLAUDE.md regle n1 : un Superuser ne peut pas avoir de fiche
        # joueur).
        lines = ["email,prenom,nom,telephone,poste,numero,date_naissance,poids,taille,type_cotisation"]
        for i in range(40):
            lines.append(f"quarante{i}@example.com,Prenom{i},Nom{i},,,,,,,")
        csv_content = "\n".join(lines)

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 40
        assert summary.batch.row_count_failed == 0
        assert Membership.all_objects.filter(club=club, status=Membership.Status.ACTIVE).count() == 40 + 1
        assert all(row.outcome != "failed" for row in summary.rows)

    def test_dates_jj_mm_aaaa_et_aaaa_mm_jj_acceptees(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,prenom,nom,date_naissance\n"
            "premier@example.com,Premier,Joueur,15/03/1990\n"
            "second@example.com,Second,Joueur,1992-07-21\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 0
        premier = Membership.all_objects.get(club=club, user__email="premier@example.com")
        second = Membership.all_objects.get(club=club, user__email="second@example.com")
        assert premier.user.birth_date == date(1990, 3, 15)
        assert second.user.birth_date == date(1992, 7, 21)

    def test_ligne_email_manquant_echoue_sans_bloquer_les_autres_lignes(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,prenom,nom\n"
            ",Sans,Email\n"
            "valide@example.com,Valide,Joueur\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 1
        assert summary.batch.row_count_failed == 1
        failed = [row for row in summary.rows if row.outcome == "failed"]
        assert len(failed) == 1
        assert failed[0].line_number == 2
        assert "email manquant" in failed[0].message
        assert Membership.all_objects.filter(club=club, user__email="valide@example.com").exists()

    def test_email_deja_present_dans_le_club_met_a_jour_au_lieu_de_dupliquer(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        existant = MembershipFactory(club=club, status=Membership.Status.ACTIVE)

        csv_content = (
            f"email,prenom,nom,poste\n"
            f"{existant.user.email},{existant.user.first_name},{existant.user.last_name},Attaquant\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 1
        assert summary.rows[0].outcome == "updated"
        assert Membership.all_objects.filter(club=club, user=existant.user).count() == 1
        existant.refresh_from_db()
        assert existant.position == Membership.Position.FORWARD

    def test_numero_de_maillot_en_conflit_echoue_sans_bloquer_lautre_ligne(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        MembershipFactory(club=club, status=Membership.Status.ACTIVE, jersey_number=9)

        csv_content = (
            "email,prenom,nom,numero\n"
            "conflit@example.com,Conflit,Joueur,9\n"
            "libre@example.com,Libre,Joueur,11\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 1
        assert summary.batch.row_count_failed == 1
        assert not Membership.all_objects.filter(club=club, user__email="conflit@example.com").exists()
        assert Membership.all_objects.filter(club=club, user__email="libre@example.com").exists()

    def test_poste_invalide_echoue_avec_message_francais(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,prenom,nom,poste\ninvalide@example.com,Test,Poste,Pilote\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 1
        assert "poste inconnu" in summary.rows[0].message

    def test_type_cotisation_invalide_ou_vide_ne_bloque_jamais_la_ligne(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,prenom,nom,type_cotisation\n"
            "un@example.com,Un,Test,VALEUR-INVENTEE-123\n"
            "deux@example.com,Deux,Test,\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 2
        assert summary.batch.row_count_failed == 0
        membership = Membership.all_objects.get(club=club, user__email="un@example.com")
        assert membership.requested_contribution_type_label == "VALEUR-INVENTEE-123"

    def test_lot_dimport_est_journalise_et_porte_le_rapport(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,prenom,nom\njoueur@example.com,Joueur,Test\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        entry = AuditLog.objects.get(
            action_type="clubs.import.created", object_id=str(summary.batch.pk)
        )
        assert entry.actor_id == recruteur.user_id
        assert summary.batch.report_file
        assert summary.batch.source_file

    # -----------------------------------------------------------------
    # Revue independante (tache 1.4t) : doublons d'email DANS LE MEME
    # fichier CSV (pas un doublon avec une fiche deja en base).
    # -----------------------------------------------------------------

    def test_deux_lignes_du_meme_fichier_avec_le_meme_email_la_seconde_met_a_jour_la_fiche_creee_par_la_premiere(
        self,
    ):
        """Chaque ligne est traitee independamment et immediatement (pas de
        transaction unique enveloppant tout le fichier, CDC 4.1 : « une
        ligne en echec n'interrompt jamais l'import des lignes suivantes »).
        Consequence observee, non documentee explicitement jusqu'ici : deux
        lignes du MEME fichier partageant le meme email ne produisent
        jamais de doublon -- la seconde ligne met a jour la fiche que la
        premiere vient de creer, exactement comme un email deja present en
        base avant l'import. Comportement coherent avec la regle CDC 4.1
        (« Un email deja present [...] met a jour la fiche au lieu de
        creer un doublon ») ; couvert explicitement ici car non teste
        jusqu'a present pour le cas intra-fichier."""

        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,prenom,nom,poste\n"
            "doublon@example.com,Premier,Passage,Milieu\n"
            "doublon@example.com,Premier,Passage,Attaquant\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 2
        assert summary.batch.row_count_failed == 0
        assert summary.rows[0].outcome == "created"
        assert summary.rows[1].outcome == "updated"
        assert (
            Membership.all_objects.filter(club=club, user__email="doublon@example.com").count() == 1
        )
        membership = Membership.all_objects.get(club=club, user__email="doublon@example.com")
        assert membership.position == Membership.Position.FORWARD  # derniere ligne gagne

    def test_deux_lignes_du_meme_fichier_avec_casse_differente_du_meme_email_sont_vues_comme_le_meme_joueur(
        self,
    ):
        """La deduplication doit reposer sur l'email normalise (minuscules),
        pas sur la chaine brute du CSV : ``Jean@Club.com`` et
        ``jean@club.com`` designent le meme joueur (CDC 4.1 : email unique
        sur la plateforme)."""

        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,prenom,nom\n"
            "Jean@Club.com,Jean,Casse\n"
            "jean@club.com,Jean,Casse\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 2
        assert summary.rows[0].outcome == "created"
        assert summary.rows[1].outcome == "updated"
        assert Membership.all_objects.filter(club=club, user__email="jean@club.com").count() == 1

    def test_email_avec_espaces_parasites_est_nettoye_avant_validation(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,prenom,nom\n  espaces@example.com  ,Avec,Espaces\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 0
        assert Membership.all_objects.filter(club=club, user__email="espaces@example.com").exists()

    # -----------------------------------------------------------------
    # Numero de maillot : conflit INTERNE au fichier (pas avec l'existant).
    # -----------------------------------------------------------------

    def test_deux_lignes_du_meme_fichier_avec_le_meme_numero_de_maillot_la_seconde_echoue(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,prenom,nom,numero\n"
            "premier@example.com,Premier,Joueur,21\n"
            "second@example.com,Second,Joueur,21\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 1
        assert summary.batch.row_count_failed == 1
        assert summary.rows[0].outcome == "created"
        assert summary.rows[1].outcome == "failed"
        assert "21" in summary.rows[1].message
        assert Membership.all_objects.filter(club=club, user__email="premier@example.com").exists()
        assert not Membership.all_objects.filter(club=club, user__email="second@example.com").exists()

    def test_numero_de_maillot_zero_echoue_avec_message_clair(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,prenom,nom,numero\nzero@example.com,Zero,Test,0\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 1
        assert "numéro de maillot invalide" in summary.rows[0].message

    def test_numero_de_maillot_negatif_echoue_avec_message_clair(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,prenom,nom,numero\nnegatif@example.com,Negatif,Test,-5\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 1
        assert "numéro de maillot invalide" in summary.rows[0].message

    def test_numero_de_maillot_non_numerique_echoue_avec_message_clair(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,prenom,nom,numero\ntexte@example.com,Texte,Test,dix\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 1
        assert "numéro de maillot invalide" in summary.rows[0].message

    # -----------------------------------------------------------------
    # Dates : format invalide et date de naissance dans le futur.
    # -----------------------------------------------------------------

    def test_date_de_naissance_invalide_echoue_sans_bloquer_les_autres_lignes(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,prenom,nom,date_naissance\n"
            "date.invalide@example.com,Date,Invalide,32/13/2024\n"
            "date.valide@example.com,Date,Valide,01/01/2000\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 1
        assert summary.batch.row_count_failed == 1
        assert "date de naissance invalide" in summary.rows[0].message
        assert not Membership.all_objects.filter(
            club=club, user__email="date.invalide@example.com"
        ).exists()
        assert Membership.all_objects.filter(club=club, user__email="date.valide@example.com").exists()

    def test_date_de_naissance_dans_le_futur_est_acceptee_a_ce_jour(self):
        """Le CDC 4.1 ne precise pas explicitement si une date de naissance
        future doit etre rejetee a l'import (contrairement au format,
        explicitement borne a JJ/MM/AAAA ou AAAA-MM-JJ). Comportement
        observe : une telle date est acceptee telle quelle -- documente ici
        comme point a faire trancher par le client (CLAUDE.md, circuit
        9.4), pas comme un bug : aucune regle du CDC ne l'interdit
        aujourd'hui."""

        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,prenom,nom,date_naissance\nfutur@example.com,Futur,Test,01/01/2099\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 0
        membership = Membership.all_objects.get(club=club, user__email="futur@example.com")
        assert membership.user.birth_date == date(2099, 1, 1)

    # -----------------------------------------------------------------
    # Email invalide (format), distinct du cas « manquant » deja couvert.
    # -----------------------------------------------------------------

    def test_email_de_format_invalide_echoue_sans_bloquer_les_autres_lignes(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,prenom,nom\n"
            "pas-un-email,Invalide,Test\n"
            "valide2@example.com,Valide,Test\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 1
        assert summary.batch.row_count_failed == 1
        assert "email invalide" in summary.rows[0].message
        assert Membership.all_objects.filter(club=club, user__email="valide2@example.com").exists()

    # -----------------------------------------------------------------
    # Fichier CSV malformé : en-tete/colonnes/lignes.
    # -----------------------------------------------------------------

    def test_fichier_totalement_vide_ne_leve_aucune_exception(self):
        """Aucune ligne, aucun en-tete : ne doit jamais planter -- se
        comporte comme un import de zero ligne (ni succes, ni echec)."""

        club = ClubFactory()
        recruteur = MembershipFactory(club=club)

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload("")
        )

        assert summary.batch.row_count_success == 0
        assert summary.batch.row_count_failed == 0
        assert summary.rows == []

    def test_en_tete_present_sans_aucune_ligne_de_donnees_ne_leve_aucune_exception(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,prenom,nom\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 0
        assert summary.batch.row_count_failed == 0
        assert summary.rows == []

    def test_colonne_email_absente_du_fichier_chaque_ligne_echoue_proprement(self):
        """Colonne obligatoire absente de l'en-tete (pas seulement vide sur
        une ligne) : chaque ligne echoue avec un message clair, sans
        jamais lever d'exception Python non maitrisee."""

        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "prenom,nom\nSans,Colonne\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 0
        assert summary.batch.row_count_failed == 1
        assert "email manquant" in summary.rows[0].message

    def test_ligne_avec_moins_de_colonnes_que_len_tete_est_traitee_comme_valeurs_vides(self):
        """``csv.DictReader`` complete par ``None`` les colonnes manquantes
        d'une ligne trop courte : un poste absent de cette facon doit etre
        traite exactement comme une cellule vide (facultatif a l'import,
        CDC 4.1), jamais comme un plantage."""

        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,prenom,nom,poste\ncourte@example.com,Courte,Ligne\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 0
        membership = Membership.all_objects.get(club=club, user__email="courte@example.com")
        assert membership.position == ""

    def test_ligne_avec_plus_de_colonnes_que_len_tete_nempeche_pas_le_traitement(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,prenom,nom\nlongue@example.com,Longue,Ligne,colonne_en_trop,encore\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 0
        assert Membership.all_objects.filter(club=club, user__email="longue@example.com").exists()

    def test_fichier_non_utf8_devrait_echouer_proprement_avec_un_message_francais(self):
        """Bug trouve par la revue 1.4t et corrige : ``import_players_
        from_csv`` encadre desormais ``raw_bytes.decode("utf-8-sig")`` d'un
        ``try/except UnicodeDecodeError`` (apps/clubs/services.py). Un
        fichier CSV encode en Latin-1 (ou tout encodage non UTF-8) leve
        maintenant une ``PlayerImportError`` avec un message clair en
        francais, conformement a CDC 4.1 (« [...] un message en francais »)
        et au principe general de robustesse d'import (9.2), au lieu d'une
        exception Python brute non maitrisee."""

        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        # 0xE9 = "é" en Latin-1/CP1252, mais une suite d'octets invalide en UTF-8.
        raw = "email,prenom,nom\naccent@example.com,Pr\xe9nom,Nom\n".encode("latin-1")
        csv_file = SimpleUploadedFile("import.csv", raw, content_type="text/csv")

        with pytest.raises(clubs_services.PlayerImportError):
            clubs_services.import_players_from_csv(
                club=club, imported_by=recruteur.user, csv_file=csv_file
            )

    # -----------------------------------------------------------------
    # Comptage exact sur un fichier mixte (critere de fin de la tache 1.4,
    # plan-lots.md : « rapport de lignes en echec correct »).
    # -----------------------------------------------------------------

    def test_row_count_success_et_failed_correspondent_exactement_a_un_fichier_mixte(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        MembershipFactory(club=club, status=Membership.Status.ACTIVE, jersey_number=50)

        # 5 lignes valides, 5 lignes en echec de causes toutes differentes.
        csv_content = "\n".join(
            [
                "email,prenom,nom,poste,numero,date_naissance",
                "valide1@example.com,Valide,Un,Gardien,1,01/01/1995",
                "valide2@example.com,Valide,Deux,,,",
                "valide3@example.com,Valide,Trois,Milieu,3,15/06/1998",
                "valide4@example.com,Valide,Quatre,,,",
                "valide5@example.com,Valide,Cinq,Attaquant,5,",
                ",SansEmail,Test,,,",  # email manquant
                "poste.invalide@example.com,Poste,Invalide,Pilote,,",  # poste inconnu
                "conflit.numero@example.com,Conflit,Numero,,50,",  # numero deja pris (pre-existant)
                "date.invalide@example.com,Date,Invalide,,,32/13/2024",  # date invalide
                "numero.invalide@example.com,Numero,Invalide,,999,",  # hors bornes
            ]
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 5
        assert summary.batch.row_count_failed == 5
        assert summary.batch.row_count_success + summary.batch.row_count_failed == len(summary.rows)
        failed_lines = sorted(row.line_number for row in summary.rows if row.outcome == "failed")
        assert failed_lines == [7, 8, 9, 10, 11]
        succeeded_lines = sorted(row.line_number for row in summary.rows if row.outcome != "failed")
        assert succeeded_lines == [2, 3, 4, 5, 6]
        for email in [f"valide{i}@example.com" for i in range(1, 6)]:
            assert Membership.all_objects.filter(club=club, user__email=email).exists()
        for email in [
            "poste.invalide@example.com",
            "conflit.numero@example.com",
            "date.invalide@example.com",
            "numero.invalide@example.com",
        ]:
            assert not Membership.all_objects.filter(club=club, user__email=email).exists()

    # -----------------------------------------------------------------
    # Garde de securite B2 (audit tache 1.13) au niveau import CSV : une
    # ligne dont l'email a deja une adhesion ACTIVE dans un autre club
    # echoue, sans jamais bloquer les lignes suivantes du meme fichier
    # (CDC 4.1 : « une ligne en echec n'interrompt jamais l'import »).
    # -----------------------------------------------------------------

    def test_ligne_avec_adhesion_active_dans_un_autre_club_echoue_sans_bloquer_la_ligne_suivante(self):
        premier_club = ClubFactory()
        second_club = ClubFactory()
        recruteur_second_club = MembershipFactory(club=second_club)
        membre_premier_club = MembershipFactory(club=premier_club, status=Membership.Status.ACTIVE)
        original_user_id = membre_premier_club.user_id

        csv_content = (
            "email,prenom,nom\n"
            f"{membre_premier_club.user.email},{membre_premier_club.user.first_name},"
            f"{membre_premier_club.user.last_name}\n"
            "nouveau@example.com,Nouveau,Joueur\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=second_club,
            imported_by=recruteur_second_club.user,
            csv_file=_csv_upload(csv_content),
        )

        assert summary.batch.row_count_success == 1
        assert summary.batch.row_count_failed == 1
        assert len(summary.rows) == 2
        # Ligne 1 (email deja actif dans premier_club) : echec, message present.
        assert summary.rows[0].line_number == 2
        assert summary.rows[0].outcome == "failed"
        assert summary.rows[0].message
        # Ligne 2 (email totalement nouveau) : traitee normalement malgre
        # l'echec de la ligne precedente.
        assert summary.rows[1].line_number == 3
        assert summary.rows[1].outcome == "created"
        # Aucune seconde adhesion n'a ete creee pour le compte de la ligne 1.
        assert Membership.all_objects.filter(user_id=original_user_id).count() == 1
        assert not Membership.all_objects.filter(club=second_club, user_id=original_user_id).exists()
        # La ligne 2, elle, a bien cree son adhesion dans second_club.
        assert Membership.all_objects.filter(
            club=second_club, user__email="nouveau@example.com"
        ).exists()

    # -----------------------------------------------------------------
    # En-tetes anglaises (bug remarques.md) : les exports reels du club
    # pilote (``data/cotisations_membres_categorie_*.csv``) utilisent
    # ``email,first_name,last_name,position,jersey_number,birth_date``,
    # pas les en-tetes francaises du CDC 4.1. Doivent etre acceptees a
    # l'identique, insensible a la casse et aux accents.
    # -----------------------------------------------------------------

    def test_en_tetes_anglaises_pures_sont_acceptees(self):
        """En-tetes exactes des vrais fichiers du club pilote."""

        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,first_name,last_name,position,jersey_number,birth_date\n"
            "joueur.un@example.com,PAUL,DURAND,,1,01/01/1970\n"
            "joueur.deux@example.com,MARC,LEROY,Attaquant,2,\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_success == 2
        assert summary.batch.row_count_failed == 0
        premier = Membership.all_objects.get(club=club, user__email="joueur.un@example.com")
        assert premier.user.first_name == "PAUL"
        assert premier.user.last_name == "DURAND"
        assert premier.jersey_number == 1
        assert premier.user.birth_date == date(1970, 1, 1)
        second = Membership.all_objects.get(club=club, user__email="joueur.deux@example.com")
        assert second.position == Membership.Position.FORWARD
        assert second.jersey_number == 2

    def test_en_tetes_anglaises_completes_toutes_colonnes_facultatives(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,first_name,last_name,phone,position,jersey_number,birth_date,"
            "weight_kg,height_cm,contribution_type\n"
            "complet@example.com,Complet,Test,0900000000,Milieu,15,10/05/1995,75.5,180,Mensuelle\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 0
        membership = Membership.all_objects.get(club=club, user__email="complet@example.com")
        assert membership.user.phone == "0900000000"
        assert membership.position == Membership.Position.MIDFIELDER
        assert membership.jersey_number == 15
        assert membership.user.birth_date == date(1995, 5, 10)
        assert membership.user.weight_kg == Decimal("75.5")
        assert membership.user.height_cm == Decimal("180")
        assert membership.requested_contribution_type_label == "Mensuelle"

    def test_en_tetes_francaises_pures_toujours_acceptees_non_regression(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,prenom,nom,telephone,poste,numero,date_naissance,poids,taille,type_cotisation\n"
            "francais@example.com,Francais,Test,0911111111,Gardien,1,05/05/1990,70,175,Libre\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 0
        membership = Membership.all_objects.get(club=club, user__email="francais@example.com")
        assert membership.user.first_name == "Francais"
        assert membership.user.phone == "0911111111"
        assert membership.position == Membership.Position.GOALKEEPER
        assert membership.jersey_number == 1

    def test_en_tetes_avec_casse_differente_sont_acceptees(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "EMAIL,First_Name,LAST_NAME,Position\n"
            "casse@example.com,Casse,Test,Defender\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 0
        membership = Membership.all_objects.get(club=club, user__email="casse@example.com")
        assert membership.user.first_name == "Casse"
        assert membership.position == Membership.Position.DEFENDER

    def test_en_tete_prenom_avec_accent_est_acceptee(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,Prénom,nom\naccent@example.com,Accent,Test\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 0
        membership = Membership.all_objects.get(club=club, user__email="accent@example.com")
        assert membership.user.first_name == "Accent"

    def test_melange_den_tetes_francaises_et_anglaises_est_accepte(self):
        """Cas peu probable en pratique (un fichier melangeant les deux
        jeux d'en-tetes selon les colonnes) mais couvert explicitement :
        chaque colonne est resolue independamment des autres."""

        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = (
            "email,prenom,last_name,position,numero\n"
            "melange@example.com,Melange,Test,Gardien,7\n"
        )

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        assert summary.batch.row_count_failed == 0
        membership = Membership.all_objects.get(club=club, user__email="melange@example.com")
        assert membership.user.first_name == "Melange"
        assert membership.user.last_name == "Test"
        assert membership.position == Membership.Position.GOALKEEPER
        assert membership.jersey_number == 7

    def test_rapport_csv_joint_liste_exactement_les_lignes_en_echec_et_leur_message(self):
        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        csv_content = "email,prenom,nom\n,Sans,Email\nvalide@example.com,Valide,Joueur\n"

        summary = clubs_services.import_players_from_csv(
            club=club, imported_by=recruteur.user, csv_file=_csv_upload(csv_content)
        )

        summary.batch.report_file.open("rb")
        try:
            content = summary.batch.report_file.read().decode("utf-8")
        finally:
            summary.batch.report_file.close()

        assert "2" in content
        assert "failed" in content
        assert "email manquant" in content
        assert "3" in content
        assert "created" in content
