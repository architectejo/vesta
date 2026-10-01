import { deriveAccentPair } from "../../design-system";

const HEX_RE = /^#[0-9A-Fa-f]{6}$/;

/**
 * Aperçu en direct de la modale « Identité du club »
 * (club-comite-bureau.md §4.1) : mini barre latérale (logo, nom, élément
 * actif) et bouton principal aux couleurs choisies. Si l'ajustement de
 * lisibilité (`deriveAccentPair`) assombrit la couleur choisie, la mention
 * correspondante s'affiche.
 */
export function ClubIdentityPreview({
  logoUrl,
  name,
  primaryColor,
}: {
  logoUrl: string | null;
  name: string;
  primaryColor: string;
}) {
  const pair = HEX_RE.test(primaryColor) ? deriveAccentPair(primaryColor) : null;
  const buttonBg = pair?.bg ?? (HEX_RE.test(primaryColor) ? primaryColor : "#1D4ED8");
  const buttonFg = pair?.fg ?? "#ffffff";
  const adjusted = pair !== null && pair.bg.toLowerCase() !== primaryColor.toLowerCase();

  return (
    <div>
      <p className="mb-1 text-sm font-medium text-text">Aperçu</p>
      <div className="flex items-center gap-3 rounded-md border border-border p-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-md bg-surface-muted">
          {logoUrl ? (
            <img src={logoUrl} alt="" className="h-full w-full object-cover" />
          ) : (
            <span className="text-[9px] text-text-muted">Logo</span>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-text">{name || "Votre club"}</p>
          <span
            className="mt-1 inline-block rounded-sm px-2 py-0.5 text-xs font-medium"
            style={{ backgroundColor: buttonBg, color: buttonFg }}
          >
            Effectif
          </span>
        </div>
        <span
          className="shrink-0 rounded-sm px-3 py-1 text-xs font-medium"
          style={{ backgroundColor: buttonBg, color: buttonFg }}
        >
          Bouton principal
        </span>
      </div>
      {adjusted ? (
        <p className="mt-1 text-xs text-text-muted">
          Pour rester lisible, la teinte sera légèrement assombrie à l&apos;affichage.
        </p>
      ) : null}
    </div>
  );
}
