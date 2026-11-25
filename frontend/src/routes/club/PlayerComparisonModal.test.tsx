import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PlayerComparisonModal } from "./PlayerComparisonModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return {
    ...actual,
    getPlayerCard: vi.fn(),
    searchActiveClubPlayers: vi.fn(),
  };
});

import { getPlayerCard, searchActiveClubPlayers } from "../../api/clubs";

const AIME = {
  membership_id: 7,
  first_name: "Aimé",
  last_name: "Kalonji",
  photo: null,
  position: "defender",
  position_label: "Défenseur",
  position_detail: "",
  jersey_number: 4,
  membership_status: "active",
  membership_status_label: "Inscrit",
  joined_on: "2024-03-15",
  roles: [],
};

const JEAN = {
  ...AIME,
  membership_id: 20,
  first_name: "Jean",
  last_name: "Kabila",
  position_label: "Milieu",
  jersey_number: 8,
};

function renderModal() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <PlayerComparisonModal
        initialPlayer={{ id: 7, firstName: "Aimé", lastName: "Kalonji", number: 4, position: "Défenseur" }}
        onClose={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe("PlayerComparisonModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche « Choisissez au moins 2 joueurs à comparer. » avec un seul joueur choisi", async () => {
    vi.mocked(getPlayerCard).mockResolvedValue(AIME);
    renderModal();

    expect(screen.getByText("Choisissez au moins 2 joueurs à comparer.")).toBeInTheDocument();
  });

  it("affiche le tableau et l'état vide du radar dès que 2 joueurs sont choisis", async () => {
    vi.mocked(getPlayerCard).mockImplementation((id: number) => Promise.resolve(id === 7 ? AIME : JEAN));
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 20, firstName: "Jean", lastName: "Kabila", number: 8, position: "Milieu" },
    ]);

    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByRole("combobox"), "Jean");
    const option = await screen.findByRole("option", { name: /Jean Kabila/ });
    await user.click(option);

    await waitFor(() => expect(screen.queryByText("Choisissez au moins 2 joueurs à comparer.")).not.toBeInTheDocument());
    expect(screen.getByText("Pas assez d'attributs pour tracer le radar.")).toBeInTheDocument();
    expect(screen.getAllByText("Note globale").length).toBeGreaterThan(0);
    expect(await screen.findAllByText("Défenseur")).not.toHaveLength(0);
    expect(await screen.findAllByText("Milieu")).not.toHaveLength(0);
  });

  it("bloque un 5e joueur avec l'aide « 4 joueurs au maximum… »", async () => {
    vi.mocked(getPlayerCard).mockResolvedValue(AIME);
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 20, firstName: "Jean", lastName: "Kabila", number: 8, position: "Milieu" },
      { id: 21, firstName: "Marc", lastName: "Ilunga", number: 9, position: "Attaquant" },
      { id: 22, firstName: "Paul", lastName: "Makasi", number: 10, position: "Attaquant" },
    ]);
    const user = userEvent.setup();
    renderModal();

    for (const name of ["Jean", "Marc", "Paul"]) {
      const input = screen.getByRole("combobox");
      await user.clear(input);
      await user.type(input, name);
      const option = await screen.findByRole("option", { name: new RegExp(name) });
      await user.click(option);
    }

    expect(await screen.findByText("4 joueurs au maximum. Retirez-en un pour en ajouter un autre.")).toBeInTheDocument();
  });
});
