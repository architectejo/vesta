import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ClubPlayerListItem, MembershipRole, MyProfile } from "../../api/clubs";
import { ToastProvider } from "../../design-system";
import { ComiteBureauPage } from "./ComiteBureauPage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return {
    ...actual,
    getMyProfile: vi.fn(),
    getClubIdentity: vi.fn(),
    listRoles: vi.fn(),
    listClubPlayers: vi.fn(),
    getPlayerCard: vi.fn(),
  };
});

import { getClubIdentity, getMyProfile, getPlayerCard, listClubPlayers, listRoles } from "../../api/clubs";

function makeProfile(): MyProfile {
  return {
    membership_id: 1,
    club: { id: 1, slug: "test", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    identity: {
      first_name: "Jean", last_name: "Coach", photo: null, email: "j@example.com", phone: "",
      birth_date: null, weight_kg: null, height_cm: null,
    },
    position: "midfielder",
    position_label: "Milieu",
    position_detail: "",
    jersey_number: null,
    membership_status: "active",
    membership_status_label: "Inscrit",
    roles: [{ role: "coach", label: "Coach" }],
    email_notifications_enabled: true,
  } as MyProfile;
}

function makePlayer(id: number, first: string, last: string): ClubPlayerListItem {
  return {
    membership_id: id, first_name: first, last_name: last, photo: null, position: "midfielder",
    position_label: "Milieu", position_detail: "", jersey_number: id, membership_status: "active",
    membership_status_label: "Inscrit", roles: [],
  };
}

function makeRole(id: number, membershipId: number, role: string): MembershipRole {
  return {
    id, membership_id: membershipId, role, role_label: role, effective_label: role,
    is_qualified_professional: null, appointed_by_id: 1, appointed_at: "2026-01-01T00:00:00Z",
    revoked_by_id: null, revoked_at: null, revoked_reason: "",
  };
}

describe("ComiteBureauPage - résolution des noms", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getClubIdentity).mockResolvedValue({
      name: "Club de test", city: "Kinshasa", country: "RDC", currency: "USD", timezone: "Africa/Kinshasa",
      logo: null, payment_link_url: "",
    } as never);
  });

  it("affiche les noms depuis la liste de l'effectif, sans requête de fiche par membre", async () => {
    vi.mocked(listRoles).mockResolvedValue([
      makeRole(1, 11, "president"),
      makeRole(2, 12, "assistant_coach"),
      makeRole(3, 13, "captain"),
    ]);
    vi.mocked(listClubPlayers).mockResolvedValue([
      makePlayer(11, "Alice", "Mukendi"),
      makePlayer(12, "Blaise", "Kasongo"),
      makePlayer(13, "Cédric", "Ilunga"),
    ]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter>
            <ComiteBureauPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Assistant du Coach" })).toBeInTheDocument();
    expect((await screen.findAllByText("Blaise Kasongo")).length).toBeGreaterThan(0);
    expect(getPlayerCard).not.toHaveBeenCalled();
  });
});
