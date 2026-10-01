export type AvatarSize = 24 | 32 | 40 | 72;

export interface AvatarProps {
  /** Nom complet, utilisé pour les initiales et le texte alternatif. */
  name: string;
  photoUrl?: string | null;
  size?: AvatarSize;
  className?: string;
}

const SIZE_PX: Record<AvatarSize, string> = {
  24: "h-6 w-6 text-[10px]",
  32: "h-8 w-8 text-xs",
  40: "h-10 w-10 text-sm",
  72: "h-[72px] w-[72px] text-lg",
};

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase();
}

/**
 * Avatar rond : photo, ou à défaut initiales sur fond neutre
 * (docs/lot0/design-system.md §3.1). Affiché partout où un nom de joueur
 * apparaît.
 */
export function Avatar({ name, photoUrl, size = 40, className = "" }: AvatarProps) {
  const base = [
    "inline-flex shrink-0 items-center justify-center rounded-full font-medium",
    "bg-surface-muted text-text-muted",
    SIZE_PX[size],
    className,
  ].join(" ");

  if (photoUrl) {
    return <img src={photoUrl} alt={name} className={[base, "object-cover"].join(" ")} />;
  }

  return (
    <span className={base} role="img" aria-label={name}>
      {initialsOf(name)}
    </span>
  );
}
