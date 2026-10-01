import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IconButton } from "./IconButton";

describe("IconButton", () => {
  it("expose son aria-label en français", () => {
    render(<IconButton aria-label="Fermer" icon={<span aria-hidden>x</span>} />);
    expect(screen.getByRole("button", { name: "Fermer" })).toBeInTheDocument();
  });
});
