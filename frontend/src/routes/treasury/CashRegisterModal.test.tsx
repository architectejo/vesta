import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import { ELIGIBILITY_QUERY_KEY } from "../sport/useEligibility";
import { CashRegisterFlow, type CashRegisterFlowProps } from "./CashRegisterModal";

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getContributionTypes: vi.fn(),
    getCurrentCashSession: vi.fn(),
    openCashSession: vi.fn(),
    closeCashSession: vi.fn(),
    searchCashSessionPlayers: vi.fn(),
    previewCashPayment: vi.fn(),
    createCashPayment: vi.fn(),
  };
});

import {
  closeCashSession,
  createCashPayment,
  getContributionTypes,
  getCurrentCashSession,
  openCashSession,
  previewCashPayment,
  searchCashSessionPlayers,
} from "../../api/treasury";

const SESSION = {
  id: "session-1",
  status: "open" as const,
  is_open: true,
  opened_at: "2026-09-29T08:00:00Z",
  expires_at: "2026-09-29T23:00:00Z",
  closed_at: null,
  club_timezone: "Africa/Kinshasa",
  payments_count: 0,
  payments_total: "0.00",
  currency: "USD",
};

function renderFlow(onClose = vi.fn(), extra: Partial<CashRegisterFlowProps> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <CashRegisterFlow open currency="USD" onClose={onClose} {...extra} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onClose, invalidateSpy };
}

const JEAN = {
  membership_id: 5,
  first_name: "Jean",
  last_name: "Kabila",
  jersey_number: 7,
  photo: null,
  membership_status: "active",
  membership_status_label: "Inscrit",
  default_contribution_type_id: null,
  balance: "-10.00",
  amount_due: "10.00",
  is_in_good_standing: false,
  reason: "Le joueur est en dette : 10.00 USD à régulariser.",
  currency: "USD",
};

describe("CashRegisterFlow", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("propose d'ouvrir une session de caisse quand aucune n'est en cours", async () => {
    vi.mocked(getCurrentCashSession).mockResolvedValue({ session: null });
    renderFlow();

    expect(await screen.findByRole("dialog", { name: "Ouvrir une session de caisse ?" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/PIN/i)).not.toBeInTheDocument();
    expect(openCashSession).not.toHaveBeenCalled();
  });

  it("ouvre la caisse après une session ouverte avec succès", async () => {
    vi.mocked(getCurrentCashSession).mockResolvedValue({ session: null });
    vi.mocked(openCashSession).mockResolvedValue({ session: SESSION });
    vi.mocked(getContributionTypes).mockResolvedValue([]);
    const user = userEvent.setup();
    renderFlow();

    await screen.findByRole("dialog", { name: "Ouvrir une session de caisse ?" });
    expect(openCashSession).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Ouvrir la session" }));
    expect(openCashSession).toHaveBeenCalledWith();

    // Le toast de succès porte le même texte que le bandeau de la caisse :
    // on cible le bandeau à l'intérieur de la modale pour éviter l'ambiguïté.
    const dialog = await screen.findByRole("dialog", { name: "Caisse Terrain Express" });
    expect(within(dialog).getByText("Session de caisse ouverte jusqu'à minuit.")).toBeInTheDocument();
  });

  it("affiche directement la caisse quand une session est déjà en cours", async () => {
    vi.mocked(getCurrentCashSession).mockResolvedValue({ session: SESSION });
    vi.mocked(getContributionTypes).mockResolvedValue([]);
    renderFlow();

    expect(await screen.findByRole("dialog", { name: "Caisse Terrain Express" })).toBeInTheDocument();
    expect(await screen.findByText("Session de caisse ouverte jusqu'à minuit.")).toBeInTheDocument();
  });

  it("recherche un joueur, affiche l'aperçu puis encaisse sans code PIN", async () => {
    vi.mocked(getCurrentCashSession).mockResolvedValue({ session: SESSION });
    vi.mocked(getContributionTypes).mockResolvedValue([]);
    vi.mocked(searchCashSessionPlayers).mockResolvedValue({
      results: [
        {
          membership_id: 5,
          first_name: "Jean",
          last_name: "Kabila",
          jersey_number: 7,
          photo: null,
          membership_status: "active",
          membership_status_label: "Inscrit",
          default_contribution_type_id: null,
          balance: "-10.00",
          amount_due: "10.00",
          is_in_good_standing: false,
          reason: "Le joueur est en dette : 10.00 USD à régulariser.",
          currency: "USD",
        },
      ],
    });
    vi.mocked(previewCashPayment).mockResolvedValue({
      membership_id: 5,
      contribution_type: { id: 1, name: "Mensuelle" },
      amount: "10.00",
      currency: "USD",
      paid_on: "2026-09-29",
      is_free_type: false,
      allocations: [
        { period: "2026-09-01", amount: "10.00", period_amount: "10.00", covered_after: "10.00", status: "paid" },
      ],
      unallocated_amount: "0.00",
      current: { balance: "-10.00", amount_due: "10.00", is_in_good_standing: false, reason: "", currency: "USD" },
      after: { balance: "0.00", amount_due: "0.00", is_in_good_standing: true, reason: "", currency: "USD" },
    });
    vi.mocked(createCashPayment).mockResolvedValue({
      id: 1,
      membership_id: 5,
      contribution_type: { id: 1, name: "Mensuelle" },
      amount: "10.00",
      currency: "USD",
      method: "cash",
      method_label: "Espèces",
      reference: "",
      paid_on: "2026-09-29",
      source: "field_cash",
      source_label: "Caisse Terrain Express",
      receipt_number: 7,
      receipt_available: true,
      receipt_url: "/r",
      attachment_url: null,
      validated_at: "2026-09-29T10:00:00Z",
      cash_session_id: "session-1",
      client_uuid: "abc",
      client_recorded_at: "2026-09-29T10:00:00Z",
      allocations: [],
      player_status: { balance: "0.00", amount_due: "0.00", is_in_good_standing: true, reason: "", currency: "USD" },
    });

    const user = userEvent.setup();
    const { invalidateSpy } = renderFlow();

    const search = await screen.findByRole("combobox", { name: "Nom ou numéro du joueur" });
    await user.type(search, "Jean");
    const option = await screen.findByRole("option", { name: /Jean Kabila/ });
    await user.click(option);

    expect(await screen.findByText("Solde : -10 USD")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Montant en espèces"), "10");
    await waitFor(() => expect(previewCashPayment).toHaveBeenCalled());
    expect(await screen.findByText("Payé")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Encaisser" }));

    await waitFor(() =>
      expect(createCashPayment).toHaveBeenCalledWith(
        "session-1",
        expect.objectContaining({ membership_id: 5, amount: "10" }),
      ),
    );
    expect(await screen.findByText("Jean est en ordre. Il peut être composé.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Encaisser pour un autre joueur" })).toBeInTheDocument();
    // Régularisation sur place (sport-feuille-de-match.md §4.1) : l'éligibilité
    // de « Composer l'équipe » est relue aussitôt après l'encaissement.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ELIGIBILITY_QUERY_KEY });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["clubs", "players"] });
  });

  it("lien « Encaisser » de la composition : joueur prérempli avec son solde, au niveau 2", async () => {
    vi.mocked(getCurrentCashSession).mockResolvedValue({ session: SESSION });
    vi.mocked(getContributionTypes).mockResolvedValue([]);
    vi.mocked(searchCashSessionPlayers).mockResolvedValue({ results: [JEAN] });
    renderFlow(vi.fn(), {
      level: 2,
      initialPlayer: { id: 5, firstName: "Jean", lastName: "Kabila", number: 7, position: "Milieu", photoUrl: null },
    });

    expect(await screen.findByText("Solde : -10 USD")).toBeInTheDocument();
    const dialog = screen.getByRole("dialog", { name: "Caisse Terrain Express" });
    expect(within(dialog).getAllByText("Jean Kabila").length).toBeGreaterThan(0);
    expect(searchCashSessionPlayers).toHaveBeenCalledWith("session-1", "Kabila");
    expect(within(dialog).getByLabelText("Montant en espèces")).toBeInTheDocument();
  });

  it("ferme la session après confirmation", async () => {
    vi.mocked(getCurrentCashSession).mockResolvedValue({ session: SESSION });
    vi.mocked(getContributionTypes).mockResolvedValue([]);
    vi.mocked(closeCashSession).mockResolvedValue({ session: { ...SESSION, status: "closed", closed_at: "now" } });
    const user = userEvent.setup();
    const { onClose } = renderFlow();

    await screen.findByRole("dialog", { name: "Caisse Terrain Express" });
    await user.click(await screen.findByRole("button", { name: "Fermer la session" }));

    const confirmDialog = await screen.findByRole("dialog", { name: "Fermer la session de caisse ?" });
    await user.click(within(confirmDialog).getByRole("button", { name: "Fermer la session" }));

    await waitFor(() => expect(closeCashSession).toHaveBeenCalledWith("session-1"));
    expect(onClose).toHaveBeenCalled();
  });
});
