import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import type { MembershipRole } from "../../api/clubs";
import { RoleModal } from "./RoleModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return {
    ...actual,
    appointRole: vi.fn(),
    revokeRole: vi.fn(),
    appointCaptain: vi.fn(),
    revokeCaptain: vi.fn(),
    searchActiveClubPlayers: vi.fn(),
  };
});

import {
  appointCaptain,
  appointRole,
  revokeCaptain,
  revokeRole,
  searchActiveClubPlayers,
} from "../../api/clubs";

const TREASURER_ROLE: MembershipRole = {
  id: 7,
  membership_id: 3,
  role: "treasurer",
  role_label: "Tresorier",
  effective_label: "Tresorier",
  is_qualified_professional: null,
  appointed_by_id: 1,
  appointed_at: "2026-01-01T00:00:00Z",
  revoked_by_id: null,
  revoked_at: null,
  revoked_reason: "",
};

const CAPTAIN_ROLE: MembershipRole = {
  id: 8,
  membership_id: 4,
  role: "captain",
  role_label: "Capitaine",
  effective_label: "Capitaine",
  is_qualified_professional: null,
  appointed_by_id: 1,
  appointed_at: "2026-01-01T00:00:00Z",
  revoked_by_id: null,
  revoked_at: null,
  revoked_reason: "",
};

const DOCTOR_ROLE: MembershipRole = {
  id: 9,
  membership_id: 6,
  role: "doctor",
  role_label: "Medecin",
  effective_label: "Medecin",
  is_qualified_professional: true,
  appointed_by_id: 1,
  appointed_at: "2026-01-01T00:00:00Z",
  revoked_by_id: null,
  revoked_at: null,
  revoked_reason: "",
};

function renderModal(props: Partial<Parameters<typeof RoleModal>[0]> = {}) {
  const onClose = vi.fn();
  const onChanged = vi.fn();
  render(
    <ToastProvider>
      <RoleModal
        roleKey="treasurer"
        roleLabel="Trésorier"
        role={null}
        holderName={null}
        canManage
        onClose={onClose}
        onChanged={onChanged}
        {...props}
      />
    </ToastProvider>,
  );
  return { onClose, onChanged };
}

describe("RoleModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("poste vacant : propose un PlayerSearch borné aux joueurs inscrits, puis nomme", async () => {
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 5, firstName: "Amos", lastName: "Kanku" },
    ]);
    vi.mocked(appointRole).mockResolvedValue({ ...TREASURER_ROLE, membership_id: 5 });
    const user = userEvent.setup();
    const { onChanged } = renderModal();

    expect(screen.getByText("Poste vacant.")).toBeInTheDocument();
    expect(screen.getByText("Un joueur peut cumuler plusieurs rôles.")).toBeInTheDocument();

    await user.type(screen.getByRole("combobox"), "Amos");
    const option = await screen.findByRole("option", { name: /Amos Kanku/ });
    await user.click(option);

    await user.click(screen.getByRole("button", { name: "Nommer" }));

    await waitFor(() => {
      expect(appointRole).toHaveBeenCalledWith({ membership_id: 5, role: "treasurer" });
      expect(onChanged).toHaveBeenCalled();
    });
  });

  it("poste occupé : « Remplacer » révèle le PlayerSearch avec l'aide dédiée", async () => {
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([]);
    const user = userEvent.setup();
    renderModal({ role: TREASURER_ROLE, holderName: "Jean Kabila" });

    expect(screen.getByText(/Titulaire actuel/)).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remplacer" }));

    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(screen.getByText("Jean Kabila sera révoqué de ce rôle.")).toBeInTheDocument();
  });

  it("poste occupé, après clic sur « Remplacer » : le pied bascule de Fermer/Remplacer vers Annuler/Nommer", async () => {
    // Verrouille le comportement REELLEMENT codé (RoleModal.tsx : une fois
    // `replacing` a `true`, la condition `canManage && role && !replacing`
    // du `footer` personnalise devient fausse -> le pied personnalise
    // disparait et la Modal retombe sur son pied par defaut, Annuler /
    // Nommer). Ne tranche pas si c'est la bonne spec (lecture interpretative
    // non arbitree, cf. compte rendu) : constate seulement ce qui est livre.
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([]);
    const user = userEvent.setup();
    renderModal({ role: TREASURER_ROLE, holderName: "Jean Kabila" });

    expect(screen.getByRole("button", { name: "Remplacer" })).toBeInTheDocument();
    // Deux elements distincts partagent l'intitule accessible « Fermer » a
    // ce stade : la croix d'en-tete (icone) et le bouton secondaire du pied.
    expect(screen.getAllByRole("button", { name: "Fermer" })).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Remplacer" }));

    expect(screen.queryByRole("button", { name: "Remplacer" })).not.toBeInTheDocument();
    // Il ne reste plus que la croix d'en-tete : le bouton « Fermer » du pied
    // a disparu au profit du pied par defaut de la Modal.
    expect(screen.getAllByRole("button", { name: "Fermer" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Annuler" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nommer" })).toBeInTheDocument();
  });

  it("révoque le titulaire actuel après confirmation", async () => {
    vi.mocked(revokeRole).mockResolvedValue({ ...TREASURER_ROLE, revoked_at: "2026-01-02T00:00:00Z" });
    const user = userEvent.setup();
    const { onChanged } = renderModal({ role: TREASURER_ROLE, holderName: "Jean Kabila" });

    await user.click(screen.getByRole("button", { name: "Révoquer Jean Kabila" }));
    await user.click(screen.getByRole("button", { name: "Révoquer" }));

    await waitFor(() => {
      expect(revokeRole).toHaveBeenCalledWith({ role_id: TREASURER_ROLE.id });
      expect(onChanged).toHaveBeenCalled();
    });
  });

  it("lecture seule pour un joueur sans droit de gestion", () => {
    renderModal({ canManage: false, role: TREASURER_ROLE, holderName: "Jean Kabila" });
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Révoquer/ })).not.toBeInTheDocument();
  });

  describe("rôle Médecin : choix qualifié / non qualifié (B1)", () => {
    it("affiche le fieldset qualifié/non qualifié uniquement pour le rôle Médecin en recherche active", () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([]);
      renderModal({ roleKey: "doctor", roleLabel: "Médecin" });

      expect(screen.getByText("Statut du médecin")).toBeInTheDocument();
      expect(screen.getByText("Professionnel de santé qualifié")).toBeInTheDocument();
      expect(
        screen.getByText("Non qualifié (affiché comme « Médecin / référent santé »)"),
      ).toBeInTheDocument();
    });

    it("n'affiche pas le fieldset qualifié/non qualifié pour un rôle non-Médecin", () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([]);
      renderModal();

      expect(screen.queryByText("Statut du médecin")).not.toBeInTheDocument();
      expect(screen.queryByText("Professionnel de santé qualifié")).not.toBeInTheDocument();
    });

    it("n'affiche pas le fieldset pour le poste Médecin déjà occupé tant que « Remplacer » n'est pas cliqué", () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([]);
      renderModal({ roleKey: "doctor", roleLabel: "Médecin", role: DOCTOR_ROLE, holderName: "Dr Kabila" });

      // showSearch est faux (poste occupé, pas encore en remplacement) : ni
      // PlayerSearch, ni fieldset qualifié/non qualifié ne doivent apparaître.
      expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
      expect(screen.queryByText("Statut du médecin")).not.toBeInTheDocument();
    });

    it("le bouton Nommer reste désactivé tant qu'aucun statut n'est choisi, même avec un joueur sélectionné", async () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([
        { id: 12, firstName: "Alice", lastName: "Tshimanga" },
      ]);
      const user = userEvent.setup();
      renderModal({ roleKey: "doctor", roleLabel: "Médecin" });

      await user.type(screen.getByRole("combobox"), "Alice");
      const option = await screen.findByRole("option", { name: /Alice Tshimanga/ });
      await user.click(option);

      expect(screen.getByRole("button", { name: "Nommer" })).toBeDisabled();

      await user.click(screen.getByRole("radio", { name: "Professionnel de santé qualifié" }));

      expect(screen.getByRole("button", { name: "Nommer" })).toBeEnabled();
      expect(appointRole).not.toHaveBeenCalled();
    });

    it("nomme avec is_qualified_professional: true quand « Professionnel de santé qualifié » est choisi", async () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([
        { id: 12, firstName: "Alice", lastName: "Tshimanga" },
      ]);
      vi.mocked(appointRole).mockResolvedValue({ ...DOCTOR_ROLE, membership_id: 12 });
      const user = userEvent.setup();
      const { onChanged } = renderModal({ roleKey: "doctor", roleLabel: "Médecin" });

      await user.type(screen.getByRole("combobox"), "Alice");
      await user.click(await screen.findByRole("option", { name: /Alice Tshimanga/ }));
      await user.click(screen.getByRole("radio", { name: "Professionnel de santé qualifié" }));

      await user.click(screen.getByRole("button", { name: "Nommer" }));

      await waitFor(() => {
        expect(appointRole).toHaveBeenCalledWith({
          membership_id: 12,
          role: "doctor",
          is_qualified_professional: true,
        });
        expect(onChanged).toHaveBeenCalled();
      });
    });

    it("nomme avec is_qualified_professional: false quand « Non qualifié » est choisi", async () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([
        { id: 13, firstName: "Bob", lastName: "Ilunga" },
      ]);
      vi.mocked(appointRole).mockResolvedValue({ ...DOCTOR_ROLE, membership_id: 13, is_qualified_professional: false });
      const user = userEvent.setup();
      const { onChanged } = renderModal({ roleKey: "doctor", roleLabel: "Médecin" });

      await user.type(screen.getByRole("combobox"), "Bob");
      await user.click(await screen.findByRole("option", { name: /Bob Ilunga/ }));
      await user.click(
        screen.getByRole("radio", { name: "Non qualifié (affiché comme « Médecin / référent santé »)" }),
      );

      await user.click(screen.getByRole("button", { name: "Nommer" }));

      await waitFor(() => {
        expect(appointRole).toHaveBeenCalledWith({
          membership_id: 13,
          role: "doctor",
          is_qualified_professional: false,
        });
        expect(onChanged).toHaveBeenCalled();
      });
    });

    it("n'envoie jamais is_qualified_professional pour un rôle non-Médecin (Trésorier)", async () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([
        { id: 5, firstName: "Amos", lastName: "Kanku" },
      ]);
      vi.mocked(appointRole).mockResolvedValue({ ...TREASURER_ROLE, membership_id: 5 });
      const user = userEvent.setup();
      renderModal();

      await user.type(screen.getByRole("combobox"), "Amos");
      await user.click(await screen.findByRole("option", { name: /Amos Kanku/ }));
      await user.click(screen.getByRole("button", { name: "Nommer" }));

      await waitFor(() => {
        expect(appointRole).toHaveBeenCalledTimes(1);
      });
      const call = vi.mocked(appointRole).mock.calls[0];
      expect(call).toBeDefined();
      const callArgs = call![0];
      expect(callArgs).toEqual({ membership_id: 5, role: "treasurer" });
      expect(callArgs).not.toHaveProperty("is_qualified_professional");
    });

    it("n'envoie jamais is_qualified_professional pour le rôle Capitaine (appointCaptain)", async () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([
        { id: 14, firstName: "Paul", lastName: "Mbala" },
      ]);
      vi.mocked(appointCaptain).mockResolvedValue({ ...CAPTAIN_ROLE, membership_id: 14 });
      const user = userEvent.setup();
      renderModal({ roleKey: "captain", roleLabel: "Capitaine" });

      await user.type(screen.getByRole("combobox"), "Paul");
      await user.click(await screen.findByRole("option", { name: /Paul Mbala/ }));
      await user.click(screen.getByRole("button", { name: "Nommer" }));

      await waitFor(() => {
        expect(appointCaptain).toHaveBeenCalledWith({ membership_id: 14 });
      });
      const call = vi.mocked(appointCaptain).mock.calls[0];
      expect(call).toBeDefined();
      const callArgs = call![0];
      expect(callArgs).not.toHaveProperty("is_qualified_professional");
    });
  });

  describe("remplacement : révocation avant nomination (B2)", () => {
    it("révoque le titulaire actuel avant de nommer le nouveau (Trésorier)", async () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([
        { id: 20, firstName: "Jean", lastName: "Kabila" },
      ]);
      vi.mocked(revokeRole).mockResolvedValue({ ...TREASURER_ROLE, revoked_at: "2026-01-02T00:00:00Z" });
      vi.mocked(appointRole).mockResolvedValue({ ...TREASURER_ROLE, id: 21, membership_id: 20 });
      const user = userEvent.setup();
      const { onChanged } = renderModal({ role: TREASURER_ROLE, holderName: "Amos Kanku" });

      await user.click(screen.getByRole("button", { name: "Remplacer" }));
      await user.type(screen.getByRole("combobox"), "Jean");
      await user.click(await screen.findByRole("option", { name: /Jean Kabila/ }));
      await user.click(screen.getByRole("button", { name: "Nommer" }));

      await waitFor(() => {
        expect(revokeRole).toHaveBeenCalledWith({ role_id: TREASURER_ROLE.id });
        expect(appointRole).toHaveBeenCalledWith({ membership_id: 20, role: "treasurer" });
        expect(onChanged).toHaveBeenCalled();
      });
      const revokeOrder = vi.mocked(revokeRole).mock.invocationCallOrder[0];
      const appointOrder = vi.mocked(appointRole).mock.invocationCallOrder[0];
      expect(revokeOrder).toBeDefined();
      expect(appointOrder).toBeDefined();
      expect(revokeOrder!).toBeLessThan(appointOrder!);
    });

    it("révoque le titulaire actuel avant de nommer le nouveau (Capitaine)", async () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([
        { id: 30, firstName: "Marc", lastName: "Ilunga" },
      ]);
      vi.mocked(revokeCaptain).mockResolvedValue({ ...CAPTAIN_ROLE, revoked_at: "2026-01-02T00:00:00Z" });
      vi.mocked(appointCaptain).mockResolvedValue({ ...CAPTAIN_ROLE, id: 31, membership_id: 30 });
      const user = userEvent.setup();
      const { onChanged } = renderModal({
        roleKey: "captain",
        roleLabel: "Capitaine",
        role: CAPTAIN_ROLE,
        holderName: "Amos Kanku",
      });

      await user.click(screen.getByRole("button", { name: "Remplacer" }));
      await user.type(screen.getByRole("combobox"), "Marc");
      await user.click(await screen.findByRole("option", { name: /Marc Ilunga/ }));
      await user.click(screen.getByRole("button", { name: "Nommer" }));

      await waitFor(() => {
        expect(revokeCaptain).toHaveBeenCalledWith({ role_id: CAPTAIN_ROLE.id });
        expect(appointCaptain).toHaveBeenCalledWith({ membership_id: 30 });
        expect(onChanged).toHaveBeenCalled();
      });
      const revokeOrder = vi.mocked(revokeCaptain).mock.invocationCallOrder[0];
      const appointOrder = vi.mocked(appointCaptain).mock.invocationCallOrder[0];
      expect(revokeOrder).toBeDefined();
      expect(appointOrder).toBeDefined();
      expect(revokeOrder!).toBeLessThan(appointOrder!);
    });

    it("n'appelle jamais appointRole si la révocation préalable échoue, et affiche l'erreur standard", async () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([
        { id: 20, firstName: "Jean", lastName: "Kabila" },
      ]);
      vi.mocked(revokeRole).mockRejectedValue(new Error("network down"));
      const user = userEvent.setup();
      const { onChanged } = renderModal({ role: TREASURER_ROLE, holderName: "Amos Kanku" });

      await user.click(screen.getByRole("button", { name: "Remplacer" }));
      await user.type(screen.getByRole("combobox"), "Jean");
      await user.click(await screen.findByRole("option", { name: /Jean Kabila/ }));
      await user.click(screen.getByRole("button", { name: "Nommer" }));

      expect(
        await screen.findByText("Une erreur est survenue de notre côté. Réessayez dans un instant."),
      ).toBeInTheDocument();
      expect(appointRole).not.toHaveBeenCalled();
      expect(onChanged).not.toHaveBeenCalled();
    });

    it("n'appelle jamais appointCaptain si la révocation préalable échoue (Capitaine)", async () => {
      vi.mocked(searchActiveClubPlayers).mockResolvedValue([
        { id: 30, firstName: "Marc", lastName: "Ilunga" },
      ]);
      vi.mocked(revokeCaptain).mockRejectedValue(new Error("network down"));
      const user = userEvent.setup();
      renderModal({
        roleKey: "captain",
        roleLabel: "Capitaine",
        role: CAPTAIN_ROLE,
        holderName: "Amos Kanku",
      });

      await user.click(screen.getByRole("button", { name: "Remplacer" }));
      await user.type(screen.getByRole("combobox"), "Marc");
      await user.click(await screen.findByRole("option", { name: /Marc Ilunga/ }));
      await user.click(screen.getByRole("button", { name: "Nommer" }));

      expect(
        await screen.findByText("Une erreur est survenue de notre côté. Réessayez dans un instant."),
      ).toBeInTheDocument();
      expect(appointCaptain).not.toHaveBeenCalled();
    });
  });
});
