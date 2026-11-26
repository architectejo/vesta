import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { ClubPlayerListItem } from "../../api/clubs";
import type { HolderDetail } from "../../api/logistics";
import { HolderDetailModal } from "./HolderDetailModal";
import { HolderFormModal } from "./HolderFormModal";
import { makeHolder, makeHolderList, makeMovement, renderWithProviders } from "./testFixtures";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, listClubPlayers: vi.fn() };
});
vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return {
    ...actual,
    listHolders: vi.fn(),
    createHolder: vi.fn(),
    getHolder: vi.fn(),
    archiveHolder: vi.fn(),
    renameHolder: vi.fn(),
  };
});

import { listClubPlayers } from "../../api/clubs";
import { archiveHolder, createHolder, getHolder, listHolders, renameHolder } from "../../api/logistics";

function player(id: number, first: string, last: string, status: ClubPlayerListItem["membership_status"]) {
  return {
    membership_id: id,
    first_name: first,
    last_name: last,
    photo: null,
    position: "midfielder",
    position_label: "Milieu",
    position_detail: "",
    jersey_number: null,
    membership_status: status,
    membership_status_label: "",
    roles: [],
  } as unknown as ClubPlayerListItem;
}

describe("HolderFormModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listHolders).mockResolvedValue(
      makeHolderList([makeHolder({ id: 5, kind: "member", name: "Éric Mbala", membership_id: 40 })]),
    );
    vi.mocked(listClubPlayers).mockResolvedValue([
      player(40, "Éric", "Mbala", "active"),
      player(41, "Paul", "Mbuyi", "pending"),
      player(42, "Marc", "Parti", "departed"),
    ]);
  });

  it("propose actifs et en attente, grise « Déjà détenteur », jamais les partis", async () => {
    const user = userEvent.setup();
    renderWithProviders(<HolderFormModal open onClose={() => {}} onCreated={() => {}} />);
    await waitFor(() => expect(listHolders).toHaveBeenCalledWith(true));
    await user.type(screen.getByRole("combobox"), "Mb");
    expect(await screen.findByText("Déjà détenteur")).toBeInTheDocument();
    expect(screen.getByText(/Paul Mbuyi|Mbuyi Paul/)).toBeInTheDocument();
    expect(screen.queryByText(/Parti/)).not.toBeInTheDocument();
  });

  it("lieu : nom obligatoire puis création avec label", async () => {
    vi.mocked(createHolder).mockResolvedValue(makeHolder({ id: 9, name: "Magasin" }));
    const onCreated = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<HolderFormModal open onClose={() => {}} onCreated={onCreated} />);
    await user.click(screen.getByRole("button", { name: "Un lieu" }));
    await user.click(screen.getByRole("button", { name: "Ajouter" }));
    expect(await screen.findByText("Ce champ est obligatoire.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: /Nom du lieu/ }), "Magasin");
    await user.click(screen.getByRole("button", { name: "Ajouter" }));
    await waitFor(() => expect(createHolder).toHaveBeenCalledWith({ kind: "place", label: "Magasin" }));
    expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: 9 }));
  });

  it("reserves stable room for player suggestions in the bottom sheet until a player is chosen", async () => {
    // À 360 px, la feuille `sm` était trop courte : la liste des suggestions
    // passait sous le pied « Annuler / Ajouter » (e2e 12-intendance, 11b).
    // La réserve ne varie pas au focus ni pendant la saisie (pas de saut).
    const user = userEvent.setup();
    renderWithProviders(<HolderFormModal open onClose={() => {}} onCreated={() => {}} />);
    expect(screen.getByTestId("holder-player-field")).toHaveClass("pb-72");
    await user.type(screen.getByRole("combobox"), "Mb");
    expect(screen.getByTestId("holder-player-field")).toHaveClass("pb-72");
    await user.click(await screen.findByText(/Paul Mbuyi|Mbuyi Paul/));
    expect(screen.getByTestId("holder-player-field")).not.toHaveClass("pb-72");
  });
});

function detail(over: Partial<HolderDetail> = {}): HolderDetail {
  return {
    ...makeHolder({ id: 1, name: "Local du club", stock_total: 8 }),
    articles: [
      {
        article_id: 10,
        name: "Maillot domicile",
        category: "jersey",
        category_display: "Maillots",
        unit: "pièce",
        quantity: 8,
        pending_decommission: 2,
      },
    ],
    recent_movements: [makeMovement(1)],
    ...over,
  };
}

describe("HolderDetailModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getHolder).mockResolvedValue(detail());
  });

  it("lecteur : matériel détenu, mouvements, ni menu ni déplacement", async () => {
    renderWithProviders(
      <HolderDetailModal holderId={1} canManage={false} onClose={() => {}} onChanged={() => {}} onShowAllMovements={() => {}} />,
    );
    expect(await screen.findByText("Maillot domicile")).toBeInTheDocument();
    expect(screen.getByText("dont 2 à déclasser")).toBeInTheDocument();
    expect(screen.getByText("5 derniers mouvements chez ce détenteur")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Plus d'actions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Déplacer du matériel" })).not.toBeInTheDocument();
  });

  it("« Voir plus » des mouvements filtre le registre sur ce détenteur", async () => {
    const onShowAll = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <HolderDetailModal holderId={1} canManage={false} onClose={() => {}} onChanged={() => {}} onShowAllMovements={onShowAll} />,
    );
    await user.click(await screen.findByRole("button", { name: "Voir plus" }));
    expect(onShowAll).toHaveBeenCalledWith({ id: 1, name: "Local du club" });
  });

  it("Intendant : renommer un lieu puis archiver, erreur de l'API affichée dans la confirmation", async () => {
    vi.mocked(renameHolder).mockResolvedValue(detail({ name: "Magasin" }));
    vi.mocked(archiveHolder).mockRejectedValue(
      new ApiError(400, { detail: "Local du club détient encore 8 pièce(s) : déplacez-les avant d'archiver." }),
    );
    const onChanged = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <HolderDetailModal holderId={1} canManage onClose={() => {}} onChanged={onChanged} onShowAllMovements={() => {}} />,
    );
    expect(await screen.findByRole("button", { name: "Déplacer du matériel" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Plus d'actions" }));
    await user.click(screen.getByRole("button", { name: "Renommer le lieu" }));
    const field = screen.getByRole("textbox", { name: /Nom du lieu/ });
    await user.clear(field);
    await user.type(field, "Magasin");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(renameHolder).toHaveBeenCalledWith(1, "Magasin"));
    expect(onChanged).toHaveBeenCalledWith("Lieu renommé.");

    await user.click(screen.getByRole("button", { name: "Plus d'actions" }));
    await user.click(screen.getByRole("button", { name: "Archiver le détenteur" }));
    expect(screen.getByText("Il ne sera plus proposé comme détenteur.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Archiver" }));
    expect(
      await screen.findByText("Local du club détient encore 8 pièce(s) : déplacez-les avant d'archiver."),
    ).toBeInTheDocument();
  });

  it("joueur : pas d'entrée « Renommer le lieu »", async () => {
    vi.mocked(getHolder).mockResolvedValue(detail({ kind: "member", kind_display: "Joueur du club", membership_id: 40 }));
    const user = userEvent.setup();
    renderWithProviders(
      <HolderDetailModal holderId={1} canManage onClose={() => {}} onChanged={() => {}} onShowAllMovements={() => {}} />,
    );
    await user.click(await screen.findByRole("button", { name: "Plus d'actions" }));
    expect(screen.queryByRole("button", { name: "Renommer le lieu" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archiver le détenteur" })).toBeInTheDocument();
  });

  it("404 : message de l'API dans le corps", async () => {
    vi.mocked(getHolder).mockRejectedValue(new ApiError(404, { detail: "Ce détenteur n'existe pas dans ce club." }));
    renderWithProviders(
      <HolderDetailModal holderId={99} canManage onClose={() => {}} onChanged={() => {}} onShowAllMovements={() => {}} />,
    );
    expect(await screen.findByText("Ce détenteur n'existe pas dans ce club.")).toBeInTheDocument();
  });
});
