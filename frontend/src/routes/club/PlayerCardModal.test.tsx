import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PlayerCardModal } from "./PlayerCardModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return {
    ...actual,
    getPlayerCard: vi.fn(),
  };
});

import { getPlayerCard } from "../../api/clubs";
import { ApiError } from "../../api/client";

const CARD = {
  membership_id: 7,
  first_name: "Aimé",
  last_name: "Kalonji",
  photo: null,
  position: "defender",
  position_label: "Défenseur",
  position_detail: "Arrière gauche",
  jersey_number: 4,
  membership_status: "active",
  membership_status_label: "Inscrit",
  joined_on: "2024-03-15",
  roles: [{ role: "captain", label: "Capitaine" }],
};

function renderModal(props: Partial<React.ComponentProps<typeof PlayerCardModal>> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={queryClient}>
      <PlayerCardModal membershipId={7} onClose={onClose} {...props} />
    </QueryClientProvider>,
  );
  return { onClose };
}

describe("PlayerCardModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche « Fiche du joueur » par défaut, avec un pied « Fermer » toujours visible (club-carte-joueur.md A3)", async () => {
    vi.mocked(getPlayerCard).mockResolvedValue(CARD);
    renderModal();

    expect(screen.getByRole("heading", { name: "Fiche du joueur" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Aimé Kalonji")).toBeInTheDocument());
    // Deux éléments portent le nom accessible « Fermer » : la croix d'en-tête
    // et le bouton du pied (A3) ; on vérifie que le second existe bien.
    expect(screen.getAllByRole("button", { name: "Fermer" })).toHaveLength(2);
  });

  it("affiche « Ma carte de joueur » quand isOwnCard est vrai (A2, A9)", async () => {
    vi.mocked(getPlayerCard).mockResolvedValue(CARD);
    renderModal({ isOwnCard: true });

    expect(screen.getByRole("heading", { name: "Ma carte de joueur" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Aimé Kalonji")).toBeInTheDocument());
  });

  it("le bouton Fermer appelle onClose", async () => {
    vi.mocked(getPlayerCard).mockResolvedValue(CARD);
    const user = userEvent.setup();
    const { onClose } = renderModal();

    await waitFor(() => expect(screen.getAllByRole("button", { name: "Fermer" })).toHaveLength(2));
    const [, footerCloseButton] = screen.getAllByRole("button", { name: "Fermer" });
    await user.click(footerCloseButton!);
    expect(onClose).toHaveBeenCalled();
  });

  it("affiche le statut (sans doublon), « Membre depuis » et les rôles sous la carte, hors carte FIFA", async () => {
    vi.mocked(getPlayerCard).mockResolvedValue(CARD);
    renderModal();

    // `membership_status_label` ("Inscrit") répète déjà le libellé du
    // statut : `StatusBadge` ne doit pas l'afficher une seconde fois via
    // `detail` (anti-pattern déjà vu sur ClubsLicencesPage, « Essai · Essai »).
    expect(await screen.findByText("Inscrit")).toBeInTheDocument();
    expect(screen.queryByText("Inscrit · Inscrit")).not.toBeInTheDocument();
    expect(screen.getByText("Membre depuis mars 2024")).toBeInTheDocument();
    expect(screen.getByText("Capitaine")).toBeInTheDocument();
  });

  it("« Aucun rôle particulier. » quand la liste des rôles est vide", async () => {
    vi.mocked(getPlayerCard).mockResolvedValue({ ...CARD, roles: [] });
    renderModal();

    expect(await screen.findByText("Aucun rôle particulier.")).toBeInTheDocument();
  });

  it("masque la ligne « Membre depuis » quand joined_on est vide", async () => {
    vi.mocked(getPlayerCard).mockResolvedValue({ ...CARD, joined_on: null });
    renderModal();

    await waitFor(() => expect(screen.getByText("Aimé Kalonji")).toBeInTheDocument());
    expect(screen.queryByText(/^Membre depuis/)).not.toBeInTheDocument();
  });

  it("affiche un état d'erreur avec « Réessayer » si l'appel échoue", async () => {
    vi.mocked(getPlayerCard).mockRejectedValue(new Error("boom"));
    renderModal();

    expect(await screen.findByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });

  it("« Comparer » ouvre la comparaison avec ce joueur déjà choisi (club-carte-joueur.md B3)", async () => {
    vi.mocked(getPlayerCard).mockResolvedValue(CARD);
    const user = userEvent.setup();
    renderModal();

    const compareButton = await screen.findByRole("button", { name: "Comparer" });
    await user.click(compareButton);

    expect(await screen.findByRole("heading", { name: "Comparer des joueurs" })).toBeInTheDocument();
    expect(screen.getByText("Choisissez au moins 2 joueurs à comparer.")).toBeInTheDocument();
  });

  it("joueur introuvable (404) : message de l'API et bouton « Fermer » (A7)", async () => {
    vi.mocked(getPlayerCard).mockRejectedValue(
      new ApiError(404, { detail: "Ce joueur n'existe pas dans ce club." }),
    );
    const user = userEvent.setup();
    const { onClose } = renderModal();

    expect(await screen.findByText("Ce joueur n'existe pas dans ce club.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();

    const closeButtons = screen.getAllByRole("button", { name: "Fermer" });
    expect(closeButtons.length).toBeGreaterThanOrEqual(2);
    await user.click(closeButtons[closeButtons.length - 1]!);
    expect(onClose).toHaveBeenCalled();
  });
});
