import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { MemberDetail, MemberListResponse, MemberRow } from "../../api/treasury";
import { ToastProvider } from "../../design-system";
import { MemberSituationModal } from "./MemberSituationModal";
import { MembersSection } from "./MembersSection";

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getMembers: vi.fn(),
    getMemberDetail: vi.fn(),
    getMemberGrid: vi.fn(),
    getPayments: vi.fn(),
    getContributionTypes: vi.fn(),
  };
});

import {
  getContributionTypes,
  getMemberDetail,
  getMemberGrid,
  getMembers,
  getPayments,
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

function makeRow(overrides: Partial<MemberRow> = {}): MemberRow {
  return {
    membership_id: 1,
    first_name: "Jean",
    last_name: "Mukendi",
    name: "Jean Mukendi",
    jersey_number: 7,
    photo: null,
    membership_status: "active",
    membership_status_label: "Inscrit",
    financial_status: "in_debt",
    financial_status_label: "En dette",
    statuses: [{ key: "in_debt", label: "En dette" }],
    is_suspended: false,
    suspension_matches_remaining: null,
    balance: "-20.00",
    amount_due: "20.00",
    is_in_good_standing: false,
    reason: "Le joueur est en dette : 20.00 USD à régulariser.",
    currency: "USD",
    monthly_type: { id: 3, name: "Mensuelle A" },
    last_payment_on: "2026-08-12",
    ...overrides,
  };
}

function makePage(results: MemberRow[], overrides: Partial<MemberListResponse> = {}): MemberListResponse {
  return {
    currency: "USD",
    today: "2026-10-07",
    ordering: "balance",
    count: results.length,
    limit: 20,
    offset: 0,
    next_offset: null,
    results,
    ...overrides,
  };
}

function makeDetail(overrides: Partial<MemberDetail> = {}): MemberDetail {
  return {
    ...makeRow(),
    today: "2026-10-07",
    next_due: {
      contribution_type: { id: 3, name: "Mensuelle A" },
      period: "2026-11-01",
      period_label: "novembre 2026",
      due_date: "2026-11-10",
      amount: "20.00",
    },
    unpaid_months: [
      {
        contribution_type: { id: 3, name: "Mensuelle A" },
        period: "2026-09-01",
        period_label: "septembre 2026",
        due_date: "2026-09-10",
        amount_due: "20.00",
        allocated: "0.00",
        remaining: "20.00",
      },
    ],
    free_contributions: [],
    can_record_payment: true,
    ...overrides,
  };
}

describe("MembersSection", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(getContributionTypes).mockResolvedValue([]);
  });

  it("affiche un chargement puis les membres, avec statut et solde fournis par l'API", async () => {
    vi.mocked(getMembers).mockResolvedValue(makePage([makeRow()]));
    wrap(<MembersSection onOpen={vi.fn()} />);

    expect(screen.getByRole("status", { name: "Chargement des membres" })).toBeInTheDocument();
    expect(await screen.findByText("Jean Mukendi")).toBeInTheDocument();
    expect(screen.getByText("En dette · 20 USD")).toBeInTheDocument();
    expect(screen.getByText("-20 USD")).toBeInTheDocument();
    expect(getMembers).toHaveBeenCalledWith(expect.objectContaining({ ordering: "balance", limit: 20, offset: 0 }));
  });

  it("ouvre la situation au clic sur une ligne", async () => {
    const onOpen = vi.fn();
    vi.mocked(getMembers).mockResolvedValue(makePage([makeRow()]));
    wrap(<MembersSection onOpen={onOpen} />);

    await userEvent.setup().click(await screen.findByText("Jean Mukendi"));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ membership_id: 1 }));
  });

  it("transmet recherche, statut, type et tri à l'API", async () => {
    const user = userEvent.setup();
    vi.mocked(getContributionTypes).mockResolvedValue([
      {
        id: 3,
        name: "Mensuelle A",
        nature: "mandatory",
        amount: "20",
        periodicity: "monthly",
        due_day: 10,
        due_month: null,
        deadline: null,
        is_membership_fee: false,
        scope: "all",
        status: "active",
        archived_at: null,
        created_at: "",
        updated_at: "",
      },
    ]);
    vi.mocked(getMembers).mockResolvedValue(makePage([makeRow()]));
    wrap(<MembersSection onOpen={vi.fn()} />);
    await screen.findByText("Jean Mukendi");

    await user.click(screen.getByRole("button", { name: "En dette" }));
    await waitFor(() =>
      expect(getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ status: ["in_debt"] })),
    );

    await user.selectOptions(screen.getByLabelText("Trier par"), "name");
    await waitFor(() => expect(getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ ordering: "name" })));

    await screen.findByRole("option", { name: "Mensuelle A" });
    await user.selectOptions(screen.getByLabelText("Type de cotisation"), "3");
    await waitFor(() =>
      expect(getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ contributionTypeIds: [3] })),
    );

    await user.type(screen.getByLabelText("Rechercher un joueur"), "muk");
    await waitFor(() => expect(getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ q: "muk" })));
  });

  it("charge la page suivante avec « Voir plus »", async () => {
    vi.mocked(getMembers)
      .mockResolvedValueOnce(makePage([makeRow()], { count: 2, next_offset: 20 }))
      .mockResolvedValueOnce(
        makePage([makeRow({ membership_id: 2, name: "Paul Kalala", jersey_number: 9 })], { count: 2, offset: 20 }),
      );
    wrap(<MembersSection onOpen={vi.fn()} />);

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Voir plus" }));
    expect(await screen.findByText("Paul Kalala")).toBeInTheDocument();
    expect(getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 20 }));
    expect(screen.queryByRole("button", { name: "Voir plus" })).not.toBeInTheDocument();
  });

  it("affiche l'état vide, puis « aucun résultat » avec un filtre", async () => {
    vi.mocked(getMembers).mockResolvedValue(makePage([]));
    wrap(<MembersSection onOpen={vi.fn()} />);
    expect(await screen.findByText("Aucun joueur dans le club.")).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Parti" }));
    expect(await screen.findByText("Aucun joueur ne correspond à ces filtres.")).toBeInTheDocument();
  });

  it("affiche l'erreur avec « Réessayer »", async () => {
    vi.mocked(getMembers).mockRejectedValueOnce(new ApiError(500, null));
    wrap(<MembersSection onOpen={vi.fn()} />);
    expect(await screen.findByText("Impossible de charger les membres du club.")).toBeInTheDocument();

    vi.mocked(getMembers).mockResolvedValue(makePage([makeRow()]));
    await userEvent.setup().click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByText("Jean Mukendi")).toBeInTheDocument();
  });
});

describe("MemberSituationModal", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(getContributionTypes).mockResolvedValue([]);
    vi.mocked(getPayments).mockResolvedValue({ count: 0, next_offset: null, results: [] });
  });

  it("affiche situation, prochaine échéance et impayés", async () => {
    vi.mocked(getMemberDetail).mockResolvedValue(makeDetail());
    wrap(<MemberSituationModal membershipId={1} onClose={vi.fn()} onPaymentRecorded={vi.fn()} />);

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/novembre 2026 · 20 USD/)).toBeInTheDocument();
    expect(within(dialog).getByText("Le joueur est en dette : 20.00 USD à régulariser.")).toBeInTheDocument();
    expect(within(dialog).getByText(/septembre 2026 · Mensuelle A/)).toBeInTheDocument();
    expect(getMemberDetail).toHaveBeenCalledWith(1);
  });

  it("masque « Enregistrer un paiement » quand l'API ne l'autorise pas", async () => {
    vi.mocked(getMemberDetail).mockResolvedValue(makeDetail({ can_record_payment: false }));
    wrap(<MemberSituationModal membershipId={1} onClose={vi.fn()} onPaymentRecorded={vi.fn()} />);

    await screen.findByText(/septembre 2026/);
    expect(screen.queryByRole("button", { name: "Enregistrer un paiement" })).not.toBeInTheDocument();
  });

  it("ouvre l'enregistrement d'un paiement avec le joueur présélectionné", async () => {
    vi.mocked(getMemberDetail).mockResolvedValue(makeDetail());
    wrap(<MemberSituationModal membershipId={1} onClose={vi.fn()} onPaymentRecorded={vi.fn()} />);

    await userEvent.setup().click(await screen.findByRole("button", { name: "Enregistrer un paiement" }));
    await waitFor(() => expect(screen.getAllByRole("dialog")).toHaveLength(2));
    const recordDialog = screen.getAllByRole("dialog")[1] as HTMLElement;
    expect(within(recordDialog).getByText("Jean Mukendi", { exact: false })).toBeInTheDocument();
  });

  it("charge les paiements du joueur dans l'onglet « Paiements »", async () => {
    vi.mocked(getMemberDetail).mockResolvedValue(makeDetail());
    vi.mocked(getPayments).mockResolvedValue({
      count: 1,
      next_offset: null,
      results: [
        {
          id: 9,
          player: { membership_id: 1, name: "Jean Mukendi", jersey_number: 7, photo: null },
          contribution_type: { id: 3, name: "Mensuelle A" },
          amount: "20.00",
          currency: "USD",
          paid_on: "2026-08-12",
          method: "cash",
          method_label: "Espèces",
          source: "manual",
          source_label: "Saisie",
          status: "validated",
          status_label: "Validé",
          reversal_pending: false,
        },
      ],
    });
    wrap(<MemberSituationModal membershipId={1} onClose={vi.fn()} onPaymentRecorded={vi.fn()} />);

    await userEvent.setup().click(await screen.findByRole("tab", { name: "Paiements" }));
    expect(await screen.findByText(/12\/08\/2026 · Espèces/)).toBeInTheDocument();
    expect(getPayments).toHaveBeenCalledWith(expect.objectContaining({ membershipId: 1, limit: 20, offset: 0 }));
  });

  it("affiche la grille en lecture dans l'onglet « Grille »", async () => {
    vi.mocked(getMemberDetail).mockResolvedValue(makeDetail());
    vi.mocked(getMemberGrid).mockResolvedValue({
      player: {
        membership_id: 1,
        first_name: "Jean",
        last_name: "Mukendi",
        name: "Jean Mukendi",
        jersey_number: 7,
        photo: null,
        membership_status: "active",
        membership_status_label: "Inscrit",
      },
      year: 2026,
      currency: "USD",
      today: "2026-10-07",
      months: [{ period: "2026-01-01", month: 1, label: "janv.", long_label: "janvier 2026" }],
      states: { paid: "Payé", partial: "Partiel", overdue: "Impayé", upcoming: "À venir", free: "Libre", not_due: "Non dû" },
      player_status: {
        balance: "-20.00",
        amount_due: "20.00",
        is_in_good_standing: false,
        reason: "",
        currency: "USD",
      },
      lines: [
        {
          contribution_type: {
            id: 3,
            name: "Mensuelle A",
            nature: "mandatory",
            nature_label: "Obligatoire",
            periodicity: "monthly",
            periodicity_label: "Mensuelle",
            amount: "20.00",
            scope: "all",
            status: "active",
            is_free: false,
          },
          cells: [
            {
              period: "2026-01-01",
              month: 1,
              amount_due: "20.00",
              allocated: "20.00",
              state: "paid",
              state_label: "Payé",
              overdue_amount: "0.00",
            },
          ],
          total: "20.00",
          overdue_amount: "0.00",
          has_unpaid: false,
        },
      ],
    });
    wrap(<MemberSituationModal membershipId={1} onClose={vi.fn()} onPaymentRecorded={vi.fn()} />);

    await userEvent.setup().click(await screen.findByRole("tab", { name: "Grille" }));
    expect(await screen.findByText("janvier 2026")).toBeInTheDocument();
    expect(getMemberGrid).toHaveBeenCalledWith(1, new Date().getFullYear());
  });

  it("affiche une erreur avec « Réessayer » si la situation ne charge pas", async () => {
    vi.mocked(getMemberDetail).mockRejectedValueOnce(new ApiError(500, null));
    wrap(<MemberSituationModal membershipId={1} onClose={vi.fn()} onPaymentRecorded={vi.fn()} />);
    expect(await screen.findByText("Impossible de charger la situation financière.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });
});
