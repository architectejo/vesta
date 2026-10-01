import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import { PresidencyHandoverModal } from "./PresidencyHandoverModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return {
    ...actual,
    handoverPresidency: vi.fn(),
    searchActiveClubPlayers: vi.fn(),
  };
});

import { handoverPresidency, searchActiveClubPlayers } from "../../api/clubs";

describe("PresidencyHandoverModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("exige une confirmation avant de transmettre, puis appelle l'API", async () => {
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 9, firstName: "Amos", lastName: "Kanku" },
    ]);
    vi.mocked(handoverPresidency).mockResolvedValue({ id: 1 });
    const user = userEvent.setup();
    const onTransferred = vi.fn();

    render(
      <ToastProvider>
        <PresidencyHandoverModal onClose={vi.fn()} onTransferred={onTransferred} />
      </ToastProvider>,
    );

    await user.type(screen.getByRole("combobox"), "Amos");
    const option = await screen.findByRole("option", { name: /Amos Kanku/ });
    await user.click(option);

    await user.click(screen.getByRole("button", { name: "Transmettre" }));
    // La ConfirmDialog s'ouvre : le bouton « Transmettre » y apparaît une
    // seconde fois, aucun appel API ne doit encore avoir eu lieu.
    expect(handoverPresidency).not.toHaveBeenCalled();
    const confirmButtons = screen.getAllByRole("button", { name: "Transmettre" });
    const lastConfirmButton = confirmButtons[confirmButtons.length - 1];
    if (!lastConfirmButton) throw new Error("Bouton de confirmation introuvable.");
    await user.click(lastConfirmButton);

    await waitFor(() => {
      expect(handoverPresidency).toHaveBeenCalledWith({ to_membership_id: 9 });
      expect(onTransferred).toHaveBeenCalled();
    });
  });
});
