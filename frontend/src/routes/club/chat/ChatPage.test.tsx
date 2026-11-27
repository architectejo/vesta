import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatChannel, ChatMessage } from "../../../api/social";
import { ChatPage } from "./ChatPage";

vi.mock("../../../api/social", async () => {
  const actual = await vi.importActual<typeof import("../../../api/social")>("../../../api/social");
  return { ...actual, listChatChannels: vi.fn() };
});

import { listChatChannels } from "../../../api/social";

function lastMessage(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: 1,
    channel_id: 1,
    sender: { id: 2, first_name: "Jean", last_name: "Kabila", avatar_url: null },
    body: "Entraînement samedi",
    image_url: null,
    sent_at: new Date().toISOString(),
    members_in_order_only: false,
    ...overrides,
  };
}

function channel(overrides: Partial<ChatChannel>): ChatChannel {
  return {
    id: 1,
    channel_type: "general",
    unread_count: 0,
    last_message: null,
    can_restrict_to_members_in_order: false,
    has_hidden_reserved_messages: false,
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ChatPage — aperçu d'un message réservé (C7.3)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("précède l'aperçu d'un message réservé d'un texte accessible « Réservé aux membres en ordre : »", async () => {
    vi.mocked(listChatChannels).mockResolvedValue({
      results: [channel({ last_message: lastMessage({ members_in_order_only: true }) })],
    });
    renderPage();

    const preview = await screen.findByText(/Jean : Entraînement samedi/);
    expect(preview).toHaveTextContent("Réservé aux membres en ordre : Jean : Entraînement samedi");
  });

  it("n'ajoute rien à l'aperçu d'un message ordinaire et n'affiche jamais le bandeau dans la liste", async () => {
    vi.mocked(listChatChannels).mockResolvedValue({
      results: [channel({ last_message: lastMessage({}), has_hidden_reserved_messages: true })],
    });
    renderPage();

    const preview = await screen.findByText(/Jean : Entraînement samedi/);
    expect(preview).toHaveTextContent(/^Jean : Entraînement samedi$/);
    expect(screen.queryByText("Certains messages sont réservés aux membres en ordre de cotisation.")).not.toBeInTheDocument();
  });
});
