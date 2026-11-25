import type { ReactNode } from "react";
import {
  isCardError,
  type AttendanceCard,
  type AttendanceRankingCard,
  type BoardDashboard,
  type CashCard,
  type Card,
  type CoachNotesCard,
  type ContributionsCard,
  type DisciplineCard,
  type EquipmentOutCard,
  type ExpensesByCategoryCard,
  type FeedActivityCard,
  type FitnessCard,
  type NewcomersCard,
  type ResultsCard,
  type SquadStatusCard,
  type SquadTrendCard,
  type ToProcessCard,
  type UpcomingCard,
  type UpcomingFinanceCard,
  type UpcomingItem,
} from "../../../api/clubBoardDashboard";
import {
  Avatar,
  BarChart,
  ChartCard,
  FormStrip,
  KpiTile,
  LineChart,
  StackedBar,
  StatusBadge,
} from "../../../design-system";
import {
  dateLabel,
  formatAmount,
  formatNumber,
  plural,
  rateNumber,
  rateText,
  shortDate,
  shortMonth,
  toChartNumber,
} from "./format";

/** Mois affichés dans un graphique de carte à 360 px ; la modale montre tout. */
const CARD_MONTHS = 6;

export interface CardEnv {
  currency: string;
  periodLabel: string;
  periodMode: "month" | "season";
  /** Relance du chargement de la page (un seul appel pour toutes les cartes). */
  onRetry: () => void;
  retrying: boolean;
}

interface CardProps<T> {
  card: Card<T>;
  env: CardEnv;
  onOpen: () => void;
}

const TODAY = "Aujourd'hui";

function errorCard<T extends object>(title: string, card: Card<T>, env: CardEnv, periodLabel: string) {
  if (!isCardError(card)) return null;
  return (
    <ChartCard
      title={title}
      periodLabel={periodLabel}
      state={env.retrying ? "loading" : "error"}
      errorMessage={card.error}
      onRetry={env.onRetry}
    />
  );
}

function lastMonths<T>(series: T[]): T[] {
  return series.slice(-CARD_MONTHS);
}

// ---------------------------------------------------------------------------
// P1
// ---------------------------------------------------------------------------

export function AttendanceBoardCard({ card, env, onOpen }: CardProps<AttendanceCard>) {
  const title = "Présences";
  if (isCardError(card)) return errorCard(title, card, env, env.periodLabel);
  const empty = card.events_count === 0;
  return (
    <ChartCard
      title={title}
      periodLabel={env.periodLabel}
      onOpen={onOpen}
      state={empty ? "empty" : "ready"}
      emptyMessage="Aucune séance sur la période."
      value={`${rateText(card.average_rate)} de présence moyenne`}
      caption={`Dernière séance ${rateText(card.last_rate)} · ${plural(card.events_count, "séance", "séances")}`}
    >
      <LineChart
        title="Taux de présence par séance"
        labels={card.points.map((p) => shortDate(p.date))}
        series={[{ name: "Présence", values: card.points.map((p) => rateNumber(p.rate)) }]}
        yMin={0}
        yMax={100}
        unit="%"
        reference={
          rateNumber(card.average_rate) !== null
            ? { value: rateNumber(card.average_rate) as number, label: `Moyenne ${rateText(card.average_rate)}` }
            : undefined
        }
      />
    </ChartCard>
  );
}

export function ContributionsBoardCard({ card, env, onOpen }: CardProps<ContributionsCard>) {
  const title = "Cotisations";
  if (isCardError(card)) return errorCard(title, card, env, env.periodLabel);
  const empty = Number(card.due_total) === 0 && Number(card.collected) === 0;
  const series = lastMonths(card.series);
  return (
    <ChartCard
      title={title}
      periodLabel={env.periodLabel}
      onOpen={onOpen}
      state={empty ? "empty" : "ready"}
      emptyMessage="Aucune cotisation due sur la période."
      value={`${rateText(card.collection_rate)} recouvré`}
      caption={`${formatAmount(card.collected, env.currency)} encaissés`}
    >
      <BarChart
        title="Cotisations encaissées par mois"
        categories={series.map((p) => shortMonth(p.month))}
        series={[
          { name: `Encaissé (${env.currency})`, values: series.map((p) => toChartNumber(p.collected)) },
          { name: `Dû échu (${env.currency})`, values: series.map((p) => toChartNumber(p.matured_due_total)) },
        ]}
      />
    </ChartCard>
  );
}

export function NewcomersBoardCard({ card, env, onOpen }: CardProps<NewcomersCard>) {
  const title = "Nouveaux venus";
  if (isCardError(card)) return errorCard(title, card, env, env.periodLabel);
  const empty = card.arrivals_count === 0 && card.pending_count === 0;
  const series = lastMonths(card.series);
  return (
    <ChartCard
      title={title}
      periodLabel={env.periodLabel}
      onOpen={onOpen}
      state={empty ? "empty" : "ready"}
      emptyMessage={env.periodMode === "month" ? "Aucun nouveau joueur ce mois-ci." : "Aucun nouveau joueur cette saison."}
      value={plural(card.arrivals_count, "nouveau joueur", "nouveaux joueurs")}
      caption={card.pending_count > 0 ? `${plural(card.pending_count, "adhésion", "adhésions")} en attente` : undefined}
    >
      <div className="space-y-2">
        {card.avatars.length > 0 ? (
          <ul className="flex flex-wrap gap-1" aria-label="Derniers arrivés">
            {card.avatars.map((a) => (
              <li key={a.membership_id}>
                <Avatar name={a.player_name ?? "Joueur"} photoUrl={a.photo} size={32} />
              </li>
            ))}
          </ul>
        ) : null}
        <BarChart
          title="Arrivées par mois"
          height={120}
          categories={series.map((p) => shortMonth(p.month))}
          series={[{ name: "Arrivées", values: series.map((p) => p.arrivals) }]}
        />
      </div>
    </ChartCard>
  );
}

const OUTCOME = { V: "win", N: "draw", D: "loss" } as const;

export function ResultsBoardCard({ card, env, onOpen }: CardProps<ResultsCard>) {
  const title = "Résultats";
  if (isCardError(card)) return errorCard(title, card, env, env.periodLabel);
  return (
    <ChartCard
      title={title}
      periodLabel={env.periodLabel}
      onOpen={onOpen}
      state={card.played === 0 ? "empty" : "ready"}
      emptyMessage="Aucun match joué sur la période."
      value={`${card.wins} V · ${card.draws} N · ${card.losses} D`}
      caption={`${plural(card.goals_for, "but marqué", "buts marqués")}, ${formatNumber(card.goals_against)} encaissés`}
    >
      <FormStrip
        title="Forme des 5 derniers matchs"
        results={card.form.map((m) => ({
          outcome: OUTCOME[m.result],
          opponent: m.opponent,
          score: `${m.goals_for}-${m.goals_against}`,
          date: shortDate(m.date),
        }))}
      />
    </ChartCard>
  );
}

export function DisciplineBoardCard({ card, env, onOpen }: CardProps<DisciplineCard>) {
  const title = "Discipline";
  if (isCardError(card)) return errorCard(title, card, env, env.periodLabel);
  const empty =
    card.yellow_cards + card.red_cards + card.internal_sanctions + card.suspended_count === 0;
  const series = lastMonths(card.series);
  return (
    <ChartCard
      title={title}
      periodLabel={`${env.periodLabel} · suspensions : ${TODAY.toLowerCase()}`}
      onOpen={onOpen}
      state={empty ? "empty" : "ready"}
      emptyMessage="Aucun carton ni suspension sur la période."
      value={plural(card.suspended_count, "joueur suspendu", "joueurs suspendus")}
      caption={`${plural(card.yellow_cards, "jaune", "jaunes")}, ${plural(card.red_cards, "rouge", "rouges")} sur la période`}
    >
      <BarChart
        title="Cartons par mois"
        stacked
        categories={series.map((p) => shortMonth(p.month))}
        series={[
          { name: "Jaunes", values: series.map((p) => p.yellow) },
          { name: "Rouges", values: series.map((p) => p.red) },
        ]}
      />
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// P2
// ---------------------------------------------------------------------------

export function SquadStatusBoardCard({ card, env, onOpen }: CardProps<SquadStatusCard>) {
  const title = "Situation de l'effectif";
  if (isCardError(card)) return errorCard(title, card, env, TODAY);
  return (
    <ChartCard
      title={title}
      periodLabel={TODAY}
      onOpen={onOpen}
      value={plural(card.total, "joueur", "joueurs")}
      caption={
        card.in_debt.count > 0
          ? `En dette : ${formatAmount(card.in_debt.amount, env.currency)} au total`
          : "Aucun joueur en dette."
      }
    >
      <StackedBar
        title="Situation des joueurs"
        segments={[
          { label: "En ordre", value: card.in_good_standing.count, family: "success" },
          { label: "En dette", value: card.in_debt.count, family: "danger" },
          { label: "En attente", value: card.pending.count, family: "warning" },
          { label: "Suspendus", value: card.suspended.count, family: "suspended" },
        ]}
      />
    </ChartCard>
  );
}

export function CashBoardCard({ card, env, onOpen }: CardProps<CashCard>) {
  const title = "Caisse";
  if (isCardError(card)) return errorCard(title, card, env, env.periodLabel);
  const empty =
    Number(card.collected) === 0 &&
    Number(card.spent) === 0 &&
    card.series.every((p) => Number(p.collected) === 0 && Number(p.spent) === 0);
  const series = lastMonths(card.series);
  return (
    <ChartCard
      title="Caisse : encaissements et dépenses"
      periodLabel={env.periodLabel}
      onOpen={onOpen}
      state={empty ? "empty" : "ready"}
      emptyMessage="Aucun mouvement de caisse sur la période."
      value={`Caisse disponible : ${formatAmount(card.available_cash, env.currency)}`}
      caption={`${formatAmount(card.collected, env.currency)} encaissés · ${formatAmount(card.spent, env.currency)} dépensés`}
    >
      <BarChart
        title="Encaissements et dépenses par mois"
        categories={series.map((p) => shortMonth(p.month))}
        series={[
          { name: `Encaissé (${env.currency})`, values: series.map((p) => toChartNumber(p.collected)) },
          { name: `Dépensé (${env.currency})`, values: series.map((p) => toChartNumber(p.spent)) },
        ]}
      />
    </ChartCard>
  );
}

export function ExpensesBoardCard({ card, env, onOpen }: CardProps<ExpensesByCategoryCard>) {
  const title = "Dépenses par catégorie";
  if (isCardError(card)) return errorCard(title, card, env, env.periodLabel);
  const empty = card.categories.length === 0 && card.pending_count === 0 && card.unjustified_count === 0;
  return (
    <ChartCard
      title={title}
      periodLabel={env.periodLabel}
      onOpen={onOpen}
      state={empty ? "empty" : "ready"}
      emptyMessage="Aucune dépense sur la période."
      value={formatAmount(card.total_spent, env.currency)}
      caption={
        card.pending_count > 0
          ? `${plural(card.pending_count, "dépense", "dépenses")} à valider (${formatAmount(card.pending_amount, env.currency)})`
          : undefined
      }
    >
      <div className="space-y-2">
        {card.unjustified_count > 0 ? (
          <p className="flex flex-wrap items-center gap-2 text-sm text-text">
            <StatusBadge status="to_justify" />
            {plural(card.unjustified_count, "dépense non justifiée", "dépenses non justifiées")}
          </p>
        ) : null}
        <BarChart
          title="Dépenses par catégorie"
          orientation="horizontal"
          categories={card.categories.map((c) => c.name)}
          series={[{ name: `Dépensé (${env.currency})`, values: card.categories.map((c) => toChartNumber(c.amount)) }]}
        />
      </div>
    </ChartCard>
  );
}

export function SquadTrendBoardCard({ card, env, onOpen }: CardProps<SquadTrendCard>) {
  const title = "Évolution de l'effectif";
  if (isCardError(card)) return errorCard(title, card, env, env.periodLabel);
  return (
    <ChartCard
      title={title}
      periodLabel={env.periodLabel}
      onOpen={onOpen}
      state={card.series.length === 0 ? "empty" : "ready"}
      emptyMessage="Aucune donnée d'effectif sur la période."
      value={`${plural(card.current_count, "joueur actif", "joueurs actifs")}`}
      caption={`+${plural(card.arrivals_count, "arrivée", "arrivées")}, −${plural(card.departures_count, "départ", "départs")} sur la période`}
    >
      <LineChart
        title="Effectif en fin de mois"
        labels={card.series.map((p) => shortMonth(p.month))}
        series={[{ name: "Joueurs actifs", values: card.series.map((p) => p.count) }]}
      />
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Aptitude (aucun diagnostic) et échéances
// ---------------------------------------------------------------------------

export function FitnessBoardCard({ card, env, onOpen }: CardProps<FitnessCard>) {
  const title = "Aptitude de l'effectif";
  if (isCardError(card)) return errorCard(title, card, env, TODAY);
  let state: "ready" | "empty" = "ready";
  let emptyMessage = "";
  if (card.no_information) {
    state = "empty";
    emptyMessage = "Aucune information d'aptitude enregistrée.";
  } else if (card.unfit === 0 && card.fit_with_restriction === 0) {
    state = "empty";
    emptyMessage = "Tous les joueurs sont aptes.";
  }
  return (
    <ChartCard
      title={title}
      periodLabel={TODAY}
      onOpen={onOpen}
      state={state}
      emptyMessage={emptyMessage}
      value={plural(card.unfit, "joueur inapte", "joueurs inaptes")}
      caption={`${plural(card.fit_with_restriction, "apte avec restriction", "aptes avec restriction")} · ${card.fit} aptes`}
    >
      <div className="space-y-2">
        <StackedBar
          title="Aptitude des joueurs"
          segments={[
            { label: "Aptes", value: card.fit, family: "success" },
            { label: "Aptes avec restriction", value: card.fit_with_restriction, family: "warning" },
            { label: "Inaptes", value: card.unfit, family: "danger" },
          ]}
        />
        {card.unfit_players.length > 0 ? (
          <ul className="text-sm text-text">
            {card.unfit_players.map((p) => (
              <li key={p.membership_id} className="break-words">
                {p.player_name}
                {p.return_date ? ` · retour prévu le ${dateLabel(p.return_date)}` : ""}
              </li>
            ))}
          </ul>
        ) : null}
        <p className="text-[13px] text-text-muted">{card.notice}</p>
      </div>
    </ChartCard>
  );
}

const UPCOMING_KIND: Record<UpcomingItem["kind"], string> = {
  session: "Séance",
  match: "Match",
  assembly: "AG",
  licence: "Licence",
  contribution_due: "Échéance",
  expense_justification: "Justificatif",
};

export function upcomingKindLabel(kind: UpcomingItem["kind"]): string {
  return UPCOMING_KIND[kind] ?? kind;
}

export function UpcomingRow({ item, currency }: { item: UpcomingItem; currency: string }) {
  const parts = [upcomingKindLabel(item.kind)];
  if (item.time) parts.push(item.time.slice(0, 5));
  if (item.detail) parts.push(item.detail);
  if (item.amount) parts.push(formatAmount(item.amount, currency));
  return (
    <li className="flex gap-3 py-1.5 text-sm">
      <span className="w-14 shrink-0 tabular-nums text-text-muted">{shortDate(item.date)}</span>
      <span className="min-w-0 flex-1 break-words text-text">
        {item.label}
        <span className="block text-xs text-text-muted">{parts.join(" · ")}</span>
      </span>
    </li>
  );
}

interface UpcomingProps {
  upcoming: Card<UpcomingCard>;
  finance: Card<UpcomingFinanceCard>;
  env: CardEnv;
  onOpen: () => void;
}

/** Agenda (matchs, séances, AG, licence) fusionné avec les échéances financières (fiche §4, carte 11). */
export function UpcomingBoardCard({ upcoming, finance, env, onOpen }: UpcomingProps) {
  const title = "Prochaines échéances";
  const upcomingFailed = isCardError(upcoming);
  const financeFailed = isCardError(finance);
  if (upcomingFailed && financeFailed) return errorCard(title, upcoming, env, TODAY);
  const agenda = isCardError(upcoming) ? [] : upcoming.items;
  const money = isCardError(finance) ? [] : finance.items;
  const items = [...agenda, ...money].sort((a, b) => a.date.localeCompare(b.date)).slice(0, 5);
  const count = (isCardError(upcoming) ? 0 : upcoming.count) + (isCardError(finance) ? 0 : finance.count);
  return (
    <ChartCard
      title={title}
      periodLabel={`${TODAY} → 30 jours`}
      onOpen={onOpen}
      state={count === 0 ? "empty" : "ready"}
      emptyMessage="Rien de prévu dans les 30 prochains jours."
      value={`${count} à venir`}
      caption={
        upcomingFailed || financeFailed
          ? "Une partie des échéances n'a pas pu être chargée."
          : undefined
      }
    >
      <ul className="divide-y divide-border">
        {items.map((item, index) => (
          <UpcomingRow key={`${item.kind}-${item.date}-${index}`} item={item} currency={env.currency} />
        ))}
      </ul>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// P3
// ---------------------------------------------------------------------------

function RankingList({ heading, rows }: { heading: string; rows: AttendanceRankingCard["top"] }) {
  return (
    <div className="min-w-0">
      <p className="text-sm font-medium text-text">{heading}</p>
      <ul className="mt-1 space-y-1.5">
        {rows.map((r) => (
          <li key={r.membership_id} className="text-sm text-text">
            <span className="flex justify-between gap-2">
              <span className="min-w-0 break-words">{r.player_name}</span>
              <span className="shrink-0 tabular-nums">{rateText(r.rate)}</span>
            </span>
            <span aria-hidden="true" className="block h-1 rounded-full bg-surface-muted">
              <span
                className="block h-1 rounded-full bg-[var(--color-series-1)]"
                style={{ width: `${Math.min(100, Math.max(0, rateNumber(r.rate) ?? 0))}%` }}
              />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AttendanceRankingBoardCard({ card, env, onOpen }: CardProps<AttendanceRankingCard>) {
  const title = "Assiduité par joueur";
  if (isCardError(card)) return errorCard(title, card, env, env.periodLabel);
  return (
    <ChartCard
      title={title}
      periodLabel={env.periodLabel}
      onOpen={onOpen}
      state={card.players_count === 0 ? "empty" : "ready"}
      emptyMessage="Aucune présence enregistrée sur la période."
    >
      <div className="space-y-3">
        <RankingList heading="Les plus assidus" rows={card.top} />
        <RankingList heading="Les moins assidus" rows={card.bottom} />
      </div>
    </ChartCard>
  );
}

export function ToProcessBoardCard({ card, env, onOpen }: CardProps<ToProcessCard>) {
  const title = "À traiter";
  if (isCardError(card)) return errorCard(title, card, env, TODAY);
  return (
    <ChartCard
      title={title}
      periodLabel={TODAY}
      onOpen={onOpen}
      state={card.total === 0 ? "empty" : "ready"}
      emptyMessage="Rien à traiter pour le moment."
      value={plural(card.total, "élément", "éléments")}
    >
      <div className="grid grid-cols-2 gap-2">
        <KpiTile label="Dépenses à valider" value={card.counts.expenses_to_validate} />
        <KpiTile label="Demandes d'assistance" value={card.counts.assistance_requests} />
        <KpiTile label="PV à signer" value={card.counts.minutes_to_sign} />
        <KpiTile label="Adhésions bloquées" value={card.counts.blocked_applications} />
      </div>
    </ChartCard>
  );
}

export function EquipmentBoardCard({ card, env, onOpen }: CardProps<EquipmentOutCard>) {
  const title = "Matériel à retourner";
  if (isCardError(card)) return errorCard(title, card, env, TODAY);
  return (
    <ChartCard
      title={title}
      periodLabel={TODAY}
      onOpen={onOpen}
      state={card.lines_count === 0 ? "empty" : "ready"}
      emptyMessage="Aucun matériel à retourner."
      value={plural(card.articles_count, "article à retourner", "articles à retourner")}
      caption={card.overdue_count > 0 ? `${card.overdue_count} en retard` : undefined}
    >
      <ul className="divide-y divide-border">
        {card.items.map((loan, index) => (
          <li key={`${loan.article_id}-${index}`} className="py-1.5 text-sm text-text">
            <span className="break-words">
              {loan.quantity} × {loan.article_name}
            </span>
            <span className="block text-xs text-text-muted">
              {loan.player_name ?? (loan.players_count > 1 ? `${loan.players_count} joueurs` : "Joueur non précisé")} ·
              depuis le {dateLabel(loan.since)}
              {loan.is_overdue ? ` · en retard de ${plural(loan.overdue_days, "jour", "jours")}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </ChartCard>
  );
}

export function CoachNotesBoardCard({ card, env, onOpen }: CardProps<CoachNotesCard>) {
  const title = "Notes du Coach";
  if (isCardError(card)) return errorCard(title, card, env, env.periodLabel);
  const series = lastMonths(card.series);
  return (
    <ChartCard
      title={title}
      periodLabel={env.periodLabel}
      onOpen={onOpen}
      state={card.events_count === 0 ? "empty" : "ready"}
      emptyMessage="Aucune note sur la période."
      value={card.average === null ? "—" : `${formatNumber(card.average)} / 10`}
      caption={`${plural(card.evaluations, "évaluation", "évaluations")} · ${plural(card.events_count, "séance ou match", "séances ou matchs")}`}
    >
      <LineChart
        title="Note moyenne par mois"
        labels={series.map((p) => shortMonth(p.month))}
        series={[{ name: "Note moyenne", values: series.map((p) => toChartNumber(p.average)) }]}
        yMin={0}
        yMax={10}
      />
    </ChartCard>
  );
}

export function FeedBoardCard({ card, env, onOpen }: CardProps<FeedActivityCard>) {
  const title = "Activité du fil";
  if (isCardError(card)) return errorCard(title, card, env, env.periodLabel);
  return (
    <ChartCard
      title={title}
      periodLabel={env.periodLabel}
      onOpen={onOpen}
      state={card.posts_count === 0 ? "empty" : "ready"}
      emptyMessage="Aucune publication sur la période."
      value={plural(card.posts_count, "publication", "publications")}
      caption={`${plural(card.comments_count, "commentaire", "commentaires")} · ${plural(card.likes_count, "réaction", "réactions")}`}
    >
      <BarChart
        title={card.granularity === "week" ? "Publications par semaine" : "Publications par mois"}
        categories={card.series.map((p) => p.label.replace("Semaine du ", ""))}
        series={[{ name: "Publications", values: card.series.map((p) => p.posts) }]}
      />
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Grille ordonnée P1 -> P3 (fiche §4, « Ordre à l'écran »)
// ---------------------------------------------------------------------------

export type CardOpenKey = Exclude<keyof BoardDashboard, "period" | "currency" | "as_of" | "upcoming_finance">;

export function BoardCardsGrid({
  data,
  env,
  onOpen,
}: {
  data: BoardDashboard;
  env: CardEnv;
  onOpen: (key: CardOpenKey) => void;
}): ReactNode {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      <AttendanceBoardCard card={data.attendance} env={env} onOpen={() => onOpen("attendance")} />
      <ContributionsBoardCard card={data.contributions} env={env} onOpen={() => onOpen("contributions")} />
      <SquadStatusBoardCard card={data.squad_status} env={env} onOpen={() => onOpen("squad_status")} />
      <CashBoardCard card={data.cash} env={env} onOpen={() => onOpen("cash")} />
      <ResultsBoardCard card={data.results} env={env} onOpen={() => onOpen("results")} />
      <DisciplineBoardCard card={data.discipline} env={env} onOpen={() => onOpen("discipline")} />
      <NewcomersBoardCard card={data.newcomers} env={env} onOpen={() => onOpen("newcomers")} />
      <FitnessBoardCard card={data.fitness} env={env} onOpen={() => onOpen("fitness")} />
      <UpcomingBoardCard
        upcoming={data.upcoming}
        finance={data.upcoming_finance}
        env={env}
        onOpen={() => onOpen("upcoming")}
      />
      <ExpensesBoardCard card={data.expenses_by_category} env={env} onOpen={() => onOpen("expenses_by_category")} />
      <SquadTrendBoardCard card={data.squad_trend} env={env} onOpen={() => onOpen("squad_trend")} />
      <AttendanceRankingBoardCard card={data.attendance_ranking} env={env} onOpen={() => onOpen("attendance_ranking")} />
      <ToProcessBoardCard card={data.to_process} env={env} onOpen={() => onOpen("to_process")} />
      <EquipmentBoardCard card={data.equipment_out} env={env} onOpen={() => onOpen("equipment_out")} />
      <CoachNotesBoardCard card={data.coach_notes} env={env} onOpen={() => onOpen("coach_notes")} />
      <FeedBoardCard card={data.feed_activity} env={env} onOpen={() => onOpen("feed_activity")} />
    </div>
  );
}
