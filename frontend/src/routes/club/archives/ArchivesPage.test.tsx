import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../../api/clubs")>("../../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});
vi.mock("../../../api/assemblies", async () => {
  const actual = await vi.importActual<typeof import("../../../api/assemblies")>("../../../api/assemblies");
  return {
    ...actual,
    listArchivedDocuments: vi.fn(),
    getArchivedDocument: vi.fn(),
    downloadArchivedDocument: vi.fn(),
    uploadArchivedDocument: vi.fn(),
    withdrawArchivedDocument: vi.fn(),
  };
});

import {
  getArchivedDocument,
  listArchivedDocuments,
  withdrawArchivedDocument,
  type ArchivedDocument,
} from "../../../api/assemblies";
import { getMyProfile } from "../../../api/clubs";
import { ClubBrandingProvider, ToastProvider } from "../../../design-system";
import { ArchivesPage } from "./ArchivesPage";

function makeProfile(role: string) {
  return {
    club: { id: 1, slug: "t", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    roles: [{ role }],
  } as unknown as Awaited<ReturnType<typeof getMyProfile>>;
}

function makeDoc(overrides: Partial<ArchivedDocument> = {}): ArchivedDocument {
  return {
    id: 1,
    category: "pv_reunion",
    category_label: "PV de réunion",
    title: "PV du bureau du 4 octobre",
    document_date: "2026-10-04",
    status: "active",
    status_label: "Actif",
    uploaded_by_name: "Amos Kanku",
    uploaded_at: "2026-10-05T08:00:00Z",
    withdrawn_by_name: "",
    withdrawn_at: null,
    withdrawn_reason: "",
    replaces_id: null,
    replaced_by_id: null,
    file_name: "pv.pdf",
    file_size: 2048,
    download_url: "/api/v1/assemblies/documents/1/file/",
    ...overrides,
  };
}

function listOf(results: ArchivedDocument[], next: number | null = null) {
  return { results, count: results.length, next_offset: next };
}

function renderPage(initial = "/club/archives") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initial]}>
        <ToastProvider>
          <ClubBrandingProvider branding={{ name: "Club de test", logoUrl: null, primaryColor: null, secondaryColor: null }}>
            <ArchivesPage />
          </ClubBrandingProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ArchivesPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("refuse l'accès à un joueur sans droit, sans rien charger", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    renderPage();
    expect(await screen.findByText("Vous n'avez pas accès à cette page.")).toBeInTheDocument();
    expect(screen.getByText("Les archives sont réservées aux membres du Bureau.")).toBeInTheDocument();
    expect(listArchivedDocuments).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Déposer un document" })).not.toBeInTheDocument();
  });

  it("affiche l'état vide en lecture seule pour un membre du Bureau sans droit d'écriture", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
    vi.mocked(listArchivedDocuments).mockResolvedValue(listOf([]));
    renderPage();
    expect(await screen.findByText("Aucun document archivé pour l'instant.")).toBeInTheDocument();
    expect(screen.getByText("Le Secrétaire dépose les documents officiels du club.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Déposer un document" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Afficher les documents retirés" })).toBeInTheDocument();
  });

  it("propose le dépôt au Secrétaire et liste les documents", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("secretary"));
    vi.mocked(listArchivedDocuments).mockResolvedValue(listOf([makeDoc()]));
    renderPage();
    expect(await screen.findByText("PV du bureau du 4 octobre")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Déposer un document" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Afficher les documents retirés" })).toBeInTheDocument();
  });

  it("demande les documents retirés à l'API quand le Secrétaire les affiche, avec le badge Retiré", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("secretary"));
    vi.mocked(listArchivedDocuments).mockResolvedValue(listOf([makeDoc({ status: "withdrawn" })]));
    renderPage("/club/archives?retires=1");
    expect(await screen.findByText("Retiré")).toBeInTheDocument();
    expect(vi.mocked(listArchivedDocuments).mock.calls[0]?.[0]).toMatchObject({ includeWithdrawn: true });
  });

  it("le Bureau en lecture seule voit la bascule des documents retirés (CDC 10.3 n° 172)", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("steward"));
    vi.mocked(listArchivedDocuments).mockResolvedValue(listOf([makeDoc()]));
    renderPage("/club/archives?retires=1");
    await screen.findByText("PV du bureau du 4 octobre");
    expect(vi.mocked(listArchivedDocuments).mock.calls[0]?.[0]).toMatchObject({ includeWithdrawn: true });
    expect(screen.getByRole("button", { name: "Masquer les documents retirés" })).toBeInTheDocument();
  });

  it("applique les filtres de l'URL et charge 10 documents de plus avec « Voir plus »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("president"));
    vi.mocked(listArchivedDocuments).mockResolvedValue(listOf([makeDoc()], 10));
    renderPage("/club/archives?categorie=pv&annee=2026");
    await screen.findByText("PV du bureau du 4 octobre");
    expect(vi.mocked(listArchivedDocuments).mock.calls[0]?.[0]).toMatchObject({
      category: "pv_reunion",
      year: "2026",
      limit: 10,
    });
    await userEvent.click(screen.getByRole("button", { name: "Voir plus" }));
    await waitFor(() => {
      expect(vi.mocked(listArchivedDocuments).mock.calls.some((c) => c[0]?.limit === 20)).toBe(true);
    });
  });

  it("affiche l'erreur de chargement avec « Réessayer »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("president"));
    vi.mocked(listArchivedDocuments).mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByText("Impossible de charger les archives.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });

  it("ouvre la modale de détail puis exige un motif pour retirer", async () => {
    const doc = makeDoc();
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("vice_president"));
    vi.mocked(listArchivedDocuments).mockResolvedValue(listOf([doc]));
    vi.mocked(getArchivedDocument).mockResolvedValue(doc);
    vi.mocked(withdrawArchivedDocument).mockResolvedValue({ ...doc, status: "withdrawn" });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /PV du bureau du 4 octobre/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Retirer le document" }));
    await userEvent.click(screen.getByRole("button", { name: "Retirer" }));
    expect(await screen.findByText("Ce champ est obligatoire.")).toBeInTheDocument();
    expect(withdrawArchivedDocument).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/Motif du retrait/), "Doublon");
    await userEvent.click(screen.getByRole("button", { name: "Retirer" }));
    await waitFor(() => expect(withdrawArchivedDocument).toHaveBeenCalledWith(1, "Doublon"));
  });

  it("masque Remplacer et Retirer pour un lecteur du Bureau sans droit d'écriture", async () => {
    const doc = makeDoc();
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
    vi.mocked(listArchivedDocuments).mockResolvedValue(listOf([doc]));
    vi.mocked(getArchivedDocument).mockResolvedValue(doc);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /PV du bureau du 4 octobre/ }));
    expect(await screen.findByRole("button", { name: "Télécharger" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retirer le document" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remplacer le fichier" })).not.toBeInTheDocument();
  });
});
