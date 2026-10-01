import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { getMyProfile, listClubPlayers, searchActiveClubPlayers } from "../../api/clubs";
import {
  addGoal,
  deleteGoal,
  getMatch,
  listEventIncidents,
  markMatchAttendance,
  publishComposition,
  removeFromComposition,
  setMatchScore,
  updateGoal,
  updateMatch,
  type Attendance,
  type CompositionEntry,
  type Goal,
  type MatchDetail,
  type MatchType,
  type MatchVenue,
} from "../../api/sport";
import {
  Avatar,
  Banner,
  Button,
  ConfirmDialog,
  EmptyState,
  Loader,
  Modal,
  NumberField,
  PlayerSearch,
  StatusBadge,
  SyncIndicator,
  TextField,
  useToast,
  type PlayerSearchResult,
  type StatusKey,
} from "../../design-system";
import { useOfflineActionQueue } from "../../hooks/useOfflineActionQueue";
import { reportInjury, type InjuryReportInput } from "../../api/medical";
import { getMatchEquipment, recordMatchEquipmentOut, type MatchEquipmentLine } from "../../api/logistics";
import { AddMatchEquipmentModal } from "../logistics/AddMatchEquipmentModal";
import { MatchEquipmentModal } from "../logistics/MatchEquipmentModal";
import { equipmentLineStatusKey } from "../logistics/materielLabels";
import { InjuryReportModal } from "../medical/InjuryReportModal";
import { IncidentModal } from "./IncidentModal";
import { MatchComposeModal } from "./MatchComposeModal";
import { getSportAccess } from "./sportAccess";
import { formatTime } from "./sportTime";

/** Section « Équipements reçus » (feuille de match, complète §4.5/§4.6 de
 * `docs/ecrans/logistique.md` : la modale « Ajouter des équipements » n'avait
 * pas été livrée au Lot 3 faute de route `apps.logistics`, cf. rapport de la
 * tâche 3.7). Coach seul peut sortir des équipements ; Coach et Intendant
 * peuvent enregistrer le retour (fiche §5.2, point ouvert n° 4). */
function MatchEquipmentSection({
  matchId,
  isCoach,
  onAddEquipment,
  onOpenDetail,
}: {
  matchId: number;
  isCoach: boolean;
  onAddEquipment: () => void;
  onOpenDetail: () => void;
}) {
  const equipmentQuery = useQuery({
    queryKey: ["logistics", "match-equipment", matchId],
    queryFn: () => getMatchEquipment(matchId),
  });
  const lines = equipmentQuery.data?.lines ?? [];

  return (
    <section className="rounded-md border border-border p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text">Équipements reçus</h2>
        {isCoach ? (
          <Button size="sm" variant="secondary" onClick={onAddEquipment}>
            Ajouter des équipements
          </Button>
        ) : null}
      </div>
      {equipmentQuery.isLoading ? (
        <p className="text-sm text-text-muted">Chargement…</p>
      ) : lines.length === 0 ? (
        <EmptyState
          message="Aucun équipement enregistré pour ce match."
          actionLabel={isCoach ? "Ajouter des équipements" : undefined}
          onAction={isCoach ? onAddEquipment : undefined}
        />
      ) : (
        <button type="button" onClick={onOpenDetail} className="w-full text-left">
          <ul className="divide-y divide-border">
            {lines.map((line: MatchEquipmentLine) => (
              <li key={line.article_id} className="flex items-center justify-between gap-2 py-1.5">
                <span className="text-sm text-text">
                  {line.article_name} · {line.out_quantity} sortis · {line.returned_quantity} rendus
                </span>
                <StatusBadge status={equipmentLineStatusKey(line.status)} />
              </li>
            ))}
          </ul>
        </button>
      )}
    </section>
  );
}

interface PendingMatchAttendance {
  membershipId: number;
  clientUuid: string;
  clientRecordedAt: string;
}

function matchTypeLabel(type: MatchType): string {
  return type === "friendly" ? "Amical" : type === "championship" ? "Championnat" : "Tournoi";
}

function venueLabel(venue: MatchVenue): string {
  return venue === "home" ? "Domicile" : "Extérieur";
}

function attendanceStatusKey(status: Attendance["status"]): StatusKey {
  if (status === "present") return "present";
  if (status === "late_absent") return "late";
  if (status === "excused_absent") return "excused";
  return "absent";
}

// ---------------------------------------------------------------------------
// Composition
// ---------------------------------------------------------------------------

function CompositionCard({
  match,
  canManage,
  ownMembershipId,
  onOpenCompose,
  onRemove,
  onPublish,
}: {
  match: MatchDetail;
  canManage: boolean;
  ownMembershipId: number | undefined;
  onOpenCompose: () => void;
  onRemove: (membershipId: number) => void;
  onPublish: () => void;
}) {
  const all = [...match.starters, ...match.substitutes];
  const ineligibleCount = all.filter((c) => c.no_longer_eligible).length;
  const ownEntry = all.find((c) => c.membership_id === ownMembershipId);

  return (
    <section className="rounded-md border border-border p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text">Composition</h2>
        <StatusBadge status={match.is_composition_published ? "lineup_published" : "lineup_draft"} />
      </div>

      {ownEntry ? (
        <p className="mb-2 text-sm text-text">
          Vous êtes convoqué : {ownEntry.role === "starter" ? "titulaire" : "remplaçant"}
        </p>
      ) : match.is_composition_published && ownMembershipId ? (
        <p className="mb-2 text-sm text-text-muted">Vous n'êtes pas convoqué pour ce match.</p>
      ) : null}

      {ineligibleCount > 0 && canManage ? (
        <Banner variant="warning" className="mb-2" action={<Button size="sm" variant="ghost" onClick={onOpenCompose}>Modifier la composition</Button>}>
          {ineligibleCount} joueur(s) de la composition ne peuvent plus jouer. Retirez-les ou attendez leur
          régularisation.
        </Banner>
      ) : null}

      {all.length === 0 ? (
        <EmptyState
          message={canManage ? "Aucune composition pour l'instant." : "La composition n'est pas encore publiée."}
          actionLabel={canManage ? "Composer l'équipe" : undefined}
          onAction={canManage ? onOpenCompose : undefined}
        />
      ) : (
        <div className="space-y-3">
          {(["starter", "substitute"] as const).map((role) => {
            const list = all.filter((c) => c.role === role);
            if (list.length === 0) return null;
            return (
              <div key={role}>
                <p className="mb-1 text-xs font-medium text-text-muted">
                  {role === "starter" ? `Titulaires (${list.length})` : `Remplaçants (${list.length})`}
                </p>
                <ul className="divide-y divide-border">
                  {list.map((entry) => (
                    <li key={entry.id} className="flex items-center gap-3 py-1.5">
                      <Avatar name={entry.player.name} photoUrl={entry.player.photo} size={32} />
                      <div className="min-w-0 flex-1">
                        <p className={`truncate text-sm ${entry.no_longer_eligible ? "text-text-muted" : "text-text"}`}>
                          n° {entry.jersey_number} · {entry.player.name}
                        </p>
                        {entry.no_longer_eligible ? (
                          <p className="text-xs text-text-muted">
                            {canManage ? `N'est plus sélectionnable : ${entry.no_longer_eligible.reason}` : "Indisponible"}
                          </p>
                        ) : (
                          <p className="text-xs text-text-muted">{entry.position_label}</p>
                        )}
                      </div>
                      {canManage && !match.is_composition_published ? (
                        <Button size="sm" variant="ghost" onClick={() => onRemove(entry.membership_id)}>
                          Retirer
                        </Button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
          {canManage && !match.is_composition_published ? (
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={onOpenCompose}>
                Modifier la composition
              </Button>
              <Button size="sm" variant="primary" disabled={ineligibleCount > 0} onClick={onPublish}>
                Publier la composition
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Pointage simple (sans A/B)
// ---------------------------------------------------------------------------

function MatchAttendanceCard({
  match,
  roster,
  canRecord,
  pendingIds,
  onMark,
}: {
  match: MatchDetail;
  roster: { membership_id: number; first_name: string; last_name: string; photo: string | null; jersey_number: number | null }[];
  canRecord: boolean;
  pendingIds: Set<number>;
  onMark: (membershipId: number) => void;
}) {
  const byMember = useMemo(() => {
    const map = new Map<number, Attendance>();
    for (const a of match.attendances) map.set(a.membership_id, a);
    return map;
  }, [match.attendances]);

  const notMarked = roster.filter((p) => !byMember.has(p.membership_id) && !pendingIds.has(p.membership_id));

  return (
    <section className="rounded-md border border-border p-3">
      <h2 className="mb-2 text-sm font-semibold text-text">Pointage</h2>
      <p className="mb-2 flex flex-wrap gap-3 text-sm">
        <span className="text-status-success-fg">Présents {match.attendance_counts.present}</span>
        <span className="text-status-danger-fg">En retard {match.attendance_counts.late}</span>
        <span className="text-text-muted">Non pointés {match.attendance_counts.not_marked}</span>
      </p>
      <ul className="divide-y divide-border">
        {match.attendances.map((a) => (
          <li key={a.id} className="flex items-center gap-3 py-1.5">
            <Avatar name={a.player.name} photoUrl={a.player.photo} size={32} />
            <span className="min-w-0 flex-1 truncate text-sm text-text">{a.player.name}</span>
            <span className="text-xs text-text-muted">{formatTime(a.arrived_at)}</span>
            <StatusBadge status={attendanceStatusKey(a.status)} />
          </li>
        ))}
        {canRecord
          ? notMarked.map((p) => (
              <li key={p.membership_id} className="flex items-center gap-3 py-1.5">
                <Avatar name={`${p.first_name} ${p.last_name}`} photoUrl={p.photo} size={32} />
                <span className="min-w-0 flex-1 truncate text-sm text-text">
                  {p.first_name} {p.last_name}
                </span>
                <Button size="sm" variant="secondary" onClick={() => onMark(p.membership_id)}>
                  Arrivé
                </Button>
              </li>
            ))
          : null}
        {[...pendingIds].map((id) => {
          const p = roster.find((r) => r.membership_id === id);
          if (!p) return null;
          return (
            <li key={`pending-${id}`} className="flex items-center gap-3 py-1.5">
              <Avatar name={`${p.first_name} ${p.last_name}`} photoUrl={p.photo} size={32} />
              <span className="min-w-0 flex-1 truncate text-sm text-text">
                {p.first_name} {p.last_name}
              </span>
              <StatusBadge status="queued" />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Modales locales : score, but, modifier le match
// ---------------------------------------------------------------------------

function ScoreModal({
  open,
  initialHome,
  initialAway,
  onClose,
  onSubmit,
  submitting,
  error,
}: {
  open: boolean;
  initialHome: number;
  initialAway: number;
  onClose: () => void;
  onSubmit: (home: number, away: number) => void;
  submitting: boolean;
  error?: string;
}) {
  const [home, setHome] = useState<number | null>(initialHome);
  const [away, setAway] = useState<number | null>(initialAway);
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Saisir le score"
      size="sm"
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      onConfirm={() => onSubmit(home ?? 0, away ?? 0)}
    >
      <div className="space-y-4">
        <p className="text-xs text-text-muted">Les buteurs se saisissent ensuite, but par but.</p>
        <div className="grid grid-cols-2 gap-3">
          <NumberField label="Buts du club" value={home} onChange={setHome} min={0} max={99} />
          <NumberField label="Buts de l'adversaire" value={away} onChange={setAway} min={0} max={99} />
        </div>
        {error ? <p className="text-sm text-status-danger-fg">{error}</p> : null}
      </div>
    </Modal>
  );
}

function GoalModal({
  open,
  goal,
  onClose,
  onSaved,
  onDeleted,
  matchId,
}: {
  open: boolean;
  goal: Goal | null;
  matchId: number;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const [scorer, setScorer] = useState<PlayerSearchResult | null>(
    goal?.scorer
      ? {
          id: goal.scorer.membership_id,
          firstName: goal.scorer.name,
          lastName: "",
          number: goal.scorer.jersey_number,
        }
      : null,
  );
  const [assist, setAssist] = useState<PlayerSearchResult | null>(
    goal?.assist
      ? {
          id: goal.assist.membership_id,
          firstName: goal.assist.name,
          lastName: "",
          number: goal.assist.jersey_number,
        }
      : null,
  );
  const [minute, setMinute] = useState<number | null>(goal?.minute ?? null);
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function handleSubmit(): Promise<void> {
    if (!scorer) {
      setError("Choisissez le buteur.");
      return;
    }
    setSubmitting(true);
    setError(undefined);
    try {
      if (goal) {
        await updateGoal(goal.id, {
          scorer_membership_id: Number(scorer.id),
          assist_membership_id: assist ? Number(assist.id) : null,
          minute,
        });
      } else {
        await addGoal(matchId, {
          scorer_membership_id: Number(scorer.id),
          assist_membership_id: assist ? Number(assist.id) : null,
          minute,
        });
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(): Promise<void> {
    if (!goal) return;
    setSubmitting(true);
    try {
      await deleteGoal(goal.id);
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Suppression impossible.");
    } finally {
      setSubmitting(false);
      setConfirmDelete(false);
    }
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={goal ? "But" : "Ajouter un but"}
        size="md"
        isSubmitting={submitting}
        confirmLabel="Enregistrer"
        onConfirm={() => void handleSubmit()}
        footer={
          <div className="flex w-full items-center justify-between gap-2">
            {goal ? (
              <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
                Supprimer ce but
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button variant="secondary" onClick={onClose}>
                Annuler
              </Button>
              <Button variant="primary" loading={submitting} onClick={() => void handleSubmit()}>
                Enregistrer
              </Button>
            </div>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-text">Buteur</label>
            <PlayerSearch value={scorer} onChange={setScorer} searchPlayers={searchActiveClubPlayers} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-text">Passeur décisif (facultatif)</label>
            <PlayerSearch value={assist} onChange={setAssist} searchPlayers={searchActiveClubPlayers} />
          </div>
          <NumberField label="Minute" optional value={minute} onChange={setMinute} min={0} max={130} />
          {error ? <p className="text-sm text-status-danger-fg">{error}</p> : null}
        </div>
      </Modal>
      <ConfirmDialog
        open={confirmDelete}
        title="Supprimer ce but ?"
        description="Les statistiques des joueurs seront recalculées."
        confirmLabel="Supprimer"
        onConfirm={() => void handleDelete()}
        onCancel={() => setConfirmDelete(false)}
        loading={submitting}
      />
    </>
  );
}

function MatchEditModal({
  open,
  match,
  onClose,
  onUpdated,
}: {
  open: boolean;
  match: MatchDetail;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [eventDate, setEventDate] = useState(match.event_date);
  const [kickoff, setKickoff] = useState(match.kickoff_time.slice(0, 5));
  const [location, setLocation] = useState(match.location);
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(): Promise<void> {
    setSubmitting(true);
    setError(undefined);
    try {
      await updateMatch(match.id, {
        event_date: eventDate,
        kickoff_time: kickoff,
        match_type: match.match_type,
        venue: match.venue,
        location,
      });
      onUpdated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Modifier le match"
      size="md"
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <label className="block text-sm font-medium text-text">
          Date
          <input
            type="date"
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
            value={eventDate}
            onChange={(e) => setEventDate(e.target.value)}
          />
        </label>
        <label className="block text-sm font-medium text-text">
          Coup d'envoi
          <input
            type="time"
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
            value={kickoff}
            onChange={(e) => setKickoff(e.target.value)}
          />
        </label>
        <TextField label="Lieu" optional value={location} onChange={setLocation} />
        {error ? <p className="text-sm text-status-danger-fg">{error}</p> : null}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Page « Match »
// ---------------------------------------------------------------------------

export function MatchPage() {
  const { id } = useParams();
  const matchId = Number(id);
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [composeOpen, setComposeOpen] = useState(false);
  const [scoreOpen, setScoreOpen] = useState(false);
  const [scoreSubmitting, setScoreSubmitting] = useState(false);
  const [goalModal, setGoalModal] = useState<{ open: boolean; goal: Goal | null }>({ open: false, goal: null });
  const [editOpen, setEditOpen] = useState(false);
  const [incidentOpen, setIncidentOpen] = useState(false);
  const [removeConfirm, setRemoveConfirm] = useState<number | null>(null);
  const [addEquipmentOpen, setAddEquipmentOpen] = useState(false);
  const [equipmentDetailOpen, setEquipmentDetailOpen] = useState(false);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const access = getSportAccess(profileQuery.data?.roles);
  // Équipements reçus (fiche `logistique.md` §5.2, §4.5) : Coach seul sort
  // du matériel ; Coach et Intendant enregistrent le retour.
  const isSteward = profileQuery.data?.roles.some((r) => r.role === "steward") ?? false;

  const matchQuery = useQuery({
    queryKey: ["sport", "match", matchId],
    queryFn: () => getMatch(matchId),
    enabled: Number.isFinite(matchId),
    refetchInterval: 15_000,
  });

  const rosterQuery = useQuery({
    queryKey: ["clubs", "players", "active"],
    queryFn: () => listClubPlayers({ status: "active" }),
  });

  const incidentsQuery = useQuery({
    queryKey: ["sport", "incidents", matchId],
    queryFn: () => listEventIncidents(matchId, { limit: 20 }),
    enabled: Number.isFinite(matchId),
  });

  const pendingQueue = useOfflineActionQueue<PendingMatchAttendance>({
    storageKey: `vesta.offline.match-attendance.${matchId}`,
    processItem: async (payload) => {
      await markMatchAttendance(matchId, {
        membership_id: payload.membershipId,
        arrived_at: payload.clientRecordedAt,
        client_uuid: payload.clientUuid,
        client_recorded_at: payload.clientRecordedAt,
      });
      void queryClient.invalidateQueries({ queryKey: ["sport", "match", matchId] });
    },
    onRejected: (_payload, message) => showToast(message),
  });

  // Déclaration de blessure hors connexion (CDC 6.6 ; medical.md §4.1).
  const [injuryOpen, setInjuryOpen] = useState(false);
  const injuryQueue = useOfflineActionQueue<InjuryReportInput>({
    storageKey: `vesta.offline.injury-report.match.${matchId}`,
    processItem: async (payload) => {
      await reportInjury(payload);
      void queryClient.invalidateQueries({ queryKey: ["sport", "match", matchId] });
    },
    onRejected: (_payload, message) => showToast(message),
  });

  const pendingIds = new Set(pendingQueue.items.map((i) => i.payload.membershipId));

  async function handleMark(membershipId: number): Promise<void> {
    const clientUuid = crypto.randomUUID();
    const clientRecordedAt = new Date().toISOString();
    if (!navigator.onLine) {
      pendingQueue.enqueue({ membershipId, clientUuid, clientRecordedAt });
      showToast("Pointage enregistré sur ce téléphone. Il sera envoyé au retour du réseau.");
      return;
    }
    try {
      await markMatchAttendance(matchId, {
        membership_id: membershipId,
        arrived_at: clientRecordedAt,
        client_uuid: clientUuid,
        client_recorded_at: clientRecordedAt,
      });
      void queryClient.invalidateQueries({ queryKey: ["sport", "match", matchId] });
      showToast(`Pointé à ${formatTime(clientRecordedAt)}.`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 0) {
        pendingQueue.enqueue({ membershipId, clientUuid, clientRecordedAt });
        showToast("Vous êtes hors connexion. Le pointage sera envoyé au retour du réseau.");
      } else {
        showToast(error instanceof ApiError ? error.detail : "Pointage non enregistré. Réessayez.");
      }
    }
  }

  async function handleRemove(membershipId: number): Promise<void> {
    try {
      await removeFromComposition(matchId, membershipId);
      void queryClient.invalidateQueries({ queryKey: ["sport", "match", matchId] });
      setRemoveConfirm(null);
    } catch (error) {
      showToast(error instanceof ApiError ? error.detail : "Retrait impossible.");
    }
  }

  async function handlePublish(): Promise<void> {
    try {
      await publishComposition(matchId);
      void queryClient.invalidateQueries({ queryKey: ["sport", "match", matchId] });
      showToast("Composition publiée.");
    } catch (error) {
      showToast(error instanceof ApiError ? error.detail : "Publication impossible.");
    }
  }

  async function handleScore(home: number, away: number): Promise<void> {
    setScoreSubmitting(true);
    try {
      await setMatchScore(matchId, { score_home: home, score_away: away });
      void queryClient.invalidateQueries({ queryKey: ["sport", "match", matchId] });
      setScoreOpen(false);
      showToast("Score enregistré.");
    } catch (error) {
      if (error instanceof ApiError && error.status === 0) {
        showToast("Score enregistré sur ce téléphone. Il sera envoyé au retour du réseau.");
        setScoreOpen(false);
      } else {
        showToast(error instanceof ApiError ? error.detail : "Enregistrement impossible.");
      }
    } finally {
      setScoreSubmitting(false);
    }
  }

  if (profileQuery.isLoading || matchQuery.isLoading || rosterQuery.isLoading) {
    return <Loader loading variant="page" />;
  }
  if (matchQuery.isError) {
    return (
      <EmptyState variant="error" message="Impossible de charger le match." actionLabel="Réessayer" onAction={() => void matchQuery.refetch()} />
    );
  }
  const match = matchQuery.data;
  if (!match) return null;
  const roster = rosterQuery.data ?? [];

  const goalsFromScore = match.sheet?.goals ?? [];
  const scoredCount = goalsFromScore.length;
  const scoreMismatch = match.sheet ? scoredCount < match.sheet.score_home : false;

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold text-text">
              {profileQuery.data?.club.name} – {match.opponent}
            </h1>
            <p className="text-sm text-text-muted">
              {matchTypeLabel(match.match_type)} · {venueLabel(match.venue)} · {match.event_date} {match.kickoff_time.slice(0, 5)}
              {match.location ? ` · ${match.location}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={match.sheet ? "lineup_published" : match.is_composition_published ? "lineup_published" : "lineup_draft"} />
            {access.canManageMatch && !match.is_locked ? (
              <Button size="sm" variant="ghost" onClick={() => setEditOpen(true)}>
                Modifier
              </Button>
            ) : null}
          </div>
        </div>
        <SyncIndicator
          isOnline={pendingQueue.isOnline}
          pendingCount={pendingQueue.pendingCount}
          isSyncing={pendingQueue.isSyncing}
          onRetry={pendingQueue.retryNow}
        />
        {injuryQueue.pendingCount > 0 || !injuryQueue.isOnline ? (
          <SyncIndicator
            isOnline={injuryQueue.isOnline}
            pendingCount={injuryQueue.pendingCount}
            isSyncing={injuryQueue.isSyncing}
            items={injuryQueue.items.map((item) => {
              const player = roster.find((p) => p.membership_id === item.payload.membership_id);
              const name = player ? `${player.first_name} ${player.last_name}` : `joueur n° ${item.payload.membership_id}`;
              return { id: item.id, label: `Blessure déclarée pour ${name}`, createdAt: item.createdAt };
            })}
            onRetry={injuryQueue.retryNow}
          />
        ) : null}
      </header>

      {match.challenge_status === "proposed" ? (
        <Banner variant="warning">En attente de la réponse de l'adversaire.</Banner>
      ) : match.challenge_status === "declined" ? (
        <Banner variant="danger">L'adversaire a refusé le défi.</Banner>
      ) : null}
      {match.is_locked ? <Banner variant="readonly">Ce match est verrouillé : lecture seule (les buts restent modifiables).</Banner> : null}

      {access.canManageMatch && !match.is_locked ? (
        <div className="flex flex-wrap gap-2">
          {match.starters.length === 0 && match.substitutes.length === 0 ? (
            <Button variant="primary" size="sm" onClick={() => setComposeOpen(true)}>
              Composer l'équipe
            </Button>
          ) : !match.is_composition_published ? (
            <Button
              variant="primary"
              size="sm"
              disabled={[...match.starters, ...match.substitutes].some((c) => c.no_longer_eligible)}
              onClick={() => void handlePublish()}
            >
              Publier la composition
            </Button>
          ) : !match.sheet ? (
            <Button variant="primary" size="sm" onClick={() => setScoreOpen(true)}>
              Saisir le score
            </Button>
          ) : (
            <Button variant="secondary" size="sm" onClick={() => setScoreOpen(true)}>
              Modifier le score
            </Button>
          )}
        </div>
      ) : null}

      {match.sheet ? (
        <section className="rounded-md border border-border p-3">
          <h2 className="mb-2 text-sm font-semibold text-text">Score</h2>
          <p className="text-2xl font-semibold tabular-nums text-text">
            {profileQuery.data?.club.name} {match.sheet.score_home} – {match.sheet.score_away} {match.opponent}
          </p>
          {scoreMismatch ? (
            <Banner variant="warning" className="mt-2">
              {match.sheet.score_home - scoredCount} but(s) du club sans buteur renseigné.
            </Banner>
          ) : null}
          <ul className="mt-2 space-y-1">
            {goalsFromScore.map((goal) => (
              <li key={goal.id}>
                <button
                  type="button"
                  className="text-left text-sm text-text hover:underline"
                  onClick={() => setGoalModal({ open: true, goal })}
                >
                  {goal.minute != null ? `${goal.minute}' ` : ""}
                  {goal.scorer?.name ?? "Buteur non renseigné"}
                  {goal.assist ? ` (passe : ${goal.assist.name})` : ""}
                </button>
              </li>
            ))}
          </ul>
          {access.canManageMatch ? (
            <Button size="sm" variant="secondary" className="mt-2" onClick={() => setGoalModal({ open: true, goal: null })}>
              Ajouter un but
            </Button>
          ) : null}
        </section>
      ) : null}

      <CompositionCard
        match={match}
        canManage={access.canManageMatch && !match.is_locked}
        ownMembershipId={profileQuery.data?.membership_id}
        onOpenCompose={() => setComposeOpen(true)}
        onRemove={(id) => setRemoveConfirm(id)}
        onPublish={() => void handlePublish()}
      />

      <MatchAttendanceCard
        match={match}
        roster={roster}
        canRecord={access.canRecordAttendance && !match.is_locked}
        pendingIds={pendingIds}
        onMark={(id) => void handleMark(id)}
      />

      <section className="rounded-md border border-border p-3">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text">Cartons et incidents</h2>
          {access.canRecordIncident ? (
            <Button size="sm" variant="secondary" onClick={() => setIncidentOpen(true)}>
              Ajouter un carton
            </Button>
          ) : null}
        </div>
        {(incidentsQuery.data?.results.length ?? 0) === 0 ? (
          <EmptyState message="Aucun incident pour l'instant." />
        ) : (
          <ul className="divide-y divide-border">
            {incidentsQuery.data!.results.slice(0, 5).map((incident) => (
              <li key={incident.id} className="py-1.5 text-sm text-text">
                {incident.player.name} — {incident.incident_type_label}
              </li>
            ))}
          </ul>
        )}
      </section>

      {access.canReportInjury || access.canSeeMedicalFull ? (
        <section className="rounded-md border border-border p-3">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text">Blessures</h2>
            {access.canReportInjury ? (
              <Button size="sm" variant="secondary" onClick={() => setInjuryOpen(true)}>
                Déclarer une blessure
              </Button>
            ) : null}
          </div>
          {access.isCaptain && !access.canSeeMedicalFull ? (
            <p className="text-sm text-text-muted">Les blessures déclarées sont suivies par le Médecin.</p>
          ) : access.canSeeMedicalFull ? (
            <p className="text-sm text-text-muted">
              La liste des blessures de ce match nécessite un point d'accès API supplémentaire (à ajouter par
              backend-dev) : elle n'est pas encore affichée ici.
            </p>
          ) : null}
        </section>
      ) : null}

      <InjuryReportModal
        open={injuryOpen}
        onClose={() => setInjuryOpen(false)}
        context={{ eventId: matchId, eventKind: "match", eventLabel: `Match contre ${match.opponent}` }}
        offline={{ isOnline: injuryQueue.isOnline, enqueue: injuryQueue.enqueue }}
        onReported={() => {
          setInjuryOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["sport", "match", matchId] });
        }}
      />

      <MatchEquipmentSection
        matchId={matchId}
        isCoach={access.isCoach}
        onAddEquipment={() => setAddEquipmentOpen(true)}
        onOpenDetail={() => setEquipmentDetailOpen(true)}
      />

      <MatchComposeModal
        open={composeOpen}
        matchId={matchId}
        existing={[...match.starters, ...match.substitutes] as CompositionEntry[]}
        onClose={() => setComposeOpen(false)}
        onSaved={() => {
          setComposeOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["sport", "match", matchId] });
          showToast("Composition enregistrée (brouillon).");
        }}
      />

      <ScoreModal
        key={`score-${match.sheet?.score_home ?? "x"}-${match.sheet?.score_away ?? "x"}`}
        open={scoreOpen}
        initialHome={match.sheet?.score_home ?? 0}
        initialAway={match.sheet?.score_away ?? 0}
        onClose={() => setScoreOpen(false)}
        onSubmit={(h, a) => void handleScore(h, a)}
        submitting={scoreSubmitting}
      />

      <GoalModal
        key={goalModal.goal?.id ?? "new"}
        open={goalModal.open}
        goal={goalModal.goal}
        matchId={matchId}
        onClose={() => setGoalModal({ open: false, goal: null })}
        onSaved={() => {
          setGoalModal({ open: false, goal: null });
          void queryClient.invalidateQueries({ queryKey: ["sport", "match", matchId] });
          showToast("But ajouté. Les statistiques sont à jour.");
        }}
        onDeleted={() => {
          setGoalModal({ open: false, goal: null });
          void queryClient.invalidateQueries({ queryKey: ["sport", "match", matchId] });
        }}
      />

      <MatchEditModal
        open={editOpen}
        match={match}
        onClose={() => setEditOpen(false)}
        onUpdated={() => {
          setEditOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["sport", "match", matchId] });
          showToast("Match mis à jour.");
        }}
      />

      <IncidentModal
        open={incidentOpen}
        eventId={matchId}
        onClose={() => setIncidentOpen(false)}
        onCreated={() => {
          setIncidentOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["sport", "incidents", matchId] });
        }}
      />

      <ConfirmDialog
        open={removeConfirm !== null}
        title="Retirer ce joueur de la composition ?"
        confirmLabel="Retirer"
        onConfirm={() => removeConfirm !== null && void handleRemove(removeConfirm)}
        onCancel={() => setRemoveConfirm(null)}
      />

      <AddMatchEquipmentModal
        open={addEquipmentOpen}
        clubName={profileQuery.data?.club.name ?? ""}
        opponent={match.opponent}
        eventDate={match.event_date}
        onClose={() => setAddEquipmentOpen(false)}
        onSubmit={async (lines) => {
          await recordMatchEquipmentOut(matchId, lines);
          setAddEquipmentOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["logistics", "match-equipment", matchId] });
          showToast("Équipements enregistrés. Sortie ajoutée au registre du matériel.");
        }}
      />

      <MatchEquipmentModal
        open={equipmentDetailOpen}
        matchId={matchId}
        opponent={match.opponent}
        eventDate={match.event_date}
        canRecordReturn={access.isCoach || isSteward}
        onClose={() => setEquipmentDetailOpen(false)}
        onReturned={() => {
          void queryClient.invalidateQueries({ queryKey: ["logistics", "match-equipment", matchId] });
          showToast("Retour enregistré.");
        }}
      />
    </div>
  );
}
