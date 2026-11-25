"""Tests du service d'audit `create_audit_log` (tache 1.6, 1.6t).

Sources : CDC 5.1 (contenu d'une entree), 5.2 (« Medical » : contenu
jamais copie) ; CLAUDE.md regles n6, n11 ; docs/lot0/schema-donnees.md
§1.3, §12.1.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog
from apps.audit.services import CLINICAL_FIELD_BLACKLIST, MedicalContentInLogError, create_audit_log
from apps.clubs.tests.factories import ClubFactory


@pytest.mark.django_db
class TestCreateAuditLog:
    def test_cree_une_entree_avec_etat_avant_apres_en_json(self):
        actor = UserFactory()
        club = ClubFactory()

        entry = create_audit_log(
            actor=actor,
            club=club,
            action_type="role.appointed",
            object_type="MembershipRole",
            object_id=42,
            before=None,
            after={"role": "coach", "membership_id": 7},
        )

        assert isinstance(entry, AuditLog)
        assert entry.pk is not None
        stored = AuditLog.objects.get(pk=entry.pk)
        assert stored.before is None
        assert stored.after == {"role": "coach", "membership_id": 7}
        assert stored.club_id == club.id
        assert stored.actor_id == actor.id
        assert stored.object_type == "MembershipRole"
        assert stored.object_id == "42"

    def test_club_facultatif_pour_une_action_de_plateforme(self):
        """schema §1.2, §12.1 : `club` vide pour une action de portee plateforme."""

        actor = UserFactory()

        entry = create_audit_log(
            actor=actor,
            club=None,
            action_type="platform.licence.activated",
            object_type="Licence",
            object_id=1,
        )

        assert entry.club_id is None

    def test_acteur_obligatoire(self):
        with pytest.raises(ValidationError):
            create_audit_log(
                actor=None,
                club=None,
                action_type="test.action",
                object_type="X",
                object_id=1,
            )

    def test_type_action_obligatoire(self):
        actor = UserFactory()
        with pytest.raises(ValidationError):
            create_audit_log(actor=actor, club=None, action_type="", object_type="X", object_id=1)

    def test_objet_concerne_obligatoire(self):
        actor = UserFactory()
        with pytest.raises(ValidationError):
            create_audit_log(actor=actor, club=None, action_type="test.action", object_type="", object_id=1)


@pytest.mark.django_db
class TestGardeFouContenuMedical:
    """CLAUDE.md regle n11 ; CDC 5.2 « Medical »."""

    @pytest.mark.parametrize("field", ["before", "after"])
    @pytest.mark.parametrize(
        "clinical_key", ["diagnosis", "notes", "circumstances", "medical_history", "severity"]
    )
    def test_action_medicale_avec_cle_clinique_est_rejetee(self, field, clinical_key):
        actor = UserFactory()
        payload = {clinical_key: "contenu clinique sensible"}

        with pytest.raises(MedicalContentInLogError):
            create_audit_log(
                actor=actor,
                club=None,
                action_type="medical.record.updated",
                object_type="HealthRecord",
                object_id=1,
                **{field: payload},
            )

        # Garantie forte : aucune entree partielle n'est ecrite en base.
        assert not AuditLog.objects.filter(action_type="medical.record.updated").exists()

    def test_action_medicale_sans_cle_clinique_est_acceptee(self):
        """Seule la metadonnee (type d'objet, identifiant) est journalisee (CDC 5.2)."""

        actor = UserFactory()

        entry = create_audit_log(
            actor=actor,
            club=None,
            action_type="medical.record.viewed",
            object_type="HealthRecord",
            object_id=7,
            before=None,
            after=None,
        )

        assert entry.before is None
        assert entry.after is None

    # Champs explicitement marques « Medecin + joueur uniquement » (ou
    # equivalent) dans docs/lot0/schema-donnees.md §6.1 (`HealthRecord`),
    # §6.2 (`Injury`), §6.3 (`InjuryFollowUp`). Recopie volontairement
    # figee ici (independante de `CLINICAL_FIELD_BLACKLIST`) : si un jour
    # le schema ajoute/retire un champ clinique sans que la liste noire du
    # service ne soit mise a jour en consequence, ce test doit le reveler
    # (CLAUDE.md regle n11 ; CDC 5.2 « Medical »).
    SCHEMA_CLINICAL_FIELDS = frozenset(
        {
            # HealthRecord §6.1
            "blood_group",
            "allergies",
            "medical_history",
            "ongoing_treatments",
            # Injury §6.2
            "circumstances",
            "location_on_body",
            "severity",
            "on_site_care",
            "referral",
            # InjuryFollowUp §6.3
            "note",
        }
    )

    @pytest.mark.parametrize("field_name", sorted(SCHEMA_CLINICAL_FIELDS))
    def test_chaque_champ_clinique_du_schema_est_dans_la_liste_noire(self, field_name):
        """Aucun champ clinique reel du schema medical ne doit manquer a la liste noire.

        Si ce test echoue, la liste noire `CLINICAL_FIELD_BLACKLIST` n'est
        plus alignee avec docs/lot0/schema-donnees.md §6 : un champ
        clinique reel pourrait alors etre copie dans le journal (regression
        de la regle n11 CLAUDE.md / CDC 5.2).
        """

        assert field_name in CLINICAL_FIELD_BLACKLIST

    def test_self_declaration_est_dans_la_liste_noire(self):
        """`HealthRecord.self_declaration` (§6.1) : declaration de sante du joueur.

        Non marque « Medecin + joueur uniquement » mot pour mot dans le
        tableau du schema, mais c'est explicitement une declaration sur
        l'etat de sante du joueur : du contenu clinique au sens de la
        regle n11 / CDC 5.2, qui ne doit jamais apparaitre dans le journal.
        """

        assert "self_declaration" in CLINICAL_FIELD_BLACKLIST

    def test_cle_clinique_hors_domaine_medical_est_acceptee(self):
        """Le garde-fou ne s'applique qu'aux actions `medical.*` (CDC 5.2)."""

        actor = UserFactory()

        entry = create_audit_log(
            actor=actor,
            club=None,
            action_type="sport.incident.created",
            object_type="Incident",
            object_id=3,
            after={"notes": "carton jaune pour contestation"},
        )

        assert entry.after == {"notes": "carton jaune pour contestation"}


def test_clinical_keys_are_rejected_when_nested():
    from apps.audit.services import assert_no_clinical_content

    for payload in (
        {"details": {"diagnosis": "x"}},
        {"items": [{"ok": 1}, {"Notes": "x"}]},
        {"a": {"b": {"c": [{"allergies": "x"}]}}},
    ):
        with pytest.raises(MedicalContentInLogError):
            assert_no_clinical_content("medical.injury.updated", payload, field_label="after")
    # Hors domaine medical, ou sans cle clinique, rien n'est rejete.
    assert_no_clinical_content("treasury.expense.created", {"details": {"notes": "x"}}, field_label="after")
    assert_no_clinical_content("medical.injury.updated", {"details": {"id": 1}}, field_label="after")
