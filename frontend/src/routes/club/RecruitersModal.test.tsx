import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import type { MembershipRole } from "../../api/clubs";
import { RecruitersModal } from "./RecruitersModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return {
    ...actual,
    appointRole: vi.fn(),
    revokeRole: vi.fn(),
    searchActiveClubPlayers: vi.fn(),
  };
});

import { appointRole, revokeRole, searchActiveClubPlayers } from "../../api/clubs";

function recruiterRole(id: number, membershipId: number): MembershipRole {
  return {
    id,
    membership_id: membershipId,
    role: "player_recruiter",
    role_label: "Joueur autorise a ajouter des joueurs",
    effective_label: "Joueur autorise a ajouter des joueurs",
    is_qualified_professional: null,
    appointed_by_id: 1,
    appointed_at: "2026-01-01T00:00:00Z",
    revoked_by_id: null,
    revoked_at: null,
    revoked_reason: "",
  };
}

describe("RecruitersModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche les recruteurs actuels comme puces déjà sélectionnées", () => {
    render(
      <ToastProvider>
        <RecruitersModal
          recruiters={[
            { role: recruiterRole(1, 10), player: { id: 10, firstName: "Amos", lastName: "Kanku" } },
          ]}
          onClose={vi.fn()}
          onChanged={vi.fn()}
        />
      </ToastProvider>,
    );
    expect(screen.getByText("Amos Kanku")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retirer Amos Kanku" })).toBeInTheDocument();
  });

  it("ajoute un nouveau recruteur et retire celui décoché, en un seul Enregistrer", async () => {
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 20, firstName: "Jean", lastName: "Kabila" },
    ]);
    vi.mocked(appointRole).mockResolvedValue(recruiterRole(2, 20));
    vi.mocked(revokeRole).mockResolvedValue({ ...recruiterRole(1, 10), revoked_at: "2026-01-02T00:00:00Z" });

    const user = userEvent.setup();
    const onChanged = vi.fn();
    render(
      <ToastProvider>
        <RecruitersModal
          recruiters={[
            { role: recruiterRole(1, 10), player: { id: 10, firstName: "Amos", lastName: "Kanku" } },
          ]}
          onClose={vi.fn()}
          onChanged={onChanged}
        />
      </ToastProvider>,
    );

    // Retire le recruteur existant.
    await user.click(screen.getByRole("button", { name: "Retirer Amos Kanku" }));

    // Ajoute un nouveau recruteur.
    await user.type(screen.getByRole("combobox"), "Jean");
    const option = await screen.findByRole("option", { name: /Jean Kabila/ });
    await user.click(option);

    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() => {
      expect(appointRole).toHaveBeenCalledWith({ membership_id: 20, role: "player_recruiter" });
      expect(revokeRole).toHaveBeenCalledWith({ role_id: 1 });
      expect(onChanged).toHaveBeenCalled();
    });
  });
});
