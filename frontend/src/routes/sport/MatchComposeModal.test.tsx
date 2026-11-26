import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ClubPlayerListItem } from "../../api/clubs";
import { MatchComposeModal } from "./MatchComposeModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, listClubPlayers: vi.fn() };
});
vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, addToComposition: vi.fn() };
});

import { listClubPlayers } from "../../api/clubs";
import { addToComposition } from "../../api/sport";

function player(id: number, first: string, last: string, unavailable = false): ClubPlayerListItem {
  return {
    membership_id: id,
    first_name: first,
    last_name: last,
    photo: null,
    position: "midfielder",
    position_label: "Milieu",
    position_detail: "",
    jersey_number: id,
    membership_status: "active",
    membership_status_label: "Inscrit",
    roles: [],
    is_unavailable: unavailable,
  };
}

function renderModal() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onSaved = vi.fn();
  render(
    <QueryClientProvider client={queryClient}>
      <MatchComposeModal open matchId={6} existing={[]} onClose={vi.fn()} onSaved={onSaved} />
    </QueryClientProvider>,
  );
  return { onSaved };
}

describe("MatchComposeModal — joueurs non sélectionnables (§4.1 bis, CLAUDE.md règle 5, série 6)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("désactive la case d'un joueur indisponible, l'affiche quand même et le range après les sélectionnables", async () => {
    vi.mocked(listClubPlayers).mockResolvedValue([
      player(28, "Aimé", "Leurre", true),
      player(12, "Kevin", "Proto"),
    ]);
    renderModal();

    const blocked = await screen.findByRole("checkbox", { name: "Sélectionner Aimé Leurre" });
    expect(blocked).toBeDisabled();
    expect(blocked).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText(/Non sélectionnable/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sélectionner Kevin Proto" })).toBeEnabled();

    const boxes = screen.getAllByRole("checkbox");
    expect(boxes[0]).toHaveAccessibleName("Sélectionner Kevin Proto");
    expect(boxes[1]).toHaveAccessibleName("Sélectionner Aimé Leurre");
  });

  it("n'envoie jamais un joueur indisponible au service de composition", async () => {
    vi.mocked(listClubPlayers).mockResolvedValue([player(28, "Aimé", "Leurre", true), player(12, "Kevin", "Proto")]);
    vi.mocked(addToComposition).mockResolvedValue({} as Awaited<ReturnType<typeof addToComposition>>);
    const user = userEvent.setup();
    const { onSaved } = renderModal();

    await user.click(await screen.findByRole("checkbox", { name: "Sélectionner Aimé Leurre" }));
    await user.click(screen.getByRole("checkbox", { name: "Sélectionner Kevin Proto" }));
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(addToComposition).toHaveBeenCalledTimes(1);
    expect(addToComposition).toHaveBeenCalledWith(6, expect.objectContaining({ membership_id: 12 }));
  });

  it("la case à cocher a une zone tactile de 44 px (h-11)", async () => {
    vi.mocked(listClubPlayers).mockResolvedValue([player(12, "Kevin", "Proto")]);
    renderModal();
    const box = await screen.findByRole("checkbox", { name: "Sélectionner Kevin Proto" });
    expect(box.closest("label")?.className).toContain("h-11");
  });
});
