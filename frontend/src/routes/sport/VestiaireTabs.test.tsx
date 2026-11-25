import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import { ToastProvider } from "../../design-system";
import { VestiairePage } from "./VestiairePage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, getLockerRoom: vi.fn(), listTacticalPlans: vi.fn(), getTacticalPlan: vi.fn() };
});

import { getMyProfile } from "../../api/clubs";
import { getLockerRoom, getTacticalPlan, listTacticalPlans } from "../../api/sport";

const PROFILE = {
  membership_id: 1,
  club: { id: 1, slug: "t", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
  identity: { first_name: "J", last_name: "M", photo: null, email: "j@e.com", phone: "", birth_date: null, weight_kg: null, height_cm: null },
  position: "",
  position_label: "",
  position_detail: "",
  jersey_number: null,
  membership_status: "active",
  membership_status_label: "Inscrit",
  roles: [],
  email_notifications_enabled: true,
} as MyProfile;

const PLAN = {
  id: 3,
  name: "Plan C",
  formation: "4-4-2" as const,
  squad_size: 11 as const,
  match_id: null,
  is_published: true,
  published_at: null,
  updated_at: "2026-09-01T00:00:00Z",
};

function renderPage(entry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[entry]}>
          <VestiairePage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("VestiairePage — onglets Aujourd'hui / Plans", () => {
  it("les plans restent accessibles un jour sans événement", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(PROFILE);
    vi.mocked(getLockerRoom).mockResolvedValue({ session: null, match: null, my_situation: null, next_event: null });
    vi.mocked(listTacticalPlans).mockResolvedValue({ count: 1, next_offset: null, results: [PLAN] });
    renderPage("/vestiaire");
    expect(await screen.findByText("Aucune séance ni aucun match aujourd'hui.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Plans" }));
    expect(await screen.findByText("Plan C")).toBeInTheDocument();
  });

  it("?onglet=plans ouvre directement l'onglet Plans, et ?plan= ouvre le plan", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(PROFILE);
    vi.mocked(listTacticalPlans).mockResolvedValue({ count: 1, next_offset: null, results: [PLAN] });
    vi.mocked(getTacticalPlan).mockReturnValue(new Promise(() => undefined));
    renderPage("/vestiaire?onglet=plans&plan=3");
    await vi.waitFor(() => expect(getTacticalPlan).toHaveBeenCalledWith(3));
  });
});
