import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { MyProfile } from "../../api/clubs";
import type { Register, RegisterExit, RegisterLine, RegisterParams, RegisterSection } from "../../api/logistics";
import { RegisterPage } from "./RegisterPage";
import {
  makeHolder,
  makeHolderList,
  makeRegister,
  makeRegisterDecommission,
  makeRegisterExit,
  makeRegisterLine,
  makeRegisterSection,
  renderWithProviders,
} from "./testFixtures";

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
  return makeRegister(over);
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
    expect(screen.getByText("Stock actuel : 22 pièces · 23 paires")).toBeInTheDocument();
    expect(screen.queryByText(/^Total :/)).not.toBeInTheDocument();
    expect(screen.getByText("2 pièces")).toBeInTheDocument();
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

  it("affiche les libellés accordés de l'API pour les lignes, les sorties et les éléments à déclasser", async () => {
    vi.mocked(getRegister).mockResolvedValue(
      register({
        include_exits: true,
        filters: { search: "", category: "", holder: null, include_exits: true },
        sections: [
          makeRegisterSection({
            lines: [makeRegisterLine({ quantity: 1, quantity_label: "1 pièce" })],
            stock_total_by_unit: [{ unit: "pièce", quantity: 19 }],
            stock_total_label: "Stock actuel : 19 pièces",
          }),
        ],
        exits: [makeRegisterExit({ quantity: 26, quantity_label: "26 pièces" })],
        decommissions: [makeRegisterDecommission({ quantity: 2, unit: "jeu", quantity_label: "2 jeux" })],
      }),
    );
    renderWithProviders(<RegisterPage />);

    expect(await screen.findByText("Stock actuel : 19 pièces")).toBeInTheDocument();
    expect(screen.getByText("1 pièce")).toBeInTheDocument();
    expect(screen.getByText("26 pièces")).toBeInTheDocument();
    expect(screen.getByText("2 jeux")).toBeInTheDocument();
    expect(screen.queryByText("26 pièce")).not.toBeInTheDocument();
  });

  it("repli si l'API ne fournit pas encore les libellés : ancien affichage, accordé", async () => {
    const legacyLine = { ...makeRegisterLine({ quantity: 26 }), quantity_label: undefined } as unknown as RegisterLine;
    const legacySection = {
      ...makeRegisterSection({
        lines: [legacyLine],
        stock_total_by_unit: [{ unit: "pièce", quantity: 1 }],
      }),
      stock_total_label: undefined,
    } as unknown as RegisterSection;
    const legacyExit = { ...makeRegisterExit({ quantity: 1 }), quantity_label: undefined } as unknown as RegisterExit;
    vi.mocked(getRegister).mockResolvedValue(register({ include_exits: true, sections: [legacySection], exits: [legacyExit] }));
    renderWithProviders(<RegisterPage />);

    expect(await screen.findByText("Total :", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("26 pièces")).toBeInTheDocument();
    // Pied de section et sortie : « 1 pièce », jamais « 1 pièces ».
    expect(screen.getAllByText("1 pièce")).toHaveLength(2);
  });
});
