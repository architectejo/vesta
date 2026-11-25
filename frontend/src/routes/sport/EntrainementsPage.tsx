import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getMyProfile } from "../../api/clubs";
import {
  getAttendanceRanking,
  getMyAttendance,
  getSessionStatsHistory,
  type AttendanceRankingEntry,
  type SessionHistoryResult,
  type StatsPeriod,
} from "../../api/sport";
import {
  Avatar,
  Button,
  ChartCard,
  DataTable,
  EmptyState,
  LineChart,
  Loader,
  Modal,
  SegmentedControl,
  StatusBadge,
  useToast,
  type DataTableColumn,
} from "../../design-system";
import { CreateSessionModal } from "./CreateSessionModal";
import { SessionStatsPanel } from "./SessionStatsPanel";
import { PerformanceTestsCard } from "./performance/PerformanceTestsCard";
import { canCreateSession, canManagePerformanceTests, canViewTrainingStaffStats } from "./sportAccess";
import { formatLongDate, formatNote, formatRate, formatSessionDate, plural, shortDateLabel } from "./statsFormat";

const LIST_STEP = 5;
const TOP = 5;

const PERIOD_OPTIONS: Array<{ value: StatsPeriod; label: string }> = [
  { value: "last10", label: "10 dernières séances" },
  { value: "season", label: "Saison" },
];

/** Pas de nouvel essai pour une réponse définitive (refus, absence de fiche joueur). */
const retryUnlessDefinitive = (count: number, error: unknown): boolean =>
  !(error instanceof ApiError && [400, 403, 404].includes(error.status)) && count < 2;

// ---------------------------------------------------------------------------
// Modale « Séance » (statistiques en lecture seule)
// ---------------------------------------------------------------------------

function SessionStatsModal({ session, onClose }: { session: SessionHistoryResult | null; onClose: () => void }) {
  const navigate = useNavigate();
  return (
    <Modal
      open={session !== null}
      onClose={onClose}
      size="lg"
      title={session ? `Séance du ${formatLongDate(session.date)}` : "Séance"}
      subtitle={session?.location || undefined}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Fermer
          </Button>
          {session ? <Button onClick={() => navigate(`/seances/${session.session_id}`)}>Ouvrir la séance</Button> : null}
        </>
      }
    >
      {session ? <SessionStatsPanel sessionId={session.session_id} /> : null}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Assiduité
// ---------------------------------------------------------------------------

function attendanceLine(entry: AttendanceRankingEntry): string {
  return `${entry.attended} ${plural(entry.attended, "séance", "séances")} sur ${entry.sessions} · ${formatRate(entry.rate)}`;
}

function AttendanceList({ title, entries }: { title: string; entries: AttendanceRankingEntry[] }) {
  return (
    <div>
      <h4 className="mb-1 text-sm font-semibold text-text">{title}</h4>
      <ul className="divide-y divide-border">
        {entries.map((entry) => (
          <li key={entry.player.membership_id} className="flex min-h-11 items-center gap-2 py-1">
            <Avatar name={entry.player.name} photoUrl={entry.player.photo} size={32} />
            <span className="min-w-0 flex-1">
              <span className="block break-words text-sm text-text">{entry.player.name}</span>
              <span className="block text-xs text-text-muted">{attendanceLine(entry)}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AttendanceRankingModal({
  open,
  onClose,
  entries,
}: {
  open: boolean;
  onClose: () => void;
  entries: AttendanceRankingEntry[];
}) {
  const columns: Array<DataTableColumn<AttendanceRankingEntry>> = [
    {
      key: "player",
      header: "Joueur",
      widthPx: 140,
      sortAccessor: (row) => row.player.name.toLowerCase(),
      render: (row) => (
        <span className="flex items-center gap-2">
          <Avatar name={row.player.name} photoUrl={row.player.photo} size={24} />
          <span className="break-words">{row.player.name}</span>
        </span>
      ),
    },
    { key: "present", header: "Présences", sortAccessor: (row) => row.present, render: (row) => row.present },
    { key: "late", header: "Retards", sortAccessor: (row) => row.late, render: (row) => row.late },
    { key: "excused", header: "Excusés", sortAccessor: (row) => row.excused, render: (row) => row.excused },
    { key: "absent", header: "Absences", sortAccessor: (row) => row.absent, render: (row) => row.absent },
    { key: "rate", header: "Taux", sortAccessor: (row) => row.rate ?? -1, render: (row) => formatRate(row.rate) },
  ];
  return (
    <Modal open={open} onClose={onClose} size="lg" title="Assiduité des joueurs" hideFooter>
      <DataTable
        columns={columns}
        rows={entries}
        getRowId={(row) => row.player.membership_id}
        getSearchableText={(row) => `${row.player.name} ${row.player.jersey_number ?? ""}`}
        searchPlaceholder="Nom ou numéro"
        resultLabel="joueurs"
        stickyFirstColumn
        pageSize={20}
      />
    </Modal>
  );
}

function AttendanceSection({ period, staff }: { period: StatsPeriod; staff: boolean }) {
  const [allOpen, setAllOpen] = useState(false);

  const rankingQuery = useQuery({
    queryKey: ["sport", "attendance-ranking", period],
    queryFn: () => getAttendanceRanking(period),
    enabled: staff,
    retry: retryUnlessDefinitive,
  });
  // Un refus (403) du classement bascule sur « Mon assiduité » : l'API reste juge.
  const rankingRefused = rankingQuery.error instanceof ApiError && rankingQuery.error.status === 403;
  const showMine = !staff || rankingRefused;
  const meQuery = useQuery({
    queryKey: ["sport", "attendance-me", period],
    queryFn: () => getMyAttendance(period),
    enabled: showMine,
    retry: retryUnlessDefinitive,
  });

  const title = showMine ? "Mon assiduité" : "Assiduité";
  let body;

  if (showMine) {
    const meNoProfile = meQuery.error instanceof ApiError && meQuery.error.status === 404;
    if (meQuery.isLoading) {
      body = <Loader loading variant="list" count={2} />;
    } else if (meNoProfile) {
      body = <EmptyState message="Aucune fiche joueur n'est associée à votre compte." />;
    } else if (meQuery.isError || !meQuery.data) {
      body = (
        <EmptyState
          variant="error"
          message="Impossible de charger votre assiduité."
          actionLabel="Réessayer"
          onAction={() => void meQuery.refetch()}
        />
      );
    } else if (meQuery.data.sessions === 0) {
      body = <EmptyState message="Aucune séance sur la période." />;
    } else {
      const me = meQuery.data;
      body = (
        <p className="text-sm text-text">
          Vous avez participé à {me.attended} {plural(me.attended, "séance", "séances")} sur {me.sessions} ·{" "}
          <strong>{formatRate(me.rate)}</strong>
        </p>
      );
    }
  } else if (rankingQuery.isLoading) {
    body = <Loader loading variant="list" count={5} />;
  } else if (rankingQuery.isError || !rankingQuery.data) {
    body = (
      <EmptyState
        variant="error"
        message="Impossible de charger l'assiduité."
        actionLabel="Réessayer"
        onAction={() => void rankingQuery.refetch()}
      />
    );
  } else if (rankingQuery.data.results.length === 0) {
    body = <EmptyState message="Aucune séance sur la période." />;
  } else {
    // Le classement est déjà trié par taux décroissant par l'API.
    const results = rankingQuery.data.results;
    const top = results.slice(0, TOP);
    const bottom = results.slice(Math.max(TOP, results.length - TOP)).reverse();
    body = (
      <div className="space-y-3">
        <AttendanceList title="Les plus assidus" entries={top} />
        {bottom.length > 0 ? <AttendanceList title="Les moins assidus" entries={bottom} /> : null}
        <Button size="sm" variant="secondary" onClick={() => setAllOpen(true)}>
          Voir tout
        </Button>
        <AttendanceRankingModal open={allOpen} onClose={() => setAllOpen(false)} entries={results} />
      </div>
    );
  }

  return (
    <section aria-label={title} className="rounded-md border border-border bg-surface p-3 shadow-card">
      <h3 className="mb-2 text-base font-semibold text-text">{title}</h3>
      {body}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function EntrainementsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [period, setPeriod] = useState<StatsPeriod>("last10");
  const [selected, setSelected] = useState<SessionHistoryResult | null>(null);
  const [visibleCount, setVisibleCount] = useState(LIST_STEP);
  const [createOpen, setCreateOpen] = useState(false);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const historyQuery = useQuery({
    queryKey: ["sport", "stats-history", period],
    queryFn: () => getSessionStatsHistory(period),
    retry: retryUnlessDefinitive,
  });

  if (profileQuery.isLoading) return <Loader loading variant="page" />;

  const roles = profileQuery.data?.roles;
  const staff = canViewTrainingStaffStats(roles);
  const history = historyQuery.data;
  const results = history?.results ?? [];
  const cardState = historyQuery.isLoading ? "loading" : historyQuery.isError ? "error" : results.length < 2 ? "empty" : "ready";
  const emptyMessage =
    results.length === 0 ? "Aucune séance pour l'instant." : "Il faut au moins 2 séances pour afficher une évolution.";
  const retry = () => void historyQuery.refetch();

  const labels = results.map((r) => shortDateLabel(r.date));
  const rates = results.map((r) => r.attendance_rate);
  const lastRate = [...rates].reverse().find((r) => r !== null) ?? null;
  const ratings = results.map((r) => {
    const value = staff ? r.average_rating : r.my_rating;
    return value === null ? null : Number(value);
  });
  const hasRatings = ratings.some((r) => r !== null);
  const lastRating = [...ratings].reverse().find((r) => r !== null) ?? null;
  const averageRating = staff ? (history?.average_rating ?? null) : (history?.my_average_rating ?? null);
  const fmtNote = (value: number) => formatNote(String(value));

  const club = profileQuery.data?.club.name;
  const context = [club, history?.season ? `Saison ${history.season.label}` : null].filter(Boolean).join(" · ");
  const shown = results.slice().reverse().slice(0, visibleCount);

  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold text-text">Entraînements</h1>
            {context ? <p className="text-sm text-text-muted">{context}</p> : null}
          </div>
          {canCreateSession(roles) ? (
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              Créer une séance
            </Button>
          ) : null}
        </div>
        <SegmentedControl<StatsPeriod>
          label="Période"
          hideLabel
          value={period}
          onChange={(value) => {
            setPeriod(value);
            setVisibleCount(LIST_STEP);
          }}
          options={PERIOD_OPTIONS}
        />
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <ChartCard
            title="Taux de présence"
            value={lastRate === null ? undefined : `Dernière séance : ${lastRate} %`}
            caption={history?.average_attendance_rate != null ? `Moyenne ${history.average_attendance_rate} %` : undefined}
            state={cardState}
            emptyMessage={emptyMessage}
            errorMessage="Impossible de charger le taux de présence."
            onRetry={retry}
            interactiveContent
          >
            <LineChart
              title="Taux de présence par séance"
              labels={labels}
              series={[{ name: "Taux de présence", values: rates }]}
              yMin={0}
              yMax={100}
              unit="%"
              reference={
                history?.average_attendance_rate != null
                  ? { value: history.average_attendance_rate, label: "Moyenne" }
                  : undefined
              }
              onSelect={(index) => setSelected(results[index] ?? null)}
              emptyMessage="Aucune séance pointée sur la période."
            />
          </ChartCard>

          <ChartCard
            title={staff ? "Note moyenne des séances" : "Mes notes"}
            value={lastRating === null ? undefined : `Dernière séance : ${fmtNote(lastRating)}`}
            caption={
              averageRating !== null ? `${staff ? "Moyenne" : "Ma moyenne"} : ${formatNote(averageRating)}` : undefined
            }
            state={cardState === "ready" && !hasRatings ? "empty" : cardState}
            emptyMessage={results.length < 2 ? emptyMessage : "Aucune séance notée sur la période."}
            errorMessage="Impossible de charger les notes."
            onRetry={retry}
            interactiveContent
          >
            <LineChart
              title={staff ? "Note moyenne par séance" : "Ma note par séance"}
              labels={labels}
              series={[{ name: staff ? "Note moyenne" : "Ma note", values: ratings }]}
              yMin={0}
              yMax={10}
              formatValue={fmtNote}
              onSelect={(index) => setSelected(results[index] ?? null)}
            />
          </ChartCard>

          <section aria-label="Séances" className="rounded-md border border-border bg-surface p-3 shadow-card">
            <h3 className="mb-2 text-base font-semibold text-text">Séances</h3>
            {historyQuery.isLoading ? (
              <Loader loading variant="list" count={3} />
            ) : historyQuery.isError ? (
              <EmptyState
                variant="error"
                message="Impossible de charger les séances."
                actionLabel="Réessayer"
                onAction={retry}
              />
            ) : results.length === 0 ? (
              <EmptyState
                message="Aucune séance pour l'instant."
                actionLabel={canCreateSession(roles) ? "Créer une séance" : undefined}
                onAction={canCreateSession(roles) ? () => setCreateOpen(true) : undefined}
              />
            ) : (
              <>
                <ul className="divide-y divide-border">
                  {shown.map((session) => (
                    <li key={session.session_id}>
                      <button
                        type="button"
                        onClick={() => setSelected(session)}
                        className="flex min-h-14 w-full items-center gap-2 py-2 text-left"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium capitalize text-text">
                            {formatSessionDate(session.date)}
                          </span>
                          <span className="block break-words text-xs text-text-muted">
                            {session.location || "Terrain non précisé"}
                          </span>
                          <span className="block text-xs text-text-muted">
                            {session.attendance_rate === null
                              ? "Personne pointé"
                              : `${session.present} ${plural(session.present, "présent", "présents")} · ${session.attendance_rate} %`}
                            {staff && session.average_rating !== null ? ` · note ${formatNote(session.average_rating)}` : ""}
                            {!staff && session.my_rating !== null ? ` · ma note ${formatNote(session.my_rating)}` : ""}
                          </span>
                        </span>
                        <StatusBadge status={session.locked ? "session_locked" : "session_open"} />
                      </button>
                    </li>
                  ))}
                </ul>
                {results.length > visibleCount ? (
                  <Button size="sm" variant="ghost" onClick={() => setVisibleCount((count) => count + LIST_STEP)}>
                    Voir plus
                  </Button>
                ) : null}
              </>
            )}
          </section>
        </div>

        <div className="space-y-4">
          <AttendanceSection period={period} staff={staff} />
          <PerformanceTestsCard staff={staff} canManage={canManagePerformanceTests(roles)} />
        </div>
      </div>

      <SessionStatsModal session={selected} onClose={() => setSelected(null)} />
      <CreateSessionModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["sport", "stats-history"] });
          showToast("Séance créée.");
        }}
      />
    </div>
  );
}
