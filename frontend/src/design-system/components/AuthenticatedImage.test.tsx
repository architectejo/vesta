import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthenticatedImage } from "./AuthenticatedImage";

describe("AuthenticatedImage", () => {
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;

  afterEach(() => {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    vi.restoreAllMocks();
  });

  it("affiche l'image récupérée par la vue authentifiée", async () => {
    const blob = new Blob(["contenu"], { type: "image/png" });
    const download = vi.fn().mockResolvedValue({ blob, filename: "image.png" });
    URL.createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    URL.revokeObjectURL = vi.fn();

    render(<AuthenticatedImage cacheKey={1} download={download} alt="Photo du joueur" />);

    const img = await screen.findByAltText("Photo du joueur");
    expect(img).toHaveAttribute("src", "blob:mock-url");
    expect(download).toHaveBeenCalledTimes(1);
  });

  it("affiche « Image indisponible » quand le téléchargement échoue", async () => {
    const download = vi.fn().mockRejectedValue(new Error("réseau"));
    render(<AuthenticatedImage cacheKey={2} download={download} alt="Photo" />);

    expect(await screen.findByText("Image indisponible")).toBeInTheDocument();
  });

  it("ne recharge pas l'image quand seule l'identité de la fonction change, tant que cacheKey est stable", async () => {
    const blob = new Blob(["contenu"], { type: "image/png" });
    URL.createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    URL.revokeObjectURL = vi.fn();
    const download1 = vi.fn().mockResolvedValue({ blob, filename: "image.png" });

    const { rerender } = render(<AuthenticatedImage cacheKey={1} download={download1} alt="Photo" />);
    await waitFor(() => expect(download1).toHaveBeenCalledTimes(1));

    const download2 = vi.fn().mockResolvedValue({ blob, filename: "image.png" });
    rerender(<AuthenticatedImage cacheKey={1} download={download2} alt="Photo" />);

    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(download2).not.toHaveBeenCalled();
  });
});
