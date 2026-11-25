import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PaymentDetail, PaymentReversalHistoryItem } from "../../api/treasury";
import { ToastProvider } from "../../design-system";
import { PaymentDetailModal } from "./PaymentDetailModal";

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return { ...actual, getPaymentDetail: vi.fn() };
});

import { getPaymentDetail } from "../../api/treasury";

function detail(history: PaymentReversalHistoryItem[] | undefined): PaymentDetail {
  return {
    id: 1,
    membership_id: 5,
    contribution_type: { id: 2, name: "Mensuelle" },
    amount: "20.00",
    currency: "CDF",
    method: "cash",
    method_label: "Espèces",
    reference: "",
    paid_on: "2026-10-01",
    source: "treasurer_entry",
    source_label: "Saisie Trésorier",
    receipt_number: 12,
    receipt_available: true,
    receipt_url: "/x",
    attachment_url: null,
    validated_at: "2026-10-01T10:00:00Z",
    cash_session_id: null,
    client_uuid: null,
    client_recorded_at: null,
    allocations: [],
    player_status: null,
    player: { membership_id: 5, name: "Jean Mukendi", jersey_number: 7, photo: null },
    status: "validated",
    status_label: "Validé",
    reversal_pending: false,
    submitted_by: { id: 3, name: "Tresor Ier" },
    submitted_at: "2026-10-01T09:00:00Z",
    validated_by: null,
    rejected_at: null,
    rejection_reason: "",
    reversal: null,
    reversal_history: history,
  };
}

function renderModal() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <PaymentDetailModal
          paymentId={1}
          canRecordPayments
          canDecideReversals={false}
          onClose={vi.fn()}
          onReviewDeclaration={vi.fn()}
          onChanged={vi.fn()}
        />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const rejected: PaymentReversalHistoryItem = {
  id: 2,
  status: "rejected",
  status_label: "Refusée",
  reason: "Doublon présumé",
  reason_kind: "error",
  requested_by: { id: 3, name: "Tresor Ier" },
  requested_at: "2026-10-05T08:00:00Z",
  decided_by: { id: 1, name: "Pres Ident" },
  decided_at: "2026-10-06T08:00:00Z",
  rejection_reason: "Le paiement est correct",
};
const approved: PaymentReversalHistoryItem = {
  id: 1,
  status: "approved",
  status_label: "Approuvée",
  reason: "Remboursement",
  reason_kind: "refund",
  requested_by: { id: 3, name: "Tresor Ier" },
  requested_at: "2026-10-02T08:00:00Z",
  decided_by: { id: 1, name: "Pres Ident" },
  decided_at: "2026-10-03T08:00:00Z",
  rejection_reason: "",
};

beforeEach(() => {
  vi.resetAllMocks();
});

describe("Historique des demandes d'annulation", () => {
  it("affiche les demandes dans l'ordre reçu, avec le motif du refus", async () => {
    vi.mocked(getPaymentDetail).mockResolvedValue(detail([rejected, approved]));
    renderModal();
    expect(await screen.findByText("Demandes d'annulation")).toBeInTheDocument();
    const items = screen.getAllByRole("listitem") as [HTMLElement, HTMLElement];
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("Refusée")).toBeInTheDocument();
    expect(within(items[0]).getByText("Doublon présumé")).toBeInTheDocument();
    expect(within(items[0]).getByText(/Demandée par Tresor Ier le 05\/10\/2026/)).toBeInTheDocument();
    expect(within(items[0]).getByText(/Refusée par Pres Ident le 06\/10\/2026/)).toBeInTheDocument();
    expect(within(items[0]).getByText("Motif du refus : Le paiement est correct")).toBeInTheDocument();
    expect(within(items[1]).getByText("Approuvée")).toBeInTheDocument();
    expect(within(items[1]).getByText(/Approuvée par Pres Ident le 03\/10\/2026/)).toBeInTheDocument();
    expect(within(items[1]).queryByText(/Motif du refus/)).not.toBeInTheDocument();
  });

  it("n'affiche aucune section quand l'historique est vide ou absent", async () => {
    vi.mocked(getPaymentDetail).mockResolvedValue(detail([]));
    renderModal();
    expect(await screen.findByText("Jean Mukendi")).toBeInTheDocument();
    expect(screen.queryByText("Demandes d'annulation")).not.toBeInTheDocument();
  });
});
