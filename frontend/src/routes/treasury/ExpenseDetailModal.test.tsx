import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { Expense, ExpenseSummary, TreasuryCapabilities } from "../../api/treasury";
import { ToastProvider } from "../../design-system";
import { ExpenseDetailModal } from "./ExpenseDetailModal";

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getExpense: vi.fn(),
    getExpenseSummary: vi.fn(),
    refuseExpense: vi.fn(),
    releaseExpense: vi.fn(),
    releaseExpenseWithDerogation: vi.fn(),
    uploadExpenseReceipt: vi.fn(),
    downloadExpenseAttachment: vi.fn(),
  };
});

import {
  getExpense,
  getExpenseSummary,
  refuseExpense,
  releaseExpense,
  releaseExpenseWithDerogation,
  uploadExpenseReceipt,
} from "../../api/treasury";

function makeCapabilities(overrides: Partial<TreasuryCapabilities> = {}): TreasuryCapabilities {
  return {
    can_read: true,
    can_write: false,
    can_record_payments: false,
    can_read_expenses: true,
    can_manage_expense_categories: false,
    can_submit_expenses: false,
    can_validate_expenses: false,
    can_derogate: false,
    can_decide_payment_reversal: false,
    can_upload_expense_receipts: false,
    can_manage_assistance_scales: false,
    can_process_assistance_requests: false,
    can_request_assistance: true,
    ...overrides,
  };
}

function makeExpense(overrides: Partial<Expense> = {}): Expense {
  return {
    id: 1,
    category: { id: 1, name: "Arbitrage" },
    amount: "30.00",
    currency: "USD",
    beneficiary_name: "Arbitre Kalala",
    beneficiary_membership_id: null,
    reason: "Match du 12/09",
    expense_date: "2026-09-12",
    status: "pending",
    status_label: "En attente",
    created_by: { id: 2, name: "Alice Trésorière" },
    created_at: "2026-09-12T10:00:00Z",
    refused_at: null,
    refusal_reason: "",
    released_at: null,
    released_by: null,
    justification_deadline: null,
    is_overdue: false,
    justified_at: null,
    unjustified_at: null,
    social_assistance_request_id: null,
    derogation: null,
    attachments: [],
    ...overrides,
  };
}

function makeSummary(overrides: Partial<ExpenseSummary> = {}): ExpenseSummary {
  return {
    can_release: true,
    reason: "Aucune dépense non justifiée : la libération est possible.",
    blocking_expense_ids: [],
    available_cash: "100.00",
    currency: "USD",
    ...overrides,
  };
}

function renderModal(capabilities: TreasuryCapabilities, expenseId: number | null = 1) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  const onChanged = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <ExpenseDetailModal expenseId={expenseId} capabilities={capabilities} onClose={onClose} onChanged={onChanged} />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onClose, onChanged };
}

describe("ExpenseDetailModal", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it("affiche « Refuser » et « Valider et libérer » pour un valideur, sans blocage", async () => {
    vi.mocked(getExpense).mockResolvedValue(makeExpense());
    vi.mocked(getExpenseSummary).mockResolvedValue(makeSummary());
    renderModal(makeCapabilities({ can_validate_expenses: true }));

    expect(await screen.findByRole("button", { name: "Valider et libérer" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Refuser" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Libérer par dérogation" })).not.toBeInTheDocument();
  });

  it("refuse la dépense avec un motif obligatoire", async () => {
    vi.mocked(getExpense).mockResolvedValue(makeExpense());
    vi.mocked(getExpenseSummary).mockResolvedValue(makeSummary());
    vi.mocked(refuseExpense).mockResolvedValue(makeExpense({ status: "refused" }));
    const user = userEvent.setup();
    renderModal(makeCapabilities({ can_validate_expenses: true }));

    await user.click(await screen.findByRole("button", { name: "Refuser" }));
    const reasonDialog = await screen.findByRole("dialog", { name: "Refuser la dépense" });
    await user.click(within(reasonDialog).getByRole("button", { name: "Refuser la dépense" }));
    expect(await within(reasonDialog).findByText("Indiquez le motif du refus.")).toBeInTheDocument();

    await user.type(within(reasonDialog).getByLabelText("Motif du refus"), "Facture manquante");
    await user.click(within(reasonDialog).getByRole("button", { name: "Refuser la dépense" }));

    await waitFor(() => expect(refuseExpense).toHaveBeenCalledWith(1, "Facture manquante"));
    expect(await screen.findByText(/Dépense refusée\. Alice Trésorière a été prévenu\./)).toBeInTheDocument();
  });

  it("libère la dépense seulement après confirmation, sans champ PIN", async () => {
    vi.mocked(getExpense).mockResolvedValue(makeExpense());
    vi.mocked(getExpenseSummary).mockResolvedValue(makeSummary());
    vi.mocked(releaseExpense).mockResolvedValue(makeExpense({ status: "released" }));
    const user = userEvent.setup();
    renderModal(makeCapabilities({ can_validate_expenses: true }));

    await user.click(await screen.findByRole("button", { name: "Valider et libérer" }));
    await screen.findByRole("dialog", { name: /Libérer cette dépense de/ });
    expect(screen.queryByLabelText(/PIN/i)).not.toBeInTheDocument();
    expect(releaseExpense).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Libérer la dépense" }));

    await waitFor(() => expect(releaseExpense).toHaveBeenCalledWith(1));
    expect(await screen.findByText("Dépense libérée. Le justificatif est attendu sous peu.")).toBeInTheDocument();
  });

  it("bloque la libération normale et propose la dérogation au Président", async () => {
    vi.mocked(getExpense).mockResolvedValue(makeExpense());
    vi.mocked(getExpenseSummary).mockResolvedValue(
      makeSummary({
        can_release: false,
        reason: "Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée.",
        blocking_expense_ids: [9],
      }),
    );
    vi.mocked(releaseExpenseWithDerogation).mockResolvedValue(makeExpense({ status: "released" }));
    const user = userEvent.setup();
    renderModal(makeCapabilities({ can_validate_expenses: true, can_derogate: true }));

    expect(
      await screen.findByText("Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Valider et libérer" })).toBeDisabled();

    const derogationButton = screen.getByRole("button", { name: "Libérer par dérogation" });
    expect(derogationButton.className).toMatch(/danger/);
    await user.click(derogationButton);
    const reasonDialog = await screen.findByRole("dialog", { name: "Libérer par dérogation" });
    expect(within(reasonDialog).getByText(/Arbitre Kalala/)).toBeInTheDocument();
    await user.type(within(reasonDialog).getByLabelText("Motif de la dérogation"), "Urgence médicale");
    await user.click(within(reasonDialog).getByRole("button", { name: "Continuer" }));

    const confirmDialog = await screen.findByRole("dialog", { name: /par dérogation \?/ });
    expect(within(confirmDialog).getByText(/Bénéficiaire : Arbitre Kalala/)).toBeInTheDocument();
    expect(releaseExpenseWithDerogation).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirmer la dérogation" }));

    await waitFor(() =>
      expect(releaseExpenseWithDerogation).toHaveBeenCalledWith(1, "Urgence médicale"),
    );
    expect(await screen.findByText("Dépense libérée par dérogation.")).toBeInTheDocument();
  });

  it("ne propose pas la dérogation à un valideur qui n'a pas cette capacité", async () => {
    vi.mocked(getExpense).mockResolvedValue(makeExpense());
    vi.mocked(getExpenseSummary).mockResolvedValue(makeSummary({ can_release: false, blocking_expense_ids: [9] }));
    renderModal(makeCapabilities({ can_validate_expenses: true, can_derogate: false }));

    await screen.findByRole("button", { name: "Refuser" });
    expect(screen.queryByRole("button", { name: "Libérer par dérogation" })).not.toBeInTheDocument();
  });

  it("propose « Ajouter le justificatif » pour une dépense libérée, au Trésorier", async () => {
    vi.mocked(getExpense).mockResolvedValue(
      makeExpense({ status: "released", released_at: "2026-09-13T00:00:00Z", justification_deadline: "2026-09-20" }),
    );
    vi.mocked(uploadExpenseReceipt).mockResolvedValue(makeExpense({ status: "justified" }));
    const user = userEvent.setup();
    renderModal(makeCapabilities({ can_upload_expense_receipts: true }));

    expect(await screen.findByText("À justifier avant le 20/09/2026")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ajouter le justificatif" }));

    const uploadDialog = await screen.findByRole("dialog", { name: "Ajouter le justificatif" });
    const file = new File(["contenu"], "facture.pdf", { type: "application/pdf" });
    const fileInput = within(uploadDialog).getByLabelText("Justificatif") as HTMLInputElement;
    await user.upload(fileInput, file);
    await user.click(within(uploadDialog).getByRole("button", { name: "Envoyer le justificatif" }));

    await waitFor(() => expect(uploadExpenseReceipt).toHaveBeenCalledWith(1, file));
    expect(await screen.findByText("Justificatif envoyé.")).toBeInTheDocument();
  });

  it("affiche une dépense justifiée en lecture seule, sans action", async () => {
    vi.mocked(getExpense).mockResolvedValue(makeExpense({ status: "justified" }));
    renderModal(makeCapabilities({ can_validate_expenses: true, can_upload_expense_receipts: true }));

    await screen.findByRole("dialog");
    expect(screen.queryByRole("button", { name: "Valider et libérer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ajouter le justificatif" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fermer" })).toBeInTheDocument();
  });

  it("affiche l'erreur renvoyée par l'API après la confirmation", async () => {
    vi.mocked(getExpense).mockResolvedValue(makeExpense());
    vi.mocked(getExpenseSummary).mockResolvedValue(makeSummary());
    vi.mocked(releaseExpense).mockRejectedValue(
      new ApiError(400, { detail: "Cette dépense a déjà été libérée." }),
    );
    const user = userEvent.setup();
    renderModal(makeCapabilities({ can_validate_expenses: true }));

    await user.click(await screen.findByRole("button", { name: "Valider et libérer" }));
    await user.click(await screen.findByRole("button", { name: "Libérer la dépense" }));

    expect(await screen.findByText("Cette dépense a déjà été libérée.")).toBeInTheDocument();
  });
});
