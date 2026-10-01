import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PublicClubCreationSettings } from "../../api/clubs";
import { AuthProvider } from "../../auth/AuthContext";
import { ClubCreationWizard } from "./ClubCreationWizard";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getPublicClubCreationSettings: vi.fn(), createClub: vi.fn() };
});

vi.mock("./colorFromImage", () => ({
  extractColorsFromImage: vi.fn(),
}));

import { createClub, getPublicClubCreationSettings } from "../../api/clubs";
import { extractColorsFromImage } from "./colorFromImage";

const SETTINGS_WITH_TERMS: PublicClubCreationSettings = {
  trial_duration_days: 30,
  grace_period_days: 15,
  timezones: ["Africa/Kinshasa"],
  terms_version: {
    id: 7,
    version_number: "1.0",
    published_at: "2026-09-01T00:00:00Z",
    content: "Contenu de test",
  },
};

const SETTINGS_WITHOUT_TERMS: PublicClubCreationSettings = {
  ...SETTINGS_WITH_TERMS,
  terms_version: null,
};

function renderWizard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ClubCreationWizard onClose={vi.fn()} />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

async function goToStep3(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Nom du club"), "Club de test");
  await user.type(screen.getByLabelText("Ville"), "Kinshasa");
  await user.type(screen.getByLabelText("Pays"), "République démocratique du Congo");
  await user.click(screen.getByRole("button", { name: "Suivant" }));

  await user.type(screen.getByLabelText("Prénom"), "Jean");
  await user.type(screen.getByLabelText("Nom"), "Mukendi");
  await user.type(screen.getByLabelText("Email"), "jean@example.com");
  await user.click(screen.getByRole("button", { name: "Milieu" }));
  await user.click(screen.getByRole("button", { name: "Suivant" }));

  await screen.findByText(/Licence d'essai gratuite de 30 jours/);
}

describe("ClubCreationWizard : étape 3, bouton « Créer mon club »", () => {
  // Chaque test saisit les étapes 1 et 2 avec userEvent (une trentaine de
  // frappes) : la limite par défaut de 5 s est trop juste sous charge.
  vi.setConfig({ testTimeout: 30_000 });

  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("explique que les CGU ne sont pas publiées et désactive le bouton", async () => {
    vi.mocked(getPublicClubCreationSettings).mockResolvedValue(SETTINGS_WITHOUT_TERMS);
    const user = userEvent.setup();
    renderWizard();
    await goToStep3(user);

    expect(
      screen.getByText(/Les conditions générales d'utilisation ne sont pas encore publiées/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Créer mon club" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeEnabled();
  });

  it("relance le chargement des paramètres avec « Réessayer » et débloque la création", async () => {
    vi.mocked(getPublicClubCreationSettings)
      .mockResolvedValueOnce(SETTINGS_WITHOUT_TERMS)
      .mockResolvedValue(SETTINGS_WITH_TERMS);
    const user = userEvent.setup();
    renderWizard();
    await goToStep3(user);

    await user.click(screen.getByRole("button", { name: "Réessayer" }));

    expect(await screen.findByRole("checkbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Créer mon club" })).toBeEnabled();
    expect(getPublicClubCreationSettings).toHaveBeenCalledTimes(2);
  });

  it("affiche l'erreur de la case sans appeler l'API quand les CGU ne sont pas cochées", async () => {
    vi.mocked(getPublicClubCreationSettings).mockResolvedValue(SETTINGS_WITH_TERMS);
    const user = userEvent.setup();
    renderWizard();
    await goToStep3(user);

    await user.click(screen.getByRole("button", { name: "Créer mon club" }));

    expect(
      await screen.findByText("Vous devez accepter les conditions générales pour créer votre club."),
    ).toBeInTheDocument();
    expect(createClub).not.toHaveBeenCalled();
  });

  it("envoie la création avec la version des CGU et accept_terms quand la case est cochée", async () => {
    vi.mocked(getPublicClubCreationSettings).mockResolvedValue(SETTINGS_WITH_TERMS);
    vi.mocked(createClub).mockRejectedValue(new Error("arrêt du test après l'appel"));
    const user = userEvent.setup();
    renderWizard();
    await goToStep3(user);

    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Créer mon club" }));

    await waitFor(() => expect(createClub).toHaveBeenCalledTimes(1));
    expect(createClub).toHaveBeenCalledWith(
      expect.objectContaining({ terms_version_id: 7, accept_terms: true }),
    );
    // L'échec réseau est visible : jamais de retour silencieux.
    expect(await screen.findByText(/La création n'a pas abouti/)).toBeInTheDocument();
  });
});

function logoInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("Champ logo introuvable");
  return input;
}

function logoFile(name = "logo.jpeg"): File {
  return new File(["x"], name, { type: "image/jpeg" });
}

describe("ClubCreationWizard : étape 1, couleurs et logo", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.mocked(getPublicClubCreationSettings).mockResolvedValue(SETTINGS_WITH_TERMS);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("pré-remplit les couleurs proposées à l'ajout d'un logo", async () => {
    vi.mocked(extractColorsFromImage).mockResolvedValue({
      primary: "#1b2143",
      secondary: "#d2232a",
    });
    const user = userEvent.setup();
    renderWizard();

    await user.upload(logoInput(), logoFile());

    await waitFor(() => {
      expect(screen.getByLabelText("Couleur principale (facultatif)")).toHaveValue("#1b2143");
    });
    expect(screen.getByLabelText("Couleur secondaire (facultatif)")).toHaveValue("#d2232a");
    expect(screen.getByText(/Couleurs proposées à partir du logo/)).toBeInTheDocument();
  });

  it("ne remplace jamais une couleur déjà choisie à la main par le logo ajouté ensuite (choix manuel prioritaire)", async () => {
    // Remontée utilisateur : le thème Classic doit refléter les couleurs
    // choisies par le club à l'inscription, pas une extraction automatique
    // qui les écraserait au moment où le logo est ajouté.
    vi.mocked(extractColorsFromImage).mockResolvedValue({
      primary: "#1b2143",
      secondary: "#d2232a",
    });
    const user = userEvent.setup();
    renderWizard();

    await user.type(screen.getByLabelText("Couleur principale (facultatif)"), "#00ff00");

    await user.upload(logoInput(), logoFile());
    await waitFor(() => expect(extractColorsFromImage).toHaveBeenCalledTimes(1));

    expect(screen.getByLabelText("Couleur principale (facultatif)")).toHaveValue("#00ff00");
    expect(screen.getByLabelText("Couleur secondaire (facultatif)")).toHaveValue("");
    expect(screen.queryByText(/Couleurs proposées à partir du logo/)).not.toBeInTheDocument();
  });
});
