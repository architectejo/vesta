import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { listClubPlayers, getMyProfile, type ClubPlayerListItem } from "../../api/clubs";
import {
  getSession,
  listEventIncidents,
  markSessionAttendance,
  type Attendance,
  type Formation,
  type SessionDetail,
  type UnassignedGroups,
} from "../../api/sport";
import {
  Avatar,
  Banner,
  Button,
  EmptyState,
  Loader,
  Modal,
  PitchPin,
  StatusBadge,
  SyncIndicator,
  Tabs,
  useToast,
  type StatusKey,
} from "../../design-system";
import { useOfflineActionQueue } from "../../hooks/useOfflineActionQueue";
import { reportInjury, type InjuryReportInput } from "../../api/medical";
import { InjuryReportModal } from "../medical/InjuryReportModal";
import { AttendanceDetailModal } from "./AttendanceDetailModal";
import {
  BulkActionBar,
  BulkConfirmModal,
  BulkExcuseModal,
  BulkHeaderBar,
  BulkResultModal,
} from "./BulkAttendance";
import { useBulkAttendance, type BulkAttendanceState } from "./useBulkAttendance";
import { EvaluationModal } from "./EvaluationModal";
import { IncidentModal } from "./IncidentModal";
import { SessionStatsPanel, sessionStatsKey } from "./SessionStatsPanel";
import { MeasureModal } from "./performance/MeasureModal";
import { PendingMeasures } from "./performance/PendingMeasures";
import { useMeasureOutbox } from "./performance/useMeasureOutbox";
import { PlayerCardModal } from "./PlayerCardModal";
import { shortLabel } from "./pinLayout";
import { SessionEditModal } from "./SessionEditModal";
import { getSportAccess } from "./sportAccess";
import { formatTime } from "./sportTime";
import { TeamsBoard } from "./TeamsBoard";
import { useTeamFieldActions } from "./useTeamFieldActions";

type PointageFilter = "not_marked" | "all" | "present" | "late" | "excused";

interface PendingAttendance {
  membershipId: number;
  clientUuid: string;
  clientRecordedAt: string;
}

function attendanceStatusKey(status: Attendance["status"]): StatusKey {
  if (status === "present") return "present";
  if (status === "late_absent") return "late";
  if (status === "excused_absent") return "excused";
  return "absent";
}

// ---------------------------------------------------------------------------
// Vue « Pointage » (§3.1)
// ---------------------------------------------------------------------------

interface PointageRow {
  membership: ClubPlayerListItem;
  attendance: Attendance | null;
  pending: PendingAttendance | null;
  rank: number | null;
}

function PointageTab({
  session,
  roster,
  canRecord,
  pendingByMember,
  onMarkArrival,
  onOpenDetail,
  bulk,
}: {
  session: SessionDetail;
  roster: ClubPlayerListItem[];
  canRecord: boolean;
  pendingByMember: Map<number, PendingAttendance>;
  onMarkArrival: (membershipId: number) => void;
  onOpenDetail: (attendance: Attendance) => void;
  bulk: BulkAttendanceState;
}) {
  const [filter, setFilter] = useState<PointageFilter>("not_marked");
  const [search, setSearch] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [excuseOpen, setExcuseOpen] = useState(false);
  // Droits renvoyés par l'API (faux si la séance est verrouillée).
  const canBulk = session.capabilities?.can_bulk_mark ?? false;
  const canBulkExcuse = session.capabilities?.can_bulk_excuse ?? false;
  const canSetTime = session.capabilities?.can_set_arrival_time ?? false;
  const selecting = bulk.active && canBulk;
  const stopBulk = bulk.stop;

  useEffect(() => {
    if (bulk.active && !canBulk) stopBulk();
  }, [bulk.active, canBulk, stopBulk]);

  const attendanceByMember = useMemo(() => {
    const map = new Map<number, Attendance>();
    for (const a of session.attendances) map.set(a.membership_id, a);
    return map;
  }, [session.attendances]);

  const rankByMember = useMemo(() => {
    const present = session.attendances
      .filter((a) => a.status === "present" || a.status === "late_absent")
      .filter((a) => a.arrived_at)
      .slice()
      .sort((a, b) => (a.arrived_at! < b.arrived_at! ? -1 : 1));
    const map = new Map<number, number>();
    present.forEach((a, i) => map.set(a.membership_id, i + 1));
    return map;
  }, [session.attendances]);

  const rows: PointageRow[] = useMemo(() => {
    return roster.map((membership) => ({
      membership,
      attendance: attendanceByMember.get(membership.membership_id) ?? null,
      pending: pendingByMember.get(membership.membership_id) ?? null,
      rank: rankByMember.get(membership.membership_id) ?? null,
    }));
  }, [roster, attendanceByMember, pendingByMember, rankByMember]);

  const filtered = rows.filter((row) => {
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      const name = `${row.membership.first_name} ${row.membership.last_name}`.toLowerCase();
      const number = String(row.membership.jersey_number ?? "");
      if (!name.includes(q) && !number.includes(q)) return false;
    }
    if (filter === "all") return true;
    if (filter === "not_marked") return !row.attendance && !row.pending;
    if (filter === "present") return row.attendance?.status === "present";
    if (filter === "late") return row.attendance?.status === "late_absent";
    if (filter === "excused") return row.attendance?.status === "excused_absent";
    return true;
  });

  filtered.sort((a, b) => {
    const aMarked = Boolean(a.attendance || a.pending);
    const bMarked = Boolean(b.attendance || b.pending);
    if (aMarked !== bMarked) return aMarked ? 1 : -1;
    if (!aMarked) {
      return `${a.membership.last_name}`.localeCompare(`${b.membership.last_name}`);
    }
    const aTime = a.attendance?.arrived_at ?? a.pending?.clientRecordedAt ?? "";
    const bTime = b.attendance?.arrived_at ?? b.pending?.clientRecordedAt ?? "";
    return aTime < bTime ? -1 : 1;
  });

  const checkableIds = filtered.filter((r) => !r.attendance && !r.pending).map((r) => r.membership.membership_id);
  const nameOf = (id: number) => {
    const m = roster.find((r) => r.membership_id === id);
    return m ? `${m.first_name} ${m.last_name}` : `Joueur n° ${id}`;
  };
  const selectedPlayers = bulk.selected.map((id) => ({ id, name: nameOf(id) }));

  const chips: Array<{ value: PointageFilter; label: string }> = [
    { value: "not_marked", label: "Non pointés" },
    { value: "all", label: "Tous" },
    { value: "present", label: "Présents" },
    { value: "late", label: "En retard" },
    { value: "excused", label: "Excusés" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="text-status-success-fg">Présents {session.counts.present}</span>
        <span className="text-status-danger-fg">En retard {session.counts.late}</span>
        <span className="text-text-muted">Non pointés {session.counts.not_marked}</span>
        <span className="text-text-muted">Excusés {session.counts.excused}</span>
      </div>

      <input
        type="text"
        placeholder="Nom ou numéro"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="h-9 w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text placeholder:text-text-muted"
      />

      {selecting ? (
        <BulkHeaderBar
          checkableIds={checkableIds}
          selected={bulk.selected}
          onCheckAll={bulk.checkAll}
          onUncheckAll={bulk.uncheckAll}
          onStop={bulk.stop}
          disabled={bulk.submitting}
        />
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex flex-wrap gap-1">
        {chips.map((chip) => (
          <button
            key={chip.value}
            type="button"
            onClick={() => setFilter(chip.value)}
            aria-pressed={filter === chip.value}
            className={[
              "h-8 rounded-full border px-3 text-xs font-medium",
              filter === chip.value
                ? "border-primary bg-primary text-on-primary"
                : "border-border-strong bg-surface text-text",
            ].join(" ")}
          >
            {chip.label}
          </button>
        ))}
      </div>
      {canBulk && !selecting ? (
        <Button size="sm" variant="secondary" onClick={bulk.start}>
          Sélectionner
        </Button>
      ) : null}
      </div>

      {filtered.length === 0 ? (
        <EmptyState message={filter === "not_marked" ? "Tout le monde est pointé." : "Aucun joueur dans ce filtre."} />
      ) : (
        <ul className="divide-y divide-border">
          {filtered.map((row) => {
            const id = row.membership.membership_id;
            const fullName = `${row.membership.first_name} ${row.membership.last_name}`;
            if (selecting && !row.attendance && !row.pending) {
              const rank = bulk.selected.indexOf(id) + 1;
              return (
                <li key={id}>
                  <label className="flex min-h-14 cursor-pointer items-center gap-3 py-2">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center">
                      <input
                        type="checkbox"
                        aria-label={`Sélectionner ${fullName}`}
                        className="h-5 w-5 rounded-sm border-border-strong text-primary"
                        checked={rank > 0}
                        disabled={bulk.submitting}
                        onChange={() => bulk.toggle(id)}
                      />
                    </span>
                    <Avatar name={fullName} photoUrl={row.membership.photo} size={40} />
                    <span className="min-w-0 flex-1">
                      <span className="block break-words text-sm text-text">{fullName}</span>
                      <span className="block break-words text-xs text-text-muted">
                        {[row.membership.jersey_number != null ? `n° ${row.membership.jersey_number}` : null, row.membership.position_label]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                    {rank > 0 ? <span className="text-[13px] text-text-muted">{rank}</span> : null}
                  </label>
                </li>
              );
            }
            return (
              <li key={row.membership.membership_id} className="flex min-h-14 items-center gap-3 py-2">
                <Avatar
                  name={`${row.membership.first_name} ${row.membership.last_name}`}
                  photoUrl={row.membership.photo}
                  size={40}
                />
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  disabled={!row.attendance}
                  onClick={() => row.attendance && onOpenDetail(row.attendance)}
                >
                  <p className="break-words text-sm text-text">
                    {row.membership.first_name} {row.membership.last_name}
                  </p>
                  <p className="break-words text-xs text-text-muted">
                    {[row.membership.jersey_number != null ? `n° ${row.membership.jersey_number}` : null, row.membership.position_label]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </button>
                {row.pending && !row.attendance ? (
                  <StatusBadge status="queued" />
                ) : row.attendance ? (
                  <div className="flex shrink-0 flex-col items-end gap-0.5">
                    <span className="text-xs text-text-muted">{formatTime(row.attendance.arrived_at)}</span>
                    <StatusBadge
                      status={attendanceStatusKey(row.attendance.status)}
                      detail={row.attendance.status === "excused_absent" ? row.attendance.excused_reason : undefined}
                    />
                    {row.rank ? <span className="text-[11px] text-text-muted">#{row.rank}</span> : null}
                  </div>
                ) : canRecord ? (
                  <Button size="sm" variant="secondary" onClick={() => onMarkArrival(row.membership.membership_id)}>
                    Arrivé
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      {selecting ? (
        <BulkActionBar
          count={bulk.selected.length}
          canExcuse={canBulkExcuse}
          submitting={bulk.submitting}
          onArrive={() => {
            bulk.clearError();
            setConfirmOpen(true);
          }}
          onExcuse={() => {
            bulk.clearError();
            setExcuseOpen(true);
          }}
        />
      ) : null}

      <BulkConfirmModal
        open={confirmOpen}
        players={selectedPlayers}
        canSetTime={canSetTime}
        eventDate={session.event_date}
        lateCutoff={session.late_arrival_cutoff}
        lateCountsAbsent={session.late_arrival_counts_absent}
        blockedCount={bulk.selected.filter((id) => session.unassigned?.cannot_play.some((p) => p.membership_id === id)).length}
        submitting={bulk.submitting}
        error={bulk.error}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={(request) => void bulk.submit(request).then((ok) => ok && setConfirmOpen(false))}
      />
      <BulkExcuseModal
        open={excuseOpen}
        players={selectedPlayers}
        submitting={bulk.submitting}
        error={bulk.error}
        onCancel={() => setExcuseOpen(false)}
        onConfirm={(request) => void bulk.submit(request).then((ok) => ok && setExcuseOpen(false))}
      />
      <BulkResultModal summary={bulk.summary} nameOf={nameOf} onClose={bulk.clearSummary} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Vue « Équipes A/B » (§3.2)
// ---------------------------------------------------------------------------

interface PinMenuState {
  kind: "unassigned" | "locked" | "president_blocked";
  membershipId: number;
  name: string;
  reason?: string;
}

function EquipesTab({
  session,
  canAssign,
  canPlaceLate,
  isPresidentOnly,
  onAssign,
  onSetFormation,
  onPlacePlayer,
  onShowCard,
}: {
  session: SessionDetail;
  canAssign: boolean;
  canPlaceLate: boolean;
  isPresidentOnly: boolean;
  onAssign: (membershipId: number, team: "A" | "B") => void;
  onSetFormation: (team: "A" | "B", formation: Formation) => void;
  onPlacePlayer: (team: "A" | "B", membershipId: number, x: number | null, y: number | null) => void;
  onShowCard: (membershipId: number) => void;
}) {
  const [menu, setMenu] = useState<PinMenuState | null>(null);
  const unassigned: UnassignedGroups = session.unassigned;

  function openUnassignedMenu(membershipId: number, name: string) {
    if (isPresidentOnly) {
      setMenu({ kind: "president_blocked", membershipId, name });
      return;
    }
    setMenu({ kind: "unassigned", membershipId, name });
  }

  function openLockedMenu(membershipId: number, name: string, reason: string) {
    setMenu({ kind: "locked", membershipId, name, reason });
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-text-muted">
        Répartition automatique : alternance selon l'ordre d'arrivée (1er en A, 2e en B…). A : {session.team_a.length}{" "}
        joueurs · B : {session.team_b.length} joueurs
      </p>

      <TeamsBoard
        session={session}
        canAssign={canAssign}
        onAssign={onAssign}
        onSetFormation={onSetFormation}
        onPlacePlayer={onPlacePlayer}
        onShowCard={onShowCard}
      />

      {unassigned.to_place_manually.length === 0 && unassigned.cannot_play.length === 0 ? null : (
        <div className="space-y-3">
          {unassigned.to_place_manually.length > 0 ? (
            <div>
              <p className="mb-1 text-sm font-medium text-text">
                À placer à la main ({unassigned.to_place_manually.length})
              </p>
              <p className="mb-2 text-xs text-text-muted">
                Arrivés après l'heure limite : ils ne sont pas répartis automatiquement.
              </p>
              <div className="grid grid-cols-4 gap-2">
                {unassigned.to_place_manually.map((player) => (
                  <PitchPin
                    key={player.membership_id}
                    vertical
                    standalone
                    draggable={canAssign && canPlaceLate}
                    dragKind="unassigned-player"
                    pin={{
                      id: String(player.membership_id),
                      membershipId: player.membership_id,
                      label: shortLabel(player.name),
                      number: player.jersey_number,
                      photoUrl: player.photo,
                      fullName: player.name,
                      x: 50,
                      y: 50,
                    }}
                    onTap={() => openUnassignedMenu(player.membership_id, player.name)}
                  />
                ))}
              </div>
            </div>
          ) : null}

          {unassigned.cannot_play.length > 0 ? (
            <div>
              <p className="mb-1 text-sm font-medium text-text">Ne peuvent pas jouer ({unassigned.cannot_play.length})</p>
              <p className="mb-2 text-xs text-text-muted">
                Ces joueurs ne peuvent être placés dans aucune équipe tant que leur situation n'est pas régularisée.
              </p>
              <div className="grid grid-cols-4 gap-2">
                {unassigned.cannot_play.map((player) => (
                  <PitchPin
                    key={player.membership_id}
                    vertical
                    standalone
                    draggable={false}
                    dragKind="locked-player"
                    pin={{
                      id: String(player.membership_id),
                      membershipId: player.membership_id,
                      label: shortLabel(player.name),
                      number: player.jersey_number,
                      photoUrl: player.photo,
                      fullName: player.name,
                      x: 50,
                      y: 50,
                      locked: true,
                    }}
                    onTap={() => openLockedMenu(player.membership_id, player.name, player.reason)}
                  />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}

      <Modal open={menu !== null} onClose={() => setMenu(null)} title={menu?.name ?? ""} size="sm" hideFooter>
        {menu?.kind === "unassigned" ? (
          <div className="space-y-2">
            <Button variant="secondary" className="w-full" onClick={() => { onAssign(menu.membershipId, "A"); setMenu(null); }}>
              Passer en A
            </Button>
            <Button variant="secondary" className="w-full" onClick={() => { onAssign(menu.membershipId, "B"); setMenu(null); }}>
              Passer en B
            </Button>
            <Button variant="ghost" className="w-full" onClick={() => { onShowCard(menu.membershipId); setMenu(null); }}>
              Voir la fiche du joueur
            </Button>
          </div>
        ) : menu?.kind === "locked" ? (
          <div className="space-y-2">
            <p className="text-sm text-text">{menu.name} ne peut pas jouer</p>
            <p className="text-sm text-text-muted">{menu.reason}</p>
            <Button variant="ghost" className="w-full" onClick={() => { onShowCard(menu.membershipId); setMenu(null); }}>
              Voir la fiche du joueur
            </Button>
          </div>
        ) : menu?.kind === "president_blocked" ? (
          <p className="text-sm text-text-muted">Seuls le Coach et le Capitaine placent un retardataire.</p>
        ) : null}
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Vue « Bilan » (§3.3)
// ---------------------------------------------------------------------------

function BilanTab({
  session,
  eventId,
  canRecordIncident,
  canEvaluate,
  canReportInjury,
  canSeeMedicalFull,
  isCaptain,
  injuryOffline,
}: {
  session: SessionDetail;
  eventId: number;
  canRecordIncident: boolean;
  canEvaluate: boolean;
  canReportInjury: boolean;
  canSeeMedicalFull: boolean;
  isCaptain: boolean;
  injuryOffline: { isOnline: boolean; enqueue: (payload: InjuryReportInput) => void };
}) {
  const [incidentOpen, setIncidentOpen] = useState(false);
  const [evalOpen, setEvalOpen] = useState(false);
  const [injuryOpen, setInjuryOpen] = useState(false);
  const [measure, setMeasure] = useState<{ testId: number | null } | null>(null);
  const outbox = useMeasureOutbox();
  const queryClient = useQueryClient();

  const incidentsQuery = useQuery({
    queryKey: ["sport", "incidents", eventId],
    queryFn: () => listEventIncidents(eventId, { limit: 20 }),
  });

  return (
    <div className="space-y-4">
      <SessionStatsPanel
        sessionId={eventId}
        onEvaluate={canEvaluate ? () => setEvalOpen(true) : undefined}
        onMeasure={(testId) => setMeasure({ testId: testId ?? null })}
        measuresExtra={<PendingMeasures outbox={outbox} eventId={eventId} />}
      />
      <MeasureModal
        open={measure !== null}
        eventId={eventId}
        outbox={outbox}
        initialTestId={measure?.testId ?? null}
        onClose={() => setMeasure(null)}
      />

      <section className="rounded-md border border-border p-3">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text">Incidents de la séance</h3>
          {canRecordIncident ? (
            <Button size="sm" variant="secondary" onClick={() => setIncidentOpen(true)}>
              Signaler un incident
            </Button>
          ) : null}
        </div>
        {incidentsQuery.isLoading ? (
          <Loader loading variant="list" count={2} />
        ) : (incidentsQuery.data?.results.length ?? 0) === 0 ? (
          <EmptyState message="Aucun incident pour l'instant." />
        ) : (
          <ul className="divide-y divide-border">
            {incidentsQuery.data!.results.slice(0, 5).map((incident) => (
              <li key={incident.id} className="py-2 text-sm text-text">
                {incident.player.name} — {incident.incident_type_label} ({incident.cause_label})
              </li>
            ))}
          </ul>
        )}
      </section>

      {canReportInjury || canSeeMedicalFull ? (
        <section className="rounded-md border border-border p-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text">Blessures</h3>
            {canReportInjury ? (
              <Button size="sm" variant="secondary" onClick={() => setInjuryOpen(true)}>
                Déclarer une blessure
              </Button>
            ) : null}
          </div>
          {isCaptain ? (
            <p className="text-sm text-text-muted">Les blessures déclarées sont suivies par le Médecin.</p>
          ) : canSeeMedicalFull ? (
            <p className="text-sm text-text-muted">
              Les blessures de la séance s'affichent ici dès qu'elles sont déclarées.
            </p>
          ) : null}
        </section>
      ) : null}

      <InjuryReportModal
        open={injuryOpen}
        onClose={() => setInjuryOpen(false)}
        context={{
          eventId,
          eventKind: "session",
          eventLabel: `Séance du ${session.event_date}`,
        }}
        offline={injuryOffline}
        onReported={() => {
          setInjuryOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["sport", "session", eventId] });
        }}
      />

      <IncidentModal
        open={incidentOpen}
        eventId={eventId}
        onClose={() => setIncidentOpen(false)}
        onCreated={() => {
          setIncidentOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["sport", "incidents", eventId] });
        }}
      />
      <EvaluationModal
        open={evalOpen}
        eventId={eventId}
        onClose={() => setEvalOpen(false)}
        onCreated={() => {
          setEvalOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["sport", "evaluations", eventId] });
          void queryClient.invalidateQueries({ queryKey: sessionStatsKey(eventId) });
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page « Séance »
// ---------------------------------------------------------------------------

export function SeancePage() {
  const { id } = useParams();
  const sessionId = Number(id);
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [tab, setTab] = useState<"pointage" | "equipes" | "bilan">("pointage");
  const tabAutoSet = useRef(false);
  const [editOpen, setEditOpen] = useState(false);
  const [instructionsOpen, setInstructionsOpen] = useState(false);
  const [detailAttendance, setDetailAttendance] = useState<Attendance | null>(null);
  const [cardMembershipId, setCardMembershipId] = useState<number | null>(null);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const access = getSportAccess(profileQuery.data?.roles);

  const sessionQuery = useQuery({
    queryKey: ["sport", "session", sessionId],
    queryFn: () => getSession(sessionId),
    enabled: Number.isFinite(sessionId),
    refetchInterval: 15_000,
  });

  const rosterQuery = useQuery({
    queryKey: ["clubs", "players", "active"],
    queryFn: () => listClubPlayers({ status: "active" }),
  });

  const pendingQueue = useOfflineActionQueue<PendingAttendance>({
    storageKey: `vesta.offline.session-attendance.${sessionId}`,
    processItem: async (payload) => {
      await markSessionAttendance(sessionId, {
        membership_id: payload.membershipId,
        arrived_at: payload.clientRecordedAt,
        client_uuid: payload.clientUuid,
        client_recorded_at: payload.clientRecordedAt,
      });
      void queryClient.invalidateQueries({ queryKey: ["sport", "session", sessionId] });
    },
    onRejected: (_payload, message) => showToast(message),
  });

  // Déclaration de blessure hors connexion (CDC 6.6 ; medical.md §4.1) :
  // file distincte du pointage, même page.
  const injuryQueue = useOfflineActionQueue<InjuryReportInput>({
    storageKey: `vesta.offline.injury-report.session.${sessionId}`,
    processItem: async (payload) => {
      await reportInjury(payload);
      void queryClient.invalidateQueries({ queryKey: ["sport", "session", sessionId] });
    },
    onRejected: (_payload, message) => showToast(message),
  });

  const refreshSession = useCallback(
    () => void queryClient.invalidateQueries({ queryKey: ["sport", "session", sessionId] }),
    [queryClient, sessionId],
  );
  const bulk = useBulkAttendance({
    kind: "session",
    eventId: sessionId,
    onChanged: refreshSession,
    enqueueOffline: (item) => pendingQueue.enqueue(item),
  });

  const pendingByMember = useMemo(() => {
    const map = new Map<number, PendingAttendance>();
    // Les éléments les plus récents priment si plusieurs pointages en
    // attente concernent le même joueur (ne devrait pas arriver en usage
    // normal, un bouton « Arrivé » disparaissant après le premier appui).
    for (const item of pendingQueue.items) map.set(item.payload.membershipId, item.payload);
    return map;
  }, [pendingQueue.items]);

  useEffect(() => {
    if (tabAutoSet.current || !sessionQuery.data) return;
    tabAutoSet.current = true;
    const [h, m] = sessionQuery.data.late_arrival_cutoff.split(":").map(Number);
    const cutoffPlus30 = new Date();
    cutoffPlus30.setHours((h ?? 0), (m ?? 0) + 30, 0, 0);
    setTab(new Date() > cutoffPlus30 ? "equipes" : "pointage");
  }, [sessionQuery.data]);

  async function handleMarkArrival(membershipId: number): Promise<void> {
    const clientUuid = crypto.randomUUID();
    const clientRecordedAt = new Date().toISOString();
    if (!navigator.onLine) {
      pendingQueue.enqueue({ membershipId, clientUuid, clientRecordedAt });
      showToast(`Pointé à ${formatTime(clientRecordedAt)}. Il sera envoyé au retour du réseau.`);
      return;
    }
    try {
      await markSessionAttendance(sessionId, {
        membership_id: membershipId,
        arrived_at: clientRecordedAt,
        client_uuid: clientUuid,
        client_recorded_at: clientRecordedAt,
      });
      void queryClient.invalidateQueries({ queryKey: ["sport", "session", sessionId] });
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

  const teamFieldActions = useTeamFieldActions(sessionId, [["sport", "session", sessionId]]);

  async function handleAssign(membershipId: number, team: "A" | "B"): Promise<void> {
    await teamFieldActions.handleAssign(sessionQuery.data, membershipId, team);
  }

  async function handleSetFormation(team: "A" | "B", formation: Formation): Promise<void> {
    await teamFieldActions.handleSetFormation(team, formation);
  }

  async function handlePlaceTeamPlayer(
    team: "A" | "B",
    membershipId: number,
    x: number | null,
    y: number | null,
  ): Promise<void> {
    await teamFieldActions.handlePlaceTeamPlayer(team, membershipId, x, y);
  }

  if (profileQuery.isLoading || sessionQuery.isLoading || rosterQuery.isLoading) {
    return <Loader loading variant="page" />;
  }
  if (sessionQuery.isError) {
    return (
      <div className="space-y-4">
        <EmptyState variant="error" message="Impossible de charger la séance." actionLabel="Réessayer" onAction={() => void sessionQuery.refetch()} />
      </div>
    );
  }
  const session = sessionQuery.data;
  if (!session) return null;
  const roster = rosterQuery.data ?? [];

  const context = [
    profileQuery.data?.club.name,
    `Rassemblement ${session.gathering_time.slice(0, 5)}`,
    `Limite ${session.late_arrival_cutoff.slice(0, 5)}`,
    session.location || null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold text-text">
              Séance du {new Date(session.event_date).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}
            </h1>
            <p className="text-sm text-text-muted">{context}</p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={session.is_locked ? "session_locked" : "session_open"} />
            {access.isCoach && !session.is_locked ? (
              <div className="relative">
                <Button size="sm" variant="ghost" onClick={() => setEditOpen(true)}>
                  Modifier
                </Button>
              </div>
            ) : null}
          </div>
        </div>
        <SyncIndicator
          isOnline={pendingQueue.isOnline}
          pendingCount={pendingQueue.pendingCount}
          isSyncing={pendingQueue.isSyncing}
          items={pendingQueue.items.map((item) => ({
            id: item.id,
            label: `Pointage · joueur n° ${item.payload.membershipId}`,
            createdAt: item.createdAt,
          }))}
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
              // Jamais les circonstances (medical.md §4.1, §5.2).
              return { id: item.id, label: `Blessure déclarée pour ${name}`, createdAt: item.createdAt };
            })}
            onRetry={injuryQueue.retryNow}
          />
        ) : null}
        {session.instructions ? (
          <button type="button" className="text-xs font-medium text-primary-text hover:underline" onClick={() => setInstructionsOpen(true)}>
            Voir les consignes
          </button>
        ) : null}
      </header>

      {!pendingQueue.isOnline ? (
        <Banner variant="info">
          Vous êtes hors connexion. Les pointages sont enregistrés sur ce téléphone et seront envoyés au retour du
          réseau.
        </Banner>
      ) : null}
      {session.is_locked ? <Banner variant="readonly">Cette séance est verrouillée : lecture seule.</Banner> : null}

      <Tabs
        label="Vue de la séance"
        value={tab}
        onChange={setTab}
        items={[
          { value: "pointage", label: "Pointage" },
          { value: "equipes", label: "Équipes A/B" },
          { value: "bilan", label: "Bilan" },
        ]}
      />

      {tab === "pointage" ? (
        <PointageTab
          session={session}
          roster={roster}
          canRecord={access.canRecordAttendance && !session.is_locked}
          pendingByMember={pendingByMember}
          onMarkArrival={(id) => void handleMarkArrival(id)}
          onOpenDetail={setDetailAttendance}
          bulk={bulk}
        />
      ) : tab === "equipes" ? (
        <EquipesTab
          session={session}
          canAssign={access.canAssignTeams && !session.is_locked}
          canPlaceLate={access.isCoach || access.isCaptain}
          isPresidentOnly={access.isPresident && !access.isCoach && !access.isCaptain}
          onAssign={(id, team) => void handleAssign(id, team)}
          onSetFormation={(team, formation) => void handleSetFormation(team, formation)}
          onPlacePlayer={(team, id, x, y) => void handlePlaceTeamPlayer(team, id, x, y)}
          onShowCard={setCardMembershipId}
        />
      ) : (
        <BilanTab
          session={session}
          eventId={session.id}
          canRecordIncident={access.canRecordIncident}
          canEvaluate={access.canEvaluate}
          canReportInjury={access.canReportInjury}
          canSeeMedicalFull={access.canSeeMedicalFull}
          isCaptain={access.isCaptain && !access.canSeeMedicalFull}
          injuryOffline={{ isOnline: injuryQueue.isOnline, enqueue: injuryQueue.enqueue }}
        />
      )}

      <SessionEditModal
        open={editOpen}
        session={session}
        onClose={() => setEditOpen(false)}
        onUpdated={() => {
          setEditOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["sport", "session", sessionId] });
          showToast("Séance mise à jour.");
        }}
      />

      <Modal open={instructionsOpen} onClose={() => setInstructionsOpen(false)} title="Consignes" size="sm" hideFooter>
        <p className="text-sm text-text">{session.instructions}</p>
      </Modal>

      {detailAttendance ? (
        <AttendanceDetailModal
          open
          sessionId={sessionId}
          attendance={detailAttendance}
          eventDate={session.event_date}
          arrivalRank={null}
          canCorrectTime={access.canCorrectAttendanceTime && !session.is_locked}
          isLocked={session.is_locked}
          onClose={() => setDetailAttendance(null)}
          onUpdated={() => {
            setDetailAttendance(null);
            void queryClient.invalidateQueries({ queryKey: ["sport", "session", sessionId] });
            showToast("Pointage corrigé.");
          }}
        />
      ) : null}

      <PlayerCardModal open={cardMembershipId !== null} membershipId={cardMembershipId} onClose={() => setCardMembershipId(null)} />
    </div>
  );
}
