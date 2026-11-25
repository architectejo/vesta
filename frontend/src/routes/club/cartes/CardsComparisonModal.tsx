import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { comparePlayers, type ComparedPlayer, type ComparedPlayerConsultable } from "../../../api/playerCards";
import { searchActiveClubPlayers } from "../../../api/clubs";
import {
  EmptyState,
  Modal,
  PlayerMultiSearch,
  PlayerTradingCard,
  RadarChart,
  Skeleton,
  type PlayerSearchResult,
} from "../../../design-system";
import { formatPercent, formatRating, toCardStats } from "./playerCardFormat";

const MAX_PLAYERS = 4;
const MIN_PLAYERS = 2;

function fullName(p: { firstName: string; lastName: string }): string {
  return `${p.firstName} ${p.lastName}`.trim();
}

function rowsFor(p: ComparedPlayerConsultable): Array<[string, string]> {
  const s = p.stats;
  return [
    ["Club", p.club.name],
    ["Poste", p.position_label || "—"],
    ["Note globale", p.overall_rating === null ? "—" : String(p.overall_rating)],
    ["Matchs", String(s.matches_played)],
    ["Buts", String(s.goals)],
    ["Passes décisives", String(s.assists)],
    ["Cartons", `${s.yellow_cards + s.red_cards} (${s.yellow_cards} jaune(s), ${s.red_cards} rouge(s))`],
    ["Taux de présence", formatPercent(s.attendance_rate)],
    ["Note moyenne", s.average_rating === null ? "—" : `${formatRating(s.average_rating)} sur 10`],
    ["Saison", p.season_label ?? "—"],
  ];
}

const ROW_LABELS = [
  "Club",
  "Poste",
  "Note globale",
  "Matchs",
  "Buts",
  "Passes décisives",
  "Cartons",
  "Taux de présence",
  "Note moyenne",
  "Saison",
];

/**
 * Modale « Comparer des joueurs » (club-carte-joueur.md B3) alimentée par
 * `GET /clubs/players/compare/`. Tout est calculé par l'API : joueur du club
 * (statistiques et radar), joueur d'un autre club (données publiques, pas de
 * radar), ou « plus consultable ».
 */
export function CardsComparisonModal({
  initialPlayers,
  onClose,
}: {
  initialPlayers: PlayerSearchResult[];
  onClose: () => void;
}) {
  const [selected, setSelected] = useState<PlayerSearchResult[]>(initialPlayers.slice(0, MAX_PLAYERS));
  const ids = selected.map((p) => Number(p.id));
  const enabled = ids.length >= MIN_PLAYERS;
  const query = useQuery({
    queryKey: ["player-compare", ids],
    queryFn: () => comparePlayers(ids),
    enabled,
  });
  const atMax = selected.length >= MAX_PLAYERS;
  const byId = new Map<number, ComparedPlayer>((query.data?.results ?? []).map((r) => [r.membership_id, r]));

  const columns = selected.map((player) => ({ player, data: byId.get(Number(player.id)) }));
  const radarColumns = columns.filter(
    (c): c is { player: PlayerSearchResult; data: ComparedPlayerConsultable } =>
      c.data?.consultable === true && c.data.radar !== null && c.data.radar.axes.some((a) => a.value !== null),
  );
  const axes = radarColumns[0]?.data.radar?.axes ?? [];

  return (
    <Modal open onClose={onClose} title="Comparer des joueurs" size="xl" hideFooter cancelLabel="Fermer">
      <div className="space-y-4">
        <div>
          <p className="mb-1 text-sm font-medium text-text">Ajouter un joueur à comparer</p>
          <PlayerMultiSearch
            values={selected}
            onChange={(next) => setSelected(next.slice(0, MAX_PLAYERS))}
            searchPlayers={searchActiveClubPlayers}
            disabled={atMax}
          />
          {atMax ? (
            <p className="mt-1 text-xs text-text-muted">4 joueurs au maximum. Retirez-en un pour en ajouter un autre.</p>
          ) : null}
        </div>

        {!enabled ? (
          <EmptyState message="Choisissez au moins 2 joueurs à comparer." />
        ) : query.isLoading ? (
          <div aria-busy="true" className="space-y-2">
            <Skeleton variant="player-card" className="w-[168px]" />
            <Skeleton variant="row" />
            <Skeleton variant="row" />
          </div>
        ) : query.isError ? (
          <EmptyState
            variant="error"
            message={query.error instanceof Error ? query.error.message : undefined}
            actionLabel="Réessayer"
            onAction={() => void query.refetch()}
          />
        ) : (
          <>
            <div className="flex gap-3 overflow-x-auto pb-2">
              {columns.map(({ player, data }) =>
                data?.consultable ? (
                  <div key={player.id} className="shrink-0">
                    <PlayerTradingCard
                      size="sm"
                      motion="static"
                      firstName={data.first_name}
                      lastName={data.last_name}
                      photoUrl={data.photo}
                      positionLabel={data.position_label}
                      jerseyNumber={data.jersey_number}
                      clubLogoUrl={data.club.logo}
                      clubName={data.club.name}
                      overallRating={data.overall_rating}
                      stats={toCardStats(data.stats)}
                    />
                    {data.scope === "public" ? (
                      <p className="mt-1 text-center text-xs text-text-muted">Données publiques</p>
                    ) : null}
                  </div>
                ) : (
                  <div key={player.id} className="w-[168px] shrink-0 rounded-md border border-border p-3 text-sm text-text">
                    <p className="font-medium">{fullName(player)}</p>
                    <p className="text-text-muted">{data?.detail ?? "Ce joueur n'est plus consultable."}</p>
                  </div>
                ),
              )}
            </div>

            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full border-collapse text-sm">
                <thead className="bg-surface-muted text-xs text-text-muted">
                  <tr>
                    <th scope="col" style={{ width: 120, minWidth: 120 }} className="sticky left-0 z-[1] bg-surface-muted px-3 py-2 text-left">
                      &nbsp;
                    </th>
                    {columns.map(({ player }) => (
                      <th key={player.id} scope="col" style={{ minWidth: 112 }} className="px-3 py-2 text-left font-medium">
                        {fullName(player)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ROW_LABELS.map((label, rowIndex) => (
                    <tr key={label} className="border-t border-border">
                      <td style={{ width: 120, minWidth: 120 }} className="sticky left-0 z-[1] bg-surface px-3 py-2 font-medium text-text">
                        {label}
                      </td>
                      {columns.map(({ player, data }) => (
                        <td key={player.id} className="px-3 py-2 text-text">
                          {data?.consultable
                            ? rowsFor(data)[rowIndex]?.[1]
                            : rowIndex === 0
                              ? "Ce joueur n'est plus consultable."
                              : "—"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div>
              <p className="mb-2 text-sm font-semibold text-text">Radar des attributs</p>
              {radarColumns.length === 0 ? (
                <EmptyState message="Aucun attribut à comparer pour ces joueurs." />
              ) : axes.length < 3 ? (
                <EmptyState message="Pas assez d'attributs pour tracer le radar." />
              ) : (
                <RadarChart
                  title="Radar des attributs"
                  axes={axes.map((a) => ({ label: a.label }))}
                  series={radarColumns.map(({ data }) => ({
                    name: `${data.first_name} ${data.last_name}`,
                    values: (data.radar?.axes ?? []).map((a) => (a.value === null ? null : Number(a.value))),
                  }))}
                  maxValue={10}
                  height={260}
                />
              )}
              <ul className="mt-2 space-y-1 text-xs text-text-muted">
                {columns
                  .filter((c) => !radarColumns.some((r) => r.player.id === c.player.id) && c.data?.consultable)
                  .map(({ player, data }) => (
                    <li key={player.id}>
                      {fullName(player)} —{" "}
                      {data?.consultable && data.scope === "public" ? "attributs non publics" : "pas encore de donnée"}
                    </li>
                  ))}
              </ul>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
