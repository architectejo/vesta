import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client";
import type { ChatChannel, ChatMessage } from "../../../api/social";
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

const CHANNEL: ChatChannel = {
  id: 1,
  channel_type: "general",
  unread_count: 0,
  last_message: null,
  can_restrict_to_members_in_order: false,
  has_hidden_reserved_messages: false,
};

function message(overrides: Partial<ChatMessage> & { id: number }): ChatMessage {
  return {
    channel_id: 1,
    sender: { id: 2, first_name: "Jean", last_name: "Kabila", avatar_url: null },
    body: "Bonjour",
    image_url: null,
    sent_at: new Date().toISOString(),
    members_in_order_only: false,
    ...overrides,
  };
}

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.hash}`}</p>;
}

function renderModal(channel: ChatChannel = CHANNEL, onClose = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = (current: ChatChannel) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/club/chat"]}>
        <Routes>
          <Route path="/club/chat" element={<ConversationModal channel={current} onClose={onClose} />} />
          <Route path="/profil" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  const result = render(view(channel));
  return { ...result, rerenderWith: (next: ChatChannel) => result.rerender(view(next)), onClose };
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
        message({ id: 1, sender: { id: 1, first_name: "Moi", last_name: "Même", avatar_url: null }, body: "Salut !" }),
        message({ id: 2 }),
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
    vi.mocked(sendChatMessage).mockResolvedValue(
      message({ id: 3, sender: { id: 1, first_name: "Moi", last_name: "Même", avatar_url: null }, body: "Nouveau message" }),
    );

    const user = userEvent.setup();
    renderModal();

    const textarea = await screen.findByLabelText("Écrire un message…");
    await user.type(textarea, "Nouveau message");
    await user.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() =>
      expect(sendChatMessage).toHaveBeenCalledWith(1, { body: "Nouveau message", image: null, membersInOrderOnly: false }),
    );
    await waitFor(() => expect(textarea).toHaveValue(""));
  });

  it("marque le canal comme lu avec le dernier message reçu", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({
      results: [message({ id: 9, body: "Dernier message" })],
      count: 1,
      next_offset: null,
    });
    vi.mocked(markChannelRead).mockResolvedValue({ detail: "ok" });
    renderModal();

    await waitFor(() => expect(markChannelRead).toHaveBeenCalledWith(1, 9));
  });
});

describe("ConversationModal — messages réservés aux membres en ordre (C7)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  const BOARD_GENERAL: ChatChannel = { ...CHANNEL, can_restrict_to_members_in_order: true };

  it("n'affiche pas la case quand l'API ne l'autorise pas (autres rôles, canal Bureau, session de support)", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({ results: [], count: 0, next_offset: null });
    renderModal({ ...CHANNEL, channel_type: "board" });

    await screen.findByText("Aucun message pour l'instant. Lancez la conversation.");
    expect(screen.queryByRole("checkbox", { name: "Réservé aux membres en ordre" })).not.toBeInTheDocument();
    expect(screen.queryByText("Seuls les joueurs en ordre de cotisation et le bureau le verront.")).not.toBeInTheDocument();
  });

  it("affiche la case décochée avec son aide, change le placeholder et envoie le message réservé", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({ results: [], count: 0, next_offset: null });
    vi.mocked(sendChatMessage).mockResolvedValue(message({ id: 4, members_in_order_only: true }));
    const user = userEvent.setup();
    renderModal(BOARD_GENERAL);

    const checkbox = await screen.findByRole("checkbox", { name: "Réservé aux membres en ordre" });
    expect(checkbox).not.toBeChecked();
    expect(checkbox).toHaveAccessibleDescription("Seuls les joueurs en ordre de cotisation et le bureau le verront.");

    const textarea = screen.getByLabelText("Écrire un message…");
    expect(textarea).toHaveAttribute("placeholder", "Écrire un message…");
    await user.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(textarea).toHaveAttribute("placeholder", "Message réservé aux membres en ordre…");

    await user.type(textarea, "Réunion samedi");
    await user.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() =>
      expect(sendChatMessage).toHaveBeenCalledWith(1, { body: "Réunion samedi", image: null, membersInOrderOnly: true }),
    );
    // Après un envoi réussi, la case revient à décochée (C7.2).
    await waitFor(() => expect(checkbox).not.toBeChecked());
    expect(textarea).toHaveValue("");
    expect(textarea).toHaveAttribute("placeholder", "Écrire un message…");
  });

  it("conserve le texte et l'état réservé si l'envoi échoue", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({ results: [], count: 0, next_offset: null });
    vi.mocked(sendChatMessage).mockRejectedValue(new ApiError(0, null));
    const user = userEvent.setup();
    renderModal(BOARD_GENERAL);

    const checkbox = await screen.findByRole("checkbox", { name: "Réservé aux membres en ordre" });
    await user.click(checkbox);
    const textarea = screen.getByLabelText("Écrire un message…");
    await user.type(textarea, "Message important");
    await user.click(screen.getByRole("button", { name: "Envoyer" }));

    expect(await screen.findByText("Non envoyé")).toBeInTheDocument();
    expect(checkbox).toBeChecked();
    expect(textarea).toHaveValue("Message important");

    // « Réessayer » (le bouton d'envoi) renvoie avec la même valeur.
    await user.click(screen.getByRole("button", { name: "Envoyer" }));
    await waitFor(() => expect(sendChatMessage).toHaveBeenCalledTimes(2));
    expect(vi.mocked(sendChatMessage).mock.calls[1]).toEqual([
      1,
      { body: "Message important", image: null, membersInOrderOnly: true },
    ]);
  });

  it("droit retiré (403) : message de la fiche, case retirée, brouillon conservé, aucun renvoi automatique", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({ results: [], count: 0, next_offset: null });
    vi.mocked(sendChatMessage).mockRejectedValue(
      new ApiError(403, { detail: "Seuls les membres du bureau peuvent réserver un message aux membres en ordre." }),
    );
    const user = userEvent.setup();
    renderModal(BOARD_GENERAL);

    await user.click(await screen.findByRole("checkbox", { name: "Réservé aux membres en ordre" }));
    const textarea = screen.getByLabelText("Écrire un message…");
    await user.type(textarea, "Pour les membres en ordre");
    await user.click(screen.getByRole("button", { name: "Envoyer" }));

    expect(await screen.findByText("Vous ne pouvez plus réserver un message aux membres en ordre.")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Réservé aux membres en ordre" })).not.toBeInTheDocument();
    expect(textarea).toHaveValue("Pour les membres en ordre");
    expect(sendChatMessage).toHaveBeenCalledTimes(1);
  });

  it("affiche le message de l'API en cas de refus 400", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({ results: [], count: 0, next_offset: null });
    vi.mocked(sendChatMessage).mockRejectedValue(
      new ApiError(400, { detail: "Un message réservé aux membres en ordre ne peut être publié que dans le canal Général." }),
    );
    const user = userEvent.setup();
    renderModal(BOARD_GENERAL);

    await user.click(await screen.findByRole("checkbox", { name: "Réservé aux membres en ordre" }));
    await user.type(screen.getByLabelText("Écrire un message…"), "Test");
    await user.click(screen.getByRole("button", { name: "Envoyer" }));

    expect(
      await screen.findByText("Un message réservé aux membres en ordre ne peut être publié que dans le canal Général."),
    ).toBeInTheDocument();
  });

  it("affiche le badge « Membres en ordre » avant le texte d'un message réservé, et seulement sur lui", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({
      results: [
        message({ id: 5, body: "Réservé", members_in_order_only: true }),
        message({ id: 6, body: "Public" }),
        message({
          id: 7,
          sender: { id: 1, first_name: "Moi", last_name: "Même", avatar_url: null },
          body: "Le mien",
          members_in_order_only: true,
        }),
      ],
      count: 3,
      next_offset: null,
    });
    vi.mocked(markChannelRead).mockResolvedValue({ detail: "ok" });
    renderModal();

    const reserved = await screen.findByTestId("chat-message-5");
    const badge = within(reserved).getByText("Membres en ordre");
    const text = within(reserved).getByText("Réservé");
    // Badge placé avant le corps dans le DOM (C7.7).
    expect(badge.compareDocumentPosition(text) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(screen.getByTestId("chat-message-6")).queryByText("Membres en ordre")).not.toBeInTheDocument();
    expect(within(screen.getByTestId("chat-message-7")).getByText("Membres en ordre")).toBeInTheDocument();
  });

  it("joueur non en ordre : bandeau discret (note), état vide dédié et lien vers la situation financière", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({ results: [], count: 0, next_offset: null });
    const user = userEvent.setup();
    const { onClose } = renderModal({ ...CHANNEL, has_hidden_reserved_messages: true });

    expect(await screen.findByText("Aucun message à afficher pour l'instant.")).toBeInTheDocument();
    const note = screen.getByRole("note");
    expect(note).toHaveTextContent("Certains messages sont réservés aux membres en ordre de cotisation.");
    expect(note).not.toHaveAttribute("aria-live");
    // Le joueur non en ordre peut toujours écrire.
    expect(screen.getByLabelText("Écrire un message…")).toBeEnabled();

    await user.click(within(note).getByRole("button", { name: "Voir mon solde" }));
    expect(await screen.findByTestId("location")).toHaveTextContent("/profil#situation-financiere");
    expect(onClose).toHaveBeenCalled();
  });

  it("demande confirmation avant de quitter vers le solde si un message est en cours de saisie", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({ results: [], count: 0, next_offset: null });
    const user = userEvent.setup();
    renderModal({ ...CHANNEL, has_hidden_reserved_messages: true });

    await user.type(await screen.findByLabelText("Écrire un message…"), "Brouillon");
    await user.click(screen.getByRole("button", { name: "Voir mon solde" }));
    expect(await screen.findByRole("heading", { name: "Abandonner les modifications ?" })).toBeInTheDocument();
    expect(screen.queryByTestId("location")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Abandonner" }));
    expect(await screen.findByTestId("location")).toHaveTextContent("/profil#situation-financiere");
  });

  it("n'affiche pas le bandeau sans message réservé caché, ni quand la liste est en erreur", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({ results: [], count: 0, next_offset: null });
    const first = renderModal();
    await screen.findByText("Aucun message pour l'instant. Lancez la conversation.");
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    first.unmount();

    vi.mocked(listChatMessages).mockRejectedValue(new ApiError(500, null));
    renderModal({ ...CHANNEL, has_hidden_reserved_messages: true });
    expect(await screen.findByText("Impossible de charger les messages.")).toBeInTheDocument();
    expect(screen.queryByText("Certains messages sont réservés aux membres en ordre de cotisation.")).not.toBeInTheDocument();
  });

  it("recharge toute la fenêtre de messages quand la situation du joueur change", async () => {
    vi.mocked(listChatMessages).mockResolvedValue({ results: [message({ id: 10, body: "Public" })], count: 1, next_offset: null });
    vi.mocked(markChannelRead).mockResolvedValue({ detail: "ok" });
    const { rerenderWith } = renderModal({ ...CHANNEL, has_hidden_reserved_messages: true });
    await screen.findByText("Public");
    expect(screen.getByRole("note")).toBeInTheDocument();
    const callsBefore = vi.mocked(listChatMessages).mock.calls.length;

    // Le joueur régularise : l'API renvoie l'ancien message réservé à sa place.
    vi.mocked(listChatMessages).mockResolvedValue({
      results: [message({ id: 8, body: "Ancien réservé", members_in_order_only: true }), message({ id: 10, body: "Public" })],
      count: 2,
      next_offset: null,
    });
    rerenderWith({ ...CHANNEL, has_hidden_reserved_messages: false });

    expect(await screen.findByText("Ancien réservé")).toBeInTheDocument();
    expect(vi.mocked(listChatMessages).mock.calls.length).toBeGreaterThan(callsBefore);
    // Fenêtre complète (`limit`), jamais une interrogation incrémentale `after=`.
    expect(vi.mocked(listChatMessages).mock.calls.at(-1)).toEqual([1, { limit: 30 }]);
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });
});
