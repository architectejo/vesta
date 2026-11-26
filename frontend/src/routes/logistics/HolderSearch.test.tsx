import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HolderPicker } from "./HolderPicker";
import { HolderSearch } from "./HolderSearch";
import { makeHolder, makeHolderList, renderWithProviders, stockRow } from "./testFixtures";

vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return { ...actual, listHolders: vi.fn() };
});

import { listHolders } from "../../api/logistics";

const HOLDERS = [
  makeHolder({ id: 1, name: "Local du club", stock_total: 12 }),
  makeHolder({ id: 2, kind: "member", name: "Éric Mbala", membership_id: 40, stock_total: 3 }),
  makeHolder({ id: 3, kind: "member", name: "Jean Parti", membership_id: 41, has_left_club: true, stock_total: 2 }),
];

describe("HolderSearch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listHolders).mockResolvedValue(makeHolderList(HOLDERS, 5));
  });

  it("propose les détenteurs dès l'ouverture, sans joueurs partis comme destination", async () => {
    const user = userEvent.setup();
    renderWithProviders(<HolderSearch value={null} onChange={() => {}} />);
    await user.click(screen.getByRole("combobox"));
    expect(await screen.findByText("Local du club")).toBeInTheDocument();
    expect(screen.getByText("Éric Mbala")).toBeInTheDocument();
    expect(screen.getByText("12 pièces")).toBeInTheDocument();
    expect(screen.queryByText("Jean Parti")).not.toBeInTheDocument();
    expect(screen.queryByText("Non localisé")).not.toBeInTheDocument();
  });

  it("filtre sans tenir compte de la casse ni des accents", async () => {
    const user = userEvent.setup();
    renderWithProviders(<HolderSearch value={null} onChange={() => {}} />);
    await user.type(screen.getByRole("combobox"), "eric");
    await waitFor(() => expect(screen.queryByText("Local du club")).not.toBeInTheDocument());
    expect(screen.getByText("Éric Mbala")).toBeInTheDocument();
  });

  it("en filtre : garde les joueurs partis et propose « Non localisé » (valeur null)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithProviders(<HolderSearch value={null} onChange={onChange} allowUnlocated purpose="filter" />);
    await user.click(screen.getByRole("combobox"));
    expect(await screen.findByText("Jean Parti")).toBeInTheDocument();
    await user.click(screen.getByText("Non localisé"));
    expect(onChange).toHaveBeenCalledWith({ id: null, name: "Non localisé" });
  });

  it("Intendant : dernière option « Ajouter un détenteur » qui ouvre la modale d'ajout", async () => {
    const user = userEvent.setup();
    renderWithProviders(<HolderSearch value={null} onChange={() => {}} canCreate />);
    await user.click(screen.getByRole("combobox"));
    const options = await screen.findAllByRole("option");
    expect(options[options.length - 1]).toHaveTextContent("Ajouter un détenteur");
    await user.click(options[options.length - 1]!);
    expect(await screen.findByRole("dialog", { name: "Ajouter un détenteur" })).toBeInTheDocument();
  });
});

describe("HolderPicker", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("affiche une puce radio par source, « Non localisé » renvoie null", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithProviders(
      <HolderPicker
        label="D'où sort le matériel ?"
        rows={[stockRow(1, "Local du club", 8), stockRow(null, "Non localisé", 4)]}
        value={1}
        onChange={onChange}
      />,
    );
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(radios[0]).toHaveAttribute("aria-checked", "true");
    expect(radios[0]).toHaveTextContent("Local du club · 8");
    await user.click(radios[1]!);
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("au-delà de 5 sources, bascule sur une recherche limitée à ces sources", async () => {
    const user = userEvent.setup();
    const rows = [1, 2, 3, 4, 5, 6].map((id) => stockRow(id, `Lieu ${id}`, id));
    const onChange = vi.fn();
    renderWithProviders(<HolderPicker label="De" rows={rows} value={undefined} onChange={onChange} />);
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByText("Lieu 6"));
    expect(onChange).toHaveBeenCalledWith(6);
    expect(listHolders).not.toHaveBeenCalled();
  });
});
