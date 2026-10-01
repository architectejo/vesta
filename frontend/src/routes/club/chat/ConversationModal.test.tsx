import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatChannel } from "../../../api/social";
import { ConversationModal } from "./ConversationModal";

vi.mock("../../../api/social", async () => {
  const actual = await vi.importActual<typeof import("../../../api/social")>("../../../api/social");
  return {
    ...actual,
    listChatMessages: vi.fn(),
    sendChatMessage: vi.fn(),
    markChannelRead: vi.fn(),
  };
});

vi.mock("../../../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1 }, club: null, status: "authenticated" }),
}));

import { listChatMessages, markChannelRead, sendChatMessage } from "../../../api/social";

const CHANNEL: ChatChannel = { id: 1, channel_type: "general", unread_count: 0, last_message: null };

function renderModal() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ConversationModal channel={CHANNEL} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("ConversationModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche le titre « Général » et l'état vide sans message", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({ results: [], count: 0, next_offset: null });
    vi.mocked(markChannelRead).mockResolvedValue({ detail: "ok" });
    renderModal();

    expect(screen.getByRole("heading", { name: "Général" })).toBeInTheDocument();
    expect(await screen.findByText("Aucun message pour l'instant. Lancez la conversation.")).toBeInTheDocument();
  });

  it("distingue mes messages (à droite, sans nom) de ceux des autres (à gauche, avec nom)", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({
      results: [
        {
          id: 1,
          channel_id: 1,
          sender: { id: 1, first_name: "Moi", last_name: "Même", avatar_url: null },
          body: "Salut !",
          image_url: null,
          sent_at: new Date().toISOString(),
        },
        {
          id: 2,
          channel_id: 1,
          sender: { id: 2, first_name: "Jean", last_name: "Kabila", avatar_url: null },
          body: "Bonjour",
          image_url: null,
          sent_at: new Date().toISOString(),
        },
      ],
      count: 2,
      next_offset: null,
    });
    vi.mocked(markChannelRead).mockResolvedValue({ detail: "ok" });
    renderModal();

    expect(await screen.findByText("Salut !")).toBeInTheDocument();
    expect(screen.getByText("Bonjour")).toBeInTheDocument();
    expect(screen.getByText("Jean Kabila")).toBeInTheDocument();
    expect(screen.queryByText("Moi Même")).not.toBeInTheDocument();
    expect(screen.getByText("Aujourd'hui")).toBeInTheDocument();
  });

  it("envoie un message et vide le champ", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({ results: [], count: 0, next_offset: null });
    vi.mocked(sendChatMessage).mockResolvedValue({
      id: 3,
      channel_id: 1,
      sender: { id: 1, first_name: "Moi", last_name: "Même", avatar_url: null },
      body: "Nouveau message",
      image_url: null,
      sent_at: new Date().toISOString(),
    });

    const user = userEvent.setup();
    renderModal();

    const textarea = await screen.findByLabelText("Écrire un message…");
    await user.type(textarea, "Nouveau message");
    await user.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(sendChatMessage).toHaveBeenCalledWith(1, { body: "Nouveau message", image: null }));
    await waitFor(() => expect(textarea).toHaveValue(""));
  });

  it("marque le canal comme lu avec le dernier message reçu", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({
      results: [
        {
          id: 9,
          channel_id: 1,
          sender: { id: 2, first_name: "Jean", last_name: "Kabila", avatar_url: null },
          body: "Dernier message",
          image_url: null,
          sent_at: new Date().toISOString(),
        },
      ],
      count: 1,
      next_offset: null,
    });
    vi.mocked(markChannelRead).mockResolvedValue({ detail: "ok" });
    renderModal();

    await waitFor(() => expect(markChannelRead).toHaveBeenCalledWith(1, 9));
  });
});
