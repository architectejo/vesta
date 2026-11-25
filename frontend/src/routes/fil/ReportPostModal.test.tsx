import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { ToastProvider } from "../../design-system";

vi.mock("../../api/social", async () => {
  const actual = await vi.importActual<typeof import("../../api/social")>("../../api/social");
  return { ...actual, reportPost: vi.fn() };
});

import { reportPost } from "../../api/social";
import { ReportPostModal } from "./ReportPostModal";

function renderModal() {
  render(
    <ToastProvider>
      <ReportPostModal open postId={1} onClose={vi.fn()} onReported={vi.fn()} />
    </ToastProvider>,
  );
}

describe("ReportPostModal : erreurs", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("affiche le message de l'API pour une erreur 400", async () => {
    vi.mocked(reportPost).mockRejectedValue(
      new ApiError(400, { detail: "Vous avez déjà signalé cette publication." }),
    );
    renderModal();
    await userEvent.click(screen.getByRole("button", { name: "Signaler" }));
    expect(await screen.findByText("Vous avez déjà signalé cette publication.")).toBeInTheDocument();
    expect(screen.queryByText(/Connexion impossible/)).not.toBeInTheDocument();
  });

  it("affiche le message réseau seulement hors connexion (status 0)", async () => {
    vi.mocked(reportPost).mockRejectedValue(new ApiError(0, null));
    renderModal();
    await userEvent.click(screen.getByRole("button", { name: "Signaler" }));
    await waitFor(() => {
      expect(screen.getByText(/Connexion impossible/)).toBeInTheDocument();
    });
  });
});
