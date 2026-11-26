import { useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import {
  PROVENANCE_MOVEMENT_TYPES,
  archiveArticle,
  getArticle,
  listMovements,
  reactivateArticle,
  toArticleSearchResult,
  type Article,
  type Provenance,
} from "../../api/logistics";
import { Button, ConfirmDialog, IconButton, IconMore, Loader, Modal, StatusBadge } from "../../design-system";
import { useClosingState } from "../../hooks/useClosingState";
import { DecommissionDetailModal } from "./DecommissionDetailModal";
import { DecommissionFlagModal } from "./DecommissionFlagModal";
import { formatDateFr } from "./format";
import { UNLOCATED_LABEL } from "./HolderSearch";
import { MovementDetailModal } from "./MovementDetailModal";
import { RecordMovementModal } from "./RecordMovementModal";
import { TransferModal } from "./TransferModal";

export interface ArticleDetailModalProps {
  article: Article | null;
  canManage: boolean;
  /** 2 quand ouverte depuis la modale d'un détenteur. */
  level?: 1 | 2;
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

/** Libellé d'origine d'une provenance (spec B4 §2.2) ; libellés de l'API. */
export function provenanceOriginLabel(provenance: Provenance): string {
  if (provenance.origin_kind === "donation") {
    return provenance.donor ? `Don de ${provenance.donor.name}` : "Don";
  }
  if (provenance.origin_kind === "club_funds") return "Frais de l'équipe";
  if (provenance.origin_kind === "unknown") return "Origine inconnue";
  return provenance.origin_kind_display;
}

/** 2e ligne d'une provenance : date d'acquisition et détenteur. */
export function provenanceDetailLabel(provenance: Provenance): string {
  let dateText: string;
  if (provenance.acquisition_date_unknown) {
    dateText = provenance.acquisition_date_note
      ? `Date inconnue — ${provenance.acquisition_date_note}`
      : "Date inconnue";
  } else {
    dateText = `Acquis le ${formatDateFr(provenance.acquisition_date ?? provenance.movement_date)}`;
  }
  return `${dateText} · chez ${provenance.holder?.name ?? UNLOCATED_LABEL}`;
}

/** « Article » (détail) — fiche `logistique.md` §4.1, spec B4 §2.2. */
export function ArticleDetailModal({
  article: listedArticle,
  canManage,
  level = 1,
  onClose,
  onEdit,
  onChanged,
  onOpenMatch,
  onOpenExpense,
  canSeeExpenseDetail = false,
}: ArticleDetailModalProps) {
  const open = listedArticle !== null;
  const [menuOpen, setMenuOpen] = useState(false);
  const { mounted: menuMounted, dataState: menuDataState, onAnimationEnd: onMenuAnimationEnd } =
    useClosingState(menuOpen, 200);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [archiveError, setArchiveError] = useState<string | undefined>(undefined);
  const [archiving, setArchiving] = useState(false);
  const [recordOpen, setRecordOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [flagOpen, setFlagOpen] = useState(false);
  const [selectedMovementId, setSelectedMovementId] = useState<number | null>(null);
  const [moreProvenances, setMoreProvenances] = useState(false);
  const [decommissionId, setDecommissionId] = useState<number | null>(null);

  // Le détail porte les provenances (5 au plus) et une répartition à jour.
  const detailQuery = useQuery({
    queryKey: ["logistics", "articles", "detail", listedArticle?.id],
    queryFn: () => getArticle(listedArticle!.id),
    enabled: open,
  });
  const article = detailQuery.data ?? listedArticle;

  const movementsQuery = useInfiniteQuery({
    queryKey: ["logistics", "movements", "article", listedArticle?.id],
    queryFn: ({ pageParam }) => listMovements({ article: listedArticle!.id, limit: PAGE_STEP, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.next_offset ?? undefined,
    enabled: open,
  });

  const provenancesQuery = useInfiniteQuery({
    queryKey: ["logistics", "movements", "article-provenances", listedArticle?.id],
    queryFn: ({ pageParam }) =>
      listMovements({ article: listedArticle!.id, types: PROVENANCE_MOVEMENT_TYPES, limit: PAGE_STEP, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.next_offset ?? undefined,
    enabled: open && moreProvenances,
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

  function afterWrite(message: string): void {
    void detailQuery.refetch();
    void movementsQuery.refetch();
    if (moreProvenances) void provenancesQuery.refetch();
    onChanged(message);
  }

  if (!article) return null;

  const movements = (movementsQuery.data?.pages ?? []).flatMap((page) => page.results);
  const provenances: Provenance[] = moreProvenances
    ? (provenancesQuery.data?.pages ?? [])
        .flatMap((page) => page.results)
        .map((movement) => movement.provenance)
        .filter((p): p is Provenance => p !== null)
    : (article.provenances ?? []);
  const searchResult = toArticleSearchResult(article);
  const isActive = article.status === "active";

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={article.name}
        subtitle={`${article.category_display} · ${article.unit}`}
        size="lg"
        level={level}
        footer={
          <div className="flex w-full items-center justify-end gap-2">
            <Button variant="secondary" size="md" onClick={onClose}>
              Fermer
            </Button>
            {canManage && isActive ? (
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
                <IconButton
                  aria-label="Plus d'actions"
                  onClick={() => setMenuOpen((v) => !v)}
                  icon={<IconMore aria-hidden="true" className="h-5 w-5" />}
                />
                {menuMounted ? (
                  <div
                    data-state={menuDataState}
                    onAnimationEnd={onMenuAnimationEnd}
                    className="vesta-anim-menu absolute right-0 z-10 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated"
                  >
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
                    {isActive && article.in_stock > 0 ? (
                      <button
                        type="button"
                        className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                        onClick={() => {
                          setMenuOpen(false);
                          setFlagOpen(true);
                        }}
                      >
                        Signaler à déclasser
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                      onClick={() => {
                        setMenuOpen(false);
                        setArchiveError(undefined);
                        setConfirmArchive(true);
                      }}
                    >
                      {isActive ? "Archiver l'article" : "Réactiver l'article"}
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
            <div className="rounded-md border border-border p-2">
              <p className="text-xs text-text-muted">En stock</p>
              <p className="tabular-nums text-base font-semibold text-text">
                {article.in_stock} {article.unit}
              </p>
            </div>
            <div className="rounded-md border border-border p-2">
              <p className="text-xs text-text-muted">À déclasser</p>
              <p className="tabular-nums text-base font-semibold text-text">{article.pending_decommission}</p>
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

          <section>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-text">Répartition</h3>
              {canManage && isActive && article.stock_by_holder.length > 0 ? (
                <Button size="sm" variant="secondary" onClick={() => setTransferOpen(true)}>
                  Déplacer
                </Button>
              ) : null}
            </div>
            {article.stock_by_holder.length === 0 ? (
              <p className="text-sm text-text-muted">Aucune pièce en stock.</p>
            ) : (
              <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                {article.stock_by_holder.map((row) => (
                  <li key={row.holder_id ?? "none"} className={row.holder_id === null ? "text-text-muted" : "text-text"}>
                    {row.holder_name} · <span className="tabular-nums">{row.quantity}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold text-text">Provenances</h3>
            {detailQuery.isLoading || (moreProvenances && provenancesQuery.isLoading) ? (
              <Loader loading variant="list" count={2} />
            ) : provenances.length === 0 ? (
              <p className="text-sm text-text-muted">Aucune provenance enregistrée.</p>
            ) : (
              <>
                <ul className="divide-y divide-border">
                  {provenances.map((provenance) => (
                    <li key={provenance.movement_id}>
                      <button
                        type="button"
                        onClick={() => setSelectedMovementId(provenance.movement_id)}
                        className="w-full py-2 text-left"
                      >
                        <span className="block text-sm text-text">
                          <span className="tabular-nums">
                            {provenance.quantity} {article.unit}
                          </span>{" "}
                          · {provenanceOriginLabel(provenance)}
                        </span>
                        <span className="block text-[13px] text-text-muted">{provenanceDetailLabel(provenance)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
                {!moreProvenances && provenances.length >= 5 ? (
                  <div className="mt-2 text-center">
                    <Button size="sm" variant="secondary" onClick={() => setMoreProvenances(true)}>
                      Voir plus
                    </Button>
                  </div>
                ) : moreProvenances && provenancesQuery.hasNextPage ? (
                  <div className="mt-2 text-center">
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={provenancesQuery.isFetchingNextPage}
                      onClick={() => void provenancesQuery.fetchNextPage()}
                    >
                      Voir plus
                    </Button>
                  </div>
                ) : null}
              </>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold text-text">Derniers mouvements</h3>
            {movementsQuery.isLoading ? (
              <Loader loading variant="list" count={3} />
            ) : movementsQuery.isError ? (
              <p role="alert" className="text-sm text-status-danger-fg">
                Impossible de charger les mouvements. Réessayez.
              </p>
            ) : movements.length === 0 ? (
              <p className="text-sm text-text-muted">Aucun mouvement pour cet article.</p>
            ) : (
              <>
                <ul className="divide-y divide-border">
                  {movements.map((movement) => (
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
                {movementsQuery.hasNextPage ? (
                  <div className="mt-2 text-center">
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={movementsQuery.isFetchingNextPage}
                      onClick={() => void movementsQuery.fetchNextPage()}
                    >
                      Voir plus
                    </Button>
                  </div>
                ) : null}
              </>
            )}
          </section>

          <p className="text-xs text-text-muted">
            Ajouté par {article.created_by.name || "Système Vesta"} le {formatDateFr(article.created_at.slice(0, 10))}.
          </p>
        </div>
      </Modal>

      <RecordMovementModal
        open={recordOpen}
        level={2}
        lockedArticle={article}
        onClose={() => setRecordOpen(false)}
        onSaved={(message) => {
          setRecordOpen(false);
          afterWrite(message);
        }}
      />

      <TransferModal
        open={transferOpen}
        level={2}
        lockedArticle={searchResult}
        onClose={() => setTransferOpen(false)}
        onSaved={(message) => {
          setTransferOpen(false);
          afterWrite(message);
        }}
      />

      <DecommissionFlagModal
        open={flagOpen}
        level={2}
        lockedArticle={searchResult}
        onClose={() => setFlagOpen(false)}
        onSaved={(message) => {
          setFlagOpen(false);
          afterWrite(message);
        }}
      />

      <MovementDetailModal
        movementId={selectedMovementId}
        level={2}
        onClose={() => setSelectedMovementId(null)}
        onOpenMatch={onOpenMatch}
        onOpenExpense={onOpenExpense}
        canSeeExpenseDetail={canSeeExpenseDetail}
        onOpenDecommission={(id) => {
          setSelectedMovementId(null);
          setDecommissionId(id);
        }}
      />

      <DecommissionDetailModal
        decommissionId={decommissionId}
        level={2}
        canManage={canManage}
        onClose={() => setDecommissionId(null)}
        onChanged={afterWrite}
      />

      <ConfirmDialog
        open={confirmArchive}
        title={isActive ? `Archiver ${article.name} ?` : `Réactiver ${article.name} ?`}
        description={
          isActive ? (
            <span>
              L'article n'apparaîtra plus dans les choix de mouvement ni dans les prochains inventaires. Son historique
              est conservé.
            </span>
          ) : undefined
        }
        error={archiveError}
        confirmLabel={isActive ? "Archiver" : "Réactiver"}
        danger={isActive}
        loading={archiving}
        onConfirm={() => void handleArchiveToggle()}
        onCancel={() => setConfirmArchive(false)}
      />
    </>
  );
}
