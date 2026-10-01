import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { ToastProvider } from "../../design-system";
import { RecordPaymentModal } from "./RecordPaymentModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, searchActiveClubPlayers: vi.fn() };
});

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getContributionTypes: vi.fn(),
    previewPayment: vi.fn(),
    createPayment: vi.fn(),
  };
});

import { searchActiveClubPlayers } from "../../api/clubs";
import { createPayment, getContributionTypes, previewPayment } from "../../api/treasury";

const MONTHLY_TYPE = {
  id: 1,
  name: "Mensuelle catégorie A",
  nature: "mandatory" as const,
  amount: "20.00",
  periodicity: "monthly" as const,
  due_day: 10,
  due_month: null,
  deadline: null,
  is_membership_fee: false,
  scope: "all" as const,
  status: "active" as const,
  archived_at: null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

function renderModal(props: Partial<Parameters<typeof RecordPaymentModal>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  const onRecorded = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RecordPaymentModal open currency="USD" onClose={onClose} onRecorded={onRecorded} {...props} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onClose, onRecorded };
}

async function choosePlayer(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole("combobox", { name: "Nom ou numéro du joueur" }), "Jean");
  const option = await screen.findByRole("option", { name: /Jean Kabila/ });
  await user.click(option);
}

describe("RecordPaymentModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("exige un joueur, un type et un montant avant d'ouvrir le code PIN", async () => {
    vi.mocked(getContributionTypes).mockResolvedValue([MONTHLY_TYPE]);
    const user = userEvent.setup();
    renderModal();

    await screen.findByText("Mensuelle catégorie A", { exact: false });
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(await screen.findByText("Choisissez un joueur.")).toBeInTheDocument();
    expect(screen.getByText("Saisissez un montant supérieur à 0.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Votre code PIN")).not.toBeInTheDocument();
  });

  it("affiche l'aperçu de répartition dès que joueur, type et montant sont remplis", async () => {
    vi.mocked(getContributionTypes).mockResolvedValue([MONTHLY_TYPE]);
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 11, firstName: "Jean", lastName: "Kabila", number: 7 },
    ]);
    vi.mocked(previewPayment).mockResolvedValue({
      membership_id: 11,
      contribution_type: { id: 1, name: "Mensuelle catégorie A" },
      amount: "20.00",
      currency: "USD",
      paid_on: "2026-09-29",
      is_free_type: false,
      allocations: [
        { period: "2026-09-01", amount: "20.00", period_amount: "20.00", covered_after: "20.00", status: "paid" },
      ],
      unallocated_amount: "0.00",
      current: { balance: "-20.00", amount_due: "20.00", is_in_good_standing: false, reason: "", currency: "USD" },
      after: { balance: "0.00", amount_due: "0.00", is_in_good_standing: true, reason: "", currency: "USD" },
    });
    const user = userEvent.setup();
    renderModal();

    await screen.findByText("Mensuelle catégorie A", { exact: false });
    await choosePlayer(user);
    await user.type(screen.getByLabelText("Montant"), "20");

    await waitFor(() => expect(previewPayment).toHaveBeenCalled());
    expect(await screen.findByText("septembre 2026")).toBeInTheDocument();
    expect(screen.getByText("Payé")).toBeInTheDocument();
  });

  it("demande le code PIN puis enregistre le paiement", async () => {
    vi.mocked(getContributionTypes).mockResolvedValue([MONTHLY_TYPE]);
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 11, firstName: "Jean", lastName: "Kabila", number: 7 },
    ]);
    vi.mocked(createPayment).mockResolvedValue({
      id: 1,
      membership_id: 11,
      contribution_type: { id: 1, name: "Mensuelle catégorie A" },
      amount: "20.00",
      currency: "USD",
      method: "cash",
      method_label: "Espèces",
      reference: "",
      paid_on: "2026-09-29",
      source: "treasurer_entry",
      source_label: "Saisie Trésorier",
      receipt_number: 42,
      receipt_available: true,
      receipt_url: "/receipt",
      attachment_url: null,
      validated_at: "2026-09-29T10:00:00Z",
      cash_session_id: null,
      client_uuid: null,
      client_recorded_at: null,
      allocations: [],
      player_status: null,
    });
    const user = userEvent.setup();
    renderModal();

    await screen.findByText("Mensuelle catégorie A", { exact: false });
    await choosePlayer(user);
    await user.type(screen.getByLabelText("Montant"), "20");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    const pinInput = await screen.findByLabelText("Votre code PIN");
    await user.type(pinInput, "1234");
    await user.click(screen.getByRole("button", { name: "Confirmer" }));

    await waitFor(() =>
      expect(createPayment).toHaveBeenCalledWith(
        expect.objectContaining({ membership_id: 11, contribution_type_id: 1, amount: "20", pin: "1234" }),
      ),
    );
    expect(await screen.findByText(/Reçu n° 42 envoyé à Jean/)).toBeInTheDocument();
  });

  it("affiche le nombre d'essais restants sur un code PIN incorrect", async () => {
    vi.mocked(getContributionTypes).mockResolvedValue([MONTHLY_TYPE]);
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 11, firstName: "Jean", lastName: "Kabila", number: 7 },
    ]);
    vi.mocked(createPayment).mockRejectedValue(new ApiError(400, { detail: "Code PIN incorrect.", attempts_remaining: 2 }));
    const user = userEvent.setup();
    renderModal();

    await screen.findByText("Mensuelle catégorie A", { exact: false });
    await choosePlayer(user);
    await user.type(screen.getByLabelText("Montant"), "20");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    const pinInput = await screen.findByLabelText("Votre code PIN");
    await user.type(pinInput, "0000");
    await user.click(screen.getByRole("button", { name: "Confirmer" }));

    expect(await screen.findByText("Code PIN incorrect. Il vous reste 2 essais.")).toBeInTheDocument();
  });

  it("affiche une erreur métier (type archivé) dans le bandeau de la modale", async () => {
    vi.mocked(getContributionTypes).mockResolvedValue([MONTHLY_TYPE]);
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 11, firstName: "Jean", lastName: "Kabila", number: 7 },
    ]);
    vi.mocked(createPayment).mockRejectedValue(new ApiError(400, { detail: "Ce type de cotisation est archivé." }));
    const user = userEvent.setup();
    renderModal();

    await screen.findByText("Mensuelle catégorie A", { exact: false });
    await choosePlayer(user);
    await user.type(screen.getByLabelText("Montant"), "20");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    const pinInput = await screen.findByLabelText("Votre code PIN");
    await user.type(pinInput, "1234");
    await user.click(screen.getByRole("button", { name: "Confirmer" }));

    expect(await screen.findByText("Ce type de cotisation est archivé.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Votre code PIN")).not.toBeInTheDocument();
  });

  it("préremplit le joueur et le type depuis la grille des cotisations, sans marquer la modale comme modifiée", async () => {
    vi.mocked(getContributionTypes).mockResolvedValue([MONTHLY_TYPE]);
    const user = userEvent.setup();
    renderModal({
      initialPlayer: { id: 11, firstName: "Jean", lastName: "Kabila", number: 7 },
      initialContributionTypeId: 1,
    });

    await screen.findByText("Jean Kabila");
    await screen.findByText("Mensuelle catégorie A", { exact: false });

    // Fermer sans rien changer ne doit pas ouvrir la confirmation d'abandon.
    await user.click(screen.getByRole("button", { name: "Annuler" }));
    expect(screen.queryByText("Abandonner les modifications ?")).not.toBeInTheDocument();
  });
});
