import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client";
import type {
  PlayerCardListResponse,
  PlayerCardListRow,
  PlayerComparisonResponse,
  PlayerStatsResponse,
} from "../../../api/playerCards";

vi.mock("../../../api/playerCards", async () => {
  const actual = await vi.importActual<typeof import("../../../api/playerCards")>("../../../api/playerCards");
  return { ...actual, listPlayerCards: vi.fn(), getPlayerStats: vi.fn(), comparePlayers: vi.fn() };
});
vi.mock("../../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../../api/clubs")>("../../../api/clubs");
  return { ...actual, searchActiveClubPlayers: vi.fn().mockResolvedValue([]) };
});

import { comparePlayers, getPlayerStats, listPlayerCards } from "../../../api/playerCards";
import { PlayerCardsPage } from "./PlayerCardsPage";

function row(id: number, first: string, last: string, extra: Partial<PlayerCardListRow> = {}): PlayerCardListRow {
  return {
    membership_id: id,
    first_name: first,
    last_name: last,
    photo: null,
    jersey_number: id,
    position: "midfielder",
    position_label: "Milieu",
    position_detail: "",
    overall_rating: null,
    stats: {
      matches_played: 12,
      goals: 5,
      assists: 3,
      yellow_cards: 2,
      red_cards: 0,
      attendance_rate: 85,
      average_rating: "6.8",
    },
    recent_ratings: ["7.5", "6.0"],
    availability: null,
    ...extra,
  };
}

function page(rows: PlayerCardListRow[], extra: Partial<PlayerCardListResponse> = {}): PlayerCardListResponse {
  return {
    count: rows.length,
    limit: 24,
    offset: 0,
    has_more: false,
    season_id: 1,
    season_label: "2026-2027",
    seasons: [{ id: 1, label: "2026-2027", is_current: true }],
    can_see_availability: false,
    can_compare: true,
    results: rows,
    ...extra,
  };
}

const STATS: PlayerStatsResponse = {
  membership_id: 1,
  season_id: 1,
  season_label: "2026-2027",
  overall_rating: null,
  stats: row(1, "A", "B").stats,
  radar: {
    axes: [
      { key: "technical", label: "Technique", value: "6.0" },
      { key: "physical", label: "Physique", value: null },
      { key: "tactical", label: "Tactique", value: "7.0" },
    ],
  },
  recent_form: [{ date: "2026-11-08", event_type: "match", label: "Match contre Lions", rating: "7.5" }],
  attendance: { sessions_expected: 20, sessions_present: 17, late: 2, excused: 1, absent: 2, rate: 85, late_counts_as_absent: false },
  discipline: { cards: [], active_suspension: null },
  fitness: null,
  performance: null,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PlayerCardsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const originalMatchMedia = window.matchMedia;
function setDesktop(on: boolean): void {
  window.matchMedia = ((query: string) => ({
    matches: on && query.includes("min-width: 1024px"),
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

describe("PlayerCardsPage", () => {
  beforeEach(() => {
    vi.mocked(getPlayerStats).mockResolvedValue(STATS);
  });
  afterEach(() => {
    vi.clearAllMocks();
    window.matchMedia = originalMatchMedia;
  });

  it("liste les cartes avec la bande de statistiques, note globale « — » et sans donnée privée", async () => {
    vi.mocked(listPlayerCards).mockResolvedValue(page([row(1, "Aimé", "Kalonji"), row(2, "Jean", "Kabila")]));
    const { container } = renderPage();
    expect(await screen.findByRole("button", { name: /Voir la fiche détaillée de Aimé Kalonji/ })).toBeInTheDocument();
    expect(screen.getAllByText(/12 matchs · 5 buts · 3 passes/)).toHaveLength(2);
    expect(screen.getAllByText(/Dernières notes : 7,5 · 6,0/)).toHaveLength(2);
    expect(screen.getAllByText("Note globale : pas encore de donnée")).toHaveLength(2);
    expect(screen.getByText(/2026-2027 · 2 joueurs/)).toBeInTheDocument();
    const text = container.textContent ?? "";
    for (const forbidden of [/téléphone/i, /poids/i, /taille/i, /solde/i, /dette/i, /diagnostic/i]) {
      expect(text).not.toMatch(forbidden);
    }
  });

  it("recherche, poste, et tri « Buts » envoient les bons paramètres", async () => {
    vi.mocked(listPlayerCards).mockResolvedValue(page([row(1, "Aimé", "Kalonji")]));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/Aimé Kalonji/);

    await user.type(screen.getByRole("searchbox", { name: "Nom ou numéro" }), "kal");
    await waitFor(() =>
      expect(vi.mocked(listPlayerCards)).toHaveBeenLastCalledWith(expect.objectContaining({ search: "kal" })),
    );
    await user.click(screen.getByRole("button", { name: "Défenseur" }));
    await waitFor(() =>
      expect(vi.mocked(listPlayerCards)).toHaveBeenLastCalledWith(expect.objectContaining({ position: "defender" })),
    );
    await user.click(screen.getByRole("button", { name: "Trier : Nom" }));
    await user.click(screen.getByRole("button", { name: "Buts" }));
    await waitFor(() =>
      expect(vi.mocked(listPlayerCards)).toHaveBeenLastCalledWith(expect.objectContaining({ ordering: "-goals" })),
    );
  });

  it("« Voir plus » ajoute la page suivante sans doublon", async () => {
    vi.mocked(listPlayerCards)
      .mockResolvedValueOnce(page([row(1, "Aimé", "Kalonji"), row(2, "Jean", "Kabila")], { count: 3, has_more: true, limit: 2 }))
      .mockResolvedValueOnce(page([row(2, "Jean", "Kabila"), row(3, "Paul", "Makasi")], { count: 3, offset: 2, limit: 2 }));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/Aimé Kalonji/);
    expect(screen.getByText("2 sur 3 joueurs")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Voir plus" }));
    await screen.findByRole("button", { name: /Paul Makasi/ });
    expect(screen.getAllByRole("button", { name: /Jean Kabila/ })).toHaveLength(1);
    expect(vi.mocked(listPlayerCards)).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 2 }));
  });

  it("joueur ordinaire : pas de filtre de disponibilité, pas de badge ; staff : familles affichées sans dette nommée", async () => {
    vi.mocked(listPlayerCards).mockResolvedValue(page([row(1, "Aimé", "Kalonji")]));
    const user = userEvent.setup();
    const first = renderPage();
    await screen.findByText(/Aimé Kalonji/);
    await user.click(screen.getByRole("button", { name: "Filtres" }));
    expect(screen.queryByText("Disponibilité")).not.toBeInTheDocument();
    expect(screen.queryByText("Indisponible")).not.toBeInTheDocument();
    first.unmount();

    vi.mocked(listPlayerCards).mockResolvedValue(
      page(
        [
          row(1, "Aimé", "Kalonji", { availability: { label: "Indisponible", family: "unavailable" } }),
          row(2, "Jean", "Kabila", { availability: { label: "Suspendu : encore 2 match(s).", family: "suspension" } }),
        ],
        { can_see_availability: true },
      ),
    );
    renderPage();
    await screen.findByText("Indisponible");
    expect(screen.getByText(/Suspendu · encore 2 match\(s\)\./)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Filtres" }));
    expect(screen.getByText("Disponibilité")).toBeInTheDocument();
  });

  it("valeurs nulles : « — » et jamais « 0 » inventé", async () => {
    vi.mocked(listPlayerCards).mockResolvedValue(
      page([row(1, "Aimé", "Kalonji", { stats: { ...row(1, "A", "B").stats, attendance_rate: null, average_rating: null }, recent_ratings: [] })]),
    );
    renderPage();
    await screen.findByText(/Aimé Kalonji/);
    expect(screen.getByText(/présence —\s*· note —/)).toBeInTheDocument();
    expect(screen.queryByText(/Dernières notes/)).not.toBeInTheDocument();
  });

  it("états : vide filtré, erreur avec « Réessayer », 400 de filtre affiché", async () => {
    vi.mocked(listPlayerCards).mockResolvedValueOnce(page([]));
    const first = renderPage();
    expect(await screen.findByText("Aucun joueur dans le club pour l'instant.")).toBeInTheDocument();
    first.unmount();

    vi.mocked(listPlayerCards).mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(page([row(1, "Aimé", "Kalonji")]));
    const user = userEvent.setup();
    const second = renderPage();
    await user.click(await screen.findByRole("button", { name: "Réessayer" }));
    expect(await screen.findByText(/Aimé Kalonji/)).toBeInTheDocument();
    second.unmount();

    vi.mocked(listPlayerCards).mockRejectedValue(
      new ApiError(400, { detail: "Le filtre de disponibilité est réservé au staff du club." }),
    );
    renderPage();
    expect(await screen.findByText("Le filtre de disponibilité est réservé au staff du club.")).toBeInTheDocument();
  });

  it("mobile : toucher une carte ouvre la fiche avec radar partiel, forme et présences", async () => {
    vi.mocked(listPlayerCards).mockResolvedValue(page([row(1, "Aimé", "Kalonji")]));
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: /Voir la fiche détaillée de Aimé Kalonji/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Fiche du joueur" })).toBeInTheDocument();
    expect(await within(dialog).findByText("Radar des attributs", { selector: "h3" })).toBeInTheDocument();
    expect(within(dialog).getByText(/17 séances sur 20 · 85\s%/)).toBeInTheDocument();
    expect(within(dialog).getByText("Aucun carton cette saison.")).toBeInTheDocument();
    expect(within(dialog).queryByText("Aptitude")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Tests de performance")).not.toBeInTheDocument();
  });

  it("ordinateur : la carte et ses statistiques sont côte à côte, sans modale", async () => {
    setDesktop(true);
    vi.mocked(listPlayerCards).mockResolvedValue(page([row(1, "Aimé", "Kalonji"), row(2, "Jean", "Kabila")]));
    renderPage();
    expect(await screen.findByText("Forme récente")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("Saison 2026-2027")).toBeInTheDocument();
    expect(vi.mocked(getPlayerStats)).toHaveBeenCalledWith(1, 1);
  });

  it("aptitude, suspension et tests de performance seulement s'ils sont servis", async () => {
    setDesktop(true);
    vi.mocked(getPlayerStats).mockResolvedValue({
      ...STATS,
      discipline: {
        cards: [],
        active_suspension: { reason: "red_card", reason_label: "Carton rouge", matches_total: 3, matches_served: 1, matches_remaining: 2, label: "Suspendu : encore 2 match(s)." },
      },
      fitness: { status: "unfit", label: "Inapte", return_date: "2027-03-01" },
      performance: [{ test: { id: 1, name: "Sprint 30 m" }, best: { date: "2026-10-01", display: "4,52 s" } }],
    });
    vi.mocked(listPlayerCards).mockResolvedValue(page([row(1, "Aimé", "Kalonji")]));
    renderPage();
    expect(await screen.findByText("Aptitude")).toBeInTheDocument();
    expect(screen.getByText("Inapte")).toBeInTheDocument();
    expect(screen.getByText(/retour prévu le/)).toBeInTheDocument();
    expect(screen.getByText(/Suspendu · encore 2 match\(s\)\./)).toBeInTheDocument();
    expect(screen.getByText("Tests de performance")).toBeInTheDocument();
  });

  it("erreur de statistiques : message avec le prénom et « Réessayer »", async () => {
    setDesktop(true);
    vi.mocked(getPlayerStats).mockRejectedValue(new Error("boom"));
    vi.mocked(listPlayerCards).mockResolvedValue(page([row(1, "Aimé", "Kalonji")]));
    renderPage();
    expect(await screen.findByText("Impossible de charger les statistiques de Aimé.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });

  it("mode tableau : colonnes et lignes", async () => {
    vi.mocked(listPlayerCards).mockResolvedValue(page([row(1, "Aimé", "Kalonji")]));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/Aimé Kalonji/);
    await user.click(screen.getByRole("button", { name: "Tableau" }));
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("columnheader", { name: /Passes décisives/ })).toBeInTheDocument();
    expect(within(table).getByText("Aimé Kalonji")).toBeInTheDocument();
    expect(within(table).getByText("2 jaunes, 0 rouge")).toBeInTheDocument();
  });

  it("comparaison : joueur du club, joueur public sans radar, joueur non consultable", async () => {
    vi.mocked(listPlayerCards).mockResolvedValue(
      page([row(1, "Aimé", "Kalonji"), row(2, "Jean", "Kabila"), row(3, "Paul", "Makasi")]),
    );
    const base = row(1, "A", "B");
    const response: PlayerComparisonResponse = {
      count: 3,
      results: [
        {
          membership_id: 1, first_name: "Aimé", last_name: "Kalonji", photo: null, jersey_number: 1, position: "midfielder",
          position_label: "Milieu", consultable: true, scope: "club", club: { id: 1, name: "Club local", logo: null },
          season_id: 1, season_label: "2026-2027", overall_rating: null, stats: base.stats, radar: STATS.radar,
        },
        {
          membership_id: 2, first_name: "Jean", last_name: "Kabila", photo: null, jersey_number: 2, position: "midfielder",
          position_label: "Milieu", consultable: true, scope: "public", club: { id: 9, name: "Club voisin", logo: null },
          season_id: 5, season_label: "2026", overall_rating: null, stats: base.stats, radar: null,
        },
        { membership_id: 3, consultable: false, detail: "Ce joueur n'est plus consultable." },
      ],
    };
    vi.mocked(comparePlayers).mockResolvedValue(response);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/Aimé Kalonji/);
    await user.click(screen.getByRole("button", { name: "Comparer" }));
    for (const name of ["Aimé Kalonji", "Jean Kabila", "Paul Makasi"]) {
      await user.click(screen.getByRole("checkbox", { name: `Comparer ${name}` }));
    }
    await user.click(screen.getByRole("button", { name: "Comparer (3)" }));
    const dialog = await screen.findByRole("dialog");
    expect(vi.mocked(comparePlayers)).toHaveBeenCalledWith([1, 2, 3]);
    expect(await within(dialog).findByText("Données publiques")).toBeInTheDocument();
    expect(within(dialog).getAllByText("Ce joueur n'est plus consultable.").length).toBeGreaterThan(0);
    expect(within(dialog).getByText(/Jean Kabila — attributs non publics/)).toBeInTheDocument();
    expect(within(dialog).getByText("Club voisin")).toBeInTheDocument();
  });

  it("n'émet aucune erreur console", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(listPlayerCards).mockResolvedValue(page([row(1, "Aimé", "Kalonji")]));
    renderPage();
    await screen.findByText(/Aimé Kalonji/);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
