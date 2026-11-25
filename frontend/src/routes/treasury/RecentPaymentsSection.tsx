import { useInfiniteQuery } from "@tanstack/react-query";
import { getPayments, type PaymentListItem } from "../../api/treasury";
import { Avatar, Button, EmptyState, Skeleton, StatusBadge } from "../../design-system";
import { formatAmount, formatDateFr } from "./money";

export const RECENT_PAYMENTS_QUERY_KEY = ["treasury", "payments", "recent"] as const;
const PAGE_SIZE = 20;

export interface RecentPaymentsSectionProps {
  canRecordPayments: boolean;
  onOpen: (payment: PaymentListItem) => void;
  onRecordPayment: () => void;
}

/**
 * « Derniers paiements » (CDC 4.4.6, 3.3) : 20 derniers puis « Voir plus » ;
 * un clic ouvre la modale de détail. Statut et libellés viennent de l'API.
 */
export function RecentPaymentsSection({ canRecordPayments, onOpen, onRecordPayment }: RecentPaymentsSectionProps) {
  const query = useInfiniteQuery({
    queryKey: RECENT_PAYMENTS_QUERY_KEY,
    queryFn: ({ pageParam }) => getPayments({ limit: PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
  });
  const items = query.data?.pages.flatMap((page) => page.results) ?? [];

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4" aria-label="Derniers paiements">
      <h2 className="mb-3 text-base font-semibold text-text">Derniers paiements</h2>
      {query.isLoading ? (
        <div role="status" aria-label="Chargement des paiements" className="space-y-3">
          {[0, 1, 2, 3, 4].map((index) => (
            <Skeleton key={index} variant="row" />
          ))}
        </div>
      ) : query.isError ? (
        <EmptyState
          variant="error"
          message="Impossible de charger les paiements."
          actionLabel="Réessayer"
          onAction={() => void query.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          message="Aucun paiement enregistré pour l'instant."
          actionLabel={canRecordPayments ? "Enregistrer un paiement" : undefined}
          onAction={canRecordPayments ? onRecordPayment : undefined}
        />
      ) : (
        <>
          <ul className="divide-y divide-border">
            {items.map((payment) => (
              <li key={payment.id}>
                <button
                  type="button"
                  onClick={() => onOpen(payment)}
                  className="flex w-full items-center gap-3 py-3 text-left"
                  aria-label={`Paiement de ${payment.player.name}, ${formatAmount(payment.amount, payment.currency)}`}
                >
                  <Avatar name={payment.player.name} photoUrl={payment.player.photo} size={32} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm font-medium text-text">{payment.player.name}</span>
                      <span className="shrink-0 text-sm font-medium tabular-nums text-text">
                        {formatAmount(payment.amount, payment.currency)}
                      </span>
                    </span>
                    <span className="mt-1 flex items-center justify-between gap-2">
                      <span className="truncate text-xs text-text-muted">
                        {payment.contribution_type.name} · {formatDateFr(payment.paid_on)} · {payment.method_label}
                      </span>
                      <StatusBadge status={payment.status} />
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {query.hasNextPage ? (
            <div className="mt-3 flex justify-center">
              <Button
                size="sm"
                variant="secondary"
                loading={query.isFetchingNextPage}
                loadingLabel="Chargement…"
                onClick={() => void query.fetchNextPage()}
              >
                Voir plus
              </Button>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
