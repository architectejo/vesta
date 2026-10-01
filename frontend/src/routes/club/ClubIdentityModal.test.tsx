import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import type { ClubIdentity } from "../../api/clubs";
import { ClubIdentityModal } from "./ClubIdentityModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, updateClubIdentity: vi.fn() };
});

vi.mock("../club-creation/colorFromImage", () => ({
  extractColorsFromImage: vi.fn(),
}));

import { updateClubIdentity } from "../../api/clubs";
import { extractColorsFromImage } from "../club-creation/colorFromImage";

// Couleurs de test synthétiques (marine et rouge), sans lien avec un club réel.
const EXISTING: ClubIdentity = {
  id: 1,
  name: "Club de démonstration",
  slug: "demo",
  logo: null,
  primary_color: "#9a95a5",
  secondary_color: "#5c5963",
  city: "Kinshasa",
  country: "RD Congo",
  currency: "USD",
  currency_locked: false,
  timezone: "Africa/Kinshasa",
};

function renderModal(identity: ClubIdentity = EXISTING) {
  const onClose = vi.fn();
  const onUpdated = vi.fn();
  render(
    <ToastProvider>
      <ClubIdentityModal identity={identity} onClose={onClose} onUpdated={onUpdated} />
    </ToastProvider>,
  );
  return { onClose, onUpdated };
}

function logoInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("Champ logo introuvable");
  return input;
}

function logoFile(name = "logo.jpeg"): File {
  return new File(["x"], name, { type: "image/jpeg" });
}

describe("ClubIdentityModal : couleurs proposées à partir du logo", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("pré-remplit les couleurs à l'ajout d'un logo, sans rien enregistrer", async () => {
    vi.mocked(extractColorsFromImage).mockResolvedValue({
      primary: "#1b2143",
      secondary: "#d2232a",
    });
    const user = userEvent.setup();
    renderModal();

    await user.upload(logoInput(), logoFile());

    await waitFor(() => {
      expect(screen.getByLabelText("Couleur principale")).toHaveValue("#1b2143");
    });
    expect(screen.getByLabelText("Couleur secondaire")).toHaveValue("#d2232a");
    expect(screen.getByText(/Couleurs proposées à partir du logo/)).toBeInTheDocument();
    expect(extractColorsFromImage).toHaveBeenCalledTimes(1);
    expect(updateClubIdentity).not.toHaveBeenCalled();
  });

  it("ne remplace jamais une couleur déjà modifiée à la main par un nouveau logo (choix manuel prioritaire)", async () => {
    // Remontée utilisateur : le thème Classic doit refléter les couleurs
    // choisies par le club, pas une extraction automatique qui les écraserait.
    vi.mocked(extractColorsFromImage).mockResolvedValue({
      primary: "#1b2143",
      secondary: "#d2232a",
    });
    const user = userEvent.setup();
    renderModal();

    const primary = screen.getByLabelText("Couleur principale");
    await user.clear(primary);
    await user.type(primary, "#00ff00");

    await user.upload(logoInput(), logoFile());
    await waitFor(() => expect(extractColorsFromImage).toHaveBeenCalledTimes(1));

    // La couleur saisie à la main reste intacte : la proposition du logo
    // n'a pas été appliquée par-dessus.
    expect(screen.getByLabelText("Couleur principale")).toHaveValue("#00ff00");
    expect(screen.getByLabelText("Couleur secondaire")).toHaveValue("#5c5963");
    expect(screen.queryByText(/Couleurs proposées à partir du logo/)).not.toBeInTheDocument();
  });

  it("enregistre les couleurs proposées seulement après « Enregistrer », modifiables avant", async () => {
    vi.mocked(extractColorsFromImage).mockResolvedValue({
      primary: "#1b2143",
      secondary: "#d2232a",
    });
    vi.mocked(updateClubIdentity).mockResolvedValue({ ...EXISTING });
    const user = userEvent.setup();
    const { onUpdated } = renderModal();

    await user.upload(logoInput(), logoFile());
    await waitFor(() => {
      expect(screen.getByLabelText("Couleur principale")).toHaveValue("#1b2143");
    });

    const secondary = screen.getByLabelText("Couleur secondaire");
    await user.clear(secondary);
    await user.type(secondary, "#aa0000");
    expect(updateClubIdentity).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() => {
      expect(updateClubIdentity).toHaveBeenCalledWith(
        expect.objectContaining({
          primary_color: "#1b2143",
          secondary_color: "#aa0000",
          logo: expect.any(File),
        }),
      );
      expect(onUpdated).toHaveBeenCalled();
    });
  });

  it("laisse les couleurs actuelles quand aucune couleur ne peut être proposée (logo noir et blanc)", async () => {
    vi.mocked(extractColorsFromImage).mockResolvedValue(null);
    const user = userEvent.setup();
    renderModal();

    await user.upload(logoInput(), logoFile());

    await waitFor(() => expect(extractColorsFromImage).toHaveBeenCalled());
    expect(screen.getByLabelText("Couleur principale")).toHaveValue("#9a95a5");
    expect(screen.getByLabelText("Couleur secondaire")).toHaveValue("#5c5963");
    expect(screen.queryByText(/Couleurs proposées à partir du logo/)).not.toBeInTheDocument();
  });

  it("indique l'analyse en cours pendant l'extraction", async () => {
    let resolveExtraction: (value: { primary: string; secondary: string } | null) => void = () => {};
    vi.mocked(extractColorsFromImage).mockReturnValue(
      new Promise((resolve) => {
        resolveExtraction = resolve;
      }),
    );
    const user = userEvent.setup();
    renderModal();

    await user.upload(logoInput(), logoFile());
    expect(await screen.findByText("Analyse du logo en cours…")).toBeInTheDocument();

    resolveExtraction({ primary: "#1b2143", secondary: "#d2232a" });
    await waitFor(() => {
      expect(screen.queryByText("Analyse du logo en cours…")).not.toBeInTheDocument();
    });
  });

  it("affiche un aperçu du logo déjà enregistré à l'ouverture", () => {
    renderModal({ ...EXISTING, logo: "https://cdn.example.test/logos/demo.png" });
    expect(screen.getByAltText("Logo actuel du club")).toHaveAttribute(
      "src",
      "https://cdn.example.test/logos/demo.png",
    );
    // Le bouton propose de remplacer, pas seulement de choisir, puisqu'un logo existe déjà.
    expect(screen.getByRole("button", { name: "Remplacer le logo" })).toBeInTheDocument();
  });

  it("affiche un état vide explicite quand aucun logo n'existe encore", () => {
    renderModal();
    expect(screen.getByText("Aucun logo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choisir un logo" })).toBeInTheDocument();
  });

  it("affiche un aperçu du fichier après sa sélection, et met à jour l'aperçu en direct", async () => {
    vi.mocked(extractColorsFromImage).mockResolvedValue(null);
    const user = userEvent.setup();
    renderModal();

    await user.upload(logoInput(), logoFile());

    await waitFor(() => {
      expect(screen.getByAltText("Aperçu du logo choisi")).toBeInTheDocument();
    });
    // Le logo déjà enregistré (absent ici) ne s'affiche plus une fois un
    // nouveau fichier choisi : un seul aperçu à la fois.
    expect(screen.queryByAltText("Logo actuel du club")).not.toBeInTheDocument();
    expect(screen.queryByText("Aucun logo")).not.toBeInTheDocument();
  });

  it("ignore la réponse tardive d'un logo remplacé entre-temps", async () => {
    let resolveFirst: (value: { primary: string; secondary: string } | null) => void = () => {};
    vi.mocked(extractColorsFromImage)
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
      )
      .mockResolvedValueOnce({ primary: "#112233", secondary: "#445566" });
    const user = userEvent.setup();
    renderModal();

    await user.upload(logoInput(), logoFile("premier.jpeg"));
    await user.upload(logoInput(), logoFile("second.jpeg"));
    await waitFor(() => {
      expect(screen.getByLabelText("Couleur principale")).toHaveValue("#112233");
    });

    resolveFirst({ primary: "#1b2143", secondary: "#d2232a" });
    await Promise.resolve();
    expect(screen.getByLabelText("Couleur principale")).toHaveValue("#112233");
    expect(screen.getByLabelText("Couleur secondaire")).toHaveValue("#445566");
  });
});
