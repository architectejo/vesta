import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import type { MemberDetail, PaymentListItem } from "../../api/treasury";
import { MemberSituationModal } from "./MemberSituationModal";

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return { ...actual, getMemberDetail: vi.fn(), getPayments: vi.fn() };
});

import { getMemberDetail, getPayments } from "../../api/treasury";

const member = {
  membership_id: 5,
  name: "Jean Joueur",
  currency: "USD",
  today: "2026-10-01",
  next_due: null,
  unpaid_months: [],
  free_contributions: [],
  can_record_payment: false,
  monthly_type: null,
  statuses: [],
} as unknown as MemberDetail;

const payment = {
  id: 42,
  player: { membership_id: 5, name: "Jean Joueur" },
  contribution_type: { id: 1, name: "Cotisation mensuelle" },
  amount: "20.00",
  currency: "USD",
  paid_on: "2026-09-10",
  method: "cash",
  method_label: "Espèces",
  source: "manual",
  source_label: "Saisie",
  status: "validated",
  status_label: "Validé",
  reversal_pending: false,
} as unknown as PaymentListItem;

describe("MemberSituationModal - onglet Paiements", () => {
  it("ouvre le détail du paiement au clic sur une ligne", async () => {
    vi.mocked(getMemberDetail).mockResolvedValue(member);
    vi.mocked(getPayments).mockResolvedValue({ count: 1, next_offset: null, results: [payment] });
    const onOpenPayment = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
        <MemberSituationModal membershipId={5} onClose={() => undefined} onPaymentRecorded={() => undefined} onOpenPayment={onOpenPayment} />
        </ToastProvider>
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Paiements" }));
    await user.click(await screen.findByRole("button", { name: /Détail du paiement/ }));
    expect(onOpenPayment).toHaveBeenCalledWith(42);
  });
});
