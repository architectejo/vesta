import { useQuery } from "@tanstack/react-query";
import { getMovement } from "../../api/logistics";
import { getExpense } from "../../api/treasury";
import { Avatar, Modal } from "../../design-system";
import { formatDateFr, formatDateTimeFr } from "./format";
import { UNLOCATED_LABEL } from "./HolderSearch";

export interface MovementDetailModalProps {
  movementId: number | null;
  /** Niveau 2 quand ouverte depuis la fiche d'un article (§4.1). */
  level?: 1 | 2;
  onClose: () => void;
  onOpenMatch?: (matchId: number) => void;
  onOpenExpense?: (expenseId: number) => void;
  /** Le lien et le détail complet de la dépense liée ne sont visibles que
   * pour le Président, le Vice-président et le Trésorier (§4.3). */
  canSeeExpenseDetail?: boolean;
  /** « Voir le déclassement » (mouvement de déclassement, spec B4 §2.3). */
  onOpenDecommission?: (decommissionId: number) => void;
}

/** « Mouvement » (détail, lecture seule) — fiche `logistique.md` §4.3. */
export function MovementDetailModal({
  movementId,
  level = 1,
  onClose,
  onOpenMatch,
  onOpenExpense,
  canSeeExpenseDetail = false,
  onOpenDecommission,
}: MovementDetailModalProps) {
  const open = movementId !== null;
  const query = useQuery({
    queryKey: ["logistics", "movement", movementId],
    queryFn: () => getMovement(movementId as number),
    enabled: open,
  });
  const movement = query.data;

  // Détail de la dépense liée : seulement pour Président/VP/Trésorier, qui
  // ont accès à `/treasury/expenses/` (matrice 2.4). Pour l'Intendant et le
  // Coach, ni la logistique ni la trésorerie n'exposent ce détail à ce jour
  // (point ouvert n° 1 de la fiche d'écran) : aucune donnée n'est inventée.
  const expenseQuery = useQuery({
    queryKey: ["logistics", "movement-expense", movement?.expense_id],
    queryFn: () => getExpense(movement?.expense_id as number),
    enabled: open && canSeeExpenseDetail && Boolean(movement?.expense_id),
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={movement ? `${movement.movement_type_display} · ${movement.article.name}` : "Mouvement"}
      subtitle={movement ? formatDateFr(movement.movement_date) : undefined}
      size="md"
      level={level}
      loading={query.isLoading}
      cancelLabel="Fermer"
    >
      {query.isError ? (
        <p role="alert" className="text-sm text-status-danger-fg">
          Impossible de charger ce détail. Réessayez.
        </p>
      ) : movement ? (
        <div className="space-y-3 text-sm">
          <div className="space-y-2 rounded-md bg-surface-muted p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">Quantité</span>
              <span className="tabular-nums text-text">
                {movement.signed_quantity > 0 ? "+" : ""}
                {movement.signed_quantity} {movement.article.unit}
              </span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">Date</span>
              <span className="text-text">{formatDateFr(movement.movement_date)}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">Motif</span>
              <span className="text-right text-text">{movement.reason || "Aucun motif"}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">Chez</span>
              <span className="text-right text-text">{movement.holder?.name ?? UNLOCATED_LABEL}</span>
            </div>
            {movement.membership ? (
              <div className="flex items-center justify-between gap-2">
                <span className="text-text-muted">Joueur concerné</span>
                <span className="flex items-center gap-2 text-text">
                  <Avatar name={movement.membership.name} size={24} />
                  {movement.membership.name}
                </span>
              </div>
            ) : null}
          </div>

          {movement.provenance ? (
            <div className="space-y-2 rounded-md border border-border p-3">
              <p className="font-semibold text-text">Provenance</p>
              <div className="flex items-center justify-between gap-2">
                <span className="text-text-muted">Origine</span>
                <span className="text-right text-text">{movement.provenance.origin_kind_display}</span>
              </div>
              {movement.provenance.donor ? (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-text-muted">Donateur</span>
                  <span className="text-right text-text">
                    {movement.provenance.donor.name}
                    {movement.provenance.donor.membership_id === null ? " (hors club)" : ""}
                  </span>
                </div>
              ) : null}
              <div className="flex items-center justify-between gap-2">
                <span className="text-text-muted">Date d'acquisition</span>
                <span className="text-right text-text">
                  {movement.provenance.acquisition_date_unknown
                    ? `Date inconnue${movement.provenance.acquisition_date_note ? ` — ${movement.provenance.acquisition_date_note}` : ""}`
                    : movement.provenance.acquisition_date
                      ? formatDateFr(movement.provenance.acquisition_date)
                      : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-text-muted">État à l'entrée</span>
                <span className="text-right text-text">{movement.provenance.condition_at_entry_display}</span>
              </div>
            </div>
          ) : null}

          {movement.transfer_group ? (
            <div className="rounded-md border border-border p-3">
              <p className="font-semibold text-text">Déplacement lié</p>
              <p className="mt-1 text-text-muted">
                {movement.movement_type === "out_transfer"
                  ? "Sortie d'un déplacement : l'entrée correspondante est enregistrée chez le nouveau détenteur."
                  : "Entrée d'un déplacement : la sortie correspondante est enregistrée chez l'ancien détenteur."}
              </p>
            </div>
          ) : null}

          {movement.decommission_id && onOpenDecommission ? (
            <button
              type="button"
              onClick={() => onOpenDecommission(movement.decommission_id as number)}
              className="flex min-h-control-sm items-center text-sm font-medium text-primary-text hover:underline"
            >
              Voir le déclassement
            </button>
          ) : null}

          {movement.match_id ? (
            <button
              type="button"
              onClick={() => {
                onClose();
                onOpenMatch?.(movement.match_id as number);
              }}
              className="inline-flex min-h-control-sm items-center text-sm font-medium text-primary-text hover:underline"
            >
              Voir le match
            </button>
          ) : null}

          {movement.expense_id ? (
            <div className="rounded-md border border-border p-3 text-sm">
              <p className="text-text-muted">Dépense liée</p>
              {canSeeExpenseDetail ? (
                expenseQuery.data ? (
                  <>
                    <p className="mt-1 text-text">
                      Dépense du {formatDateFr(expenseQuery.data.expense_date)} · {expenseQuery.data.category.name} ·{" "}
                      {expenseQuery.data.amount} {expenseQuery.data.currency}
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        onOpenExpense?.(movement.expense_id as number);
                      }}
                      className="inline-flex min-h-control-sm items-center font-medium text-primary-text hover:underline"
                    >
                      Voir la dépense
                    </button>
                  </>
                ) : (
                  <p className="mt-1 text-text-muted">Chargement…</p>
                )
              ) : (
                <p className="mt-1 text-text-muted">
                  Dépense rattachée à cet achat. Le détail n'est pas accessible depuis ce rôle (accès aux dépenses
                  non prévu par la matrice 2.4, point ouvert n° 1 de la fiche d'écran).
                </p>
              )}
            </div>
          ) : null}

          <p className="text-xs text-text-muted">
            Saisi par {movement.recorded_by.name || "Système Vesta"} le {formatDateTimeFr(movement.created_at)}.
          </p>
        </div>
      ) : null}
    </Modal>
  );
}
