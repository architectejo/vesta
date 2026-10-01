import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import type { MatchDetail, MatchListItem, LockerRoom } from "../../api/sport";
import type { ContributeInfo, ExpenseSummary, MyBalance, TreasuryCapabilitiesResponse } from "../../api/treasury";
import { ToastProvider } from "../../design-system";
import { AccueilPage } from "./AccueilPage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});
vi.mock("../../api/social", async () => {
  const actual = await vi.importActual<typeof import("../../api/social")>("../../api/social");
  return { ...actual, listAnnouncements: vi.fn() };
});
vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return {
    ...actual,
    getLockerRoom: vi.fn(),
    listSuspensions: vi.fn(),
    listMatches: vi.fn(),
    getMatch: vi.fn(),
  };
});
vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getMyBalance: vi.fn(),
    getContributeInfo: vi.fn(),
    getExpenseSummary: vi.fn(),
    getTreasuryCapabilities: vi.fn(),
  };
});

import { getMyProfile } from "../../api/clubs";
import { listAnnouncements } from "../../api/social";
import { getLockerRoom, getMatch, listMatches, listSuspensions } from "../../api/sport";
import { getContributeInfo, getExpenseSummary, getMyBalance, getTreasuryCapabilities } from "../../api/treasury";

function makeProfile(roles: Array<{ role: string; label: string }> = []): MyProfile {
  return {
    membership_id: 42,
    club: { id: 1, slug: "test", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    identity: {
      first_name: "Jean",
      last_name: "Membre",
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
    roles,
    email_notifications_enabled: true,
  };
}

const emptyLockerRoom: LockerRoom = { session: null, match: null, my_situation: null };

const defaultCapabilities: TreasuryCapabilitiesResponse = {
  currency: "USD",
  capabilities: {
    can_read: true,
    can_write: false,
    can_record_payments: false,
    can_read_expenses: false,
    can_manage_expense_categories: false,
    can_submit_expenses: false,
    can_validate_expenses: false,
    can_derogate: false,
    can_upload_expense_receipts: false,
    can_manage_assistance_scales: false,
    can_process_assistance_requests: false,
    can_request_assistance: false,
  },
};

const defaultExpenseSummary: ExpenseSummary = {
  can_release: true,
  reason: "",
  blocking_expense_ids: [],
  available_cash: "0.00",
  currency: "USD",
};

const defaultBalance: MyBalance = {
  membership_id: 42,
  club_id: 1,
  balance: "0.00",
  amount_due: "0.00",
  is_in_good_standing: true,
  reason: "Le joueur est en ordre.",
  currency: "USD",
};

const defaultContribute: ContributeInfo = {
  payment_link_configured: false,
  payment_link_url: null,
  currency: "USD",
  contribution_types: [],
  default_contribution_type_id: null,
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter>
          <AccueilPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("AccueilPage", () => {
  beforeEach(() => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getLockerRoom).mockResolvedValue(emptyLockerRoom);
    vi.mocked(listSuspensions).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(getMyBalance).mockResolvedValue(defaultBalance);
    vi.mocked(getContributeInfo).mockResolvedValue(defaultContribute);
    vi.mocked(getExpenseSummary).mockResolvedValue(defaultExpenseSummary);
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(defaultCapabilities);
    vi.mocked(listAnnouncements).mockResolvedValue({ results: [], count: 0, next_offset: null });
    vi.mocked(listMatches).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(getMatch).mockResolvedValue({} as MatchDetail);
  });

  it("affiche le prénom et le club une fois le profil chargé", async () => {
    renderPage();
    expect(await screen.findByText("Bonjour, Jean")).toBeInTheDocument();
    expect(screen.getByText(/Club de test/)).toBeInTheDocument();
  });

  it("affiche l'état vide des communiqués sans bouton de publication pour un simple joueur", async () => {
    renderPage();
    expect(await screen.findByText("Aucun communiqué pour l'instant.")).toBeInTheDocument();
    expect(screen.queryByText("Publier un communiqué")).not.toBeInTheDocument();
  });

  it("propose « Publier un communiqué » au Président", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile([{ role: "president", label: "Président" }]));
    renderPage();
    await screen.findByText("Bonjour, Jean");
    expect(await screen.findAllByText("Publier un communiqué")).not.toHaveLength(0);
  });

  it("masque la carte « Vestiaire du jour » s'il n'y a rien aujourd'hui", async () => {
    renderPage();
    await screen.findByText("Bonjour, Jean");
    await waitFor(() => expect(screen.queryByText("Vestiaire du jour")).not.toBeInTheDocument());
  });

  it("affiche toujours une valeur dans « Ma situation », jamais un état vide", async () => {
    renderPage();
    expect(await screen.findByText("Ma situation")).toBeInTheDocument();
    expect(await screen.findByText(/Solde : 0.00 USD/)).toBeInTheDocument();
    expect(await screen.findByText("Le joueur est en ordre.")).toBeInTheDocument();
  });

  it("masque le bouton « Contribuer » si le club n'a pas configuré de lien de paiement", async () => {
    renderPage();
    await screen.findByText(/Solde : 0.00 USD/);
    expect(screen.queryByText("Contribuer")).not.toBeInTheDocument();
  });

  it("affiche le bouton « Contribuer » si un lien de paiement est configuré", async () => {
    vi.mocked(getContributeInfo).mockResolvedValue({
      ...defaultContribute,
      payment_link_configured: true,
      payment_link_url: "https://pay.example.com/club",
    });
    renderPage();
    expect(await screen.findByText("Contribuer")).toBeInTheDocument();
  });

  it("affiche l'état vide du prochain rendez-vous quand rien n'est prévu aujourd'hui", async () => {
    renderPage();
    expect(await screen.findByText("Aucune séance ni aucun match prévu aujourd'hui.")).toBeInTheDocument();
  });

  it("affiche l'état vide des derniers résultats quand aucun match n'est joué", async () => {
    renderPage();
    const section = (await screen.findByText("Derniers résultats")).closest("section");
    expect(section).not.toBeNull();
    expect(
      await within(section as HTMLElement).findByText("Aucun match joué pour l'instant."),
    ).toBeInTheDocument();
  });

  it("affiche un résultat de match joué avec son issue en texte simple", async () => {
    const listItem: MatchListItem = {
      id: 7,
      event_date: "2026-09-20",
      kickoff_time: "15:00:00",
      opponent: "FC Rivaux",
      match_type: "friendly",
      venue: "home",
      is_composition_published: true,
      is_locked: true,
    };
    vi.mocked(listMatches).mockResolvedValue({ count: 1, next_offset: null, results: [listItem] });
    vi.mocked(getMatch).mockResolvedValue({
      id: 7,
      kind: "match",
      event_date: "2026-09-20",
      season_id: null,
      is_locked: true,
      unlocked_by: null,
      unlocked_at: null,
      unlock_reason: "",
      kickoff_time: "15:00:00",
      opponent: "FC Rivaux",
      match_type: "friendly",
      venue: "home",
      location: "",
      challenge_status: "n_a",
      is_composition_published: true,
      composition_published_at: null,
      attendances: [],
      attendance_counts: { present: 0, late: 0, excused: 0, not_marked: 0 },
      starters: [],
      substitutes: [],
      sheet: { score_home: 3, score_away: 1, filled_at: "2026-09-20T17:00:00Z", goals: [] },
    } as MatchDetail);

    renderPage();
    expect(await screen.findByText(/vs FC Rivaux/)).toBeInTheDocument();
    expect(await screen.findByText(/Victoire 3-1/)).toBeInTheDocument();
  });

  it("affiche la bannière de dépense non justifiée pour un Trésorier", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile([{ role: "treasurer", label: "Trésorier" }]));
    vi.mocked(getTreasuryCapabilities).mockResolvedValue({
      ...defaultCapabilities,
      capabilities: { ...defaultCapabilities.capabilities, can_read_expenses: true },
    });
    vi.mocked(getExpenseSummary).mockResolvedValue({
      can_release: false,
      reason: "Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée.",
      blocking_expense_ids: [99],
      available_cash: "0.00",
      currency: "USD",
    });
    renderPage();
    expect(
      await screen.findByText("Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée."),
    ).toBeInTheDocument();
    expect(screen.getByText("Voir la dépense")).toBeInTheDocument();
  });

  it("ne montre pas la bannière de dépense à un simple joueur", async () => {
    vi.mocked(getExpenseSummary).mockResolvedValue({
      can_release: false,
      reason: "Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée.",
      blocking_expense_ids: [99],
      available_cash: "0.00",
      currency: "USD",
    });
    renderPage();
    await screen.findByText("Bonjour, Jean");
    expect(
      screen.queryByText("Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée."),
    ).not.toBeInTheDocument();
  });
});
