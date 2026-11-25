import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../../api/clubs")>("../../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

vi.mock("../../../api/assemblies", async () => {
  const actual = await vi.importActual<typeof import("../../../api/assemblies")>("../../../api/assemblies");
  return { ...actual, listAssemblies: vi.fn() };
});

import { listAssemblies } from "../../../api/assemblies";
import { getMyProfile } from "../../../api/clubs";
import { ToastProvider } from "../../../design-system";
import { AssembleesPage } from "./AssembleesPage";

function makeProfile(role: string) {
  return {
    club: { id: 1, slug: "test", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    roles: [{ role }],
  } as unknown as Awaited<ReturnType<typeof getMyProfile>>;
}

function emptyList() {
  return { count: 0, next: null, previous: null, results: [] } as unknown as Awaited<
    ReturnType<typeof listAssemblies>
  >;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ToastProvider>
          <AssembleesPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AssembleesPage : bouton « Convoquer une AG »", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("reste affiché pour le Président quand aucune assemblée n'existe (pas de clignotement)", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("president"));
    vi.mocked(listAssemblies).mockResolvedValue(emptyList());
    renderPage();

    // Les listes vides ne doivent pas faire disparaître le bouton une fois chargées.
    await screen.findByText("Aucune assemblée prévue.");
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: "Convoquer une AG" }).length).toBeGreaterThan(0);
    });
  });

  it("n'est pas proposé à un joueur sans droit de convocation", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(listAssemblies).mockResolvedValue(emptyList());
    renderPage();

    await screen.findByText("Aucune assemblée prévue.");
    expect(screen.queryByRole("button", { name: "Convoquer une AG" })).not.toBeInTheDocument();
  });

  it("affiche « Convoquer une AG » au Secrétaire mais pas le seuil de quorum (réservé Président/VP)", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("secretary"));
    vi.mocked(listAssemblies).mockResolvedValue(emptyList());
    renderPage();

    await screen.findByText("Aucune assemblée prévue.");
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: "Convoquer une AG" }).length).toBeGreaterThan(0);
    });
    expect(screen.queryByRole("button", { name: "Plus d'actions" })).not.toBeInTheDocument();
  });

  it("suit can_convene renvoyé par l'API même si le profil n'est pas encore connu", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("member"));
    vi.mocked(listAssemblies).mockResolvedValue({
      count: 1,
      next_offset: null,
      results: [
        {
          id: 1,
          assembly_type: "ordinary",
          scheduled_date: "2026-12-01",
          scheduled_time: "10:00:00",
          location: "",
          status: "scheduled",
          created_at: "2026-10-01T00:00:00Z",
          agenda_items: [],
          decisions: [],
          quorum: { present: 0, total: 10, percentage: "0", threshold: "50", reached: false },
          minutes: null,
          can_manage: false,
          can_convene: true,
          can_sign_president: false,
          can_sign_vice_president: false,
        },
      ],
    } as Awaited<ReturnType<typeof listAssemblies>>);
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: "Convoquer une AG" }).length).toBeGreaterThan(0);
    });
  });

  it("propose « Voir plus » pour la liste « À venir » quand l'API indique une suite", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("member"));
    // Une assemblée à venir au minimum pour afficher la liste.
    const base = {
      id: 1,
      assembly_type: "ordinary",
      scheduled_date: "2026-12-01",
      scheduled_time: "10:00:00",
      location: "",
      status: "scheduled",
      created_at: "2026-10-01T00:00:00Z",
      agenda_items: [],
      decisions: [],
      can_manage: false,
      can_convene: false,
    };
    vi.mocked(listAssemblies).mockImplementation(((params: { status?: string; limit?: number }) =>
      Promise.resolve(
        params.status === "scheduled"
          ? { count: 11, next_offset: 10, results: [base] }
          : { count: 0, next_offset: null, results: [] },
      )) as unknown as typeof listAssemblies);
    renderPage();

    const more = await screen.findByRole("button", { name: "Voir plus" });
    more.click();
    await waitFor(() => {
      expect(listAssemblies).toHaveBeenCalledWith({ status: "scheduled", limit: 20 });
    });
  });
});
