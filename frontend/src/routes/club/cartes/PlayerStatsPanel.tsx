import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { getPlayerStats, type PlayerStatsResponse } from "../../../api/playerCards";
import { ApiError } from "../../../api/client";
import { BarChart, Button, EmptyState, RadarChart, Skeleton, StatusBadge } from "../../../design-system";
import { FITNESS_STATUS_KEY, formatPercent, formatRating, formatShortDate, plural } from "./playerCardFormat";

const VISIBLE_CARDS = 3;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-surface p-3">
      <h3 className="mb-2 text-sm font-semibold text-text">{title}</h3>
      {children}
    </section>
  );
}

function RadarSection({ data, fullName }: { data: PlayerStatsResponse; fullName: string }) {
  const axes = data.radar.axes;
  const hasValue = axes.some((axis) => axis.value !== null);
  let body: ReactNode;
  if (axes.length < 3) {
    body = <EmptyState message="Pas assez d'attributs pour tracer le radar." />;
  } else if (!hasValue) {
    body = <EmptyState message="Pas encore de donnée" />;
  } else {
    body = (
      <RadarChart
        title="Radar des attributs"
        axes={axes.map((axis) => ({ label: axis.label }))}
        series={[{ name: fullName, values: axes.map((axis) => (axis.value === null ? null : Number(axis.value))) }]}
        maxValue={10}
        height={240}
      />
    );
  }
  return <Section title="Radar des attributs">{body}</Section>;
}

function RecentFormSection({ data }: { data: PlayerStatsResponse }) {
  const entries = data.recent_form;
  if (entries.length === 0) {
    return (
      <Section title="Forme récente">
        <EmptyState message="Aucune note pour l'instant." />
      </Section>
    );
  }
  // L'API sert la plus récente d'abord ; le graphique se lit de gauche à droite.
  const chronological = [...entries].reverse();
  return (
    <Section title="Forme récente">
      <BarChart
        title="Dernières notes"
        categories={chronological.map((entry) => formatShortDate(entry.date))}
        series={[{ name: "Note", values: chronological.map((entry) => Number(entry.rating)) }]}
        height={120}
        formatValue={(value) => formatRating(String(value))}
      />
      <ul className="mt-2 space-y-1 text-sm text-text">
        {entries.map((entry, index) => (
          <li key={`${entry.date}-${index}`}>
            {formatShortDate(entry.date)} · {entry.label} · <span className="tabular-nums">{formatRating(entry.rating)}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function AttendanceSection({ data }: { data: PlayerStatsResponse }) {
  const a = data.attendance;
  if (a.sessions_expected === 0) {
    return (
      <Section title="Présences">
        <EmptyState message="Aucune séance pointée cette saison." />
      </Section>
    );
  }
  return (
    <Section title="Présences">
      <p className="text-sm text-text">
        {plural(a.sessions_present, "séance", "séances")} sur {a.sessions_expected} · {formatPercent(a.rate)}
      </p>
      <p className="mt-1 text-sm text-text-muted">
        {plural(a.late, "retard", "retards")}
        {" · "}
        {plural(a.excused, "absence excusée", "absences excusées")}
        {" · "}
        {plural(a.absent, "absence", "absences")}
      </p>
    </Section>
  );
}

function DisciplineSection({ data }: { data: PlayerStatsResponse }) {
  const [showAll, setShowAll] = useState(false);
  const { cards, active_suspension: suspension } = data.discipline;
  const shown = showAll ? cards : cards.slice(0, VISIBLE_CARDS);
  return (
    <Section title="Discipline">
      {suspension ? (
        <p className="mb-2">
          <StatusBadge status="suspended" detail={suspension.label.replace(/^Suspendu\s*:\s*/, "")} />
        </p>
      ) : null}
      {cards.length === 0 ? (
        <EmptyState message="Aucun carton cette saison." />
      ) : (
        <>
          <ul className="space-y-1 text-sm text-text">
            {shown.map((card) => (
              <li key={card.id}>
                {formatShortDate(card.date)} · {card.incident_type_label}
                {card.cause_label ? ` · ${card.cause_label}` : ""}
              </li>
            ))}
          </ul>
          {cards.length > VISIBLE_CARDS && !showAll ? (
            <Button className="mt-2" size="sm" variant="secondary" onClick={() => setShowAll(true)}>
              Voir plus
            </Button>
          ) : null}
        </>
      )}
    </Section>
  );
}

/**
 * Blocs de statistiques d'un joueur (club-cartes-joueurs.md §4.2), partagés
 * par le panneau d'ordinateur (à droite de la carte) et la fiche mobile (sous
 * la carte). Les six indicateurs sont déjà sur la carte. Aptitude, suspension
 * et tests de performance ne sont affichés que si l'API les sert (elle les
 * réserve au staff et au joueur lui-même) ; aucune donnée médicale détaillée.
 */
export function PlayerStatsPanel({
  membershipId,
  firstName,
  lastName,
  seasonId,
}: {
  membershipId: number;
  firstName: string;
  lastName: string;
  seasonId: number | null;
}) {
  const query = useQuery({
    queryKey: ["player-stats", membershipId, seasonId],
    queryFn: () => getPlayerStats(membershipId, seasonId),
  });

  if (query.isLoading) {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Chargement des statistiques">
        <Skeleton variant="chart" />
        <Skeleton variant="row" />
        <Skeleton variant="row" />
      </div>
    );
  }
  if (query.isError) {
    const error = query.error;
    if (error instanceof ApiError && error.status === 404) {
      return <EmptyState variant="error" message="Ce joueur ne fait plus partie du club." />;
    }
    return (
      <EmptyState
        variant="error"
        message={`Impossible de charger les statistiques de ${firstName}.`}
        actionLabel="Réessayer"
        onAction={() => void query.refetch()}
      />
    );
  }
  const data = query.data;
  if (!data) return null;
  const fullName = `${firstName} ${lastName}`.trim();

  return (
    <div className="space-y-3">
      <RadarSection data={data} fullName={fullName} />
      <RecentFormSection data={data} />
      <AttendanceSection data={data} />
      <DisciplineSection data={data} />
      {data.fitness ? (
        <Section title="Aptitude">
          <StatusBadge status={FITNESS_STATUS_KEY[data.fitness.status] ?? "fit"} />
          {data.fitness.return_date ? (
            <p className="mt-1 text-sm text-text-muted">retour prévu le {formatShortDate(data.fitness.return_date)}</p>
          ) : null}
        </Section>
      ) : null}
      {data.performance ? (
        <Section title="Tests de performance">
          {data.performance.length === 0 ? (
            <EmptyState message="Aucun résultat de test pour l'instant." />
          ) : (
            <ul className="space-y-1 text-sm text-text">
              {data.performance.map((row) => (
                <li key={row.test.id}>
                  {row.test.name} : <span className="tabular-nums">{row.best.display ?? "—"}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      ) : null}
    </div>
  );
}
