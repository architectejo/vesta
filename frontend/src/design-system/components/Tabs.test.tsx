import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Tabs } from "./Tabs";

type Tab = "a" | "b" | "c" | "d" | "e";
const ITEMS: Array<{ value: Tab; label: string }> = [
  { value: "a", label: "Effectif" },
  { value: "b", label: "En règle" },
  { value: "c", label: "En dette" },
  { value: "d", label: "Inaptes" },
  { value: "e", label: "Suspendus" },
];

// jsdom ne calcule pas la mise en page : on simule une barre de 200 px qui
// contient 5 onglets de 90 px espacés de 100 px (500 px au total).
const TAB_STEP = 100;
const TAB_WIDTH = 90;
const BAR_WIDTH = 200;
const scrollPositions = new WeakMap<Element, number>();

function isTablist(el: Element): boolean {
  return el.getAttribute("role") === "tablist";
}

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockImplementation(function (this: HTMLElement) {
    return isTablist(this) ? this.children.length * TAB_STEP : 0;
  });
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(function (this: HTMLElement) {
    return isTablist(this) ? BAR_WIDTH : 0;
  });
  vi.spyOn(HTMLElement.prototype, "offsetLeft", "get").mockImplementation(function (this: HTMLElement) {
    if (this.getAttribute("role") !== "tab" || !this.parentElement) return 0;
    return Array.from(this.parentElement.children).indexOf(this) * TAB_STEP;
  });
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockImplementation(function (this: HTMLElement) {
    return this.getAttribute("role") === "tab" ? TAB_WIDTH : 0;
  });
  vi.spyOn(Element.prototype, "scrollLeft", "get").mockImplementation(function (this: Element) {
    return scrollPositions.get(this) ?? 0;
  });
  vi.spyOn(Element.prototype, "scrollLeft", "set").mockImplementation(function (this: Element, v: number) {
    scrollPositions.set(this, v);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function Harness({ initial = "a" as Tab }: { initial?: Tab }) {
  const [value, setValue] = useState<Tab>(initial);
  return <Tabs items={ITEMS} value={value} onChange={setValue} label="Situation de l'effectif" />;
}

describe("Tabs — indice de défilement (vérification visuelle B7)", () => {
  it("signale par un fondu à droite qu'il reste des onglets cachés", () => {
    render(<Harness />);
    const list = screen.getByRole("tablist", { name: "Situation de l'effectif" });
    expect(list).toHaveAttribute("data-overflow-end");
    expect(list).not.toHaveAttribute("data-overflow-start");
    expect(list.style.maskImage).toContain("transparent 100%");
    expect(list.style.maskImage).not.toContain("transparent 0");
  });

  it("met un fondu à gauche une fois défilé, et retire celui de droite au bout", () => {
    render(<Harness />);
    const list = screen.getByRole("tablist");
    act(() => {
      list.scrollLeft = 300;
    });
    fireEvent.scroll(list);
    expect(list).toHaveAttribute("data-overflow-start");
    expect(list).not.toHaveAttribute("data-overflow-end");
    expect(list.style.maskImage).toContain("transparent 0");
  });

  it("n'affiche aucun fondu quand tous les onglets tiennent", () => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1000);
    render(<Harness />);
    const list = screen.getByRole("tablist");
    expect(list).not.toHaveAttribute("data-overflow-end");
    expect(list.style.maskImage).toBe("");
  });

  it("ramène l'onglet actif dans la vue quand il change", () => {
    render(<Harness initial="e" />);
    const list = screen.getByRole("tablist");
    // Onglet 5 : 400 → 490 px ; visible en entier avec la marge du fondu.
    expect(list.scrollLeft).toBe(400 + TAB_WIDTH + 24 - BAR_WIDTH);
    fireEvent.click(screen.getByRole("tab", { name: "Effectif" }));
    expect(list.scrollLeft).toBe(0);
  });

  it("le fondu ne bloque ni le clic ni la navigation au clavier", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.tab();
    expect(screen.getByRole("tab", { name: "Effectif" })).toHaveFocus();
    for (let i = 0; i < 4; i += 1) await user.tab();
    const last = screen.getByRole("tab", { name: "Suspendus" });
    expect(last).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(last).toHaveAttribute("aria-selected", "true");
  });
});
