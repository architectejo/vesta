import { test, expect, type Page, type Locator } from "@playwright/test";
import { loginAs } from "./support/auth";
import {
  AVAILABLE_UNMARKED_PLAYERS,
  DEMO,
  DRAFT_PLAN_NAME,
  PERFORMANCE_TESTS,
  PUBLISHED_PLAN_NAME,
  TODAY_SESSION_ID,
  UNAVAILABLE_PLAYERS,
} from "./support/demo";

/**
 * Série 5 de tests fonctionnels (tâche B2 de MESSAGES.md), contre les vrais
 * serveurs de dev et la base locale de DÉMONSTRATION (club fictif
 * « Club Démo »). Viewport 360 px (CLAUDE.md §2.16).
 *
 * Couvre : tableau de bord du Président / VP (`club-tableau-de-bord-bureau.md`),
 * pointage groupé (`sport-pointage-selection-multiple.md`), photos des pions
 * (`sport-vestiaire.md` §9), statistiques de séance et page « Entraînements »
 * (`sport-statistiques-seance.md` parties A et B), tests de performance et
 * chrono, y compris la sauvegarde locale « Un chrono non enregistré a été
 * retrouvé » (partie C), page des cartes (`club-cartes-joueurs.md`) et
 * Vestiaire avec l'onglet « Plans » (`sport-vestiaire.md` §10).
 *
 * Certaines étapes ÉCRIVENT dans la base de démonstration (pointage groupé,
 * mesures du chrono) : elles choisissent à chaque exécution des joueurs
 * encore non pointés, pour rester rejouables tant qu'il en reste.
 */
// Ordre d'exécution : celui du fichier (workers: 1, fullyParallel: false),
// sans mode « serial » pour qu'un échec n'empêche pas les parcours suivants.

const SESSION_URL = `/seances/${TODAY_SESSION_ID}`;

async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width, "aucun défilement horizontal à 360 px").toBeLessThanOrEqual(360);
}

async function openSessionTab(page: Page, tab: "Pointage" | "Équipes A/B" | "Bilan"): Promise<void> {
  await page.goto(SESSION_URL);
  await expect(page.getByRole("heading", { name: /Séance du/ })).toBeVisible();
  await page.getByRole("tab", { name: tab }).click();
}

/** Ligne du pointage d'un joueur (vue « Pointage »). */
function pointageRow(page: Page, name: string): Locator {
  return page.locator("li").filter({ has: page.getByText(name, { exact: true }) });
}

/** Renvoie les joueurs de `candidates` encore non pointés (filtre « Non pointés » par défaut). */
async function unmarkedAmong(page: Page, candidates: readonly string[]): Promise<string[]> {
  const found: string[] = [];
  for (const name of candidates) {
    if ((await pointageRow(page, name).count()) > 0) found.push(name);
  }
  return found;
}

// ---------------------------------------------------------------------------
// 1. Tableau de bord du Président et du Vice-président
// ---------------------------------------------------------------------------

test.describe("Tableau de bord du club", () => {
  test("president_sees_board_dashboard_cards_without_horizontal_scroll", async ({ page }) => {
    await loginAs(page, DEMO.president);
    await page.goto("/tableau-de-bord");
    await expect(page.getByRole("heading", { name: "Tableau de bord du club" })).toBeVisible();
    for (const title of ["Présences", "Cotisations", "Situation de l'effectif", "Aptitude de l'effectif", "Prochaines échéances"]) {
      await expect(page.getByText(title, { exact: true }).first()).toBeVisible();
    }
    await expect(page.getByText(/Mis à jour à \d{2}:\d{2}/)).toBeVisible();
    await expectNoHorizontalScroll(page);
  });

  test("board_dashboard_shows_page_banner_when_an_unjustified_expense_blocks_releases", async ({ page }) => {
    // Fiche §3 « Bandeaux » : dépense non justifiée qui bloque les libérations
    // (alerte rouge, CDC 4.5.2). La base de démo a 1 dépense non justifiée
    // (`expenses_by_category.release_blocked = true`).
    await loginAs(page, DEMO.president);
    await page.goto("/tableau-de-bord");
    await expect(page.getByRole("heading", { name: "Tableau de bord du club" })).toBeVisible();
    await expect(
      page.getByText("Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée.").first(),
    ).toBeVisible();
  });

  test("fitness_card_and_modal_never_show_a_diagnosis_and_state_return_date", async ({ page }) => {
    await loginAs(page, DEMO.president);
    await page.goto("/tableau-de-bord");
    await expect(page.getByText("Le détail médical n'est visible que par le Médecin et le joueur.").first()).toBeVisible();
    // Chaque inapte porte sa date de retour, ou l'indication qu'elle n'est pas fixée.
    await expect(page.getByText(/Victor Echant · (retour prévu le|date de retour non précisée)/)).toBeVisible();
    await page.getByRole("button", { name: "Voir le détail : Aptitude de l'effectif" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Victor Echant").first()).toBeVisible();
    await expect(dialog.getByText(/diagnostic\s*:/i)).toHaveCount(0);
    await expect(dialog.getByRole("link", { name: /dossier médical/i })).toHaveCount(0);
  });

  test("board_dashboard_switches_to_season_period", async ({ page }) => {
    await loginAs(page, DEMO.president);
    await page.goto("/tableau-de-bord");
    await page.getByRole("radio", { name: "Saison" }).or(page.getByRole("button", { name: "Saison", exact: true })).first().click();
    await expect(page).toHaveURL(/saison=/);
    await expect(page.getByText(/Saison/).first()).toBeVisible();
    await expect(page.getByText("Impossible de charger le tableau de bord.")).toHaveCount(0);
  });

  test("vice_president_can_open_board_dashboard", async ({ page }) => {
    await loginAs(page, DEMO.vicePresident);
    await page.goto("/tableau-de-bord");
    await expect(page.getByText("Présences", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Cette page est réservée au Président et au Vice-président.")).toHaveCount(0);
  });

  for (const [role, email] of [
    ["coach", DEMO.coach],
    ["treasurer", DEMO.treasurer],
    ["player", DEMO.player],
  ] as const) {
    test(`${role}_is_refused_board_dashboard_and_has_no_menu_entry`, async ({ page }) => {
      await loginAs(page, email);
      await page.goto("/tableau-de-bord");
      await expect(page.getByText("Cette page est réservée au Président et au Vice-président.")).toBeVisible();
      await expect(page.getByRole("link", { name: "Retour à l'accueil" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Tableau de bord du club" })).toHaveCount(0);
    });
  }

  test("board_attendance_rate_equals_trainings_page_rate_for_the_same_session", async ({ page }) => {
    // Fiche §9 : « un taux de présence affiché ici doit être égal à celui de
    // la page Entraînements pour la même période (critère d'acceptation à
    // tester) » ; définition commune `sport-statistiques-seance.md` A4.1 :
    // taux « arrondi à l'unité ».
    await loginAs(page, DEMO.president);
    await page.goto("/entrainements");
    // `\s` : le format français insère une espace insécable avant « % ».
    const trainingsLine = page.getByText(/Dernière séance\s:\s\d+\s%/).first();
    await expect(trainingsLine).toBeVisible();
    const trainingsRate = (await trainingsLine.innerText()).match(/(\d+)\s%/)![1];
    await page.goto("/tableau-de-bord");
    const boardLine = page.getByText(/Dernière séance\s[\d,]+\s%/).first();
    await expect(boardLine).toBeVisible();
    const boardRate = (await boardLine.innerText()).match(/Dernière séance\s([\d,]+)\s%/)![1];
    expect(boardRate, "taux de la dernière séance : tableau de bord = Entraînements").toBe(trainingsRate);
  });
});

// ---------------------------------------------------------------------------
// 2. Pointage groupé
// ---------------------------------------------------------------------------

test.describe("Pointage groupé", () => {
  test("player_without_attendance_role_has_no_select_mode_nor_arrival_button", async ({ page }) => {
    await loginAs(page, DEMO.player);
    await openSessionTab(page, "Pointage");
    await expect(page.getByRole("button", { name: "Sélectionner" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Arrivé" })).toHaveCount(0);
  });

  test("unavailable_unmarked_player_shows_neutral_badge_without_reason", async ({ page }) => {
    // sport-seance.md §3.1 point 3 : un joueur bloqué « peut être pointé ; un
    // petit badge de statut rappelle qu'il ne pourra pas être réparti ».
    // L'effectif ne sert que le booléen `is_unavailable` (10.2 n° 16) :
    // « Indisponible », jamais le motif.
    await loginAs(page, DEMO.coach);
    await openSessionTab(page, "Pointage");
    const blocked = await unmarkedAmong(page, UNAVAILABLE_PLAYERS);
    test.skip(blocked.length === 0, "Tous les joueurs indisponibles sont déjà pointés dans la base de démo.");
    const row = pointageRow(page, blocked[0]);
    await expect(row.getByText("Indisponible")).toBeVisible();
    await expect(row.getByText(/dette|suspendu|inapte/i)).toHaveCount(0);
  });

  test("captain_bulk_mode_has_no_excuse_action_nor_common_time", async ({ page }) => {
    await loginAs(page, DEMO.captain);
    await openSessionTab(page, "Pointage");
    await page.getByRole("button", { name: "Sélectionner" }).click();
    await expect(page.getByRole("button", { name: /Tout cocher \(\d+\)/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Absent excusé" })).toHaveCount(0);
    const arrive = page.getByRole("button", { name: /Pointer l'arrivée \(0\)/ });
    await expect(arrive).toBeDisabled();
    const candidates = await unmarkedAmong(page, AVAILABLE_UNMARKED_PLAYERS);
    test.skip(candidates.length === 0, "Plus aucun joueur disponible non pointé.");
    await page.getByRole("checkbox", { name: `Sélectionner ${candidates[0]}` }).check();
    await page.getByRole("button", { name: /Pointer l'arrivée \(1\)/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/Heure enregistrée/)).toBeVisible();
    await expect(dialog.getByText("Indiquer une autre heure d'arrivée")).toHaveCount(0);
    await dialog.getByRole("button", { name: "Annuler" }).click();
    await page.getByRole("button", { name: "Terminer" }).click();
    await expect(page.getByRole("button", { name: "Sélectionner" })).toBeVisible();
  });

  test("coach_check_all_counts_only_visible_rows_after_search", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await openSessionTab(page, "Pointage");
    await page.getByRole("button", { name: "Sélectionner" }).click();
    const all = page.getByRole("button", { name: /Tout cocher \((\d+)\)/ });
    const total = Number((await all.innerText()).match(/\((\d+)\)/)![1]);
    const counter = await page.getByText(/Non pointés \d+/).first().innerText();
    expect(total).toBe(Number(counter.match(/(\d+)/)![1]));
    await page.getByPlaceholder("Nom ou numéro").fill("Echant");
    await expect(page.getByRole("button", { name: /Tout cocher \((0|1)\)/ })).toBeVisible();
    await page.getByRole("button", { name: "Terminer" }).click();
  });

  test("coach_bulk_marks_one_available_and_one_unavailable_player_with_blocked_warning", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await openSessionTab(page, "Pointage");
    const blocked = await unmarkedAmong(page, UNAVAILABLE_PLAYERS);
    const available = await unmarkedAmong(page, AVAILABLE_UNMARKED_PLAYERS);
    test.skip(blocked.length === 0 || available.length === 0, "Plus assez de joueurs non pointés dans la base de démo.");
    const [first, second] = [available[0], blocked[0]];

    await page.getByRole("button", { name: "Sélectionner" }).click();
    await page.getByRole("checkbox", { name: `Sélectionner ${first}` }).check();
    await page.getByRole("checkbox", { name: `Sélectionner ${second}` }).check();
    await expect(page.getByText("2 sélectionnés").or(page.getByText(/2 sélectionné/)).first()).toBeVisible();
    await page.getByRole("button", { name: /Pointer l'arrivée \(2\)/ }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/Heure enregistrée : \d{2}:\d{2}/)).toBeVisible();
    // sport-pointage-selection-multiple.md §4.1 : « {k} de ces joueurs ne
    // pourront pas être placés dans une équipe. » (aucun motif).
    await expect(dialog.getByText("1 de ces joueurs ne pourront pas être placés dans une équipe.")).toBeVisible();
    await expect(dialog.getByText("Indiquer une autre heure d'arrivée")).toBeVisible();
    await dialog.getByRole("button", { name: "Pointer (2)" }).click();

    await expect(page.getByText(/2 joueurs pointés/).first()).toBeVisible();
    await page.getByRole("button", { name: "Tous" }).click();
    await expect(pointageRow(page, first).getByText(/Présent|En retard/).first()).toBeVisible();
    await expect(pointageRow(page, second).getByText(/Présent|En retard/).first()).toBeVisible();

    // Le joueur bloqué pointé n'est jamais réparti : « Ne peuvent pas jouer ».
    await page.getByRole("tab", { name: "Équipes A/B" }).click();
    await expect(page.getByText(/Ne peuvent pas jouer \(\d+\)/)).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 3. Photos des pions
// ---------------------------------------------------------------------------

test.describe("Photos des pions", () => {
  test("pitch_pins_with_photo_keep_40px_box_and_images_never_capture_gestures", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await openSessionTab(page, "Équipes A/B");
    const pinImages = page.locator("img[alt='']");
    await expect(pinImages.first()).toBeVisible();
    const report = await pinImages.evaluateAll((imgs) =>
      imgs.map((img) => {
        const button = img.closest("button");
        const box = (button?.firstElementChild ?? img).getBoundingClientRect();
        const style = getComputedStyle(img);
        return {
          draggable: img.getAttribute("draggable"),
          pointerEvents: style.pointerEvents,
          userSelect: style.userSelect,
          inButtonWithLabel: Boolean(button?.getAttribute("aria-label")),
          circle: Math.round(img.parentElement!.getBoundingClientRect().width),
          box: Math.round(box.width),
        };
      }),
    );
    for (const pin of report) {
      expect(pin.draggable).toBe("false");
      expect(pin.pointerEvents).toBe("none");
      expect(pin.userSelect).toBe("none");
      expect(pin.inButtonWithLabel, "image décorative dans un bouton qui porte aria-label").toBe(true);
      expect(pin.circle).toBe(40);
    }
    await expectNoHorizontalScroll(page);
  });

  test("blocked_pin_offers_no_move_action", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await openSessionTab(page, "Équipes A/B");
    const zone = page.locator("div, section").filter({ has: page.getByText(/^Ne peuvent pas jouer \(\d+\)$/) }).last();
    test.skip((await page.getByText(/^Ne peuvent pas jouer \(\d+\)$/).count()) === 0, "Aucun joueur bloqué pointé.");
    await zone.getByRole("button").first().click();
    const panel = page.getByRole("dialog");
    await expect(panel.getByText(/ne peut pas jouer/)).toBeVisible();
    await expect(panel.getByRole("button", { name: /Passer en (A|B)/ })).toHaveCount(0);
  });

  test("locker_room_pitch_view_shows_photos_and_no_unavailability_reason", async ({ page }) => {
    await loginAs(page, DEMO.player);
    await page.goto("/vestiaire");
    await expect(page.getByRole("heading", { name: "Vestiaire du jour" })).toBeVisible();
    await page.getByRole("radio", { name: "Terrain" }).or(page.getByRole("button", { name: "Terrain", exact: true })).first().click();
    // Lecture seule : les photos servies par l'API (URL absolue) sont affichées.
    const photos = page.locator("main img[src*='/media/']");
    await expect(photos.first()).toBeVisible();
    for (const img of await photos.all()) {
      expect(await img.evaluate((el) => (el as HTMLImageElement).naturalWidth > 0)).toBe(true);
    }
    await expect(page.getByText(/En dette|Suspendu ·|Inapte ·/)).toHaveCount(0);
    await expectNoHorizontalScroll(page);
  });
});

// ---------------------------------------------------------------------------
// 4. Statistiques de séance et page « Entraînements »
// ---------------------------------------------------------------------------

test.describe("Statistiques de séance", () => {
  test("coach_bilan_shows_presence_and_coach_notes_with_consistent_counters", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await openSessionTab(page, "Bilan");
    await expect(page.getByText("Taux de présence").first()).toBeVisible();
    await expect(page.getByText("Notes du Coach").first()).toBeVisible();
    await expect(page.getByText("Mesures de la séance")).toBeVisible();
    const attendance = await page.evaluate(async (id) => {
      const access = sessionStorage.getItem("vesta:access");
      const res = await fetch(`/api/v1/sport/sessions/${id}/stats/`, { headers: { Authorization: `Bearer ${access}` } });
      return (await res.json()).attendance;
    }, TODAY_SESSION_ID);
    // A4.1 : « les quatre compteurs font toujours la somme des attendus ».
    expect(attendance.present + attendance.late + attendance.absent + attendance.excused).toBe(attendance.expected);
    await expect(page.getByText(`${attendance.rate} %`).first()).toBeVisible();
    await expectNoHorizontalScroll(page);
  });

  test("player_bilan_hides_team_coach_notes", async ({ page }) => {
    // A3 : les coéquipiers ne voient ni moyenne d'équipe ni classement.
    await loginAs(page, DEMO.player);
    await openSessionTab(page, "Bilan");
    await expect(page.getByText("Taux de présence").first()).toBeVisible();
    await expect(page.getByText("Meilleures notes")).toHaveCount(0);
    await expect(page.getByText("Notes les plus faibles")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Mesurer" })).toHaveCount(0);
  });

  test("trainings_page_staff_and_player_views", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await page.goto("/entrainements");
    await expect(page.getByRole("heading", { name: "Entraînements" })).toBeVisible();
    await expect(page.getByText("Note moyenne des séances")).toBeVisible();
    await expect(page.getByText("Les plus assidus")).toBeVisible();
    await expectNoHorizontalScroll(page);

    await loginAs(page, DEMO.player);
    await page.goto("/entrainements");
    await expect(page.getByText("Mes notes")).toBeVisible();
    await expect(page.getByText("Note moyenne des séances")).toHaveCount(0);
    await expect(page.getByText("Les plus assidus")).toHaveCount(0);
    await expect(page.getByText(/Mon assiduité/)).toBeVisible();
  });

  test("trainings_page_session_row_opens_read_only_session_statistics", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await page.goto("/entrainements");
    await page.getByRole("button", { name: /^jeu\. 26 nov\./i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    // L'écran « Entraînements » ouvre une modale « Séance du … » consacrée
    // aux statistiques (l'Espace coach et son onglet « Statistiques » n'ont
    // pas d'entrée de menu) ; le chemin vers la page passe par « Ouvrir la séance ».
    await expect(dialog.getByRole("heading", { name: /Séance du jeudi 26 novembre/ })).toBeVisible();
    await expect(dialog.getByText("Taux de présence").first()).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Ouvrir la séance" })).toBeVisible();
    // A5.1 : lecture seule, aucun bouton « Évaluer » ni « Mesurer ».
    await expect(dialog.getByRole("button", { name: "Mesurer" })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Évaluer les joueurs" })).toHaveCount(0);
  });

  test("past_sessions_are_shown_locked_on_trainings_page", async ({ page }) => {
    // CDC 4.7 : une séance se verrouille à minuit. Les séances de septembre
    // doivent apparaître « Verrouillée ».
    await loginAs(page, DEMO.coach);
    await page.goto("/entrainements");
    const row = page.locator("li").filter({ hasText: /mer\. 9 sept\./i }).first();
    await expect(row).toBeVisible();
    await expect(row.getByText("Verrouillée")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 5. Tests de performance et chrono
// ---------------------------------------------------------------------------

async function openMeasure(page: Page, testName: string, players: string[]): Promise<Locator> {
  await openSessionTab(page, "Bilan");
  await page.getByRole("button", { name: "Mesurer" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("radio", { name: new RegExp(testName) }).first().click();
  await dialog.getByRole("radio", { name: "Chronomètre" }).or(dialog.getByRole("button", { name: "Chronomètre" })).first().click();
  for (const name of players) {
    await dialog.getByRole("checkbox", { name: new RegExp(name) }).check();
  }
  await dialog.getByRole("button", { name: "Commencer" }).click();
  await expect(dialog.getByText(/00:00,00/)).toBeVisible();
  return dialog;
}

test.describe("Tests de performance et chrono", () => {
  test("staff_sees_all_active_tests_and_player_sees_only_his_own", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await page.goto("/entrainements");
    for (const name of PERFORMANCE_TESTS) {
      await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
    }
    await page.getByText("Sprint 30 m", { exact: true }).first().click();
    await expect(page.getByRole("dialog").getByText(/Classement/).first()).toBeVisible();
    await page.keyboard.press("Escape");

    await loginAs(page, DEMO.player);
    await page.goto("/entrainements");
    await expect(page.getByText("Mes tests")).toBeVisible();
    await expect(page.getByText("Meilleur de la saison")).toHaveCount(0);
  });

  test("coach_measures_two_players_with_group_stopwatch_and_sends_results", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    const dialog = await openMeasure(page, "Sprint 30 m", ["Cédric Testc", "Fabrice Fauxf"]);
    await dialog.getByRole("button", { name: "Départ", exact: true }).click();
    // Temps plausible sur 30 m (~4,3 s) : un temps trop court créerait un
    // résultat aberrant (> 45 km/h) dans la base de démonstration.
    await page.waitForTimeout(4300);
    await dialog.getByRole("button", { name: "Arrêter Cédric Testc" }).click();
    await page.waitForTimeout(300);
    await dialog.getByRole("button", { name: "Arrêter Fabrice Fauxf" }).click();
    await expect(dialog.getByText("Chrono terminé")).toBeVisible();
    await expect(dialog.getByText(/km\/h/).first()).toBeVisible();
    // Pied du chrono : « Enregistrer ({n}) » (sport-statistiques-seance.md C6.2).
    await dialog.getByRole("button", { name: "Enregistrer (2)" }).click();
    const confirm = page.getByRole("dialog").filter({ hasText: /Envoyer 2 mesures/ });
    await confirm.getByRole("button", { name: "Envoyer les mesures" }).click();
    await expect(page.getByText(/2 (résultats|mesures) enregistré/).first()).toBeVisible();
  });

  test("unsaved_stopwatch_is_found_again_after_reload_and_can_be_resumed_then_abandoned", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    const dialog = await openMeasure(page, "Sprint 30 m", ["Gérard Simulég"]);
    await dialog.getByRole("button", { name: "Départ", exact: true }).click();
    await page.waitForTimeout(1500);
    // Le téléphone « s'éteint » : rechargement de la page sans enregistrer.
    await page.reload();
    const banner = page.getByText(/Un chrono non enregistré a été retrouvé \(Sprint 30 m, \d{2}:\d{2}\)\./);
    await expect(banner).toBeVisible();
    await page.getByRole("button", { name: "Reprendre" }).click();
    const resumed = page.getByRole("dialog");
    await expect(resumed.getByText(/Chronomètre : Sprint 30 m/)).toBeVisible();
    await expect(resumed.getByRole("button", { name: "Arrêter Gérard Simulég" })).toBeVisible();
    // Le temps a continué pendant l'extinction (horodatage, pas un compteur).
    const shown = await resumed.getByText(/\d{2}:\d{2},\d{2}/).first().innerText();
    const seconds = Number(shown.split(":")[1].replace(",", "."));
    expect(seconds).toBeGreaterThanOrEqual(1.5);
    // Fermeture : confirmation d'abandon (C6.2), puis plus aucune sauvegarde.
    await page.keyboard.press("Escape");
    const confirm = page.getByRole("dialog").filter({ hasText: "Abandonner ces mesures ?" });
    await confirm.getByRole("button", { name: "Abandonner" }).click();
    await expect(confirm).toHaveCount(0);
    // Retour explicite sur la séance (la fermeture peut faire reculer
    // l'historique en dev, voir le compte rendu de la série 5).
    await page.goto(SESSION_URL);
    await expect(page.getByRole("heading", { name: /Séance du/ })).toBeVisible();
    await expect(page.getByText(/Un chrono non enregistré a été retrouvé/)).toHaveCount(0);
  });

  test("unsaved_stopwatch_banner_abandon_clears_the_local_backup", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    const dialog = await openMeasure(page, "Sprint 30 m", ["Igor Modèlei"]);
    await dialog.getByRole("button", { name: "Départ", exact: true }).click();
    await page.waitForTimeout(1200);
    await page.reload();
    await expect(page.getByText(/Un chrono non enregistré a été retrouvé/)).toBeVisible();
    await page.getByRole("button", { name: "Abandonner" }).first().click();
    const confirm = page.getByRole("dialog").filter({ hasText: "Abandonner ces mesures ?" });
    await confirm.getByRole("button", { name: "Abandonner" }).click();
    await expect(page.getByText(/Un chrono non enregistré a été retrouvé/)).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("heading", { name: /Séance du/ })).toBeVisible();
    await expect(page.getByText(/Un chrono non enregistré a été retrouvé/)).toHaveCount(0);
  });

  test("chrono_backup_is_not_offered_to_another_account_on_the_same_phone", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    const dialog = await openMeasure(page, "Sprint 30 m", ["Hervé Inventéh"]);
    await dialog.getByRole("button", { name: "Départ", exact: true }).click();
    await page.waitForTimeout(800);
    // Même téléphone, un joueur se connecte ensuite (session remplacée sans
    // passer par « Se déconnecter ») : il ne doit pas pouvoir reprendre.
    await loginAs(page, DEMO.player);
    await page.goto(SESSION_URL);
    await expect(page.getByRole("heading", { name: /Séance du/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reprendre" })).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// 6. Cartes des joueurs
// ---------------------------------------------------------------------------

test.describe("Cartes des joueurs", () => {
  test("cards_page_lists_players_two_columns_without_financial_data", async ({ page }) => {
    await loginAs(page, DEMO.president);
    await page.goto("/club/joueurs");
    await expect(page.getByRole("heading", { name: "Cartes des joueurs" })).toBeVisible();
    await expect(page.getByText(/· \d+ joueurs/).first()).toBeVisible();
    const body = await page.locator("main").innerText();
    expect(body).not.toMatch(/USD|\$|solde|En dette/i);
    const columns = await page.locator("[data-cards-grid]").evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);
    expect(columns).toBe(2);
    await expectNoHorizontalScroll(page);
  });

  test("search_filters_cards_and_detail_shows_fitness_to_coach_only", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await page.goto("/club/joueurs");
    await page.getByLabel("Nom ou numéro").fill("Echant");
    await expect(page.getByText(/Victor Echant/).first()).toBeVisible();
    await expect(page.getByText(/Alain Démoa/)).toHaveCount(0);
    await page.getByText(/Victor Echant/).first().click();
    const dialog = page.getByRole("dialog", { name: "Fiche du joueur" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Aptitude").first()).toBeVisible();
    await expect(dialog.getByText(/Inapte/).first()).toBeVisible();

    await loginAs(page, DEMO.player);
    await page.goto("/club/joueurs");
    await page.getByLabel("Nom ou numéro").fill("Echant");
    await expect(page.getByText(/Inapte|Indisponible|Suspendu/)).toHaveCount(0);
    await page.getByText(/Victor Echant/).first().click();
    const playerDialog = page.getByRole("dialog", { name: "Fiche du joueur" });
    await expect(playerDialog).toBeVisible();
    await expect(playerDialog.getByText(/Inapte|retour prévu/)).toHaveCount(0);
  });

  test("compare_mode_opens_comparison_with_two_players", async ({ page }) => {
    await loginAs(page, DEMO.player);
    await page.goto("/club/joueurs");
    await page.getByRole("button", { name: "Comparer", exact: true }).click();
    await page.getByRole("checkbox", { name: "Comparer Alain Démoa" }).check();
    await page.getByRole("checkbox", { name: "Comparer Bruno Fictifb" }).check();
    await page.getByRole("button", { name: "Comparer (2)" }).click();
    await expect(page.getByRole("dialog").getByText(/Comparer des joueurs/).first()).toBeVisible();
  });

  test("table_view_is_one_tap_away", async ({ page }) => {
    await loginAs(page, DEMO.player);
    await page.goto("/club/joueurs");
    await page.getByRole("radio", { name: "Tableau" }).or(page.getByRole("button", { name: "Tableau", exact: true })).first().click();
    await expect(page.getByRole("table")).toBeVisible();
    await expectNoHorizontalScroll(page);
  });
});

// ---------------------------------------------------------------------------
// 7. Vestiaire et onglet « Plans »
// ---------------------------------------------------------------------------

test.describe("Vestiaire et plans", () => {
  test("locker_room_header_shows_club_and_event_date", async ({ page }) => {
    // sport-vestiaire.md §3 : contexte « {nom du club} · {jeudi 26 novembre} ».
    await loginAs(page, DEMO.player);
    await page.goto("/vestiaire");
    await expect(page.getByText(/Club Démo · jeudi 26 novembre/)).toBeVisible();
  });

  test("coach_plans_tab_lists_published_and_draft_plans_with_actions", async ({ page }) => {
    await loginAs(page, DEMO.coach);
    await page.goto("/vestiaire");
    await page.getByRole("radio", { name: "Plans" }).or(page.getByRole("button", { name: "Plans", exact: true })).first().click();
    await expect(page).toHaveURL(/onglet=plans/);
    await expect(page.getByRole("button", { name: "Nouveau plan" })).toBeVisible();
    await expect(page.getByText(PUBLISHED_PLAN_NAME)).toBeVisible();
    await expect(page.getByText(DRAFT_PLAN_NAME)).toBeVisible();
    await page.getByRole("button", { name: "Brouillons" }).click();
    await expect(page.getByText(PUBLISHED_PLAN_NAME)).toHaveCount(0);
    await expect(page.getByText(DRAFT_PLAN_NAME)).toBeVisible();
    await expectNoHorizontalScroll(page);
  });

  test("plan_badge_reads_publie_in_masculine", async ({ page }) => {
    // sport-vestiaire.md §10 : « badge Publié ou Brouillon » (un plan).
    await loginAs(page, DEMO.player);
    await page.goto("/vestiaire?onglet=plans");
    const row = page.locator("li, button").filter({ hasText: PUBLISHED_PLAN_NAME }).first();
    await expect(row.getByText("Publié", { exact: true })).toBeVisible();
  });

  test("player_sees_only_published_plans_and_opens_plan_in_read_mode", async ({ page }) => {
    await loginAs(page, DEMO.player);
    await page.goto("/vestiaire?onglet=plans");
    await expect(page.getByText(PUBLISHED_PLAN_NAME)).toBeVisible();
    await expect(page.getByText(DRAFT_PLAN_NAME)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Nouveau plan" })).toHaveCount(0);
    await page.getByText(PUBLISHED_PLAN_NAME).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Modifier sur le tableau noir|Supprimer le plan|Dupliquer/ })).toHaveCount(0);
  });

  test("legacy_plans_route_redirects_to_locker_room_plans_tab", async ({ page }) => {
    await loginAs(page, DEMO.player);
    await page.goto("/plans");
    await expect(page).toHaveURL(/\/vestiaire\?onglet=plans/);
    await expect(page.getByText(PUBLISHED_PLAN_NAME)).toBeVisible();
  });
});
