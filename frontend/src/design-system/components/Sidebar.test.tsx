import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ClubBrandingProvider, type ClubBranding } from "../context/ClubBrandingContext";
import { ThemeProvider } from "../context/ThemeContext";
import { Sidebar, type SidebarNavGroup } from "./Sidebar";

const FICTITIOUS_BRANDING: ClubBranding = {
  name: "Club de démonstration",
  logoUrl: null,
  primaryColor: "#1D4ED8",
  secondaryColor: "#F97316",
};

const GROUPS: SidebarNavGroup[] = [
  {
    items: [
      { key: "home", label: "Accueil", href: "/accueil" },
      { key: "profile", label: "Mon profil", href: "/profil" },
    ],
  },
  {
    title: "Trésorerie",
    items: [{ key: "dashboard", label: "Tableau de bord", href: "/tresorerie" }],
  },
];

function renderSidebar(props?: { currentPath?: string }) {
  const onNavigate = vi.fn();
  const onLogout = vi.fn();
  render(
    <ClubBrandingProvider branding={FICTITIOUS_BRANDING}>
      <ThemeProvider initialTheme="light">
        <Sidebar
          groups={GROUPS}
          currentPath={props?.currentPath ?? "/accueil"}
          user={{ name: "Jean Kabila", roleLabel: "Trésorier" }}
          profileHref="/profil"
          onNavigate={onNavigate}
          onLogout={onLogout}
        />
      </ThemeProvider>
    </ClubBrandingProvider>,
  );
  return { onNavigate, onLogout };
}

describe("Sidebar", () => {
  it("affiche le nom du club depuis le contexte (jamais en dur)", () => {
    renderSidebar();
    expect(screen.getAllByText("Club de démonstration").length).toBeGreaterThan(0);
  });

  it("marque l'élément de navigation actif avec aria-current", () => {
    renderSidebar({ currentPath: "/tresorerie" });
    const link = screen.getByText("Tableau de bord").closest("a");
    expect(link).toHaveAttribute("aria-current", "page");
  });

  it("utilise les jetons de barre latérale (jamais text-muted ni surface-muted, illisibles sur fond foncé)", () => {
    renderSidebar({ currentPath: "/tresorerie" });

    const active = screen.getAllByText("Tableau de bord")[0]!.closest("a")!;
    expect(active).toHaveClass("bg-sidebar-active-bg", "text-sidebar-active-text", "border-accent");

    const inactive = screen.getAllByText("Accueil")[0]!.closest("a")!;
    expect(inactive).toHaveClass("text-sidebar-text", "hover:bg-sidebar-hover-bg");
    expect(inactive).not.toHaveClass("hover:bg-surface-muted");

    expect(screen.getAllByText("Trésorerie")[0]).toHaveClass("text-sidebar-text-muted");
    expect(screen.getAllByText("Trésorier")[0]).toHaveClass("text-sidebar-text-muted");
    expect(screen.getAllByText("Trésorier")[0]).not.toHaveClass("text-text-muted");
  });

  it("ancre la barre fixe au bord gauche (sinon elle chevauche le contenu décalé par le layout)", () => {
    renderSidebar();
    const aside = screen.getByText("Tableau de bord").closest("aside")!;
    expect(aside).toHaveClass("lg:fixed", "lg:inset-y-0", "lg:left-0", "w-sidebar");
  });

  it("appelle onNavigate au clic sur un élément de navigation (barre fixe)", async () => {
    const user = userEvent.setup();
    const { onNavigate } = renderSidebar();
    const links = screen.getAllByText("Mon profil");
    await user.click(links[0]!);
    expect(onNavigate).toHaveBeenCalledWith("/profil");
  });

  it("ouvre le tiroir mobile puis le referme avec Échap", async () => {
    const user = userEvent.setup();
    renderSidebar();
    await user.click(screen.getByRole("button", { name: "Ouvrir le menu" }));
    expect(screen.getByRole("button", { name: "Fermer" })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    // Le tiroir reste monté pendant son animation de fermeture
    // (design-system-icones-animations.md §2.2 : démontage différé).
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Fermer" })).not.toBeInTheDocument(),
    );
  });

  it("ouvre le menu utilisateur et déclenche la déconnexion", async () => {
    const user = userEvent.setup();
    const { onLogout } = renderSidebar();
    const menuButtons = screen.getAllByRole("button", { name: "Ouvrir le menu utilisateur" });
    await user.click(menuButtons[menuButtons.length - 1]!);

    const logoutButtons = screen.getAllByRole("button", { name: "Se déconnecter" });
    await user.click(logoutButtons[logoutButtons.length - 1]!);
    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it("propose les trois thèmes dans le menu utilisateur", async () => {
    const user = userEvent.setup();
    renderSidebar();
    const menuButtons = screen.getAllByRole("button", { name: "Ouvrir le menu utilisateur" });
    await user.click(menuButtons[menuButtons.length - 1]!);

    const menus = screen.getAllByText("Thème");
    const panel = menus[menus.length - 1]!.closest("div");
    expect(panel).not.toBeNull();
    expect(within(panel!).getByText("Classic")).toBeInTheDocument();
    expect(within(panel!).getByText("Clair")).toBeInTheDocument();
    expect(within(panel!).getByText("Sombre")).toBeInTheDocument();
  });
});
