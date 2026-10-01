import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

/**
 * Sélectionne un joueur dans un composant `PlayerSearch` du design system
 * (CLAUDE.md §2.15 : jamais de `<select>` pour choisir un joueur — un champ
 * de recherche avec suggestions). `container` restreint la recherche à une
 * zone précise de la page (une modale ouverte, en général) pour ne pas
 * confondre plusieurs champs de recherche affichés en même temps.
 */
export async function pickPlayerFromSearch(
  page: Page,
  container: ReturnType<Page["locator"]>,
  query: string,
): Promise<void> {
  const input = container.getByPlaceholder("Nom ou numéro du joueur").first();
  await input.click();
  await input.fill(query);
  const option = container.getByRole("option").first();
  await expect(option).toBeVisible({ timeout: 8_000 });
  await option.click();
}

/** Saisit le code PIN dans la boîte modale `PinPrompt` du design system. */
export async function fillPin(page: Page, pin: string): Promise<void> {
  const input = page.getByLabel("Votre code PIN");
  await input.fill(pin);
}
