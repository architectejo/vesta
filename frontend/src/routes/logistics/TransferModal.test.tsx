import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { TransferModal } from "./TransferModal";
import {
  makeArticle,
  makeHolder,
  makeHolderList,
  makeMovement,
  renderWithProviders,
  toSearchResult,
} from "./testFixtures";

vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return { ...actual, createTransfer: vi.fn(), listHolders: vi.fn() };
});

import { createTransfer, listHolders } from "../../api/logistics";

const article = toSearchResult(makeArticle());

describe("TransferModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listHolders).mockResolvedValue(
      makeHolderList([
        makeHolder({ id: 1, name: "Local du club" }),
        makeHolder({ id: 2, kind: "member", name: "Éric Mbala", membership_id: 40 }),
      ]),
    );
    vi.mocked(createTransfer).mockResolvedValue({
      transfer_group: "g",
      out_movement: makeMovement(1),
      in_movement: makeMovement(2),
      in_stock: 12,
      stock_by_holder: [],
    });
  });

  async function chooseDestination(user: ReturnType<typeof userEvent.setup>, name: string) {
    await user.click(screen.getByRole("combobox", { name: "Nouveau détenteur" }));
    await user.click(await screen.findByText(name));
  }

  it("refuse un détenteur d'arrivée identique au départ", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    renderWithProviders(
      <TransferModal open lockedArticle={article} initialFrom={1} onClose={() => {}} onSaved={onSaved} />,
    );
    await chooseDestination(user, "Local du club");
    await user.type(screen.getByRole("spinbutton", { name: /Quantité/ }), "2");
    await user.click(screen.getByRole("button", { name: "Déplacer" }));
    expect(
      await screen.findByText("Le détenteur d'arrivée doit être différent du détenteur de départ."),
    ).toBeInTheDocument();
    expect(createTransfer).not.toHaveBeenCalled();
  });

  it("depuis « Non localisé » : from_holder_id null, toast avec la destination", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    renderWithProviders(
      <TransferModal open lockedArticle={article} initialFrom={null} onClose={() => {}} onSaved={onSaved} />,
    );
    expect(screen.getByRole("radio", { name: /Non localisé/ })).toHaveAttribute("aria-checked", "true");
    await chooseDestination(user, "Éric Mbala");
    await user.type(screen.getByRole("spinbutton", { name: /Quantité/ }), "3");
    await user.click(screen.getByRole("button", { name: "Déplacer" }));
    await waitFor(() => expect(createTransfer).toHaveBeenCalled());
    expect(vi.mocked(createTransfer).mock.calls[0]![0]).toMatchObject({
      article_id: 10,
      from_holder_id: null,
      to_holder_id: 2,
      quantity: 3,
    });
    expect(onSaved).toHaveBeenCalledWith("Matériel déplacé : 3 pièces de Maillot domicile chez Éric Mbala.");
  });

  // Remplace l'ancien test « la quantité est bornée au stock de la source »,
  // qui figeait un plafonnement SILENCIEUX : saisir 99 déplaçait en réalité
  // tout le stock de la source, sans aucun message (constaté en e2e,
  // `e2e/12-intendance.spec.ts`). La spec §4.3 demande le message
  // « Quantité supérieure au stock de {détenteur} ({n}). » : la saisie est
  // conservée telle quelle et rien n'est envoyé.
  it("never silently caps the quantity: shows the source stock error and sends nothing", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <TransferModal open lockedArticle={article} initialFrom={null} onClose={() => {}} onSaved={() => {}} />,
    );
    await chooseDestination(user, "Éric Mbala");
    const input = screen.getByRole("spinbutton", { name: /Quantité/ });
    await user.type(input, "9");
    expect(input).toHaveValue(9);
    expect(screen.getByText("Stock de la source : 4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Déplacer" }));
    expect(await screen.findByText("Quantité supérieure au stock de Non localisé (4).")).toBeInTheDocument();
    expect(createTransfer).not.toHaveBeenCalled();
  });

  it("route l'erreur de quantité de l'API sous le champ Quantité", async () => {
    vi.mocked(createTransfer).mockRejectedValue(
      new ApiError(400, { detail: "Quantité supérieure au stock de Local du club (8)." }),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <TransferModal open lockedArticle={article} initialFrom={1} onClose={() => {}} onSaved={() => {}} />,
    );
    await chooseDestination(user, "Éric Mbala");
    await user.type(screen.getByRole("spinbutton", { name: /Quantité/ }), "2");
    await user.click(screen.getByRole("button", { name: "Déplacer" }));
    const message = await screen.findByText("Quantité supérieure au stock de Local du club (8).");
    expect(message.previousElementSibling).not.toBeNull();
  });
});
