import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  getBoardSection,
  type BoardPeriodQuery,
  type BoardSectionKey,
  type ExpenseItem,
  type PlayerRef,
} from "../../../api/clubBoardDashboard";
import {
  Banner,
  BarChart,
  EmptyState,
  LineChart,
  Loader,
  StatusBadge,
  Tabs,
  type StatusKey,
} from "../../../design-system";
import { Block, List, PagedSection, PlayerRow, Row } from "./BoardParts";
import { UpcomingRow } from "./BoardCards";
import {
  dateLabel,
  formatAmount,
  formatNumber,
  periodKey,
  plural,
  rateNumber,
  rateText,
  shortDate,
  shortMonth,
  toChartNumber,
} from "./format";

const CHART_HEIGHT = 220;

/** Taille de la première page et des « Voir plus », par section (fiche §5). */
const PAGE_SIZE: Partial<Record<BoardSectionKey, number>> = {
  contributions: 20,
  results: 5,
  discipline: 5,
};

export function pageSizeOf(section: BoardSectionKey): number {
  return PAGE_SIZE[section] ?? 10;
}

export interface DetailProps {
  period: BoardPeriodQuery | null;
  currency: string;
}

function useSection<K extends BoardSectionKey>(section: K, period: BoardPeriodQuery | null) {
  const limit = pageSizeOf(section);
  return useQuery({
    queryKey: ["board-dashboard", "section", section, periodKey(period), limit],
    queryFn: () => getBoardSection(section, period, { limit }),
    staleTime: 30_000,
  });
}

function Boundary<T>({ query, children }: { query: UseQueryResult<T>; children: (data: T) => ReactNode }) {
  if (query.isLoading) return <Loader loading variant="list" listSkeleton="row" count={4} />;
  if (query.isError || !query.data) {
    return (
      <EmptyState
        variant="error"
        message="Impossible de charger ce détail."
        actionLabel="Réessayer"
        onAction={() => void query.refetch()}
      />
    );
  }
  return <>{children(query.data)}</>;
}

function ModuleLink({ to, children }: { to: string; children: string }) {
  return (
    <p className="pt-2">
      <Link to={to} className="text-sm font-medium text-primary-text hover:underline">
        {children}
      </Link>
    </p>
  );
}

function playerSub(p: PlayerRef & { position_label?: string }): string | undefined {
  return p.position_label || undefined;
}

// ---------------------------------------------------------------------------
// Présences, assiduité
// ---------------------------------------------------------------------------

export function AttendanceDetail({ period }: DetailProps) {
  const query = useSection("attendance", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-4">
          <LineChart
            title="Taux de présence par séance"
            height={CHART_HEIGHT}
            labels={d.summary.points.map((p) => shortDate(p.date))}
            series={[{ name: "Présence", values: d.summary.points.map((p) => rateNumber(p.rate)) }]}
            yMin={0}
            yMax={100}
            unit="%"
          />
          <p className="text-sm text-text-muted">
            Moyenne {rateText(d.summary.average_rate)} sur {plural(d.summary.events_count, "séance", "séances")}.
            {d.summary.late_counts_absent ? " Un retard compte comme une absence." : ""}
          </p>
          <PagedSection
            key={periodKey(period)}
            title="Séances"
            section="attendance"
            period={period}
            name="sessions"
            list={d.sessions}
            limit={pageSizeOf("attendance")}
            emptyMessage="Aucune séance sur la période."
            renderItem={(s) => (
              <Row
                key={s.event_id}
                title={`${dateLabel(s.date)} · ${s.kind_label}`}
                sub={`Présents ${s.present}/${s.expected} · retards ${s.late} · excusés ${s.excused} · absents ${s.absent}`}
                right={rateText(s.rate)}
              />
            )}
          />
        </div>
      )}
    </Boundary>
  );
}

export function AttendanceRankingDetail({ period }: DetailProps) {
  const query = useSection("attendance_ranking", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <PagedSection
          key={periodKey(period)}
          title="Taux de présence des joueurs"
          section="attendance_ranking"
          period={period}
          name="players"
          list={d.players}
          limit={pageSizeOf("attendance_ranking")}
          emptyMessage="Aucune présence enregistrée sur la période."
          renderItem={(p) => (
            <PlayerRow
              key={p.membership_id}
              name={p.player_name}
              photo={p.photo}
              sub={`Présents ${p.present}/${p.expected} · retards ${p.late} · excusés ${p.excused} · absences ${p.absent}`}
              right={rateText(p.rate)}
            />
          )}
        />
      )}
    </Boundary>
  );
}

// ---------------------------------------------------------------------------
// Finances
// ---------------------------------------------------------------------------

export function ContributionsDetail({ period, currency }: DetailProps) {
  const query = useSection("contributions", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-4">
          <BarChart
            title="Cotisations encaissées par mois"
            height={CHART_HEIGHT}
            categories={d.series.map((p) => shortMonth(p.month))}
            series={[
              { name: `Encaissé (${currency})`, values: d.series.map((p) => toChartNumber(p.collected)) },
              { name: `Dû échu (${currency})`, values: d.series.map((p) => toChartNumber(p.matured_due_total)) },
            ]}
          />
          <p className="text-sm text-text-muted">
            Recouvrement {rateText(d.summary.collection_rate)} · cotisations libres encaissées :{" "}
            {formatAmount(d.summary.collected_free, currency)} (jamais comptées en dette).
          </p>
          <Block title="Par type de cotisation">
            <List>
              {d.by_type.map((t) => (
                <Row
                  key={t.contribution_type_id}
                  title={t.name}
                  sub={
                    t.due_total === null
                      ? `${t.nature_label} · encaissé ${formatAmount(t.collected, currency)}`
                      : `${t.nature_label} · dû ${formatAmount(t.due_total, currency)} · encaissé ${formatAmount(t.collected, currency)}`
                  }
                  right={t.collection_rate === null ? undefined : rateText(t.collection_rate)}
                />
              ))}
            </List>
          </Block>
          <PagedSection
            key={`payments-${periodKey(period)}`}
            title="Derniers paiements"
            section="contributions"
            period={period}
            name="payments"
            list={d.payments}
            limit={pageSizeOf("contributions")}
            emptyMessage="Aucun paiement sur la période."
            renderItem={(p) => (
              <PlayerRow
                key={p.payment_id}
                name={p.player_name}
                photo={p.photo}
                sub={`${p.contribution_type_name} · ${dateLabel(p.paid_on)}${p.status === "cancelled" ? ` · ${p.status_label}` : ""}`}
                right={formatAmount(p.amount, currency)}
              />
            )}
          />
          <PagedSection
            key={`debtors-${periodKey(period)}`}
            title="Joueurs en dette"
            section="contributions"
            period={period}
            name="debtors"
            list={d.debtors}
            limit={pageSizeOf("contributions")}
            emptyMessage="Aucun joueur en dette."
            renderItem={(p) => (
              <PlayerRow
                key={p.membership_id}
                name={p.player_name}
                photo={p.photo}
                right={`En dette : ${formatAmount(p.amount_due, currency)}`}
              />
            )}
          />
          <ModuleLink to="/tresorerie">Ouvrir la trésorerie</ModuleLink>
        </div>
      )}
    </Boundary>
  );
}

type SquadTab = "in_good_standing" | "in_debt" | "pending" | "suspended";

export function SquadStatusDetail({ period, currency }: DetailProps) {
  const query = useSection("squad_status", period);
  const [tab, setTab] = useState<SquadTab>("in_debt");
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-3">
          <Tabs<SquadTab>
            label="Situation des joueurs"
            value={tab}
            onChange={setTab}
            items={[
              { value: "in_good_standing", label: `En ordre (${d.summary.in_good_standing.count})` },
              { value: "in_debt", label: `En dette (${d.summary.in_debt.count})` },
              { value: "pending", label: `En attente (${d.summary.pending.count})` },
              { value: "suspended", label: `Suspendus (${d.summary.suspended.count})` },
            ]}
          />
          {tab === "suspended" ? (
            <PagedSection
              key="suspended"
              section="squad_status"
              period={period}
              name="suspended"
              list={d.suspended}
              limit={pageSizeOf("squad_status")}
              emptyMessage="Aucun joueur suspendu."
              renderItem={(p) => (
                <PlayerRow
                  key={p.membership_id}
                  name={p.player_name}
                  photo={p.photo}
                  sub={`${p.reason_label} · ${plural(p.matches_remaining, "match restant", "matchs restants")}`}
                  right={p.amount_due ? `En dette : ${formatAmount(p.amount_due, currency)}` : undefined}
                />
              )}
            />
          ) : (
            <PagedSection
              key={tab}
              section="squad_status"
              period={period}
              name={tab}
              list={d[tab]}
              limit={pageSizeOf("squad_status")}
              emptyMessage="Aucun joueur dans cette situation."
              renderItem={(p) => (
                <PlayerRow
                  key={p.membership_id}
                  name={p.player_name}
                  photo={p.photo}
                  sub={p.is_suspended ? "Suspendu" : undefined}
                  right={p.amount_due ? `En dette : ${formatAmount(p.amount_due, currency)}` : undefined}
                />
              )}
            />
          )}
          <ModuleLink to="/tresorerie/grille">Ouvrir la grille des cotisations</ModuleLink>
        </div>
      )}
    </Boundary>
  );
}

export function CashDetail({ period, currency }: DetailProps) {
  const query = useSection("cash", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-4">
          <BarChart
            title="Encaissements et dépenses par mois"
            height={CHART_HEIGHT}
            categories={d.months.map((m) => shortMonth(m.month))}
            series={[
              { name: `Encaissé (${currency})`, values: d.months.map((m) => toChartNumber(m.collected)) },
              { name: `Dépensé (${currency})`, values: d.months.map((m) => toChartNumber(m.spent)) },
            ]}
          />
          <p className="text-sm text-text">
            Caisse disponible : {formatAmount(d.summary.available_cash, currency)}
          </p>
          <Block title="Mois par mois">
            <List>
              {[...d.months].reverse().map((m) => (
                <Row
                  key={m.month}
                  title={m.label}
                  sub={`Encaissé ${formatAmount(m.collected, currency)} · dépensé ${formatAmount(m.spent, currency)} · solde du mois ${formatAmount(m.net, currency)}`}
                  right={`Caisse ${formatAmount(m.cash_end, currency)}`}
                />
              ))}
            </List>
          </Block>
          <ModuleLink to="/tresorerie">Ouvrir la trésorerie</ModuleLink>
        </div>
      )}
    </Boundary>
  );
}

const EXPENSE_STATUS: Record<ExpenseItem["status"], StatusKey> = {
  pending: "expense_pending",
  released: "expense_released",
  justified: "expense_justified",
  unjustified: "expense_unjustified",
};

export function ExpensesDetail({ period, currency }: DetailProps) {
  const query = useSection("expenses_by_category", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-4">
          {d.summary.release_blocked && d.summary.release_blocked_reason ? (
            <Banner variant="danger">{d.summary.release_blocked_reason}</Banner>
          ) : null}
          <BarChart
            title="Dépenses par catégorie"
            height={CHART_HEIGHT}
            orientation="horizontal"
            categories={d.categories.map((c) => c.name)}
            series={[{ name: `Dépensé (${currency})`, values: d.categories.map((c) => toChartNumber(c.amount)) }]}
          />
          <p className="text-sm text-text-muted">
            {plural(d.summary.pending_count, "dépense", "dépenses")} à valider (
            {formatAmount(d.summary.pending_amount, currency)}) ·{" "}
            {plural(d.summary.unjustified_count, "dépense non justifiée", "dépenses non justifiées")}.
          </p>
          <PagedSection
            key={periodKey(period)}
            title="Dépenses de la période"
            section="expenses_by_category"
            period={period}
            name="expenses"
            list={d.expenses}
            limit={pageSizeOf("expenses_by_category")}
            emptyMessage="Aucune dépense sur la période."
            renderItem={(e) => (
              <Row
                key={e.expense_id}
                title={`${e.category_name} · ${formatAmount(e.amount, currency)}`}
                sub={`${dateLabel(e.expense_date)}${e.beneficiary_name ? ` · ${e.beneficiary_name}` : ""}`}
                right={<StatusBadge status={EXPENSE_STATUS[e.status] ?? "expense_pending"} />}
              />
            )}
          />
          <ModuleLink to="/tresorerie/depenses">Ouvrir les dépenses</ModuleLink>
        </div>
      )}
    </Boundary>
  );
}

// ---------------------------------------------------------------------------
// Effectif
// ---------------------------------------------------------------------------

export function NewcomersDetail({ period }: DetailProps) {
  const query = useSection("newcomers", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-4">
          <BarChart
            title="Arrivées et départs par mois"
            height={CHART_HEIGHT}
            categories={d.summary.series.map((p) => shortMonth(p.month))}
            series={[
              { name: "Arrivées", values: d.summary.series.map((p) => p.arrivals) },
              { name: "Départs", values: d.summary.series.map((p) => p.departures) },
            ]}
          />
          <PagedSection
            key={`arrivals-${periodKey(period)}`}
            title="Arrivées de la période"
            section="newcomers"
            period={period}
            name="arrivals"
            list={d.arrivals}
            limit={pageSizeOf("newcomers")}
            emptyMessage="Aucun nouveau joueur sur la période."
            renderItem={(a) => (
              <PlayerRow
                key={a.membership_id}
                name={a.player_name}
                photo={a.photo}
                sub={[playerSub(a), `inscrit le ${dateLabel(a.joined_on)}`, a.sponsor_name ? `parrain : ${a.sponsor_name}` : ""]
                  .filter(Boolean)
                  .join(" · ")}
              />
            )}
          />
          <PagedSection
            key={`pending-${periodKey(period)}`}
            title="En attente d'adhésion"
            section="newcomers"
            period={period}
            name="pending"
            list={d.pending}
            limit={pageSizeOf("newcomers")}
            emptyMessage="Aucune adhésion en attente."
            renderItem={(a) => (
              <PlayerRow
                key={a.membership_id}
                name={a.player_name}
                photo={a.photo}
                sub={a.missing_steps.length > 0 ? a.missing_steps.map((s) => s.label).join(" · ") : a.stage_label}
                right={a.stage_label}
              />
            )}
          />
          <PagedSection
            key={`departures-${periodKey(period)}`}
            title="Départs de la période"
            section="newcomers"
            period={period}
            name="departures"
            list={d.departures}
            limit={pageSizeOf("newcomers")}
            emptyMessage="Aucun départ sur la période."
            renderItem={(a) => (
              <PlayerRow
                key={a.membership_id}
                name={a.player_name}
                photo={a.photo}
                sub={[a.left_reason_label, a.left_on ? dateLabel(a.left_on) : ""].filter(Boolean).join(" · ")}
              />
            )}
          />
          <ModuleLink to="/club/comite">Ouvrir Comité et bureau</ModuleLink>
        </div>
      )}
    </Boundary>
  );
}

export function SquadTrendDetail({ period }: DetailProps) {
  const query = useSection("squad_trend", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-4">
          <LineChart
            title="Effectif en fin de mois"
            height={CHART_HEIGHT}
            labels={d.summary.series.map((p) => shortMonth(p.month))}
            series={[{ name: "Joueurs actifs", values: d.summary.series.map((p) => p.count) }]}
          />
          <PagedSection
            key={`arrivals-${periodKey(period)}`}
            title="Arrivées"
            section="squad_trend"
            period={period}
            name="arrivals"
            list={d.arrivals}
            limit={pageSizeOf("squad_trend")}
            emptyMessage="Aucune arrivée sur la période."
            renderItem={(a) => (
              <PlayerRow key={a.membership_id} name={a.player_name} photo={a.photo} sub={`inscrit le ${dateLabel(a.joined_on)}`} />
            )}
          />
          <PagedSection
            key={`departures-${periodKey(period)}`}
            title="Départs"
            section="squad_trend"
            period={period}
            name="departures"
            list={d.departures}
            limit={pageSizeOf("squad_trend")}
            emptyMessage="Aucun départ sur la période."
            renderItem={(a) => (
              <PlayerRow
                key={a.membership_id}
                name={a.player_name}
                photo={a.photo}
                sub={[a.left_reason_label, a.left_on ? dateLabel(a.left_on) : ""].filter(Boolean).join(" · ")}
              />
            )}
          />
        </div>
      )}
    </Boundary>
  );
}

/** Aptitude seulement : aucun diagnostic, aucune circonstance, aucun lien vers un dossier médical. */
export function FitnessDetail({ period }: DetailProps) {
  const query = useSection("fitness", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-4">
          <PagedSection
            key="unfit"
            title="Inaptes"
            section="fitness"
            period={period}
            name="unfit"
            list={d.unfit}
            limit={pageSizeOf("fitness")}
            emptyMessage="Aucun joueur inapte."
            renderItem={(p) => (
              <PlayerRow
                key={p.membership_id}
                name={p.player_name}
                photo={p.photo}
                sub={p.return_date ? `retour prévu le ${dateLabel(p.return_date)}` : "Date de retour non précisée"}
              />
            )}
          />
          <PagedSection
            key="restricted"
            title="Aptes avec restriction"
            section="fitness"
            period={period}
            name="restricted"
            list={d.restricted}
            limit={pageSizeOf("fitness")}
            emptyMessage="Aucun joueur apte avec restriction."
            renderItem={(p) => (
              <PlayerRow
                key={p.membership_id}
                name={p.player_name}
                photo={p.photo}
                sub={p.return_date ? `jusqu'au ${dateLabel(p.return_date)}` : undefined}
              />
            )}
          />
          <details>
            <summary className="min-h-[36px] cursor-pointer text-base font-semibold text-text">
              Aptes ({d.fit.count})
            </summary>
            <PagedSection
              key="fit"
              section="fitness"
              period={period}
              name="fit"
              list={d.fit}
              limit={pageSizeOf("fitness")}
              emptyMessage="Aucun joueur apte."
              renderItem={(p) => <PlayerRow key={p.membership_id} name={p.player_name} photo={p.photo} />}
            />
          </details>
          <p className="text-[13px] text-text-muted">{d.summary.notice}</p>
        </div>
      )}
    </Boundary>
  );
}

// ---------------------------------------------------------------------------
// Sport
// ---------------------------------------------------------------------------

export function ResultsDetail({ period }: DetailProps) {
  const query = useSection("results", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-4">
          <p className="text-sm text-text">
            {plural(d.summary.played, "match joué", "matchs joués")} : {d.summary.wins} V · {d.summary.draws} N ·{" "}
            {d.summary.losses} D · {formatNumber(d.summary.goals_for)} buts marqués,{" "}
            {formatNumber(d.summary.goals_against)} encaissés.
          </p>
          <PagedSection
            key={periodKey(period)}
            title="Matchs de la période"
            section="results"
            period={period}
            name="matches"
            list={d.matches}
            limit={pageSizeOf("results")}
            emptyMessage="Aucun match joué sur la période."
            renderItem={(m) => (
              <Row
                key={m.match_id}
                title={`${m.venue_label} · ${m.opponent}`}
                sub={`${dateLabel(m.date)} · ${m.match_type_label}`}
                right={`${m.goals_for}-${m.goals_against} · ${m.result_label}`}
              />
            )}
          />
          <Block title="Meilleurs buteurs">
            {d.top_scorers.length === 0 ? (
              <EmptyState message="Aucun but sur la période." />
            ) : (
              <List>
                {d.top_scorers.map((p) => (
                  <PlayerRow key={p.membership_id} name={p.player_name} photo={p.photo} right={formatNumber(p.count)} />
                ))}
              </List>
            )}
          </Block>
          <Block title="Meilleurs passeurs">
            {d.top_assists.length === 0 ? (
              <EmptyState message="Aucune passe décisive sur la période." />
            ) : (
              <List>
                {d.top_assists.map((p) => (
                  <PlayerRow key={p.membership_id} name={p.player_name} photo={p.photo} right={formatNumber(p.count)} />
                ))}
              </List>
            )}
          </Block>
        </div>
      )}
    </Boundary>
  );
}

export function DisciplineDetail({ period }: DetailProps) {
  const query = useSection("discipline", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-4">
          <BarChart
            title="Cartons par mois"
            height={CHART_HEIGHT}
            stacked
            categories={d.summary.series.map((p) => shortMonth(p.month))}
            series={[
              { name: "Jaunes", values: d.summary.series.map((p) => p.yellow) },
              { name: "Rouges", values: d.summary.series.map((p) => p.red) },
              { name: "Sanctions internes", values: d.summary.series.map((p) => p.internal) },
            ]}
          />
          <PagedSection
            key="suspensions"
            title="Suspensions en cours"
            section="discipline"
            period={period}
            name="suspensions"
            list={d.suspensions}
            limit={pageSizeOf("discipline")}
            emptyMessage="Aucune suspension en cours."
            renderItem={(s) => (
              <PlayerRow
                key={s.membership_id}
                name={s.player_name}
                photo={s.photo}
                sub={s.reason_label}
                right={plural(s.matches_remaining, "match restant", "matchs restants")}
              />
            )}
          />
          <PagedSection
            key={`incidents-${periodKey(period)}`}
            title="Incidents de la période"
            section="discipline"
            period={period}
            name="incidents"
            list={d.incidents}
            limit={pageSizeOf("discipline")}
            emptyMessage="Aucun incident sur la période."
            renderItem={(i) => (
              <PlayerRow
                key={i.incident_id}
                name={i.player_name}
                photo={i.photo}
                sub={[
                  dateLabel(i.date),
                  i.cause_label,
                  i.cause_detail,
                  i.minute !== null ? `${i.minute}'` : "",
                ]
                  .filter(Boolean)
                  .join(" · ")}
                right={i.type_label}
              />
            )}
          />
          <Block title="Joueurs les plus sanctionnés">
            {d.most_sanctioned.length === 0 ? (
              <EmptyState message="Aucune sanction sur la période." />
            ) : (
              <List>
                {d.most_sanctioned.map((p) => (
                  <PlayerRow
                    key={p.membership_id}
                    name={p.player_name}
                    photo={p.photo}
                    sub={`${p.yellow} jaune(s) · ${p.red} rouge(s) · ${p.internal} sanction(s) interne(s)`}
                    right={formatNumber(p.total)}
                  />
                ))}
              </List>
            )}
          </Block>
        </div>
      )}
    </Boundary>
  );
}

export function CoachNotesDetail({ period }: DetailProps) {
  const query = useSection("coach_notes", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-4">
          <LineChart
            title="Note moyenne par mois"
            height={CHART_HEIGHT}
            labels={d.summary.series.map((p) => shortMonth(p.month))}
            series={[{ name: "Note moyenne", values: d.summary.series.map((p) => toChartNumber(p.average)) }]}
            yMin={0}
            yMax={10}
          />
          <PagedSection
            key={periodKey(period)}
            title="Séances et matchs notés"
            section="coach_notes"
            period={period}
            name="events"
            list={d.events}
            limit={pageSizeOf("coach_notes")}
            emptyMessage="Aucune note sur la période."
            renderItem={(e) => (
              <Row
                key={e.event_id}
                title={`${dateLabel(e.date)} · ${e.kind_label}`}
                sub={plural(e.evaluations, "évaluation", "évaluations")}
                right={e.average === null ? "—" : `${formatNumber(e.average)} / 10`}
              />
            )}
          />
        </div>
      )}
    </Boundary>
  );
}

// ---------------------------------------------------------------------------
// Échéances, à traiter, matériel, fil
// ---------------------------------------------------------------------------

export function UpcomingDetail({ period, currency }: DetailProps) {
  const agenda = useSection("upcoming", period);
  const finance = useSection("upcoming_finance", period);
  return (
    <div className="space-y-4">
      <Boundary query={agenda}>
        {(d) => (
          <PagedSection
            key="agenda"
            title="Agenda"
            section="upcoming"
            period={period}
            name="items"
            list={d.items}
            limit={pageSizeOf("upcoming")}
            emptyMessage="Rien de prévu dans les 30 prochains jours."
            renderItem={(item, index) => (
              <UpcomingRow key={`${item.kind}-${item.date}-${index}`} item={item} currency={currency} />
            )}
          />
        )}
      </Boundary>
      <Boundary query={finance}>
        {(d) => (
          <PagedSection
            key="finance"
            title="Échéances financières"
            section="upcoming_finance"
            period={period}
            name="upcoming"
            list={d.upcoming}
            limit={pageSizeOf("upcoming_finance")}
            emptyMessage="Aucune échéance financière dans les 30 prochains jours."
            renderItem={(item, index) => (
              <UpcomingRow key={`${item.kind}-${item.date}-${index}`} item={item} currency={currency} />
            )}
          />
        )}
      </Boundary>
    </div>
  );
}

export function ToProcessDetail({ period, currency }: DetailProps) {
  const query = useSection("to_process", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <PagedSection
          key="to-process"
          title="Éléments à traiter"
          section="to_process"
          period={period}
          name="items"
          list={d.items}
          limit={pageSizeOf("to_process")}
          emptyMessage="Rien à traiter pour le moment."
          renderItem={(item) => (
            <PlayerRow
              key={`${item.kind}-${item.ref_id}`}
              name={item.player_name ?? item.label}
              photo={item.photo}
              sub={item.player_name ? item.label : item.date ? dateLabel(item.date) : undefined}
              right={item.amount ? formatAmount(item.amount, currency) : undefined}
            />
          )}
        />
      )}
    </Boundary>
  );
}

export function EquipmentDetail({ period }: DetailProps) {
  const query = useSection("equipment_out", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-3">
          <PagedSection
            key="loans"
            title="Prêts en cours"
            section="equipment_out"
            period={period}
            name="loans"
            list={d.loans}
            limit={pageSizeOf("equipment_out")}
            emptyMessage="Aucun matériel à retourner."
            renderItem={(l, index) => (
              <Row
                key={`${l.article_id}-${index}`}
                title={`${l.quantity} × ${l.article_name}`}
                sub={`${l.player_name ?? (l.players_count > 1 ? `${l.players_count} joueurs` : "Joueur non précisé")} · depuis le ${dateLabel(l.since)}`}
                right={l.is_overdue ? `En retard de ${plural(l.overdue_days, "jour", "jours")}` : undefined}
              />
            )}
          />
          <ModuleLink to="/materiel">Ouvrir le matériel</ModuleLink>
        </div>
      )}
    </Boundary>
  );
}

export function FeedDetail({ period }: DetailProps) {
  const query = useSection("feed_activity", period);
  return (
    <Boundary query={query}>
      {(d) => (
        <div className="space-y-4">
          <BarChart
            title={d.summary.granularity === "week" ? "Publications par semaine" : "Publications par mois"}
            height={CHART_HEIGHT}
            categories={d.summary.series.map((p) => p.label.replace("Semaine du ", ""))}
            series={[{ name: "Publications", values: d.summary.series.map((p) => p.posts) }]}
          />
          <PagedSection
            key={periodKey(period)}
            title="Publications"
            section="feed_activity"
            period={period}
            name="posts"
            list={d.posts}
            limit={pageSizeOf("feed_activity")}
            emptyMessage="Aucune publication sur la période."
            renderItem={(p) => (
              <Row
                key={p.post_id}
                title={p.excerpt || p.kind_label}
                sub={`${p.author_name} · ${dateLabel(p.date)}`}
                right={`${p.likes_count} réaction(s) · ${p.comments_count} commentaire(s)`}
              />
            )}
          />
        </div>
      )}
    </Boundary>
  );
}
