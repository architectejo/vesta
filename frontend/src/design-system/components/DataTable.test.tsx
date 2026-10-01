import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DataTable, type DataTableColumn } from "./DataTable";

interface Player {
  id: number;
  name: string;
  number: number;
}

const PLAYERS: Player[] = Array.from({ length: 25 }, (_, i) => ({
  id: i + 1,
  name: `Joueur ${i + 1}`,
  number: i + 1,
}));

const columns: Array<DataTableColumn<Player>> = [
  { key: "name", header: "Joueur", render: (p) => p.name, sortAccessor: (p) => p.name },
  { key: "number", header: "N°", render: (p) => p.number, align: "right" },
];

describe("DataTable", () => {
  it("affiche les colonnes, les lignes et le nombre de résultats", () => {
    render(
      <DataTable columns={columns} rows={PLAYERS.slice(0, 3)} getRowId={(p) => p.id} resultLabel="joueurs" />,
    );
    expect(screen.getByText("Joueur")).toBeInTheDocument();
    expect(screen.getByText("Joueur 1")).toBeInTheDocument();
    expect(screen.getByText("3 joueurs")).toBeInTheDocument();
  });

  it("appelle onRowClick au clic sur une ligne", async () => {
    const onRowClick = vi.fn();
    const user = userEvent.setup();
    render(
      <DataTable
        columns={columns}
        rows={PLAYERS.slice(0, 2)}
        getRowId={(p) => p.id}
        onRowClick={onRowClick}
      />,
    );
    await user.click(screen.getByText("Joueur 1"));
    expect(onRowClick).toHaveBeenCalledWith(PLAYERS[0]);
  });

  it("filtre les lignes avec la recherche (debounce)", async () => {
    const user = userEvent.setup();
    render(
      <DataTable
        columns={columns}
        rows={PLAYERS}
        getRowId={(p) => p.id}
        getSearchableText={(p) => p.name}
        searchPlaceholder="Rechercher un joueur"
      />,
    );
    await user.type(screen.getByPlaceholderText("Rechercher un joueur"), "Joueur 2");

    // Après le debounce, seuls les joueurs correspondant à "Joueur 2" restent
    // (Joueur 2, 20 à 25).
    expect(await screen.findByText("7 résultats")).toBeInTheDocument();
  });

  it("affiche l'état « aucun résultat » avec un bouton Effacer les filtres", async () => {
    const onClearFilters = vi.fn();
    const user = userEvent.setup();
    render(
      <DataTable
        columns={columns}
        rows={PLAYERS}
        getRowId={(p) => p.id}
        getSearchableText={(p) => p.name}
        onClearFilters={onClearFilters}
      />,
    );
    await user.type(screen.getByRole("searchbox"), "Zzzz");

    const button = await screen.findByRole("button", { name: "Effacer les filtres" });
    await user.click(button);
    expect(onClearFilters).toHaveBeenCalledTimes(1);
  });

  it("pagine à 20 lignes par défaut", async () => {
    const user = userEvent.setup();
    render(<DataTable columns={columns} rows={PLAYERS} getRowId={(p) => p.id} />);

    expect(screen.getByText("1–20 sur 25")).toBeInTheDocument();
    expect(screen.queryByText("Joueur 21")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Suivant" }));
    expect(screen.getByText("21–25 sur 25")).toBeInTheDocument();
    expect(screen.getByText("Joueur 21")).toBeInTheDocument();
  });

  it("trie par colonne quand un accesseur de tri est fourni", async () => {
    const user = userEvent.setup();
    render(
      <DataTable
        columns={columns}
        rows={[
          { id: 1, name: "Zoé", number: 9 },
          { id: 2, name: "Amos", number: 4 },
        ]}
        getRowId={(p) => p.id}
      />,
    );

    const table = screen.getByRole("table");
    let rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Zoé");

    await user.click(screen.getByRole("button", { name: /Joueur/ }));
    rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Amos");
  });

  it("affiche 5 lignes de squelette pendant le chargement, pas les données", () => {
    render(<DataTable columns={columns} rows={PLAYERS} getRowId={(p) => p.id} loading />);
    const table = screen.getByRole("table");
    const bodyRows = within(table).getAllByRole("row").slice(1); // sans l'en-tête
    expect(bodyRows).toHaveLength(5);
    expect(screen.queryByText("Joueur 1")).not.toBeInTheDocument();
  });

  it("affiche l'état vide par défaut sans filtre", () => {
    render(<DataTable columns={columns} rows={[]} getRowId={(p) => p.id} />);
    expect(screen.getByText("Rien à afficher pour l'instant.")).toBeInTheDocument();
  });

  it("applique une largeur fixe à une colonne, même sans colonne figée (grille des cotisations)", () => {
    const gridColumns: Array<DataTableColumn<Player>> = [
      { key: "name", header: "Joueur", render: (p) => p.name, widthPx: 120 },
      { key: "number", header: "N°", render: (p) => p.number, widthPx: 56 },
    ];
    render(<DataTable columns={gridColumns} rows={PLAYERS.slice(0, 1)} getRowId={(p) => p.id} variant="grid" />);
    const headers = screen.getAllByRole("columnheader");
    expect(headers[0]).toHaveStyle({ width: "120px" });
    expect(headers[1]).toHaveStyle({ width: "56px" });
  });

  it("défile une seule fois vers la colonne demandée quand les lignes sont chargées", () => {
    const gridColumns: Array<DataTableColumn<Player>> = [
      { key: "name", header: "Joueur", render: (p) => p.name, widthPx: 120 },
      { key: "m1", header: "Jan", render: () => "—", widthPx: 56 },
      { key: "m2", header: "Fév", render: () => "—", widthPx: 56 },
      { key: "m3", header: "Mars", render: () => "—", widthPx: 56 },
    ];
    render(
      <DataTable
        columns={gridColumns}
        rows={PLAYERS.slice(0, 1)}
        getRowId={(p) => p.id}
        stickyFirstColumn
        scrollToColumnKey="m3"
      />,
    );
    const scrollArea = screen.getByRole("table").parentElement as HTMLDivElement;
    // 120 (Joueur) + 56 (Jan) + 56 (Fév) - 120 (largeur figée retirée) = 112
    expect(scrollArea.scrollLeft).toBe(112);
  });
});
