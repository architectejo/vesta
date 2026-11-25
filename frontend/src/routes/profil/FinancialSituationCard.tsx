import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getContributeInfo, getMyBalance, getMyPayments, getPaymentDeclarations } from "../../api/treasury";
import { Button, EmptyState, Skeleton, StatusBadge } from "../../design-system";
import { useDeepLink } from "../../hooks/useDeepLink";
import { DeclarePaymentModal } from "../treasury/DeclarePaymentModal";
import { formatAmount, formatDateFr } from "../treasury/money";
import { MyPaymentDetailModal, type MyPaymentTarget } from "./MyPaymentDetailModal";
import { MyContributionsSection } from "./MyContributionsSection";
import { ReceiptDownloadButton } from "./ReceiptDownloadButton";

/** CDC 4.1 / 3.3 : les 20 derniers paiements, puis « Voir plus » par tranche de 20. */
const PAGE_SIZE = 20;
const PENDING_LIMIT = 50;
const MY_PAYMENTS_KEY = ["treasury", "my-payments"] as const;
const MY_DECLARATIONS_KEY = ["treasury", "payment-declarations", "mine"] as const;

interface PaymentRow {
  key: string;
  target: MyPaymentTarget;
  paid_on: string;
  contribution_type: { name: string };
  amount: string;
  currency: string;
  status: "to_validate" | "validated" | "refused" | "cancelled";
  receipt_available: boolean;
  id: number;
}

/**
 * Carte « Situation financière » de « Mon profil » (comptes-mon-profil.md §3
 * point 2 ; CDC 4.1, 4.4.4, 4.6). Solde, statut et raison viennent de l'API
 * (`/treasury/my-balance/`) ; lien de paiement et devise de
 * `/treasury/contribute/`. Aucun calcul ici.
 *
 * « Derniers paiements » fusionne deux sources de l'API : les paiements
 * validés/annulés (`/treasury/my-payments/`, paginés) et les déclarations « À
 * valider »/refusées (`/treasury/payment-declarations/?mine=1`). Tri par date
 * décroissante. « Mes cotisations » est dans `MyContributionsSection`.
 */
export function FinancialSituationCard() {
  const queryClient = useQueryClient();
  const [declareOpen, setDeclareOpen] = useState(false);
  const [detail, setDetail] = useState<MyPaymentTarget | null>(null);
  // Liens depuis une notification : paiement validé (`?paiement=<id>`) ou
  // déclaration « J'ai payé » refusée (`?declaration=<id>`).
  useDeepLink("paiement", (id) => setDetail({ id, kind: "payment" }));
  useDeepLink("declaration", (id) => setDetail({ id, kind: "declaration" }));

  const balanceQuery = useQuery({ queryKey: ["treasury", "my-balance"], queryFn: getMyBalance });
  const contributeQuery = useQuery({ queryKey: ["treasury", "contribute-info"], queryFn: getContributeInfo });
  const paymentsQuery = useInfiniteQuery({
    queryKey: MY_PAYMENTS_KEY,
    queryFn: ({ pageParam }) =>
      getMyPayments({ status: ["validated", "cancelled"], limit: PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
  });
  const pendingQuery = useQuery({
    queryKey: MY_DECLARATIONS_KEY,
    queryFn: () => getPaymentDeclarations({ mine: true, status: "to_validate,refused", limit: PENDING_LIMIT }),
  });
  const payments: PaymentRow[] = [
    ...(pendingQuery.data?.results ?? []).map((item) => ({
      key: `declaration-${item.id}`,
      target: { id: item.id, kind: "declaration" as const },
      id: item.id,
      paid_on: item.paid_on,
      contribution_type: item.contribution_type,
      amount: item.amount,
      currency: item.currency,
      status: item.status,
      receipt_available: false,
    })),
    ...(paymentsQuery.data?.pages.flatMap((page) => page.results) ?? []).map((item) => ({
      key: `payment-${item.id}`,
      target: { id: item.id, kind: "payment" as const },
      id: item.id,
      paid_on: item.paid_on,
      contribution_type: item.contribution_type,
      amount: item.amount,
      currency: item.currency,
      status: item.status,
      receipt_available: item.receipt_available,
    })),
  ].sort((a, b) => (a.paid_on === b.paid_on ? b.id - a.id : a.paid_on < b.paid_on ? 1 : -1));
  const isLoadingPayments = paymentsQuery.isLoading || pendingQuery.isLoading;
  const isPaymentsError = paymentsQuery.isError || pendingQuery.isError;
  const balance = balanceQuery.data;
  const contribute = contributeQuery.data;
  const paymentLink = contribute?.payment_link_configured ? contribute.payment_link_url : null;

  function refreshAfterDeclaration(): void {
    void queryClient.invalidateQueries({ queryKey: MY_PAYMENTS_KEY });
    void queryClient.invalidateQueries({ queryKey: MY_DECLARATIONS_KEY });
    void queryClient.invalidateQueries({ queryKey: ["treasury", "my-balance"] });
  }

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4" aria-label="Situation financière">
      <h2 className="text-base font-semibold text-text">Situation financière</h2>

      {balanceQuery.isLoading ? (
        <div className="mt-2" role="status" aria-label="Chargement de la situation financière">
          <Skeleton variant="kpi" />
        </div>
      ) : balanceQuery.isError || !balance ? (
        <EmptyState
          variant="error"
          message="Impossible de charger votre situation financière."
          actionLabel="Réessayer"
          onAction={() => void balanceQuery.refetch()}
        />
      ) : (
        <div className="mt-2 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xl font-semibold tabular-nums text-text">
              Solde : {formatAmount(balance.balance, balance.currency)}
            </p>
            <StatusBadge
              status={balance.is_in_good_standing ? "in_good_standing" : "in_debt"}
              detail={balance.is_in_good_standing ? undefined : formatAmount(balance.amount_due, balance.currency)}
            />
          </div>
          <p className="text-sm text-text-muted">{balance.reason}</p>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {paymentLink ? (
              <Button
                variant="primary"
                size="sm"
                onClick={() => window.open(paymentLink, "_blank", "noopener,noreferrer")}
              >
                Contribuer
              </Button>
            ) : null}
            <Button variant="secondary" size="sm" onClick={() => setDeclareOpen(true)}>
              J'ai payé
            </Button>
          </div>
          {contributeQuery.isSuccess && !paymentLink ? (
            <p className="text-xs text-text-muted">
              Le club n'a pas encore configuré de lien de paiement. Réglez auprès du trésorier.
            </p>
          ) : null}
        </div>
      )}

      <h3 className="mt-4 text-sm font-semibold text-text">Derniers paiements</h3>
      {isLoadingPayments ? (
        <div role="status" aria-label="Chargement des paiements" className="mt-2 space-y-3">
          {[0, 1, 2].map((index) => (
            <Skeleton key={index} variant="row" />
          ))}
        </div>
      ) : isPaymentsError ? (
        <EmptyState
          variant="error"
          message="Impossible de charger vos paiements."
          actionLabel="Réessayer"
          onAction={() => {
            void paymentsQuery.refetch();
            void pendingQuery.refetch();
          }}
        />
      ) : payments.length === 0 ? (
        <EmptyState message="Aucun paiement enregistré pour l'instant." />
      ) : (
        <>
          <ul className="divide-y divide-border">
            {payments.map((payment) => (
              <li key={payment.key} className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setDetail(payment.target)}
                  className="flex min-w-0 flex-1 items-center gap-2 py-2 text-left"
                  aria-label={`Paiement du ${formatDateFr(payment.paid_on)}, ${formatAmount(payment.amount, payment.currency)}`}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-text">{payment.contribution_type.name}</span>
                    <span className="block text-xs text-text-muted">{formatDateFr(payment.paid_on)}</span>
                  </span>
                  <span className="text-sm tabular-nums text-text">{formatAmount(payment.amount, payment.currency)}</span>
                  <StatusBadge status={payment.status} />
                </button>
                {payment.receipt_available ? <ReceiptDownloadButton paymentId={payment.id} /> : null}
              </li>
            ))}
          </ul>
          {paymentsQuery.hasNextPage ? (
            <div className="pt-2 text-center">
              <Button
                variant="ghost"
                size="sm"
                loading={paymentsQuery.isFetchingNextPage}
                loadingLabel="Chargement…"
                onClick={() => void paymentsQuery.fetchNextPage()}
              >
                Voir plus
              </Button>
            </div>
          ) : null}
        </>
      )}

      <DeclarePaymentModal open={declareOpen} onClose={() => setDeclareOpen(false)} onDeclared={refreshAfterDeclaration} />
      <MyContributionsSection />
      <MyPaymentDetailModal target={detail} onClose={() => setDetail(null)} />
    </section>
  );
}
