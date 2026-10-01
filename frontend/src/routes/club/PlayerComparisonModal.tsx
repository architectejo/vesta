import { useQueries } from "@tanstack/react-query";
import { useState } from "react";
import { getPlayerCard, searchActiveClubPlayers } from "../../api/clubs";
import {
  Banner,
  EmptyState,
  Modal,
  PlayerMultiSearch,
  PlayerTradingCard,
  Skeleton,
  useClubBranding,
  type PlayerSearchResult,
} from "../../design-system";

const MAX_PLAYERS = 4;
const MIN_PLAYERS = 2;

const TABLE_ROWS = [
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
] as const;

/**
 * Modale « Comparer des joueurs » (club-carte-joueur.md B3), portée réduite
 * au périmètre réellement servi par l'API aujourd'hui : identité, poste et
 * rôles d'un joueur **de ce club** (`GET /clubs/players/{id}/card/`, déjà
 * utilisé par la « Fiche du joueur »). Les six indicateurs, la note
 * globale, le radar et la portée « Tous les clubs » dépendent de champs qui
 * n'existent pas encore côté API (`overall_rating`, `stats`, recherche
 * publique inter-clubs) : conformément à B1 (« Aucune donnée » -> « — ») et
 * à CLAUDE.md §3 (aucune donnée inventée), ils sont affichés dans leur état
 * « pas encore de donnée » plutôt que masqués ou simulés. Voir le compte
 * rendu de tâche pour le détail des champs manquants, à construire par
 * `backend-dev` avant de retirer cette limitation.
 */
export function PlayerComparisonModal({
  initialPlayer,
  onClose,
}: {
  initialPlayer?: PlayerSearchResult;
  onClose: () => void;
}) {
  const branding = useClubBranding();
  const [selected, setSelected] = useState<PlayerSearchResult[]>(initialPlayer ? [initialPlayer] : []);

  const cardQueries = useQueries({
    queries: selected.map((player) => ({
      queryKey: ["player-card", player.id],
      queryFn: () => getPlayerCard(Number(player.id)),
    })),
  });

  function handleChange(next: PlayerSearchResult[]): void {
    setSelected(next.slice(0, MAX_PLAYERS));
  }

  const atMax = selected.length >= MAX_PLAYERS;
  const isLoading = cardQueries.some((q) => q.isLoading);

  return (
    <Modal open onClose={onClose} title="Comparer des joueurs" size="xl" hideFooter cancelLabel="Fermer">
      <div className="space-y-4">
        <Banner variant="info">
          Les statistiques sportives (matchs, buts, note globale…) ne sont pas encore disponibles : seuls
          l'identité, le poste et les rôles sont comparés pour l'instant.
        </Banner>

        <div>
          <p className="mb-1 text-sm font-medium text-text">Ajouter un joueur à comparer</p>
          <PlayerMultiSearch
            values={selected}
            onChange={handleChange}
            searchPlayers={searchActiveClubPlayers}
            disabled={atMax}
            renderMeta={(player) => (
              <span>{[player.number != null ? `n° ${player.number}` : null, player.position].filter(Boolean).join(" · ")}</span>
            )}
          />
          {atMax ? (
            <p className="mt-1 text-xs text-text-muted">
              4 joueurs au maximum. Retirez-en un pour en ajouter un autre.
            </p>
          ) : null}
        </div>

        {selected.length < MIN_PLAYERS ? (
          <EmptyState message="Choisissez au moins 2 joueurs à comparer." />
        ) : (
          <>
            <div className="flex gap-3 overflow-x-auto pb-2">
              {selected.map((player, index) => {
                const card = cardQueries[index]?.data;
                return (
                  <div key={player.id} className="shrink-0">
                    {cardQueries[index]?.isLoading ? (
                      <Skeleton variant="player-card" className="w-[168px]" />
                    ) : card ? (
                      <PlayerTradingCard
                        size="sm"
                        motion="static"
                        firstName={card.first_name}
                        lastName={card.last_name}
                        photoUrl={card.photo}
                        positionLabel={card.position_label}
                        jerseyNumber={card.jersey_number}
                        clubLogoUrl={branding?.logoUrl ?? null}
                        clubName={branding?.name ?? ""}
                        overallRating={null}
                      />
                    ) : null}
                  </div>
                );
              })}
            </div>

            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full border-collapse text-sm">
                <thead className="bg-surface-muted text-xs text-text-muted">
                  <tr>
                    <th scope="col" style={{ width: 120, minWidth: 120 }} className="sticky left-0 z-[1] bg-surface-muted px-3 py-2 text-left">
                      &nbsp;
                    </th>
                    {selected.map((player) => (
                      <th key={player.id} scope="col" style={{ width: 112, minWidth: 112 }} className="px-3 py-2 text-left font-medium">
                        {player.firstName} {player.lastName}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {TABLE_ROWS.map((rowLabel) => (
                    <tr key={rowLabel} className="border-t border-border">
                      <td style={{ width: 120, minWidth: 120 }} className="sticky left-0 z-[1] bg-surface px-3 py-2 font-medium text-text">
                        {rowLabel}
                      </td>
                      {selected.map((player, index) => {
                        const card = cardQueries[index]?.data;
                        const value =
                          rowLabel === "Club"
                            ? (branding?.name ?? "—")
                            : rowLabel === "Poste"
                              ? (card?.position_label ?? "—")
                              : "—";
                        return (
                          <td key={player.id} className="px-3 py-2 text-text">
                            {value}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div>
              <p className="mb-2 text-sm font-semibold text-text">Radar des attributs</p>
              <EmptyState message="Pas assez d'attributs pour tracer le radar." />
            </div>
          </>
        )}
        {isLoading && selected.length >= MIN_PLAYERS ? <p className="text-xs text-text-muted">Chargement…</p> : null}
      </div>
    </Modal>
  );
}
