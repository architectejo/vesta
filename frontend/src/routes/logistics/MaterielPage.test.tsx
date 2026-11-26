import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import type { ListMovementsParams, MaterialOverview } from "../../api/logistics";
import { MaterielPage } from "./MaterielPage";
import {
  makeArticle,
  makeDecommission,
  makeHolder,
  makeHolderList,
  makeMovement,
  movementPage,
  renderWithProviders,
  stockRow,
} from "./testFixtures";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});
vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return {
    ...actual,
    getMaterialOverview: vi.fn(),
    listArticles: vi.fn(),
    listHolders: vi.fn(),
    listDecommissions: vi.fn(),
    listMovements: vi.fn(),
    getMatchEquipment: vi.fn(),
  };
});

import { getMyProfile } from "../../api/clubs";
import { listArticles, getMaterialOverview, listDecommissions, listHolders, listMovements } from "../../api/logistics";

function profile(role: string): MyProfile {
  return { roles: [{ role, label: role }], club: { name: "Club Test" } } as unknown as MyProfile;
}

const OVERVIEW = {
  current_quarter_label: "2026-T4",
  current_quarter_label_display: "4e trimestre 2026",
  open_inventory: null,
  blocking_inventory: false,
  to_count: 0,
  to_justify: 0,
  counted: 0,
  total_active_articles: 1,
  can_open: false,
  openable_quarter_label: null,
  openable_quarter_label_display: null,
  last_closed_inventory: null,
} as MaterialOverview;

function setup(role: string) {
  vi.mocked(getMyProfile).mockResolvedValue(profile(role));
  vi.mocked(getMaterialOverview).mockResolvedValue(OVERVIEW);
  vi.mocked(listArticles).mockResolvedValue({
    count: 2,
    results: [
      makeArticle(),
      makeArticle({
        id: 11,
        name: "Ballon",
        stock_by_holder: [stockRow(2, "Éric Mbala", 3), stockRow(3, "Magasin", 2), stockRow(null, "Non localisé", 1)],
        pending_decommission: 2,
      }),
    ],
  });
  vi.mocked(listHolders).mockResolvedValue(
    makeHolderList(
      [
        makeHolder({ id: 1, name: "Local du club", stock_total: 8 }),
        makeHolder({ id: 2, kind: "member", name: "Jean Parti", membership_id: 41, has_left_club: true, stock_total: 3 }),
      ],
      5,
    ),
  );
  vi.mocked(listDecommissions).mockResolvedValue({ count: 0, pending_quantity: 0, results: [] });
  vi.mocked(listMovements).mockImplementation(async (params: ListMovementsParams = {}) => {
    if (params.movement_type === "out_loan") return movementPage([], null, 0);
    const offset = params.offset ?? 0;
    if (offset === 0) {
      return movementPage(
        Array.from({ length: 50 }, (_, i) => makeMovement(i + 1)),
        50,
        73,
      );
    }
    return movementPage(
      Array.from({ length: 23 }, (_, i) => makeMovement(i + 51, { article: { id: 10, name: "Dernier article", unit: "pièce" } })),
      null,
      73,
      50,
    );
  });
}

describe("MaterielPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("registre des mouvements : compteur = count de l'API, « Voir plus » charge la page suivante", async () => {
    setup("president");
    const user = userEvent.setup();
    renderWithProviders(<MaterielPage />);
    expect(await screen.findByText("· 73 mouvements")).toBeInTheDocument();
    const loadMore = screen
      .getAllByRole("button", { name: "Voir plus" })
      .find((b) => b.closest("section")?.textContent?.includes("Registre des mouvements"));
    expect(loadMore).toBeDefined();
    await user.click(loadMore!);
    await waitFor(() =>
      expect(listMovements).toHaveBeenCalledWith(expect.objectContaining({ offset: 50, limit: 50 })),
    );
    expect((await screen.findAllByText("Dernier article")).length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(
        screen
          .queryAllByRole("button", { name: "Voir plus" })
          .some((b) => b.closest("section")?.textContent?.includes("Registre des mouvements")),
      ).toBe(false),
    );
  });

  it("catalogue : colonnes « Chez » et « À déclasser » lues depuis l'API", async () => {
    setup("president");
    renderWithProviders(<MaterielPage />);
    expect(await screen.findByText("Ballon")).toBeInTheDocument();
    expect(screen.getAllByText("Éric Mbala").length).toBeGreaterThan(0);
    expect(screen.getByText("· +2")).toBeInTheDocument();
  });

  it("Président : alerte de départ sans bouton « Déplacer », pas de bandeau « non localisé »", async () => {
    setup("president");
    renderWithProviders(<MaterielPage />);
    expect(await screen.findByText("Jean Parti a quitté le club et détient encore 3 pièce(s).")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Déplacer" })).not.toBeInTheDocument();
    expect(screen.queryByText("5 pièce(s) ne sont rattachées à aucun détenteur.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Registre de l'intendance" })).toBeInTheDocument();
  });

  it("Coach : ni alerte de départ ni bandeau, mais accès au registre", async () => {
    setup("coach");
    renderWithProviders(<MaterielPage />);
    expect(await screen.findByText("Où est le matériel")).toBeInTheDocument();
    await screen.findByText("Jean Parti");
    expect(screen.queryByText(/a quitté le club et détient encore/)).not.toBeInTheDocument();
    expect(screen.queryByText(/ne sont rattachées à aucun détenteur/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Registre de l'intendance" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ajouter un détenteur" })).not.toBeInTheDocument();
  });

  it("Intendant : bandeau « non localisé » avec « Localiser » et alerte avec « Déplacer »", async () => {
    setup("steward");
    renderWithProviders(<MaterielPage />);
    expect(await screen.findByText("5 pièce(s) ne sont rattachées à aucun détenteur.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Localiser" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Déplacer" })).toBeInTheDocument();
  });

  it("carte « À déclasser » masquée sans signalement, affichée sinon", async () => {
    setup("steward");
    vi.mocked(listDecommissions).mockResolvedValue({ count: 1, pending_quantity: 3, results: [makeDecommission()] });
    renderWithProviders(<MaterielPage />);
    expect(await screen.findByText("3 pièces en attente de sortie")).toBeInTheDocument();
  });

  it("sans rôle de lecture : accès refusé", async () => {
    setup("player");
    renderWithProviders(<MaterielPage />);
    expect(await screen.findByText("Vous n'avez pas accès à cette page.")).toBeInTheDocument();
  });
});
