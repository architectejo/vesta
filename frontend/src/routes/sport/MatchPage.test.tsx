import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MyProfile, ClubPlayerListItem } from "../../api/clubs";
import type { MatchDetail } from "../../api/sport";
import { ToastProvider } from "../../design-system";
import { MatchPage } from "./MatchPage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn(), listClubPlayers: vi.fn() };
});

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, getMatch: vi.fn(), listEventIncidents: vi.fn(), publishMatchResult: vi.fn() };
});

vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return { ...actual, getMatchEquipment: vi.fn().mockResolvedValue({ lines: [] }) };
});

import { getMyProfile, listClubPlayers } from "../../api/clubs";
import { getMatchEquipment } from "../../api/logistics";
import { ApiError } from "../../api/client";
import { getMatch, listEventIncidents, publishMatchResult } from "../../api/sport";

function makeProfile(...roles: string[]): MyProfile {
  return {
    membership_id: 1,
    club: { id: 1, slug: "test", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    identity: {
      first_name: "Jean",
      last_name: "Coach",
      photo: null,
      email: "jean@example.com",
      phone: "",
      birth_date: null,
      weight_kg: null,
      height_cm: null,
    },
    position: "midfielder",
    position_label: "Milieu",
    position_detail: "",
    jersey_number: null,
    membership_status: "active",
    membership_status_label: "Inscrit",
    roles: roles.map((role) => ({ role, label: role })),
    email_notifications_enabled: true,
  };
}

function makeRoster(): ClubPlayerListItem[] {
  return [];
}

function makeMatch(overrides: Partial<MatchDetail> = {}): MatchDetail {
  return {
    id: 5,
    kind: "match",
    event_date: "2026-10-03",
    season_id: 1,
    is_locked: false,
    unlocked_by: null,
    unlocked_at: null,
    unlock_reason: "",
    kickoff_time: "15:00:00",
    opponent: "FC Espoir",
    match_type: "friendly",
    venue: "home",
    location: "",
    challenge_status: "n_a",
    is_composition_published: false,
    composition_published_at: null,
    attendances: [],
    attendance_counts: { present: 0, late: 0, excused: 0, not_marked: 0 },
    starters: [],
    substitutes: [],
    sheet: null,
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/matchs/5"]}>
          <Routes>
            <Route path="/matchs/:id" element={<MatchPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("MatchPage", () => {
  beforeEach(() => {
    vi.mocked(listClubPlayers).mockResolvedValue(makeRoster());
    vi.mocked(listEventIncidents).mockResolvedValue({ count: 0, next_offset: null, results: [] });
  });

  it("propose « Composer l'équipe » au Coach sans composition", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getMatch).mockResolvedValue(makeMatch());
    renderPage();
    // Deux boutons legitimes portent ce libellé (action d'en-tête et action
    // de l'état vide de la carte « Composition ») : on vérifie qu'au moins
    // un existe, sans figer lequel des deux l'emporte.
    expect((await screen.findAllByRole("button", { name: "Composer l'équipe" })).length).toBeGreaterThan(0);
  });

  it("n'affiche aucune action de gestion pour un simple joueur", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getMatch).mockResolvedValue(makeMatch());
    renderPage();
    expect(await screen.findByText("Club de test – FC Espoir")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Composer l'équipe" })).not.toBeInTheDocument();
  });

  it("n'appelle pas GET equipment pour un simple joueur (rôle non habilité)", async () => {
    vi.mocked(getMatchEquipment).mockClear();
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getMatch).mockResolvedValue(makeMatch());
    renderPage();
    expect(await screen.findByText("Club de test – FC Espoir")).toBeInTheDocument();
    expect(screen.queryByText("Équipements reçus")).not.toBeInTheDocument();
    expect(getMatchEquipment).not.toHaveBeenCalled();
  });

  it("charge les équipements pour le Coach", async () => {
    vi.mocked(getMatchEquipment).mockClear();
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getMatch).mockResolvedValue(makeMatch());
    renderPage();
    expect(await screen.findByText("Équipements reçus")).toBeInTheDocument();
    expect(getMatchEquipment).toHaveBeenCalledWith(5);
  });
});

describe("MatchPage : publication du résultat", () => {
  const sheet = { score_home: 2, score_away: 1, goals: [] } as unknown as MatchDetail["sheet"];
  const BUTTON = "Publier le résultat sur le fil";

  beforeEach(() => {
    vi.mocked(listClubPlayers).mockResolvedValue(makeRoster());
    vi.mocked(listEventIncidents).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(publishMatchResult).mockReset();
  });

  it("affiche le bouton au Coach quand le score est saisi et le résultat non publié", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getMatch).mockResolvedValue(makeMatch({ sheet, result_published: false }));
    renderPage();
    expect(await screen.findByRole("button", { name: BUTTON })).toBeInTheDocument();
  });

  it("affiche le bouton à l'assistant du Coach", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("assistant_coach"));
    vi.mocked(getMatch).mockResolvedValue(makeMatch({ sheet, result_published: false }));
    renderPage();
    expect(await screen.findByRole("button", { name: BUTTON })).toBeInTheDocument();
  });

  it("masque le bouton à un simple joueur, sans score, ou si déjà publié", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getMatch).mockResolvedValue(makeMatch({ sheet, result_published: false }));
    const first = renderPage();
    expect(await screen.findByText("Club de test – FC Espoir")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: BUTTON })).not.toBeInTheDocument();
    first.unmount();

    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getMatch).mockResolvedValue(makeMatch({ sheet: null, result_published: false }));
    const second = renderPage();
    expect(await screen.findByText("Club de test – FC Espoir")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: BUTTON })).not.toBeInTheDocument();
    second.unmount();

    vi.mocked(getMatch).mockResolvedValue(makeMatch({ sheet, result_published: true }));
    renderPage();
    expect(await screen.findByText("Résultat publié sur le fil")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: BUTTON })).not.toBeInTheDocument();
  });

  it("demande confirmation avant d'envoyer, puis affiche la mention", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getMatch)
      .mockResolvedValueOnce(makeMatch({ sheet, result_published: false }))
      .mockResolvedValue(makeMatch({ sheet, result_published: true }));
    vi.mocked(publishMatchResult).mockResolvedValue(makeMatch({ sheet, result_published: true }));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: BUTTON }));
    expect(screen.getByText(/Publier le résultat de ce match sur le fil du club \?/)).toBeInTheDocument();
    expect(publishMatchResult).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Publier" }));
    await waitFor(() => expect(publishMatchResult).toHaveBeenCalledWith(5));
    expect(await screen.findByText("Résultat publié sur le fil")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: BUTTON })).not.toBeInTheDocument();
  });

  it("affiche l'erreur 400 de l'API telle quelle", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getMatch).mockResolvedValue(makeMatch({ sheet, result_published: false }));
    vi.mocked(publishMatchResult).mockRejectedValue(
      new ApiError(400, { detail: "Le résultat de ce match est déjà publié." }),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: BUTTON }));
    await user.click(screen.getByRole("button", { name: "Publier" }));
    expect(await screen.findByText("Le résultat de ce match est déjà publié.")).toBeInTheDocument();
  });
});

describe("MatchPage — composition hors connexion (§4.1 bis)", () => {
  beforeEach(() => {
    vi.mocked(listClubPlayers).mockResolvedValue(makeRoster());
    vi.mocked(listEventIncidents).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
  });

  it("« Composer l'équipe » désactivé avec « Cette action nécessite une connexion. »", async () => {
    const onLine = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    vi.mocked(getMatch).mockResolvedValue(makeMatch());
    renderPage();

    // En-tête ET état vide : le bouton reste affiché, désactivé (jamais masqué).
    const buttons = await screen.findAllByRole("button", { name: "Composer l'équipe" });
    expect(buttons).toHaveLength(2);
    for (const button of buttons) expect(button).toBeDisabled();
    // Aide écrite et visible (pas un simple `title`) dans l'en-tête et l'état vide.
    expect(screen.getAllByText("Cette action nécessite une connexion.")).toHaveLength(2);
    for (const button of buttons) expect(button).not.toHaveAttribute("title");
    expect(document.getElementById("match-header-action-help")).toHaveTextContent(
      "Cette action nécessite une connexion.",
    );
    onLine.mockRestore();
  });

  it("« Publier la composition » et « Modifier la composition » désactivés hors connexion", async () => {
    const onLine = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const brief = { membership_id: 12, name: "Kevin Proto", jersey_number: 12, position: "midfielder", position_label: "Milieu", photo: null };
    vi.mocked(getMatch).mockResolvedValue(
      makeMatch({
        starters: [
          {
            id: 1,
            membership_id: 12,
            player: brief,
            role: "starter",
            role_label: "Titulaire",
            position: "midfielder",
            position_label: "Milieu",
            jersey_number: 12,
            no_longer_eligible: null,
          },
        ],
      }),
    );
    renderPage();

    const publish = await screen.findAllByRole("button", { name: "Publier la composition" });
    for (const button of publish) expect(button).toBeDisabled();
    expect(screen.getByRole("button", { name: "Modifier la composition" })).toBeDisabled();
    expect(document.getElementById("match-header-action-help")).toHaveTextContent(
      "Cette action nécessite une connexion.",
    );
    expect(document.getElementById("composition-action-help")).toHaveTextContent(
      "Cette action nécessite une connexion.",
    );
    for (const button of publish) expect(button).not.toHaveAttribute("title");
    onLine.mockRestore();
  });

  it("en ligne : « Composer l'équipe » reste actif", async () => {
    vi.mocked(getMatch).mockResolvedValue(makeMatch());
    renderPage();
    const buttons = await screen.findAllByRole("button", { name: "Composer l'équipe" });
    for (const button of buttons) expect(button).toBeEnabled();
  });
});

describe("MatchPage — composition devenue non conforme (§3 point 2)", () => {
  const brief = (id: number, name: string) => ({
    membership_id: id,
    name,
    jersey_number: id,
    position: "midfielder",
    position_label: "Milieu",
    photo: null,
  });
  const entry = (id: number, name: string, blocked: boolean) => ({
    id,
    membership_id: id,
    player: brief(id, name),
    role: "starter" as const,
    role_label: "Titulaire",
    position: "midfielder",
    position_label: "Milieu",
    jersey_number: id,
    no_longer_eligible: blocked
      ? { eligible: false, reason_code: "suspended", reason: "Suspendu : encore 1 match(s)" }
      : null,
  });

  beforeEach(() => {
    vi.mocked(listClubPlayers).mockResolvedValue(makeRoster());
    vi.mocked(listEventIncidents).mockResolvedValue({ count: 0, next_offset: null, results: [] });
  });

  it("Coach : publication désactivée avec l'aide « Retirez d'abord… », ligne avec cadenas et motif de l'API", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getMatch).mockResolvedValue(
      makeMatch({ starters: [entry(12, "Kevin Proto", false), entry(13, "Aimé Leurre", true)] }),
    );
    renderPage();

    const publish = await screen.findAllByRole("button", { name: "Publier la composition" });
    for (const button of publish) expect(button).toBeDisabled();
    expect(screen.getAllByText("Retirez d'abord les joueurs qui ne peuvent plus jouer.").length).toBeGreaterThan(0);
    expect(document.getElementById("match-header-action-help")).toHaveTextContent(
      "Retirez d'abord les joueurs qui ne peuvent plus jouer.",
    );
    expect(screen.getByText("N'est plus sélectionnable : Suspendu : encore 1 match(s)")).toBeInTheDocument();
    expect(screen.getAllByTestId("composition-lock")).toHaveLength(1);
    expect(screen.getByText(/1 joueur\(s\) de la composition ne peuvent plus jouer/)).toBeInTheDocument();
  });

  it("composition conforme : aucune aide de blocage", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getMatch).mockResolvedValue(makeMatch({ starters: [entry(12, "Kevin Proto", false)] }));
    renderPage();

    const publish = await screen.findAllByRole("button", { name: "Publier la composition" });
    for (const button of publish) expect(button).toBeEnabled();
    expect(screen.queryByText("Retirez d'abord les joueurs qui ne peuvent plus jouer.")).not.toBeInTheDocument();
  });

  it("hors staff : badge gris « Indisponible », sans motif ni cadenas (10.2 n° 16)", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getMatch).mockResolvedValue(
      makeMatch({
        is_composition_published: true,
        starters: [entry(12, "Kevin Proto", false), entry(13, "Aimé Leurre", true)],
      }),
    );
    renderPage();

    const badge = await screen.findByText("Indisponible");
    expect(badge.closest("span.rounded-full")?.className).toContain("bg-status-neutral-bg");
    expect(screen.queryByText(/Suspendu/)).not.toBeInTheDocument();
    expect(screen.queryByText(/N'est plus sélectionnable/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("composition-lock")).not.toBeInTheDocument();
  });
});
