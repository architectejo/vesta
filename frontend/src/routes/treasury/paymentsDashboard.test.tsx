import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type {
  ContributeInfo,
  DashboardSummary,
  PaymentDeclaration,
  PaymentDetail,
  PaymentListItem,
} from "../../api/treasury";
import { ToastProvider } from "../../design-system";
import { DashboardSummarySection } from "./DashboardSummarySection";
import { DeclarationReviewModal } from "./DeclarationReviewModal";
import { DeclarePaymentModal } from "./DeclarePaymentModal";
import { PaymentDetailModal } from "./PaymentDetailModal";
import { RecentPaymentsSection } from "./RecentPaymentsSection";
import { ToValidateSection } from "./ToValidateSection";

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getDashboardSummary: vi.fn(),
    getPayments: vi.fn(),
    getPaymentDetail: vi.fn(),
    requestPaymentReversal: vi.fn(),
    approvePaymentReversal: vi.fn(),
    rejectPaymentReversal: vi.fn(),
    getPaymentDeclaration: vi.fn(),
    previewPaymentDeclaration: vi.fn(),
    validatePaymentDeclaration: vi.fn(),
    rejectPaymentDeclaration: vi.fn(),
    createPaymentDeclaration: vi.fn(),
    getContributeInfo: vi.fn(),
  };
});

import {
  approvePaymentReversal,
  createPaymentDeclaration,
  getContributeInfo,
  getDashboardSummary,
  getPaymentDeclaration,
  getPaymentDetail,
  getPayments,
  previewPaymentDeclaration,
  requestPaymentReversal,
  validatePaymentDeclaration,
} from "../../api/treasury";

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

function listItem(overrides: Partial<PaymentListItem> = {}): PaymentListItem {
  return {
    id: 1,
    player: { membership_id: 5, name: "Jean Mukendi", jersey_number: 7, photo: null },
    contribution_type: { id: 2, name: "Mensuelle" },
    amount: "20.00",
    currency: "CDF",
    paid_on: "2026-10-01",
    method: "cash",
    method_label: "Espèces",
    source: "treasurer_entry",
    source_label: "Saisie Trésorier",
    status: "validated",
    status_label: "Validé",
    reversal_pending: false,
    ...overrides,
  };
}

function detail(overrides: Partial<PaymentDetail> = {}): PaymentDetail {
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
    allocations: [{ period: "2026-10-01", amount: "20.00" }],
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
    ...overrides,
  };
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("DashboardSummarySection", () => {
  it("affiche les indicateurs calculés par l'API avec la devise du club", async () => {
    const summary: DashboardSummary = {
      period: "2026-10",
      currency: "CDF",
      collected: "150.00",
      collection_rate: "75.00",
      matured_due_total: "200.00",
      matured_due_covered: "150.00",
      total_debts: "50.00",
      members_in_debt: 2,
      available_cash: "90.00",
    };
    vi.mocked(getDashboardSummary).mockResolvedValue(summary);
    wrap(<DashboardSummarySection />);
    expect(await screen.findByText("150 CDF")).toBeInTheDocument();
    expect(screen.getByText("75 %")).toBeInTheDocument();
    expect(screen.getByText("50 CDF")).toBeInTheDocument();
    expect(screen.getByText("2 joueurs en dette")).toBeInTheDocument();
    expect(screen.getByText("90 CDF")).toBeInTheDocument();
  });

  it("propose de réessayer en cas d'erreur", async () => {
    vi.mocked(getDashboardSummary).mockRejectedValue(new ApiError(500, {}));
    wrap(<DashboardSummarySection />);
    expect(await screen.findByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });
});

describe("RecentPaymentsSection", () => {
  it("affiche l'état vide avec l'action pour le Trésorier", async () => {
    vi.mocked(getPayments).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    const onRecord = vi.fn();
    wrap(<RecentPaymentsSection canRecordPayments onOpen={vi.fn()} onRecordPayment={onRecord} />);
    expect(await screen.findByText("Aucun paiement enregistré pour l'instant.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer un paiement" }));
    expect(onRecord).toHaveBeenCalled();
  });

  it("charge la suite avec « Voir plus » et ouvre le détail au clic", async () => {
    vi.mocked(getPayments)
      .mockResolvedValueOnce({ count: 2, next_offset: 1, results: [listItem({ id: 1 })] })
      .mockResolvedValueOnce({
        count: 2,
        next_offset: null,
        results: [listItem({ id: 2, player: { membership_id: 6, name: "Paul Kasongo", jersey_number: null, photo: null } })],
      });
    const onOpen = vi.fn();
    wrap(<RecentPaymentsSection canRecordPayments={false} onOpen={onOpen} onRecordPayment={vi.fn()} />);
    expect(await screen.findByText("Jean Mukendi")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Voir plus" }));
    expect(await screen.findByText("Paul Kasongo")).toBeInTheDocument();
    expect(getPayments).toHaveBeenLastCalledWith({ limit: 20, offset: 1 });
    expect(screen.queryByRole("button", { name: "Voir plus" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Paiement de Paul Kasongo/ }));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }));
  });

  it("affiche une erreur avec « Réessayer »", async () => {
    vi.mocked(getPayments).mockRejectedValue(new ApiError(500, {}));
    wrap(<RecentPaymentsSection canRecordPayments onOpen={vi.fn()} onRecordPayment={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });
});

describe("ToValidateSection", () => {
  it("est masquée quand il n'y a rien à valider", async () => {
    vi.mocked(getPayments).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    wrap(<ToValidateSection canValidateDeclarations canDecideReversals onOpen={vi.fn()} />);
    await waitFor(() => expect(getPayments).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByLabelText("Chargement des éléments à valider")).not.toBeInTheDocument());
    expect(screen.queryByText("À valider")).not.toBeInTheDocument();
  });

  it("liste les déclarations et les annulations demandées", async () => {
    vi.mocked(getPayments).mockImplementation(async (params) =>
      params?.reversal
        ? { count: 1, next_offset: null, results: [listItem({ id: 9, reversal_pending: true })] }
        : {
            count: 1,
            next_offset: null,
            results: [listItem({ id: 8, status: "to_validate", source: "player_declaration" })],
          },
    );
    wrap(<ToValidateSection canValidateDeclarations canDecideReversals onOpen={vi.fn()} />);
    expect(await screen.findByText(/Déclaration J'ai payé · 20 CDF/)).toBeInTheDocument();
    expect(screen.getByText(/Annulation demandée · 20 CDF/)).toBeInTheDocument();
  });
});

describe("ToValidateSection — Voir plus", () => {
  it("propose « Voir plus » quand l'API compte plus d'éléments et redemande 20 de plus", async () => {
    vi.mocked(getPayments).mockResolvedValue({
      count: 25,
      next_offset: 20,
      results: [listItem({ id: 8, status: "to_validate", source: "player_declaration" })],
    });
    wrap(<ToValidateSection canValidateDeclarations canDecideReversals={false} onOpen={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Voir plus" }));
    await waitFor(() => expect(getPayments).toHaveBeenCalledWith(expect.objectContaining({ limit: 40 })));
  });
});

describe("PaymentDetailModal", () => {
  it("envoie une demande d'annulation motivée (jamais de suppression)", async () => {
    vi.mocked(getPaymentDetail).mockResolvedValue(detail());
    vi.mocked(requestPaymentReversal).mockResolvedValue(
      detail({
        reversal: {
          id: 1,
          status: "pending_approval",
          status_label: "En attente",
          reason: "Erreur de saisie",
          reason_kind: "error",
          requested_by: { id: 3, name: "Tresor Ier" },
          requested_at: "2026-10-02T08:00:00Z",
          approved_by: null,
          approved_at: null,
          rejected_by: null,
          rejected_at: null,
          rejection_reason: "",
        },
      }),
    );
    const onChanged = vi.fn();
    wrap(
      <PaymentDetailModal
        paymentId={1}
        canRecordPayments
        canDecideReversals={false}
        onClose={vi.fn()}
        onReviewDeclaration={vi.fn()}
        onChanged={onChanged}
      />,
    );
    expect(await screen.findByText("Jean Mukendi")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Demander l'annulation" }));
    await userEvent.click(screen.getByRole("button", { name: "Envoyer la demande" }));
    expect(await screen.findByText("Indiquez le motif.")).toBeInTheDocument();
    expect(requestPaymentReversal).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("Motif de l'annulation"), "Erreur de saisie");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer la demande" }));
    await waitFor(() => expect(requestPaymentReversal).toHaveBeenCalledWith(1, "Erreur de saisie"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(await screen.findByText("En attente de validation par le Président.")).toBeInTheDocument();
  });

  it("n'affiche pas « Demander l'annulation » sans la capacité", async () => {
    vi.mocked(getPaymentDetail).mockResolvedValue(detail());
    wrap(
      <PaymentDetailModal
        paymentId={1}
        canRecordPayments={false}
        canDecideReversals={false}
        onClose={vi.fn()}
        onReviewDeclaration={vi.fn()}
        onChanged={vi.fn()}
      />,
    );
    expect(await screen.findByText("Jean Mukendi")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Demander l'annulation" })).not.toBeInTheDocument();
  });

  it("permet au Président de valider l'annulation après confirmation, sans champ PIN", async () => {
    const pending = detail({
      reversal: {
        id: 1,
        status: "pending_approval",
        status_label: "En attente",
        reason: "Doublon",
        reason_kind: "error",
        requested_by: { id: 3, name: "Tresor Ier" },
        requested_at: "2026-10-02T08:00:00Z",
        approved_by: null,
        approved_at: null,
        rejected_by: null,
        rejected_at: null,
        rejection_reason: "",
      },
    });
    vi.mocked(getPaymentDetail).mockResolvedValue(pending);
    vi.mocked(approvePaymentReversal).mockResolvedValue({ ...pending, status: "cancelled", status_label: "Annulé" });
    wrap(
      <PaymentDetailModal
        paymentId={1}
        canRecordPayments={false}
        canDecideReversals
        onClose={vi.fn()}
        onReviewDeclaration={vi.fn()}
        onChanged={vi.fn()}
      />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Valider l'annulation" }));
    await screen.findByRole("dialog", { name: /Annuler ce paiement de/ });
    expect(screen.queryByLabelText(/PIN/i)).not.toBeInTheDocument();
    expect(approvePaymentReversal).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Annuler le paiement" }));
    await waitFor(() => expect(approvePaymentReversal).toHaveBeenCalledWith(1));
  });
});

describe("DeclarationReviewModal", () => {
  const declaration = {
    ...detail({ status: "to_validate", status_label: "À valider", source: "player_declaration", receipt_available: false }),
    player: { membership_id: 5, name: "Jean Mukendi" },
    transaction: { provider: "link", status: "pending", external_ref: "" },
  } as unknown as PaymentDeclaration;

  it("affiche l'aperçu de répartition puis valide après confirmation, sans PIN", async () => {
    vi.mocked(getPaymentDeclaration).mockResolvedValue(declaration);
    vi.mocked(previewPaymentDeclaration).mockResolvedValue({
      membership_id: 5,
      contribution_type: { id: 2, name: "Mensuelle" },
      amount: "20.00",
      currency: "CDF",
      paid_on: "2026-10-01",
      is_free_type: false,
      allocations: [{ period: "2026-10-01", amount: "20.00", period_amount: "20.00", covered_after: "20.00", status: "paid" }],
      unallocated_amount: "0.00",
      current: { balance: "-20.00", amount_due: "20.00", is_in_good_standing: false, reason: "En dette : 20 CDF", currency: "CDF" },
      after: { balance: "0.00", amount_due: "0.00", is_in_good_standing: true, reason: "En ordre", currency: "CDF" },
    });
    vi.mocked(validatePaymentDeclaration).mockResolvedValue(declaration);
    const onDone = vi.fn();
    wrap(<DeclarationReviewModal paymentId={1} onClose={vi.fn()} onDone={onDone} />);
    await userEvent.click(await screen.findByRole("button", { name: "Valider" }));
    expect(await screen.findByText(/Nouveau solde/)).toBeInTheDocument();
    expect(screen.getByText("En ordre")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Continuer" }));
    expect(screen.queryByLabelText(/PIN/i)).not.toBeInTheDocument();
    expect(validatePaymentDeclaration).not.toHaveBeenCalled();
    const confirm = await screen.findByRole("dialog", { name: /Valider ce paiement de/ });
    await userEvent.click(within(confirm).getByRole("button", { name: "Valider le paiement" }));
    await waitFor(() => expect(validatePaymentDeclaration).toHaveBeenCalledWith(1));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });
});

describe("DeclarePaymentModal", () => {
  const info: ContributeInfo = {
    payment_link_configured: true,
    payment_link_url: "https://pay.example/club",
    currency: "CDF",
    contribution_types: [{ id: 2, name: "Mensuelle", nature: "mandatory", periodicity: "monthly", amount: "20.00" }],
    default_contribution_type_id: 2,
  };

  it("exige un montant et une référence, puis envoie la déclaration", async () => {
    vi.mocked(getContributeInfo).mockResolvedValue(info);
    vi.mocked(createPaymentDeclaration).mockResolvedValue({} as PaymentDeclaration);
    const onDeclared = vi.fn();
    wrap(<DeclarePaymentModal open onClose={vi.fn()} onDeclared={onDeclared} />);
    await userEvent.click(await screen.findByRole("button", { name: "Envoyer la déclaration" }));
    expect(await screen.findByText("Saisissez un montant supérieur à 0.")).toBeInTheDocument();
    expect(screen.getByText("Indiquez la référence reçue lors du paiement.")).toBeInTheDocument();
    expect(createPaymentDeclaration).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText("Montant"), "20");
    await userEvent.type(screen.getByLabelText("Référence de transaction"), "TX123");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer la déclaration" }));
    await waitFor(() =>
      expect(createPaymentDeclaration).toHaveBeenCalledWith({
        contribution_type_id: 2,
        amount: "20",
        reference: "TX123",
        attachment: null,
      }),
    );
    await waitFor(() => expect(onDeclared).toHaveBeenCalled());
  });
});
