import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { MyProfile } from "../../api/clubs";
import type { Register, RegisterParams } from "../../api/logistics";
import { RegisterPage } from "./RegisterPage";
import { makeHolder, makeHolderList, renderWithProviders } from "./testFixtures";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});
vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return {
    ...actual,
    getRegister: vi.fn(),
    downloadRegisterPdf: vi.fn(),
    downloadRegisterCsv: vi.fn(),
    listHolders: vi.fn(),
  };
});

import { getMyProfile } from "../../api/clubs";
import { downloadRegisterCsv, downloadRegisterPdf, getRegister, listHolders } from "../../api/logistics";

function register(over: Partial<Register> = {}): Register {
  return {
    club: { id: 1, name: "Club de l'API" },
    as_of: "2026-11-26",
    filters: {},
    filters_label: "",
    include_exits: false,
    sections: [
      {
        category: "balls",
        category_display: "Ballons",
        lines: [
          {
            movement_id: 31,
            article_id: 11,
            designation: "Ballon match",
            category: "balls",
            category_display: "Ballons",
            unit: "pièce",
            quantity: 2,
            movement_type: "in_donation",
            origin_kind: "donation",
            donor_name: "Papa Wemba",
            origin: "Don de Papa Wemba",
            acquisition_date: "2025-06-22",
            acquisition_date_unknown: false,
            acquisition_date_note: "",
            acquisition_label: "22/06/2025",
            recorded_on: "2026-10-01",
            holder_id: 1,
            location: "Local du club",
            condition: "good",
            condition_display: "Bon état",
          },
        ],
        stock_total_by_unit: [
          { unit: "pièces", quantity: 22 },
          { unit: "paires", quantity: 23 },
        ],
        current_distribution: [{ holder_id: 1, holder_name: "Local du club", quantity: 14 }],
      },
    ],
    decommissions: [],
    exits: [],
    is_empty: false,
    ...over,
  };
}

describe("RegisterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getMyProfile).mockResolvedValue({ roles: [{ role: "treasurer", label: "Trésorier" }] } as unknown as MyProfile);
    vi.mocked(getRegister).mockResolvedValue(register());
    vi.mocked(downloadRegisterPdf).mockResolvedValue(undefined);
    vi.mocked(downloadRegisterCsv).mockResolvedValue(undefined);
    vi.mocked(listHolders).mockResolvedValue(makeHolderList([makeHolder({ id: 1, name: "Local du club" })], 2));
  });

  it("affiche le nom du club de l'API, les lignes et le pied de section", async () => {
    renderWithProviders(<RegisterPage />);
    expect(await screen.findByText("Club de l'API · arrêté au 26/11/2026")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ballons" })).toBeInTheDocument();
    expect(screen.getByText("Don de Papa Wemba · 22/06/2025")).toBeInTheDocument();
    expect(screen.getByText("22 pièces · 23 paires")).toBeInTheDocument();
    expect(screen.getByText("Répartition actuelle : Chez Local du club 14")).toBeInTheDocument();
    expect(screen.getByText("Aucun élément à déclasser.")).toBeInTheDocument();
  });

  it("transmet les filtres à l'API et aux téléchargements PDF et CSV", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);
    await screen.findByRole("heading", { name: "Ballons" });
    await user.click(screen.getByRole("button", { name: "Ballons" }));
    await user.click(screen.getByRole("combobox", { name: "Détenteur" }));
    await user.click(await screen.findByText("Non localisé"));
    await user.click(screen.getByRole("checkbox", { name: "Afficher les sorties" }));
    await user.type(screen.getByRole("searchbox", { name: "Rechercher un article, un donateur" }), "wemba");
    const expected: RegisterParams = { search: "wemba", category: "balls", holder: "none", include_exits: true };
    await waitFor(() => expect(getRegister).toHaveBeenLastCalledWith(expected));

    await user.click(screen.getByRole("button", { name: "Télécharger (PDF)" }));
    await waitFor(() => expect(downloadRegisterPdf).toHaveBeenCalledWith(expected));
    await user.click(screen.getByRole("button", { name: "Plus d'actions" }));
    await user.click(screen.getByRole("button", { name: "Exporter (CSV)" }));
    await waitFor(() => expect(downloadRegisterCsv).toHaveBeenCalledWith(expected));
  });

  it("échec du PDF : toast d'erreur en français", async () => {
    vi.mocked(downloadRegisterPdf).mockRejectedValue(new ApiError(500, { detail: "x" }));
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);
    await screen.findByRole("heading", { name: "Ballons" });
    await user.click(screen.getByRole("button", { name: "Télécharger (PDF)" }));
    expect(await screen.findByText("Le registre n'a pas pu être généré. Réessayez.")).toBeInTheDocument();
  });

  it("registre vide sans filtre", async () => {
    vi.mocked(getRegister).mockResolvedValue(register({ sections: [], is_empty: true }));
    renderWithProviders(<RegisterPage />);
    expect(await screen.findByText("Le registre est vide.")).toBeInTheDocument();
  });

  it("aucun résultat avec filtre : « Effacer les filtres »", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);
    await screen.findByRole("heading", { name: "Ballons" });
    vi.mocked(getRegister).mockResolvedValue(register({ sections: [], is_empty: true }));
    await user.type(screen.getByRole("searchbox", { name: "Rechercher un article, un donateur" }), "zzz");
    expect(await screen.findByText("Aucun résultat pour « zzz ».")).toBeInTheDocument();
  });

  it("détenteur introuvable (404) : filtre remis à zéro et toast", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);
    await screen.findByRole("heading", { name: "Ballons" });
    vi.mocked(getRegister).mockImplementation(async (params: RegisterParams = {}) => {
      if (params.holder !== undefined) throw new ApiError(404, { detail: "Ce détenteur n'existe pas dans ce club." });
      return register();
    });
    await user.click(screen.getByRole("combobox", { name: "Détenteur" }));
    await user.click(await screen.findByText("Local du club"));
    expect(await screen.findByText("Ce détenteur n'existe pas dans ce club.")).toBeInTheDocument();
    await waitFor(() => expect(getRegister).toHaveBeenLastCalledWith({}));
  });

  it("erreur de chargement : message global et « Réessayer »", async () => {
    vi.mocked(getRegister).mockRejectedValue(new ApiError(500, { detail: "x" }));
    renderWithProviders(<RegisterPage />);
    expect(await screen.findByText("Impossible de charger le registre.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });

  it("sans rôle de lecture : accès refusé", async () => {
    vi.mocked(getMyProfile).mockResolvedValue({ roles: [{ role: "player", label: "Joueur" }] } as unknown as MyProfile);
    renderWithProviders(<RegisterPage />);
    expect(await screen.findByText("Vous n'avez pas accès à cette page.")).toBeInTheDocument();
    expect(getRegister).not.toHaveBeenCalled();
  });
});
