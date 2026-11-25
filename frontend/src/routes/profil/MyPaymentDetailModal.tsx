import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { getMyPayment, getPaymentDeclaration } from "../../api/treasury";
import { Banner, Button, Modal, StatusBadge } from "../../design-system";
import { formatAmount, formatDateFr, formatMonthYear } from "../treasury/money";
import { ReceiptDownloadButton } from "./ReceiptDownloadButton";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="shrink-0 text-text-muted">{label}</span>
      <span className="min-w-0 break-words text-right text-text">{children}</span>
    </div>
  );
}

/** « payment » : paiement validé/annulé (my-payments) ; « declaration » : « À valider »/refusé. */
export interface MyPaymentTarget {
  id: number;
  kind: "payment" | "declaration";
}

export interface MyPaymentDetailModalProps {
  target: MyPaymentTarget | null;
  onClose: () => void;
}

interface DetailView {
  id: number;
  paid_on: string;
  contribution_type: { name: string };
  amount: string;
  currency: string;
  method_label: string;
  reference: string;
  status: "to_validate" | "validated" | "refused" | "cancelled";
  receipt_available: boolean;
  receipt_number: number | null;
  rejection_reason: string;
  allocations: Array<{ period: string; amount: string }>;
}

async function fetchDetail(target: MyPaymentTarget): Promise<DetailView> {
  if (target.kind === "payment") {
    const payment = await getMyPayment(target.id);
    return { ...payment, rejection_reason: "" };
  }
  return getPaymentDeclaration(target.id);
}

/**
 * « Détail du paiement » côté joueur (comptes-mon-profil.md §3.2, §4.4).
 * Paiements validés/annulés : `/treasury/my-payments/<id>/` ; déclarations en
 * attente ou refusées : `/treasury/payment-declarations/<id>/`. Statut, reçu et
 * répartition par mois viennent de l'API.
 */
export function MyPaymentDetailModal({ target, onClose }: MyPaymentDetailModalProps) {
  const open = target !== null;
  const query = useQuery({
    queryKey: ["treasury", "my-payment-detail", target?.kind, target?.id],
    queryFn: () => fetchDetail(target as MyPaymentTarget),
    enabled: open,
  });
  const payment = query.data;

  const footer = (
    <div className="flex w-full flex-wrap items-center justify-end gap-2">
      <Button variant="secondary" size="md" onClick={onClose}>
        Fermer
      </Button>
      {payment?.receipt_available ? <ReceiptDownloadButton paymentId={payment.id} variant="text" /> : null}
    </div>
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Détail du paiement"
      size="md"
      loading={query.isLoading}
      footer={footer}
    >
      {query.isError ? (
        <p role="alert" className="text-sm text-status-danger-fg">
          Impossible de charger ce paiement. Réessayez.
        </p>
      ) : payment ? (
        <div className="space-y-4">
          <div className="space-y-2 rounded-md bg-surface-muted p-3 text-sm">
            <Row label="Date">{formatDateFr(payment.paid_on)}</Row>
            <Row label="Type">{payment.contribution_type.name}</Row>
            <Row label="Montant">
              <span className="tabular-nums">{formatAmount(payment.amount, payment.currency)}</span>
            </Row>
            <Row label="Mode">{payment.method_label}</Row>
            <Row label="Référence">{payment.reference || "—"}</Row>
            <Row label="Statut">
              <StatusBadge status={payment.status} />
            </Row>
            {payment.receipt_available ? <Row label="Reçu n°">{payment.receipt_number}</Row> : null}
          </div>

          {payment.status === "to_validate" ? (
            <Banner variant="info">En attente de validation par le trésorier.</Banner>
          ) : null}
          {payment.status === "refused" && payment.rejection_reason ? (
            <Banner variant="danger">Motif du refus : {payment.rejection_reason}</Banner>
          ) : null}

          {payment.allocations.length > 0 ? (
            <table className="w-full text-sm">
              <thead className="text-xs text-text-muted">
                <tr>
                  <th scope="col" className="py-1 text-left font-medium">Mois</th>
                  <th scope="col" className="py-1 text-right font-medium">Montant</th>
                </tr>
              </thead>
              <tbody>
                {payment.allocations.map((line) => (
                  <tr key={line.period} className="border-t border-border">
                    <td className="py-1 text-text">{formatMonthYear(line.period)}</td>
                    <td className="py-1 text-right tabular-nums text-text">
                      {formatAmount(line.amount, payment.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
}
