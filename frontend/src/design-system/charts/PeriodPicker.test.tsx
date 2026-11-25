import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PeriodPicker, formatMonthLabel, shiftMonth, type PeriodValue } from "./PeriodPicker";

const NOW = new Date(2026, 10, 15);
const SEASONS = [
  { id: "s2026", label: "2026-2027" },
  { id: "s2025", label: "2025-2026" },
];

describe("PeriodPicker (fonctions)", () => {
  it("décale les mois à travers les années et formate en français", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(formatMonthLabel("2026-11")).toBe("novembre 2026");
  });
});

describe("PeriodPicker", () => {
  it("affiche le mois et navigue avec les flèches", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<PeriodPicker value={{ mode: "month", month: "2026-10" }} onChange={onChange} now={NOW} />);
    expect(screen.getByText("octobre 2026")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mois précédent" }));
    expect(onChange).toHaveBeenLastCalledWith({ mode: "month", month: "2026-09" });
    await user.click(screen.getByRole("button", { name: "Mois suivant" }));
    expect(onChange).toHaveBeenLastCalledWith({ mode: "month", month: "2026-11" });
  });

  it("désactive « suivant » sur le mois en cours (pas de mois futur)", () => {
    render(<PeriodPicker value={{ mode: "month", month: "2026-11" }} onChange={() => undefined} now={NOW} />);
    expect(screen.getByRole("button", { name: "Mois suivant" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Mois précédent" })).toBeEnabled();
  });

  it("désactive « précédent » au mois minimal fourni", () => {
    render(<PeriodPicker value={{ mode: "month", month: "2026-03" }} minMonth="2026-03" onChange={() => undefined} now={NOW} />);
    expect(screen.getByRole("button", { name: "Mois précédent" })).toBeDisabled();
  });

  it("bascule en Saison sur la plus récente puis navigue vers les anciennes", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <PeriodPicker value={{ mode: "month", month: "2026-11" }} onChange={onChange} seasons={SEASONS} now={NOW} />,
    );
    await user.click(screen.getByRole("button", { name: "Saison" }));
    expect(onChange).toHaveBeenLastCalledWith({ mode: "season", seasonId: "s2026" });

    const value: PeriodValue = { mode: "season", seasonId: "s2026" };
    rerender(<PeriodPicker value={value} onChange={onChange} seasons={SEASONS} now={NOW} />);
    expect(screen.getByText("Saison 2026-2027")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Saison suivante" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Saison précédente" }));
    expect(onChange).toHaveBeenLastCalledWith({ mode: "season", seasonId: "s2025" });
  });

  it("masque « Saison » quand aucune saison n'est fournie et retourne au mois en cours", async () => {
    const onChange = vi.fn();
    render(<PeriodPicker value={{ mode: "month", month: "2026-05" }} onChange={onChange} now={NOW} />);
    expect(screen.queryByRole("button", { name: "Saison" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mois" })).toHaveAttribute("aria-pressed", "true");
  });

  it("revient au mois le plus récent depuis la saison", async () => {
    const onChange = vi.fn();
    render(<PeriodPicker value={{ mode: "season", seasonId: "s2025" }} onChange={onChange} seasons={SEASONS} now={NOW} />);
    await userEvent.click(screen.getByRole("button", { name: "Mois" }));
    expect(onChange).toHaveBeenCalledWith({ mode: "month", month: "2026-11" });
  });

  it("boutons des flèches d'au moins 40 px (h-10 w-10)", () => {
    render(<PeriodPicker value={{ mode: "month", month: "2026-10" }} onChange={() => undefined} now={NOW} />);
    expect(screen.getByRole("button", { name: "Mois précédent" }).className).toContain("h-10 w-10");
  });
});
