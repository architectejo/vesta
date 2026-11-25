import { useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getSessionStats,
  type MembershipBrief,
  type PlayerNoteRow,
  type SessionAttendanceStats,
  type SessionEvaluationStats,
  type SessionStats,
} from "../../api/sport";
import {
  Avatar,
  BarChart,
  Button,
  DataTable,
  EmptyState,
  KpiTile,
  Loader,
  Modal,
  SegmentedControl,
  StackedBar,
  type DataTableColumn,
} from "../../design-system";
import { formatDayMonth, formatNote, formatRate, formatSignedInt, formatSignedNote } from "./statsFormat";
import { formatTime } from "./sportTime";
import { SessionMeasuresCard } from "./performance/SessionMeasuresCard";

type ListKey = "late" | "excused" | "absent";
const LIST_PAGE = 5;

function PlayerLine({ player, right }: { player: MembershipBrief; right?: string }) {
  return (
    <li className="flex min-h-11 items-center gap-2 py-1">
      <Avatar name={player.name} photoUrl={player.photo} size={32} />
      <span className="min-w-0 flex-1 break-words text-sm text-text">{player.name}</span>
      {right ? <span className="shrink-0 text-sm text-text-muted">{right}</span> : null}
    </li>
  );
}

function ExpandableList({
  title,
  count,
  open,
  onToggle,
  emptyText,
  children,
  innerRef,
}: {
  title: string;
  count: number;
  open: boolean;
  onToggle: () => void;
  emptyText: string;
  children: (limit: number | null) => ReactNode;
  innerRef: (node: HTMLDivElement | null) => void;
}) {
  const [all, setAll] = useState(false);
  return (
    <div ref={innerRef} className="border-t border-border">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="flex h-10 w-full items-center justify-between text-left text-sm font-medium text-text"
      >
        <span>
          {title} ({count})
        </span>
        <span aria-hidden="true" className="text-text-muted">
          {open ? "−" : "+"}
        </span>
      </button>
      {open ? (
        count === 0 ? (
          <p className="pb-2 text-sm text-text-muted">{emptyText}</p>
        ) : (
          <div className="pb-2">
            <ul className="divide-y divide-border">{children(all ? null : LIST_PAGE)}</ul>
            {count > LIST_PAGE && !all ? (
              <Button size="sm" variant="ghost" onClick={() => setAll(true)}>
                Voir plus
              </Button>
            ) : null}
          </div>
        )
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// A4.1 Carte « Présence »
// ---------------------------------------------------------------------------

function AttendanceCard({ attendance }: { attendance: SessionAttendanceStats }) {
  const [open, setOpen] = useState<Record<ListKey, boolean>>({ late: false, excused: false, absent: false });
  const refs = useRef<Partial<Record<ListKey, HTMLDivElement | null>>>({});

  function reveal(key: ListKey): void {
    setOpen((current) => ({ ...current, [key]: true }));
    window.setTimeout(() => refs.current[key]?.scrollIntoView?.({ block: "nearest" }), 0);
  }
  const toggle = (key: ListKey) => setOpen((current) => ({ ...current, [key]: !current[key] }));

  const a = attendance;
  return (
    <section aria-label="Présence" className="rounded-md border border-border p-3">
      <h3 className="mb-2 text-base font-semibold text-text">Présence</h3>
      {a.nobody_marked ? (
        <p className="mb-2 text-sm text-text-muted">Personne n'est encore pointé.</p>
      ) : null}
      <div className="grid grid-cols-2 gap-2 min-[400px]:grid-cols-3">
        <KpiTile label="Taux de présence" value={formatRate(a.rate)} hint={`${a.expected} joueurs attendus`} />
        <KpiTile label="Présents" value={a.present} family="success" statusLabel="Pointés" />
        <KpiTile
          label={a.late_label}
          value={a.late}
          family={a.late_family}
          statusLabel={a.late_counts_as_absent ? "Compté absent" : "Compté présent"}
          onClick={() => reveal("late")}
        />
        <KpiTile label="Absents" value={a.absent} family="danger" statusLabel="Non pointés" onClick={() => reveal("absent")} />
        <KpiTile
          label="Excusés"
          value={a.excused}
          family="neutral"
          statusLabel="Absence excusée"
          onClick={() => reveal("excused")}
        />
        {a.delta_vs_average !== null ? (
          <KpiTile
            label="Écart avec la moyenne"
            value={`${formatSignedInt(a.delta_vs_average)} pts`}
            hint="par rapport aux 10 dernières séances"
          />
        ) : null}
      </div>

      {a.nobody_marked ? null : (
        <div className="mt-3">
          <StackedBar
            title="Répartition de la présence"
            segments={[
              { label: "Présents", value: a.present, family: "success" },
              { label: a.late_label, value: a.late, family: a.late_family },
              { label: "Excusés", value: a.excused, family: "neutral" },
              { label: "Absents", value: a.absent, family: "danger" },
            ]}
          />
        </div>
      )}

      <div className="mt-3">
        <ExpandableList
          title="En retard"
          count={a.late_list.length}
          open={open.late}
          onToggle={() => toggle("late")}
          emptyText="Aucun retard."
          innerRef={(node) => {
            refs.current.late = node;
          }}
        >
          {(limit) =>
            a.late_list
              .slice(0, limit ?? undefined)
              .map((p) => <PlayerLine key={p.membership_id} player={p} right={formatTime(p.arrived_at)} />)
          }
        </ExpandableList>
        <ExpandableList
          title="Excusés"
          count={a.excused_list.length}
          open={open.excused}
          onToggle={() => toggle("excused")}
          emptyText="Aucune absence excusée."
          innerRef={(node) => {
            refs.current.excused = node;
          }}
        >
          {(limit) =>
            a.excused_list
              .slice(0, limit ?? undefined)
              .map((p) => <PlayerLine key={p.membership_id} player={p} right={p.reason} />)
          }
        </ExpandableList>
        <ExpandableList
          title="Absents"
          count={a.absent_list.length}
          open={open.absent}
          onToggle={() => toggle("absent")}
          emptyText="Aucun absent."
          innerRef={(node) => {
            refs.current.absent = node;
          }}
        >
          {(limit) => a.absent_list.slice(0, limit ?? undefined).map((p) => <PlayerLine key={p.membership_id} player={p} />)}
        </ExpandableList>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// A5.3 Modale « Notes de la séance »
// ---------------------------------------------------------------------------

type NoteSort = "note" | "name";

function NotesDetailModal({
  open,
  onClose,
  date,
  evaluations,
  onEvaluate,
}: {
  open: boolean;
  onClose: () => void;
  date: string;
  evaluations: SessionEvaluationStats;
  onEvaluate?: () => void;
}) {
  const [sort, setSort] = useState<NoteSort>("note");
  const [commentsOf, setCommentsOf] = useState<PlayerNoteRow | null>(null);

  const rows = evaluations.players.slice().sort((x, y) =>
    sort === "name"
      ? x.player.name.localeCompare(y.player.name, "fr")
      : Number(y.overall) - Number(x.overall) || x.player.name.localeCompare(y.player.name, "fr"),
  );
  const dash = (value: string | null) => (value === null ? "—" : formatNote(value));

  const columns: Array<DataTableColumn<PlayerNoteRow>> = [
    {
      key: "player",
      header: "Joueur",
      widthPx: 140,
      render: (row) => (
        <span className="flex items-center gap-2">
          <Avatar name={row.player.name} photoUrl={row.player.photo} size={24} />
          <span className="break-words">{row.player.name}</span>
        </span>
      ),
    },
    { key: "overall", header: "Note", render: (row) => <strong>{formatNote(row.overall)}</strong> },
    { key: "technical", header: "Technique", render: (row) => dash(row.technical) },
    { key: "physical", header: "Physique", render: (row) => dash(row.physical) },
    { key: "tactical", header: "Tactique", render: (row) => dash(row.tactical) },
    { key: "mental", header: "Mental", render: (row) => dash(row.mental) },
    { key: "attitude", header: "Attitude", render: (row) => dash(row.attitude) },
    { key: "evaluators", header: "Évaluateurs", render: (row) => row.evaluators_count },
    {
      key: "comment",
      header: "Commentaire",
      render: (row) =>
        row.comments.length === 0 ? (
          "—"
        ) : (
          <Button size="sm" variant="ghost" onClick={() => setCommentsOf(row)}>
            Voir
          </Button>
        ),
    },
  ];

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        size="lg"
        title={`Notes de la séance du ${formatDayMonth(`${date}T12:00:00`)}`}
        subtitle={`${evaluations.evaluated} joueurs évalués sur ${evaluations.eligible} · moyenne ${formatNote(
          evaluations.average,
        )} sur 10`}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>
              Fermer
            </Button>
            {onEvaluate ? <Button onClick={onEvaluate}>Modifier les notes</Button> : null}
          </>
        }
      >
        <div className="space-y-3">
          <SegmentedControl<NoteSort>
            label="Trier par"
            value={sort}
            onChange={setSort}
            options={[
              { value: "note", label: "Note" },
              { value: "name", label: "Nom" },
            ]}
          />
          {rows.length === 0 ? (
            <EmptyState message="Aucune note pour cette séance." />
          ) : (
            <DataTable
              columns={columns}
              rows={rows}
              getRowId={(row) => row.player.membership_id}
              getSearchableText={(row) => `${row.player.name} ${row.player.jersey_number ?? ""}`}
              searchPlaceholder="Nom ou numéro"
              resultLabel="joueurs"
              stickyFirstColumn
            />
          )}
          {evaluations.not_evaluated.length > 0 ? (
            <div>
              <h4 className="mb-1 text-sm font-semibold text-text">
                Pas encore évalués ({evaluations.not_evaluated.length})
              </h4>
              <ul className="divide-y divide-border">
                {evaluations.not_evaluated.map((p) => (
                  <PlayerLine key={p.membership_id} player={p} />
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </Modal>
      <Modal
        open={commentsOf !== null}
        onClose={() => setCommentsOf(null)}
        level={2}
        size="sm"
        title={commentsOf ? `Commentaires : ${commentsOf.player.name}` : ""}
        hideFooter
      >
        <ul className="space-y-3">
          {commentsOf?.comments.map((comment, index) => (
            <li key={index} className="text-sm text-text">
              <p className="break-words">{comment.text}</p>
              <p className="text-xs text-text-muted">
                {comment.visible_to_player ? "Visible par le joueur" : "Non visible par le joueur"}
              </p>
            </li>
          ))}
        </ul>
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------------------
// A4.2 Carte « Notes du Coach » (uniquement si l'API fournit `evaluations`)
// ---------------------------------------------------------------------------

function RankedList({ title, items }: { title: string; items: SessionEvaluationStats["best"] }) {
  return (
    <div>
      <h4 className="mb-1 text-sm font-semibold text-text">{title}</h4>
      <ul className="divide-y divide-border">
        {items.map((item) => (
          <li key={item.player.membership_id} className="flex min-h-11 items-center gap-2 py-1">
            <span className="w-5 shrink-0 text-sm tabular-nums text-text-muted">{item.rank}</span>
            <Avatar name={item.player.name} photoUrl={item.player.photo} size={32} />
            <span className="min-w-0 flex-1 break-words text-sm text-text">{item.player.name}</span>
            <span className="shrink-0 text-base font-semibold tabular-nums text-text">{formatNote(item.note)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CoachNotesCard({
  stats,
  evaluations,
  onEvaluate,
}: {
  stats: SessionStats;
  evaluations: SessionEvaluationStats;
  onEvaluate?: () => void;
}) {
  const [detailOpen, setDetailOpen] = useState(false);
  const [distributionOpen, setDistributionOpen] = useState(false);
  const ev = evaluations;
  const canEvaluate = Boolean(onEvaluate) && stats.capabilities.can_evaluate && ev.remaining > 0;

  const context = ev.locked
    ? `Évaluations verrouillées depuis le ${formatDayMonth(ev.open_until)}`
    : `Évaluations ouvertes encore ${ev.hours_left ?? 0} h`;
  const progress = ev.eligible > 0 ? Math.min(100, Math.round((ev.evaluated / ev.eligible) * 100)) : 0;

  return (
    <section aria-label="Notes du Coach" className="rounded-md border border-border p-3">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-2">
        <h3 className="text-base font-semibold text-text">Notes du Coach</h3>
        <p className="text-[13px] text-text-muted">{context}</p>
      </div>

      {ev.evaluated === 0 ? (
        <EmptyState
          message={ev.locked ? "Aucune note n'a été saisie dans les 48 heures." : "Aucune note pour cette séance."}
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 min-[400px]:grid-cols-3">
            <KpiTile label="Note moyenne" value={`${formatNote(ev.average)} sur 10`} hint="Moyenne des notes globales retenues" />
            <KpiTile
              label="Joueurs évalués"
              value={
                <>
                  {ev.evaluated} sur {ev.eligible}
                  <span className="mt-1 block h-1 w-full overflow-hidden rounded-full bg-surface-muted" aria-hidden="true">
                    <span className="block h-full bg-primary" style={{ width: `${progress}%` }} />
                  </span>
                </>
              }
              hint="évalués sur pointés"
            />
            {ev.delta_vs_average !== null ? (
              <KpiTile
                label="Écart avec la moyenne"
                value={formatSignedNote(ev.delta_vs_average)}
                hint="par rapport aux 10 dernières séances"
              />
            ) : null}
          </div>

          <div className="mt-3 space-y-3">
            {ev.ranking_available ? (
              <>
                <RankedList title="Meilleures notes" items={ev.best} />
                {ev.lowest.length > 0 ? <RankedList title="Notes les plus faibles" items={ev.lowest} /> : null}
              </>
            ) : (
              <p className="text-sm text-text-muted">Pas assez de notes pour un classement.</p>
            )}

            <div>
              <button
                type="button"
                aria-expanded={distributionOpen}
                onClick={() => setDistributionOpen((value) => !value)}
                className="h-9 text-sm font-medium text-primary-text"
              >
                {distributionOpen ? "Masquer la répartition" : "Voir la répartition"}
              </button>
              {distributionOpen ? (
                <BarChart
                  title="Répartition des notes"
                  categories={ev.distribution.map((bucket) => bucket.label)}
                  series={[{ name: "Joueurs", values: ev.distribution.map((bucket) => bucket.count) }]}
                />
              ) : null}
            </div>
          </div>
        </>
      )}

      <div className="mt-3 flex flex-wrap justify-end gap-2">
        {ev.players.length > 0 || ev.not_evaluated.length > 0 ? (
          <Button size="sm" variant="secondary" onClick={() => setDetailOpen(true)}>
            Voir toutes les notes
          </Button>
        ) : null}
        {canEvaluate ? (
          <Button size="sm" onClick={onEvaluate}>
            Évaluer les joueurs
          </Button>
        ) : null}
      </div>

      <NotesDetailModal
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        date={stats.date}
        evaluations={ev}
        onEvaluate={
          canEvaluate
            ? () => {
                setDetailOpen(false);
                onEvaluate?.();
              }
            : undefined
        }
      />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Vue du joueur : « Ma note » (jamais de moyenne d'équipe ni de classement)
// ---------------------------------------------------------------------------

const CRITERIA_LABELS: Array<[keyof NonNullable<SessionStats["my_evaluation"]>["criteria"], string]> = [
  ["technical", "Technique"],
  ["physical", "Physique"],
  ["tactical", "Tactique"],
  ["mental", "Mental"],
  ["attitude", "Attitude"],
];

function MyNoteCard({ mine }: { mine: SessionStats["my_evaluation"] }) {
  return (
    <section aria-label="Ma note" className="rounded-md border border-border p-3">
      <h3 className="mb-2 text-base font-semibold text-text">Ma note</h3>
      {mine === null ? (
        <p className="text-sm text-text-muted">Vous n'avez pas encore été évalué pour cette séance.</p>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-text">
            Votre note : <strong className="text-base tabular-nums">{formatNote(mine.overall)}</strong> sur 10
          </p>
          <p className="text-sm text-text-muted">
            {CRITERIA_LABELS.filter(([key]) => mine.criteria[key] !== null)
              .map(([key, label]) => `${label} ${formatNote(mine.criteria[key])}`)
              .join(" · ")}
          </p>
          {mine.comments.map((comment, index) => (
            <p key={index} className="break-words rounded-sm bg-surface-muted p-2 text-sm text-text">
              {comment}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Panneau complet
// ---------------------------------------------------------------------------

export interface SessionStatsPanelProps {
  sessionId: number;
  /** Ouvre « Évaluer les joueurs » ; absent en lecture seule (modale « Séance »). */
  onEvaluate?: () => void;
  /** Ouvre l'écran de mesure ; absent en lecture seule (modale « Séance »). */
  onMeasure?: (testId?: number) => void;
  /** Mesures en attente d'envoi ou refusées (hors connexion), affichées dans la carte des mesures. */
  measuresExtra?: ReactNode;
}

export const sessionStatsKey = (sessionId: number) => ["sport", "session-stats", sessionId] as const;

/**
 * Statistiques d'une séance : présence, « Notes du Coach » ou « Ma note »
 * selon ce que l'API renvoie (jamais plus), puis « Mesures de la séance »
 * (partie C : le joueur n'y voit que les siennes, côté API).
 */
export function SessionStatsPanel({ sessionId, onEvaluate, onMeasure, measuresExtra }: SessionStatsPanelProps) {
  const query = useQuery({
    queryKey: sessionStatsKey(sessionId),
    queryFn: () => getSessionStats(sessionId),
    refetchInterval: 30_000,
  });

  if (query.isLoading) return <Loader loading variant="list" listSkeleton="card" count={2} />;
  if (query.isError || !query.data) {
    return (
      <EmptyState
        variant="error"
        message="Impossible de charger les statistiques."
        actionLabel="Réessayer"
        onAction={() => void query.refetch()}
      />
    );
  }
  const stats = query.data;
  const online = typeof navigator === "undefined" || navigator.onLine;
  const stamp = formatTime(stats.generated_at);

  return (
    <div className="space-y-4">
      <AttendanceCard attendance={stats.attendance} />
      {stats.evaluations ? (
        <CoachNotesCard stats={stats} evaluations={stats.evaluations} onEvaluate={onEvaluate} />
      ) : (
        <MyNoteCard mine={stats.my_evaluation} />
      )}
      <SessionMeasuresCard
        sessionId={sessionId}
        measures={stats.measures}
        canMeasure={stats.capabilities.can_measure}
        onMeasure={onMeasure}
        extra={measuresExtra}
      />
      {stamp ? (
        <p className="text-xs text-text-muted">{online ? `Mis à jour à ${stamp}` : `Données du ${stamp}`}</p>
      ) : null}
    </div>
  );
}
