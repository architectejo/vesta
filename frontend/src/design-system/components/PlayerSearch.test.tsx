import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PlayerMultiSearch, PlayerSearch, type PlayerSearchResult } from "./PlayerSearch";

const AMOS: PlayerSearchResult = {
  id: 1,
  firstName: "Amos",
  lastName: "Kanku",
  number: 4,
  position: "Défenseur",
  eligible: true,
};

const JEAN: PlayerSearchResult = {
  id: 2,
  firstName: "Jean",
  lastName: "Kabila",
  number: 10,
  position: "Attaquant",
  eligible: false,
  ineligibleReason: "En dette : 20 $",
};

function makeSearch(results: PlayerSearchResult[]) {
  return vi.fn(async (_query: string) => results);
}

describe("PlayerSearch", () => {
  it("affiche l'aide initiale au focus, avant toute saisie", async () => {
    const user = userEvent.setup();
    render(
      <PlayerSearch value={null} onChange={vi.fn()} searchPlayers={makeSearch([AMOS])} />,
    );
    await user.click(screen.getByRole("combobox"));
    expect(screen.getByText("Tapez un nom ou un numéro.")).toBeInTheDocument();
  });

  it("affiche les suggestions puis sélectionne un joueur au clic", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <PlayerSearch value={null} onChange={onChange} searchPlayers={makeSearch([AMOS])} />,
    );
    await user.type(screen.getByRole("combobox"), "Amos");

    const option = await screen.findByRole("option", { name: /Amos Kanku/ });
    await user.click(option);

    expect(onChange).toHaveBeenCalledWith(AMOS);
  });

  it("remplace le champ par une puce joueur une fois sélectionné, avec bouton Changer", () => {
    render(<PlayerSearch value={AMOS} onChange={vi.fn()} searchPlayers={makeSearch([])} />);
    expect(screen.getByText("Amos Kanku")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Changer" })).toBeInTheDocument();
  });

  it("« Changer » revient au champ de recherche", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<PlayerSearch value={AMOS} onChange={onChange} searchPlayers={makeSearch([])} />);
    await user.click(screen.getByRole("button", { name: "Changer" }));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("grise les joueurs non éligibles et affiche la raison de l'API, sans les rendre sélectionnables", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <PlayerSearch value={null} onChange={onChange} searchPlayers={makeSearch([JEAN])} />,
    );
    await user.type(screen.getByRole("combobox"), "Jean");

    const option = await screen.findByRole("option", { name: /Jean Kabila/ });
    expect(option).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("En dette : 20 $")).toBeInTheDocument();

    await user.click(option);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("affiche un message d'erreur si la recherche échoue", async () => {
    const user = userEvent.setup();
    const failingSearch = vi.fn(async () => {
      throw new Error("network");
    });
    render(<PlayerSearch value={null} onChange={vi.fn()} searchPlayers={failingSearch} />);
    await user.type(screen.getByRole("combobox"), "Amos");

    expect(
      await screen.findByText("Recherche impossible. Vérifiez votre connexion."),
    ).toBeInTheDocument();
  });

  it("affiche « aucun joueur » quand la recherche ne trouve rien", async () => {
    const user = userEvent.setup();
    render(<PlayerSearch value={null} onChange={vi.fn()} searchPlayers={makeSearch([])} />);
    await user.type(screen.getByRole("combobox"), "Zzzz");

    expect(
      await screen.findByText("Aucun joueur ne correspond à « Zzzz ».", { exact: false }),
    ).toBeInTheDocument();
  });

  it("permet de sélectionner au clavier (flèches puis Entrée)", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    // Le premier résultat (Jean) est inéligible : la flèche bas doit déplacer
    // la sélection clavier vers le second (Amos), que Entrée confirme.
    render(
      <PlayerSearch value={null} onChange={onChange} searchPlayers={makeSearch([JEAN, AMOS])} />,
    );
    const input = screen.getByRole("combobox");
    await user.type(input, "a");
    await screen.findByRole("option", { name: /Amos Kanku/ });

    await user.keyboard("{ArrowDown}{Enter}");
    expect(onChange).toHaveBeenCalledWith(AMOS);
  });
});

describe("PlayerMultiSearch", () => {
  it("ajoute des joueurs sous forme de puces retirables", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <PlayerMultiSearch values={[]} onChange={onChange} searchPlayers={makeSearch([AMOS])} />,
    );
    await user.type(screen.getByRole("combobox"), "Amos");
    const option = await screen.findByRole("option", { name: /Amos Kanku/ });
    await user.click(option);
    expect(onChange).toHaveBeenCalledWith([AMOS]);

    rerender(
      <PlayerMultiSearch
        values={[AMOS]}
        onChange={onChange}
        searchPlayers={makeSearch([AMOS])}
      />,
    );
    expect(screen.getByRole("button", { name: "Retirer Amos Kanku" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retirer Amos Kanku" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
