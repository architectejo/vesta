import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { PlansRedirect } from "./PlansRedirect";

function Where() {
  const { pathname, search } = useLocation();
  return <p>{`${pathname}${search}`}</p>;
}

describe("PlansRedirect", () => {
  it("renvoie /plans?plan=3 vers l'onglet Plans du Vestiaire en gardant le plan", () => {
    render(
      <MemoryRouter initialEntries={["/plans?plan=3"]}>
        <Routes>
          <Route path="/plans" element={<PlansRedirect />} />
          <Route path="/vestiaire" element={<Where />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("/vestiaire?plan=3&onglet=plans")).toBeInTheDocument();
  });

  it("renvoie /plans seul vers l'onglet Plans", () => {
    render(
      <MemoryRouter initialEntries={["/plans"]}>
        <Routes>
          <Route path="/plans" element={<PlansRedirect />} />
          <Route path="/vestiaire" element={<Where />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("/vestiaire?onglet=plans")).toBeInTheDocument();
  });
});
