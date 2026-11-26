import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RecordMovementModal } from "./RecordMovementModal";
import { makeArticle, makeHolder, makeHolderList, makeMovement, renderWithProviders } from "./testFixtures";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return {
    ...actual,
    getMyProfile: vi.fn(),
    searchActiveClubPlayers: vi.fn().mockResolvedValue([]),
    listClubPlayers: vi.fn().mockResolvedValue([]),
  };
});
vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return { ...actual, getExpenses: vi.fn() };
});
vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return {
    ...actual,
    recordMovement: vi.fn(),
    listHolders: vi.fn(),
    searchLinkableExpenses: vi.fn(),
  };
});

import { getExpenses } from "../../api/treasury";
import { listHolders, recordMovement, searchLinkableExpenses } from "../../api/logistics";

const article = makeArticle();

function renderModal() {
  return renderWithProviders(<RecordMovementModal open lockedArticle={article} onClose={() => {}} onSaved={() => {}} />);
}

async function fillCommon(user: ReturnType<typeof userEvent.setup>, sense: "Entrée" | "Sortie", type: string) {
  await user.click(screen.getByRole("button", { name: sense }));
  await user.click(screen.getByRole("button", { name: type }));
  await user.type(screen.getByRole("spinbutton", { name: "Quantité" }), "2");
}

function submit(user: ReturnType<typeof userEvent.setup>) {
  return user.click(screen.getByRole("button", { name: "Enregistrer le mouvement" }));
}

describe("RecordMovementModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(recordMovement).mockResolvedValue({ movement: makeMovement(1), in_stock: 14 });
    vi.mocked(listHolders).mockResolvedValue(makeHolderList([makeHolder()]));
    vi.mocked(searchLinkableExpenses).mockResolvedValue([
      {
        id: 9,
        reference: "D-9",
        expense_date: "2026-10-02",
        amount: "40.00",
        currency: "USD",
        category: "Équipement",
        status: "released",
        status_display: "Libérée",
      },
    ]);
  });

  it("dépense liée : passe par logistics/expenses/linkable/, jamais par treasury/expenses/", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(screen.getByRole("button", { name: "Achat" }));
    expect(screen.queryByText(/nécessite un accès aux dépenses/)).not.toBeInTheDocument();
    await user.type(screen.getByRole("combobox", { name: "Rechercher une dépense" }), "40");
    expect(await screen.findByText(/D-9 · 02\/10\/2026 · Équipement · 40.00 USD/)).toBeInTheDocument();
    expect(searchLinkableExpenses).toHaveBeenCalledWith("40");
    expect(getExpenses).not.toHaveBeenCalled();
  });

  it("entrée sans détenteur ni provenance : holder_id omis et provenance null", async () => {
    const user = userEvent.setup();
    renderModal();
    await fillCommon(user, "Entrée", "Achat");
    expect(screen.getByText(/Provenance :/)).toHaveTextContent("Provenance : non renseignée · Modifier");
    await submit(user);
    await waitFor(() => expect(recordMovement).toHaveBeenCalled());
    const payload = vi.mocked(recordMovement).mock.calls[0]![0];
    expect(payload).not.toHaveProperty("holder_id");
    expect(payload.provenance).toBeNull();
    expect(payload.movement_type).toBe("in_purchase");
  });

  it("achat avec origine « Frais de l'équipe » : provenance envoyée", async () => {
    const user = userEvent.setup();
    renderModal();
    await fillCommon(user, "Entrée", "Achat");
    await user.click(screen.getByRole("button", { name: "Modifier" }));
    await user.click(screen.getByRole("button", { name: "Frais de l'équipe" }));
    await submit(user);
    await waitFor(() => expect(recordMovement).toHaveBeenCalled());
    expect(vi.mocked(recordMovement).mock.calls[0]![0].provenance).toEqual({
      origin_kind: "club_funds",
      condition_at_entry: "unknown",
    });
  });

  it("reprise du registre : bloc déplié, aide affichée, date inconnue avec précision", async () => {
    const user = userEvent.setup();
    renderModal();
    await fillCommon(user, "Entrée", "Reprise du registre");
    expect(screen.getByText("Pour le matériel que le club possédait avant d'utiliser Vesta.")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Date inconnue" }));
    await user.type(screen.getByLabelText(/Précision sur la date/), "comité 2019");
    await submit(user);
    await waitFor(() => expect(recordMovement).toHaveBeenCalled());
    expect(vi.mocked(recordMovement).mock.calls[0]![0].provenance).toEqual({
      origin_kind: "unknown",
      condition_at_entry: "unknown",
      acquisition_date_unknown: true,
      acquisition_date_note: "comité 2019",
    });
  });

  it("dotation : « Don » d'office, donateur obligatoire, nom libre hors club envoyé dans donor_name", async () => {
    const user = userEvent.setup();
    renderModal();
    await fillCommon(user, "Entrée", "Dotation");
    await submit(user);
    expect(await screen.findByText("Indiquez le donateur.")).toBeInTheDocument();
    expect(recordMovement).not.toHaveBeenCalled();
    await user.type(screen.getByRole("combobox", { name: "Donateur" }), "Papa Wemba");
    await user.click(await screen.findByText("Utiliser « Papa Wemba » (hors club)"));
    await submit(user);
    await waitFor(() => expect(recordMovement).toHaveBeenCalled());
    const provenance = vi.mocked(recordMovement).mock.calls[0]![0].provenance;
    expect(provenance).toMatchObject({ origin_kind: "donation", donor_name: "Papa Wemba" });
    expect(provenance).not.toHaveProperty("donor_membership_id");
  });

  it("sortie : « D'où sort le matériel ? » prérempli avec le détenteur suggéré", async () => {
    const user = userEvent.setup();
    renderModal();
    await fillCommon(user, "Sortie", "Distribution");
    const group = screen.getByRole("radiogroup", { name: "D'où sort le matériel ?" });
    expect(within(group).getByRole("radio", { name: /Local du club/ })).toHaveAttribute("aria-checked", "true");
    await submit(user);
    await waitFor(() => expect(recordMovement).toHaveBeenCalled());
    expect(vi.mocked(recordMovement).mock.calls[0]![0]).toMatchObject({ holder_id: 1, movement_type: "out_distribution" });
    expect(vi.mocked(recordMovement).mock.calls[0]![0]).not.toHaveProperty("provenance");
  });

  it("sortie depuis « Non localisé » : holder_id null", async () => {
    const user = userEvent.setup();
    renderModal();
    await fillCommon(user, "Sortie", "Perte");
    await user.click(screen.getByRole("radio", { name: /Non localisé/ }));
    await submit(user);
    await waitFor(() => expect(recordMovement).toHaveBeenCalled());
    expect(vi.mocked(recordMovement).mock.calls[0]![0].holder_id).toBeNull();
  });

  it("sortie d'un article sans détenteur : champ « Chez » masqué", async () => {
    const user = userEvent.setup();
    const bare = makeArticle({ stock_by_holder: [], suggested_holder: null });
    renderWithProviders(<RecordMovementModal open lockedArticle={bare} onClose={() => {}} onSaved={() => {}} />);
    await fillCommon(user, "Sortie", "Usure");
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
  });

  it("affiche sous le bon champ l'erreur renvoyée par l'API", async () => {
    vi.mocked(recordMovement).mockRejectedValue(
      new (await import("../../api/client")).ApiError(400, {
        detail: "La date d'acquisition ne peut pas être postérieure à la date d'enregistrement.",
      }),
    );
    const user = userEvent.setup();
    renderModal();
    await fillCommon(user, "Entrée", "Achat");
    await submit(user);
    expect(
      await screen.findByText("La date d'acquisition ne peut pas être postérieure à la date d'enregistrement."),
    ).toBeInTheDocument();
  });
});

describe("RecordMovementModal — mise en page à 320 px", () => {
  it("lets the provenance fieldset shrink to the modal width (no min-content overflow)", async () => {
    // Un <fieldset> a `min-width: min-content` par défaut : à 320 px, le bloc
    // « Provenance » débordait de la modale et était rogné à droite (relevé
    // Playwright `e2e/12-intendance.spec.ts`, capture 06-…-320).
    vi.mocked(listHolders).mockResolvedValue(makeHolderList([makeHolder()]));
    const user = userEvent.setup();
    renderModal();
    await user.click(screen.getByRole("button", { name: "Entrée" }));
    await user.click(screen.getByRole("button", { name: "Dotation" }));
    const legend = await screen.findByText("Provenance", { selector: "legend" });
    expect(legend.closest("fieldset")).toHaveClass("min-w-0");
  });
});
