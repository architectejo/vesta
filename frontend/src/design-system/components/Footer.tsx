/**
 * Texte exact et unique (CLAUDE.md §2.19, docs/lot0/design-system.md §3.10).
 * Seule occurrence du nom de l'Éditeur dans tout le code de l'interface.
 */
export const FOOTER_TEXT =
  "VESTA by IMARA TECH Group — une partie de nos revenus est destinée aux orphelinats locaux";

/**
 * Pied de page unique, affiché sur toutes les pages, non collant (§3.10).
 */
export function Footer() {
  return (
    <footer className="mt-8 border-t border-border px-4 py-4 text-center text-xs text-text-muted">
      {FOOTER_TEXT}
    </footer>
  );
}
