import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import type {
  GridCellState,
  GridContributionType,
  GridMonthDetail,
  GridResponse,
  GridTypesResponse,
  TreasuryCapabilities,
} from "../../api/treasury";
import { AuthProvider } from "../../auth/AuthContext";
import { ToastProvider } from "../../design-system";
import { GrilleCotisationsPage } from "./GrilleCotisationsPage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getGridContributionTypes: vi.fn(),
    getFullContributionGrid: vi.fn(),
    getContributionGridPage: vi.fn(),
    getTreasuryCapabilities: vi.fn(),
    downloadContributionGridCsv: vi.fn(),
    getGridMonthDetail: vi.fn(),
  };
});

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return { ...actual, triggerBlobDownload: vi.fn() };
});

import { triggerBlobDownload } from "../../api/client";
import { getMyProfile } from "../../api/clubs";
import {
  downloadContributionGridCsv,
  getFullContributionGrid,
  getGridContributionTypes,
  getGridMonthDetail,
  getTreasuryCapabilities,
} from "../../api/treasury";

const ACCESS_DENIED = "Vous n'avez pas accès à la grille des cotisations.";

function makeProfile(...roles: string[]): MyProfile {
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
    roles: roles.map((role) => ({ role, label: role })),
    email_notifications_enabled: true,
  };
}

const DEFAULT_TYPE: GridContributionType = {
  id: 1,
  name: "Mensuelle catégorie A",
  nature: "mandatory",
  nature_label: "Obligatoire",
  periodicity: "monthly",
  periodicity_label: "Mensuelle",
  amount: "20.00",
  scope: "all",
  status: "active",
  is_free: false,
};

function makeTypesResponse(overrides: Partial<GridTypesResponse> = {}): GridTypesResponse {
  return {
    currency: "USD",
    default_type_id: 1,
    active: [DEFAULT_TYPE],
    archived: [],
    ...overrides,
  };
}

const MONTH_LABELS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."] as const;

function makeMonths(): GridResponse["months"] {
  return MONTH_LABELS.map((label, i) => ({
    period: `2026-${String(i + 1).padStart(2, "0")}-01`,
    month: i + 1,
    label,
    long_label: `mois ${i + 1}`,
  }));
}

function makeGrid(overrides: Partial<GridResponse> = {}): GridResponse {
  return {
    contribution_type: DEFAULT_TYPE,
    year: 2026,
    currency: "USD",
    today: "2026-09-29",
    months: makeMonths(),
    states: { paid: "Payé", partial: "Partiel", overdue: "Impayé échu", upcoming: "À venir", free: "Libre", not_due: "Non dû" },
    rows_total: 1,
    count: 1,
    limit: 100,
    offset: 0,
    next_offset: null,
    results: [
      {
        membership_id: 11,
        first_name: "Jean",
        last_name: "Kabila",
        name: "Jean Kabila",
        jersey_number: 7,
        photo: null,
        membership_status: "active",
        membership_status_label: "Inscrit",
        cells: Array.from({ length: 12 }, (_, i) => {
          const state: GridCellState = i === 8 ? "paid" : i < 8 ? "overdue" : "upcoming";
          return {
            period: `2026-${String(i + 1).padStart(2, "0")}-01`,
            month: i + 1,
            amount_due: "20.00",
            allocated: i === 8 ? "20.00" : "0.00",
            state,
            state_label: i === 8 ? "Payé" : i < 8 ? "Impayé échu" : "À venir",
            overdue_amount: "0.00",
          };
        }),
        total: "20.00",
        overdue_amount: "160.00",
        has_unpaid: true,
        player_status: { balance: "-160.00", amount_due: "160.00", is_in_good_standing: false, reason: "En dette : 160.00 USD.", currency: "USD" },
      },
    ],
    ...overrides,
  };
}

function makeCapabilities(overrides: Partial<TreasuryCapabilities> = {}): { currency: string; capabilities: TreasuryCapabilities } {
  return {
    currency: "USD",
    capabilities: {
      can_read: true,
      can_write: false,
      can_record_payments: true,
      can_read_expenses: false,
      can_manage_expense_categories: false,
      can_submit_expenses: false,
      can_validate_expenses: false,
      can_derogate: false,
      can_upload_expense_receipts: false,
      can_manage_assistance_scales: false,
      can_process_assistance_requests: false,
      can_request_assistance: true,
      ...overrides,
    },
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AuthProvider>
          <ToastProvider>
            <GrilleCotisationsPage />
          </ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("GrilleCotisationsPage", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it("refuse l'accès à un rôle non autorisé, seulement après le chargement du profil", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    renderPage();

    expect(screen.queryByText(ACCESS_DENIED)).not.toBeInTheDocument();
    expect(await screen.findByText(ACCESS_DENIED)).toBeInTheDocument();
    expect(getGridContributionTypes).not.toHaveBeenCalled();
  });

  it("accorde la lecture au Vice-président (défaut appliqué, matrice 2.4 — point ouvert de la fiche §7)", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("vice_president"));
    vi.mocked(getGridContributionTypes).mockResolvedValue(makeTypesResponse());
    vi.mocked(getFullContributionGrid).mockResolvedValue(makeGrid());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities({ can_record_payments: false }));

    renderPage();

    expect(await screen.findByRole("heading", { name: "Grille des cotisations" })).toBeInTheDocument();
    expect(screen.queryByText(ACCESS_DENIED)).not.toBeInTheDocument();
  });

  it("affiche l'état vide « Aucun type de cotisation » avec l'action réservée au Président/Trésorier", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("vice_president"));
    vi.mocked(getGridContributionTypes).mockResolvedValue(makeTypesResponse({ active: [] }));
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());

    renderPage();

    expect(await screen.findByText("Aucun type de cotisation.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aller à la trésorerie" })).not.toBeInTheDocument();
  });

  it("affiche la grille avec les cellules colorées et le total, et ouvre le détail du mois au clic", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
    vi.mocked(getGridContributionTypes).mockResolvedValue(makeTypesResponse());
    vi.mocked(getFullContributionGrid).mockResolvedValue(makeGrid());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());
    vi.mocked(getGridMonthDetail).mockResolvedValue({
      contribution_type: DEFAULT_TYPE,
      player: { membership_id: 11, first_name: "Jean", last_name: "Kabila", name: "Jean Kabila", jersey_number: 7, photo: null, membership_status: "active", membership_status_label: "Inscrit" },
      currency: "USD",
      period: "2026-09-01",
      period_label: "septembre 2026",
      cell: { period: "2026-09-01", month: 9, amount_due: "20.00", allocated: "20.00", state: "paid", state_label: "Payé", overdue_amount: "0.00" },
      payments: [],
      can_record_payment: true,
    } satisfies GridMonthDetail);

    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("heading", { name: "Grille des cotisations" })).toBeInTheDocument();
    const septemberCell = await screen.findByRole("button", { name: /septembre|mois 9.*Payé/ });
    await user.click(septemberCell);

    expect(await screen.findByRole("heading", { name: "septembre 2026 — Jean Kabila" })).toBeInTheDocument();
    expect(getGridMonthDetail).toHaveBeenCalledWith(1, 2026, 11, 9);
  });

  it("filtre la grille par la recherche locale et propose d'effacer la recherche sans résultat", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
    vi.mocked(getGridContributionTypes).mockResolvedValue(makeTypesResponse());
    vi.mocked(getFullContributionGrid).mockResolvedValue(makeGrid());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Jean Kabila", { exact: false });
    await user.type(screen.getByLabelText("Rechercher un joueur"), "Zzzz");

    expect(await screen.findByText("Aucun joueur ne correspond à « Zzzz ».")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Effacer la recherche" }));
    expect(await screen.findByText("Jean Kabila", { exact: false })).toBeInTheDocument();
  });

  it("exporte la grille en CSV et affiche un toast de confirmation", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
    vi.mocked(getGridContributionTypes).mockResolvedValue(makeTypesResponse());
    vi.mocked(getFullContributionGrid).mockResolvedValue(makeGrid());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());
    vi.mocked(downloadContributionGridCsv).mockResolvedValue({
      blob: new Blob(["a,b"], { type: "text/csv" }),
      filename: "grille-mensuelle-categorie-a-2026.csv",
    });

    const user = userEvent.setup();
    renderPage();

    await screen.findByRole("heading", { name: "Grille des cotisations" });
    await user.click(screen.getByRole("button", { name: "Exporter (CSV)" }));

    expect(await screen.findByText("Export téléchargé.")).toBeInTheDocument();
    expect(downloadContributionGridCsv).toHaveBeenCalledWith(1, 2026);
    expect(triggerBlobDownload).toHaveBeenCalledWith(expect.any(Blob), "grille-mensuelle-categorie-a-2026.csv");
  });
});
