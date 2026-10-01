import { useEffect, useRef, useState, type ReactNode } from "react";
import { useClubBranding } from "../context/ClubBrandingContext";
import { THEME_LABELS, useTheme, type ThemeName } from "../context/ThemeContext";
import { Avatar } from "./Avatar";
import { IconButton } from "./IconButton";
import { Skeleton } from "./Skeleton";

export interface SidebarNavItem {
  key: string;
  label: string;
  href: string;
  icon?: ReactNode;
}

export interface SidebarNavGroup {
  /** Titre de groupe (13 px, muted) ; absent pour le premier groupe (3.9). */
  title?: string;
  items: SidebarNavItem[];
}

export interface SidebarUser {
  name: string;
  roleLabel: string;
  photoUrl?: string | null;
}

export interface SidebarProps {
  groups: SidebarNavGroup[];
  currentPath: string;
  user: SidebarUser;
  profileHref: string;
  onNavigate: (href: string) => void;
  onLogout: () => void;
  /** Squelette pendant le chargement de l'identité du club. */
  brandLoading?: boolean;
  /** Emplacement pour SyncIndicator / NotificationBell (tâches suivantes). */
  topbarRight?: ReactNode;
}

function clubInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((p) => p[0] ?? "")
    .join("")
    .toUpperCase();
}

function ClubBrand({ size, loading }: { size: 28 | 40; loading?: boolean }) {
  const branding = useClubBranding();
  const boxClass = size === 40 ? "h-10 w-10" : "h-7 w-7";

  if (loading) {
    return <Skeleton variant="row" className={[boxClass, "shrink-0"].join(" ")} />;
  }

  if (!branding) {
    return (
      <span
        className={[
          boxClass,
          "flex shrink-0 items-center justify-center rounded-md bg-sidebar-text/10 text-sm font-semibold text-sidebar-text",
        ].join(" ")}
      >
        ?
      </span>
    );
  }

  return (
    <div className="flex min-w-0 items-center gap-2">
      {branding.logoUrl ? (
        <img
          src={branding.logoUrl}
          alt={branding.name}
          className={[boxClass, "shrink-0 rounded-md object-cover"].join(" ")}
        />
      ) : (
        <span
          className={[
            boxClass,
            "flex shrink-0 items-center justify-center rounded-md bg-sidebar-text/10 text-sm font-semibold text-sidebar-text",
          ].join(" ")}
        >
          {clubInitials(branding.name)}
        </span>
      )}
      <span
        className="truncate text-base font-semibold text-sidebar-text"
        title={branding.name}
      >
        {branding.name}
      </span>
    </div>
  );
}

function ThemeMenu() {
  const { theme, setTheme } = useTheme();
  const names: ThemeName[] = ["classic", "light", "dark"];
  return (
    <div className="py-1">
      <p className="px-3 py-1 text-xs text-text-muted">Thème</p>
      {names.map((name) => (
        <button
          key={name}
          type="button"
          onClick={() => setTheme(name)}
          aria-current={theme === name || undefined}
          className={[
            "flex w-full items-center px-3 py-2 text-left text-sm hover:bg-surface-muted",
            theme === name ? "font-medium text-primary-text" : "text-text",
          ].join(" ")}
        >
          {THEME_LABELS[name]}
        </button>
      ))}
    </div>
  );
}

function NavList({
  groups,
  currentPath,
  onNavigate,
}: {
  groups: SidebarNavGroup[];
  currentPath: string;
  onNavigate: (href: string) => void;
}) {
  return (
    <nav className="flex-1 overflow-y-auto px-2 py-2">
      {groups.map((group, groupIndex) => (
        <div key={group.title ?? `group-${groupIndex}`} className="mb-3">
          {group.title ? (
            <p className="px-2 py-1 text-xs text-sidebar-text-muted">{group.title}</p>
          ) : null}
          <ul>
            {group.items.map((item) => {
              const active = currentPath === item.href;
              return (
                <li key={item.key}>
                  <a
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={(e) => {
                      e.preventDefault();
                      onNavigate(item.href);
                    }}
                    className={[
                      "flex h-10 items-center gap-2 rounded-sm border-l-[3px] px-2 text-sm",
                      active
                        ? "border-accent bg-sidebar-active-bg font-medium text-sidebar-active-text"
                        : "border-transparent text-sidebar-text hover:bg-sidebar-hover-bg",
                    ].join(" ")}
                  >
                    {item.icon}
                    <span className="truncate">{item.label}</span>
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function UserBar({
  user,
  profileHref,
  onNavigate,
  onLogout,
}: {
  user: SidebarUser;
  profileHref: string;
  onNavigate: (href: string) => void;
  onLogout: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuOpen) return undefined;
    function handleClick(event: MouseEvent): void {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function handleKey(event: KeyboardEvent): void {
      if (event.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [menuOpen]);

  return (
    <div ref={menuRef} className="relative border-t border-border px-2 py-2">
      <div className="flex h-14 items-center gap-2">
        <Avatar name={user.name} photoUrl={user.photoUrl} size={32} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-sidebar-text" title={user.name}>
            {user.name}
          </p>
          <p className="truncate text-xs text-sidebar-text-muted">{user.roleLabel}</p>
        </div>
        <IconButton
          variant="sidebar"
          aria-label="Ouvrir le menu utilisateur"
          onClick={() => setMenuOpen((v) => !v)}
          icon={
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
              <circle cx="5" cy="12" r="1.5" />
              <circle cx="12" cy="12" r="1.5" />
              <circle cx="19" cy="12" r="1.5" />
            </svg>
          }
        />
      </div>
      {menuOpen ? (
        <div className="absolute bottom-full left-2 right-2 mb-1 rounded-md border border-border bg-surface py-1 shadow-elevated">
          <button
            type="button"
            onClick={() => {
              setMenuOpen(false);
              onNavigate(profileHref);
            }}
            className="flex w-full items-center px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
          >
            Mon profil
          </button>
          <ThemeMenu />
          <button
            type="button"
            onClick={onLogout}
            className="flex w-full items-center px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
          >
            Se déconnecter
          </button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Navigation principale et identité du club connecté (docs/lot0/design-system.md
 * §3.9). Logo et nom toujours lus de l'API (contexte `ClubBrandingContext`) :
 * aucun nom ni logo de club dans le code.
 */
export function Sidebar({
  groups,
  currentPath,
  user,
  profileHref,
  onNavigate,
  onLogout,
  brandLoading = false,
  topbarRight,
}: SidebarProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (!drawerOpen) return undefined;
    function handleKey(event: KeyboardEvent): void {
      if (event.key === "Escape") setDrawerOpen(false);
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [drawerOpen]);

  function handleNavigate(href: string): void {
    setDrawerOpen(false);
    onNavigate(href);
  }

  return (
    <>
      {/* Barre supérieure mobile (< 1024 px) */}
      <header className="flex h-topbar items-center gap-2 border-b border-border bg-sidebar-bg px-3 lg:hidden">
        <IconButton
          variant="sidebar"
          aria-label="Ouvrir le menu"
          onClick={() => setDrawerOpen(true)}
          icon={
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
            </svg>
          }
        />
        <ClubBrand size={28} loading={brandLoading} />
        <div className="ml-auto flex items-center gap-1">{topbarRight}</div>
      </header>

      {/* Tiroir mobile */}
      {drawerOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-overlay"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className="relative flex h-full w-[280px] max-w-[85vw] flex-col bg-sidebar-bg">
            <div className="flex items-center justify-between p-3">
              <ClubBrand size={40} loading={brandLoading} />
              <IconButton
                variant="sidebar"
                aria-label="Fermer"
                onClick={() => setDrawerOpen(false)}
                icon={
                  <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                  </svg>
                }
              />
            </div>
            <NavList groups={groups} currentPath={currentPath} onNavigate={handleNavigate} />
            <UserBar
              user={user}
              profileHref={profileHref}
              onNavigate={handleNavigate}
              onLogout={onLogout}
            />
          </div>
        </div>
      ) : null}

      {/* Barre latérale fixe (>= 1024 px) */}
      <aside className="hidden w-sidebar shrink-0 flex-col bg-sidebar-bg lg:fixed lg:inset-y-0 lg:left-0 lg:flex">
        <div className="p-3">
          <ClubBrand size={40} loading={brandLoading} />
        </div>
        <NavList groups={groups} currentPath={currentPath} onNavigate={onNavigate} />
        <UserBar
          user={user}
          profileHref={profileHref}
          onNavigate={onNavigate}
          onLogout={onLogout}
        />
      </aside>
    </>
  );
}
