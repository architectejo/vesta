import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import type { Post } from "../../api/social";
import { PostDetailModal } from "./PostDetailModal";

vi.mock("../../api/social", async () => {
  const actual = await vi.importActual<typeof import("../../api/social")>("../../api/social");
  return {
    ...actual,
    getPost: vi.fn(),
    listComments: vi.fn(),
    addComment: vi.fn(),
    deleteComment: vi.fn(),
  };
});

import { addComment, getPost, listComments } from "../../api/social";

function makePost(overrides: Partial<Post> = {}): Post {
  return {
    id: 7,
    author: { id: 10, first_name: "Amos", last_name: "Kanku", avatar_url: null },
    club_id: 1,
    club_name: "Club fictif",
    body: "Bonne séance aujourd'hui !",
    visibility: "club_only",
    post_kind: "manual",
    created_at: "2026-11-26T18:00:00Z",
    images: [],
    like_count: 0,
    comment_count: 0,
    is_liked_by_me: false,
    recent_comments: [],
    can_delete: false,
    is_reported_by_me: false,
    ...overrides,
  };
}

function renderModal(onChanged = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <PostDetailModal postId={7} onClose={vi.fn()} onChanged={onChanged} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onChanged };
}

describe("PostDetailModal — rafraîchissement du fil (série 6)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("prévient le fil après l'envoi d'un commentaire, pour mettre à jour le compteur « Commenter » de la carte", async () => {
    vi.mocked(getPost).mockResolvedValue(makePost());
    vi.mocked(listComments).mockResolvedValue({ results: [], count: 0, next_offset: null });
    vi.mocked(addComment).mockResolvedValue({
      id: 1,
      post_id: 7,
      author: { id: 11, first_name: "Éric", last_name: "Fictif", avatar_url: null },
      body: "Bravo",
      created_at: "2026-11-26T18:05:00Z",
    });
    const user = userEvent.setup();
    const { onChanged } = renderModal();

    const field = await screen.findByLabelText("Écrire un commentaire…");
    await user.type(field, "Bravo");
    await user.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(addComment).toHaveBeenCalledWith(7, "Bravo"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("ne prévient pas le fil si l'envoi du commentaire échoue", async () => {
    vi.mocked(getPost).mockResolvedValue(makePost());
    vi.mocked(listComments).mockResolvedValue({ results: [], count: 0, next_offset: null });
    vi.mocked(addComment).mockRejectedValue(new Error("réseau"));
    const user = userEvent.setup();
    const { onChanged } = renderModal();

    await user.type(await screen.findByLabelText("Écrire un commentaire…"), "Bravo");
    await user.click(screen.getByRole("button", { name: "Envoyer" }));

    expect(await screen.findByText("Non envoyé")).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });
});
