import type { PlayerCardListRow } from "../../../api/playerCards";
import { Button, Modal, PlayerTradingCard, StatusBadge, useClubBranding } from "../../../design-system";
import { PlayerStatsPanel } from "./PlayerStatsPanel";
import { availabilityBadge, toCardStats } from "./playerCardFormat";

/**
 * Carte `md` et ses statistiques (club-cartes-joueurs.md §3.2 et §4.1).
 * `side` : carte à gauche, statistiques à droite (ordinateur, sans modale) ;
 * `stacked` : statistiques sous la carte (fiche mobile).
 */
export function PlayerDetail({
  row,
  seasonId,
  seasonLabel,
  layout,
}: {
  row: PlayerCardListRow;
  seasonId: number | null;
  seasonLabel: string | null;
  layout: "side" | "stacked";
}) {
  const branding = useClubBranding();
  const badge = row.availability ? availabilityBadge(row.availability) : null;
  return (
    <div className={layout === "side" ? "grid grid-cols-[280px_1fr] items-start gap-4" : "space-y-3"}>
      <div>
        <PlayerTradingCard
          firstName={row.first_name}
          lastName={row.last_name}
          photoUrl={row.photo}
          positionLabel={row.position_label}
          positionDetail={row.position_detail}
          jerseyNumber={row.jersey_number}
          clubLogoUrl={branding?.logoUrl ?? null}
          clubName={branding?.name ?? ""}
          overallRating={row.overall_rating}
          stats={toCardStats(row.stats)}
          seasonLabel={seasonLabel ?? undefined}
        />
        {badge ? (
          <p className="mt-2 text-center">
            <StatusBadge status={badge.status} detail={badge.detail} label={badge.label} />
          </p>
        ) : null}
      </div>
      <PlayerStatsPanel
        membershipId={row.membership_id}
        firstName={row.first_name}
        lastName={row.last_name}
        seasonId={seasonId}
      />
    </div>
  );
}

/** Modale « Fiche du joueur » (mobile) : carte puis statistiques, navigation par boutons. */
export function PlayerDetailModal({
  rows,
  index,
  seasonId,
  seasonLabel,
  canCompare,
  onNavigate,
  onCompare,
  onClose,
}: {
  rows: PlayerCardListRow[];
  index: number;
  seasonId: number | null;
  seasonLabel: string | null;
  canCompare: boolean;
  onNavigate: (index: number) => void;
  onCompare: (row: PlayerCardListRow) => void;
  onClose: () => void;
}) {
  const row = rows[index];
  if (!row) return null;
  return (
    <Modal
      open
      onClose={onClose}
      title="Fiche du joueur"
      size="lg"
      cancelLabel="Fermer"
      footer={
        <div className="flex w-full items-center justify-between gap-2">
          <Button variant="secondary" size="md" onClick={onClose}>
            Fermer
          </Button>
          {canCompare ? (
            <Button variant="secondary" size="md" onClick={() => onCompare(row)}>
              Comparer
            </Button>
          ) : null}
        </div>
      }
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <Button size="md" variant="secondary" disabled={index <= 0} onClick={() => onNavigate(index - 1)}>
          Joueur précédent
        </Button>
        <Button size="md" variant="secondary" disabled={index >= rows.length - 1} onClick={() => onNavigate(index + 1)}>
          Joueur suivant
        </Button>
      </div>
      <PlayerDetail row={row} seasonId={seasonId} seasonLabel={seasonLabel} layout="stacked" />
    </Modal>
  );
}
