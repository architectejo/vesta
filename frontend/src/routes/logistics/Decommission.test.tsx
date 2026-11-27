import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { DecommissionDetailModal } from "./DecommissionDetailModal";
import { DecommissionFlagModal } from "./DecommissionFlagModal";
import { DecommissionListModal } from "./DecommissionListModal";
import { makeArticle, makeDecommission, renderWithProviders, toSearchResult } from "./testFixtures";

vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return {
    ...actual,
    flagDecommission: vi.fn(),
    getDecommission: vi.fn(),
    executeDecommission: vi.fn(),
    cancelDecommission: vi.fn(),
    listDecommissions: vi.fn(),
    searchArticles: vi.fn(),
  };
});

import {
  cancelDecommission,
  executeDecommission,
  flagDecommission,
  getDecommission,
  listDecommissions,
  searchArticles,
} from "../../api/logistics";

const article = toSearchResult(makeArticle());

describe("DecommissionFlagModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(flagDecommission).mockResolvedValue(makeDecommission());
  });

  it("clears the « Choisissez un article. » error once an article is chosen", async () => {
    // Constaté en e2e (12-intendance) : l'erreur restait affichée sous
    // l'article pourtant choisi, jusqu'au prochain envoi.
    vi.mocked(searchArticles).mockResolvedValue([article]);
    const user = userEvent.setup();
    renderWithProviders(<DecommissionFlagModal open onClose={() => {}} onSaved={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Signaler" }));
    expect(await screen.findByText("Choisissez un article.")).toBeInTheDocument();
    await user.type(screen.getByRole("combobox"), "Mai");
    await user.click(await screen.findByRole("option", { name: new RegExp(article.name) }));
    expect(screen.queryByText("Choisissez un article.")).not.toBeInTheDocument();
  });

  it("exige le détenteur, le motif, et une précision pour « Autre »", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DecommissionFlagModal open lockedArticle={article} onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getByText("Les pièces restent dans le stock jusqu'à leur sortie.")).toBeInTheDocument();
    await user.type(screen.getByRole("spinbutton", { name: /Quantité/ }), "2");
    await user.click(screen.getByRole("button", { name: "Signaler" }));
    expect(await screen.findByText("Choisissez chez qui se trouvent les pièces.")).toBeInTheDocument();
    expect(screen.getByText("Choisissez le motif.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Autre" }));
    await user.click(screen.getByRole("button", { name: "Signaler" }));
    expect(await screen.findByText("Précisez le motif.")).toBeInTheDocument();
    expect(flagDecommission).not.toHaveBeenCalled();
  });

  it("envoie holder_id, motif et date du constat ; toast « {n} {unité} de {article} à déclasser. »", async () => {
    const onSaved = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<DecommissionFlagModal open lockedArticle={article} onClose={() => {}} onSaved={onSaved} />);
    await user.click(screen.getByRole("radio", { name: /Local du club/ }));
    await user.type(screen.getByRole("spinbutton", { name: /Quantité/ }), "2");
    await user.click(screen.getByRole("button", { name: "Hors d'usage" }));
    await user.click(screen.getByRole("button", { name: "Signaler" }));
    await waitFor(() => expect(flagDecommission).toHaveBeenCalled());
    expect(vi.mocked(flagDecommission).mock.calls[0]![0]).toMatchObject({
      article_id: 10,
      holder_id: 1,
      quantity: 2,
      reason: "unusable",
    });
    expect(vi.mocked(flagDecommission).mock.calls[0]![0].noted_on).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(onSaved).toHaveBeenCalledWith("2 pièces de Maillot domicile à déclasser.");
  });
});

describe("DecommissionDetailModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getDecommission).mockResolvedValue(makeDecommission({ noted_on: "2026-01-05" }));
    vi.mocked(executeDecommission).mockResolvedValue({
      decommission: makeDecommission({ status: "done" }),
      in_stock: 9,
    });
  });

  it("sortie du stock : confirmation explicite avant l'appel, confirm envoyé par l'API cliente", async () => {
    const onChanged = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<DecommissionDetailModal decommissionId={7} canManage onClose={() => {}} onChanged={onChanged} />);
    await user.click(await screen.findByRole("button", { name: "Sortir du stock" }));
    await user.type(screen.getByRole("textbox", { name: /Destination/ }), "École du quartier");
    await user.click(screen.getByRole("button", { name: "Continuer" }));
    expect(await screen.findByText("Sortir 3 pièces de Maillot domicile du stock ?")).toBeInTheDocument();
    expect(screen.getByText("Cette sortie est définitive : elle ne pourra pas être supprimée.")).toBeInTheDocument();
    expect(executeDecommission).not.toHaveBeenCalled();
    const buttons = screen.getAllByRole("button", { name: "Sortir du stock" });
    await user.click(buttons[buttons.length - 1]!);
    await waitFor(() => expect(executeDecommission).toHaveBeenCalled());
    expect(vi.mocked(executeDecommission).mock.calls[0]![1]).toMatchObject({ destination: "École du quartier" });
    expect(onChanged).toHaveBeenCalledWith("Sortie du stock : 3 pièces. Stock de Maillot domicile : 9 pièces.");
  });

  it("annulation : motif obligatoire puis appel cancel/", async () => {
    vi.mocked(cancelDecommission).mockResolvedValue(makeDecommission({ status: "cancelled" }));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<DecommissionDetailModal decommissionId={7} canManage onClose={() => {}} onChanged={onChanged} />);
    await user.click(await screen.findByRole("button", { name: "Plus d'actions" }));
    await user.click(screen.getByRole("button", { name: "Annuler le signalement" }));
    const confirmButtons = screen.getAllByRole("button", { name: "Annuler le signalement" });
    await user.click(confirmButtons[confirmButtons.length - 1]!);
    expect(await screen.findByText("Indiquez le motif de l'annulation.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Motif" }), "Erreur de saisie");
    await user.click(confirmButtons[confirmButtons.length - 1]!);
    await waitFor(() => expect(cancelDecommission).toHaveBeenCalledWith(7, "Erreur de saisie"));
    expect(onChanged).toHaveBeenCalledWith("Signalement annulé.");
  });

  it("affiche l'erreur de l'API dans la confirmation", async () => {
    vi.mocked(executeDecommission).mockRejectedValue(new ApiError(400, { detail: "Ce signalement n'est plus en attente." }));
    const user = userEvent.setup();
    renderWithProviders(<DecommissionDetailModal decommissionId={7} canManage onClose={() => {}} onChanged={() => {}} />);
    await user.click(await screen.findByRole("button", { name: "Sortir du stock" }));
    await user.click(screen.getByRole("button", { name: "Continuer" }));
    const buttons = await screen.findAllByRole("button", { name: "Sortir du stock" });
    await user.click(buttons[buttons.length - 1]!);
    expect(await screen.findByText("Ce signalement n'est plus en attente.")).toBeInTheDocument();
  });

  it("lecteur ou déclassement terminé : aucune action d'écriture", async () => {
    vi.mocked(getDecommission).mockResolvedValue(
      makeDecommission({
        status: "done",
        exit_date: "2026-11-10",
        exit_destination: "Don",
        exit_movement_id: 30,
        executed_by: { id: 3, name: "Paul Intendant" },
      }),
    );
    renderWithProviders(<DecommissionDetailModal decommissionId={7} canManage onClose={() => {}} onChanged={() => {}} />);
    expect(await screen.findByText("Sorti le 10/11/2026 · Don · par Paul Intendant")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Voir le mouvement" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sortir du stock" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Plus d'actions" })).not.toBeInTheDocument();
  });
});

describe("DecommissionListModal", () => {
  it("transmet le filtre de statut à l'API", async () => {
    vi.mocked(listDecommissions).mockResolvedValue({ count: 1, pending_quantity: 3, results: [makeDecommission()] });
    const user = userEvent.setup();
    renderWithProviders(<DecommissionListModal open onClose={() => {}} onOpenDecommission={() => {}} />);
    await waitFor(() => expect(listDecommissions).toHaveBeenCalledWith({ status: "pending" }));
    expect(await screen.findByText(/Usé · chez Local du club · signalé le 01\/11\/2026/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tous" }));
    await waitFor(() => expect(listDecommissions).toHaveBeenLastCalledWith({}));
    await user.click(screen.getByRole("button", { name: "Déclassés" }));
    await waitFor(() => expect(listDecommissions).toHaveBeenLastCalledWith({ status: "done" }));
  });
});

describe("DecommissionRows", () => {
  it("keeps the status badge on a single line next to long rows (360 px)", async () => {
    // Constaté en e2e (12-intendance, 22) : « À déclasser » se cassait en deux.
    vi.mocked(listDecommissions).mockResolvedValue({ count: 1, pending_quantity: 3, results: [makeDecommission()] });
    renderWithProviders(<DecommissionListModal open onClose={() => {}} onOpenDecommission={() => {}} />);
    const row = await screen.findByText(/Usé · chez Local du club/);
    const badge = row.closest("button")!.lastElementChild!;
    expect(badge).toHaveClass("shrink-0", "whitespace-nowrap");
  });
});
