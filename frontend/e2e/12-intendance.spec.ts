import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect, type Browser, type Locator, type Page } from "@playwright/test";
import { loginAs } from "./support/auth";

/**
 * Tâche B4 — vérification VISUELLE à 360 px (et 320 px) et parcours
 * fonctionnels des écrans de l'intendance (spec
 * `docs/ecrans/logistique-intendance-registre.md` §3, §4, §5, §7, §10, §14,
 * §15), contre les vrais serveurs de dev et la base locale de DÉMONSTRATION
 * (club fictif « Club Démo », comptes `@demo.local`).
 *
 * Les données sont créées PAR L'INTERFACE en tant qu'Intendant
 * (`joueur13@demo.local`) : détenteurs (lieu, joueur), entrées avec
 * provenance, transfert, signalement puis sortie d'un déclassement,
 * annulation d'un autre. Les noms de lieu portent un suffixe propre à
 * l'exécution : le parcours peut être rejoué sans heurter la règle « Ce lieu
 * existe déjà. ».
 *
 * Captures et relevés JSON : `frontend/test-results/intendance-360/`
 * (ignoré par Git). Contrôles automatiques de la charte (CDC chapitre 3,
 * CLAUDE.md §2.13–2.20) : défilement horizontal, cibles < 36 px, polices
 * hors 12–24 px, textes coupés, pied collant qui masque du contenu, et
 * EMPILEMENT des modales (la modale du dessus reçoit bien les clics).
 */

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.resolve(__dirname, "../test-results/intendance-360");
const WIDTHS = [360, 320] as const;
const INTENDANT = "joueur13@demo.local";
// Suffixe stable entre les groupes lancés séparément (`--grep`) :
// `INTENDANCE_RUN=AB12 npx playwright test …`.
const RUN = process.env.INTENDANCE_RUN ?? Date.now().toString(36).slice(-4).toUpperCase();
const PLACE_A = `Local du club ${RUN}`;
const PLACE_B = `Stade ${RUN}`;
const DONOR = `Donateur extérieur ${RUN}`;
const BALLS = "Ballons de match";
const JERSEYS = "Maillots équipe A";

// Poste dev-b : Windows peut bloquer `chrome-headless-shell.exe` (incident
// Defender, MESSAGES.md 26/11). `PW_CHANNEL=chromium` fait tourner le même
// Chromium 1243 en mode headless « complet », sans rien télécharger.
// `ffmpeg-win64.exe` (vidéo) est bloqué de la même façon : vidéo coupée.
if (process.env.PW_CHANNEL) test.use({ channel: process.env.PW_CHANNEL, video: "off" });

fs.mkdirSync(OUT_DIR, { recursive: true });
const STATE_FILE = path.join(OUT_DIR, `etat-${RUN}.json`);

function loadMemberHolder(): string {
  try {
    return (JSON.parse(fs.readFileSync(STATE_FILE, "utf-8")) as { memberHolder: string }).memberHolder;
  } catch {
    return "";
  }
}

interface AuditReport {
  width: number;
  scrollWidth: number;
  clientWidth: number;
  smallTargets: { label: string; height: number; width: number }[];
  offCharterFonts: { size: number; text: string }[];
  clipped: { text: string; scrollWidth: number; clientWidth: number }[];
  outOfViewport: { text: string; right: number }[];
  stickyOverlaps: { footer: string; hidden: string; overlapPx: number }[];
  stack: { dialogs: string[]; topTitle: string; topReceivesClicks: boolean; hitTitle: string } | null;
}

/** Relevé automatique dans la modale du dessus si elle existe, sinon la page. */
async function audit(page: Page, width: number): Promise<AuditReport> {
  return page.evaluate((w) => {
    const visible = (el: Element) => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0";
    };
    const dialogs = Array.from(document.querySelectorAll<HTMLElement>("[role=dialog],[role=alertdialog]")).filter(visible);
    const titleOf = (d: Element) =>
      (d.getAttribute("aria-label") ||
        document.getElementById(d.getAttribute("aria-labelledby") ?? "")?.textContent ||
        "?").trim();
    // Modale réellement au-dessus : celle que touche un clic au centre de l'écran.
    let stack: AuditReport["stack"] = null;
    let root: HTMLElement = document.body;
    if (dialogs.length > 0) {
      const domTop = dialogs[dialogs.length - 1];
      const r = domTop.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + Math.min(r.height / 2, 60));
      const hitDialog = hit?.closest("[role=dialog],[role=alertdialog]") ?? null;
      stack = {
        dialogs: dialogs.map(titleOf),
        topTitle: titleOf(domTop),
        topReceivesClicks: hitDialog === domTop,
        hitTitle: hitDialog ? titleOf(hitDialog) : hit?.tagName ?? "(rien)",
      };
      root = domTop;
    }
    const labelOf = (el: Element) =>
      (el.getAttribute("aria-label") || (el as HTMLElement).innerText || el.getAttribute("placeholder") || el.tagName)
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 60);
    const inHorizontalScroller = (el: Element) => {
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const ox = getComputedStyle(p).overflowX;
        if (ox === "auto" || ox === "scroll") return true;
      }
      return false;
    };
    const isSrOnly = (el: Element) => {
      for (let p: Element | null = el; p; p = p.parentElement) if (p.classList.contains("sr-only")) return true;
      return false;
    };
    const smallTargets: AuditReport["smallTargets"] = [];
    const interactive = root.querySelectorAll(
      "button, a[href], input:not([type=hidden]), select, textarea, [role=button], [role=radio], [role=checkbox], [role=option]",
    );
    for (const el of Array.from(interactive)) {
      let target: Element = el;
      if (el.matches("input[type=checkbox], input[type=radio]")) target = el.closest("label") ?? el;
      if (!visible(target) || isSrOnly(target)) continue;
      const r = target.getBoundingClientRect();
      if (r.height < 36) smallTargets.push({ label: labelOf(el), height: Math.round(r.height), width: Math.round(r.width) });
    }
    const offCharterFonts: AuditReport["offCharterFonts"] = [];
    const clipped: AuditReport["clipped"] = [];
    const outOfViewport: AuditReport["outOfViewport"] = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const seen = new Set<Element>();
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const text = (n.textContent ?? "").trim();
      const el = n.parentElement;
      if (!text || !el || seen.has(el) || !visible(el) || isSrOnly(el)) continue;
      seen.add(el);
      const size = parseFloat(getComputedStyle(el).fontSize);
      if (size < 12 || size > 24) offCharterFonts.push({ size, text: text.slice(0, 50) });
      const r = el.getBoundingClientRect();
      if (r.right > w + 1 && !inHorizontalScroller(el)) outOfViewport.push({ text: text.slice(0, 50), right: Math.round(r.right) });
    }
    for (const el of Array.from(root.querySelectorAll<HTMLElement>("*"))) {
      if (!visible(el) || isSrOnly(el) || !el.innerText?.trim()) continue;
      const s = getComputedStyle(el);
      const hides = s.overflowX === "hidden" || s.overflowX === "clip" || s.textOverflow === "ellipsis";
      if (hides && el.scrollWidth > el.clientWidth + 1 && el.children.length === 0) {
        clipped.push({ text: el.innerText.trim().slice(0, 50), scrollWidth: el.scrollWidth, clientWidth: el.clientWidth });
      }
    }
    const stickyOverlaps: AuditReport["stickyOverlaps"] = [];
    for (const el of Array.from(root.querySelectorAll<HTMLElement>("*"))) {
      const s = getComputedStyle(el);
      if ((s.position !== "sticky" && s.position !== "fixed") || !visible(el) || s.bottom === "auto") continue;
      if (el.closest("[aria-live]") || s.pointerEvents === "none") continue; // toasts transitoires
      let scroller: HTMLElement | null = el.parentElement;
      while (scroller && scroller !== document.body) {
        const oy = getComputedStyle(scroller).overflowY;
        if ((oy === "auto" || oy === "scroll") && scroller.scrollHeight > scroller.clientHeight) break;
        scroller = scroller.parentElement;
      }
      if (scroller && scroller !== document.body) scroller.scrollTop = scroller.scrollHeight;
      else window.scrollTo(0, document.documentElement.scrollHeight);
      const prev = el.previousElementSibling as HTMLElement | null;
      if (!prev || !visible(prev)) continue;
      const overlap = prev.getBoundingClientRect().bottom - el.getBoundingClientRect().top;
      if (overlap > 1) stickyOverlaps.push({ footer: labelOf(el), hidden: labelOf(prev), overlapPx: Math.round(overlap) });
    }
    return {
      width: w,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      smallTargets,
      offCharterFonts,
      clipped,
      outOfViewport,
      stickyOverlaps,
      stack,
    };
  }, width);
}

/**
 * Capture à 360 puis 320 px (écran réel si une modale est ouverte, pleine
 * page sinon), relevé JSON, assertions de charte à 360 px. Pour une modale,
 * seconde capture défilée jusqu'en bas (contenu sous le pied collant).
 */
async function shoot(page: Page, name: string, widths: readonly number[] = WIDTHS): Promise<AuditReport[]> {
  await page.waitForTimeout(450);
  const reports: AuditReport[] = [];
  for (const width of widths) {
    await page.setViewportSize({ width, height: 740 });
    await page.waitForTimeout(250);
    const dialogOpen = (await page.locator("[role=dialog]:visible, [role=alertdialog]:visible").count()) > 0;
    await page.screenshot({ path: path.join(OUT_DIR, `${name}-${width}.png`), fullPage: !dialogOpen });
    const report = await audit(page, width);
    const scrolled = await page.evaluate(() => {
      const dialogs = Array.from(document.querySelectorAll<HTMLElement>("[role=dialog],[role=alertdialog]"));
      const top = dialogs[dialogs.length - 1];
      if (!top) return false;
      let moved = false;
      for (const el of Array.from(top.querySelectorAll<HTMLElement>("*")).concat(top)) {
        const oy = getComputedStyle(el).overflowY;
        if ((oy === "auto" || oy === "scroll") && el.scrollHeight > el.clientHeight + 4) {
          el.scrollTop = el.scrollHeight;
          moved = true;
        }
      }
      return moved;
    });
    if (scrolled) {
      await page.waitForTimeout(150);
      await page.screenshot({ path: path.join(OUT_DIR, `${name}-${width}-bas.png`) });
      // Remet le contenu en haut pour la suite du parcours.
      await page.evaluate(() => {
        const dialogs = Array.from(document.querySelectorAll<HTMLElement>("[role=dialog],[role=alertdialog]"));
        const top = dialogs[dialogs.length - 1];
        for (const el of Array.from(top?.querySelectorAll<HTMLElement>("*") ?? [])) el.scrollTop = 0;
      });
    }
    fs.writeFileSync(path.join(OUT_DIR, `${name}-${width}.json`), JSON.stringify(report, null, 2));
    if (width === 360) {
      expect.soft(report.scrollWidth, `${name} : aucun défilement horizontal à 360 px`).toBeLessThanOrEqual(report.clientWidth);
      expect.soft(report.stickyOverlaps, `${name} : un pied collant masque du contenu`).toEqual([]);
      if (report.stack) {
        expect.soft(report.stack.topReceivesClicks, `${name} : la modale du dessus (${report.stack.topTitle}) reçoit les clics`).toBe(true);
      }
    }
    reports.push(report);
  }
  await page.setViewportSize({ width: 360, height: 740 });
  await page.waitForTimeout(150);
  return reports;
}

function dialog(page: Page, title: string | RegExp): Locator {
  return page.getByRole("dialog", { name: title });
}

/** Choisit une option d'un combobox (ArticleSearch, HolderSearch, SearchCombobox) dans `scope`. */
async function pickOption(scope: Locator, comboboxName: string | RegExp | null, query: string, option: string | RegExp): Promise<void> {
  const input = comboboxName ? scope.getByRole("combobox", { name: comboboxName }) : scope.getByRole("combobox").first();
  await input.click();
  if (query) await input.fill(query);
  const opt = scope.getByRole("option").filter({ hasText: option }).first();
  await expect(opt).toBeVisible({ timeout: 10_000 });
  await opt.click();
}

/** Source d'une sortie : puces (≤ 5 sources) ou recherche au-delà (HolderPicker). */
async function chooseSource(scope: Locator, label: string, name: string): Promise<void> {
  const chip = scope.getByRole("radio", { name: new RegExp(name) });
  if (await chip.isVisible().catch(() => false)) await chip.click();
  else await pickOption(scope, label, name.slice(0, 5), name);
}

/** Source préremplie : puce cochée (≤ 5 sources) ou sélection affichée dans la recherche. */
async function expectSourceSelected(scope: Locator, name: RegExp): Promise<void> {
  const chip = scope.getByRole("radio", { name });
  if ((await chip.count()) > 0) await expect(chip).toHaveAttribute("aria-checked", "true");
  else await expect(scope.getByText(name).first()).toBeVisible();
}

async function expectToast(page: Page, text: string | RegExp): Promise<void> {
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 15_000 });
}

async function gotoMateriel(page: Page): Promise<void> {
  await page.goto("/materiel");
  await expect(page.getByRole("heading", { level: 1, name: "Matériel" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Où est le matériel/ })).toBeVisible();
}

function holdersCard(page: Page): Locator {
  return page.locator("section").filter({ has: page.getByRole("heading", { name: /Où est le matériel/ }) });
}

/** Au-delà de 5 détenteurs, la carte affiche « Voir plus » (§3.2). */
async function expandHolders(page: Page): Promise<void> {
  const more = holdersCard(page).getByRole("button", { name: "Voir plus" });
  if (await more.isVisible().catch(() => false)) await more.click();
}

/** Ajoute un détenteur dans la modale « Ajouter un détenteur » déjà ouverte. */
async function fillHolderForm(form: Locator, kind: "place" | "member", value: string): Promise<string> {
  if (kind === "place") {
    await form.getByRole("button", { name: "Un lieu" }).click();
    await form.getByLabel("Nom du lieu").fill(value);
    await form.getByRole("button", { name: "Ajouter", exact: true }).click();
    return value;
  }
  const input = form.getByPlaceholder("Nom ou numéro du joueur");
  await input.click();
  await input.fill(value);
  // Premier joueur qui n'est pas déjà détenteur (rejouable).
  const opt = form.locator("[role=option]:not([aria-disabled=true])").first();
  await expect(opt).toBeVisible({ timeout: 10_000 });
  const name = ((await opt.locator("p").first().textContent()) ?? "").trim();
  await opt.click();
  await form.getByRole("button", { name: "Ajouter", exact: true }).click();
  return name;
}

let page: Page;
let memberHolder = loadMemberHolder();

async function newIntendantPage(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ viewport: { width: 360, height: 740 }, acceptDownloads: true });
  const p = await context.newPage();
  await loginAs(p, INTENDANT);
  return p;
}

test.describe.serial("Intendance à 360 px — parcours de l'Intendant", () => {
  test.beforeAll(async ({ browser }) => {
    page = await newIntendantPage(browser);
  });
  test.afterAll(async () => {
    await page.context().close();
  });

  test("intendant_adds_place_and_player_holders_from_materiel_page", async () => {
    await gotoMateriel(page);
    await shoot(page, "01-materiel-depart");
    const card = holdersCard(page);
    const form = dialog(page, "Ajouter un détenteur");
    if (!memberHolder) {
      // État vide (premier passage) ou bouton de carte (passages suivants).
      await card.getByRole("button", { name: "Ajouter un détenteur" }).first().click();
      await expect(form).toBeVisible();
      await shoot(page, "02-ajouter-detenteur-joueur");
      // Validation : aucun joueur choisi.
      await form.getByRole("button", { name: "Ajouter", exact: true }).click();
      await expect(form.getByText("Choisissez un joueur.")).toBeVisible();
      memberHolder = await fillHolderForm(form, "member", "e");
      fs.writeFileSync(STATE_FILE, JSON.stringify({ memberHolder }));
      await expectToast(page, "Détenteur ajouté.");
      await expect(form).toBeHidden();
    }
    await expandHolders(page);
    if (await card.getByText(PLACE_A).isVisible().catch(() => false)) return; // rejoué après une relance
    await card.getByRole("button", { name: "Ajouter un détenteur" }).click();
    await expect(form).toBeVisible();
    await form.getByRole("button", { name: "Un lieu" }).click();
    await form.getByRole("button", { name: "Ajouter", exact: true }).click();
    await expect(form.getByText("Ce champ est obligatoire.")).toBeVisible();
    await shoot(page, "03-ajouter-detenteur-lieu-erreur");
    await form.getByLabel("Nom du lieu").fill(PLACE_A);
    await form.getByRole("button", { name: "Ajouter", exact: true }).click();
    await expect(form).toBeHidden();

    // Doublon de lieu (§4.2).
    await card.getByRole("button", { name: "Ajouter un détenteur" }).click();
    await fillHolderForm(form, "place", PLACE_A);
    await expect(form.getByText(/existe déjà/)).toBeVisible();
    await form.getByRole("button", { name: "Fermer" }).click();
    const abandon = page.getByRole("alertdialog", { name: "Abandonner les modifications ?" });
    if (await abandon.isVisible().catch(() => false)) await abandon.getByRole("button").last().click();
    await expect(form).toBeHidden();

    await expandHolders(page);
    await expect(card.getByText(PLACE_A)).toBeVisible();
    await expect(card.getByText(memberHolder)).toBeVisible();
    // Bandeau « non localisé » dès qu'un détenteur existe (§3.3).
    await expect(page.getByText(/pièce\(s\) ne sont rattachées à aucun détenteur/)).toBeVisible();
    await shoot(page, "04-materiel-avec-detenteurs");
  });

  test("intendant_records_entries_with_holder_and_provenance", async () => {
    await gotoMateriel(page);
    await page.getByRole("button", { name: "Enregistrer un mouvement" }).first().click();
    const modal = dialog(page, "Enregistrer un mouvement");
    await expect(modal).toBeVisible();
    // Achat : bloc « Provenance » replié en une ligne (§5.2).
    await modal.getByRole("button", { name: "Achat", exact: true }).click();
    await expect(modal.getByText("non renseignée")).toBeVisible();
    await shoot(page, "05-mouvement-achat-provenance-repliee");

    // Dotation : bloc déplié d'office, « Don » proposé.
    await modal.getByRole("button", { name: "Dotation", exact: true }).click();
    await expect(modal.getByRole("group", { name: "Origine" })).toBeVisible();
    await pickOption(modal, null, "Ball", BALLS);
    await modal.getByRole("spinbutton", { name: /Quantité/ }).fill("4");
    await pickOption(modal, "Qui reçoit le matériel ?", "", PLACE_A);
    await modal.getByRole("group", { name: "Origine" }).getByRole("button", { name: "Don" }).click();
    await pickOption(modal, "Donateur", DONOR, /hors club/);
    await modal.getByText("Date inconnue").click();
    await modal.getByLabel(/Précision sur la date/).fill("Voir le comité précédent");
    await modal.getByRole("group", { name: "État à l'entrée" }).getByRole("button", { name: "Bon état" }).click();
    await shoot(page, "06-mouvement-dotation-provenance");
    await modal.getByRole("button", { name: "Enregistrer le mouvement" }).click();
    await expect(modal).toBeHidden({ timeout: 15_000 });

    // Reprise du registre chez le joueur détenteur.
    await page.getByRole("button", { name: "Enregistrer un mouvement" }).first().click();
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: "Reprise du registre", exact: true }).click();
    await expect(modal.getByText("Pour le matériel que le club possédait avant d'utiliser Vesta.")).toBeVisible();
    await pickOption(modal, null, "Maill", JERSEYS);
    await modal.getByRole("spinbutton", { name: /Quantité/ }).fill("6");
    await pickOption(modal, "Qui reçoit le matériel ?", memberHolder.split(" ")[0], memberHolder);
    await modal.getByRole("group", { name: "Origine" }).getByRole("button", { name: "Frais de l'équipe" }).click();
    await modal.getByLabel(/Date d'acquisition/).fill("2025-06-22");
    await shoot(page, "07-mouvement-reprise-registre");
    await modal.getByRole("button", { name: "Enregistrer le mouvement" }).click();
    await expect(modal).toBeHidden({ timeout: 15_000 });

    // Sortie : « D'où sort le matériel ? » en puces (HolderPicker).
    await page.getByRole("button", { name: "Enregistrer un mouvement" }).first().click();
    await modal.getByRole("button", { name: "Sortie", exact: true }).click();
    await pickOption(modal, null, "Ball", BALLS);
    // Puces jusqu'à 5 sources, recherche au-delà (HolderPicker), préremplie
    // avec le détenteur qui en a le plus (§4.4).
    await expect(modal.getByText("D'où sort le matériel ?", { exact: true })).toBeVisible();
    await shoot(page, "08-mouvement-sortie-holderpicker");
    await modal.getByRole("button", { name: "Annuler" }).click();
    const abandon = page.getByRole("alertdialog", { name: "Abandonner les modifications ?" });
    if (await abandon.isVisible().catch(() => false)) await abandon.getByRole("button").last().click();
    await expect(modal).toBeHidden();
  });

  test("intendant_moves_material_and_creates_holder_from_nested_modal_stack", async () => {
    await gotoMateriel(page);
    await expandHolders(page);
    await holdersCard(page).getByRole("button", { name: new RegExp(PLACE_A) }).click();
    const holder = dialog(page, PLACE_A);
    await expect(holder).toBeVisible();
    await expect(holder.getByText(BALLS, { exact: true })).toBeVisible();
    await shoot(page, "09-detenteur-lieu");

    await holder.getByRole("button", { name: "Déplacer du matériel" }).click();
    const transfer = dialog(page, "Déplacer du matériel");
    await expect(transfer).toBeVisible();
    await shoot(page, "10-deplacer-depuis-detenteur");
    await pickOption(transfer, null, "Ball", BALLS);
    await expectSourceSelected(transfer, new RegExp(PLACE_A));

    // Empilement : « + Ajouter un détenteur » (niveau 2) depuis « Déplacer » (niveau 2) depuis « Détenteur ».
    await pickOption(transfer, "Nouveau détenteur", "", /Ajouter un détenteur/);
    const nested = dialog(page, "Ajouter un détenteur");
    await expect(nested).toBeVisible();
    const [stackReport] = await shoot(page, "11-empilement-ajouter-detenteur", [360]);
    expect(stackReport.stack?.topTitle).toBe("Ajouter un détenteur");
    await shoot(page, "11-empilement-ajouter-detenteur-320", [320]);
    // Suggestions de joueurs dans la feuille empilée : visibles et cliquables.
    await nested.getByPlaceholder("Nom ou numéro du joueur").fill("a");
    await expect(nested.getByRole("option").first()).toBeVisible({ timeout: 10_000 });
    await page.screenshot({ path: path.join(OUT_DIR, "11b-empilement-suggestions-joueurs-360.png") });
    const optionBox = await nested.getByRole("option").first().boundingBox();
    const hitsOption = await page.evaluate(
      ([x, y]) => Boolean(document.elementFromPoint(x, y)?.closest("[role=option]")),
      [optionBox!.x + optionBox!.width / 2, optionBox!.y + optionBox!.height / 2],
    );
    expect.soft(hitsOption, "la 1re suggestion de joueur est cliquable dans la feuille empilée").toBe(true);
    await nested.getByRole("button", { name: "Un lieu" }).click();
    await nested.getByLabel("Nom du lieu").fill(PLACE_B);
    await nested.getByRole("button", { name: "Ajouter", exact: true }).click();
    await expect(nested).toBeHidden();
    await expect(transfer).toBeVisible();
    await expect(transfer.getByText(PLACE_B)).toBeVisible();

    // Erreur : quantité au-delà du stock de la source (§4.3).
    await transfer.getByRole("spinbutton", { name: /Quantité/ }).fill("99");
    await transfer.getByRole("button", { name: "Déplacer", exact: true }).click();
    await expect(transfer.getByText(/Quantité supérieure au stock/)).toBeVisible({ timeout: 10_000 });
    await shoot(page, "12-deplacer-erreur-quantite");
    await transfer.getByRole("spinbutton", { name: /Quantité/ }).fill("2");
    await transfer.getByRole("button", { name: "Déplacer", exact: true }).click();
    await expectToast(page, new RegExp(`Matériel déplacé : 2 pièce de ${BALLS} chez ${PLACE_B}`));
    await expect(transfer).toBeHidden();
    await expect(holder).toBeVisible();
    await shoot(page, "13-detenteur-apres-transfert");

    // Article au niveau 2 depuis le détenteur.
    await holder.getByRole("button", { name: new RegExp(BALLS) }).click();
    const article = dialog(page, BALLS);
    await expect(article).toBeVisible();
    await shoot(page, "14-article-niveau2-depuis-detenteur");
    await page.keyboard.press("Escape");
    await expect(article).toBeHidden();
    await page.keyboard.press("Escape");
    await expect(holder).toBeHidden();
  });

  test("intendant_localises_unlocated_material_from_banner_and_unlocated_modal", async () => {
    await gotoMateriel(page);
    await holdersCard(page).getByRole("button", { name: /Non localisé/ }).click();
    const unlocated = dialog(page, "Non localisé");
    await expect(unlocated).toBeVisible();
    await shoot(page, "15-non-localise");
    await page.keyboard.press("Escape");
    await expect(unlocated).toBeHidden();

    await page.getByRole("button", { name: "Localiser", exact: true }).click();
    const transfer = dialog(page, "Déplacer du matériel");
    await expect(transfer).toBeVisible();
    await expect(transfer.getByText(/De :/)).toBeVisible();
    await pickOption(transfer, null, "Troux", /Trousse/).catch(async () => {
      await pickOption(transfer, null, "Trousse", /Trousse/);
    });
    await expectSourceSelected(transfer, /Non localisé/);
    await pickOption(transfer, "Nouveau détenteur", PLACE_A.slice(0, 5), PLACE_A);
    await transfer.getByRole("spinbutton", { name: /Quantité/ }).fill("1");
    await shoot(page, "16-localiser-depuis-bandeau");
    await transfer.getByRole("button", { name: "Déplacer", exact: true }).click();
    await expect(transfer).toBeHidden({ timeout: 15_000 });
  });

  test("catalogue_shows_holder_and_decommission_columns_and_article_modal_sections", async () => {
    await gotoMateriel(page);
    const catalogue = page.locator("section").filter({ has: page.getByRole("heading", { name: /^Catalogue/ }) });
    await expect(catalogue.getByText(BALLS).first()).toBeVisible();
    await catalogue.screenshot({ path: path.join(OUT_DIR, "17-catalogue-360.png") });
    await catalogue.getByText(BALLS).first().click();
    const article = dialog(page, BALLS);
    await expect(article).toBeVisible();
    await expect(article.getByRole("heading", { name: "Répartition" })).toBeVisible();
    await expect(article.getByRole("heading", { name: "Provenances" })).toBeVisible();
    await expect(article.getByText(new RegExp(`Don de ${DONOR}`)).first()).toBeVisible();
    await shoot(page, "18-article-repartition-provenances");
    // « Déplacer » depuis la répartition : modale de niveau 2 au-dessus de l'article.
    await article.getByRole("button", { name: "Déplacer", exact: true }).click();
    const transfer = dialog(page, "Déplacer du matériel");
    await expect(transfer).toBeVisible();
    const [rep] = await shoot(page, "19-article-deplacer-niveau2", [360]);
    expect(rep.stack?.topTitle).toBe("Déplacer du matériel");
    await page.keyboard.press("Escape");
    await expect(transfer).toBeHidden();
    await page.keyboard.press("Escape");
    await expect(article).toBeHidden();

    // Desktop : colonnes « Chez » et « À déclasser » du tableau.
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.waitForTimeout(400);
    await expect(catalogue.getByRole("columnheader", { name: "Chez" })).toBeVisible();
    await expect(catalogue.getByRole("columnheader", { name: "À déclasser" })).toBeVisible();
    await page.screenshot({ path: path.join(OUT_DIR, "20-materiel-1280.png"), fullPage: true });
    await page.setViewportSize({ width: 360, height: 740 });
  });

  test("intendant_flags_two_decommissions_executes_one_and_cancels_the_other", async () => {
    await gotoMateriel(page);
    const header = page.locator("main header").first();
    await header.getByRole("button", { name: "Plus d'actions" }).click();
    await page.getByRole("button", { name: "Signaler à déclasser" }).first().click();
    const flag = dialog(page, "Signaler à déclasser");
    await expect(flag).toBeVisible();
    await flag.getByRole("button", { name: "Signaler", exact: true }).click();
    await expect(flag.getByText("Choisissez un article.")).toBeVisible();
    await pickOption(flag, null, "Ball", BALLS);
    await expect(flag.getByText("Choisissez un article.")).toBeHidden();
    await chooseSource(flag, "Chez", PLACE_B);
    await flag.getByRole("spinbutton", { name: /Quantité/ }).fill("1");
    await flag.getByRole("group", { name: "Motif" }).getByRole("button", { name: "Usé" }).click();
    await shoot(page, "21-signaler-a-declasser");
    await flag.getByRole("button", { name: "Signaler", exact: true }).click();
    await expectToast(page, new RegExp(`1 pièce de ${BALLS} à déclasser`));
    await expect(flag).toBeHidden();

    const decoCard = page.locator("section").filter({ has: page.getByRole("heading", { name: /^À déclasser/ }) });
    await expect(decoCard).toBeVisible();
    await decoCard.getByRole("button", { name: "Signaler à déclasser" }).click();
    await expect(flag).toBeVisible();
    await pickOption(flag, null, "Maill", JERSEYS);
    await chooseSource(flag, "Chez", memberHolder);
    await flag.getByRole("spinbutton", { name: /Quantité/ }).fill("1");
    await flag.getByRole("group", { name: "Motif" }).getByRole("button", { name: "Autre" }).click();
    await flag.getByRole("button", { name: "Signaler", exact: true }).click();
    await expect(flag.getByText("Précisez le motif.")).toBeVisible();
    await flag.getByLabel(/Précision/).fill("Écusson décousu");
    await flag.getByRole("button", { name: "Signaler", exact: true }).click();
    await expect(flag).toBeHidden({ timeout: 15_000 });
    await decoCard.scrollIntoViewIfNeeded();
    await decoCard.screenshot({ path: path.join(OUT_DIR, "22-carte-a-declasser-360.png") });

    // Sortie du stock du premier signalement.
    await decoCard.getByRole("button", { name: new RegExp(BALLS) }).first().click();
    const detail = dialog(page, new RegExp(`Déclassement · ${BALLS}`));
    await expect(detail).toBeVisible();
    await shoot(page, "23-declassement-en-attente");
    await detail.getByRole("button", { name: "Sortir du stock" }).click();
    const exit = dialog(page, "Sortir du stock");
    await expect(exit).toBeVisible();
    await exit.getByLabel(/Destination/).fill("Donné à l'école du quartier");
    await shoot(page, "24-sortir-du-stock");
    await exit.getByRole("button", { name: "Continuer" }).click();
    const confirm = dialog(page, new RegExp(`Sortir 1 pièce de ${BALLS} du stock`));
    await expect(confirm).toBeVisible();
    await expect(confirm.getByText("Cette sortie est définitive : elle ne pourra pas être supprimée.")).toBeVisible();
    await shoot(page, "25-confirmation-sortie");
    await confirm.getByRole("button", { name: "Sortir du stock" }).click();
    await expectToast(page, /1 pièce sortis du stock|sortis du stock/);
    await expect(detail.getByText(/Sorti le/)).toBeVisible({ timeout: 15_000 });
    await shoot(page, "26-declassement-declasse");
    await detail.getByRole("button", { name: "Voir le mouvement" }).click();
    await expect(page.getByRole("dialog").last()).toBeVisible();
    await shoot(page, "27-mouvement-declassement-niveau2", [360]);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expect(detail).toBeHidden();

    // Annulation du second.
    await decoCard.getByRole("button", { name: new RegExp(JERSEYS) }).first().click();
    const detail2 = dialog(page, new RegExp(`Déclassement · ${JERSEYS}`));
    await expect(detail2).toBeVisible();
    await detail2.getByRole("button", { name: "Plus d'actions" }).click();
    await detail2.getByRole("button", { name: "Annuler le signalement" }).click();
    const cancel = dialog(page, "Annuler le signalement ?");
    await expect(cancel).toBeVisible();
    await cancel.getByRole("button", { name: "Annuler le signalement" }).click();
    await expect(cancel.getByRole("alert")).toBeVisible();
    await shoot(page, "28-annuler-signalement-motif-requis");
    await cancel.getByLabel("Motif").fill("Pièces finalement gardées");
    await cancel.getByRole("button", { name: "Annuler le signalement" }).click();
    await expectToast(page, "Signalement annulé.");
    await expect(detail2.getByText(/Annulé/).first()).toBeVisible({ timeout: 15_000 });
    await shoot(page, "29-declassement-annule");
    await page.keyboard.press("Escape");

    await decoCard.getByRole("button", { name: "Voir plus" }).click();
    const list = dialog(page, "Déclassements");
    await expect(list).toBeVisible();
    await shoot(page, "30-liste-declassements");
    await page.keyboard.press("Escape");
    await expect(list).toBeHidden();
  });

  test("movements_register_lists_transfer_and_opens_movement_modal", async () => {
    await gotoMateriel(page);
    const mv = page.locator("section").filter({ has: page.getByRole("heading", { name: /^Registre des mouvements/ }) });
    await mv.scrollIntoViewIfNeeded();
    await expect(mv.getByRole("cell", { name: "Transfert reçu" }).first()).toBeVisible();
    await mv.screenshot({ path: path.join(OUT_DIR, "31-registre-mouvements-360.png") });
    await mv.getByRole("cell", { name: "Transfert reçu" }).first().click();
    const modal = page.getByRole("dialog").last();
    await expect(modal).toBeVisible();
    await shoot(page, "32-mouvement-transfert");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    // Page complète finale (360 / 320) : toutes les cartes remplies.
    await shoot(page, "33-materiel-final");
  });

  test("register_page_filters_layout_and_pdf_csv_downloads", async () => {
    await page.goto("/materiel/registre");
    await expect(page.getByRole("heading", { level: 1, name: "Registre de l'intendance" })).toBeVisible();
    await expect(page.getByText(/arrêté au/)).toBeVisible();
    await expect(page.getByText(BALLS).first()).toBeVisible();
    // 360 px : listes compactes, aucun tableau.
    expect(await page.locator("main table").count()).toBe(0);
    await shoot(page, "34-registre-intendance");
    await page.screenshot({ path: path.join(OUT_DIR, "34-registre-intendance-360-ecran-defile.png") });

    await page.getByLabel("Rechercher un article, un donateur").fill(DONOR);
    await expect(page.getByText(/Extrait/)).toBeVisible();
    await shoot(page, "35-registre-filtre-donateur", [360]);
    await page.getByLabel("Rechercher un article, un donateur").fill("zzzz-introuvable");
    await expect(page.getByRole("button", { name: "Effacer les filtres" })).toBeVisible();
    await shoot(page, "36-registre-aucun-resultat", [360]);
    await page.getByRole("button", { name: "Effacer les filtres" }).click();
    await page.getByText("Afficher les sorties").click();
    await expect(page.getByRole("heading", { name: "Sorties de l'année" })).toBeVisible();
    await shoot(page, "37-registre-avec-sorties", [360]);

    const [pdf] = await Promise.all([
      page.waitForEvent("download", { timeout: 30_000 }),
      page.getByRole("button", { name: "Télécharger (PDF)" }).click(),
    ]);
    expect(pdf.suggestedFilename()).toMatch(/\.pdf$/);
    const pdfPath = path.join(OUT_DIR, `registre-${RUN}.pdf`);
    await pdf.saveAs(pdfPath);
    expect(fs.readFileSync(pdfPath).subarray(0, 4).toString()).toBe("%PDF");

    await page.locator("main header").getByRole("button", { name: "Plus d'actions" }).click();
    const [csv] = await Promise.all([
      page.waitForEvent("download", { timeout: 30_000 }),
      page.getByRole("button", { name: "Exporter (CSV)" }).click(),
    ]);
    expect(csv.suggestedFilename()).toMatch(/\.csv$/);
    const csvPath = path.join(OUT_DIR, `registre-${RUN}.csv`);
    await csv.saveAs(csvPath);
    const bytes = fs.readFileSync(csvPath);
    expect(bytes.subarray(0, 3).toString("hex")).toBe("efbbbf");
    expect(bytes.toString("utf-8")).toContain(";");

    // Ligne → modale « Mouvement ».
    await page.getByText(BALLS).first().click();
    await expect(page.getByRole("dialog").last()).toBeVisible();
    await shoot(page, "38-registre-mouvement", [360]);
    await page.keyboard.press("Escape");

    // Barre de filtres collante (§10.2) : vue écran réelle après défilement,
    // à 360 et 768 px ; elle ne doit pas passer sous la barre de l'application.
    for (const width of [360, 768]) {
      await page.setViewportSize({ width, height: width === 360 ? 740 : 1000 });
      await page.evaluate(() => window.scrollTo(0, 900));
      await page.waitForTimeout(400);
      await page.screenshot({ path: path.join(OUT_DIR, `34b-registre-filtres-colles-${width}.png`) });
      const overlap = await page.evaluate(() => {
        const bar = document.querySelector<HTMLElement>("main .sticky");
        const appBar = Array.from(document.querySelectorAll<HTMLElement>("header, nav")).find((el) => {
          const s = getComputedStyle(el);
          return (s.position === "sticky" || s.position === "fixed") && !el.closest("main");
        });
        if (!bar || !appBar) return { bar: Boolean(bar), appBar: Boolean(appBar), overlapPx: 0, barHeight: 0 };
        const b = bar.getBoundingClientRect();
        const a = appBar.getBoundingClientRect();
        return { bar: true, appBar: true, overlapPx: Math.round(a.bottom - b.top), barHeight: Math.round(b.height) };
      });
      fs.writeFileSync(path.join(OUT_DIR, `34b-registre-filtres-colles-${width}.json`), JSON.stringify(overlap, null, 2));
      expect.soft(overlap.overlapPx, `barre de filtres masquée par la barre de l'application à ${width} px`).toBeLessThanOrEqual(0);
    }
    await page.evaluate(() => window.scrollTo(0, 0));

    // ≥ 768 px : tableaux.
    for (const width of [768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await page.waitForTimeout(400);
      await expect(page.locator("main table").first()).toBeVisible();
      await page.screenshot({ path: path.join(OUT_DIR, `39-registre-${width}.png`), fullPage: true });
    }
    await page.setViewportSize({ width: 360, height: 740 });
  });
});

test.describe("Intendance — rôles en lecture et sans accès", () => {
  test("president_reads_materiel_without_write_actions", async ({ page: p }) => {
    await loginAs(p, "president@demo.local");
    await gotoMateriel(p);
    await expect(p.getByRole("button", { name: "Enregistrer un mouvement" })).toHaveCount(0);
    await expect(p.getByRole("button", { name: "Ajouter un détenteur" })).toHaveCount(0);
    await expect(p.getByRole("button", { name: "Localiser", exact: true })).toHaveCount(0);
    await holdersCard(p).locator("li button").first().click();
    const holder = p.getByRole("dialog").last();
    await expect(holder).toBeVisible();
    await expect(holder.getByRole("button", { name: "Déplacer du matériel" })).toHaveCount(0);
    await expect(holder.getByRole("button", { name: "Plus d'actions" })).toHaveCount(0);
    await p.keyboard.press("Escape");
    await p.screenshot({ path: path.join(OUT_DIR, "40-president-materiel-360.png"), fullPage: true });
    await p.getByRole("button", { name: "Registre de l'intendance" }).click();
    await expect(p.getByRole("button", { name: "Télécharger (PDF)" })).toBeVisible();
  });

  test("treasurer_and_coach_read_register_without_write_actions", async ({ page: p }) => {
    for (const email of ["tresorier@demo.local", "coach@demo.local"]) {
      await loginAs(p, email);
      await p.goto("/materiel/registre");
      await expect(p.getByRole("heading", { level: 1, name: "Registre de l'intendance" })).toBeVisible();
      await gotoMateriel(p);
      await expect(p.getByRole("button", { name: "Enregistrer un mouvement" })).toHaveCount(0);
      await expect(p.getByRole("button", { name: "Signaler à déclasser" })).toHaveCount(0);
    }
  });

  test("plain_player_has_no_access_to_materiel_nor_register", async ({ page: p }) => {
    await loginAs(p, "joueur03@demo.local");
    await p.goto("/materiel");
    await expect(p.getByText("Vous n'avez pas accès à cette page.")).toBeVisible();
    await p.goto("/materiel/registre");
    await expect(p.getByText("Vous n'avez pas accès à cette page.")).toBeVisible();
    await p.screenshot({ path: path.join(OUT_DIR, "41-joueur-sans-acces-360.png") });
  });
});
