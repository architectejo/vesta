import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { AttachmentLink } from "./AttachmentLink";

describe("AttachmentLink", () => {
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;
  const originalOpen = window.open;

  afterEach(() => {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    window.open = originalOpen;
    vi.restoreAllMocks();
  });

  it("récupère le fichier via le téléchargement authentifié et l'ouvre dans un nouvel onglet", async () => {
    const blob = new Blob(["contenu"], { type: "application/pdf" });
    const download = vi.fn().mockResolvedValue({ blob, filename: "justificatif.pdf" });
    URL.createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    URL.revokeObjectURL = vi.fn();
    window.open = vi.fn().mockReturnValue({} as Window);

    const user = userEvent.setup();
    render(<AttachmentLink label="Voir le justificatif" download={download} />);

    await user.click(screen.getByRole("button", { name: "Voir le justificatif" }));

    await waitFor(() => expect(download).toHaveBeenCalledTimes(1));
    expect(window.open).toHaveBeenCalledWith("blob:mock-url", "_blank", "noopener,noreferrer");
  });

  it("affiche l'erreur en français quand le téléchargement échoue", async () => {
    const download = vi.fn().mockRejectedValue(new ApiError(404, { detail: "Ce fichier n'existe plus." }));
    const user = userEvent.setup();
    render(<AttachmentLink label="Voir le justificatif" download={download} />);

    await user.click(screen.getByRole("button", { name: "Voir le justificatif" }));

    expect(await screen.findByText("Ce fichier n'existe plus.")).toBeInTheDocument();
  });
});
