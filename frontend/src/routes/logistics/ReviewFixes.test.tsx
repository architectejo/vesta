/** Correctifs après audit (E1 hors connexion, E2 « Voir le déclassement », E3 erreur du registre). */
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { MyProfile } from "../../api/clubs";
import type { ListMovementsParams, MaterialOverview } from "../../api/logistics";
import { ArticleDetailModal } from "./ArticleDetailModal";
import { DecommissionDetailModal } from "./DecommissionDetailModal";
import { DecommissionFlagModal } from "./DecommissionFlagModal";
import { MaterielPage } from "./MaterielPage";
import { TransferModal } from "./TransferModal";
import {
  makeArticle,
  makeDecommission,
  makeHolderList,
  makeMovement,
  movementPage,
  renderWithProviders,
  toSearchResult,
} from "./testFixtures";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});
vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return {
    ...actual,
    createTransfer: vi.fn(),
    flagDecommission: vi.fn(),
    getDecommission: vi.fn(),
    executeDecommission: vi.fn(),
    cancelDecommission: vi.fn(),
    getArticle: vi.fn(),
    getMovement: vi.fn(),
    listMovements: vi.fn(),
    listHolders: vi.fn(),
    getMaterialOverview: vi.fn(),
    listArticles: vi.fn(),
    listDecommissions: vi.fn(),
  };
});

import { getMyProfile } from "../../api/clubs";
import {
  createTransfer,
  flagDecommission,
  getArticle,
  getDecommission,
  getMaterialOverview,
  getMovement,
  listArticles,
  listDecommissions,
  listHolders,
  listMovements,
} from "../../api/logistics";

const OFFLINE = "Cette action nécessite une connexion.";
const article = toSearchResult(makeArticle());

function goOffline() {
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listHolders).mockResolvedValue(makeHolderList([]));
  vi.mocked(getDecommission).mockResolvedValue(makeDecommission());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("E1 — actions d'écriture hors connexion", () => {
  it("Déplacer du matériel : bouton désactivé et message, aucun envoi", async () => {
    goOffline();
    const user = userEvent.setup();
    renderWithProviders(<TransferModal open lockedArticle={article} initialFrom={1} onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getByText(OFFLINE)).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Déplacer" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(createTransfer).not.toHaveBeenCalled();
  });

  it("Signaler à déclasser : bouton désactivé et message", () => {
    goOffline();
    renderWithProviders(<DecommissionFlagModal open lockedArticle={article} onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getByText(OFFLINE)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Signaler" })).toBeDisabled();
    expect(flagDecommission).not.toHaveBeenCalled();
  });

  it("Déclassement : « Sortir du stock » et « Annuler le signalement » désactivés", async () => {
    goOffline();
    const user = userEvent.setup();
    renderWithProviders(<DecommissionDetailModal decommissionId={7} canManage onClose={() => {}} onChanged={() => {}} />);
    expect(await screen.findByRole("button", { name: "Sortir du stock" })).toBeDisabled();
    expect(screen.getByText(OFFLINE)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Plus d'actions" }));
    expect(screen.getByRole("button", { name: "Annuler le signalement" })).toBeDisabled();
  });

  it("le retour du réseau réactive l'action", async () => {
    const spy = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    renderWithProviders(<DecommissionFlagModal open lockedArticle={article} onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getByRole("button", { name: "Signaler" })).toBeDisabled();
    spy.mockReturnValue(true);
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Signaler" })).toBeEnabled());
    expect(screen.queryByText(OFFLINE)).not.toBeInTheDocument();
  });
});

describe("E2 — « Voir le déclassement » depuis la fiche Article", () => {
  it("ouvre le détail du déclassement lié au mouvement", async () => {
    vi.mocked(getArticle).mockResolvedValue(makeArticle({ provenances: [] }));
    vi.mocked(listMovements).mockResolvedValue(
      movementPage(
        [
          makeMovement(40, {
            movement_type: "out_decommission",
            movement_type_display: "Déclassement",
            signed_quantity: -3,
            decommission_id: 7,
          }),
        ],
        null,
        1,
      ),
    );
    vi.mocked(getMovement).mockResolvedValue(
      makeMovement(40, { movement_type: "out_decommission", movement_type_display: "Déclassement", decommission_id: 7 }),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <ArticleDetailModal article={makeArticle()} canManage={false} onClose={() => {}} onEdit={() => {}} onChanged={() => {}} />,
    );
    await user.click(await screen.findByText(/· Déclassement/));
    await user.click(await screen.findByRole("button", { name: "Voir le déclassement" }));
    await waitFor(() => expect(getDecommission).toHaveBeenCalledWith(7));
    expect(await screen.findByRole("dialog", { name: "Déclassement · Maillot domicile" })).toBeInTheDocument();
  });
});

describe("E3 — registre des mouvements en erreur", () => {
  it("affiche seulement l'état d'erreur et « Réessayer », sans l'état vide", async () => {
    vi.mocked(getMyProfile).mockResolvedValue({
      roles: [{ role: "steward", label: "Intendant" }],
      club: { name: "Club Test" },
    } as unknown as MyProfile);
    vi.mocked(getMaterialOverview).mockResolvedValue({
      current_quarter_label_display: "4e trimestre 2026",
      open_inventory: null,
      blocking_inventory: false,
      can_open: false,
      last_closed_inventory: null,
    } as unknown as MaterialOverview);
    vi.mocked(listArticles).mockResolvedValue({ count: 0, results: [] });
    vi.mocked(listDecommissions).mockResolvedValue({ count: 0, pending_quantity: 0, results: [] });
    vi.mocked(listMovements).mockImplementation(async (params: ListMovementsParams = {}) => {
      if (params.movement_type === "out_loan") return movementPage([], null, 0);
      throw new ApiError(500, { detail: "x" });
    });
    renderWithProviders(<MaterielPage />);
    expect(await screen.findByText("Impossible de charger les mouvements.")).toBeInTheDocument();
    const section = screen.getByText("Impossible de charger les mouvements.").closest("section")!;
    expect(section).not.toHaveTextContent("Aucun mouvement enregistré.");
    expect(section.querySelector("table")).toBeNull();
    expect(section).toHaveTextContent("Réessayer");
  });
});
