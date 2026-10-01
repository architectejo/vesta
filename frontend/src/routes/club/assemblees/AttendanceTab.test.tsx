import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../../design-system";
import type { Assembly } from "../../../api/assemblies";
import { AttendanceTab } from "./AttendanceTab";

vi.mock("../../../api/assemblies", async () => {
  const actual = await vi.importActual<typeof import("../../../api/assemblies")>("../../../api/assemblies");
  return {
    ...actual,
    listAttendance: vi.fn(),
    markAttendance: vi.fn(),
    removeAttendance: vi.fn(),
  };
});

import { listAttendance, markAttendance } from "../../../api/assemblies";

function makeAssembly(overrides: Partial<Assembly> = {}): Assembly {
  return {
    id: 1,
    assembly_type: "ordinary",
    scheduled_date: "2026-10-03",
    scheduled_time: "18:30:00",
    location: "Salle du club",
    status: "scheduled",
    created_at: "2026-09-01T00:00:00Z",
    agenda_items: [],
    decisions: [],
    quorum: { present: 8, total: 20, percentage: "40.00", threshold: "50", reached: false },
    minutes: null,
    can_manage: true,
    can_sign_president: false,
    can_sign_vice_president: false,
    ...overrides,
  };
}

function renderTab(assembly: Assembly) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AttendanceTab assembly={assembly} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("AttendanceTab", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche le bandeau de quorum non atteint", async () => {
    vi.mocked(listAttendance).mockResolvedValue({
      results: [],
      counts: { all: 20, present: 8, unchecked: 12 },
    });
    renderTab(makeAssembly());

    expect(
      await screen.findByText("8 présents sur 20 joueurs actifs (40.00 %) · Quorum requis : 50 % — non atteint"),
    ).toBeInTheDocument();
  });

  it("pointe un joueur présent au clic sur « Présent »", async () => {
    vi.mocked(listAttendance).mockResolvedValue({
      results: [{ membership_id: 5, first_name: "Jean", last_name: "Kabila", jersey_number: 8, present: false }],
      counts: { all: 20, present: 8, unchecked: 12 },
    });
    vi.mocked(markAttendance).mockResolvedValue(undefined);

    const user = userEvent.setup();
    renderTab(makeAssembly());

    const button = await screen.findByRole("button", { name: "Présent" });
    await user.click(button);

    await waitFor(() => expect(markAttendance).toHaveBeenCalledWith(1, 5));
  });

  it("désactive le pointage hors connexion", async () => {
    vi.mocked(listAttendance).mockResolvedValue({
      results: [{ membership_id: 5, first_name: "Jean", last_name: "Kabila", jersey_number: 8, present: false }],
      counts: { all: 20, present: 8, unchecked: 12 },
    });
    const originalOnLine = Object.getOwnPropertyDescriptor(window.navigator, "onLine");
    Object.defineProperty(window.navigator, "onLine", { value: false, configurable: true });

    renderTab(makeAssembly());

    expect(await screen.findByText("Cette action nécessite une connexion.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Présent" })).toBeDisabled();

    if (originalOnLine) Object.defineProperty(window.navigator, "onLine", originalOnLine);
  });
});
