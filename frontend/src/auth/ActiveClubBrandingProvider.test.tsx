import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../api/clubs";
import { ThemeProvider } from "../design-system";
import { ActiveClubBrandingProvider } from "./ActiveClubBrandingProvider";

// Régression : avant ce correctif, `ThemeProvider` était le PARENT de
// `ClubBrandingProvider` dans `main.tsx` réel (celui-ci n'était posé que par
// `AppLayout`, un descendant de `ThemeProvider`). `useContext` ne remonte
// jamais un arbre React : `ThemeProvider` recevait donc toujours `branding:
// null` et ne posait jamais les variables CSS globales du thème Classic
// (--color-primary, --color-sidebar-bg…), quel que soit le club connecté.
// Ce test reconstruit la VRAIE imbrication de `main.tsx`
// (`ActiveClubBrandingProvider` au-dessus de `ThemeProvider`) pour garantir
// que la régression ne revienne pas.

let mockAuth: {
  status: "anonymous" | "authenticated";
  user: {
    id: number;
    email: string;
    first_name: string;
    last_name: string;
    is_superuser: boolean;
    must_change_password?: boolean;
  } | null;
  club: {
    id: number;
    slug: string;
    name: string;
    logo: string | null;
    primary_color: string;
    secondary_color: string;
  } | null;
};

vi.mock("./AuthContext", () => ({
  useAuth: () => mockAuth,
}));

vi.mock("../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../api/clubs")>("../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

import { getMyProfile } from "../api/clubs";

// Couleurs synthétiques (marine et rouge) : donnée de test uniquement.
const CLUB_MEMBER_AUTH = {
  status: "authenticated" as const,
  user: { id: 1, email: "j@example.com", first_name: "Jean", last_name: "Kabila", is_superuser: false },
  club: {
    id: 4,
    slug: "malaika",
    name: "Fc Malaïka",
    logo: null,
    primary_color: "#1B2143",
    secondary_color: "#D2232A",
  },
};

const FRESH_PROFILE: MyProfile = {
  membership_id: 1,
  club: {
    id: 4,
    slug: "malaika",
    name: "Fc Malaïka",
    logo: null,
    primary_color: "#1B2143",
    secondary_color: "#D2232A",
  },
  identity: {
    first_name: "Jean",
    last_name: "Kabila",
    photo: null,
    email: "j@example.com",
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
  roles: [{ role: "player", label: "Joueur" }],
  email_notifications_enabled: true,
};

function renderTree() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      {/* Même imbrication que `main.tsx` : `ThemeProvider` DANS `ActiveClubBrandingProvider`. */}
      <ActiveClubBrandingProvider>
        <ThemeProvider>
          <div>contenu</div>
        </ThemeProvider>
      </ActiveClubBrandingProvider>
    </QueryClientProvider>,
  );
}

describe("ActiveClubBrandingProvider — variables CSS globales du thème Classic", () => {
  afterEach(() => {
    vi.clearAllMocks();
    document.documentElement.removeAttribute("style");
    document.documentElement.removeAttribute("data-theme");
  });

  it("pose les vraies couleurs du club sur <html> pour un membre de club authentifié", async () => {
    mockAuth = CLUB_MEMBER_AUTH;
    vi.mocked(getMyProfile).mockResolvedValue(FRESH_PROFILE);

    renderTree();

    await waitFor(() =>
      expect(document.documentElement.style.getPropertyValue("--color-sidebar-bg")).toBe("#1b2143"),
    );
    expect(document.documentElement.style.getPropertyValue("--color-primary")).not.toBe("");
    expect(document.documentElement.style.getPropertyValue("--color-accent")).not.toBe("");
  });

  it("retombe sur l'instantané de connexion tant que le profil n'a pas encore chargé", () => {
    mockAuth = CLUB_MEMBER_AUTH;
    vi.mocked(getMyProfile).mockReturnValue(new Promise(() => {}));

    renderTree();

    expect(document.documentElement.style.getPropertyValue("--color-sidebar-bg")).toBe("#1b2143");
  });

  it("reste neutre sans session (page de connexion)", () => {
    mockAuth = { status: "anonymous", user: null, club: null };

    renderTree();

    expect(document.documentElement.getAttribute("style") ?? "").toBe("");
    expect(getMyProfile).not.toHaveBeenCalled();
  });

  it("reste neutre en espace Superuser, même si un club était mémorisé", () => {
    mockAuth = {
      status: "authenticated",
      user: { id: 9, email: "admin@example.com", first_name: "Admin", last_name: "Vesta", is_superuser: true },
      club: CLUB_MEMBER_AUTH.club,
    };

    renderTree();

    expect(document.documentElement.getAttribute("style") ?? "").toBe("");
    expect(getMyProfile).not.toHaveBeenCalled();
  });

  it("ne demande pas le profil tant que le mot de passe provisoire n'est pas changé (série 6)", () => {
    mockAuth = { ...CLUB_MEMBER_AUTH, user: { ...CLUB_MEMBER_AUTH.user, must_change_password: true } };

    renderTree();

    expect(getMyProfile).not.toHaveBeenCalled();
    expect(document.documentElement.style.getPropertyValue("--color-sidebar-bg")).toBe("#1b2143");
  });
});
