"""Import des cotisations historiques CSV -- services (tâche 2.6 ; CDC
4.4.3, 4.4.8, 7.2, 9.2 Lot 2 ; schema-treasury.md Q17).

Couvre : aperçu sans aucune écriture, « ok » = montant plein, montant
réparti selon 4.4.3 (60 $ sur un type à 10 $ = le mois et les 5
suivants), « ok » déjà couvert par un paiement anticipé (pas de double
comptage), cellule vide, lignes en échec (joueur introuvable, ambiguïté,
valeur illisible) avec détail, import définitif = paiements normaux
consultables dans la grille et le solde, ré-import sans doublon, montants
invalides, gros fichier, extrait anonymisé des fichiers de suivi du club
pilote (soldes identiques au fichier).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.services import InvalidPinError
from apps.audit.models import AuditLog
from apps.clubs.models import ImportBatch, Membership
from apps.treasury import services
from apps.treasury.models import ContributionType, Due, Payment, PaymentAllocation, Transaction
from apps.treasury.tests.conftest import PIN, WRONG_PIN
from apps.treasury.tests.grid_helpers import (
    NOW,
    TODAY,
    YEAR,
    attach,
    attached_type,
    csv_file,
    csv_line,
    free_monthly_type,
    grid_for,
    make_dues,
    pay,
    period,
    player,
    row_of,
)

pytestmark = pytest.mark.django_db

D = Decimal


def preview(ctx, ctype, upload, *, year=YEAR, user=None, now=NOW):
    return services.preview_contribution_import(
        contribution_type=ctype, year=year, csv_file=upload, requested_by=(user or ctx.treasurer).user, now=now
    )


def run_import(ctx, ctype, upload, *, year=YEAR, user=None, pin=PIN, now=NOW):
    return services.import_contributions(
        contribution_type=ctype, year=year, csv_file=upload, imported_by=(user or ctx.treasurer).user, pin=pin, now=now
    )


def counts():
    return (
        Payment.all_objects.count(),
        Transaction.all_objects.count(),
        Due.all_objects.count(),
        PaymentAllocation.all_objects.count(),
        ImportBatch.all_objects.count() if hasattr(ImportBatch, "all_objects") else ImportBatch.objects.count(),
        AuditLog.objects.count(),
    )


def only_row(report):
    assert len(report.rows) == 1
    return report.rows[0]


def amounts(row):
    return [(line.period.month, line.amount) for line in row.payments]


@pytest.fixture
def setup(ctx):
    ctype = attached_type(ctx)
    member = player(ctx, "Adolphe", "Abedi", email="adolphe.abedi@example.com")
    attach(ctx, member, ctype)
    return ctype, member


class TestApercu:
    def test_apercu_n_ecrit_rien(self, ctx, setup):
        ctype, _ = setup
        before = counts()
        report = preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "60", "ok", "ok")]))
        assert report.is_preview and report.import_batch is None
        assert counts() == before
        row = only_row(report)
        assert row.status == "ok" and amounts(row) == [(1, D("60.00"))]
        assert len(row.dues) == 9  # janvier à septembre (Q17)

    def test_ok_seul_est_un_paiement_au_montant_plein(self, ctx, setup):
        ctype, _ = setup
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "ok")])))
        assert amounts(row) == [(1, D("10.00"))]
        assert row.payments[0].origin == "ok" and row.payments[0].paid_on == datetime.date(2026, 1, 1)

    def test_soixante_couvrent_le_mois_et_les_cinq_suivants(self, ctx, setup):
        """CDC 4.4.8 : « 60 $ sur un type à 10 $ couvrent le mois et les 5
        suivants » -- même moteur que le paiement normal."""

        ctype, _ = setup
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "60")])))
        assert amounts(row) == [(1, D("60.00"))]
        cells = row.grid_row.cells
        assert [cell.state for cell in cells[:6]] == ["paid"] * 6
        assert [cell.state for cell in cells[6:9]] == ["overdue"] * 3
        assert row.balance_before == D("0.00") and row.balance_after == D("-30.00")

    def test_ok_deja_couverts_par_le_paiement_anticipe(self, ctx, setup):
        """Fichiers de suivi réels : « 60, Ok, Ok, Ok, Ok, Ok » = un seul
        versement de 60 $, pas 110 $."""

        ctype, _ = setup
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "60", "ok", "ok", "ok", "ok", "ok")])))
        assert amounts(row) == [(1, D("60.00"))]

    def test_ok_au_dela_de_la_couverture_cree_le_complement(self, ctx, setup):
        ctype, _ = setup
        line = csv_line("Adolphe Abedi", "50", "ok", "ok", "ok", "ok", "ok", "ok")
        row = only_row(preview(ctx, ctype, csv_file([line])))
        assert amounts(row) == [(1, D("50.00")), (6, D("10.00")), (7, D("10.00"))]

    def test_ok_complete_un_mois_partiel(self, ctx, setup):
        ctype, _ = setup
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "15", "ok")])))
        assert amounts(row) == [(1, D("15.00")), (2, D("5.00"))]

    def test_cellules_vides_rien_paye_mais_montants_dus(self, ctx, setup):
        ctype, _ = setup
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi")])))
        assert row.status == "ok" and row.payments == ()
        assert [line.period.month for line in row.dues] == list(range(1, 10))
        assert row.balance_after == D("-90.00")
        assert row.summary_after.is_in_good_standing is False

    def test_montant_sur_un_mois_futur_date_du_jour(self, ctx, setup):
        ctype, _ = setup
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", *([""] * 10), "10")])))
        assert row.payments[0].period == period(11) and row.payments[0].paid_on == TODAY

    @pytest.mark.parametrize("value", ["-10", "abc", "10.555", "1,000", "10 EUR", "ok!", "1e3"])
    def test_valeur_illisible_fait_echouer_la_ligne(self, ctx, setup, value):
        ctype, _ = setup
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10", value)])))
        assert row.failed and row.payments == ()
        assert row.errors == (f"Valeur illisible en févr. 2026 : « {value} ».",)

    @pytest.mark.parametrize("value,expected", [("10$", "10.00"), ("$ 12,50", "12.50"), ("10 USD", "10.00"), ("OK", "10.00"), ("Ok", "10.00")])
    def test_valeurs_acceptees(self, ctx, setup, value, expected):
        ctype, _ = setup
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", value)])))
        assert amounts(row) == [(1, D(expected))]

    @pytest.mark.parametrize("value", ["0", "-", "—", "   "])
    def test_valeurs_equivalentes_a_rien(self, ctx, setup, value):
        ctype, _ = setup
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", value)])))
        assert row.status == "ok" and row.payments == ()


class TestRechercheDuJoueur:
    def test_email_prioritaire(self, ctx, setup):
        ctype, member = setup
        header = "email;nom;" + ";".join(["janv.", "févr."])
        upload = csv_file(["ADOLPHE.ABEDI@example.com;Nom Different;10;"], header=header)
        row = only_row(preview(ctx, ctype, upload))
        assert row.membership.pk == member.pk
        assert "joueur trouvé par son email" in row.warnings[0]

    def test_nom_dans_n_importe_quel_ordre_sans_casse_ni_accents(self, ctx, setup):
        ctype, member = setup
        for name in ("ABEDI ADOLPHE", "adolphe abédi", "  Abedi   Adolphe "):
            row = only_row(preview(ctx, ctype, csv_file([csv_line(name, "10")])))
            assert row.membership is not None and row.membership.pk == member.pk, name

    def test_email_inconnu_puis_nom(self, ctx, setup):
        ctype, member = setup
        upload = csv_file(["inconnu@example.com;Adolphe Abedi;10"], header="email;nom;janv.")
        row = only_row(preview(ctx, ctype, upload))
        assert row.membership.pk == member.pk
        assert row.warnings[0] == "Email inconnu dans ce club : joueur trouvé par son nom."

    def test_prenom_et_nom_en_deux_colonnes(self, ctx, setup):
        ctype, member = setup
        row = only_row(preview(ctx, ctype, csv_file(["Adolphe;Abedi;10"], header="prénom;nom;janv.")))
        assert row.membership.pk == member.pk

    def test_joueur_introuvable(self, ctx, setup):
        ctype, _ = setup
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe", "10")])))
        assert row.failed and row.errors == ("Joueur introuvable dans ce club (« Adolphe »).",)

    def test_nom_ambigu_echoue(self, ctx, setup):
        ctype, _ = setup
        homonym = player(ctx, "Adolphe", "Abedi")
        attach(ctx, homonym, ctype)
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10")])))
        assert row.failed and "Plusieurs joueurs du club portent le nom" in row.errors[0]

    def test_email_et_nom_de_deux_joueurs_differents(self, ctx, setup):
        ctype, _ = setup
        player(ctx, "Serge", "Kadiobo")
        upload = csv_file(["adolphe.abedi@example.com;Serge Kadiobo;10"], header="email;nom;janv.")
        row = only_row(preview(ctx, ctype, upload))
        assert row.failed and row.errors == ("L'email et le nom désignent deux joueurs différents du club : ligne ignorée.",)

    def test_joueur_parti(self, ctx, setup):
        ctype, _ = setup
        gone = player(ctx, "Ancien", "Joueur")
        gone.status = Membership.Status.DEPARTED
        gone.left_on = datetime.date(2026, 2, 28)
        gone.left_reason = Membership.LeftReason.RESIGNATION
        gone.left_by = ctx.president.user
        gone.save()
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Ancien Joueur", "10")])))
        assert row.failed and "a quitté le club" in row.errors[0]

    def test_joueur_d_un_autre_club_introuvable(self, ctx, other_ctx, setup):
        ctype, _ = setup
        player(other_ctx, "Etranger", "Autreclub", email="etranger@example.com")
        upload = csv_file(["etranger@example.com;Etranger Autreclub;10"], header="email;nom;janv.")
        row = only_row(preview(ctx, ctype, upload))
        assert row.failed and row.errors[0].startswith("Joueur introuvable dans ce club")

    def test_meme_joueur_sur_deux_lignes(self, ctx, setup):
        ctype, _ = setup
        report = preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10"), csv_line("Abedi Adolphe", "10")]))
        assert not report.rows[0].failed
        assert report.rows[1].errors == ("Joueur déjà présent à la ligne 2 : ligne ignorée.",)

    def test_ligne_sans_joueur_mais_avec_valeurs(self, ctx, setup):
        ctype, _ = setup
        report = preview(ctx, ctype, csv_file([csv_line("", "", "", "", "", "", "", "", "", "Trésorier du club")]))
        assert only_row(report).errors == ("Joueur non indiqué (colonne email ou nom vide).",)


class TestFichier:
    def test_titre_au_dessus_de_l_en_tete_colonnes_ignorees_lignes_vides(self, ctx, setup):
        ctype, _ = setup
        text = (
            "COTISATIONS MENSUELLES 2026;;;\n"
            "N°S;NOMS;Jan-26;Feb-26;Total\n"
            "01;ABEDI ADOLPHE;10;10;20\n"
            ";;;;\n"
        )
        upload = SimpleUploadedFile("f.csv", text.encode("utf-8"), content_type="text/csv")
        report = preview(ctx, ctype, upload)
        assert report.ignored_columns == ("N°S", "Total")
        assert report.ignored_lines == (1, 4)
        assert amounts(only_row(report)) == [(1, D("10.00")), (2, D("10.00"))]

    def test_separateur_virgule(self, ctx, setup):
        ctype, _ = setup
        upload = csv_file([csv_line("Adolphe Abedi", "10", '"12,5"', delimiter=",")], delimiter=",")
        assert amounts(only_row(preview(ctx, ctype, upload))) == [(1, D("10.00")), (2, D("12.50"))]

    @pytest.mark.parametrize(
        "header",
        ["Nom;janvier;février", "Nom;Jan-26;Feb-26", "Nom;01/2026;02/2026", "Nom;2026-01;2026-02", "Nom;1;2", "Nom;jan 2026;fev 2026"],
    )
    def test_formats_d_en_tete_des_mois(self, ctx, setup, header):
        ctype, _ = setup
        upload = csv_file(["Adolphe Abedi;10;ok"], header=header)
        assert amounts(only_row(preview(ctx, ctype, upload))) == [(1, D("10.00")), (2, D("10.00"))]

    def test_annee_des_colonnes_differente(self, ctx, setup):
        ctype, _ = setup
        with pytest.raises(services.ContributionImportError, match="concerne l'année 2025"):
            preview(ctx, ctype, csv_file(["Adolphe Abedi;10"], header="Nom;Jan-25"))

    def test_mois_en_double(self, ctx, setup):
        ctype, _ = setup
        with pytest.raises(services.ContributionImportError, match="plusieurs colonnes"):
            preview(ctx, ctype, csv_file(["Adolphe Abedi;10;10"], header="Nom;janv.;janvier"))

    def test_en_tete_introuvable(self, ctx, setup):
        ctype, _ = setup
        with pytest.raises(services.ContributionImportError, match="En-tête introuvable"):
            preview(ctx, ctype, csv_file(["a;b;c"], header="x;y;z"))

    def test_fichier_non_utf8(self, ctx, setup):
        ctype, _ = setup
        upload = SimpleUploadedFile("f.csv", "Nom;févr.\nAbédi;10\n".encode("cp1252"), content_type="text/csv")
        with pytest.raises(services.ContributionImportError, match="UTF-8"):
            preview(ctx, ctype, upload)

    def test_fichier_binaire_refuse(self, ctx, setup):
        ctype, _ = setup
        upload = SimpleUploadedFile("f.csv", b"%PDF-1.4 binaire", content_type="text/csv")
        with pytest.raises(services.ContributionImportError):
            preview(ctx, ctype, upload)

    def test_trop_de_lignes(self, ctx, setup, monkeypatch):
        ctype, _ = setup
        monkeypatch.setattr(services, "IMPORT_MAX_ROWS", 3)
        with pytest.raises(services.ContributionImportError, match="trop volumineux"):
            preview(ctx, ctype, csv_file([csv_line(f"Joueur {i}", "10") for i in range(4)]))

    def test_annee_future_refusee(self, ctx, setup):
        ctype, _ = setup
        with pytest.raises(services.TreasuryValidationError, match="Année invalide"):
            preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10")]), year=2027)

    def test_type_archive_refuse(self, ctx, setup):
        ctype, _ = setup
        services.archive_contribution_type(contribution_type=ctype, archived_by=ctx.president.user)
        ctype.refresh_from_db()
        with pytest.raises(services.TreasuryValidationError, match="archivé"):
            preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10")]))

    def test_type_obligatoire_non_mensuel_refuse(self, ctx, fee_type):
        with pytest.raises(services.TreasuryValidationError, match="mensuels ou libres"):
            preview(ctx, fee_type, csv_file([csv_line("X", "10")]))


class TestRoles:
    @pytest.mark.parametrize("role", ["president", "vice_president", "player"])
    def test_seuls_tresorier_et_adjoint(self, ctx, setup, role):
        ctype, _ = setup
        with pytest.raises(services.TreasuryPermissionError):
            preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10")]), user=getattr(ctx, role))
        with pytest.raises(services.TreasuryPermissionError):
            run_import(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10")]), user=getattr(ctx, role))

    def test_adjoint_autorise(self, ctx, setup):
        ctype, _ = setup
        report = run_import(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10")]), user=ctx.assistant_treasurer)
        assert report.success_count == 1


class TestImportDefinitif:
    def test_paiements_normaux_consultables_dans_la_grille_et_le_solde(self, ctx, setup):
        ctype, member = setup
        upload_lines = [csv_line("Adolphe Abedi", "60", "ok", "ok", "ok", "ok", "ok", "", "10")]
        expected = only_row(preview(ctx, ctype, csv_file(upload_lines)))
        report = run_import(ctx, ctype, csv_file(upload_lines))
        row = only_row(report)
        assert row.status == "imported" and report.import_batch is not None

        payments = list(Payment.all_objects.filter(membership=member).order_by("paid_on"))
        assert [(p.amount, p.paid_on) for p in payments] == [
            (D("60.00"), datetime.date(2026, 1, 1)),
            (D("10.00"), datetime.date(2026, 8, 1)),
        ]
        for payment in payments:
            assert payment.source == Payment.Source.CSV_IMPORT
            assert payment.method == Payment.Method.HISTORICAL_IMPORT
            assert payment.import_batch_id == report.import_batch.pk
            assert payment.receipt_number is not None
            assert payment.reference.startswith("Import historique ")
            assert payment.transaction.status == Transaction.Status.SUCCEEDED and payment.transaction.sealed_at
        dues = Due.all_objects.filter(membership=member, contribution_type=ctype)
        assert dues.count() == 9 and set(dues.values_list("source", flat=True)) == {Due.Source.IMPORT}
        assert services.verify_chain(ctx.club).ok

        grid_row = row_of(grid_for(ctx, ctype), member)
        assert grid_row.cells == expected.grid_row.cells
        assert grid_row.total == D("70.00")
        summary = services.get_balance_summary(member, at_date=TODAY)
        assert summary.balance == expected.balance_after == D("-20.00")

    def test_journal_et_lot_d_import(self, ctx, setup):
        ctype, member = setup
        report = run_import(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10"), csv_line("Inconnu Total", "10")]))
        batch = report.import_batch
        assert batch.import_type == ImportBatch.ImportType.HISTORICAL_CONTRIBUTIONS
        assert (batch.row_count_success, batch.row_count_failed) == (1, 1)
        assert batch.source_file and batch.report_file
        report_text = batch.report_file.open("rb").read().decode("utf-8")
        assert "Joueur introuvable dans ce club (« Inconnu Total »)." in report_text
        actions = set(AuditLog.objects.values_list("action_type", flat=True))
        assert {
            "treasury.contribution_import.completed",
            "treasury.payment.validated",
            "treasury.due.imported",
        } <= actions
        log = AuditLog.objects.get(action_type="treasury.contribution_import.completed")
        assert PIN not in str(log.after)

    def test_rapport_lignes_reussies_et_en_echec(self, ctx, setup):
        ctype, _ = setup
        player(ctx, "Serge", "Kadiobo")
        lines = [
            csv_line("Adolphe Abedi", "10"),
            csv_line("Personne Inconnue", "10"),
            csv_line("Serge Kadiobo", "dix"),
        ]
        report = run_import(ctx, ctype, csv_file(lines))
        assert (report.success_count, report.failed_count) == (1, 2)
        failed = {row.line_number: row.errors for row in report.rows if row.failed}
        assert failed == {
            3: ("Joueur introuvable dans ce club (« Personne Inconnue »).",),
            4: ("Valeur illisible en janv. 2026 : « dix ».",),
        }
        assert Payment.all_objects.count() == 1

    def test_reimport_identique_sans_doublon(self, ctx, setup):
        ctype, member = setup
        lines = [csv_line("Adolphe Abedi", "30", "ok", "ok", "ok", "10")]
        run_import(ctx, ctype, csv_file(lines))
        before = (Payment.all_objects.count(), Due.all_objects.count())
        balance = services.get_balance(member, at_date=TODAY)

        again_preview = only_row(preview(ctx, ctype, csv_file(lines)))
        assert again_preview.payments == () and len(again_preview.already_imported) == 3
        assert again_preview.dues == ()
        report = run_import(ctx, ctype, csv_file(lines))
        assert report.success_count == 1 and report.payments_count == 0 and report.already_imported_count == 3
        assert (Payment.all_objects.count(), Due.all_objects.count()) == before
        assert services.get_balance(member, at_date=TODAY) == balance

    def test_fichier_complete_le_mois_suivant(self, ctx, setup):
        ctype, _ = setup
        run_import(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10", "10")]))
        report = run_import(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10", "10", "10")]))
        row = only_row(report)
        assert amounts(row) == [(3, D("10.00"))] and len(row.already_imported) == 2
        assert Payment.all_objects.count() == 3

    def test_montant_modifie_apres_import_fait_echouer_la_ligne(self, ctx, setup):
        ctype, _ = setup
        run_import(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10")]))
        row = only_row(run_import(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "20")])))
        assert row.failed and "déjà été importé" in row.errors[0] and "annulation" in row.errors[0]
        assert Payment.all_objects.count() == 1

    def test_pin_faux_rien_n_est_ecrit(self, ctx, setup):
        ctype, _ = setup
        before = counts()
        with pytest.raises(InvalidPinError):
            run_import(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10")]), pin=WRONG_PIN)
        assert counts()[:5] == before[:5]

    def test_fichier_invalide_ne_consomme_pas_d_essai_de_pin(self, ctx, setup):
        ctype, _ = setup
        for _ in range(4):
            with pytest.raises(services.ContributionImportError):
                run_import(ctx, ctype, csv_file(["x"], header="a;b"), pin=WRONG_PIN)
        run_import(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10")]))  # PIN toujours utilisable

    def test_registre_gele_refuse_tout(self, ctx, setup):
        ctype, _ = setup
        services.freeze_ledger(club=ctx.club, reason="test", actor=None, now=NOW)
        before = counts()
        with pytest.raises(services.LedgerFrozenError):
            run_import(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "10")]))
        assert counts()[:5] == before[:5]

    def test_paiement_existant_hors_import_signale(self, ctx, setup):
        ctype, member = setup
        make_dues(ctx, member, ctype, [1])
        pay(ctx, member, ctype, "10", datetime.date(2026, 1, 5))
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi", "ok", "ok")])))
        # janvier déjà couvert par le paiement existant : seul février est créé.
        assert amounts(row) == [(2, D("10.00"))]
        assert any("hors import" in warning for warning in row.warnings)


class TestMontantsDus:
    def test_joueur_entre_en_cours_d_annee_et_mois_d_arrivee(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Nouveau", "Venu", joined_on=datetime.date(2026, 4, 12))
        attach(ctx, member, ctype)
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Nouveau Venu")])))
        # B7 : le mois d'arrivée est dû en entier (proposition par défaut
        # 10.2 n° 5, non tranchée), avec la même règle d'échéance que la
        # génération mensuelle : arrivé le 12 (après le 10) -> 12 + 9 jours.
        assert [line.period.month for line in row.dues] == [4, 5, 6, 7, 8, 9]
        assert row.dues[0].due_date == datetime.date(2026, 4, 21)
        assert not any("Mois d'arrivée" in warning for warning in row.warnings)
        assert any("Aucun montant dû créé pour janv. 2026, févr. 2026, mars 2026" in warning for warning in row.warnings)

    def test_rattachement_tardif(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Tardif", "Rattache")
        attach(ctx, member, ctype, starts_on=period(6))
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Tardif Rattache", "", "", "", "", "", "10")])))
        assert [line.period.month for line in row.dues] == [6, 7, 8, 9]
        failed = only_row(preview(ctx, ctype, csv_file([csv_line("Tardif Rattache", "ok")])))
        assert failed.failed and "aucun montant n'est dû" in failed.errors[0]

    def test_tarif_anterieur_a_la_creation_du_type(self, ctx):
        ctype = services.create_contribution_type(
            club=ctx.club,
            created_by=ctx.president.user,
            name="Créé en juin",
            nature=ContributionType.Nature.MANDATORY,
            periodicity=ContributionType.Periodicity.MONTHLY,
            amount="20",
            scope=ContributionType.Scope.ATTACHED,
            now=datetime.datetime(2026, 6, 3, tzinfo=datetime.timezone.utc),
        )
        member = player(ctx, "Ancien", "Membre")
        attach(ctx, member, ctype)
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Ancien Membre", "ok")])))
        assert amounts(row) == [(1, D("20.00"))]
        assert [line.amount for line in row.dues] == [D("20.00")] * 9
        assert any("premier tarif connu (20.00 USD)" in warning for warning in row.warnings)

    def test_montant_du_existant_jamais_recree(self, ctx, setup):
        ctype, member = setup
        make_dues(ctx, member, ctype, [1, 2])
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Adolphe Abedi")])))
        assert [line.period.month for line in row.dues] == list(range(3, 10))


class TestTypeLibre:
    def test_import_type_libre_sans_dette(self, ctx):
        ctype = free_monthly_type(ctx, amount="3")
        member = player(ctx, "Genereux", "Donateur")
        report = run_import(ctx, ctype, csv_file([csv_line("Genereux Donateur", "5", "", "ok")]))
        row = only_row(report)
        assert amounts(row) == [(1, D("5.00")), (3, D("3.00"))] and row.dues == ()
        assert Due.all_objects.filter(membership=member).count() == 0
        grid_row = row_of(grid_for(ctx, ctype), member)
        assert {cell.state for cell in grid_row.cells} == {"free"}
        assert services.get_balance(member, at_date=TODAY) == D("0.00")

    def test_ok_sans_montant_suggere(self, ctx):
        ctype = free_monthly_type(ctx, name="Spéciale", amount=None)
        player(ctx, "Genereux", "Donateur")
        row = only_row(preview(ctx, ctype, csv_file([csv_line("Genereux Donateur", "ok")])))
        assert row.failed and "pas de montant suggéré" in row.errors[0]


class TestGrosFichier:
    def test_apercu_de_cinq_cents_lignes(self, ctx):
        """Limite du fichier (500 lignes) : l'aperçu reste une lecture, sans
        aucune écriture, et chaque ligne est traitée."""

        ctype = attached_type(ctx)
        lines = []
        for index in range(services.IMPORT_MAX_ROWS):
            member = player(ctx, f"Prenom{index:03d}", f"Nom{index:03d}")
            attach(ctx, member, ctype)
            lines.append(csv_line(f"Nom{index:03d} Prenom{index:03d}", "30", "ok", "ok", "10", "", "", "ok"))
        before = counts()
        report = preview(ctx, ctype, csv_file(lines))
        assert counts() == before
        assert (report.success_count, report.failed_count) == (services.IMPORT_MAX_ROWS, 0)
        # 30 (janvier à mars) + 10 (avril) + ok (juillet, non couvert) = 50 $.
        assert report.payments_total == D("50.00") * services.IMPORT_MAX_ROWS

    def test_import_de_soixante_joueurs(self, ctx):
        ctype = attached_type(ctx)
        lines = []
        for index in range(60):
            member = player(ctx, f"Prenom{index:03d}", f"Nom{index:03d}")
            attach(ctx, member, ctype)
            lines.append(csv_line(f"Nom{index:03d} Prenom{index:03d}", "30", "ok", "ok", "10", "10", "", "ok", "ok"))
        report = run_import(ctx, ctype, csv_file(lines))
        assert (report.success_count, report.failed_count) == (60, 0)
        # 30 + 10 + 10 + ok (juillet) + ok (août) = 70 $ par joueur.
        assert report.payments_total == D("70.00") * 60
        assert Payment.all_objects.filter(source=Payment.Source.CSV_IMPORT).count() == 5 * 60
        balances = services.get_balances(ctx.club, at_date=TODAY)
        imported = Membership.all_objects.filter(user__first_name__startswith="Prenom")
        assert {balances[m.pk] for m in imported} == {D("-20.00")}
        assert services.verify_chain(ctx.club).ok


# Extrait anonymisé d'un fichier de suivi réel du club pilote (catégorie à
# 10 $, année 2026) : mêmes valeurs de cellules, noms remplacés. Solde
# attendu au 15/09/2026 = total versé - 9 mois échus x 10 $.
PILOT_EXTRACT = [
    ("Joueur Alpha", ["10", "10", "10", "10", "Ok"], D("50")),
    ("Joueur Bravo", ["60", "Ok", "Ok", "Ok", "Ok", "Ok"], D("60")),
    # 30 $ couvrent janvier à mars ; avril « Ok » non couvert = 10 $ versés.
    ("Joueur Charlie", ["30", "Ok", "Ok", "Ok"], D("40")),
    ("Joueur Delta", [], D("0")),
    ("Joueur Echo", ["50", "Ok", "Ok", "Ok", "Ok", "Ok", "Ok"], D("70")),
    ("Joueur Foxtrot", ["10", "10", "50", "Ok", "Ok", "Ok", "Ok"], D("70")),
    ("Joueur Golf", ["", "", "10"], D("10")),
    ("Joueur Hotel", ["10", "10", "10", "10", "10", "10", "Ok", "Ok"], D("80")),
    ("Joueur India", ["10"] * 11, D("110")),
    ("Joueur Juliet", ["30", "10", "10", "Ok", "Ok"], D("50")),
    ("Joueur Kilo", ["", "10", "10", "10", "10"], D("40")),
    ("Joueur Lima", ["10", "", "", "", "Ok"], D("20")),
    ("Joueur Mike", ["10", "", "", "Ok", "Ok", "Ok"], D("40")),
    ("Joueur November", ["120"] + ["Ok"] * 11, D("120")),
]


class TestExtraitClubPilote:
    def test_soldes_identiques_au_fichier(self, ctx):
        ctype = attached_type(ctx, name="Mensuelle catégorie 10")
        members = {}
        for name, _, _ in PILOT_EXTRACT:
            first, last = name.split(" ")
            members[name] = player(ctx, first, last)
            attach(ctx, members[name], ctype)
        header = "N°S;NOMS;Jan-26;Feb-26;Mar-26;Apr-26;May-26;Jun-26;Jul-26;aout 2026;Sep-26;Oct-26;Nov-26;Dec-26"
        body = [f"{index:02d};{name.upper()};" + ";".join(cells + [""] * (12 - len(cells)))
                for index, (name, cells, _) in enumerate(PILOT_EXTRACT, start=1)]
        text = "COTISATIONS MENSUELLES 2026 (catégorie 10$)\n" + header + "\n" + "\n".join(body)
        text += "\n;;;;;;;;;;Trésorier du club;;;\n"
        upload = SimpleUploadedFile("suivi.csv", text.encode("utf-8"), content_type="text/csv")

        report = run_import(ctx, ctype, upload)
        assert report.success_count == len(PILOT_EXTRACT)
        assert [row.errors for row in report.rows if row.failed] == [
            ("Joueur non indiqué (colonne email ou nom vide).",)
        ]
        grid = grid_for(ctx, ctype)
        for name, _, paid in PILOT_EXTRACT:
            member = members[name]
            assert services.get_balance(member, at_date=TODAY) == paid - D("90"), name
            assert row_of(grid, member).total == min(paid, D("120")), name
