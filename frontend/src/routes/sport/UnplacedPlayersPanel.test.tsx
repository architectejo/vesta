import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { MembershipBrief } from "../../api/sport";
import { UnplacedPlayersPanel } from "./UnplacedPlayersPanel";

function brief(id: number, name: string, position: string, label: string): MembershipBrief {
  return { membership_id: id, name, jersey_number: id, position, position_label: label, photo: null };
}

const players = [
  brief(1, "Zoé Attaque", "forward", "Attaquant"),
  brief(2, "Sans Poste", "", ""),
  brief(3, "Yves Gardien", "goalkeeper", "Gardien"),
  brief(4, "Albert Défense", "defender", "Défenseur"),
  brief(5, "Abel Gardien", "goalkeeper", "Gardien"),
];

function pinNames(container: HTMLElement = document.body): string[] {
  return Array.from(container.querySelectorAll("[title]")).map((el) => el.getAttribute("title") ?? "");
}

describe("UnplacedPlayersPanel — joueurs à placer subdivisés par poste (remarques.md)", () => {
  it("sous « Tous » : intertitres par poste, sans poste en dernier, joueurs triés par nom", () => {
    render(<UnplacedPlayersPanel players={players} draggable onTapPlayer={vi.fn()} />);
    expect(screen.getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual([
      "Gardiens (2)",
      "Défenseurs (1)",
      "Attaquants (1)",
      "Sans poste (1)",
    ]);
    expect(pinNames()).toEqual(["Abel Gardien", "Yves Gardien", "Albert Défense", "Zoé Attaque", "Sans Poste"]);
    expect(pinNames(screen.getByRole("region", { name: "Sans poste" }))).toEqual(["Sans Poste"]);
  });

  it("une puce filtre le poste ; le joueur sans poste n'apparaît que sous « Tous »", async () => {
    const user = userEvent.setup();
    render(<UnplacedPlayersPanel players={players} draggable onTapPlayer={vi.fn()} />);
    const chips = screen.getByRole("group", { name: "Filtrer les joueurs à placer par poste" });
    expect(within(chips).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Tous",
      "Gardiens",
      "Défenseurs",
      "Milieux",
      "Attaquants",
    ]);

    await user.click(within(chips).getByRole("button", { name: "Gardiens" }));
    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument();
    expect(pinNames()).toEqual(["Abel Gardien", "Yves Gardien"]);

    await user.click(within(chips).getByRole("button", { name: "Milieux" }));
    expect(screen.getByText("Aucun joueur à placer dans « Milieux ».")).toBeInTheDocument();

    await user.click(within(chips).getByRole("button", { name: "Tous" }));
    expect(pinNames()).toContain("Sans Poste");
  });

  it("toucher un joueur ouvre son menu (Passer en A / B) comme avant", async () => {
    const user = userEvent.setup();
    const onTap = vi.fn();
    render(<UnplacedPlayersPanel players={players} draggable onTapPlayer={onTap} />);
    await user.click(screen.getByTitle("Zoé Attaque"));
    expect(onTap).toHaveBeenCalledWith(1, "Zoé Attaque");
  });

  it("un seul joueur : pas de puces", () => {
    render(<UnplacedPlayersPanel players={[players[0]!]} draggable onTapPlayer={vi.fn()} />);
    expect(screen.queryByRole("group", { name: /Filtrer/ })).not.toBeInTheDocument();
  });
});
