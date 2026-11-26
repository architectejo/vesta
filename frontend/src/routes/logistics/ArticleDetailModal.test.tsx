import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ListMovementsParams, Provenance } from "../../api/logistics";
import { ArticleDetailModal, provenanceDetailLabel, provenanceOriginLabel } from "./ArticleDetailModal";
import { makeArticle, makeMovement, movementPage, renderWithProviders } from "./testFixtures";

vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return { ...actual, getArticle: vi.fn(), listMovements: vi.fn() };
});

import { getArticle, listMovements } from "../../api/logistics";

function provenance(id: number, over: Partial<Provenance> = {}): Provenance {
  return {
    movement_id: id,
    quantity: 2,
    movement_type: "in_donation",
    origin_kind: "donation",
    origin_kind_display: "Don",
    donor: { membership_id: null, name: "Papa Wemba" },
    acquisition_date: "2025-06-22",
    acquisition_date_unknown: false,
    acquisition_date_note: "",
    condition_at_entry: "good",
    condition_at_entry_display: "Bon état",
    holder: { id: 1, name: "Local du club", kind: "place" },
    movement_date: "2026-10-01",
    ...over,
  };
}

describe("libellés de provenance", () => {
  it("origine : don, frais de l'équipe, inconnue, non renseignée", () => {
    expect(provenanceOriginLabel(provenance(1))).toBe("Don de Papa Wemba");
    expect(provenanceOriginLabel(provenance(1, { origin_kind: "club_funds" }))).toBe("Frais de l'équipe");
    expect(provenanceOriginLabel(provenance(1, { origin_kind: "unknown" }))).toBe("Origine inconnue");
    expect(
      provenanceOriginLabel(provenance(1, { origin_kind: "", origin_kind_display: "Origine non renseignée" })),
    ).toBe("Origine non renseignée");
  });

  it("date et détenteur", () => {
    expect(provenanceDetailLabel(provenance(1))).toBe("Acquis le 22/06/2025 · chez Local du club");
    expect(
      provenanceDetailLabel(
        provenance(1, { acquisition_date_unknown: true, acquisition_date: null, acquisition_date_note: "comité", holder: null }),
      ),
    ).toBe("Date inconnue — comité · chez Non localisé");
  });
});

describe("ArticleDetailModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getArticle).mockResolvedValue(
      makeArticle({ pending_decommission: 3, provenances: [1, 2, 3, 4, 5].map((i) => provenance(i)) }),
    );
    vi.mocked(listMovements).mockImplementation(async (params: ListMovementsParams = {}) => {
      if (params.types) {
        return movementPage(
          [makeMovement(6, { movement_type: "in_opening", provenance: provenance(6, { origin_kind: "unknown" }) })],
          null,
          6,
        );
      }
      return movementPage([makeMovement(1)], params.offset ? null : 10, 11, params.offset ?? 0);
    });
  });

  it("valeurs clés, répartition et provenances ; « Voir plus » lit les entrées paginées", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ArticleDetailModal article={makeArticle()} canManage={false} onClose={() => {}} onEdit={() => {}} onChanged={() => {}} />,
    );
    expect(await screen.findAllByText(/Don de Papa Wemba/)).toHaveLength(5);
    expect(screen.getByText("À déclasser")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").some((li) => li.textContent === "Local du club · 8")).toBe(true);
    const buttons = screen.getAllByRole("button", { name: "Voir plus" });
    await user.click(buttons[0]!);
    await waitFor(() =>
      expect(listMovements).toHaveBeenCalledWith(
        expect.objectContaining({ article: 10, types: ["in_purchase", "in_donation", "in_opening"], offset: 0 }),
      ),
    );
    expect(await screen.findByText(/Origine inconnue/)).toBeInTheDocument();
  });

  it("derniers mouvements paginés par l'API (limit/offset)", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ArticleDetailModal article={makeArticle()} canManage={false} onClose={() => {}} onEdit={() => {}} onChanged={() => {}} />,
    );
    await waitFor(() =>
      expect(listMovements).toHaveBeenCalledWith(expect.objectContaining({ article: 10, limit: 10, offset: 0 })),
    );
    const buttons = await screen.findAllByRole("button", { name: "Voir plus" });
    await user.click(buttons[buttons.length - 1]!);
    await waitFor(() => expect(listMovements).toHaveBeenCalledWith(expect.objectContaining({ offset: 10 })));
  });

  it("Intendant : « Déplacer » ouvre « Déplacer du matériel » au niveau 2", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ArticleDetailModal article={makeArticle()} canManage onClose={() => {}} onEdit={() => {}} onChanged={() => {}} />,
    );
    await user.click(await screen.findByRole("button", { name: "Déplacer" }));
    expect(await screen.findByRole("dialog", { name: "Déplacer du matériel" })).toBeInTheDocument();
  });
});
