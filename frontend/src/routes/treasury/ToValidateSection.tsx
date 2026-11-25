import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getPayments, type PaymentListItem } from "../../api/treasury";
import { Avatar, Button, EmptyState, Skeleton, StatusBadge } from "../../design-system";
import { formatAmount, formatDateFr } from "./money";

export const TO_VALIDATE_QUERY_KEY = ["treasury", "payments", "to-validate"] as const;
export const REVERSALS_PENDING_QUERY_KEY = ["treasury", "payments", "reversals-pending"] as const;
const PAGE_STEP = 20;

export interface ToValidateSectionProps {
  /** Valider les déclarations « J'ai payé » (Trésorier, adjoint). */
  canValidateDeclarations: boolean;
  /** Valider les annulations (Président). */
  canDecideReversals: boolean;
  onOpen: (payment: PaymentListItem) => void;
}

interface Row {
  payment: PaymentListItem;
  kind: "declaration" | "reversal";
}

/**
 * « À valider » (fiche §3.2) : déclarations « J'ai payé » et annulations
 * demandées. Section masquée si vide ; les listes sont filtrées par l'API.
 */
export function ToValidateSection({ canValidateDeclarations, canDecideReversals, onOpen }: ToValidateSectionProps) {
  const [limit, setLimit] = useState(PAGE_STEP);
  const declarations = useQuery({
    queryKey: [...TO_VALIDATE_QUERY_KEY, limit],
    queryFn: () => getPayments({ status: "to_validate", limit }),
    enabled: canValidateDeclarations,
    placeholderData: keepPreviousData,
  });
  const reversals = useQuery({
    queryKey: [...REVERSALS_PENDING_QUERY_KEY, limit],
    queryFn: () => getPayments({ reversal: "pending_approval", limit }),
    enabled: canDecideReversals,
    placeholderData: keepPreviousData,
  });

  if (!canValidateDeclarations && !canDecideReversals) return null;
  if (declarations.isLoading || reversals.isLoading) {
    return (
      <section className="rounded-lg bg-surface p-3 shadow-card" aria-label="Chargement des éléments à valider">
        <Skeleton variant="row" />
      </section>
    );
  }
  if (declarations.isError || reversals.isError) {
    return (
      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <EmptyState
          variant="error"
          message="Impossible de charger les éléments à valider."
          actionLabel="Réessayer"
          onAction={() => {
            void declarations.refetch();
            void reversals.refetch();
          }}
        />
      </section>
    );
  }

  const rows: Row[] = [
    ...(canValidateDeclarations
      ? (declarations.data?.results ?? [])
          .filter((payment) => payment.source === "player_declaration")
          .map((payment): Row => ({ payment, kind: "declaration" }))
      : []),
    ...(canDecideReversals
      ? (reversals.data?.results ?? []).map((payment): Row => ({ payment, kind: "reversal" }))
      : []),
  ];
  if (rows.length === 0) return null;
  const hasMore =
    (canValidateDeclarations && declarations.data !== undefined && declarations.data.results.length < declarations.data.count) ||
    (canDecideReversals && reversals.data !== undefined && reversals.data.results.length < reversals.data.count);

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4" aria-label="À valider">
      <h2 className="mb-3 text-base font-semibold text-text">À valider</h2>
      <ul className="divide-y divide-border">
        {rows.map(({ payment, kind }) => (
          <li key={`${kind}-${payment.id}`}>
            <button type="button" onClick={() => onOpen(payment)} className="flex w-full items-center gap-3 py-3 text-left">
              <Avatar name={payment.player.name} photoUrl={payment.player.photo} size={32} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-text">{payment.player.name}</span>
                <span className="block truncate text-xs text-text-muted">
                  {kind === "declaration"
                    ? `Déclaration J'ai payé · ${formatAmount(payment.amount, payment.currency)} · ${formatDateFr(payment.paid_on)}`
                    : `Annulation demandée · ${formatAmount(payment.amount, payment.currency)}`}
                </span>
              </span>
              <StatusBadge status="to_validate" />
            </button>
          </li>
        ))}
      </ul>
      {hasMore ? (
        <div className="pt-2 text-center">
          <Button
            variant="ghost"
            size="sm"
            loading={declarations.isFetching || reversals.isFetching}
            loadingLabel="Chargement…"
            onClick={() => setLimit((value) => value + PAGE_STEP)}
          >
            Voir plus
          </Button>
        </div>
      ) : null}
    </section>
  );
}
