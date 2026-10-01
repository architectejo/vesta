import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ArticleSearch, type ArticleSearchResult } from "./ArticleSearch";

const MAILLOT: ArticleSearchResult = {
  id: 1,
  name: "Maillot domicile",
  categoryLabel: "Maillots",
  unit: "pièce",
  inStock: 12,
};

const BALLON_VIDE: ArticleSearchResult = {
  id: 2,
  name: "Ballon",
  categoryLabel: "Ballons",
  unit: "pièce",
  inStock: 0,
};

function makeSearch(results: ArticleSearchResult[]) {
  return vi.fn(async (_query: string) => results);
}

describe("ArticleSearch", () => {
  it("affiche les suggestions puis sélectionne un article au clic", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ArticleSearch value={null} onChange={onChange} searchArticles={makeSearch([MAILLOT])} />);
    await user.type(screen.getByRole("combobox"), "Maillot");

    const option = await screen.findByRole("option", { name: /Maillot domicile/ });
    await user.click(option);

    expect(onChange).toHaveBeenCalledWith(MAILLOT);
  });

  it("remplace le champ par une puce article une fois sélectionné, avec le stock et « Changer »", () => {
    render(<ArticleSearch value={MAILLOT} onChange={vi.fn()} searchArticles={makeSearch([])} />);
    expect(screen.getByText("Maillot domicile")).toBeInTheDocument();
    expect(screen.getByText("En stock : 12")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Changer" })).toBeInTheDocument();
  });

  it("« Changer » revient au champ de recherche", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ArticleSearch value={MAILLOT} onChange={onChange} searchArticles={makeSearch([])} />);
    await user.click(screen.getByRole("button", { name: "Changer" }));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("mode « out » : grise un article à stock nul et l'empêche d'être sélectionné", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ArticleSearch value={null} onChange={onChange} searchArticles={makeSearch([BALLON_VIDE])} mode="out" />,
    );
    await user.type(screen.getByRole("combobox"), "Ballon");

    const option = await screen.findByRole("option", { name: /Ballon/ });
    expect(option).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Stock épuisé")).toBeInTheDocument();

    await user.click(option);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("mode « in » : un article à stock nul reste sélectionnable", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ArticleSearch value={null} onChange={onChange} searchArticles={makeSearch([BALLON_VIDE])} mode="in" />);
    await user.type(screen.getByRole("combobox"), "Ballon");

    const option = await screen.findByRole("option", { name: /Ballon/ });
    await user.click(option);
    expect(onChange).toHaveBeenCalledWith(BALLON_VIDE);
  });

  it("exclut les articles déjà choisis sur une autre ligne", async () => {
    const user = userEvent.setup();
    render(
      <ArticleSearch
        value={null}
        onChange={vi.fn()}
        searchArticles={makeSearch([MAILLOT, BALLON_VIDE])}
        excludeIds={new Set([1])}
      />,
    );
    await user.type(screen.getByRole("combobox"), "a");

    await screen.findByRole("option", { name: /Ballon/ });
    expect(screen.queryByRole("option", { name: /Maillot domicile/ })).not.toBeInTheDocument();
  });

  it("affiche un message d'erreur si la recherche échoue", async () => {
    const user = userEvent.setup();
    const failingSearch = vi.fn(async () => {
      throw new Error("network");
    });
    render(<ArticleSearch value={null} onChange={vi.fn()} searchArticles={failingSearch} />);
    await user.type(screen.getByRole("combobox"), "Maillot");

    expect(await screen.findByText("Recherche impossible. Vérifiez votre connexion.")).toBeInTheDocument();
  });

  it("affiche « aucun article » quand la recherche ne trouve rien", async () => {
    const user = userEvent.setup();
    render(<ArticleSearch value={null} onChange={vi.fn()} searchArticles={makeSearch([])} />);
    await user.type(screen.getByRole("combobox"), "Zzzz");

    expect(await screen.findByText("Aucun article ne correspond à « Zzzz ».", { exact: false })).toBeInTheDocument();
  });
});
