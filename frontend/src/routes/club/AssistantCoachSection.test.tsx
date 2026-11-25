import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import type { MembershipRole } from "../../api/clubs";
import { ApiError } from "../../api/client";
import { AssistantCoachSection } from "./AssistantCoachSection";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return {
    ...actual,
    appointAssistantCoach: vi.fn(),
    revokeAssistantCoach: vi.fn(),
    searchActiveClubPlayers: vi.fn(),
  };
});

import { appointAssistantCoach, revokeAssistantCoach, searchActiveClubPlayers } from "../../api/clubs";

const ASSISTANT: MembershipRole = {
  id: 12,
  membership_id: 4,
  role: "assistant_coach",
  role_label: "Assistant du Coach",
  effective_label: "Assistant du Coach",
  is_qualified_professional: null,
  appointed_by_id: 1,
  appointed_at: "2026-11-01T00:00:00Z",
  revoked_by_id: null,
  revoked_at: null,
  revoked_reason: "",
};

function renderSection(props: Partial<Parameters<typeof AssistantCoachSection>[0]> = {}) {
  const onChanged = vi.fn();
  render(
    <ToastProvider>
      <AssistantCoachSection
        assistant={undefined}
        assistantName={null}
        loading={false}
        canManage
        onChanged={onChanged}
        {...props}
      />
    </ToastProvider>,
  );
  return { onChanged };
}

async function pickPlayer(user: ReturnType<typeof userEvent.setup>) {
  vi.mocked(searchActiveClubPlayers).mockResolvedValue([{ id: 5, firstName: "Amos", lastName: "Kanku" }]);
  await user.type(screen.getByRole("combobox"), "Amos");
  await user.click(await screen.findByRole("option", { name: /Amos Kanku/ }));
}

describe("AssistantCoachSection", () => {
  afterEach(() => vi.clearAllMocks());

  it("sans assistant : état vide et bouton de nomination pour le Coach", () => {
    renderSection();
    expect(screen.getByText("Aucun assistant nommé")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nommer l'assistant" })).toBeInTheDocument();
  });

  it("l'assistant (ou tout non-Coach) voit le titulaire mais aucun bouton de gestion", () => {
    renderSection({ assistant: ASSISTANT, assistantName: "Jean Kabila", canManage: false });
    expect(screen.getByText("Jean Kabila")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Nommer|Changer|Retirer/ })).not.toBeInTheDocument();
  });

  it("nomme après confirmation : rien n'est envoyé avant la confirmation", async () => {
    vi.mocked(appointAssistantCoach).mockResolvedValue({ ...ASSISTANT, membership_id: 5 });
    const user = userEvent.setup();
    const { onChanged } = renderSection();

    await user.click(screen.getByRole("button", { name: "Nommer l'assistant" }));
    await pickPlayer(user);
    await user.click(screen.getByRole("button", { name: "Continuer" }));

    expect(await screen.findByText("Nommer Amos Kanku assistant du Coach ?")).toBeInTheDocument();
    expect(appointAssistantCoach).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Nommer" }));
    await waitFor(() => {
      expect(appointAssistantCoach).toHaveBeenCalledWith({ membership_id: 5 });
      expect(onChanged).toHaveBeenCalled();
    });
  });

  it("remplace : la confirmation mentionne le remplacement", async () => {
    const user = userEvent.setup();
    renderSection({ assistant: ASSISTANT, assistantName: "Jean Kabila" });

    await user.click(screen.getByRole("button", { name: "Changer l'assistant" }));
    expect(screen.getByText("Jean Kabila sera remplacé.")).toBeInTheDocument();
    await pickPlayer(user);
    await user.click(screen.getByRole("button", { name: "Continuer" }));
    expect(await screen.findByText(/remplacera l'assistant actuel/)).toBeInTheDocument();
  });

  it("retire après confirmation", async () => {
    vi.mocked(revokeAssistantCoach).mockResolvedValue({ ...ASSISTANT, revoked_at: "2026-11-13T00:00:00Z" });
    const user = userEvent.setup();
    const { onChanged } = renderSection({ assistant: ASSISTANT, assistantName: "Jean Kabila" });

    await user.click(screen.getByRole("button", { name: "Retirer l'assistant" }));
    expect(revokeAssistantCoach).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Retirer" }));
    await waitFor(() => {
      expect(revokeAssistantCoach).toHaveBeenCalledWith({ role_id: 12 });
      expect(onChanged).toHaveBeenCalled();
    });
  });

  it("affiche le refus 403 de l'API en français", async () => {
    vi.mocked(appointAssistantCoach).mockRejectedValue(
      new ApiError(403, { detail: "Réservé au Coach du club." }),
    );
    const user = userEvent.setup();
    const { onChanged } = renderSection();

    await user.click(screen.getByRole("button", { name: "Nommer l'assistant" }));
    await pickPlayer(user);
    await user.click(screen.getByRole("button", { name: "Continuer" }));
    await user.click(await screen.findByRole("button", { name: "Nommer" }));

    expect(await screen.findByText("Réservé au Coach du club.")).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("affiche l'erreur 400 au retrait", async () => {
    vi.mocked(revokeAssistantCoach).mockRejectedValue(new ApiError(400, { detail: "Ce rôle est déjà retiré." }));
    const user = userEvent.setup();
    renderSection({ assistant: ASSISTANT, assistantName: "Jean Kabila" });

    await user.click(screen.getByRole("button", { name: "Retirer l'assistant" }));
    await user.click(screen.getByRole("button", { name: "Retirer" }));
    expect(await screen.findByText("Ce rôle est déjà retiré.")).toBeInTheDocument();
  });
});
