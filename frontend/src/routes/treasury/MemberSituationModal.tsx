import { useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getMemberDetail,
  getMemberGrid,
  getPayments,
  type MemberDetail,
  type MemberGridResponse,
  type PaymentListItem,
} from "../../api/treasury";
import {
  Avatar,
  Button,
  EmptyState,
  IconChevronLeft,
  IconChevronRight,
  IconButton,
  Modal,
  Skeleton,
  StatusBadge,
  Tabs,
  type PlayerSearchResult,
} from "../../design-system";
import { GRID_STATE_TO_STATUS_KEY, cellAmountText } from "./gridCellVisuals";
import { formatAmount, formatDateFr } from "./money";
import { RecordPaymentModal } from "./RecordPaymentModal";

const MEMBER_DETAIL_QUERY_KEY = ["treasury", "member-detail"] as const;
const PAYMENTS_PAGE_SIZE = 20;

type TabKey = "unpaid" | "payments" | "free" | "grid";

const TABS: Array<{ value: TabKey; label: string }> = [
  { value: "unpaid", label: "Impayés" },
  { value: "payments", label: "Paiements" },
  { value: "free", label: "Cotisations libres" },
  { value: "grid", label: "Grille" },
];

function toSearchResult(member: MemberDetail): PlayerSearchResult {
  return {
    id: member.membership_id,
    firstName: member.first_name,
    lastName: member.last_name,
    number: member.jersey_number,
    photoUrl: member.photo,
  };
}

function SectionError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <EmptyState variant="error" message={message} actionLabel="Réessayer" onAction={onRetry} />;
}

function ListSkeleton() {
  return (
    <div role="status" aria-label="Chargement" className="space-y-2">
      {[0, 1, 2].map((index) => (
        <Skeleton key={index} variant="row" />
      ))}
    </div>
  );
}

function PaymentsList({
  membershipId,
  nature,
  onOpenPayment,
}: {
  membershipId: number;
  nature?: "free" | "mandatory";
  onOpenPayment?: (paymentId: number) => void;
}) {
  const query = useInfiniteQuery({
    queryKey: ["treasury", "payments", "member", membershipId, nature ?? "all"],
    queryFn: ({ pageParam }) => getPayments({ membershipId, nature, limit: PAYMENTS_PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
  });
  const items: PaymentListItem[] = query.data?.pages.flatMap((page) => page.results) ?? [];

  if (query.isLoading) return <ListSkeleton />;
  if (query.isError) {
    return <SectionError message="Impossible de charger les paiements." onRetry={() => void query.refetch()} />;
  }
  if (items.length === 0) return <EmptyState message="Aucun paiement enregistré pour ce joueur." />;

  return (
    <>
      <ul className="divide-y divide-border">
        {items.map((payment) => (
          <li key={payment.id}>
            <button
              type="button"
              onClick={() => onOpenPayment?.(payment.id)}
              disabled={!onOpenPayment}
              aria-label={`Détail du paiement de ${formatAmount(payment.amount, payment.currency)} du ${formatDateFr(payment.paid_on)}`}
              className="block w-full py-2 text-left disabled:cursor-default"
            >
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-sm font-medium text-text">{payment.contribution_type.name}</span>
              <span className="shrink-0 text-sm font-medium tabular-nums text-text">
                {formatAmount(payment.amount, payment.currency)}
              </span>
            </div>
            <div className="mt-1 flex items-center justify-between gap-2">
              <span className="truncate text-xs text-text-muted">
                {formatDateFr(payment.paid_on)} · {payment.method_label}
              </span>
              <StatusBadge status={payment.status} />
            </div>
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
  );
}

function GridTab({ membershipId, currency }: { membershipId: number; currency: string }) {
  const [year, setYear] = useState(() => new Date().getFullYear());
  const query = useQuery<MemberGridResponse>({
    queryKey: ["treasury", "member-grid", membershipId, year],
    queryFn: () => getMemberGrid(membershipId, year),
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-center gap-2">
        <IconButton
          aria-label="Année précédente"
          icon={<IconChevronLeft aria-hidden="true" className="h-4 w-4" />}
          onClick={() => setYear((value) => value - 1)}
        />
        <span className="min-w-12 text-center text-sm font-medium tabular-nums text-text">{year}</span>
        <IconButton
          aria-label="Année suivante"
          icon={<IconChevronRight aria-hidden="true" className="h-4 w-4" />}
          onClick={() => setYear((value) => value + 1)}
        />
      </div>
      {query.isLoading ? (
        <ListSkeleton />
      ) : query.isError ? (
        <SectionError message="Impossible de charger la grille." onRetry={() => void query.refetch()} />
      ) : !query.data || query.data.lines.length === 0 ? (
        <EmptyState message={`Aucune cotisation ne concerne ce joueur en ${year}.`} />
      ) : (
        query.data.lines.map((line) => (
          <div key={line.contribution_type.id}>
            <h4 className="mb-1 text-sm font-medium text-text">{line.contribution_type.name}</h4>
            <table className="w-full text-sm">
              <thead className="text-xs text-text-muted">
                <tr>
                  <th scope="col" className="py-1 text-left font-medium">
                    Mois
                  </th>
                  <th scope="col" className="py-1 text-right font-medium">
                    Montant
                  </th>
                  <th scope="col" className="py-1 pl-2 text-left font-medium">
                    État
                  </th>
                </tr>
              </thead>
              <tbody>
                {line.cells.map((cell, index) => (
                  <tr key={cell.period} className="border-t border-border">
                    <td className="py-1 text-text">{query.data.months[index]?.long_label ?? cell.period}</td>
                    <td className="py-1 text-right tabular-nums text-text">{cellAmountText(cell)}</td>
                    <td className="py-1 pl-2">
                      <StatusBadge status={GRID_STATE_TO_STATUS_KEY[cell.state]} />
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-border font-medium">
                  <td className="py-1 text-text">Total</td>
                  <td className="py-1 text-right tabular-nums text-text">{formatAmount(line.total, currency)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        ))
      )}
    </div>
  );
}

export interface MemberSituationModalProps {
  /** Adhésion ouverte ; `null` = modale fermée. */
  membershipId: number | null;
  onClose: () => void;
  /** Après un paiement enregistré depuis cette modale (rafraîchit la page). */
  onPaymentRecorded: () => void;
  /** Clic sur un paiement de l'onglet « Paiements » : ouvre son détail (CDC 3.3) par-dessus cette modale. */
  onOpenPayment?: (paymentId: number) => void;
}

/**
 * Modale « Situation financière » d'un membre (CDC 4.4.6 ; fiche
 * tresorerie-tableau-de-bord §4.3). Situation, impayés, prochaine échéance et
 * cotisations libres viennent de `GET treasury/members/<id>/` ; le bouton
 * « Enregistrer un paiement » n'apparaît que si l'API l'autorise
 * (`can_record_payment`).
 */
export function MemberSituationModal({ membershipId, onClose, onPaymentRecorded, onOpenPayment }: MemberSituationModalProps) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<TabKey>("unpaid");
  const [showRecordPayment, setShowRecordPayment] = useState(false);
  const open = membershipId !== null;

  const query = useQuery({
    queryKey: [...MEMBER_DETAIL_QUERY_KEY, membershipId],
    queryFn: () => getMemberDetail(membershipId as number),
    enabled: open,
  });
  const member = query.data;

  function handleClose(): void {
    setShowRecordPayment(false);
    setTab("unpaid");
    onClose();
  }

  const canRecord = Boolean(member?.can_record_payment);

  return (
    <>
      <Modal
        open={open}
        onClose={handleClose}
        title="Situation financière"
        subtitle={member?.name}
        size="lg"
        loading={query.isLoading}
        cancelLabel="Fermer"
        confirmLabel={canRecord ? "Enregistrer un paiement" : undefined}
        onConfirm={canRecord ? () => setShowRecordPayment(true) : undefined}
      >
        {query.isError ? (
          <SectionError message="Impossible de charger la situation financière." onRetry={() => void query.refetch()} />
        ) : member ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <Avatar name={member.name} photoUrl={member.photo} size={40} />
              <div className="min-w-0">
                <p className="truncate text-base font-medium text-text">{member.name}</p>
                {member.jersey_number != null ? (
                  <p className="text-xs text-text-muted">n° {member.jersey_number}</p>
                ) : null}
              </div>
              <div className="ml-auto flex flex-wrap justify-end gap-1">
                {member.statuses.map((entry) => (
                  <StatusBadge
                    key={entry.key}
                    status={entry.key}
                    detail={entry.key === "in_debt" ? formatAmount(member.amount_due, member.currency) : undefined}
                  />
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2 rounded-md bg-surface-muted p-3 text-sm sm:grid-cols-3">
              <div>
                <p className="text-text-muted">Solde</p>
                <p className={["tabular-nums", Number(member.balance) < 0 ? "text-status-danger-fg" : "text-text"].join(" ")}>
                  {formatAmount(member.balance, member.currency)}
                </p>
              </div>
              <div>
                <p className="text-text-muted">Montant dû échu</p>
                <p className="tabular-nums text-text">{formatAmount(member.amount_due, member.currency)}</p>
              </div>
              <div>
                <p className="text-text-muted">Prochaine échéance</p>
                <p className="text-text">
                  {member.next_due
                    ? `${member.next_due.period_label} · ${formatAmount(member.next_due.amount, member.currency)} (${formatDateFr(member.next_due.due_date)})`
                    : "Aucune échéance à venir"}
                </p>
              </div>
            </div>
            {member.reason ? <p className="text-sm text-text-muted">{member.reason}</p> : null}

            <Tabs items={TABS} value={tab} onChange={setTab} label="Détail de la situation" />

            <div role="tabpanel">
              {tab === "unpaid" ? (
                member.unpaid_months.length === 0 ? (
                  <EmptyState message="Aucun mois impayé." />
                ) : (
                  <ul className="divide-y divide-border">
                    {member.unpaid_months.map((item) => (
                      <li
                        key={`${item.contribution_type?.id ?? "x"}-${item.period}`}
                        className="flex items-baseline justify-between gap-2 py-2"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium text-text">
                            {item.period_label}
                            {item.contribution_type ? ` · ${item.contribution_type.name}` : ""}
                          </span>
                          <span className="block text-xs text-text-muted">
                            Échu le {formatDateFr(item.due_date)} · dû {formatAmount(item.amount_due, member.currency)}
                          </span>
                        </span>
                        <span className="shrink-0 text-sm font-medium tabular-nums text-status-danger-fg">
                          {formatAmount(item.remaining, member.currency)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )
              ) : null}

              {tab === "payments" ? <PaymentsList membershipId={member.membership_id} onOpenPayment={onOpenPayment} /> : null}

              {tab === "free" ? (
                <div className="space-y-3">
                  {member.free_contributions.length === 0 ? (
                    <EmptyState message="Aucune cotisation libre pour ce joueur." />
                  ) : (
                    <ul className="divide-y divide-border">
                      {member.free_contributions.map((item, index) => (
                        <li key={item.contribution_type?.id ?? index} className="flex items-baseline justify-between gap-2 py-2">
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium text-text">
                              {item.contribution_type?.name ?? "Cotisation libre"}
                            </span>
                            <span className="block text-xs text-text-muted">
                              {item.payments_count} paiement{item.payments_count > 1 ? "s" : ""}
                              {item.last_paid_on ? ` · dernier le ${formatDateFr(item.last_paid_on)}` : ""}
                            </span>
                          </span>
                          <span className="shrink-0 text-sm font-medium tabular-nums text-text">
                            {formatAmount(item.total, member.currency)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="text-xs text-text-muted">Les cotisations libres ne comptent pas dans le solde.</p>
                </div>
              ) : null}

              {tab === "grid" ? <GridTab membershipId={member.membership_id} currency={member.currency} /> : null}
            </div>
          </div>
        ) : null}
      </Modal>

      {member ? (
        <RecordPaymentModal
          open={showRecordPayment}
          level={2}
          currency={member.currency}
          initialPlayer={toSearchResult(member)}
          initialContributionTypeId={member.monthly_type?.id}
          onClose={() => setShowRecordPayment(false)}
          onRecorded={() => {
            setShowRecordPayment(false);
            void queryClient.invalidateQueries({ queryKey: MEMBER_DETAIL_QUERY_KEY });
            void queryClient.invalidateQueries({ queryKey: ["treasury", "member-grid"] });
            onPaymentRecorded();
          }}
        />
      ) : null}
    </>
  );
}
