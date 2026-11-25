import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import type { Post } from "../../api/social";
import { PostCard } from "./PostCard";

vi.mock("../../api/social", async () => {
  const actual = await vi.importActual<typeof import("../../api/social")>("../../api/social");
  return {
    ...actual,
    togglePostLike: vi.fn(),
    deletePost: vi.fn(),
    reportPost: vi.fn(),
  };
});

import { deletePost, reportPost, togglePostLike } from "../../api/social";

function makePost(overrides: Partial<Post> = {}): Post {
  return {
    id: 1,
    author: { id: 10, first_name: "Amos", last_name: "Kanku", avatar_url: null },
    club_id: 1,
    club_name: "Loisirs Club Discovery",
    body: "Bonne séance aujourd'hui !",
    visibility: "club_only",
    post_kind: "manual",
    created_at: "2026-09-29T18:00:00Z",
    images: [],
    like_count: 0,
    comment_count: 0,
    is_liked_by_me: false,
    recent_comments: [],
    can_delete: true,
    is_reported_by_me: false,
    ...overrides,
  };
}

function renderCard(post: Post, onOpen = vi.fn(), onChanged = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <PostCard post={post} onOpen={onOpen} onChanged={onChanged} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onOpen, onChanged };
}

describe("PostCard", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("les boutons « J'aime » et « Commenter » ont une cible tactile d'au moins 36 px (règle 16)", () => {
    renderCard(makePost());
    expect(screen.getByRole("button", { name: /J'aime/ }).className).toContain("min-h-[36px]");
    expect(screen.getByRole("button", { name: /Commenter/ }).className).toContain("min-h-[36px]");
  });

  it("affiche l'auteur, le texte et la puce de visibilité « Club »", () => {
    renderCard(makePost());
    expect(screen.getByText("Amos Kanku")).toBeInTheDocument();
    expect(screen.getByText("Bonne séance aujourd'hui !")).toBeInTheDocument();
    expect(screen.getByText("Club")).toBeInTheDocument();
  });

  it("« J'aime » bascule via l'API", async () => {
    vi.mocked(togglePostLike).mockResolvedValue({ liked: true, like_count: 1 });
    const user = userEvent.setup();
    renderCard(makePost());

    await user.click(screen.getByRole("button", { name: "J'aime" }));
    await waitFor(() => expect(togglePostLike).toHaveBeenCalledWith(1));
  });

  it("le menu « … » permet de signaler la publication", async () => {
    vi.mocked(reportPost).mockResolvedValue({ detail: "ok" });
    const user = userEvent.setup();
    renderCard(makePost());

    await user.click(screen.getByRole("button", { name: "Plus d'actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Signaler la publication" }));
    await user.click(screen.getByRole("button", { name: "Signaler" }));

    await waitFor(() => expect(reportPost).toHaveBeenCalledWith(1, ""));
    expect(await screen.findByText("Merci. La publication a été signalée à l'équipe Vesta.")).toBeInTheDocument();
  });

  it("« Supprimer la publication » n'apparaît que si can_delete est vrai", async () => {
    const user = userEvent.setup();
    renderCard(makePost({ can_delete: false }));
    await user.click(screen.getByRole("button", { name: "Plus d'actions" }));
    expect(screen.queryByRole("menuitem", { name: "Supprimer la publication" })).not.toBeInTheDocument();
  });

  it("supprime la publication après confirmation", async () => {
    vi.mocked(deletePost).mockResolvedValue(undefined);
    const user = userEvent.setup();
    const { onChanged } = renderCard(makePost());

    await user.click(screen.getByRole("button", { name: "Plus d'actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Supprimer la publication" }));
    await user.click(screen.getByRole("button", { name: "Supprimer" }));

    await waitFor(() => expect(deletePost).toHaveBeenCalledWith(1));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });
});
