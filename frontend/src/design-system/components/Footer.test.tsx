import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Footer, FOOTER_TEXT } from "./Footer";

describe("Footer", () => {
  it("affiche le texte exact et unique de l'éditeur", () => {
    render(<Footer />);
    expect(screen.getByText(FOOTER_TEXT)).toBeInTheDocument();
  });

  it("n'est pas positionné en collant (pas de classe fixed/sticky)", () => {
    render(<Footer />);
    const footer = screen.getByText(FOOTER_TEXT).closest("footer");
    expect(footer?.className).not.toMatch(/\b(fixed|sticky)\b/);
  });
});
