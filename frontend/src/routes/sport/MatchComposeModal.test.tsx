import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { ClubPlayerListItem } from "../../api/clubs";
import { ToastProvider } from "../../design-system";
import { MatchComposeModal } from "./MatchComposeModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, listClubPlayers: vi.fn() };
});
vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, addToComposition: vi.fn(), listEligibility: vi.fn() };
});
vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return { ...actual, getTreasuryCapabilities: vi.fn(), getCurrentCashSession: vi.fn() };
});

import { listClubPlayers } from "../../api/clubs";
import { addToComposition, listEligibility } from "../../api/sport";
import { getCurrentCashSession, getTreasuryCapabilities, type TreasuryCapabilities } from "../../api/treasury";

function player(id: number, first: string, last: string, unavailable = false): ClubPlayerListItem {
  return {
    membership_id: id,
    first_name: first,
    last_name: last,
    photo: null,
    position: "midfielder",
    position_label: "Milieu",
    position_detail: "",
    jersey_number: id,
    membership_status: "active",
    membership_status_label: "Inscrit",
    roles: [],
    is_unavailable: unavailable,
  };
}

/** Effectif servi par statut, comme l'API (`?status=active` / `?status=pending`). */
function mockRoster(active: ClubPlayerListItem[], pending: ClubPlayerListItem[] = []) {
  vi.mocked(listClubPlayers).mockImplementation((params = {}) =>
    Promise.resolve(params.status === "pending" ? pending : active),
  );
}

function capabilities(canRecord: boolean) {
  return {
    currency: "USD",
    capabilities: { can_record_payments: canRecord } as TreasuryCapabilities,
  };
}

function renderModal() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onSaved = vi.fn();
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MatchComposeModal open matchId={6} existing={[]} onClose={vi.fn()} onSaved={onSaved} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onSaved, queryClient };
}

beforeEach(() => {
  vi.mocked(getTreasuryCapabilities).mockResolvedValue(capabilities(false));
});

describe("MatchComposeModal — joueurs non sélectionnables (§4.1 bis, CLAUDE.md règle 5, série 6)", () => {
  beforeEach(() => {
    vi.mocked(listEligibility).mockResolvedValue({ count: 0, results: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("désactive la case d'un joueur indisponible, l'affiche quand même et le range après les sélectionnables", async () => {
    mockRoster([
      player(28, "Aimé", "Leurre", true),
      player(12, "Kevin", "Proto"),
    ]);
    renderModal();

    const blocked = await screen.findByRole("checkbox", { name: "Sélectionner Aimé Leurre" });
    expect(blocked).toBeDisabled();
    expect(blocked).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText(/Non sélectionnable/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sélectionner Kevin Proto" })).toBeEnabled();

    const boxes = screen.getAllByRole("checkbox");
    expect(boxes[0]).toHaveAccessibleName("Sélectionner Kevin Proto");
    expect(boxes[1]).toHaveAccessibleName("Sélectionner Aimé Leurre");
  });

  it("n'envoie jamais un joueur indisponible au service de composition", async () => {
    mockRoster([player(28, "Aimé", "Leurre", true), player(12, "Kevin", "Proto")]);
    vi.mocked(addToComposition).mockResolvedValue({} as Awaited<ReturnType<typeof addToComposition>>);
    const user = userEvent.setup();
    const { onSaved } = renderModal();

    await user.click(await screen.findByRole("checkbox", { name: "Sélectionner Aimé Leurre" }));
    await user.click(screen.getByRole("checkbox", { name: "Sélectionner Kevin Proto" }));
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(addToComposition).toHaveBeenCalledTimes(1);
    expect(addToComposition).toHaveBeenCalledWith(6, expect.objectContaining({ membership_id: 12 }));
  });

  it("la case à cocher a une zone tactile de 44 px (h-11)", async () => {
    mockRoster([player(12, "Kevin", "Proto")]);
    renderModal();
    const box = await screen.findByRole("checkbox", { name: "Sélectionner Kevin Proto" });
    expect(box.closest("label")?.className).toContain("h-11");
  });
});

describe("MatchComposeModal — motif d'indisponibilité lu de l'API (§4.1 bis)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche sous le nom le motif fourni par GET /sport/eligibility/, sans le recomposer", async () => {
    mockRoster([player(13, "Aimé", "Leurre", true), player(12, "Kevin", "Proto")]);
    vi.mocked(listEligibility).mockResolvedValue({
      count: 2,
      results: [
        { membership_id: 13, eligible: false, reason_code: "debt", reason: "En dette : 10.00 USD." },
        { membership_id: 12, eligible: true, reason_code: "", reason: "" },
      ],
    });
    renderModal();

    expect(await screen.findByText("En dette : 10.00 USD.")).toBeInTheDocument();
    expect(screen.queryByText(/Non sélectionnable/)).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sélectionner Aimé Leurre" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "Sélectionner Kevin Proto" })).toBeEnabled();
  });

  it("un joueur déclaré non éligible par l'API est désactivé et rangé en fin de liste même sans is_unavailable", async () => {
    mockRoster([player(13, "Aimé", "Leurre"), player(12, "Kevin", "Proto")]);
    vi.mocked(listEligibility).mockResolvedValue({
      count: 1,
      results: [{ membership_id: 13, eligible: false, reason_code: "suspension", reason: "Suspendu : encore 1 match." }],
    });
    renderModal();

    expect(await screen.findByText("Suspendu : encore 1 match.")).toBeInTheDocument();
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes[0]).toHaveAccessibleName("Sélectionner Kevin Proto");
    expect(boxes[1]).toHaveAccessibleName("Sélectionner Aimé Leurre");
    expect(boxes[1]).toBeDisabled();
  });

  it("403 : garde le texte générique, sans message d'erreur bloquant", async () => {
    mockRoster([player(13, "Aimé", "Leurre", true), player(12, "Kevin", "Proto")]);
    vi.mocked(listEligibility).mockRejectedValue(new ApiError(403, { detail: "Accès refusé." }));
    renderModal();

    expect(await screen.findByText(/Non sélectionnable/)).toBeInTheDocument();
    await waitFor(() => expect(listEligibility).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Accès refusé.")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sélectionner Kevin Proto" })).toBeEnabled();
  });

  it("erreur réseau : garde le comportement actuel (is_unavailable sans motif)", async () => {
    mockRoster([player(13, "Aimé", "Leurre", true)]);
    vi.mocked(listEligibility).mockRejectedValue(new ApiError(0, null));
    renderModal();

    expect(await screen.findByText(/Non sélectionnable/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sélectionner Aimé Leurre" })).toBeDisabled();
  });
});

describe("MatchComposeModal — régularisation sur place et non-contournement (§4.1, §4.1 bis)", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("charge aussi les joueurs en attente d'adhésion, grisés avec le motif de l'API", async () => {
    mockRoster([player(12, "Kevin", "Proto")], [{ ...player(40, "Paul", "Attente", true), membership_status: "pending" }]);
    vi.mocked(listEligibility).mockResolvedValue({
      count: 1,
      results: [{ membership_id: 40, eligible: false, reason_code: "pending_membership", reason: "En attente d'adhésion." }],
    });
    renderModal();

    expect(await screen.findByText("En attente d'adhésion.")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sélectionner Paul Attente" })).toBeDisabled();
    expect(listClubPlayers).toHaveBeenCalledWith({ status: "active" });
    expect(listClubPlayers).toHaveBeenCalledWith({ status: "pending" });
  });

  it("rafraîchit l'éligibilité et l'effectif toutes les 15 s tant que la modale est ouverte", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockRoster([player(12, "Kevin", "Proto")]);
    vi.mocked(listEligibility).mockResolvedValue({ count: 0, results: [] });
    renderModal();

    await screen.findByRole("checkbox", { name: "Sélectionner Kevin Proto" });
    await waitFor(() => expect(listEligibility).toHaveBeenCalledTimes(1));
    const rosterCalls = vi.mocked(listClubPlayers).mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    await waitFor(() => expect(listEligibility).toHaveBeenCalledTimes(2));
    expect(vi.mocked(listClubPlayers).mock.calls.length).toBeGreaterThan(rosterCalls);
  });

  it("joueur coché devenu non sélectionnable : décoché, bandeau avec le motif de l'API", async () => {
    mockRoster([player(12, "Kevin", "Proto"), player(13, "Aimé", "Leurre")]);
    vi.mocked(listEligibility).mockResolvedValue({ count: 0, results: [] });
    const user = userEvent.setup();
    const { queryClient } = renderModal();

    const box = await screen.findByRole("checkbox", { name: "Sélectionner Aimé Leurre" });
    await waitFor(() => expect(listEligibility).toHaveBeenCalled());
    await user.click(box);
    expect(box).toBeChecked();

    vi.mocked(listEligibility).mockResolvedValue({
      count: 1,
      results: [{ membership_id: 13, eligible: false, reason_code: "debt", reason: "En dette : 20.00 USD." }],
    });
    await act(async () => {
      await queryClient.refetchQueries();
    });

    expect(
      await screen.findByText(
        "Aimé Leurre n'est plus sélectionnable : En dette : 20.00 USD. Il a été retiré de votre sélection.",
      ),
    ).toBeInTheDocument();
    const after = screen.getByRole("checkbox", { name: "Sélectionner Aimé Leurre" });
    expect(after).not.toBeChecked();
    expect(after).toBeDisabled();
    expect(screen.getByText("0 titulaires · 0 remplaçants")).toBeInTheDocument();
  });

  it("joueur redevenu sélectionnable : toast « {nom} est désormais sélectionnable. »", async () => {
    mockRoster([player(13, "Aimé", "Leurre")]);
    vi.mocked(listEligibility).mockResolvedValue({
      count: 1,
      results: [{ membership_id: 13, eligible: false, reason_code: "debt", reason: "En dette : 20.00 USD." }],
    });
    const { queryClient } = renderModal();
    expect(await screen.findByText("En dette : 20.00 USD.")).toBeInTheDocument();
    expect(screen.queryByText(/désormais sélectionnable/)).not.toBeInTheDocument();

    vi.mocked(listEligibility).mockResolvedValue({
      count: 1,
      results: [{ membership_id: 13, eligible: true, reason_code: "", reason: "" }],
    });
    await act(async () => {
      await queryClient.refetchQueries();
    });

    expect(await screen.findByText("Aimé Leurre est désormais sélectionnable.")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sélectionner Aimé Leurre" })).toBeEnabled();
  });

  it("toucher une ligne grisée : panneau d'information seul, sans « Encaisser » ni choix de rôle", async () => {
    mockRoster([player(13, "Aimé", "Leurre", true)]);
    vi.mocked(listEligibility).mockResolvedValue({
      count: 1,
      results: [{ membership_id: 13, eligible: false, reason_code: "debt", reason: "En dette : 20.00 USD." }],
    });
    const user = userEvent.setup();
    renderModal();

    await screen.findByText("En dette : 20.00 USD.");
    await user.click(screen.getByRole("button", { name: "Pourquoi Aimé Leurre n'est pas sélectionnable" }));
    const note = screen.getByRole("note");
    expect(note).toHaveTextContent("Aimé Leurre ne peut pas être sélectionné : En dette : 20.00 USD");
    expect(within(note).queryByRole("button", { name: "Encaisser" })).not.toBeInTheDocument();
    expect(screen.queryByText("Titulaire")).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sélectionner Aimé Leurre" })).not.toBeChecked();
  });

  it("« Encaisser » seulement si l'API accorde l'encaissement ; ouvre la Caisse Terrain Express", async () => {
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(capabilities(true));
    vi.mocked(getCurrentCashSession).mockResolvedValue({ session: null });
    mockRoster([player(13, "Aimé", "Leurre", true)]);
    vi.mocked(listEligibility).mockResolvedValue({
      count: 1,
      results: [{ membership_id: 13, eligible: false, reason_code: "debt", reason: "En dette : 20.00 USD." }],
    });
    const user = userEvent.setup();
    renderModal();

    await screen.findByText("En dette : 20.00 USD.");
    await user.click(screen.getByRole("button", { name: "Pourquoi Aimé Leurre n'est pas sélectionnable" }));
    await user.click(await within(screen.getByRole("note")).findByRole("button", { name: "Encaisser" }));
    expect(await screen.findByRole("dialog", { name: "Ouvrir une session de caisse ?" })).toBeInTheDocument();
  });

  it("hors connexion : « Enregistrer » désactivé avec « Cette action nécessite une connexion. »", async () => {
    const onLine = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    mockRoster([player(12, "Kevin", "Proto")]);
    vi.mocked(listEligibility).mockResolvedValue({ count: 0, results: [] });
    const user = userEvent.setup();
    renderModal();

    await user.click(await screen.findByRole("checkbox", { name: "Sélectionner Kevin Proto" }));
    expect(screen.getByText("Cette action nécessite une connexion.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
    onLine.mockRestore();
  });
});

describe("MatchComposeModal — états de la liste (charte, CLAUDE.md règle 17)", () => {
  beforeEach(() => {
    vi.mocked(listEligibility).mockResolvedValue({ count: 0, results: [] });
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("effectif vide : « Aucun joueur dans l'effectif. »", async () => {
    mockRoster([]);
    renderModal();
    expect(await screen.findByText("Aucun joueur dans l'effectif.")).toBeInTheDocument();
  });

  it("échec du chargement : message explicite et « Réessayer »", async () => {
    vi.mocked(listClubPlayers).mockRejectedValue(new ApiError(500, {}));
    const user = userEvent.setup();
    renderModal();
    expect(await screen.findByText("Impossible de charger l'effectif.")).toBeInTheDocument();
    mockRoster([player(12, "Kevin", "Proto")]);
    await user.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByRole("checkbox", { name: "Sélectionner Kevin Proto" })).toBeInTheDocument();
  });

  it("aucun joueur sélectionnable : message en haut, liste grisée conservée", async () => {
    mockRoster([player(13, "Aimé", "Leurre", true)]);
    renderModal();
    expect(await screen.findByText("Aucun joueur n'est sélectionnable pour l'instant.")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sélectionner Aimé Leurre" })).toBeDisabled();
  });

  it("recherche sans résultat : état « aucun résultat »", async () => {
    mockRoster([player(12, "Kevin", "Proto")]);
    const user = userEvent.setup();
    renderModal();
    await screen.findByRole("checkbox", { name: "Sélectionner Kevin Proto" });
    await user.type(screen.getByRole("textbox", { name: "Nom ou numéro" }), "zzz");
    expect(screen.getByText("Aucun joueur ne correspond à « zzz ».")).toBeInTheDocument();
  });
});

describe("MatchComposeModal — puces de poste et tri (§4.1, demande du client remarques.md)", () => {
  beforeEach(() => {
    vi.mocked(listEligibility).mockResolvedValue({ count: 0, results: [] });
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  function at(
    id: number,
    first: string,
    last: string,
    position: ClubPlayerListItem["position"] | "",
    label: string,
    unavailable = false,
  ): ClubPlayerListItem {
    // Le poste est facultatif côté API (import historique) : "" possible.
    return {
      ...player(id, first, last, unavailable),
      position: position as ClubPlayerListItem["position"],
      position_label: label,
    };
  }

  const roster = () => [
    at(1, "Zoé", "Attaque", "forward", "Attaquant"),
    at(2, "Bruno", "Milieu", "midfielder", "Milieu"),
    at(3, "Albert", "Défense", "defender", "Défenseur"),
    at(4, "Yves", "Gardien", "goalkeeper", "Gardien"),
    at(5, "Abel", "Gardien", "goalkeeper", "Gardien"),
    at(6, "Sans", "Poste", "", ""),
    at(7, "Aaron", "Bloqué", "goalkeeper", "Gardien", true),
    at(8, "Victor", "Ailier", "forward", "Attaquant"),
  ];

  function checkboxNames(): string[] {
    return screen.getAllByRole("checkbox").map((box) => box.getAttribute("aria-label") ?? "");
  }

  it("joueur sans poste : « Choisir un poste » affiché, enregistrement refusé tant qu'aucun poste n'est choisi", async () => {
    mockRoster(roster());
    vi.mocked(addToComposition).mockResolvedValue({} as Awaited<ReturnType<typeof addToComposition>>);
    const user = userEvent.setup();
    const { onSaved } = renderModal();

    await user.click(await screen.findByRole("checkbox", { name: "Sélectionner Sans Poste" }));
    const select = screen.getByRole("combobox", { name: /Poste du jour/ });
    expect(select).toHaveDisplayValue("Choisir un poste");

    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(await screen.findByText("Choisissez le poste du jour.")).toBeInTheDocument();
    expect(addToComposition).not.toHaveBeenCalled();

    await user.selectOptions(select, "goalkeeper");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(addToComposition).toHaveBeenCalledWith(6, expect.objectContaining({ membership_id: 6, position: "goalkeeper" }));
  });

  it("affiche les puces de la spec, « Tous » actif par défaut", async () => {
    mockRoster(roster());
    renderModal();
    const group = await screen.findByRole("group", { name: "Filtrer par poste" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Tous",
      "Gardiens",
      "Défenseurs",
      "Milieux",
      "Attaquants",
    ]);
    expect(within(group).getByRole("button", { name: "Tous" })).toHaveAttribute("aria-pressed", "true");
  });

  it("trie par poste puis nom, sans poste en dernier, non sélectionnables toujours en fin", async () => {
    mockRoster(roster());
    renderModal();
    await screen.findByRole("checkbox", { name: "Sélectionner Abel Gardien" });
    expect(checkboxNames()).toEqual([
      "Sélectionner Abel Gardien",
      "Sélectionner Yves Gardien",
      "Sélectionner Albert Défense",
      "Sélectionner Bruno Milieu",
      "Sélectionner Victor Ailier",
      "Sélectionner Zoé Attaque",
      "Sélectionner Sans Poste",
      "Sélectionner Aaron Bloqué",
    ]);
  });

  it("sous « Tous » : intertitres par poste avec le nombre de lignes visibles, dont « Sans poste »", async () => {
    mockRoster(roster());
    renderModal();
    await screen.findByRole("checkbox", { name: "Sélectionner Abel Gardien" });
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      "Gardiens (2)",
      "Défenseurs (1)",
      "Milieux (1)",
      "Attaquants (2)",
      "Sans poste (1)",
      "Ne peuvent pas être composés (1)",
    ]);
  });

  it("une puce ne garde que son poste (non sélectionnables en fin) ; le joueur sans poste n'apparaît que sous « Tous »", async () => {
    mockRoster(roster());
    const user = userEvent.setup();
    renderModal();
    await screen.findByRole("checkbox", { name: "Sélectionner Abel Gardien" });
    const group = screen.getByRole("group", { name: "Filtrer par poste" });

    await user.click(within(group).getByRole("button", { name: "Gardiens" }));
    expect(checkboxNames()).toEqual([
      "Sélectionner Abel Gardien",
      "Sélectionner Yves Gardien",
      "Sélectionner Aaron Bloqué",
    ]);
    expect(screen.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();

    for (const chip of ["Défenseurs", "Milieux", "Attaquants"]) {
      await user.click(within(group).getByRole("button", { name: chip }));
      expect(screen.queryByRole("checkbox", { name: "Sélectionner Sans Poste" })).not.toBeInTheDocument();
    }

    await user.click(within(group).getByRole("button", { name: "Tous" }));
    expect(screen.getByRole("checkbox", { name: "Sélectionner Sans Poste" })).toBeInTheDocument();
  });

  it("le filtre se combine avec la recherche ; état vide explicite", async () => {
    mockRoster(roster());
    const user = userEvent.setup();
    renderModal();
    await screen.findByRole("checkbox", { name: "Sélectionner Abel Gardien" });
    const search = screen.getByRole("textbox", { name: "Nom ou numéro" });

    await user.click(within(screen.getByRole("group", { name: "Filtrer par poste" })).getByRole("button", { name: "Attaquants" }));
    await user.type(search, "zoé");
    expect(checkboxNames()).toEqual(["Sélectionner Zoé Attaque"]);

    await user.clear(search);
    await user.type(search, "abel");
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.getByText("Aucun joueur ne correspond à « abel » dans « Attaquants ».")).toBeInTheDocument();
  });

  it("une sélection masquée par une puce reste dans le récapitulatif et reste cochée", async () => {
    mockRoster(roster());
    const user = userEvent.setup();
    renderModal();
    await user.click(await screen.findByRole("checkbox", { name: "Sélectionner Abel Gardien" }));
    const group = screen.getByRole("group", { name: "Filtrer par poste" });
    await user.click(within(group).getByRole("button", { name: "Attaquants" }));
    expect(screen.getByText("1 titulaires · 0 remplaçants")).toBeInTheDocument();
    await user.click(within(group).getByRole("button", { name: "Gardiens" }));
    expect(screen.getByRole("checkbox", { name: "Sélectionner Abel Gardien" })).toBeChecked();
  });
});
