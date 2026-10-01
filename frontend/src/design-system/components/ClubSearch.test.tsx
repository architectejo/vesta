import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ClubSearch, type ClubSearchResult } from "./ClubSearch";

const DISCOVERY: ClubSearchResult = { id: 1, name: "Loisirs Club Discovery", city: "Kinshasa" };

function makeSearch(results: ClubSearchResult[]) {
  return vi.fn(async (_query: string) => results);
}

describe("ClubSearch", () => {
  it("affiche les suggestions puis sélectionne un club au clic", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ClubSearch value={null} onChange={onChange} searchClubs={makeSearch([DISCOVERY])} />);
    await user.type(screen.getByRole("combobox"), "Discovery");

    const option = await screen.findByRole("option", { name: /Loisirs Club Discovery/ });
    await user.click(option);

    expect(onChange).toHaveBeenCalledWith(DISCOVERY);
  });

  it("remplace le champ par une puce club une fois sélectionné, avec « Changer »", () => {
    render(<ClubSearch value={DISCOVERY} onChange={vi.fn()} searchClubs={makeSearch([])} />);
    expect(screen.getByText("Loisirs Club Discovery")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Changer" })).toBeInTheDocument();
  });

  it("« Changer » revient au champ de recherche", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ClubSearch value={DISCOVERY} onChange={onChange} searchClubs={makeSearch([])} />);
    await user.click(screen.getByRole("button", { name: "Changer" }));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("affiche « aucun club » quand la recherche ne trouve rien", async () => {
    const user = userEvent.setup();
    render(<ClubSearch value={null} onChange={vi.fn()} searchClubs={makeSearch([])} />);
    await user.type(screen.getByRole("combobox"), "Zzzz");

    expect(await screen.findByText("Aucun club ne correspond à « Zzzz ».", { exact: false })).toBeInTheDocument();
  });

  it("affiche un message d'erreur si la recherche échoue", async () => {
    const user = userEvent.setup();
    const failingSearch = vi.fn(async () => {
      throw new Error("network");
    });
    render(<ClubSearch value={null} onChange={vi.fn()} searchClubs={failingSearch} />);
    await user.type(screen.getByRole("combobox"), "Discovery");

    expect(await screen.findByText("Recherche impossible. Vérifiez votre connexion.")).toBeInTheDocument();
  });
});
