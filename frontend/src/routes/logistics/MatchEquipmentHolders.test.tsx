import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MatchEquipmentOutLine } from "../../api/logistics";
import { AddMatchEquipmentModal } from "./AddMatchEquipmentModal";
import { MatchEquipmentModal } from "./MatchEquipmentModal";
import { makeArticle, makeHolder, makeHolderList, renderWithProviders, toSearchResult } from "./testFixtures";

vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return {
    ...actual,
    searchArticles: vi.fn(),
    getMatchEquipment: vi.fn(),
    recordMatchEquipmentReturn: vi.fn(),
    listHolders: vi.fn(),
  };
});

import { getMatchEquipment, listHolders, recordMatchEquipmentReturn, searchArticles } from "../../api/logistics";

describe("AddMatchEquipmentModal — détenteur de la sortie", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(searchArticles).mockResolvedValue([toSearchResult(makeArticle())]);
  });

  async function pickArticle(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByRole("combobox", { name: "Nom de l'article" }), "Mai");
    await user.click(await screen.findByText("Maillot domicile"));
    await user.type(screen.getByRole("spinbutton", { name: "Quantité" }), "2");
  }

  function renderModal(onSubmit: (lines: MatchEquipmentOutLine[]) => Promise<void>) {
    return renderWithProviders(
      <AddMatchEquipmentModal
        open
        clubName="Club"
        opponent="Adversaire"
        eventDate="2026-11-30"
        onClose={() => {}}
        onSubmit={onSubmit}
      />,
    );
  }

  it("sans changement : affiche le détenteur suggéré et n'envoie pas holder_id", async () => {
    const onSubmit = vi.fn<(lines: MatchEquipmentOutLine[]) => Promise<void>>().mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderModal(onSubmit);
    await pickArticle(user);
    expect(screen.getByText(/Chez Local du club/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0]![0]).toEqual([{ article_id: 10, quantity: 2 }]);
  });

  it("source changée vers « Non localisé » : holder_id null envoyé", async () => {
    const onSubmit = vi.fn<(lines: MatchEquipmentOutLine[]) => Promise<void>>().mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderModal(onSubmit);
    await pickArticle(user);
    await user.click(
      screen.getAllByRole("button", { name: "Changer" }).find((b) => b.parentElement?.textContent?.includes("Chez"))!,
    );
    await user.click(screen.getByRole("radio", { name: /Non localisé/ }));
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0]![0]).toEqual([{ article_id: 10, quantity: 2, holder_id: null }]);
  });
});

describe("MatchEquipmentModal — destination du retour", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getMatchEquipment).mockResolvedValue({
      lines: [
        {
          article_id: 10,
          article_name: "Maillot domicile",
          out_quantity: 4,
          returned_quantity: 0,
          remaining_quantity: 4,
          status: "out",
          holder: { id: 1, name: "Local du club", kind: "place" },
        },
      ],
    });
    vi.mocked(recordMatchEquipmentReturn).mockResolvedValue({ lines: [] });
    vi.mocked(listHolders).mockResolvedValue(
      makeHolderList([makeHolder({ id: 1, name: "Local du club" }), makeHolder({ id: 2, name: "Magasin" })]),
    );
  });

  function renderModal() {
    return renderWithProviders(
      <MatchEquipmentModal open matchId={5} opponent="Adversaire" eventDate="2026-11-30" canRecordReturn onClose={() => {}} />,
    );
  }

  it("détail : « Sorti de chez » ; retour sans changement sans holder_id", async () => {
    const user = userEvent.setup();
    renderModal();
    expect(await screen.findByText("Sorti de chez Local du club")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enregistrer le retour" }));
    expect(await screen.findByText(/Retour chez Local du club/)).toBeInTheDocument();
    const buttons = screen.getAllByRole("button", { name: "Enregistrer le retour" });
    await user.click(buttons[buttons.length - 1]!);
    await waitFor(() => expect(recordMatchEquipmentReturn).toHaveBeenCalled());
    expect(vi.mocked(recordMatchEquipmentReturn).mock.calls[0]![1]).toEqual([{ article_id: 10, quantity_returned: 4 }]);
  });

  it("retour vers un autre détenteur : holder_id envoyé", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(await screen.findByRole("button", { name: "Enregistrer le retour" }));
    await user.click(await screen.findByRole("button", { name: "Changer" }));
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByText("Magasin"));
    const buttons = screen.getAllByRole("button", { name: "Enregistrer le retour" });
    await user.click(buttons[buttons.length - 1]!);
    await waitFor(() => expect(recordMatchEquipmentReturn).toHaveBeenCalled());
    expect(vi.mocked(recordMatchEquipmentReturn).mock.calls[0]![1]).toEqual([
      { article_id: 10, quantity_returned: 4, holder_id: 2 },
    ]);
  });
});
