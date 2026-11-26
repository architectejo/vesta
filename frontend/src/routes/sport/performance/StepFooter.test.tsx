import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StepFooter } from "./StepFooter";

describe("StepFooter", () => {
  it("colle au bord bas du corps défilant de la modale, rembourrage de 16 px compris", () => {
    // Vérification visuelle B3 (360 px) : avec `bottom-0`, le pied restait
    // 16 px au-dessus du bord pendant le défilement ; les lignes du chrono
    // restaient visibles et touchables dessous (un « Arrêter » involontaire).
    // jsdom ne calcule pas la mise en page : on fige le décalage attendu.
    render(
      <StepFooter>
        <button type="button">Terminer</button>
      </StepFooter>,
    );
    const footer = screen.getByRole("button", { name: "Terminer" }).parentElement!;
    const classes = footer.className.split(/\s+/);
    expect(classes).toContain("sticky");
    expect(classes).toContain("-bottom-4");
    expect(classes).toContain("-mb-4");
    // Au-dessus des avatars et des temps des lignes du chrono (`relative z-10`).
    expect(classes).toContain("z-20");
    expect(classes).not.toContain("bottom-0");
  });
});
