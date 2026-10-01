"""Modeles de l'app sport (taches 3.2-3.4).

Sources : CDC 4.7-4.11 (entrainements, matchs, discipline, evaluations,
plan tactique) ; docs/lot0/schema-donnees.md §5 (Event, Session,
Attendance, TeamAssignment, Match, MatchComposition, MatchSheet,
MatchGoal, Incident, Suspension, Evaluation, TacticalPlan,
TacticalPlanPlacement, TacticalPlanAnnotation) ; 10.2 n° 6, 7, 8, 9, 16,
17, 25, 29, 31, 32, 38 ; CLAUDE.md regle n° 5 (dette/suspendu/inapte/en
attente jamais composable ni placeable, y compris manuellement).

Toutes les regles d'eligibilite (dette, suspension, inaptitude, attente
d'adhesion), de verrouillage a minuit et de suspension automatique
vivent dans ``apps.sport.services`` -- ce module ne porte que la
structure des donnees et les coherences purement structurelles
(meme club, meme type d'evenement...), conformement a CLAUDE.md
section 5.

Un seul ajout au-dela du schema documente (justifie ci-dessous) :
``Suspension.credited_events`` -- mecanisme technique d'idempotence
pour la commande cron qui incremente ``matches_served`` (tache 3.4),
absent de docs/lot0/schema-donnees.md §5.9 parce que ce document ne
detaille pas le mecanisme d'incrementation lui-meme.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.clubs.models import Club, Membership, Season
from apps.core.models import TenantModel

# Reutilise l'enumeration des postes deja definie sur ``Membership``
# (CDC 4.1) : aucune duplication d'enum pour "Gardien/Defenseur/
# Milieu/Attaquant", utilisee ici par ``MatchComposition.position`` et
# ``TacticalPlanPlacement.position_override`` (4.8, 4.11).
Position = Membership.Position


class Formation(models.TextChoices):
    """Bibliotheque de formations nommees, definie au niveau du module pour
    etre partagee sans duplication entre ``Session`` (formation par
    equipe A/B, extension validee par le client le 30/09/2026, pas
    encore ecrite au CDC -- comparable par sa nature aux extensions du
    10.2 comme le n° 24 ; voir le compte rendu de cette tache) et
    ``TacticalPlan`` (CDC 4.11), qui expose la meme enumeration sous
    ``TacticalPlan.Formation`` (alias, pas une copie) pour ne rien casser
    cote appelants existants."""

    F_4_4_2 = "4-4-2", "4-4-2"
    F_4_3_3 = "4-3-3", "4-3-3"
    F_4_2_3_1 = "4-2-3-1", "4-2-3-1"
    F_3_5_2 = "3-5-2", "3-5-2"
    F_3_4_3 = "3-4-3", "3-4-3"
    F_5_3_2 = "5-3-2", "5-3-2"
    F_4_1_4_1 = "4-1-4-1", "4-1-4-1"
    F_4_5_1 = "4-5-1", "4-5-1"
    CUSTOM = "custom", "Personnalisée"


class Event(TenantModel):
    """Evenement commun a une seance ou un match (schema §5.1, CDC 6.4).

    ``Session`` et ``Match`` en heritent chacun en relation 1-1 (leur
    champ ``event`` est leur cle primaire).
    """

    class Kind(models.TextChoices):
        SESSION = "session", "Séance"
        MATCH = "match", "Match"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    event_date = models.DateField(help_text="Dans le fuseau du club (CDC 4.7).")
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="events")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", help_text="Coach (CDC 4.7, 4.8)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    unlocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Superuser ayant deverrouille un evenement de la veille (CDC 4.7).",
    )
    unlocked_at = models.DateTimeField(null=True, blank=True)
    unlock_reason = models.TextField(blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Événement"
        verbose_name_plural = "Événements"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.kind} du {self.event_date} (club {self.club_id})"

    def clean(self):
        if self.season_id and self.club_id and self.season.club_id != self.club_id:
            raise ValidationError("La saison doit appartenir au même club que l'événement.")
        if self.season_id and self.event_date and not (
            self.season.start_date <= self.event_date <= self.season.end_date
        ):
            raise ValidationError("La date de l'événement doit être comprise dans la saison choisie.")
        if self.unlocked_by_id and not self.unlocked_at:
            raise ValidationError("Un déverrouillage doit porter une date/heure.")
        if self.unlocked_by_id and not (self.unlock_reason or "").strip():
            raise ValidationError(
                "Un déverrouillage par le Superuser doit porter un motif écrit (CLAUDE.md règle n° 6)."
            )


class Session(TenantModel):
    """Séance d'entraînement (CDC 4.7 ; schema §5.2).

    ``team_a_formation``/``team_b_formation`` : extension validée par le
    client le 30/09/2026 (pas encore écrite au CDC, comparable par sa
    nature aux extensions actées au 10.2 comme le n° 24 -- voir le
    compte rendu de cette tâche), portée par la séance et non par
    ``TeamAssignment`` : une formation s'applique à toute une équipe pour
    la séance, pas à un joueur. Les deux champs sont indépendants : le
    Coach choisit librement une formation par équipe (ex. A en 4-4-2, B
    en 4-3-3). Vides tant que le Coach n'a pas encore choisi -- aucune
    valeur par défaut imposée, à la différence des couleurs de maillot.
    """

    event = models.OneToOneField(Event, primary_key=True, on_delete=models.CASCADE, related_name="session")
    gathering_time = models.TimeField(help_text="Heure de rassemblement.")
    late_arrival_cutoff = models.TimeField(help_text="Heure limite d'arrivée.")
    location = models.CharField(max_length=160, blank=True, help_text="Terrain (facultatif).")
    team_a_color = models.CharField(max_length=7, help_text="Défaut issu de ClubSettings (bleu).")
    team_b_color = models.CharField(max_length=7, help_text="Défaut issu de ClubSettings (rouge).")
    team_a_formation = models.CharField(
        max_length=10,
        choices=Formation.choices,
        blank=True,
        default="",
        help_text="Formation de l'équipe A pour cette séance (facultative).",
    )
    team_b_formation = models.CharField(
        max_length=10,
        choices=Formation.choices,
        blank=True,
        default="",
        help_text="Formation de l'équipe B pour cette séance, indépendante de l'équipe A.",
    )
    instructions = models.TextField(blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Séance"
        verbose_name_plural = "Séances"

    def __str__(self) -> str:  # pragma: no cover
        return f"Séance {self.event_id}"

    def clean(self):
        if self.event_id and self.event.kind != Event.Kind.SESSION:
            raise ValidationError("Une séance doit être rattachée à un événement de type 'séance'.")
        if self.event_id and self.club_id and self.event.club_id != self.club_id:
            raise ValidationError("La séance doit porter le même club que son événement.")


class Match(TenantModel):
    """Match (CDC 4.8 ; schema §5.5)."""

    class MatchType(models.TextChoices):
        FRIENDLY = "friendly", "Amical"
        CHAMPIONSHIP = "championship", "Championnat"
        TOURNAMENT = "tournament", "Tournoi"

    class Venue(models.TextChoices):
        HOME = "home", "Domicile"
        AWAY = "away", "Extérieur"

    class ChallengeStatus(models.TextChoices):
        NOT_APPLICABLE = "n_a", "Sans objet"
        PROPOSED = "proposed", "Proposé"
        ACCEPTED = "accepted", "Accepté"
        DECLINED = "declined", "Refusé"

    event = models.OneToOneField(Event, primary_key=True, on_delete=models.CASCADE, related_name="match")
    opponent_club = models.ForeignKey(
        Club, null=True, blank=True, on_delete=models.PROTECT, related_name="+", help_text="Adversaire Vesta (défi)."
    )
    opponent_name = models.CharField(max_length=160, blank=True, help_text="Équipe extérieure saisie en texte.")
    match_type = models.CharField(max_length=13, choices=MatchType.choices)
    venue = models.CharField(max_length=4, choices=Venue.choices)
    kickoff_time = models.TimeField()
    location = models.CharField(max_length=160, blank=True)
    challenge_status = models.CharField(
        max_length=10, choices=ChallengeStatus.choices, default=ChallengeStatus.NOT_APPLICABLE
    )
    challenge_to_club = models.ForeignKey(
        Club, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    is_composition_published = models.BooleanField(default=False)
    composition_published_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Match"
        verbose_name_plural = "Matchs"

    def __str__(self) -> str:  # pragma: no cover
        return f"Match {self.event_id}"

    def clean(self):
        if self.event_id and self.event.kind != Event.Kind.MATCH:
            raise ValidationError("Un match doit être rattaché à un événement de type 'match'.")
        if self.event_id and self.club_id and self.event.club_id != self.club_id:
            raise ValidationError("Le match doit porter le même club que son événement.")
        if not self.opponent_club_id and not (self.opponent_name or "").strip():
            raise ValidationError("Indiquez un club adverse Vesta ou le nom d'une équipe extérieure.")
        if self.challenge_status != self.ChallengeStatus.NOT_APPLICABLE and not self.challenge_to_club_id:
            raise ValidationError("Un défi doit désigner le club destinataire.")


class Attendance(TenantModel):
    """Pointage (CDC 4.7, 4.8, 6.6 ; schema §5.3)."""

    class Status(models.TextChoices):
        PRESENT = "present", "Présent"
        LATE_ABSENT = "late_absent", "En retard, compté absent"
        ABSENT = "absent", "Absent"
        EXCUSED_ABSENT = "excused_absent", "Absence excusée"

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="attendances")
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="attendances")
    status = models.CharField(max_length=15, choices=Status.choices)
    excused_reason = models.TextField(blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    client_uuid = models.UUIDField(null=True, blank=True, help_text="Pointage hors connexion (6.6).")
    client_recorded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Pointage"
        verbose_name_plural = "Pointages"
        constraints = [
            models.UniqueConstraint(fields=["event", "membership"], name="attendance_unique_event_membership"),
            models.UniqueConstraint(fields=["club", "client_uuid"], name="attendance_unique_client_uuid"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Pointage {self.membership_id} @ {self.event_id}"

    def clean(self):
        if self.event_id and self.club_id and self.event.club_id != self.club_id:
            raise ValidationError("Le pointage doit porter le même club que l'événement.")
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("Le pointage doit porter le même club que l'adhésion.")
        if self.status in (self.Status.PRESENT, self.Status.LATE_ABSENT) and not self.arrived_at:
            raise ValidationError("Une heure d'arrivée est requise pour un pointage présent ou en retard.")
        if self.client_uuid and not self.client_recorded_at:
            raise ValidationError("Un pointage hors connexion doit porter l'heure réelle de la saisie.")


class TeamAssignment(TenantModel):
    """Répartition en équipe A/B d'une séance (CDC 4.7 ; schema §5.4).

    **Rattachée uniquement à une ``Session``** (décision documentée dans
    le compte rendu de la tâche 3.2) : la matrice 2.4 mentionne la
    répartition A/B sur la ligne « Séances et matchs », mais
    `sport-feuille-de-match.md` §7 (point ouvert 2) tranche déjà, à
    titre provisoire, que le pointage d'un match n'affiche « que le
    pointage, sans terrains A/B » au MVP -- ce module suit cette
    position déjà actée par `ui-designer`, sans la rouvrir.

    La zone « Non répartis » (10.2 n° 29, n° 38) n'est **jamais** un
    champ stocké ici : elle se déduit, à la lecture, de l'absence de
    ligne pour un ``(session, membership)`` pointé -- voir
    ``apps.sport.services.get_unassigned_players``.

    ``is_on_field``/``x_coord``/``y_coord`` : extension validée par le
    client le 30/09/2026 (pas encore écrite au CDC -- voir le compte
    rendu de cette tâche). Une ligne par ``(session, membership)`` reste
    l'unité naturelle : la position sur le terrain est un attribut du
    joueur au sein de son équipe pour cette séance, pas une entité à
    part -- à la différence du plan tactique (``TacticalPlanPlacement``,
    CDC 4.11), délibérément non dupliqué ici (besoin différent : une
    séance d'entraînement, pas un plan de match). Même précision de
    coordonnées (0-100, ``max_digits=5``, ``decimal_places=2``) que
    ``TacticalPlanPlacement`` pour rester cohérent. ``is_on_field=False``
    (banc) implique toujours des coordonnées nulles ; ``True`` (terrain)
    les exige toutes les deux -- voir :meth:`clean` et les contraintes
    ci-dessous. Le plafond de 11 joueurs « sur le terrain » par équipe et
    l'échange de place ne sont **pas** des contraintes de base (un
    comptage n'est pas exprimable proprement en ``CheckConstraint``) :
    appliqués par ``apps.sport.services.place_team_player``, seul point
    d'écriture légitime de ces trois champs.
    """

    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name="assignments")
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="team_assignments")

    class Team(models.TextChoices):
        A = "A", "Équipe A"
        B = "B", "Équipe B"

    team = models.CharField(max_length=1, choices=Team.choices)
    arrival_order = models.PositiveIntegerField(help_text="Ordre d'arrivée, base de l'alternance (10.2 n° 7).")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    is_on_field = models.BooleanField(
        default=False,
        help_text="Sur le terrain (True) ou sur le banc (False) -- extension du 30/09/2026.",
    )
    x_coord = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Position sur le terrain (0-100), nulle si sur le banc.",
    )
    y_coord = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Position sur le terrain (0-100), nulle si sur le banc.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Répartition A/B"
        verbose_name_plural = "Répartitions A/B"
        constraints = [
            models.UniqueConstraint(fields=["session", "membership"], name="team_assignment_unique_session_member"),
            models.CheckConstraint(condition=Q(arrival_order__gt=0), name="team_assignment_arrival_order_gt_0"),
            models.CheckConstraint(
                condition=Q(x_coord__isnull=True) | (Q(x_coord__gte=0) & Q(x_coord__lte=100)),
                name="team_assignment_x_coord_range",
            ),
            models.CheckConstraint(
                condition=Q(y_coord__isnull=True) | (Q(y_coord__gte=0) & Q(y_coord__lte=100)),
                name="team_assignment_y_coord_range",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_on_field=True, x_coord__isnull=False, y_coord__isnull=False)
                    | Q(is_on_field=False, x_coord__isnull=True, y_coord__isnull=True)
                ),
                name="team_assignment_field_position_consistency",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.membership_id} -> équipe {self.team} ({self.session_id})"

    def clean(self):
        if self.session_id and self.club_id and self.session.club_id != self.club_id:
            raise ValidationError("La répartition doit porter le même club que la séance.")
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("La répartition doit porter le même club que l'adhésion.")
        if self.is_on_field and (self.x_coord is None or self.y_coord is None):
            raise ValidationError("Un joueur placé sur le terrain doit avoir une position (x et y).")
        if not self.is_on_field and (self.x_coord is not None or self.y_coord is not None):
            raise ValidationError("Un joueur sur le banc ne peut pas porter de position sur le terrain.")


class MatchComposition(TenantModel):
    """Composition d'un match (CDC 4.8 ; schema §5.6)."""

    class Role(models.TextChoices):
        STARTER = "starter", "Titulaire"
        SUBSTITUTE = "substitute", "Remplaçant"

    match = models.ForeignKey(Match, on_delete=models.PROTECT, related_name="compositions")
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="match_compositions")
    role = models.CharField(max_length=10, choices=Role.choices)
    position = models.CharField(max_length=12, choices=Position.choices, help_text="Poste du jour.")
    jersey_number = models.PositiveSmallIntegerField(help_text="Numéro du jour (1-99).")
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Composition"
        verbose_name_plural = "Compositions"
        constraints = [
            models.UniqueConstraint(
                fields=["club", "match", "jersey_number"], name="composition_unique_jersey_per_match"
            ),
            models.UniqueConstraint(fields=["match", "membership"], name="composition_unique_match_member"),
            models.CheckConstraint(
                condition=Q(jersey_number__gte=1) & Q(jersey_number__lte=99),
                name="composition_jersey_number_range",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.membership_id} @ match {self.match_id} (#{self.jersey_number})"

    def clean(self):
        if self.match_id and self.club_id and self.match.club_id != self.club_id:
            raise ValidationError("La composition doit porter le même club que le match.")
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("La composition doit porter le même club que l'adhésion.")


class MatchSheet(TenantModel):
    """Feuille de match : score (CDC 4.8 ; schema §5.7)."""

    match = models.OneToOneField(Match, primary_key=True, on_delete=models.CASCADE, related_name="sheet")
    score_home = models.PositiveIntegerField()
    score_away = models.PositiveIntegerField()
    filled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    filled_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Feuille de match"
        verbose_name_plural = "Feuilles de match"

    def __str__(self) -> str:  # pragma: no cover
        return f"Score {self.match_id} : {self.score_home}-{self.score_away}"

    def clean(self):
        if self.match_id and self.club_id and self.match.club_id != self.club_id:
            raise ValidationError("La feuille de match doit porter le même club que le match.")


class MatchGoal(TenantModel):
    """But d'un match (CDC 4.8 ; schema §5.7)."""

    match_sheet = models.ForeignKey(MatchSheet, on_delete=models.PROTECT, related_name="goals")
    scorer_membership = models.ForeignKey(
        Membership, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    assist_membership = models.ForeignKey(
        Membership, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    minute = models.PositiveSmallIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "But"
        verbose_name_plural = "Buts"
        constraints = [
            models.CheckConstraint(
                condition=Q(minute__isnull=True) | (Q(minute__gte=0) & Q(minute__lte=130)),
                name="match_goal_minute_range",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"But {self.pk} @ {self.match_sheet_id}"

    def clean(self):
        if self.match_sheet_id and self.club_id and self.match_sheet.club_id != self.club_id:
            raise ValidationError("Le but doit porter le même club que la feuille de match.")
        if (
            self.scorer_membership_id
            and self.assist_membership_id
            and self.scorer_membership_id == self.assist_membership_id
        ):
            raise ValidationError("Le passeur décisif doit être différent du buteur.")


class Incident(TenantModel):
    """Incident disciplinaire (CDC 4.9 ; schema §5.8)."""

    class IncidentType(models.TextChoices):
        YELLOW_CARD = "yellow_card", "Carton jaune"
        RED_CARD = "red_card", "Carton rouge"
        INTERNAL_SANCTION = "internal_sanction", "Sanction interne"

    class Cause(models.TextChoices):
        CONTESTATION = "contestation", "Contestation"
        SERIOUS_FOUL = "serious_foul", "Faute grossière"
        BEHAVIOUR = "behaviour", "Comportement"
        LATENESS = "lateness", "Retard"
        OTHER = "other", "Autre"

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="incidents")
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="incidents")
    incident_type = models.CharField(max_length=18, choices=IncidentType.choices)
    minute = models.PositiveSmallIntegerField(null=True, blank=True)
    cause = models.CharField(max_length=15, choices=Cause.choices)
    cause_detail = models.TextField(blank=True)
    issued_by = models.CharField(max_length=160, blank=True, help_text="Arbitre ou auteur de la sanction.")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    recorded_at = models.DateTimeField()

    class Meta(TenantModel.Meta):
        verbose_name = "Incident"
        verbose_name_plural = "Incidents"
        constraints = [
            models.CheckConstraint(
                condition=Q(minute__isnull=True) | (Q(minute__gte=0) & Q(minute__lte=130)),
                name="incident_minute_range",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.incident_type} — {self.membership_id} @ {self.event_id}"

    def clean(self):
        if self.event_id and self.club_id and self.event.club_id != self.club_id:
            raise ValidationError("L'incident doit porter le même club que l'événement.")
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("L'incident doit porter le même club que l'adhésion.")


class Suspension(TenantModel):
    """Suspension disciplinaire (CDC 4.9 ; schema §5.9).

    ``credited_events`` : ajout au-delà du schéma documenté, réservé à
    l'usage interne de ``apps.sport.services.advance_suspensions_for_elapsed_matches``
    (tâche 3.4) -- garantit l'idempotence de la commande cron qui
    incrémente ``matches_served`` (un même match ne compte jamais deux
    fois, même si la commande est rejouée).
    """

    class Reason(models.TextChoices):
        CUMULATIVE_YELLOW = "cumulative_yellow", "Cumul de cartons jaunes"
        RED_CARD = "red_card", "Carton rouge"
        INTERNAL = "internal", "Sanction interne"

    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="suspensions")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    triggering_incident = models.ForeignKey(
        Incident, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="+")
    matches_total = models.PositiveIntegerField()
    matches_served = models.PositiveIntegerField(default=0)
    starts_event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="+")
    lifted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    credited_events = models.ManyToManyField(Event, blank=True, related_name="+")

    class Meta(TenantModel.Meta):
        verbose_name = "Suspension"
        verbose_name_plural = "Suspensions"
        constraints = [
            models.CheckConstraint(condition=Q(matches_total__gt=0), name="suspension_matches_total_gt_0"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Suspension {self.membership_id} ({self.matches_served}/{self.matches_total})"

    def clean(self):
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("La suspension doit porter le même club que l'adhésion.")
        if self.season_id and self.club_id and self.season.club_id != self.club_id:
            raise ValidationError("La suspension doit porter le même club que la saison.")
        if self.starts_event_id and self.club_id and self.starts_event.club_id != self.club_id:
            raise ValidationError("La suspension doit porter le même club que l'événement déclencheur.")
        if (
            self.triggering_incident_id
            and self.membership_id
            and self.triggering_incident.membership_id != self.membership_id
        ):
            raise ValidationError("L'incident déclencheur doit concerner le même joueur.")

    @property
    def is_active(self) -> bool:
        """Vrai si la suspension s'applique encore (schema §5.9)."""

        return self.matches_served < self.matches_total and self.lifted_at is None


#: Champs de note d'``Evaluation`` (module-level : un comprehension dans
#: ``Meta`` ne voit pas l'espace de noms de la classe englobante, seulement
#: le module -- particularité de Python, pas de Django).
_EVALUATION_SCORE_FIELDS = (
    "overall_score",
    "technical_score",
    "physical_score",
    "tactical_score",
    "mental_score",
    "attitude_score",
)


class Evaluation(TenantModel):
    """Évaluation d'un joueur (CDC 4.10 ; schema §5.10).

    La note retenue en cas de plusieurs évaluateurs (moyenne) et le
    verrouillage à 48 h ne sont **jamais stockés** : calculés à la
    lecture par ``apps.sport.services`` (invariant J1, schema-donnees.md
    §15), comme le score moyen d'un joueur ou son état « verrouillé ».
    """

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="evaluations")
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="evaluations")
    evaluator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    overall_score = models.DecimalField(max_digits=3, decimal_places=1)
    technical_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    physical_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    tactical_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    mental_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    attitude_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    comment = models.TextField(blank=True)
    comment_visible_to_player = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Évaluation"
        verbose_name_plural = "Évaluations"
        constraints = [
            models.UniqueConstraint(
                fields=["event", "membership", "evaluator"], name="evaluation_unique_event_member_evaluator"
            ),
        ] + [
            models.CheckConstraint(
                condition=Q(**{f"{field}__isnull": True})
                | (Q(**{f"{field}__gte": 0}) & Q(**{f"{field}__lte": 10})),
                name=f"evaluation_{field}_range",
            )
            for field in _EVALUATION_SCORE_FIELDS
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Évaluation {self.membership_id} @ {self.event_id} par {self.evaluator_id}"

    def clean(self):
        if self.event_id and self.club_id and self.event.club_id != self.club_id:
            raise ValidationError("L'évaluation doit porter le même club que l'événement.")
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("L'évaluation doit porter le même club que l'adhésion.")


class TacticalPlan(TenantModel):
    """Plan tactique (CDC 4.11 ; schema §5.11)."""

    # Alias (pas une copie) de l'enumeration au niveau module, partagee
    # avec ``Session.team_a_formation``/``team_b_formation`` (extension
    # du 30/09/2026) : ``TacticalPlan.Formation`` continue de fonctionner
    # a l'identique pour tout appelant existant (serializers, tests).
    Formation = Formation

    SQUAD_SIZE_CHOICES = ((7, 7), (8, 8), (11, 11))

    name = models.CharField(max_length=120)
    formation = models.CharField(max_length=10, choices=Formation.choices)
    squad_size = models.PositiveSmallIntegerField(choices=SQUAD_SIZE_CHOICES)
    match = models.ForeignKey(Match, null=True, blank=True, on_delete=models.PROTECT, related_name="tactical_plans")
    duplicated_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Plan tactique"
        verbose_name_plural = "Plans tactiques"
        constraints = [
            models.CheckConstraint(condition=Q(squad_size__in=[7, 8, 11]), name="tactical_plan_squad_size_valid"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    def clean(self):
        if self.match_id and self.club_id and self.match.club_id != self.club_id:
            raise ValidationError("Le plan doit porter le même club que le match rattaché.")
        if self.squad_size != 11 and self.formation != self.Formation.CUSTOM:
            # Point ouvert non tranché (sport-plan-tactique.md §8, point 3) :
            # aucune bibliothèque de formations nommées à 7/8 n'est
            # confirmée par le client. Position provisoire : ces effectifs
            # n'utilisent que la formation « Personnalisée » tant que la
            # bibliothèque n'est pas validée (voir compte rendu).
            raise ValidationError(
                "À effectif réduit (7 ou 8 joueurs), seule la formation « Personnalisée » est "
                "disponible pour l'instant (bibliothèque à confirmer par le client)."
            )


class TacticalPlanPlacement(TenantModel):
    """Emplacement d'un joueur sur un plan (CDC 4.11 ; schema §5.11)."""

    plan = models.ForeignKey(TacticalPlan, on_delete=models.CASCADE, related_name="placements")
    membership = models.ForeignKey(Membership, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    x_coord = models.DecimalField(max_digits=5, decimal_places=2)
    y_coord = models.DecimalField(max_digits=5, decimal_places=2)
    jersey_number_override = models.PositiveSmallIntegerField(null=True, blank=True)
    position_override = models.CharField(max_length=12, choices=Position.choices, blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Emplacement du plan"
        verbose_name_plural = "Emplacements du plan"
        constraints = [
            models.UniqueConstraint(fields=["plan", "membership"], name="placement_unique_plan_member"),
            models.CheckConstraint(
                condition=Q(x_coord__gte=0) & Q(x_coord__lte=100), name="placement_x_coord_range"
            ),
            models.CheckConstraint(
                condition=Q(y_coord__gte=0) & Q(y_coord__lte=100), name="placement_y_coord_range"
            ),
            models.CheckConstraint(
                condition=Q(jersey_number_override__isnull=True)
                | (Q(jersey_number_override__gte=1) & Q(jersey_number_override__lte=99)),
                name="placement_jersey_number_range",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Emplacement {self.pk} du plan {self.plan_id}"

    def clean(self):
        if self.plan_id and self.club_id and self.plan.club_id != self.club_id:
            raise ValidationError("L'emplacement doit porter le même club que le plan.")
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("L'emplacement doit porter le même club que l'adhésion.")


class TacticalPlanAnnotation(TenantModel):
    """Tableau noir : flèches, zones, consignes (CDC 4.11 ; schema §5.11)."""

    class AnnotationType(models.TextChoices):
        ARROW = "arrow", "Flèche"
        ZONE = "zone", "Zone"
        NOTE = "note", "Consigne"

    class TargetLine(models.TextChoices):
        DEFENSE = "defense", "Défense"
        MIDFIELD = "midfield", "Milieu"
        ATTACK = "attack", "Attaque"

    plan = models.ForeignKey(TacticalPlan, on_delete=models.CASCADE, related_name="annotations")
    annotation_type = models.CharField(max_length=5, choices=AnnotationType.choices)
    path_data = models.TextField(blank=True, help_text="Coordonnées du tracé (JSON), requis pour flèche/zone.")
    text = models.TextField(blank=True, help_text="Consigne écrite.")
    target_membership = models.ForeignKey(
        Membership, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    target_line = models.CharField(max_length=8, choices=TargetLine.choices, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Annotation du tableau noir"
        verbose_name_plural = "Annotations du tableau noir"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.annotation_type} sur plan {self.plan_id}"

    def clean(self):
        if self.plan_id and self.club_id and self.plan.club_id != self.club_id:
            raise ValidationError("L'annotation doit porter le même club que le plan.")
        if self.target_membership_id and self.club_id and self.target_membership.club_id != self.club_id:
            raise ValidationError("La consigne doit porter le même club que l'adhésion visée.")
        if self.annotation_type in (self.AnnotationType.ARROW, self.AnnotationType.ZONE) and not (
            self.path_data or ""
        ).strip():
            raise ValidationError("Une flèche ou une zone doit porter les coordonnées de son tracé.")
        if self.target_membership_id and self.target_line:
            raise ValidationError("Une consigne cible soit un joueur, soit une ligne, jamais les deux.")
