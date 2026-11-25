import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuditLogDetail, AuditLogLine, AuditLogPage } from "../../api/audit";
import { ToastProvider } from "../../design-system";
import { JournalPage } from "./JournalPage";

vi.mock("../../api/audit", async () => {
  const actual = await vi.importActual<typeof import("../../api/audit")>("../../api/audit");
  return {
    ...actual,
    listAuditLogs: vi.fn(),
    getAuditLog: vi.fn(),
    listAuditActionTypes: vi.fn(),
    exportAuditLogs: vi.fn(),
  };
});
vi.mock("../../api/licences", () => ({ listLicences: vi.fn().mockResolvedValue([]) }));
vi.mock("../../api/auth", () => ({ searchAccounts: vi.fn().mockResolvedValue([]) }));

import { getAuditLog, listAuditActionTypes, listAuditLogs } from "../../api/audit";

function line(id: number, over: Partial<AuditLogLine> = {}): AuditLogLine {
  return {
    id,
    created_at: "2026-10-01T22:30:00Z",
    club_id: 1,
    club_name: "Club Test",
    club_timezone: "Africa/Kinshasa",
    actor_id: 5,
    actor_display: "Jean Dupont",
    acted_as_ghost: false,
    support_session_id: null,
    action_type: "payment.validated",
    object_type: "Payment",
    object_id: String(id),
    is_alert: false,
    ...over,
  };
}

function page(results: AuditLogLine[], next: string | null = null, count = results.length): AuditLogPage {
  return { count, next, previous: null, results };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <JournalPage />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("JournalPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAuditActionTypes).mockResolvedValue({ results: [] });
  });

  it("affiche l'heure dans le fuseau du club et la mention support", async () => {
    vi.mocked(listAuditLogs).mockResolvedValue(page([line(1, { acted_as_ghost: true, is_alert: true })]));
    renderPage();
    expect(await screen.findByText(/Jean Dupont \(support\)/)).toBeInTheDocument();
    // 22:30 UTC = 23:30 à Kinshasa (UTC+1)
    expect(screen.getByText(/23:30:00/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Alerte" })).toBeInTheDocument();
  });

  it("charge la page suivante avec « Voir plus »", async () => {
    vi.mocked(listAuditLogs)
      .mockResolvedValueOnce(page([line(1)], "http://x/?page=2", 2))
      .mockResolvedValueOnce(page([line(2)], null, 2));
    renderPage();
    await screen.findByText("Voir plus");
    await userEvent.click(screen.getByText("Voir plus"));
    await waitFor(() => expect(screen.getAllByText("Jean Dupont")).toHaveLength(2));
    expect(screen.queryByText("Voir plus")).not.toBeInTheDocument();
    expect(vi.mocked(listAuditLogs).mock.calls[1]?.[1]).toBe(2);
  });

  it("affiche l'état vide et l'erreur avec Réessayer", async () => {
    vi.mocked(listAuditLogs).mockRejectedValueOnce(new Error("boom")).mockResolvedValue(page([]));
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Réessayer" }));
    expect(await screen.findByText("Aucune entrée pour ces filtres.")).toBeInTheDocument();
  });

  it("ouvre la modale de détail avec avant/après", async () => {
    vi.mocked(listAuditLogs).mockResolvedValue(page([line(1)]));
    const detail: AuditLogDetail = {
      ...line(1),
      support_session: null,
      before: { amount: "10" },
      after: { amount: "20" },
      medical_content_withheld: false,
      ip_address: "10.0.0.1",
      user_agent: "UA",
      device: "Mobile",
    };
    vi.mocked(getAuditLog).mockResolvedValue(detail);
    renderPage();
    await userEvent.click(await screen.findByText("Jean Dupont"));
    expect(await screen.findByText("Entrée du journal")).toBeInTheDocument();
    expect(await screen.findByText("20")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
  });

  it("masque avant/après pour une entrée médicale", async () => {
    vi.mocked(listAuditLogs).mockResolvedValue(page([line(1)]));
    vi.mocked(getAuditLog).mockResolvedValue({
      ...line(1),
      support_session: { id: 3, reason: "Aide" },
      before: null,
      after: null,
      medical_content_withheld: true,
      ip_address: null,
      user_agent: "",
      device: "",
    });
    renderPage();
    await userEvent.click(await screen.findByText("Jean Dupont"));
    expect(await screen.findByText("Contenu médical non copié dans le journal.")).toBeInTheDocument();
    expect(screen.getByText(/Motif : Aide/)).toBeInTheDocument();
  });
});
