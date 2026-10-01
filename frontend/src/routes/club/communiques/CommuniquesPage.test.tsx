import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ClubBrandingProvider, ToastProvider } from "../../../design-system";
import { CommuniquesPage } from "./CommuniquesPage";

vi.mock("../../../api/social", async () => {
  const actual = await vi.importActual<typeof import("../../../api/social")>("../../../api/social");
  return {
    ...actual,
    listAnnouncements: vi.fn(),
    getAnnouncement: vi.fn(),
  };
});

import { getAnnouncement, listAnnouncements } from "../../../api/social";

const ANNOUNCEMENT = {
  id: 1,
  title: "Réunion du bureau",
  body: "Texte",
  published_by: { id: 1, first_name: "Amos", last_name: "Kanku", avatar_url: null },
  published_at: "2026-09-20T10:00:00Z",
  pinned: false,
  expires_at: null,
  images: [],
  is_read_by_me: false,
  read_summary: null as null | { read_count: number; total: number },
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ClubBrandingProvider branding={{ name: "Loisirs Club Discovery", logoUrl: null, primaryColor: null, secondaryColor: null }}>
          <CommuniquesPage />
        </ClubBrandingProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("CommuniquesPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche le nombre de non lus et masque « Publier un communiqué » pour un simple joueur", async () => {
    vi.mocked(listAnnouncements).mockImplementation((params) =>
      Promise.resolve({
        results: params?.pinned ? [] : [ANNOUNCEMENT],
        count: 1,
        next_offset: null,
      }),
    );
    renderPage();

    expect(await screen.findByText("Réunion du bureau")).toBeInTheDocument();
    expect(screen.getByText("Loisirs Club Discovery · 1 non lu(s)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publier un communiqué" })).not.toBeInTheDocument();
  });

  it("« Tout est lu » et « Publier un communiqué » visible pour le Président (read_summary présent)", async () => {
    vi.mocked(listAnnouncements).mockImplementation((params) =>
      Promise.resolve({
        results: params?.pinned ? [] : [{ ...ANNOUNCEMENT, is_read_by_me: true, read_summary: { read_count: 5, total: 10 } }],
        count: 1,
        next_offset: null,
      }),
    );
    renderPage();

    expect(await screen.findByText("Réunion du bureau")).toBeInTheDocument();
    expect(screen.getByText("Loisirs Club Discovery · Tout est lu")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publier un communiqué" })).toBeInTheDocument();
    expect(screen.getByText("Lu par 5 sur 10")).toBeInTheDocument();
  });

  it("« Aucun communiqué pour l'instant. » quand la liste est vide", async () => {
    vi.mocked(listAnnouncements).mockResolvedValue({ results: [], count: 0, next_offset: null });
    renderPage();

    expect(await screen.findByText("Aucun communiqué pour l'instant.")).toBeInTheDocument();
  });

  it("ouvre la modale de détail au clic sur une ligne", async () => {
    vi.mocked(listAnnouncements).mockImplementation((params) =>
      Promise.resolve({
        results: params?.pinned ? [] : [ANNOUNCEMENT],
        count: 1,
        next_offset: null,
      }),
    );
    vi.mocked(getAnnouncement).mockResolvedValue(ANNOUNCEMENT);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Réunion du bureau"));
    expect(await screen.findByRole("heading", { name: "Réunion du bureau" })).toBeInTheDocument();
  });
});
