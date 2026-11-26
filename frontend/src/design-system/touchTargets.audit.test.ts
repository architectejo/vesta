import { describe, expect, it } from "vitest";

/**
 * Garde-fous B7 (vérification visuelle à 360 px, CLAUDE.md règle 16,
 * docs/lot0/design-system.md §1.3) sur tout le code des écrans.
 * jsdom ne calcule pas la mise en page : on contrôle les classes à la source,
 * pour qu'un nouveau lien ou un nouveau pied collant ne réintroduise pas les
 * défauts corrigés.
 */
const SOURCES = import.meta.glob<string>(["../**/*.tsx", "!../**/*.test.tsx"], {
  query: "?raw",
  import: "default",
  eager: true,
});

/** Chaînes entre guillemets doubles (les classes Tailwind du projet le sont toutes). */
function stringLiterals(source: string): string[] {
  return source.match(/"[^"\n]*"/g) ?? [];
}

function offenders(predicate: (literal: string) => boolean): string[] {
  const found: string[] = [];
  for (const [file, source] of Object.entries(SOURCES)) {
    for (const literal of stringLiterals(source)) {
      if (predicate(literal)) found.push(`${file} : ${literal}`);
    }
  }
  return found;
}

describe("zones tactiles et pieds collants (B7)", () => {
  it("analyse bien les fichiers des écrans", () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(100);
  });

  it("chaque lien texte souligné offre une zone tactile d'au moins 36 px", () => {
    // Lien autonome : `min-h-control-sm` (36 px). Lien dans une phrase :
    // `-my-2 py-2` (20 + 16 px sans changer la ligne). Pastille : marge de clic
    // invisible `before:-inset-y-*`.
    const bad = offenders(
      (literal) =>
        /(^"|\s)(hover:)?underline(\s|"$)/.test(literal) &&
        !/\bmin-h-control-sm\b|(^"|\s)-my-2(\s|"$)|before:-inset-y-/.test(literal),
    );
    expect(bad).toEqual([]);
  });

  it("aucune puce de filtre ne descend à 32 px", () => {
    const bad = offenders((literal) => /(^"|\s)h-[5-8] rounded-full border/.test(literal));
    expect(bad).toEqual([]);
  });

  it("série 6 : boutons repérés sous 36 px à 360 px (retrait de filtre, tri, banc, pointage, préférence)", () => {
    const source = (suffix: string) => Object.entries(SOURCES).find(([file]) => file.endsWith(suffix))?.[1] ?? "";
    // Croix « Retirer le filtre … » des puces de DataTable (16 px).
    expect(source("components/DataTable.tsx")).toMatch(/Retirer le filtre \$\{chip\.label\}`\}\s*className="[^"]*\bh-9 w-9\b/);
    // Bouton de tri d'en-tête de colonne (18 px).
    expect(source("components/DataTable.tsx")).toMatch(/toggleSort\(column\.key\)\}\s*className="[^"]*\bmin-h-control-sm\b/);
    // Recherche du banc (32 px) du panneau d'équipe.
    expect(source("sport/TeamFieldPanel.tsx")).not.toMatch(/"h-8 w-full rounded-sm/);
    // « N joueurs pas encore pointés » du Vestiaire (20 px).
    expect(source("sport/VestiairePage.tsx")).toMatch(/"flex min-h-control-sm items-center gap-1 text-sm text-text"/);
    // Nom d'un joueur sans numéro ni poste dans le pointage de séance (20 px).
    expect(source("sport/SeancePage.tsx")).toMatch(/className="min-h-control-sm min-w-0 flex-1 text-left"/);
    // Interrupteur « Recevoir aussi mes notifications par email » (20 px).
    expect(source("profil/ProfilPage.tsx")).toMatch(/<label className="[^"]*\bmin-h-control-sm\b[^"]*">\s*<span>Recevoir aussi mes notifications par email/);
  });

  it("aucun pied collant de modale ne reste à `bottom-0` avec `-mb-4`", () => {
    // `bottom-0` laisse 16 px (rembourrage du corps de la modale) sous le pied :
    // le contenu y reste visible et cliquable. Correction : `-bottom-4`.
    const bad = offenders(
      (literal) => /(^"|\s)sticky(\s|"$)/.test(literal) && /(^"|\s)bottom-0(\s|"$)/.test(literal) && /(^"|\s)-mb-4(\s|"$)/.test(literal),
    );
    expect(bad).toEqual([]);
  });
});
