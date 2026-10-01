import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Avatar } from "./Avatar";

describe("Avatar", () => {
  it("affiche les initiales du prénom et du nom sans photo", () => {
    render(<Avatar name="Jean Kabila" />);
    expect(screen.getByRole("img", { name: "Jean Kabila" })).toHaveTextContent("JK");
  });

  it("affiche la photo quand une URL est fournie", () => {
    render(<Avatar name="Jean Kabila" photoUrl="https://example.test/photo.jpg" />);
    const img = screen.getByRole("img", { name: "Jean Kabila" });
    expect(img).toHaveAttribute("src", "https://example.test/photo.jpg");
  });
});
