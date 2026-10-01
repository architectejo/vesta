import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import { ApiError } from "../../api/client";
import type { Expense, ExpenseCategory, ExpenseListResponse, TreasuryCapabilities } from "../../api/treasury";
import { ToastProvider } from "../../design-system";
import { DepensesPage } from "./DepensesPage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getTreasuryCapabilities: vi.fn(),
    getExpenseSummary: vi.fn(),
    getExpenses: vi.fn(),
    getExpenseCategories: vi.fn(),
    createExpense: vi.fn(),
    createExpenseCategory: vi.fn(),
    archiveExpenseCategory: vi.fn(),
  };
});

import { getMyProfile } from "../../api/clubs";
import {
  createExpense,
  getExpenseCategories,
  getExpenseSummary,
  getExpenses,
  getTreasuryCapabilities,
} from "../../api/treasury";

function makeProfile(): MyProfile {
  return {
    membership_id: 1,
    club: { id: 1, slug: "test", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    identity: {
      first_name: "Jean",
      last_name: "Mukendi",
      photo: null,
      email: "jean@example.com",
      phone: "",
      birth_date: null,
      weight_kg: null,
      height_cm: null,
    },
    position: "midfielder",
    position_label: "Milieu",
    position_detail: "",
    jersey_number: null,
    membership_status: "active",
    membership_status_label: "Inscrit",
    roles: [{ role: "treasurer", label: "Trésorier" }],
    email_notifications_enabled: true,
  };
}

function makeCapabilities(overrides: Partial<TreasuryCapabilities> = {}): {
  currency: string;
  capabilities: TreasuryCapabilities;
} {
  return {
    currency: "USD",
    capabilities: {
      can_read: true,
      can_write: false,
      can_record_payments: false,
      can_read_expenses: true,
      can_manage_expense_categories: false,
      can_submit_expenses: true,
      can_validate_expenses: false,
      can_derogate: false,
      can_upload_expense_receipts: true,
      can_manage_assistance_scales: false,
      can_process_assistance_requests: false,
      can_request_assistance: true,
      ...overrides,
    },
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

function listResponse(results: Expense[]): ExpenseListResponse {
  return { count: results.length, next_offset: null, results };
}

function makeCategory(overrides: Partial<ExpenseCategory> = {}): ExpenseCategory {
  return {
    id: 1,
    name: "Arbitrage",
    ceiling: null,
    receipt_required: true,
    good_standing_only: false,
    status: "active",
    archived_at: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/tresorerie/depenses"]}>
        <ToastProvider>
          <DepensesPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DepensesPage", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it("affiche le loader puis refuse l'accès à un rôle sans droit de lecture", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities({ can_read_expenses: false }));
    renderPage();

    expect(await screen.findByText("Vous n'avez pas accès aux dépenses.")).toBeInTheDocument();
  });

  it("affiche un message d'erreur en français quand les capacités ne chargent pas", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockRejectedValueOnce(new ApiError(500, null));
    renderPage();

    expect(await screen.findByText("Impossible de charger cette section.")).toBeInTheDocument();
  });

  it("affiche le bandeau de blocage quand une dépense n'est pas justifiée", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());
    vi.mocked(getExpenseSummary).mockResolvedValue({
      can_release: false,
      reason: "Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée.",
      blocking_expense_ids: [7],
      available_cash: "100.00",
      currency: "USD",
    });
    vi.mocked(getExpenses).mockResolvedValue(listResponse([]));
    vi.mocked(getExpenseCategories).mockResolvedValue([]);
    renderPage();

    expect(
      await screen.findByText("Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Voir la dépense" })).toBeInTheDocument();
  });

  it("affiche les états vides distincts pour « À traiter », « Dépenses récentes » et « Catégories »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());
    vi.mocked(getExpenseSummary).mockResolvedValue({
      can_release: true,
      reason: "Aucune dépense non justifiée : la libération est possible.",
      blocking_expense_ids: [],
      available_cash: "100.00",
      currency: "USD",
    });
    vi.mocked(getExpenses).mockResolvedValue(listResponse([]));
    vi.mocked(getExpenseCategories).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText("Aucune dépense à traiter.")).toBeInTheDocument();
    expect(
      await screen.findByText("Aucune dépense enregistrée pour l'instant."),
    ).toBeInTheDocument();
    expect(await screen.findByText("Aucune catégorie de dépense.")).toBeInTheDocument();
  });

  it("liste les dépenses à traiter et ouvre la saisie d'une nouvelle dépense", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());
    vi.mocked(getExpenseSummary).mockResolvedValue({
      can_release: true,
      reason: "Aucune dépense non justifiée : la libération est possible.",
      blocking_expense_ids: [],
      available_cash: "100.00",
      currency: "USD",
    });
    vi.mocked(getExpenses).mockImplementation(({ status } = {}) =>
      Promise.resolve(listResponse(status?.includes("pending") ? [makeExpense()] : [])),
    );
    vi.mocked(getExpenseCategories).mockResolvedValue([makeCategory()]);
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText(/Arbitre Kalala/)).toBeInTheDocument();
    // « Arbitrage » apparaît deux fois : la dépense « À traiter » et la catégorie.
    expect(await screen.findAllByText("Arbitrage")).toHaveLength(2);

    await user.click((await screen.findAllByRole("button", { name: "Saisir une dépense" }))[0]!);
    expect(await screen.findByRole("dialog", { name: "Saisir une dépense" })).toBeInTheDocument();
  });

  it("saisit une dépense et affiche le message de succès", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());
    vi.mocked(getExpenseSummary).mockResolvedValue({
      can_release: true,
      reason: "Aucune dépense non justifiée : la libération est possible.",
      blocking_expense_ids: [],
      available_cash: "100.00",
      currency: "USD",
    });
    vi.mocked(getExpenses).mockResolvedValue(listResponse([]));
    vi.mocked(getExpenseCategories).mockResolvedValue([makeCategory()]);
    vi.mocked(createExpense).mockResolvedValue(makeExpense());
    const user = userEvent.setup();
    renderPage();

    await user.click((await screen.findAllByRole("button", { name: "Saisir une dépense" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Saisir une dépense" });

    await user.selectOptions(
      within(dialog).getByLabelText("Catégorie", { selector: "select" }),
      within(dialog).getByRole("option", { name: "Arbitrage" }),
    );
    await user.type(within(dialog).getByLabelText("Montant"), "30");
    await user.type(within(dialog).getByLabelText("Nom du bénéficiaire"), "Arbitre Kalala");
    await user.type(within(dialog).getByLabelText("Motif"), "Match du 12/09");
    await user.type(within(dialog).getByLabelText("Date"), "2026-09-12");

    await user.click(within(dialog).getByRole("button", { name: "Enregistrer la dépense" }));

    await waitFor(() =>
      expect(createExpense).toHaveBeenCalledWith(
        expect.objectContaining({
          category_id: 1,
          amount: "30",
          beneficiary_name: "Arbitre Kalala",
          reason: "Match du 12/09",
          expense_date: "2026-09-12",
        }),
      ),
    );
    expect(await screen.findByText("Dépense enregistrée.")).toBeInTheDocument();
  });

  it("masque « Saisir une dépense » et « Gérer les catégories » sans les capacités correspondantes", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(
      makeCapabilities({ can_submit_expenses: false, can_manage_expense_categories: false }),
    );
    vi.mocked(getExpenseSummary).mockResolvedValue({
      can_release: true,
      reason: "",
      blocking_expense_ids: [],
      available_cash: "0.00",
      currency: "USD",
    });
    vi.mocked(getExpenses).mockResolvedValue(listResponse([]));
    vi.mocked(getExpenseCategories).mockResolvedValue([]);
    renderPage();

    await screen.findByText("Aucune dépense à traiter.");
    expect(screen.queryByRole("button", { name: "Saisir une dépense" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Plus d'actions" })).not.toBeInTheDocument();
  });
});
