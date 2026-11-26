import fs from "node:fs";
import path from "node:path";
import { expect, type Page } from "@playwright/test";

/**
 * Relevé automatique de la charte (CDC chapitre 3, CLAUDE.md §2.13–2.20) à
 * 360 px, repris de `12-intendance.spec.ts` (série 12) pour la série 6
 * (`13-serie6-plateforme.spec.ts`) : défilement horizontal, cibles < 36 px,
 * polices hors 12–24 px, textes coupés, pied collant qui masque du contenu,
 * empilement des modales.
 */
export interface AuditReport {
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
export async function audit(page: Page, width: number): Promise<AuditReport> {
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
 * Capture à 360 px (écran réel si une modale est ouverte, pleine page sinon),
 * relevé JSON et assertions souples de charte. Pour une modale, seconde
 * capture défilée jusqu'en bas (contenu sous le pied collant).
 */
export async function shoot(page: Page, outDir: string, name: string): Promise<AuditReport> {
  fs.mkdirSync(outDir, { recursive: true });
  await page.waitForTimeout(400);
  await page.setViewportSize({ width: 360, height: 740 });
  const dialogOpen = (await page.locator("[role=dialog]:visible, [role=alertdialog]:visible").count()) > 0;
  await page.screenshot({ path: path.join(outDir, `${name}.png`), fullPage: !dialogOpen });
  const report = await audit(page, 360);
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
    await page.screenshot({ path: path.join(outDir, `${name}-bas.png`) });
    await page.evaluate(() => {
      const dialogs = Array.from(document.querySelectorAll<HTMLElement>("[role=dialog],[role=alertdialog]"));
      const top = dialogs[dialogs.length - 1];
      for (const el of Array.from(top?.querySelectorAll<HTMLElement>("*") ?? [])) el.scrollTop = 0;
    });
  }
  fs.writeFileSync(path.join(outDir, `${name}.json`), JSON.stringify(report, null, 2));
  expect.soft(report.scrollWidth, `${name} : aucun défilement horizontal à 360 px`).toBeLessThanOrEqual(report.clientWidth);
  expect.soft(report.stickyOverlaps, `${name} : un pied collant masque du contenu`).toEqual([]);
  if (report.stack) {
    expect.soft(report.stack.topReceivesClicks, `${name} : la modale du dessus (${report.stack.topTitle}) reçoit les clics`).toBe(true);
  }
  return report;
}
