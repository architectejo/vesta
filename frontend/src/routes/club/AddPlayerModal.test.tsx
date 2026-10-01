import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import { AddPlayerModal } from "./AddPlayerModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return {
    ...actual,
    addPlayerWithSponsor: vi.fn(),
    searchActiveClubPlayers: vi.fn(),
  };
});

import { addPlayerWithSponsor, searchActiveClubPlayers } from "../../api/clubs";
import { ApiError } from "../../api/client";

function renderModal(onAdded = vi.fn()) {
  render(
    <ToastProvider>
      <AddPlayerModal onClose={vi.fn()} onAdded={onAdded} />
    </ToastProvider>,
  );
  return { onAdded };
}

describe("AddPlayerModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("exige un parrain choisi via PlayerSearch (jamais de <select>) avant l'envoi", async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByLabelText("Prénom"), "Paul");
    await user.type(screen.getByLabelText("Nom"), "Tshimanga");
    await user.type(screen.getByLabelText("Email"), "paul@example.test");
    await user.click(screen.getByRole("button", { name: "Milieu" }));

    await user.click(screen.getByRole("button", { name: "Ajouter le joueur" }));

    expect(await screen.findByText("Choisissez un parrain.")).toBeInTheDocument();
    expect(addPlayerWithSponsor).not.toHaveBeenCalled();
  });

  it("envoie sponsor_membership_id du joueur choisi dans le champ Parrain (joueurs inscrits)", async () => {
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 11, firstName: "Amos", lastName: "Kanku" },
    ]);
    vi.mocked(addPlayerWithSponsor).mockResolvedValue({
      membership_id: 99,
      application: {
        id: 1,
        membership_id: 99,
        application_pdf_file: null,
        generated_at: null,
        sponsor_notified_at: null,
        sponsor_decision: "pending",
        sponsor_signed_by_id: null,
        sponsor_signed_at: null,
        sponsor_refused_reason: "",
        sponsor_reminder_sent_at: null,
        president_alerted_at: null,
        resolved_at: null,
        cancelled_by_id: null,
        cancelled_reason: "",
        membership_fee_payment_id: null,
        membership_fee_disposition: "",
      },
    });
    const user = userEvent.setup();
    const { onAdded } = renderModal();

    await user.type(screen.getByLabelText("Prénom"), "Paul");
    await user.type(screen.getByLabelText("Nom"), "Tshimanga");
    await user.type(screen.getByLabelText("Email"), "paul@example.test");
    await user.click(screen.getByRole("button", { name: "Milieu" }));

    await user.type(screen.getByRole("combobox"), "Amos");
    const option = await screen.findByRole("option", { name: /Amos Kanku/ });
    await user.click(option);

    await user.click(screen.getByRole("button", { name: "Ajouter le joueur" }));

    await waitFor(() => {
      expect(addPlayerWithSponsor).toHaveBeenCalledWith(
        expect.objectContaining({ sponsor_membership_id: 11, email: "paul@example.test" }),
      );
      expect(onAdded).toHaveBeenCalled();
    });
  });

  it("affiche l'erreur API « déjà utilisée » sur le champ email", async () => {
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 11, firstName: "Amos", lastName: "Kanku" },
    ]);
    vi.mocked(addPlayerWithSponsor).mockRejectedValue(
      new ApiError(400, { email: ["Cette adresse email est déjà utilisée."] }),
    );
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByLabelText("Prénom"), "Paul");
    await user.type(screen.getByLabelText("Nom"), "Tshimanga");
    await user.type(screen.getByLabelText("Email"), "paul@example.test");
    await user.click(screen.getByRole("button", { name: "Milieu" }));
    await user.type(screen.getByRole("combobox"), "Amos");
    await user.click(await screen.findByRole("option", { name: /Amos Kanku/ }));

    await user.click(screen.getByRole("button", { name: "Ajouter le joueur" }));

    const messages = await screen.findAllByText("Cette adresse email est déjà utilisée.");
    expect(messages.length).toBeGreaterThan(0);
  });
});
