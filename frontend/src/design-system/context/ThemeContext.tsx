import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  deriveAccentOnSurface,
  deriveAccentPair,
  deriveClassicSidebarTokens,
  derivePlayerCardTokens,
  deriveReadableTextColor,
} from "../tokens/color-contrast";
import { LIGHT_SURFACE, LIGHT_SURFACE_MUTED } from "../tokens/light-neutrals";
import { useClubBranding } from "./ClubBrandingContext";

export type ThemeName = "classic" | "light" | "dark";

const THEME_STORAGE_KEY = "vesta:theme";
const DEFAULT_THEME: ThemeName = "classic";
const THEME_VALUES: readonly ThemeName[] = ["classic", "light", "dark"];

function isThemeName(value: string | null): value is ThemeName {
  return value !== null && (THEME_VALUES as readonly string[]).includes(value);
}

function readStoredTheme(): ThemeName {
  if (typeof window === "undefined") return DEFAULT_THEME;
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return isThemeName(stored) ? stored : DEFAULT_THEME;
}

interface ThemeContextValue {
  theme: ThemeName;
  setTheme: (theme: ThemeName) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

/** Propriétés posées en style inline sur `<html>` par le thème Classic (2.4, §7.2) ; toutes retirées hors Classic. */
const CLASSIC_ACCENT_PROPERTIES = [
  "--color-sidebar-bg",
  "--color-sidebar-text",
  "--color-sidebar-text-muted",
  "--color-sidebar-hover-bg",
  "--color-sidebar-active-bg",
  "--color-sidebar-active-text",
  "--color-primary",
  "--color-on-primary",
  "--color-primary-text",
  "--color-accent",
  // Carte de joueur (docs/ecrans/club-carte-joueur.md A6).
  "--color-player-card-from",
  "--color-player-card-to",
  "--color-player-card-fg",
  "--color-player-card-fg-muted",
  "--color-player-card-band-bg",
  "--color-player-card-band-fg",
  "--color-player-card-frame",
  "--color-player-card-frame-highlight",
] as const;

/**
 * Fournit le thème choisi par l'utilisateur (Classic / Clair / Sombre,
 * docs/lot0/design-system.md §2.4). Mémorisé en `localStorage` pour le
 * premier affichage sans flash ; la synchronisation avec la préférence de
 * compte côté API sera branchée par `frontend-dev` (tâche 1.9) une fois
 * l'API des comptes disponible — voir compte rendu.
 */
export function ThemeProvider({
  children,
  initialTheme,
}: {
  children: ReactNode;
  /** Pour les tests et la page de démonstration : force un thème initial. */
  initialTheme?: ThemeName;
}) {
  const [theme, setThemeState] = useState<ThemeName>(() => initialTheme ?? readStoredTheme());
  const branding = useClubBranding();

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    const primary = branding?.primaryColor ?? null;
    const secondary = branding?.secondaryColor ?? null;

    if (theme !== "classic" || !primary) {
      for (const property of CLASSIC_ACCENT_PROPERTIES) {
        root.style.removeProperty(property);
      }
      return;
    }

    // Repartir d'un état propre : une couleur devenue invalide ne doit pas laisser de reste.
    for (const property of CLASSIC_ACCENT_PROPERTIES) {
      root.style.removeProperty(property);
    }

    const sidebar = deriveAccentPair(primary);
    const primaryButton = deriveAccentPair(primary);
    // Un lien peut apparaître sur `--color-surface-muted` (bouton ghost
    // survolé, en-tête de tableau) : c'est le neutre le plus sombre (§7.1).
    const primaryText = deriveReadableTextColor(primary, LIGHT_SURFACE_MUTED);

    if (sidebar) {
      root.style.setProperty("--color-sidebar-bg", sidebar.bg);
      root.style.setProperty("--color-sidebar-text", sidebar.fg);
    }
    if (primaryButton) {
      root.style.setProperty("--color-primary", primaryButton.bg);
      root.style.setProperty("--color-on-primary", primaryButton.fg);
    }
    if (primaryText) {
      root.style.setProperty("--color-primary-text", primaryText);
    }
    if (sidebar && primaryText) {
      const sidebarTokens = deriveClassicSidebarTokens({
        sidebarBg: sidebar.bg,
        sidebarText: sidebar.fg,
        primaryText,
        surfaceHex: LIGHT_SURFACE,
      });
      if (sidebarTokens) {
        root.style.setProperty("--color-sidebar-text-muted", sidebarTokens.textMuted);
        root.style.setProperty("--color-sidebar-hover-bg", sidebarTokens.hoverBg);
        root.style.setProperty("--color-sidebar-active-bg", sidebarTokens.activeBg);
        root.style.setProperty("--color-sidebar-active-text", sidebarTokens.activeText);
      }
    }
    // L'accent (liseré, anneau d'avatar) ne porte jamais de texte, mais doit
    // rester visible (3:1) sur la carte : assombri sinon (§7.2).
    const accent = deriveAccentOnSurface(secondary ?? primary, LIGHT_SURFACE);
    if (accent) {
      root.style.setProperty("--color-accent", accent);
    } else {
      root.style.removeProperty("--color-accent");
    }

    // Carte de joueur (docs/ecrans/club-carte-joueur.md A6) : dérivée de la
    // même couleur primaire et du même accent, retirée si indérivable (club
    // sans couleur valide) pour garder les valeurs par défaut du Clair.
    const playerCard = derivePlayerCardTokens({ primaryHex: primary, accentHex: accent });
    if (playerCard) {
      root.style.setProperty("--color-player-card-from", playerCard.from);
      root.style.setProperty("--color-player-card-to", playerCard.to);
      root.style.setProperty("--color-player-card-fg", playerCard.fg);
      root.style.setProperty("--color-player-card-fg-muted", playerCard.fgMuted);
      root.style.setProperty("--color-player-card-band-bg", playerCard.bandBg);
      root.style.setProperty("--color-player-card-band-fg", playerCard.bandFg);
      root.style.setProperty("--color-player-card-frame", playerCard.frame);
      root.style.setProperty("--color-player-card-frame-highlight", playerCard.frameHighlight);
    }
  }, [theme, branding?.primaryColor, branding?.secondaryColor]);

  const setTheme = (next: ThemeName): void => {
    setThemeState(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    }
  };

  const value = useMemo<ThemeContextValue>(() => ({ theme, setTheme }), [theme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme doit être utilisé à l'intérieur d'un <ThemeProvider>.");
  }
  return ctx;
}

export const THEME_LABELS: Record<ThemeName, string> = {
  classic: "Classic",
  light: "Clair",
  dark: "Sombre",
};
