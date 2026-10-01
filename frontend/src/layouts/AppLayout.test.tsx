import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../api/clubs";
import { useClubBranding } from "../design-system";
import { AppLayout } from "./AppLayout";

// Bug remarques.md : après que le Président modifie « Couleur principale »/
// « Couleur secondaire » dans Identité du club (ClubIdentityModal.tsx), le
// thème Classic affichait des couleurs de club périmées tant que l'onglet
// n'était pas rechargé. Cause : `branding.primaryColor`/`secondaryColor` ne
// retombaient que sur `auth.club` (instantané posé une seule fois au login),
// jamais sur `profileQuery.data` (rafraîchi après édition). Ce test couvre
// uniquement ce calcul, pas le reste de l'écran.

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: { id: 1, email: "p@example.com", first_name: "Jean", last_name: "Kabila" },
    // Instantané périmé posé au login : couleurs différentes de celles du profil à jour.
    club: {
      id: 1,
      slug: "discovery",
      name: "Loisirs Club Discovery",
      logo: null,
      primary_color: "#111111",
      secondary_color: "#222222",
    },
    logout: vi.fn(),
  }),
}));

vi.mock("../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../api/clubs")>("../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

import { getMyProfile } from "../api/clubs";

const FRESH_PROFILE: MyProfile = {
  membership_id: 1,
  club: {
    id: 1,
    slug: "discovery",
    name: "Loisirs Club Discovery",
    logo: null,
    // Couleurs mises à jour par le Président, après édition du profil.
    primary_color: "#1b2143",
    secondary_color: "#d2232a",
  },
  identity: {
    first_name: "Jean",
    last_name: "Kabila",
    photo: null,
    email: "p@example.com",
    phone: "",
    birth_date: null,
    weight_kg: null,
    height_cm: null,
  },
  position: "",
  position_label: "",
  position_detail: "",
  jersey_number: null,
  membership_status: "active",
  membership_status_label: "Actif",
  roles: [{ role: "president", label: "Président" }],
  email_notifications_enabled: true,
};

function BrandingProbe() {
  const branding = useClubBranding();
  return (
    <div>
      <span data-testid="primary">{branding?.primaryColor ?? ""}</span>
      <span data-testid="secondary">{branding?.secondaryColor ?? ""}</span>
    </div>
  );
}

function renderLayout() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AppLayout>
          <BrandingProbe />
        </AppLayout>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AppLayout — branding (couleurs Classic)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("utilise les couleurs à jour du profil, pas l'instantané périmé de la connexion", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(FRESH_PROFILE);
    renderLayout();

    await waitFor(() => expect(screen.getByTestId("primary")).toHaveTextContent("#1b2143"));
    expect(screen.getByTestId("secondary")).toHaveTextContent("#d2232a");
  });

  it("retombe sur l'instantané de connexion tant que le profil n'a pas encore chargé", () => {
    vi.mocked(getMyProfile).mockReturnValue(new Promise(() => {}));
    renderLayout();

    expect(screen.getByTestId("primary")).toHaveTextContent("#111111");
    expect(screen.getByTestId("secondary")).toHaveTextContent("#222222");
  });
});
