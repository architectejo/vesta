import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TacticalPlanDetail } from "../../api/sport";
import { PlanDetailModal } from "./PlanDetailModal";

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, getTacticalPlan: vi.fn() };
});

import { getTacticalPlan } from "../../api/sport";

function makePlan(): TacticalPlanDetail {
  return {
    id: 1,
    name: "Plan A",
    formation: "4-4-2",
    squad_size: 11,
    match_id: null,
    is_published: true,
    published_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    created_at: "2026-09-01T00:00:00Z",
    placements: [
      {
        id: 10,
        membership_id: 5,
        player: {
          membership_id: 5,
          name: "Jean Joueur",
          jersey_number: 9,
          position: "forward",
          position_label: "Attaquant",
          photo: null,
        },
        x_coord: "50",
        y_coord: "80",
        jersey_number_override: null,
        position_override: "",
        no_longer_eligible: null,
      },
    ],
    annotations: [
      {
        id: 20,
        annotation_type: "note",
        path_data: "[]",
        text: "Restez compacts.",
        target_membership_id: null,
        target_line: "defense",
      },
    ],
  };
}

function renderModal(isCoach = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PlanDetailModal
          open
          planId={1}
          isCoach={isCoach}
          ownMembershipId={undefined}
          onClose={() => {}}
          onDuplicate={() => {}}
          onDelete={() => {}}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Restaure `matchMedia` par défaut (aucune query ne correspond) après
 * chaque test qui le personnalise (jsdom, `src/test/setup.ts`). */
function mockMatchMedia(matching: string[]): void {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: matching.includes(query),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

describe("PlanDetailModal", () => {
  afterEach(() => {
    mockMatchMedia([]);
  });

  it("pied du Coach à 360 px : actions secondaires sur leur ligne, action principale extensible (B3)", async () => {
    // Vérification visuelle B3 : quatre boutons sur une ligne, « Modifier sur le
    // tableau noir » débordait de l’écran. jsdom ne calcule pas la mise en
    // page : on fige la structure qui permet le retour à la ligne.
    mockMatchMedia([]);
    vi.mocked(getTacticalPlan).mockResolvedValue(makePlan());
    renderModal(true);
    const main = await screen.findByRole("button", { name: "Modifier sur le tableau noir" });
    const footer = main.closest("[data-plan-footer]")!;
    expect(footer.className.split(" ")).toContain("flex-wrap");
    expect(main.className.split(" ")).toEqual(expect.arrayContaining(["min-w-0", "flex-1"]));
    const secondary = screen.getByRole("button", { name: "Dupliquer" }).parentElement!;
    expect(secondary.className.split(" ")).toContain("w-full");
    expect(secondary).toContainElement(screen.getByRole("button", { name: "Supprimer le plan" }));
    expect(secondary).not.toContainElement(main);
  });

  it("affiche le terrain et les consignes, empilés en portrait mobile", async () => {
    mockMatchMedia([]);
    vi.mocked(getTacticalPlan).mockResolvedValue(makePlan());
    renderModal();

    expect(await screen.findByText("Plan A")).toBeInTheDocument();
    expect(screen.getByText("Consignes")).toBeInTheDocument();
    expect(screen.getByText(/Restez compacts\./)).toBeInTheDocument();
    // Portrait : pas de disposition en deux colonnes.
    const consignes = screen.getByText("Consignes").closest("div");
    expect(consignes?.className ?? "").not.toContain("flex-1");
  });

  it("bascule en deux colonnes (terrain à gauche, consignes à droite) à partir de 640 px", async () => {
    mockMatchMedia(["(min-width: 640px)"]);
    vi.mocked(getTacticalPlan).mockResolvedValue(makePlan());
    renderModal();

    expect(await screen.findByText("Plan A")).toBeInTheDocument();
    const consignesHeading = screen.getByText("Consignes");
    const consignesColumn = consignesHeading.closest("div");
    expect(consignesColumn?.className).toContain("flex-1");
    // Le terrain (rôle « group », `aria-label` = nom du plan) reste affiché.
    expect(screen.getByRole("group", { name: "Plan A" })).toBeInTheDocument();
  });

  it("bascule en deux colonnes en paysage mobile, sous 640 px", async () => {
    mockMatchMedia(["(orientation: landscape)"]);
    vi.mocked(getTacticalPlan).mockResolvedValue(makePlan());
    renderModal();

    expect(await screen.findByText("Plan A")).toBeInTheDocument();
    const consignesColumn = screen.getByText("Consignes").closest("div");
    expect(consignesColumn?.className).toContain("flex-1");
  });

  it("ouvre le détail d'un pion touché", async () => {
    mockMatchMedia([]);
    vi.mocked(getTacticalPlan).mockResolvedValue(makePlan());
    renderModal();

    const pin = await screen.findByRole("button", { name: "Jean J." });
    fireEvent.pointerDown(pin, { clientX: 0, clientY: 0, pointerId: 1 });
    fireEvent.pointerUp(pin, { clientX: 0, clientY: 0, pointerId: 1 });
    const dialog = await screen.findByRole("dialog", { name: "Jean Joueur" });
    expect(within(dialog).getByText(/n° 9/)).toBeInTheDocument();
  });
});
