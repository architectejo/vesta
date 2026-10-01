import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { archiveArticle, listMovements, reactivateArticle, type Article } from "../../api/logistics";
import { Button, ConfirmDialog, Modal, StatusBadge } from "../../design-system";
import { formatDateFr } from "./format";
import { MovementDetailModal } from "./MovementDetailModal";
import { RecordMovementModal } from "./RecordMovementModal";

export interface ArticleDetailModalProps {
  article: Article | null;
  canManage: boolean;
  onClose: () => void;
  onEdit: (article: Article) => void;
  onChanged: (message: string) => void;
  onOpenMatch?: (matchId: number) => void;
  onOpenExpense?: (expenseId: number) => void;
  canSeeExpenseDetail?: boolean;
}

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

const PAGE_STEP = 10;

/** « Article » (détail) — fiche `logistique.md` §4.1. */
export function ArticleDetailModal({
  article,
  canManage,
  onClose,
  onEdit,
  onChanged,
  onOpenMatch,
  onOpenExpense,
  canSeeExpenseDetail = false,
}: ArticleDetailModalProps) {
  const open = article !== null;
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [archiveError, setArchiveError] = useState<string | undefined>(undefined);
  const [archiving, setArchiving] = useState(false);
  const [movementLimit, setMovementLimit] = useState(PAGE_STEP);
  const [recordOpen, setRecordOpen] = useState(false);
  const [selectedMovementId, setSelectedMovementId] = useState<number | null>(null);

  const movementsQuery = useQuery({
    queryKey: ["logistics", "movements", "article", article?.id],
    queryFn: () => listMovements({ article: article?.id }),
    enabled: open,
  });

  async function handleArchiveToggle(): Promise<void> {
    if (!article) return;
    setArchiving(true);
    setArchiveError(undefined);
    try {
      if (article.status === "active") {
        await archiveArticle(article.id);
        onChanged("Article archivé.");
      } else {
        await reactivateArticle(article.id);
        onChanged("Article réactivé.");
      }
      setConfirmArchive(false);
    } catch (error) {
      setArchiveError(apiErrorMessage(error));
    } finally {
      setArchiving(false);
    }
  }

  if (!article) return null;

  const movements = movementsQuery.data?.results ?? [];
  const visibleMovements = movements.slice(0, movementLimit);

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={article.name}
        subtitle={`${article.category_display} · ${article.unit}`}
        size="lg"
        footer={
          <div className="flex w-full items-center justify-end gap-2">
            <Button variant="secondary" size="md" onClick={onClose}>
              Fermer
            </Button>
            {canManage && article.status === "active" ? (
              <Button variant="primary" size="md" onClick={() => setRecordOpen(true)}>
                Enregistrer un mouvement
              </Button>
            ) : null}
          </div>
        }
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-2">
            {article.status === "archived" ? <StatusBadge status="archived" /> : <span />}
            {canManage ? (
              <div className="relative">
                <Button size="sm" variant="ghost" onClick={() => setMenuOpen((v) => !v)}>
                  …
                </Button>
                {menuOpen ? (
                  <div className="absolute right-0 z-10 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated">
                    <button
                      type="button"
                      className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                      onClick={() => {
                        setMenuOpen(false);
                        onEdit(article);
                      }}
                    >
                      Modifier l'article
                    </button>
                    <button
                      type="button"
                      className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                      onClick={() => {
                        setMenuOpen(false);
                        setArchiveError(undefined);
                        setConfirmArchive(true);
                      }}
                    >
                      {article.status === "active" ? "Archiver l'article" : "Réactiver l'article"}
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-md border border-border p-2">
              <p className="text-xs text-text-muted">En stock</p>
              <p className="tabular-nums text-base font-semibold text-text">
                {article.in_stock} {article.unit}
              </p>
            </div>
            <div className="rounded-md border border-border p-2">
              <p className="text-xs text-text-muted">Sortis pour un match</p>
              <p className="tabular-nums text-base font-semibold text-text">{article.loaned_for_match}</p>
            </div>
            <div className="rounded-md border border-border p-2">
              <p className="text-xs text-text-muted">État</p>
              <p className="text-base font-semibold text-text">{article.reference_condition_display}</p>
            </div>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold text-text">Derniers mouvements</h3>
            {movementsQuery.isLoading ? (
              <p className="text-sm text-text-muted">Chargement…</p>
            ) : movements.length === 0 ? (
              <p className="text-sm text-text-muted">Aucun mouvement pour cet article.</p>
            ) : (
              <>
                <ul className="divide-y divide-border">
                  {visibleMovements.map((movement) => (
                    <li key={movement.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedMovementId(movement.id)}
                        className="flex w-full items-center justify-between gap-2 py-2 text-left"
                      >
                        <span className="min-w-0 flex-1 truncate text-sm text-text">
                          {formatDateFr(movement.movement_date)} · {movement.movement_type_display}
                          {movement.membership ? ` · ${movement.membership.name}` : ""}
                        </span>
                        <span className="shrink-0 tabular-nums text-sm text-text">
                          {movement.signed_quantity > 0 ? "+" : ""}
                          {movement.signed_quantity}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                {movements.length > movementLimit ? (
                  <div className="mt-2 text-center">
                    <Button size="sm" variant="secondary" onClick={() => setMovementLimit((l) => l + PAGE_STEP)}>
                      Voir plus
                    </Button>
                  </div>
                ) : null}
              </>
            )}
          </div>

          <p className="text-xs text-text-muted">
            Ajouté par {article.created_by.name || "Système Vesta"} le {formatDateFr(article.created_at.slice(0, 10))}.
          </p>
        </div>
      </Modal>

      <RecordMovementModal
        open={recordOpen}
        lockedArticle={article}
        onClose={() => setRecordOpen(false)}
        onSaved={(message) => {
          setRecordOpen(false);
          void movementsQuery.refetch();
          onChanged(message);
        }}
      />

      <MovementDetailModal
        movementId={selectedMovementId}
        level={2}
        onClose={() => setSelectedMovementId(null)}
        onOpenMatch={onOpenMatch}
        onOpenExpense={onOpenExpense}
        canSeeExpenseDetail={canSeeExpenseDetail}
      />

      <ConfirmDialog
        open={confirmArchive}
        title={article.status === "active" ? `Archiver ${article.name} ?` : `Réactiver ${article.name} ?`}
        description={
          <>
            {article.status === "active" ? (
              <span>
                L'article n'apparaîtra plus dans les choix de mouvement ni dans les prochains inventaires. Son
                historique est conservé.
              </span>
            ) : null}
            {archiveError ? <span className="mt-2 block text-status-danger-fg">{archiveError}</span> : null}
          </>
        }
        confirmLabel={article.status === "active" ? "Archiver" : "Réactiver"}
        danger={article.status === "active"}
        loading={archiving}
        onConfirm={() => void handleArchiveToggle()}
        onCancel={() => setConfirmArchive(false)}
      />
    </>
  );
}
