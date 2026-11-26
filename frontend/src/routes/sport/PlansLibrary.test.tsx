import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import type { TacticalPlanDetail, TacticalPlanListItem } from "../../api/sport";
import { ToastProvider } from "../../design-system";
import { PlansLibrary } from "./PlansLibrary";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, listTacticalPlans: vi.fn(), getTacticalPlan: vi.fn() };
});

import { getMyProfile } from "../../api/clubs";
import { getTacticalPlan, listTacticalPlans } from "../../api/sport";

function makeProfile(...roles: string[]): MyProfile {
  return {
    membership_id: 1,
    club: { id: 1, slug: "test", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    identity: {
      first_name: "Jean",
      last_name: "Joueur",
      photo: null,
      email: "jean@example.com",
      phone: "",
      birth_date: null,
      weight_kg: null,
      height_cm: null,
    },
    position: "midfielder",
    position_label: "Milieu",
    position_detail: "",
    jersey_number: null,
    membership_status: "active",
    membership_status_label: "Inscrit",
    roles: roles.map((role) => ({ role, label: role })),
    email_notifications_enabled: true,
  };
}

function renderPage(initialEntry = "/plans") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/plans" element={<PlansLibrary />} />
            <Route path="/vestiaire" element={<PlansLibrary />} />
            <Route path="/plans/:id/tableau" element={<p>Tableau noir</p>} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("PlansLibrary", () => {
  it("ouvre le plan indiqué par ?plan= (lien d'une notification)", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(listTacticalPlans).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(getTacticalPlan).mockReturnValue(new Promise(() => undefined));
    renderPage("/plans?plan=7");
    await vi.waitFor(() => expect(getTacticalPlan).toHaveBeenCalledWith(7));
  });

  it("n'affiche « Nouveau plan » qu'au Coach", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(listTacticalPlans).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    renderPage();
    expect(await screen.findByText("Aucun plan publié pour l'instant.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nouveau plan" })).not.toBeInTheDocument();
  });

  const planA: TacticalPlanListItem = {
    id: 1,
    name: "Plan A",
    formation: "4-4-2",
    squad_size: 11,
    match_id: null,
    is_published: true,
    published_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
  const onePlan = { count: 1, next_offset: null, results: [planA] };
  const planADetail: TacticalPlanDetail = { ...planA, created_at: "", placements: [], annotations: [] };

  it("liste les plans avec leur statut", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(listTacticalPlans).mockResolvedValue(onePlan);
    renderPage();
    expect(await screen.findByText("Plan A")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nouveau plan" })).toBeInTheDocument();
  });

  it("accorde le badge au masculin : un plan « Publié » (série 5, sport-vestiaire.md §10)", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(listTacticalPlans).mockResolvedValue({
      count: 2,
      next_offset: null,
      results: [planA, { ...planA, id: 2, name: "Plan B", is_published: false, published_at: null }],
    });
    vi.mocked(getTacticalPlan).mockResolvedValue(planADetail);
    renderPage();
    expect(await screen.findByText("Plan A")).toBeInTheDocument();
    expect(screen.getByText("Publié")).toBeInTheDocument();
    expect(screen.getByText("Brouillon")).toBeInTheDocument();
    expect(screen.queryByText("Publiée")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Plan A"));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Publié")).toBeInTheDocument();
  });

  it.each(["coach", "assistant_coach"])("%s : boutons de création et de gestion visibles", async (role) => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile(role));
    vi.mocked(listTacticalPlans).mockResolvedValue(onePlan);
    vi.mocked(getTacticalPlan).mockResolvedValue(planADetail);
    renderPage();
    fireEvent.click(await screen.findByText("Plan A"));
    expect(await screen.findByRole("button", { name: "Dupliquer" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Supprimer le plan" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Modifier sur le tableau noir" })).toBeInTheDocument();
  });

  it.each(["captain", "president", ""])("rôle « %s » : lecture seule", async (role) => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile(...(role ? [role] : [])));
    vi.mocked(listTacticalPlans).mockResolvedValue(onePlan);
    vi.mocked(getTacticalPlan).mockResolvedValue(planADetail);
    renderPage();
    fireEvent.click(await screen.findByText("Plan A"));
    expect((await screen.findAllByRole("button", { name: "Fermer" })).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Nouveau plan" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dupliquer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Supprimer le plan" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Modifier sur le tableau noir" })).not.toBeInTheDocument();
  });

  it("« Modifier sur le tableau noir » ferme la modale et reste sur le tableau noir", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(listTacticalPlans).mockResolvedValue(onePlan);
    vi.mocked(getTacticalPlan).mockResolvedValue(planADetail);
    renderPage("/vestiaire");
    fireEvent.click(await screen.findByText("Plan A"));
    fireEvent.click(await screen.findByRole("button", { name: "Modifier sur le tableau noir" }));
    expect(await screen.findByText("Tableau noir")).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(screen.getByText("Tableau noir")).toBeInTheDocument();
  });
});
