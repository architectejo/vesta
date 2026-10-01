"""Tests HTTP de l'import CSV des joueurs (CDC 4.1 ; matrice 2.4 ; tache 1.4).

Verifie que l'endpoint respecte la colonne « Ajout et import de joueurs »
de la matrice 2.4 (« É » President, « D » joueur recruteur designe) et le
critere de fin exact de la tache 1.4 (plan-lots.md) : « Import de 40
joueurs sans poste ni date reussit sans echec ».
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import ClubFactory, MembershipFactory, MembershipRoleFactory


def _csv_upload(content: str, name: str = "import.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


def _authenticated_client(user) -> APIClient:
    """Meme principe que apps.clubs.tests.test_views_roles : jeton d'acces
    reel, pour que le club actif soit resolu depuis l'adhesion reelle
    (CLAUDE.md regle n9)."""

    client = APIClient()
    access_token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return client


@pytest.mark.django_db
class TestPlayerImportView:
    def test_le_president_importe_des_joueurs(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)

        # Prefixe "recrue" (pas "joueur") : evite toute collision avec la
        # sequence d'emails `UserFactory`/`SuperuserFactory`
        # (`joueur{n}@example.com`, partagee par `MembershipFactory.added_by`).
        csv_content = "email,prenom,nom\nrecrue1@example.com,Joueur,Un\nrecrue2@example.com,Joueur,Deux\n"

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["row_count_success"] == 2
        assert response.data["row_count_failed"] == 0
        assert response.data["failed_rows"] == []
        assert Membership.all_objects.filter(club=club, user__email="recrue1@example.com").exists()

    def test_un_recruteur_designe_peut_importer(self):
        """Matrice 2.4 : « D » -- joueur designe par le President (CDC 2.3,
        ``MembershipRole.Role.PLAYER_RECRUITER``)."""

        club = ClubFactory()
        recruteur = MembershipFactory(club=club)
        MembershipRoleFactory(membership=recruteur, role=MembershipRole.Role.PLAYER_RECRUITER)
        client = _authenticated_client(recruteur.user)

        csv_content = "email,prenom,nom\njoueur@example.com,Joueur,Test\n"

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["row_count_success"] == 1

    def test_un_simple_joueur_est_refuse(self):
        club = ClubFactory()
        joueur = MembershipFactory(club=club)
        client = _authenticated_client(joueur.user)

        csv_content = "email,prenom,nom\njoueur@example.com,Joueur,Test\n"

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Membership.all_objects.filter(club=club, user__email="joueur@example.com").exists()

    def test_le_coach_seul_est_refuse(self):
        """Matrice 2.4 : comme toute fonction hors President, le Coach a bien
        « D » sur cette colonne -- mais seulement via une designation
        explicite du President (CDC 2.4 ligne 170, role
        ``MembershipRole.Role.PLAYER_RECRUITER``). Ici le Coach n'a pas
        cette designation : il est donc refuse, comme un simple joueur."""

        club = ClubFactory()
        coach = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach, role=MembershipRole.Role.COACH)
        client = _authenticated_client(coach.user)

        csv_content = "email,prenom,nom\njoueur@example.com,Joueur,Test\n"

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_hors_authentification_est_refuse(self):
        client = APIClient()
        csv_content = "email,prenom,nom\njoueur@example.com,Joueur,Test\n"

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_fichier_non_csv_est_refuse(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)

        response = client.post(
            reverse("clubs:players-import"),
            {"file": SimpleUploadedFile("import.txt", b"email,prenom,nom\n", content_type="text/plain")},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_import_de_40_joueurs_sans_poste_ni_date_reussit_sans_echec(self):
        """Critere de fin exact de la tache 1.4 (plan-lots.md)."""

        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)

        lines = ["email,prenom,nom,poste,date_naissance"]
        for i in range(40):
            lines.append(f"quarante{i}@example.com,Prenom{i},Nom{i},,")
        csv_content = "\n".join(lines)

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["row_count_success"] == 40
        assert response.data["row_count_failed"] == 0

    def test_lignes_en_echec_sont_listees_avec_numero_et_message(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)

        csv_content = "email,prenom,nom\n,Sans,Email\nvalide@example.com,Valide,Joueur\n"

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["row_count_success"] == 1
        assert response.data["row_count_failed"] == 1
        assert len(response.data["failed_rows"]) == 1
        assert response.data["failed_rows"][0]["line_number"] == 2
        assert "Ligne 2" in response.data["failed_rows"][0]["message"]

    # -----------------------------------------------------------------
    # Revue independante (tache 1.4t) : permissions (cumul de roles
    # ACTIFS uniquement) et etancheite multi-tenant sur l'endpoint HTTP.
    # -----------------------------------------------------------------

    def test_un_membre_du_bureau_sans_designation_explicite_est_refuse(self):
        """Matrice 2.4 : la colonne « Ajout et import de joueurs » est
        « D » (seulement si designe par le President) pour TOUTES les
        fonctions autres que le President -- y compris le bureau (VP,
        Directeur sportif, Tresorier...). Porter un role du bureau ne
        donne donc, par lui-meme, aucun droit d'import : seule la
        designation explicite (``PLAYER_RECRUITER``) le fait."""

        club = ClubFactory()
        vice_president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=vice_president, role=MembershipRole.Role.VICE_PRESIDENT)
        client = _authenticated_client(vice_president.user)

        csv_content = "email,prenom,nom\njoueur@example.com,Joueur,Test\n"

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Membership.all_objects.filter(club=club, user__email="joueur@example.com").exists()

    def test_cumul_coach_et_recruteur_designe_peut_importer(self):
        """CDC 2.2 : « Un joueur peut cumuler plusieurs roles [...] Ses
        droits sont alors l'union des droits de ses roles ». Un Coach
        EN PLUS designe comme recruteur doit pouvoir importer -- le
        cumul ne doit jamais retirer un droit par ailleurs accorde."""

        club = ClubFactory()
        coach_recruteur = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach_recruteur, role=MembershipRole.Role.COACH)
        MembershipRoleFactory(
            membership=coach_recruteur, role=MembershipRole.Role.PLAYER_RECRUITER
        )
        client = _authenticated_client(coach_recruteur.user)

        csv_content = "email,prenom,nom\njoueur@example.com,Joueur,Test\n"

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Membership.all_objects.filter(club=club, user__email="joueur@example.com").exists()

    def test_un_recruteur_dont_le_role_a_ete_revoque_est_refuse(self):
        """CDC 2.2 : le cumul de droits ne porte que sur les roles
        ACTIFS -- un role revoque (mais toujours present en base, jamais
        supprime) ne doit plus donner aucun droit d'import."""

        club = ClubFactory()
        ancien_recruteur = MembershipFactory(club=club)
        role = MembershipRoleFactory(
            membership=ancien_recruteur, role=MembershipRole.Role.PLAYER_RECRUITER
        )
        role.revoked_by = ancien_recruteur.user
        role.revoked_at = timezone.now()
        role.revoked_reason = "Retire du recrutement"
        role.save()
        client = _authenticated_client(ancien_recruteur.user)

        csv_content = "email,prenom,nom\njoueur@example.com,Joueur,Test\n"

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Membership.all_objects.filter(club=club, user__email="joueur@example.com").exists()

    def test_falsifier_un_identifiant_de_club_dans_la_requete_est_sans_effet(self):
        """CLAUDE.md regle n9 : le club actif se deduit de l'adhesion
        reelle, jamais d'un parametre transmis par le client. Un President
        du club A qui glisse un identifiant du club B dans le corps de la
        requete ne doit jamais faire basculer l'import vers ce club B."""

        club_a = ClubFactory()
        club_b = ClubFactory()
        president_a = MembershipFactory(club=club_a)
        MembershipRoleFactory(membership=president_a, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president_a.user)

        csv_content = "email,prenom,nom\nfalsifie@example.com,Falsifie,Test\n"

        response = client.post(
            reverse("clubs:players-import"),
            {
                "file": _csv_upload(csv_content),
                "club_id": club_b.id,
                "club": club_b.id,
                "club_slug": club_b.slug,
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Membership.all_objects.filter(club=club_a, user__email="falsifie@example.com").exists()
        assert not Membership.all_objects.filter(club=club_b, user__email="falsifie@example.com").exists()

    def test_import_mixte_valide_et_invalide_le_rapport_distingue_correctement_les_deux(self):
        """Critere de fin exact de la tache 1.4 (plan-lots.md) : le rapport
        doit distinguer correctement les lignes reussies des lignes en
        echec sur un fichier MELANGEANT les deux -- pas seulement un
        fichier entierement valide (deja couvert par le test des 40
        joueurs) ni entierement en echec."""

        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)

        lines = ["email,prenom,nom,poste"]
        for i in range(30):
            lines.append(f"mixte-valide{i}@example.com,Prenom{i},Nom{i},")
        for i in range(10):
            lines.append(f",Sans,Email{i},")  # 10 lignes en echec (email manquant)
        csv_content = "\n".join(lines)

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["row_count_success"] == 30
        assert response.data["row_count_failed"] == 10
        assert len(response.data["failed_rows"]) == 10
        assert all("email manquant" in row["message"] for row in response.data["failed_rows"])

    def test_le_rapport_joint_est_coherent_avec_la_reponse_http(self):
        """Le ``report_file`` attache au lot doit correspondre exactement
        au detail des echecs renvoye dans la reponse HTTP (CDC 4.1)."""

        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)

        csv_content = "email,prenom,nom\n,Sans,Email\nvalide@example.com,Valide,Joueur\n"

        response = client.post(
            reverse("clubs:players-import"),
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["report_file_url"]  # une URL de telechargement authentifiee est bien renvoyee

        from apps.clubs.models import ImportBatch

        batch = ImportBatch.all_objects.get(pk=response.data["id"])
        batch.report_file.open("rb")
        try:
            report_content = batch.report_file.read().decode("utf-8")
        finally:
            batch.report_file.close()

        assert "email manquant" in report_content
        assert str(response.data["failed_rows"][0]["line_number"]) in report_content

    def test_fichier_non_utf8_ne_doit_jamais_faire_planter_lendpoint(self):
        """Bug trouve par la revue 1.4t et corrige : un fichier CSV encode en
        Latin-1 levait une ``UnicodeDecodeError`` brute jusqu'a la vue (voir
        le test service equivalent,
        ``test_fichier_non_utf8_devrait_echouer_proprement_avec_un_message_francais``
        dans ``test_services_player_import.py``). ``PlayerImportView.post``
        capture desormais ``PlayerImportError`` et renvoie une reponse HTTP
        400 avec un message en francais."""

        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)

        raw = "email,prenom,nom\naccent@example.com,Pr\xe9nom,Nom\n".encode("latin-1")
        csv_file = SimpleUploadedFile("import.csv", raw, content_type="text/csv")

        response = client.post(
            reverse("clubs:players-import"),
            {"file": csv_file},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "detail" in response.data
