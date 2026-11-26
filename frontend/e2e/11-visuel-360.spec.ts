import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect, type Page, type Locator } from "@playwright/test";
import { loginAs } from "./support/auth";
import { AVAILABLE_UNMARKED_PLAYERS, DEMO, TODAY_SESSION_ID, UNAVAILABLE_PLAYERS } from "./support/demo";

/**
 * Tâche B3 (MESSAGES.md §2) — vérification VISUELLE à 360 px des écrans jamais
 * vus dans un navigateur, contre les vrais serveurs de dev et la base locale de
 * DÉMONSTRATION (club fictif « Club Démo »).
 *
 * Pour chaque écran : capture pleine page à 360 × 740 puis à 320 px de large,
 * et un contrôle automatique selon la charte (CDC chapitre 3, CLAUDE.md
 * §2.13–2.20) :
 *  - aucun défilement horizontal de la page (assertion à 360 px) ;
 *  - cibles tactiles visibles de moins de 36 px de haut (relevé) ;
 *  - tailles de police hors de 12–24 px (relevé ; 12 px = texte secondaire) ;
 *  - textes coupés (débordement masqué) ou qui sortent de l'écran (relevé) ;
 *  - pied collant (modale, barre d'actions) qui masque le dernier contenu
 *    une fois défilé jusqu'en bas (assertion) ;
 *  - focus visible au clavier (relevé).
 * Les relevés sont écrits en JSON à côté des captures, dans
 * `frontend/test-results/visuel-360/` (dossier ignoré par Git), puis relus à
 * la main avec les captures : c'est une vérification visuelle.
 *
 * AUCUNE écriture en base : les chronos ne sont jamais envoyés (abandon), les
 * modales de pointage groupé et d'excuse sont annulées.
 */

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.resolve(__dirname, "../test-results/visuel-360");
const SESSION_URL = `/seances/${TODAY_SESSION_ID}`;
const WIDTHS = [360, 320] as const;

interface AuditReport {
  width: number;
  scrollWidth: number;
  clientWidth: number;
  smallTargets: { label: string; height: number; width: number }[];
  fontSizes: Record<string, string[]>;
  offCharterFonts: { size: number; text: string }[];
  clipped: { text: string; scrollWidth: number; clientWidth: number }[];
  outOfViewport: { text: string; right: number }[];
  stickyOverlaps: { footer: string; hidden: string; overlapPx: number }[];
  stickyGaps: { footer: string; gapPx: number }[];
  focus: { label: string; visible: boolean }[];
}

fs.mkdirSync(OUT_DIR, { recursive: true });

/** Relevé automatique dans la modale du dessus si elle existe, sinon la page. */
async function audit(page: Page, width: number): Promise<AuditReport> {
  return page.evaluate((w) => {
    const dialogs = Array.from(document.querySelectorAll<HTMLElement>("[role=dialog],[role=alertdialog]")).filter((d) => {
      const r = d.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });
    const root: HTMLElement = dialogs.length > 0 ? dialogs[dialogs.length - 1] : document.body;
    const visible = (el: Element) => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0";
    };
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
      for (let p: Element | null = el; p; p = p.parentElement) {
        if (p.classList.contains("sr-only")) return true;
      }
      return false;
    };

    const smallTargets: AuditReport["smallTargets"] = [];
    const interactive = root.querySelectorAll(
      "button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], [role=radio], [role=checkbox], [role=option]",
    );
    for (const el of Array.from(interactive)) {
      let target: Element = el;
      if (el.matches("input[type=checkbox], input[type=radio]")) target = el.closest("label") ?? el;
      if (!visible(target) || isSrOnly(target)) continue;
      const r = target.getBoundingClientRect();
      if (r.height < 36) smallTargets.push({ label: labelOf(el), height: Math.round(r.height), width: Math.round(r.width) });
    }

    const fontSizes: Record<string, string[]> = {};
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
      const s = getComputedStyle(el);
      const size = parseFloat(s.fontSize);
      const key = `${size}px`;
      (fontSizes[key] ??= []).length < 4 && fontSizes[key].push(text.slice(0, 40));
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

    // Pieds collants : une fois leur conteneur défilé jusqu'en bas, le
    // dernier élément qui les précède ne doit pas passer dessous.
    const stickyOverlaps: AuditReport["stickyOverlaps"] = [];
    const stickyGaps: AuditReport["stickyGaps"] = [];
    for (const el of Array.from(root.querySelectorAll<HTMLElement>("*"))) {
      const s = getComputedStyle(el);
      if ((s.position !== "sticky" && s.position !== "fixed") || !visible(el)) continue;
      if (s.bottom === "auto") continue;
      let scroller: HTMLElement | null = el.parentElement;
      while (scroller && scroller !== document.body) {
        const oy = getComputedStyle(scroller).overflowY;
        if ((oy === "auto" || oy === "scroll") && scroller.scrollHeight > scroller.clientHeight) break;
        scroller = scroller.parentElement;
      }
      // Pied collant décollé du bas de son cadre pendant le défilement : le
      // contenu reste visible (et cliquable) sous le pied.
      if (scroller && scroller !== document.body && scroller.scrollTop + scroller.clientHeight < scroller.scrollHeight - 2) {
        const gap = scroller.getBoundingClientRect().bottom - el.getBoundingClientRect().bottom;
        if (gap > 1) stickyGaps.push({ footer: labelOf(el), gapPx: Math.round(gap) });
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
      fontSizes,
      offCharterFonts,
      clipped,
      outOfViewport,
      stickyOverlaps,
      stickyGaps,
      focus: [],
    };
  }, width);
}

/** Quelques tabulations : le focus doit rester visible (outline ou anneau). */
async function auditFocus(page: Page, presses = 5): Promise<AuditReport["focus"]> {
  const out: AuditReport["focus"] = [];
  for (let i = 0; i < presses; i += 1) {
    await page.keyboard.press("Tab");
    out.push(
      await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return { label: "(body)", visible: false };
        const s = getComputedStyle(el);
        const outline = s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0;
        const ring = s.boxShadow !== "none" && s.boxShadow !== "";
        const label = (el.getAttribute("aria-label") || el.innerText || el.tagName).replace(/\s+/g, " ").trim().slice(0, 50);
        return { label, visible: outline || ring };
      }),
    );
  }
  return out;
}

/**
 * Capture pleine page à 360 puis 320 px, relevés JSON, assertions de charte
 * à 360 px (pas de défilement horizontal, pied collant qui ne masque rien).
 * `focus` : ajoute le relevé du focus clavier (à éviter si une tabulation
 * déclencherait une action).
 */
async function shoot(page: Page, name: string, options: { focus?: boolean } = {}): Promise<void> {
  await page.waitForTimeout(400); // fin des transitions d'ouverture
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 740 });
    await page.waitForTimeout(250);
    // Capture d'abord : le relevé des pieds collants fait défiler les conteneurs.
    // Modale ouverte (position fixe) : capture de l'écran réel du téléphone ;
    // une capture « pleine page » étirerait la fenêtre et fausserait le rendu.
    const dialogOpen = (await page.locator("[role=dialog]:visible, [role=alertdialog]:visible").count()) > 0;
    await page.screenshot({ path: path.join(OUT_DIR, `${name}-${width}.png`), fullPage: !dialogOpen });
    // Page : en plus, l'écran tel que vu sur le téléphone (barres collantes à leur vraie place).
    if (!dialogOpen) await page.screenshot({ path: path.join(OUT_DIR, `${name}-${width}-ecran.png`) });
    const report = await audit(page, width);
    // Modale : seconde capture défilée jusqu'en bas (contenu sous le pied collant).
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
    }
    if (width === 360 && options.focus) report.focus = await auditFocus(page);
    fs.writeFileSync(path.join(OUT_DIR, `${name}-${width}.json`), JSON.stringify(report, null, 2));
    if (width === 360) {
      expect.soft(report.scrollWidth, `${name} : aucun défilement horizontal à 360 px`).toBeLessThanOrEqual(report.clientWidth);
      expect.soft(report.stickyOverlaps, `${name} : un pied collant masque du contenu`).toEqual([]);
      expect.soft(report.stickyGaps, `${name} : un pied collant laisse voir le contenu dessous`).toEqual([]);
    }
  }
  await page.setViewportSize({ width: 360, height: 740 });
  await page.waitForTimeout(150);
}

async function openSessionTab(page: Page, tab: "Pointage" | "Équipes A/B" | "Bilan"): Promise<void> {
  await page.goto(SESSION_URL);
  await expect(page.getByRole("heading", { name: /Séance du/ })).toBeVisible();
  await page.getByRole("tab", { name: tab }).click();
}

/** Décoche les derniers joueurs cochés au-delà de `max` (départ groupé : 12 au plus). */
async function uncheckBeyond(dialog: Locator, max: number): Promise<void> {
  const checked = dialog.getByRole("checkbox", { checked: true });
  while ((await checked.count()) > max) await checked.last().uncheck();
}

/** Ouvre « Mesurer », choisit le test, la méthode Chronomètre et coche tous les pointés (au plus `max`). */
async function openMeasureChoose(page: Page, testName: RegExp, max?: number): Promise<Locator> {
  await openSessionTab(page, "Bilan");
  await page.getByRole("button", { name: "Mesurer" }).first().click();
  const dialog = page.getByRole("dialog").filter({ hasText: "Mesurer" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("radio", { name: testName }).first().click();
  await dialog.getByRole("radio", { name: "Chronomètre" }).or(dialog.getByRole("button", { name: "Chronomètre" })).first().click();
  await expect(dialog.getByRole("checkbox").first()).toBeVisible();
  await dialog.getByRole("button", { name: "Tout cocher" }).click();
  if (max !== undefined) await uncheckBeyond(dialog, max);
  return dialog;
}

async function abandonOpenChrono(page: Page): Promise<void> {
  await page.keyboard.press("Escape");
  const confirm = page.getByRole("dialog").filter({ hasText: "Abandonner ces mesures ?" });
  if (await confirm.isVisible().catch(() => false)) {
    await confirm.getByRole("button", { name: "Abandonner" }).click();
  }
}

// ---------------------------------------------------------------------------
// 1. Chrono
// ---------------------------------------------------------------------------

test.describe("Chrono à 360 px", () => {
  test("group_start_stopwatch_with_all_present_players_before_during_and_after", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    const dialog = await openMeasureChoose(page, /Sprint 30 m/);
    if ((await dialog.getByRole("checkbox", { checked: true }).count()) > 12) {
      // Plus de 12 pointés : refus du départ groupé (bandeau d'erreur à capturer).
      await dialog.getByRole("button", { name: "Commencer" }).click();
      await expect(dialog.getByText(/12 joueurs au plus par départ groupé/)).toBeVisible();
      await shoot(page, "chrono-01b-choix-groupe-plus-de-12");
      await uncheckBeyond(dialog, 12);
    }
    const count = await dialog.getByRole("checkbox", { checked: true }).count();
    expect(count, "6 à 12 joueurs pour le départ groupé").toBeGreaterThanOrEqual(6);
    expect(count).toBeLessThanOrEqual(12);

    await dialog.getByRole("button", { name: "Commencer" }).click();
    const chrono = page.getByRole("dialog").filter({ hasText: /Chronomètre : Sprint 30 m/ });
    await expect(chrono.getByRole("timer")).toBeVisible();
    await shoot(page, "chrono-02-groupe-pret");

    await chrono.getByRole("button", { name: "Départ", exact: true }).click();
    await page.waitForTimeout(1200);
    const stops = chrono.getByRole("button", { name: /^Arrêter / });
    // Deux arrêts, le reste continue : état « pendant la course ».
    await stops.first().click();
    await stops.first().click();
    await shoot(page, "chrono-03-groupe-en-cours");

    // Abandon d'un joueur par le menu de l'avatar.
    await chrono.getByRole("button", { name: /^Options pour / }).last().click();
    await shoot(page, "chrono-04-groupe-menu-joueur");
    await chrono.getByRole("button", { name: "Abandon", exact: true }).click();

    while ((await stops.count()) > 0) await stops.first().click();
    await expect(chrono.getByText("Chrono terminé")).toBeVisible();
    await shoot(page, "chrono-05-groupe-termine");

    await chrono.getByRole("button", { name: /^Enregistrer \(\d+\)$/ }).click();
    const review = page.getByRole("alertdialog").or(page.getByRole("dialog").filter({ hasText: /Envoyer \d+ mesures/ })).last();
    await expect(review).toBeVisible();
    await shoot(page, "chrono-06-groupe-confirmation-envoi");
    await review.getByRole("button", { name: "Annuler" }).click();
    await abandonOpenChrono(page);
  });

  test("individual_start_stopwatch_before_during_and_after", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    const dialog = await openMeasureChoose(page, /Sprint 30 m/);
    await dialog.getByRole("radio", { name: "Un par un" }).or(dialog.getByRole("button", { name: "Un par un" })).first().click();
    await shoot(page, "chrono-07-choix-un-par-un");
    await dialog.getByRole("button", { name: "Commencer" }).click();
    const chrono = page.getByRole("dialog").filter({ hasText: /Chronomètre : Sprint 30 m/ });
    await expect(chrono.getByRole("button", { name: /^Départ de / })).toBeVisible();
    await shoot(page, "chrono-08-individuel-pret");

    await chrono.getByRole("button", { name: /^Départ de / }).click();
    await page.waitForTimeout(800);
    await shoot(page, "chrono-09-individuel-en-cours");
    await chrono.getByRole("button", { name: /^Arrêter / }).click();
    // Deuxième joueur lancé puis arrêté : on termine avec des joueurs non partis.
    await chrono.getByRole("button", { name: /^Départ de / }).click();
    await page.waitForTimeout(600);
    await chrono.getByRole("button", { name: /^Arrêter / }).click();
    await shoot(page, "chrono-10-individuel-deux-arretes");
    await chrono.getByRole("button", { name: "Terminer" }).click();
    const confirmStop = page.getByRole("dialog").filter({ hasText: "Arrêter le chrono ?" });
    if (await confirmStop.isVisible().catch(() => false)) {
      await shoot(page, "chrono-11-individuel-confirmation-arret");
      await confirmStop.getByRole("button", { name: "Arrêter", exact: true }).click();
    }
    await expect(chrono.getByText("Chrono terminé")).toBeVisible();
    await shoot(page, "chrono-12-individuel-termine");
    await abandonOpenChrono(page);
  });

  test("cooper_countdown_and_distance_entry", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    const dialog = await openMeasureChoose(page, /Cooper/);
    await dialog.getByRole("button", { name: "Commencer" }).click();
    const chrono = page.getByRole("dialog").filter({ hasText: /Chronomètre : Test de Cooper/ });
    await expect(chrono.getByRole("timer")).toHaveText("12:00");
    await shoot(page, "chrono-13-cooper-pret");
    await chrono.getByRole("button", { name: "Départ", exact: true }).click();
    await page.waitForTimeout(1500);
    await shoot(page, "chrono-14-cooper-en-cours");
    await chrono.getByRole("button", { name: "Terminer maintenant" }).click();
    const manual = page.getByRole("dialog").last();
    await expect(manual.getByText("Temps écoulé. Saisissez la distance de chaque joueur.")).toBeVisible();
    await shoot(page, "chrono-15-cooper-saisie-vide", { focus: true });
    const inputs = manual.locator("input[inputmode], input[type=number], input[type=text]");
    const n = Math.min(await inputs.count(), 3);
    for (let i = 0; i < n; i += 1) await inputs.nth(i).fill(String(2400 + i * 150));
    await shoot(page, "chrono-16-cooper-saisie-remplie");
    await abandonOpenChrono(page);
  });

  test("unsaved_stopwatch_banner_after_reload", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    const dialog = await openMeasureChoose(page, /Sprint 30 m/, 8);
    await dialog.getByRole("button", { name: "Commencer" }).click();
    const chrono = page.getByRole("dialog").filter({ hasText: /Chronomètre : Sprint 30 m/ });
    await chrono.getByRole("button", { name: "Départ", exact: true }).click();
    await page.waitForTimeout(1500);
    await page.reload();
    await expect(page.getByText(/Un chrono non enregistré a été retrouvé/)).toBeVisible();
    await shoot(page, "chrono-17-bandeau-retrouve", { focus: true });
    await page.getByRole("button", { name: "Abandonner" }).first().click();
    const confirm = page.getByRole("dialog").filter({ hasText: "Abandonner ces mesures ?" });
    await expect(confirm).toBeVisible();
    await shoot(page, "chrono-18-bandeau-confirmation-abandon");
    await confirm.getByRole("button", { name: "Abandonner" }).click();
    await expect(page.getByText(/Un chrono non enregistré a été retrouvé/)).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// 2. Vestiaire « Aujourd'hui / Plans »
// ---------------------------------------------------------------------------

test.describe("Vestiaire à 360 px", () => {
  for (const [role, email] of [
    ["coach", DEMO.coach],
    ["joueur", DEMO.player],
  ] as const) {
    test(`locker_room_today_and_plans_tabs_for_${role}`, async ({ page }) => {
      await loginAs(page, email);
      await page.goto("/vestiaire");
      await expect(page.getByRole("heading", { name: "Vestiaire du jour" })).toBeVisible();
      await page.waitForLoadState("networkidle");
      await shoot(page, `vestiaire-${role}-01-aujourdhui-liste`, { focus: true });
      await page.getByRole("radio", { name: "Terrain" }).or(page.getByRole("button", { name: "Terrain", exact: true })).first().click();
      await page.waitForLoadState("networkidle");
      await shoot(page, `vestiaire-${role}-02-aujourdhui-terrain`);
      await page.getByRole("radio", { name: "Plans" }).or(page.getByRole("button", { name: "Plans", exact: true })).first().click();
      await expect(page).toHaveURL(/onglet=plans/);
      await page.waitForLoadState("networkidle");
      await shoot(page, `vestiaire-${role}-03-plans`);
      const firstPlan = page.getByText("Démo — 4-3-3 de base").first();
      if (await firstPlan.isVisible().catch(() => false)) {
        await firstPlan.click();
        await expect(page.getByRole("dialog")).toBeVisible();
        await page.waitForLoadState("networkidle");
        await shoot(page, `vestiaire-${role}-04-detail-plan`);
      }
    });
  }
});

// ---------------------------------------------------------------------------
// 3. Cartes des joueurs
// ---------------------------------------------------------------------------

test.describe("Cartes des joueurs à 360 px", () => {
  test("cards_grid_detail_comparison_and_table", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await page.goto("/club/joueurs");
    await expect(page.getByRole("heading", { name: "Cartes des joueurs" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await shoot(page, "cartes-01-grille", { focus: true });

    await page.getByText(/Victor Echant/).first().click();
    await expect(page.getByRole("dialog", { name: "Fiche du joueur" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await shoot(page, "cartes-02-fiche-joueur");
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "Comparer", exact: true }).click();
    await shoot(page, "cartes-03-mode-comparaison");
    await page.getByRole("checkbox", { name: "Comparer Alain Démoa" }).check();
    await page.getByRole("checkbox", { name: "Comparer Bruno Fictifb" }).check();
    await page.getByRole("checkbox", { name: /^Comparer / }).nth(2).check();
    await shoot(page, "cartes-04-comparaison-selection");
    await page.getByRole("button", { name: /Comparer \(\d\)/ }).click();
    await expect(page.getByRole("dialog").getByText(/Comparer des joueurs/).first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    await shoot(page, "cartes-05-modale-comparaison");
    await page.keyboard.press("Escape");

    await page.goto("/club/joueurs");
    await page.getByRole("radio", { name: "Tableau" }).or(page.getByRole("button", { name: "Tableau", exact: true })).first().click();
    await expect(page.getByRole("table")).toBeVisible();
    await shoot(page, "cartes-06-tableau");
  });
});

// ---------------------------------------------------------------------------
// 4. Modales du tableau de bord du Président / VP
// ---------------------------------------------------------------------------

test.describe("Tableau de bord à 360 px", () => {
  test("board_dashboard_page_and_every_detail_modal", async ({ page }) => {
    test.setTimeout(400_000);
    await loginAs(page, DEMO.president);
    await page.goto("/tableau-de-bord");
    await expect(page.getByRole("heading", { name: "Tableau de bord du club" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await shoot(page, "tdb-00-page", { focus: true });

    const detailButtons = page.getByRole("button", { name: /^Voir le détail : / });
    const labels = await detailButtons.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") ?? ""));
    expect(labels.length).toBeGreaterThan(0);
    for (const [index, label] of labels.entries()) {
      const slug = label
        .replace("Voir le détail : ", "")
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
      await page.getByRole("button", { name: label, exact: true }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      await page.waitForLoadState("networkidle");
      await shoot(page, `tdb-${String(index + 1).padStart(2, "0")}-${slug}`);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
    }

    await loginAs(page, DEMO.vicePresident);
    await page.goto("/tableau-de-bord");
    await expect(page.getByRole("heading", { name: "Tableau de bord du club" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await shoot(page, "tdb-vp-page");
  });
});

// ---------------------------------------------------------------------------
// 5. Barre d'actions du pointage groupé
// ---------------------------------------------------------------------------

test.describe("Pointage groupé à 360 px", () => {
  test("bulk_action_bar_and_confirmation_and_excuse_modals", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await openSessionTab(page, "Pointage");
    await page.waitForLoadState("networkidle");
    await shoot(page, "pointage-01-liste");
    await page.getByRole("button", { name: "Sélectionner" }).click();
    await shoot(page, "pointage-02-mode-selection-vide", { focus: true });

    const candidates = [...AVAILABLE_UNMARKED_PLAYERS, ...UNAVAILABLE_PLAYERS];
    let checked = 0;
    for (const name of candidates) {
      const box = page.getByRole("checkbox", { name: `Sélectionner ${name}` });
      if ((await box.count()) > 0) {
        await box.check();
        checked += 1;
      }
      if (checked >= 4) break;
    }
    test.skip(checked < 2, "Moins de deux joueurs non pointés dans la base de démo.");
    await shoot(page, "pointage-03-selection-barre");

    await page.getByRole("button", { name: /Pointer l'arrivée \(\d+\)/ }).click();
    const arrive = page.getByRole("dialog").last();
    await expect(arrive.getByText(/Heure enregistrée/)).toBeVisible();
    await shoot(page, "pointage-04-confirmation-arrivee");
    const otherTime = arrive.getByText("Indiquer une autre heure d'arrivée");
    if (await otherTime.isVisible().catch(() => false)) {
      await otherTime.click();
      await shoot(page, "pointage-05-confirmation-autre-heure");
    }
    const fold = arrive.getByText("Voir les joueurs");
    if (await fold.isVisible().catch(() => false)) {
      await fold.click();
      await shoot(page, "pointage-06-confirmation-liste-joueurs");
    }
    await arrive.getByRole("button", { name: "Annuler" }).click();

    await page.getByRole("button", { name: "Absent excusé" }).click();
    const excuse = page.getByRole("dialog").filter({ hasText: /absences? excusées?/ });
    await expect(excuse).toBeVisible();
    await shoot(page, "pointage-07-excuse-vide");
    // Validation sans motif : message d'erreur sous le champ.
    await excuse.getByRole("button", { name: /Marquer excusés/ }).click();
    await shoot(page, "pointage-08-excuse-erreur-motif");
    await excuse.getByRole("group", { name: "Motif" }).getByRole("button").first().click();
    await excuse.getByRole("textbox").fill("Déplacement professionnel prévu de longue date, prévenu la veille.");
    await shoot(page, "pointage-09-excuse-remplie");
    await excuse.getByRole("button", { name: "Annuler" }).click();
    const discard = page.getByRole("dialog").filter({ hasText: /Abandonner/ });
    if (await discard.isVisible().catch(() => false)) {
      await discard.getByRole("button", { name: /Abandonner/ }).last().click();
    }
    await page.getByRole("button", { name: "Terminer" }).click();
  });
});
