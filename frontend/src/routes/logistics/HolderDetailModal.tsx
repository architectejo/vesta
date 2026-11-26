import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { archiveHolder, getArticle, getHolder, renameHolder, type HolderDetail } from "../../api/logistics";
import {
  Button,
  ConfirmDialog,
  IconButton,
  IconMore,
  Modal,
  StatusBadge,
  TextField,
} from "../../design-system";
import { useClosingState } from "../../hooks/useClosingState";
import { ArticleDetailModal } from "./ArticleDetailModal";
import { formatDateFr } from "./format";
import { TransferModal } from "./TransferModal";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

const ARTICLES_STEP = 10;

export interface HolderDetailModalProps {
  holderId: number | null;
  canManage: boolean;
  canSeeExpenseDetail?: boolean;
  onClose: () => void;
  /** Écriture réussie (renommage, archivage, déplacement) : message du toast. */
  onChanged: (message: string) => void;
  /** « Voir plus » des mouvements : filtre le registre de la page sur ce détenteur. */
  onShowAllMovements: (holder: { id: number; name: string }) => void;
}

/** « Détenteur » (détail), spec B4 §1.2. */
export function HolderDetailModal({
  holderId,
  canManage,
  canSeeExpenseDetail = false,
  onClose,
  onChanged,
  onShowAllMovements,
}: HolderDetailModalProps) {
  const open = holderId !== null;
  const query = useQuery({
    queryKey: ["logistics", "holders", "detail", holderId],
    queryFn: () => getHolder(holderId as number),
    enabled: open,
  });
  const holder: HolderDetail | undefined = query.data;

  const [articlesLimit, setArticlesLimit] = useState(ARTICLES_STEP);
  const [menuOpen, setMenuOpen] = useState(false);
  const { mounted: menuMounted, dataState: menuDataState, onAnimationEnd } = useClosingState(menuOpen, 200);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | undefined>(undefined);
  const [renaming, setRenaming] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [archiveError, setArchiveError] = useState<string | undefined>(undefined);
  const [archiving, setArchiving] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [articleId, setArticleId] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    setArticlesLimit(ARTICLES_STEP);
    setMenuOpen(false);
  }, [open, holderId]);

  const articleQuery = useQuery({
    queryKey: ["logistics", "articles", "detail", articleId],
    queryFn: () => getArticle(articleId as number),
    enabled: articleId !== null,
  });

  const notFound = query.error instanceof ApiError && query.error.status === 404;
  const isActive = holder?.status === "active";

  async function handleRename(): Promise<void> {
    if (!holder) return;
    if (!renameValue.trim()) {
      setRenameError("Ce champ est obligatoire.");
      return;
    }
    setRenaming(true);
    setRenameError(undefined);
    try {
      await renameHolder(holder.id, renameValue.trim());
      setRenameOpen(false);
      void query.refetch();
      onChanged("Lieu renommé.");
    } catch (error) {
      setRenameError(apiErrorMessage(error));
    } finally {
      setRenaming(false);
    }
  }

  async function handleArchive(): Promise<void> {
    if (!holder) return;
    setArchiving(true);
    setArchiveError(undefined);
    try {
      await archiveHolder(holder.id);
      setArchiveOpen(false);
      void query.refetch();
      onChanged("Détenteur archivé.");
    } catch (error) {
      setArchiveError(apiErrorMessage(error));
    } finally {
      setArchiving(false);
    }
  }

  const articles = holder?.articles ?? [];

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={holder?.name ?? "Détenteur"}
        subtitle={holder?.kind_display}
        size="md"
        loading={query.isLoading}
        footer={
          <div className="flex w-full items-center justify-end gap-2">
            <Button variant="secondary" size="md" onClick={onClose}>
              Fermer
            </Button>
            {canManage && holder && holder.stock_total > 0 ? (
              <Button variant="primary" size="md" onClick={() => setTransferOpen(true)}>
                Déplacer du matériel
              </Button>
            ) : null}
          </div>
        }
      >
        {query.isError ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            {notFound ? apiErrorMessage(query.error) : "Impossible de charger ce détail. Réessayez."}
          </p>
        ) : holder ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-2">
              <span className="flex flex-wrap gap-1">
                {holder.has_left_club ? <StatusBadge status="holder_left" /> : null}
                {holder.status === "archived" ? <StatusBadge status="archived" /> : null}
              </span>
              {canManage && isActive ? (
                <div className="relative">
                  <IconButton
                    aria-label="Plus d'actions"
                    onClick={() => setMenuOpen((v) => !v)}
                    icon={<IconMore aria-hidden="true" className="h-5 w-5" />}
                  />
                  {menuMounted ? (
                    <div
                      data-state={menuDataState}
                      onAnimationEnd={onAnimationEnd}
                      className="vesta-anim-menu absolute right-0 z-10 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated"
                    >
                      {holder.kind === "place" ? (
                        <button
                          type="button"
                          className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                          onClick={() => {
                            setMenuOpen(false);
                            setRenameValue(holder.label || holder.name);
                            setRenameError(undefined);
                            setRenameOpen(true);
                          }}
                        >
                          Renommer le lieu
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                        onClick={() => {
                          setMenuOpen(false);
                          setArchiveError(undefined);
                          setArchiveOpen(true);
                        }}
                      >
                        Archiver le détenteur
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>

            <section>
              <h3 className="mb-2 text-sm font-semibold text-text">Matériel détenu</h3>
              {articles.length === 0 ? (
                <p className="text-sm text-text-muted">Ce détenteur n'a aucun matériel.</p>
              ) : (
                <>
                  <ul className="divide-y divide-border">
                    {articles.slice(0, articlesLimit).map((row) => (
                      <li key={row.article_id}>
                        <button
                          type="button"
                          onClick={() => setArticleId(row.article_id)}
                          className="flex min-h-11 w-full items-center justify-between gap-2 py-2 text-left"
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm text-text">{row.name}</span>
                            <span className="block text-[13px] text-text-muted">{row.category_display}</span>
                          </span>
                          <span className="shrink-0 text-right">
                            <span className="block tabular-nums text-sm text-text">
                              {row.quantity} {row.unit}
                            </span>
                            {row.pending_decommission > 0 ? (
                              <span className="block text-sm text-status-warning-fg">
                                dont {row.pending_decommission} à déclasser
                              </span>
                            ) : null}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  {articles.length > articlesLimit ? (
                    <div className="mt-2 text-center">
                      <Button size="sm" variant="secondary" onClick={() => setArticlesLimit((n) => n + ARTICLES_STEP)}>
                        Voir plus
                      </Button>
                    </div>
                  ) : null}
                </>
              )}
            </section>

            <section>
              <h3 className="mb-2 text-sm font-semibold text-text">5 derniers mouvements chez ce détenteur</h3>
              {holder.recent_movements.length === 0 ? (
                <p className="text-sm text-text-muted">Aucun mouvement chez ce détenteur.</p>
              ) : (
                <>
                  <ul className="divide-y divide-border">
                    {holder.recent_movements.map((movement) => (
                      <li key={movement.id} className="flex items-center justify-between gap-2 py-2">
                        <span className="min-w-0">
                          <span className="block truncate text-sm text-text">
                            {movement.movement_type_display} · {movement.article.name}
                          </span>
                          <span className="block text-[13px] text-text-muted">
                            {formatDateFr(movement.movement_date)}
                          </span>
                        </span>
                        <span className="shrink-0 tabular-nums text-sm text-text">
                          {movement.signed_quantity > 0 ? "+" : ""}
                          {movement.signed_quantity}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-2 text-center">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => onShowAllMovements({ id: holder.id, name: holder.name })}
                    >
                      Voir plus
                    </Button>
                  </div>
                </>
              )}
            </section>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={renameOpen}
        onClose={() => setRenameOpen(false)}
        title="Renommer le lieu"
        size="sm"
        level={2}
        isDirty={Boolean(holder) && renameValue.trim() !== (holder?.label || holder?.name || "")}
        isSubmitting={renaming}
        confirmLabel="Enregistrer"
        confirmLoadingLabel="Enregistrement…"
        onConfirm={() => void handleRename()}
      >
        <TextField label="Nom du lieu" value={renameValue} onChange={setRenameValue} maxLength={60} error={renameError} />
      </Modal>

      <ConfirmDialog
        open={archiveOpen}
        title={`Archiver ${holder?.name ?? ""} ?`}
        description="Il ne sera plus proposé comme détenteur."
        confirmLabel="Archiver"
        loading={archiving}
        loadingLabel="Archivage…"
        error={archiveError}
        onConfirm={() => void handleArchive()}
        onCancel={() => setArchiveOpen(false)}
      />

      {holder ? (
        <TransferModal
          open={transferOpen}
          level={2}
          initialFrom={holder.id}
          initialFromName={holder.name}
          onClose={() => setTransferOpen(false)}
          onSaved={(message) => {
            setTransferOpen(false);
            void query.refetch();
            onChanged(message);
          }}
        />
      ) : null}

      <ArticleDetailModal
        article={articleId !== null ? (articleQuery.data ?? null) : null}
        level={2}
        canManage={false}
        canSeeExpenseDetail={canSeeExpenseDetail}
        onClose={() => setArticleId(null)}
        onEdit={() => undefined}
        onChanged={onChanged}
      />
    </>
  );
}
