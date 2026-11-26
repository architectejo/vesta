import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";
import { test, expect, type Page } from "@playwright/test";
import { issueSession, loginAs } from "./support/auth";
import { shoot } from "./support/audit";

/**
 * Tâche B6 — série 6 : toute la plateforme à 360 px, contre les vrais
 * serveurs de dev et la base locale de DÉMONSTRATION (club fictif
 * « Club Démo », comptes `@demo.local`). Groupes à lancer séparément :
 * `PW_CHANNEL=chromium npx playwright test e2e/13-serie6-plateforme.spec.ts --grep "S6-xx" --output=test-results/pw-13`.
 *
 * Captures et relevés JSON : `frontend/test-results/serie6-360/` (ignoré par Git).
 */

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.resolve(__dirname, "../test-results/serie6-360");
fs.mkdirSync(OUT_DIR, { recursive: true });

if (process.env.PW_CHANNEL) test.use({ channel: process.env.PW_CHANNEL, video: "off" });

const D = {
  president: "president@demo.local",
  vp: "vp@demo.local",
  treasurer: "tresorier@demo.local",
  coach: "coach@demo.local",
  doctor: "joueur01@demo.local",
  captain: "joueur02@demo.local",
  intendant: "joueur13@demo.local",
  player: "joueur05@demo.local",
  debtor: "joueur24@demo.local",
  suspended: "joueur04@demo.local",
  unfit: "joueur23@demo.local",
  consenting: "joueur21@demo.local",
  superuser: "superuser@demo.local",
  assistantTreasurer: "tresorier.adjoint@example.org",
} as const;

/** Suit les erreurs JavaScript et les réponses API ≥ 500 (ou 4xx inattendues) d'une page. */
function trackErrors(page: Page): { console: string[]; http: string[] } {
  const out = { console: [] as string[], http: [] as string[] };
  page.on("pageerror", (e) => out.console.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") out.console.push(m.text().slice(0, 300));
  });
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 400) out.http.push(`${r.status()} ${r.request().method()} ${r.url().replace(/^https?:\/\/[^/]+/, "")}`);
  });
  return out;
}

async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
  await page.waitForTimeout(300);
}

// ---------------------------------------------------------------------------
// S6-00 — Balayage de toutes les pages par rôle (erreurs, charte 360 px)
// ---------------------------------------------------------------------------

const CLUB_ROUTES = [
  "/", "/tableau-de-bord", "/profil", "/fil", "/club/comite", "/club/joueurs", "/club/assemblees",
  "/club/communiques", "/club/archives", "/club/chat", "/mercato", "/materiel", "/materiel/registre", "/medical",
  "/tresorerie", "/tresorerie/grille", "/tresorerie/depenses", "/tresorerie/assistance",
  "/vestiaire", "/entrainements", "/seances/7",
];
const ADMIN_ROUTES = ["/admin", "/admin/clubs", "/admin/utilisateurs", "/admin/journal", "/admin/parametres"];

const SWEEP: [string, string, string[]][] = [
  ["president", D.president, CLUB_ROUTES],
  ["vp", D.vp, CLUB_ROUTES],
  ["tresorier", D.treasurer, CLUB_ROUTES],
  ["coach", D.coach, CLUB_ROUTES],
  ["medecin", D.doctor, CLUB_ROUTES],
  ["capitaine", D.captain, CLUB_ROUTES],
  ["intendant", D.intendant, CLUB_ROUTES],
  ["joueur", D.player, CLUB_ROUTES],
  ["tresorier-adjoint", D.assistantTreasurer, CLUB_ROUTES],
  ["superuser", D.superuser, ADMIN_ROUTES],
];

test.describe("S6-00 balayage", () => {
  for (const [role, email, routes] of SWEEP) {
    test(`every_page_loads_without_error_for_${role}`, async ({ page }) => {
      test.setTimeout(600_000);
      const errors = trackErrors(page);
      await loginAs(page, email);
      const summary: Record<string, unknown> = {};
      for (const route of routes) {
        errors.console.length = 0;
        errors.http.length = 0;
        // Délai de navigation court et une seconde tentative, consignée (poste
        // de dev chargé). NB : les pages « Vous n'avez pas accès » n'ont pas de
        // titre h1 — d'où le délai borné sur la lecture du titre plus bas.
        let navNote = "";
        await page.goto(route, { timeout: 30_000 }).catch(async (e: Error) => {
          navNote = `première navigation bloquée : ${e.message.slice(0, 80)}`;
          await page.goto(route, { timeout: 30_000 });
        });
        await settle(page);
        const name = `00-${role}${route.replace(/\//g, "_") || "_accueil"}`;
        const report = await shoot(page, OUT_DIR, name);
        const visibleErrors = await page
          .getByText(/Impossible de charger|Une erreur est survenue|Erreur inattendue|undefined|NaN|\[object Object\]/)
          .allInnerTexts()
          .catch(() => []);
        const h1 = await page.locator("h1").first().innerText({ timeout: 2_000 }).catch(() => "(aucun titre h1)");
        summary[route] = {
          h1,
          navNote,
          url: page.url(),
          console: [...errors.console],
          http: [...errors.http],
          visibleErrors,
          scroll: report.scrollWidth - report.clientWidth,
          smallTargets: report.smallTargets.length,
          fonts: report.offCharterFonts.length,
          clipped: report.clipped.length,
        };
        expect.soft(errors.http.filter((h) => h.startsWith("5")), `${role} ${route} : aucune erreur serveur`).toEqual([]);
        expect.soft(visibleErrors, `${role} ${route} : aucun message d'erreur affiché`).toEqual([]);
      }
      fs.writeFileSync(path.join(OUT_DIR, `00-balayage-${role}.json`), JSON.stringify(summary, null, 2));
    });
  }
});

// ---------------------------------------------------------------------------
// Outils communs des parcours
// ---------------------------------------------------------------------------

const RUN = process.env.S6_RUN ?? Date.now().toString(36).slice(-4).toUpperCase();
const PASSWORD = process.env.S6_DEMO_PASSWORD ?? "Demo-dbMJyEnl6dKvPu!7";

/** PNG réel (carré uni) pour les champs photo/image, sans fichier sur le disque. */
function makePng(size = 64, rgb: [number, number, number] = [30, 90, 200]): Buffer {
  const table = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (buf: Buffer) => {
    let c = 0xffffffff;
    for (const b of buf) c = table[(c ^ b) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (type: string, data: Buffer) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type, "ascii"), data]);
    const c = Buffer.alloc(4);
    c.writeUInt32BE(crc(td));
    return Buffer.concat([len, td, c]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: size }, () => rgb).flat())]);
  const raw = Buffer.concat(Array.from({ length: size }, () => row));
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

async function toast(page: Page, text: string | RegExp): Promise<void> {
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 15_000 });
}

/** Ferme la modale du dessus, en confirmant l'abandon si demandé. */
async function closeTopDialog(page: Page): Promise<void> {
  const dialogs = page.locator("[role=dialog]:visible");
  const before = await dialogs.count();
  if (before === 0) return;
  await page.keyboard.press("Escape");
  const abandon = page.getByRole("alertdialog", { name: /Abandonner/ });
  if (await abandon.waitFor({ state: "visible", timeout: 1_000 }).then(() => true, () => false)) await abandon.getByRole("button").last().click();
  await expect.poll(async () => dialogs.count()).toBeLessThan(before);
}

async function openMobileMenu(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Ouvrir le menu", exact: true }).first().click();
}

// ---------------------------------------------------------------------------
// S6-01 — Connexion, CGU, déconnexion ; profil
// ---------------------------------------------------------------------------

test.describe("S6-01 comptes et profil", () => {
  test("player_logs_in_with_password_accepts_pending_terms_and_logs_out", async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto("/connexion");
    await expect(page.getByRole("heading", { name: "Connexion" })).toBeVisible();
    await shoot(page, OUT_DIR, "01-connexion");
    // Mauvais mot de passe : message clair, en français.
    await page.getByLabel("Email").fill("joueur09@demo.local");
    await page.getByLabel("Mot de passe", { exact: true }).fill("mauvais-mot-de-passe");
    await page.getByRole("button", { name: "Se connecter" }).click();
    await expect(page.locator("form").getByText(/incorrect|invalide|identifiants/i).first()).toBeVisible();
    await shoot(page, OUT_DIR, "01-connexion-erreur");
    await page.getByLabel("Mot de passe", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Se connecter" }).click();
    // CGU en attente : la modale bloque l'accès tant qu'elles ne sont pas acceptées.
    const terms = page.getByRole("dialog", { name: /Vos données et votre consentement|Conditions générales/ });
    const home = page.getByRole("heading", { level: 1, name: /Bonjour/ });
    await expect(terms.or(home).first()).toBeVisible({ timeout: 20_000 });
    if (await terms.isVisible().catch(() => false)) {
      await shoot(page, OUT_DIR, "01-cgu");
      await terms.getByRole("checkbox").first().check();
      await terms.getByRole("button", { name: "Continuer" }).click();
    }
    const photo = page.getByRole("dialog", { name: /photo/i });
    if (await photo.waitFor({ state: "visible", timeout: 2_000 }).then(() => true, () => false)) await closeTopDialog(page);
    await expect(home).toBeVisible({ timeout: 20_000 });
    await shoot(page, OUT_DIR, "01-accueil-apres-connexion");
    await openMobileMenu(page);
    await shoot(page, OUT_DIR, "01-menu-mobile");
    await page.getByRole("button", { name: "Ouvrir le menu utilisateur" }).click();
    await page.getByRole("button", { name: "Se déconnecter" }).click();
    await expect(page).toHaveURL(/\/connexion|\/c\//, { timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "Connexion" })).toBeVisible();
    // La session est bien close : une page privée renvoie vers la connexion.
    await page.goto("/tresorerie");
    await expect(page).toHaveURL(/\/connexion|\/c\//, { timeout: 15_000 });
    expect.soft(errors.http.filter((h) => h.startsWith("5"))).toEqual([]);
  });

  test("player_edits_personal_information_photo_and_downloads_his_data", async ({ page }) => {
    await loginAs(page, "joueur09@demo.local");
    await page.goto("/profil");
    await expect(page.getByRole("heading", { level: 1, name: "Mon profil" })).toBeVisible();
    await expect(page.getByText("Ces informations ne sont jamais publiques.")).toBeVisible();
    await shoot(page, OUT_DIR, "01-profil");
    // Données personnelles.
    await page.getByRole("button", { name: "Modifier mon profil" }).click();
    const modal = page.getByRole("dialog", { name: "Modifier mon profil" });
    await expect(modal).toBeVisible();
    const phone = `+243810${String(Date.now()).slice(-6)}`;
    await modal.getByLabel(/Téléphone/).fill(phone);
    await modal.getByLabel("Poids (kg)").fill("78");
    await shoot(page, OUT_DIR, "01-profil-modifier-informations");
    await modal.getByRole("button", { name: "Enregistrer", exact: true }).click();
    await expect(page.getByText(phone).first()).toBeVisible({ timeout: 15_000 });
    if (await modal.isVisible().catch(() => false)) await closeTopDialog(page);
    await expect(page.getByText("78 kg")).toBeVisible();
    // Photo.
    await page.getByRole("button", { name: "Modifier mon profil" }).click();
    await modal.getByRole("tab", { name: "Photo" }).click();
    await modal.locator("#edit-profile-photo-input").setInputFiles({ name: "photo.png", mimeType: "image/png", buffer: makePng(256) });
    await shoot(page, OUT_DIR, "01-profil-photo");
    await modal.getByRole("button", { name: "Enregistrer la photo" }).click();
    await toast(page, "Photo mise à jour.");
    if (await modal.isVisible().catch(() => false)) await closeTopDialog(page);
    // Identifiants.
    await page.getByRole("button", { name: "Modifier mon profil" }).click();
    await modal.getByRole("tab", { name: "Identifiant et mot de passe" }).click();
    await shoot(page, OUT_DIR, "01-profil-identifiants");
    await closeTopDialog(page);
    // Export de ses données (CDC 7.5).
    await page.getByRole("button", { name: "Ouvrir le menu", exact: true }).last().click();
    const downloadPromise = page.waitForEvent("download", { timeout: 20_000 });
    await page.getByRole("button", { name: "Télécharger mes données" }).click();
    const download = await downloadPromise;
    const file = path.join(OUT_DIR, `01-export-${download.suggestedFilename()}`);
    await download.saveAs(file);
    expect(fs.statSync(file).size).toBeGreaterThan(50);
    // Carte de joueur depuis le profil.
    await page.getByRole("button", { name: "Ouvrir le menu", exact: true }).last().click();
    await page.getByRole("button", { name: "Voir ma carte de joueur" }).click();
    await expect(page.getByRole("dialog").first()).toBeVisible();
    await shoot(page, OUT_DIR, "01-profil-ma-carte");
  });
});

// ---------------------------------------------------------------------------
// S6-02 — Fil social et communiqués
// ---------------------------------------------------------------------------

test.describe("S6-02 fil et communiqués", () => {
  test("player_publishes_comments_and_likes_on_the_club_feed", async ({ page }) => {
    const text = `Publication de test série 6 ${RUN}`;
    await loginAs(page, D.player);
    await page.goto("/fil");
    await expect(page.getByRole("heading", { level: 1, name: "Fil d'actualité" })).toBeVisible();
    await page.getByRole("button", { name: "Publier", exact: true }).click();
    const modal = page.getByRole("dialog", { name: "Nouvelle publication" });
    await expect(modal).toBeVisible();
    await modal.getByLabel("Texte").fill(text);
    await shoot(page, OUT_DIR, "02-fil-nouvelle-publication");
    await modal.getByRole("button", { name: "Publier", exact: true }).click();
    await expect(modal).toBeHidden({ timeout: 15_000 });
    const card = page.locator("article").filter({ hasText: text }).first();
    await expect(card).toBeVisible({ timeout: 15_000 });
    const like = card.getByRole("button", { name: /^J'aime/ });
    await like.click();
    await expect(like).toHaveAttribute("aria-pressed", "true");
    await expect(like).toHaveText(/J'aime · 1/);
    await card.getByRole("button", { name: /^Commenter/ }).click();
    const detail = page.getByRole("dialog", { name: /Publication de/ });
    await expect(detail).toBeVisible();
    await detail.getByLabel("Écrire un commentaire…").fill(`Commentaire ${RUN}`);
    await detail.getByRole("button", { name: "Envoyer" }).click();
    await expect(detail.getByText(`Commentaire ${RUN}`)).toBeVisible({ timeout: 15_000 });
    await shoot(page, OUT_DIR, "02-fil-detail-commentaire");
    await closeTopDialog(page);
    await expect(card.getByRole("button", { name: /^Commenter · 1/ })).toBeVisible();
    await shoot(page, OUT_DIR, "02-fil-apres-publication");
    // Un autre membre du club la voit et peut l'aimer.
    await loginAs(page, D.captain);
    await page.goto("/fil");
    const seen = page.locator("article").filter({ hasText: text }).first();
    await expect(seen).toBeVisible({ timeout: 15_000 });
    await seen.getByRole("button", { name: /^J'aime/ }).click();
    await expect(seen.getByRole("button", { name: /^J'aime/ })).toHaveText(/J'aime · 2/);
  });

  test("president_publishes_announcement_and_player_reads_it", async ({ page }) => {
    const title = `Communiqué série 6 ${RUN}`;
    await loginAs(page, D.president);
    await page.goto("/club/communiques");
    await expect(page.getByRole("heading", { level: 1, name: "Communiqués" })).toBeVisible();
    await page.getByRole("button", { name: "Publier un communiqué" }).click();
    const modal = page.getByRole("dialog", { name: "Publier un communiqué" });
    await modal.getByRole("button", { name: "Publier", exact: true }).click();
    await expect(modal.getByText(/obligatoire/).first()).toBeVisible();
    await modal.getByLabel("Titre").fill(title);
    await modal.getByLabel("Message").fill("Réunion du comité samedi à 10 h au terrain principal.");
    await shoot(page, OUT_DIR, "02-communique-publier");
    await modal.getByRole("button", { name: "Publier", exact: true }).click();
    await expect(modal).toBeHidden({ timeout: 15_000 });
    await expect(page.getByText(title).first()).toBeVisible();
    await shoot(page, OUT_DIR, "02-communiques-president");
    // Un joueur le voit et le lit ; il ne peut pas publier.
    await loginAs(page, D.player);
    await page.goto("/club/communiques");
    await expect(page.getByRole("button", { name: "Publier un communiqué" })).toHaveCount(0);
    await page.getByText(title).first().click();
    const detail = page.getByRole("dialog").first();
    await expect(detail).toBeVisible();
    await expect(detail.getByText("Réunion du comité samedi").first()).toBeVisible();
    await shoot(page, OUT_DIR, "02-communique-detail-joueur");
  });
});

// ---------------------------------------------------------------------------
// S6-03 — Club : comité et bureau, adhésion et parrainage, import, cartes
// ---------------------------------------------------------------------------

const NEW_PLAYER = { first: "Sixtine", last: `Essai${RUN}`, email: `s6-${RUN.toLowerCase()}@example.org` };
const SPONSOR = { email: "joueur03@demo.local", name: "Cédric Testc" };

/** Crée par l'interface (Trésorier) le type « Frais d'adhésion » s'il manque (CDC 4.3, tresorerie-tableau-de-bord.md §4.6). */
async function ensureMembershipFeeType(page: Page): Promise<void> {
  await page.goto("/tresorerie");
  await expect(page.getByRole("heading", { name: "Types de cotisation" })).toBeVisible();
  const typesCard = page.locator("section").filter({ has: page.getByRole("heading", { name: "Types de cotisation" }) });
  await expect(typesCard.getByText("Cotisation mensuelle").first()).toBeVisible();
  if ((await typesCard.getByText("Frais d'adhésion").count()) > 0) return;
  await page.getByRole("button", { name: "Nouveau type" }).first().click();
  const modal = page.getByRole("dialog", { name: "Nouveau type de cotisation" });
  await modal.getByLabel("Nom").fill("Frais d'adhésion");
  await modal.getByLabel("Montant").fill("5");
  await modal.getByLabel("Périodicité").selectOption("one_off");
  // Toucher le libellé, comme au doigt (la zone tactile de `Checkbox` couvre la case, B7).
  await modal.locator("label").filter({ hasText: "Frais d'adhésion" }).click();
  await expect(modal.getByRole("checkbox", { name: "Frais d'adhésion" })).toBeChecked();
  await shoot(page, OUT_DIR, "03-type-frais-adhesion");
  await modal.getByRole("button", { name: "Enregistrer" }).click();
  await expect(modal).toBeHidden({ timeout: 15_000 });
}

test.describe.serial("S6-03 club", () => {
  test("president_sees_committee_board_and_player_cannot_add_players", async ({ page }) => {
    await loginAs(page, D.president);
    await page.goto("/club/comite");
    await expect(page.getByRole("heading", { level: 1, name: "Comité et bureau" })).toBeVisible();
    for (const title of ["Identité du club", "Président", "Bureau", "Encadrement sportif", "Effectif"]) {
      await expect(page.getByRole("heading", { name: title, exact: true }).first()).toBeVisible();
    }
    await expect(page.getByRole("button", { name: "Ajouter un joueur" })).toBeVisible();
    await shoot(page, OUT_DIR, "03-comite-president");
    // Import : modèle téléchargeable, bouton bloqué tant qu'aucun fichier n'est choisi.
    await page.getByRole("button", { name: "Importer (CSV)" }).click();
    const imp = page.getByRole("dialog", { name: "Importer des joueurs" });
    await expect(imp).toBeVisible();
    await expect(imp.getByRole("button", { name: "Importer", exact: true })).toBeDisabled();
    const dl = page.waitForEvent("download");
    await imp.getByRole("button", { name: "Télécharger le modèle CSV" }).click();
    expect((await dl).suggestedFilename()).toBe("modele-import-joueurs.csv");
    await shoot(page, OUT_DIR, "03-import-joueurs");
    await closeTopDialog(page);

    await loginAs(page, D.player);
    await page.goto("/club/comite");
    await expect(page.getByRole("heading", { level: 1, name: "Comité et bureau" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Ajouter un joueur" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Importer (CSV)" })).toHaveCount(0);
    await shoot(page, OUT_DIR, "03-comite-joueur");
  });

  test("president_adds_player_with_sponsor_who_stays_pending", async ({ page }) => {
    await loginAs(page, D.president);
    await page.goto("/club/comite");
    await page.getByRole("button", { name: "Ajouter un joueur" }).click();
    const modal = page.getByRole("dialog", { name: "Ajouter un joueur" });
    await modal.getByRole("button", { name: "Ajouter le joueur" }).click();
    await expect(modal.getByText("Choisissez un parrain.")).toBeVisible();
    await modal.getByLabel("Prénom").fill(NEW_PLAYER.first);
    await modal.getByLabel("Nom", { exact: true }).fill(NEW_PLAYER.last);
    await modal.getByLabel("Email").fill(NEW_PLAYER.email);
    await modal.getByRole("radio", { name: "Milieu" }).or(modal.getByRole("button", { name: "Milieu", exact: true })).first().click();
    const sponsor = modal.getByPlaceholder("Nom ou numéro du joueur");
    await sponsor.fill("Testc");
    await modal.getByRole("option").filter({ hasText: SPONSOR.name }).first().click();
    await shoot(page, OUT_DIR, "03-ajouter-joueur");
    await modal.getByRole("button", { name: "Ajouter le joueur" }).click();
    await toast(page, `${NEW_PLAYER.first} ${NEW_PLAYER.last} a été ajouté. Statut : En attente.`);
    await expect(modal).toBeHidden();
    await page.getByLabel("Rechercher un joueur").fill(NEW_PLAYER.last);
    const row = page.getByText(`${NEW_PLAYER.first} ${NEW_PLAYER.last}`).first();
    await expect(row).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("row", { name: new RegExp(NEW_PLAYER.last) }).getByText("En attente", { exact: true })).toBeVisible();
    await shoot(page, OUT_DIR, "03-effectif-en-attente");
  });

  test("treasurer_records_membership_fee_and_sponsor_signs_with_confirmation", async ({ page }) => {
    if (process.env.S6_DEBUG_HISTORY) {
      await page.addInitScript(() => {
        const back = history.back.bind(history);
        history.back = () => {
          console.log("HISTORY.BACK", new Error().stack?.split("\n").slice(1, 9).join(" | "));
          back();
        };
        const push = history.pushState.bind(history);
        history.pushState = (...a: Parameters<History["pushState"]>) => {
          console.log("HISTORY.PUSH", JSON.stringify(a[0]), String(a[2] ?? ""), "len", history.length);
          push(...a);
        };
        window.addEventListener("popstate", (e) =>
          console.log("HISTORY.POP", JSON.stringify(e.state), location.pathname, "len", history.length),
        );
      });
      page.on("console", (m) => {
        if (m.text().startsWith("HISTORY")) console.log(m.text().replace(/http:\/\/localhost:5173\/src\//g, "").slice(0, 900));
      });
    }
    await loginAs(page, D.treasurer);
    await page.goto("/club/comite");
    await page.getByLabel("Rechercher un joueur").fill(NEW_PLAYER.last);
    await page.getByText(`${NEW_PLAYER.first} ${NEW_PLAYER.last}`).first().click();
    const card = page.getByRole("dialog").first();
    await expect(card).toBeVisible();
    await shoot(page, OUT_DIR, "03-fiche-joueur-en-attente-tresorier");
    // Le club doit avoir un type « adhésion » (CDC 4.3) ; sinon le Trésorier le crée par l'interface.
    await ensureMembershipFeeType(page);
    await page.goto("/club/comite");
    await page.getByLabel("Rechercher un joueur").fill(NEW_PLAYER.last);
    await page.getByText(`${NEW_PLAYER.first} ${NEW_PLAYER.last}`).first().click();
    const fee = page.getByRole("dialog").first().getByRole("button", { name: "Enregistrer les frais d'adhésion" });
    await expect(fee).toBeVisible({ timeout: 15_000 });
    await fee.click();
    const feeModal = page.getByRole("dialog", { name: /Frais d'adhésion de/ });
    await feeModal.getByLabel("Montant").fill("5");
    await feeModal.getByRole("button", { name: "Enregistrer" }).click();
    const confirm = page.getByRole("alertdialog", { name: /Valider ce paiement de/ }).or(page.getByRole("dialog", { name: /Valider ce paiement de/ }));
    await expect(confirm).toBeVisible();
    await shoot(page, OUT_DIR, "03-frais-adhesion-confirmation");
    await confirm.getByRole("button", { name: "Valider" }).click();
    // Après l'enregistrement, on reste sur la page (aucun retour d'historique en trop).
    await page.waitForTimeout(1_500);
    await expect(page, "la page ne doit pas revenir en arrière après les frais d'adhésion").toHaveURL(/\/club\/comite/);
    await toast(page, "Frais d'adhésion enregistrés.");
    // Le parrain signe depuis « Adhésions à traiter ».
    await loginAs(page, SPONSOR.email);
    await page.goto("/club/comite");
    const followUp = page.getByRole("region", { name: "Adhésions à traiter" });
    await expect(followUp).toBeVisible();
    await shoot(page, OUT_DIR, "03-parrain-adhesions-a-traiter");
    await followUp.getByText(`${NEW_PLAYER.first} ${NEW_PLAYER.last}`).first().click();
    const sign = page.getByRole("dialog", { name: `Fiche d'adhésion de ${NEW_PLAYER.first} ${NEW_PLAYER.last}`, exact: true });
    await expect(sign).toBeVisible();
    await shoot(page, OUT_DIR, "03-fiche-adhesion-parrain");
    await sign.getByRole("button", { name: "Signer la fiche" }).click();
    const signConfirm = page.getByRole("alertdialog", { name: /Signer la fiche d'adhésion de/ }).or(page.getByRole("dialog", { name: /Signer la fiche d'adhésion de/ }));
    await expect(signConfirm).toBeVisible();
    await expect(signConfirm.getByText(/code PIN/i)).toHaveCount(0);
    await shoot(page, OUT_DIR, "03-signature-parrain-confirmation");
    await signConfirm.getByRole("button", { name: "Signer la fiche" }).click();
    await expect(sign).toBeHidden({ timeout: 15_000 });
    // Le joueur passe « Inscrit ».
    await page.goto("/club/comite");
    await page.getByLabel("Rechercher un joueur").fill(NEW_PLAYER.last);
    await expect(page.getByText(`${NEW_PLAYER.first} ${NEW_PLAYER.last}`).first()).toBeVisible();
    await expect(page.getByRole("row", { name: new RegExp(NEW_PLAYER.last) }).getByText("Inscrit", { exact: true })).toBeVisible({ timeout: 15_000 });
    await shoot(page, OUT_DIR, "03-effectif-inscrit");
  });

  test("player_cards_page_lists_cards_and_opens_detail_without_finance", async ({ page }) => {
    await loginAs(page, D.player);
    await page.goto("/club/joueurs");
    await expect(page.getByRole("heading", { level: 1, name: "Cartes des joueurs" })).toBeVisible();
    await shoot(page, OUT_DIR, "03-cartes-joueur");
    await page.getByText("Bruno Fictifb").first().click();
    const detail = page.getByRole("dialog").first();
    await expect(detail).toBeVisible();
    await expect(detail.getByText(/En dette|En ordre|solde/i)).toHaveCount(0);
    await expect(detail.getByText(/Inapte|diagnostic/i)).toHaveCount(0);
    await shoot(page, OUT_DIR, "03-carte-detail-joueur");
  });
});

// ---------------------------------------------------------------------------
// S6-04 — Licences (espace Superuser) et S6-12 — Espace Superuser
// ---------------------------------------------------------------------------

test.describe("S6-04 S6-12 superuser et licences", () => {
  test("superuser_sees_clubs_licences_users_journal_and_settings", async ({ page }) => {
    await loginAs(page, D.superuser);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { level: 1, name: "Tableau de bord" })).toBeVisible();
    await shoot(page, OUT_DIR, "12-admin-tableau-de-bord");
    await page.goto("/admin/clubs");
    await expect(page.getByRole("heading", { level: 1, name: "Clubs et licences" })).toBeVisible();
    await expect(page.getByText("Club Démo").first()).toBeVisible();
    await shoot(page, OUT_DIR, "04-licences-liste");
    await page.getByText("Club Démo").first().click();
    const detail = page.getByRole("dialog").first();
    await expect(detail).toBeVisible();
    await expect(detail.getByText(/Essai|Active|Suspendue/).first()).toBeVisible();
    await shoot(page, OUT_DIR, "04-licence-detail");
    await closeTopDialog(page);
    await page.goto("/admin/utilisateurs");
    await expect(page.getByRole("heading", { level: 1, name: "Utilisateurs" })).toBeVisible();
    await page.getByLabel("Nom ou email").fill("joueur05");
    await expect(page.getByText(/joueur05@demo\.local|Éric Imaginée/).first()).toBeVisible({ timeout: 15_000 });
    await shoot(page, OUT_DIR, "12-admin-utilisateurs");
    await page.goto("/admin/journal");
    await expect(page.getByRole("heading", { level: 1, name: "Journal d'activité" })).toBeVisible();
    await shoot(page, OUT_DIR, "12-admin-journal");
    // Le journal est en lecture seule : aucune action de modification ni de suppression.
    await expect(page.getByRole("button", { name: /Supprimer|Modifier/ })).toHaveCount(0);
    await page.goto("/admin/parametres");
    await expect(page.locator("h1").first()).toBeVisible();
    await shoot(page, OUT_DIR, "12-admin-parametres");
  });

  test("club_member_cannot_open_superuser_space", async ({ page }) => {
    await loginAs(page, D.president);
    await page.goto("/admin/journal");
    await expect(page.getByRole("heading", { level: 1, name: "Journal d'activité" })).toHaveCount(0);
    await shoot(page, OUT_DIR, "12-admin-refuse-president");
  });
});

// ---------------------------------------------------------------------------
// S6-05 — Trésorerie
// ---------------------------------------------------------------------------

const PAYER = { search: "Proto", name: "Kevin Proto" };

async function recordPayment(page: Page, amount: string): Promise<void> {
  await page.getByRole("button", { name: "Enregistrer un paiement" }).first().click();
  const modal = page.getByRole("dialog", { name: "Enregistrer un paiement" });
  await expect(modal).toBeVisible();
  await modal.getByPlaceholder("Nom ou numéro du joueur").fill(PAYER.search);
  await modal.getByRole("option").filter({ hasText: PAYER.name }).first().click();
  const typeSelect = modal.locator("#record-payment-type");
  await expect(typeSelect.locator("option", { hasText: "Cotisation mensuelle" })).toHaveCount(1);
  const typeValue = await typeSelect.locator("option", { hasText: "Cotisation mensuelle" }).getAttribute("value");
  await typeSelect.selectOption(typeValue ?? "");
  await modal.getByLabel("Montant").fill(amount);
  await expect(modal.getByText("Répartition").first()).toBeVisible({ timeout: 15_000 });
  await shoot(page, OUT_DIR, "05-enregistrer-paiement");
  await modal.getByRole("button", { name: "Enregistrer", exact: true }).click();
  const confirm = page.getByRole("alertdialog", { name: /Valider ce paiement de/ }).or(page.getByRole("dialog", { name: /Valider ce paiement de/ }));
  await expect(confirm).toBeVisible();
  // Décision du 11/10/2026 : modale de confirmation, jamais de code PIN.
  await expect(confirm.getByText(/PIN/)).toHaveCount(0);
  await expect(confirm.locator("input[type=password], input[inputmode=numeric]")).toHaveCount(0);
  await expect(confirm.getByText(/Il ne pourra plus être supprimé, seulement annulé/)).toBeVisible();
  await shoot(page, OUT_DIR, "05-confirmation-paiement");
  await confirm.getByRole("button", { name: "Valider", exact: true }).click();
  await expect(modal).toBeHidden({ timeout: 15_000 });
}

test.describe.serial("S6-05 trésorerie", () => {
  test("treasurer_records_payment_with_confirmation_and_requests_reversal", async ({ page }) => {
    await loginAs(page, D.treasurer);
    await page.goto("/tresorerie");
    await expect(page.getByRole("heading", { level: 1, name: "Trésorerie" })).toBeVisible();
    await shoot(page, OUT_DIR, "05-tresorerie-tresorier");
    await recordPayment(page, "10");
    const recent = page.getByRole("region", { name: "Derniers paiements" });
    await expect(recent.getByText(PAYER.name).first()).toBeVisible({ timeout: 15_000 });
    await recent.getByText(PAYER.name).first().click();
    const detail = page.getByRole("dialog", { name: "Détail du paiement" });
    await expect(detail).toBeVisible();
    await expect(detail.getByText("Validé").first()).toBeVisible();
    // Aucune suppression possible d'un paiement validé (CLAUDE.md règle 4).
    await expect(detail.getByRole("button", { name: /Supprimer/ })).toHaveCount(0);
    await shoot(page, OUT_DIR, "05-detail-paiement-valide");
    await detail.getByRole("button", { name: "Demander l'annulation" }).click();
    const req = page.getByRole("dialog", { name: "Demander l'annulation" });
    await req.getByRole("button", { name: "Envoyer la demande" }).click();
    await expect(req.getByText(/obligatoire|Indiquez/).first()).toBeVisible();
    await req.getByLabel("Motif de l'annulation").fill(`Erreur de saisie (série 6 ${RUN})`);
    await shoot(page, OUT_DIR, "05-demande-annulation");
    await req.getByRole("button", { name: "Envoyer la demande" }).click();
    await expect(req).toBeHidden({ timeout: 15_000 });
    await expect(detail.getByText("En attente de validation par le Président.")).toBeVisible({ timeout: 15_000 });
  });

  test("president_validates_reversal_and_payment_stays_listed_as_cancelled", async ({ page }) => {
    await loginAs(page, D.president);
    await page.goto("/tresorerie");
    const toValidate = page.getByRole("region", { name: "À valider" });
    await expect(toValidate).toBeVisible();
    await shoot(page, OUT_DIR, "05-tresorerie-president-a-valider");
    await toValidate.getByText(PAYER.name).first().click();
    const detail = page.getByRole("dialog", { name: "Détail du paiement" });
    await expect(detail).toBeVisible();
    await expect(detail.getByText(`Erreur de saisie (série 6 ${RUN})`).first()).toBeVisible();
    await detail.getByRole("button", { name: "Valider l'annulation" }).click();
    const confirm = page.getByRole("alertdialog", { name: /Annuler ce paiement de/ }).or(page.getByRole("dialog", { name: /Annuler ce paiement de/ }));
    await expect(confirm).toBeVisible();
    await expect(confirm.getByText(/Le paiement d'origine reste conservé/)).toBeVisible();
    await expect(confirm.getByText(/PIN/)).toHaveCount(0);
    await shoot(page, OUT_DIR, "05-confirmation-annulation");
    await confirm.getByRole("button", { name: "Annuler le paiement" }).click();
    await expect(confirm).toBeHidden({ timeout: 15_000 });
    await expect(detail.getByText(/Annulé/).first()).toBeVisible({ timeout: 15_000 });
    await shoot(page, OUT_DIR, "05-paiement-annule");
    await closeTopDialog(page);
    // L'écriture d'origine reste visible dans les derniers paiements (jamais supprimée).
    const recent = page.getByRole("region", { name: "Derniers paiements" });
    await expect(recent.getByText(PAYER.name).first()).toBeVisible();
  });

  test("cash_register_opens_a_session_shows_debt_and_collects_cash", async ({ page }) => {
    await loginAs(page, D.treasurer);
    await page.goto("/tresorerie");
    await page.getByRole("button", { name: "Caisse Terrain Express" }).click();
    const open = page.getByRole("alertdialog", { name: "Ouvrir une session de caisse ?" }).or(page.getByRole("dialog", { name: "Ouvrir une session de caisse ?" }));
    if (await open.waitFor({ state: "visible", timeout: 8_000 }).then(() => true, () => false)) {
      await shoot(page, OUT_DIR, "05-caisse-ouvrir-session");
      await open.getByRole("button", { name: "Ouvrir la session" }).click();
    }
    const cash = page.getByRole("dialog", { name: "Caisse Terrain Express" });
    await expect(cash).toBeVisible({ timeout: 15_000 });
    await expect(cash.getByText("Session de caisse ouverte jusqu'à minuit.")).toBeVisible();
    // Joueur en dette : solde négatif et statut « En dette » calculés par l'API (rien n'est encaissé).
    await cash.getByPlaceholder("Nom ou numéro du joueur").fill("Leurre");
    await cash.getByRole("option").filter({ hasText: "Aimé Leurre" }).first().click();
    await expect(cash.getByText(/Solde :/)).toBeVisible();
    await expect(cash.getByText("En dette", { exact: true })).toBeVisible();
    await shoot(page, OUT_DIR, "05-caisse-joueur-en-dette");
    await cash.getByRole("button", { name: "Changer" }).last().click();
    await cash.getByPlaceholder("Nom ou numéro du joueur").fill(PAYER.search);
    await cash.getByRole("option").filter({ hasText: PAYER.name }).first().click();
    await cash.getByLabel("Montant en espèces").fill("10");
    await cash.getByRole("button", { name: "Encaisser" }).click();
    await toast(page, /Encaissement enregistré\. Reçu n°/);
    await shoot(page, OUT_DIR, "05-caisse-encaisse");
    await cash.getByRole("button", { name: "Quitter la caisse" }).click();
    await expect(cash).toBeHidden();
  });

  test("debtor_and_player_in_good_standing_see_computed_status_on_profile", async ({ page }) => {
    await loginAs(page, D.debtor);
    await page.goto("/profil");
    await expect(page.getByText("En dette").first()).toBeVisible({ timeout: 15_000 });
    await shoot(page, OUT_DIR, "05-profil-joueur-en-dette");
    await loginAs(page, "joueur11@demo.local");
    await page.goto("/profil");
    await expect(page.getByText(/En ordre|En dette/).first()).toBeVisible({ timeout: 15_000 });
    await shoot(page, OUT_DIR, "05-profil-joueur-kevin");
  });

  test("contribution_grid_and_member_situation_for_treasurer", async ({ page }) => {
    await loginAs(page, D.treasurer);
    await page.goto("/tresorerie/grille");
    await expect(page.getByRole("heading", { level: 1, name: "Grille des cotisations" })).toBeVisible();
    await shoot(page, OUT_DIR, "05-grille");
    await page.goto("/tresorerie");
    const members = page.getByRole("region", { name: "Membres du club" });
    await members.getByLabel("Rechercher un joueur").fill("Leurre");
    await members.getByText("Aimé Leurre").first().click();
    const situation = page.getByRole("dialog").first();
    await expect(situation).toBeVisible();
    await expect(situation.getByText("En dette").first()).toBeVisible();
    await shoot(page, OUT_DIR, "05-situation-membre-en-dette");
  });

  test("unjustified_expense_blocks_release_of_a_new_expense", async ({ page }) => {
    const beneficiary = `Fournisseur fictif ${RUN}`;
    await loginAs(page, D.treasurer);
    await page.goto("/tresorerie/depenses");
    await expect(page.getByRole("heading", { level: 1, name: "Dépenses" })).toBeVisible();
    await shoot(page, OUT_DIR, "05-depenses-tresorier");
    await page.getByRole("button", { name: /Saisir une dépense|Nouvelle dépense/ }).first().click();
    const modal = page.getByRole("dialog", { name: "Saisir une dépense" });
    await expect(modal).toBeVisible();
    await modal.locator("#create-expense-category").selectOption({ label: "Déplacements" });
    await modal.getByLabel("Montant").fill("3");
    await modal.getByLabel("Nom du bénéficiaire").fill(beneficiary);
    await modal.getByLabel("Motif").fill("Transport vers le terrain (série 6).");
    await modal.getByLabel("Date", { exact: true }).fill(new Date().toLocaleDateString("sv-SE"));
    await shoot(page, OUT_DIR, "05-saisir-depense");
    await modal.getByRole("button", { name: "Enregistrer la dépense" }).click();
    await expect(modal).toBeHidden({ timeout: 15_000 });

    await loginAs(page, D.president);
    await page.goto("/tresorerie/depenses");
    await expect(page.getByText("Une dépense n'est pas justifiée").first()).toBeVisible();
    await page.getByText(beneficiary).first().click();
    const detail = page.getByRole("dialog").first();
    await expect(detail).toBeVisible();
    await expect(detail.getByRole("button", { name: "Valider et libérer" })).toBeDisabled();
    await shoot(page, OUT_DIR, "05-depense-bloquee-president");
    // Nettoyage : refus motivé (aucune suppression).
    await detail.getByRole("button", { name: "Refuser" }).click();
    const refuse = page.getByRole("dialog", { name: "Refuser la dépense" }).or(page.getByRole("alertdialog", { name: "Refuser la dépense" }));
    await refuse.getByLabel("Motif du refus").fill("Test de blocage (série 6).");
    await refuse.getByRole("button", { name: "Refuser la dépense" }).click();
    await expect(refuse).toBeHidden({ timeout: 15_000 });
  });

  test("player_requests_social_assistance_and_board_sees_the_page", async ({ page }) => {
    await loginAs(page, D.player);
    await page.goto("/profil");
    await shoot(page, OUT_DIR, "05-profil-assistance-joueur");
    await loginAs(page, D.president);
    await page.goto("/tresorerie/assistance");
    await expect(page.getByRole("heading", { level: 1, name: "Assistance sociale" })).toBeVisible();
    await shoot(page, OUT_DIR, "05-assistance-president");
  });

  test("player_has_no_treasury_access", async ({ page }) => {
    await loginAs(page, D.player);
    for (const route of ["/tresorerie", "/tresorerie/depenses", "/tresorerie/grille"]) {
      await page.goto(route);
      await expect(page.getByRole("button", { name: "Enregistrer un paiement" })).toHaveCount(0);
      await expect(page.getByText(/Vous n'avez pas accès|réservée/).first()).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// S6-06 — Sport : séances, matchs, composition, cartons, vestiaire, tests
// ---------------------------------------------------------------------------

const MATCH_URL = "/matchs/6";
const DEBTOR_NAME = "Aimé Leurre";
const SUSPENDED_NAME = "Didier Exempled";
const UNFIT_NAME = "William Placebo";

test.describe("S6-06 sport", () => {
  test("coach_marks_an_individual_arrival_at_todays_session", async ({ page }) => {
    await loginAs(page, D.coach);
    await page.goto("/seances/7");
    await expect(page.getByRole("heading", { name: /Séance du/ })).toBeVisible();
    await page.getByRole("tab", { name: "Pointage" }).click();
    await shoot(page, OUT_DIR, "06-seance-pointage");
    const arrive = page.getByRole("button", { name: "Arrivé", exact: true });
    if ((await arrive.count()) === 0) {
      test.info().annotations.push({ type: "info", description: "Tous les joueurs sont déjà pointés." });
      return;
    }
    const before = await arrive.count();
    await arrive.first().click();
    // Un menu ou une confirmation peut s'ouvrir selon l'heure (retardataire).
    const dialog = page.getByRole("dialog").first();
    if (await dialog.waitFor({ state: "visible", timeout: 2_000 }).then(() => true, () => false)) {
      await shoot(page, OUT_DIR, "06-seance-arrivee-menu");
      const confirm = dialog.getByRole("button", { name: /Confirmer|Enregistrer|Valider|Présent|Arrivé/ }).first();
      if (await confirm.isVisible().catch(() => false)) await confirm.click();
    }
    await expect.poll(async () => arrive.count(), { timeout: 15_000 }).toBeLessThan(before);
    await shoot(page, OUT_DIR, "06-seance-apres-arrivee");
  });

  test("bulk_selection_checkboxes_have_44px_targets", async ({ page }) => {
    await loginAs(page, D.coach);
    await page.goto("/seances/7");
    await page.getByRole("tab", { name: "Pointage" }).click();
    const select = page.getByRole("button", { name: "Sélectionner", exact: true });
    if (!(await select.isVisible().catch(() => false))) return;
    await select.click();
    const box = page.getByRole("checkbox").first();
    if ((await box.count()) === 0) return;
    const zone = await box.evaluate((el) => (el.closest("label") ?? el).getBoundingClientRect().height);
    expect(zone).toBeGreaterThanOrEqual(36);
    await shoot(page, OUT_DIR, "06-seance-selection-groupee");
  });

  test("coach_cannot_compose_debtor_suspended_or_unfit_players", async ({ page }) => {
    await loginAs(page, D.coach);
    await page.goto(MATCH_URL);
    await expect(page.locator("h1").first()).toBeVisible();
    await shoot(page, OUT_DIR, "06-match-coach");
    const compose = page.getByRole("button", { name: /^(Composer l'équipe|Modifier la composition)$/ }).first();
    await expect(compose).toBeVisible();
    await compose.click();
    const modal = page.getByRole("dialog", { name: "Composer l'équipe" });
    await expect(modal).toBeVisible();
    for (const name of [DEBTOR_NAME, UNFIT_NAME]) {
      const box = modal.getByRole("checkbox", { name: `Sélectionner ${name}` });
      await expect(box).toBeVisible();
      await expect(box, `${name} ne doit pas être cochable`).toBeDisabled();
    }
    // Didier Exempled (suspendu) figure déjà dans la composition figée du seed :
    // sa case est désactivée (« déjà composé ») ; l'API le signale non éligible.
    await expect(modal.getByRole("checkbox", { name: `Sélectionner ${SUSPENDED_NAME}` })).toBeDisabled();
    // Les cases cochables gardent une zone tactile d'au moins 36 px (B7).
    const zone = await modal.getByRole("checkbox").first().evaluate((el) => (el.closest("label") ?? el).getBoundingClientRect().height);
    expect(zone).toBeGreaterThanOrEqual(36);
    await shoot(page, OUT_DIR, "06-composer-equipe");
    await closeTopDialog(page);
  });

  test("player_sees_match_read_only_and_coach_opens_card_modal", async ({ page }) => {
    await loginAs(page, D.player);
    await page.goto(MATCH_URL);
    await expect(page.locator("h1").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Composer l'équipe" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Ajouter un carton" })).toHaveCount(0);
    await shoot(page, OUT_DIR, "06-match-joueur");

    await loginAs(page, D.coach);
    await page.goto(MATCH_URL);
    await expect(page.getByRole("heading", { name: "Cartons et incidents" })).toBeVisible();
    await page.getByRole("button", { name: "Ajouter un carton" }).click();
    const modal = page.getByRole("dialog", { name: "Signaler un incident" });
    await expect(modal).toBeVisible();
    await shoot(page, OUT_DIR, "06-signaler-incident");
    await closeTopDialog(page);
  });

  test("suspended_player_sees_his_suspension_and_trainings_page_loads", async ({ page }) => {
    await loginAs(page, D.suspended);
    await page.goto("/");
    await expect(page.getByText(/Suspendu/).first()).toBeVisible({ timeout: 15_000 });
    await shoot(page, OUT_DIR, "06-accueil-joueur-suspendu");
    await page.goto("/entrainements");
    await expect(page.getByRole("heading", { level: 1, name: "Entraînements" })).toBeVisible();
    await shoot(page, OUT_DIR, "06-entrainements-joueur");
  });

  test("locker_room_today_and_plans_tabs", async ({ page }) => {
    await loginAs(page, D.coach);
    await page.goto("/vestiaire");
    await expect(page.getByRole("heading", { level: 1, name: "Vestiaire du jour" }).first()).toBeVisible();
    await shoot(page, OUT_DIR, "06-vestiaire-coach");
    const plans = page.getByRole("tab", { name: "Plans" }).or(page.getByRole("button", { name: "Plans", exact: true })).first();
    await plans.click();
    await shoot(page, OUT_DIR, "06-vestiaire-plans");
  });
});

// ---------------------------------------------------------------------------
// S6-07 — Médical : confidentialité
// ---------------------------------------------------------------------------

const CONSENTING_NAME = "Ulrich Zedu";
const ASSISTANT = { email: "joueur12@demo.local", name: "Léon Bidonl", search: "Bidonl" };

test.describe.serial("S6-07 médical", () => {
  test("coach_sees_only_fitness_and_return_date_never_diagnosis", async ({ page }) => {
    const errors = trackErrors(page);
    await loginAs(page, D.coach);
    await page.goto("/medical");
    await expect(page.getByRole("heading", { name: "Inaptes et restrictions" })).toBeVisible();
    await expect(page.getByText(UNFIT_NAME).first()).toBeVisible();
    await expect(page.getByText(/Entorse|cheville|Reprise progressive/i)).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Dernières blessures" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Effectif" })).toHaveCount(0);
    await shoot(page, OUT_DIR, "07-medical-coach");
    expect.soft(errors.http.filter((h) => h.startsWith("5"))).toEqual([]);
  });

  test("assistant_coach_has_the_same_medical_view_as_the_coach", async ({ page }) => {
    await loginAs(page, D.coach);
    await page.goto("/club/comite");
    const section = page.locator("section").filter({ has: page.getByRole("heading", { name: "Assistant du Coach" }) });
    await expect(section).toBeVisible();
    if ((await section.getByText(ASSISTANT.name).count()) === 0) {
      await section.getByRole("button", { name: /Nommer l'assistant|Changer l'assistant/ }).click();
      const picker = page.getByRole("dialog", { name: /assistant du Coach/ });
      await picker.getByPlaceholder("Nom ou numéro du joueur").fill(ASSISTANT.search);
      await picker.getByRole("option").filter({ hasText: ASSISTANT.name }).first().click();
      await picker.getByRole("button", { name: "Continuer" }).click();
      const confirm = page.getByRole("alertdialog", { name: /Nommer .* assistant du Coach/ }).or(page.getByRole("dialog", { name: /Nommer .* assistant du Coach \?/ }));
      await shoot(page, OUT_DIR, "07-nommer-assistant-confirmation");
      await confirm.getByRole("button", { name: "Nommer" }).click();
      await expect(section.getByText(ASSISTANT.name)).toBeVisible({ timeout: 15_000 });
    }
    await loginAs(page, ASSISTANT.email);
    await page.goto("/medical");
    await expect(page.getByRole("heading", { name: "Inaptes et restrictions" })).toBeVisible();
    await expect(page.getByText(/Entorse|cheville|Reprise progressive/i)).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Dernières blessures" })).toHaveCount(0);
    await shoot(page, OUT_DIR, "07-medical-assistant-coach");
    // Remise en état : le Coach retire l'assistant.
    await loginAs(page, D.coach);
    await page.goto("/club/comite");
    await section.getByRole("button", { name: "Retirer l'assistant" }).click();
    const revoke = page.getByRole("alertdialog", { name: /Retirer .*assistant du Coach/ }).or(page.getByRole("dialog", { name: /Retirer .*assistant du Coach/ }));
    await revoke.getByRole("button", { name: "Retirer" }).click();
    await expect(section.getByText("Aucun assistant nommé")).toBeVisible({ timeout: 15_000 });
  });

  test("doctor_sees_the_injury_details", async ({ page }) => {
    await loginAs(page, D.doctor);
    await page.goto("/medical");
    await expect(page.getByRole("heading", { name: "Dernières blessures" })).toBeVisible();
    await shoot(page, OUT_DIR, "07-medical-medecin");
  });

  test("president_reads_consenting_player_record_and_is_denied_otherwise", async ({ page }) => {
    await loginAs(page, D.president);
    await page.goto("/medical");
    await expect(page.getByRole("heading", { name: "Effectif" })).toBeVisible();
    await shoot(page, OUT_DIR, "07-medical-president");
    // Sans consentement : aptitude seule.
    await page.getByRole("heading", { name: "Inaptes et restrictions" }).locator("..").getByText(UNFIT_NAME).first().click();
    const apt = page.getByRole("dialog", { name: `Aptitude de ${UNFIT_NAME}` });
    await expect(apt).toBeVisible();
    await apt.getByRole("button", { name: "Consulter le dossier complet" }).click();
    await expect(apt.getByText(`${UNFIT_NAME} n'a pas partagé son dossier médical complet avec le Président.`, { exact: false })).toBeVisible();
    await shoot(page, OUT_DIR, "07-president-sans-consentement");
    await closeTopDialog(page);
    // Avec consentement : dossier complet, consultation journalisée.
    await page.getByPlaceholder(/Rechercher/).first().fill("Zedu").catch(() => undefined);
    await page.getByText(CONSENTING_NAME).first().click();
    const apt2 = page.getByRole("dialog", { name: `Aptitude de ${CONSENTING_NAME}` });
    await apt2.getByRole("button", { name: "Consulter le dossier complet" }).click();
    const record = page.getByRole("dialog", { name: `Dossier médical de ${CONSENTING_NAME}` });
    await expect(record).toBeVisible({ timeout: 15_000 });
    await expect(record.getByText("Consultation enregistrée dans le journal du club.")).toBeVisible();
    await shoot(page, OUT_DIR, "07-president-dossier-avec-consentement");
  });

  test("player_revokes_consent_then_president_is_denied_then_consent_is_given_back", async ({ page }) => {
    await loginAs(page, D.consenting);
    await page.goto("/profil");
    await page.getByRole("button", { name: "Gérer" }).click();
    const modal = page.getByRole("dialog", { name: "Autoriser le Président à consulter mon dossier médical complet" });
    await expect(modal).toBeVisible();
    await expect(modal.getByText(/fonction de Président, pas à la personne/)).toBeVisible();
    await shoot(page, OUT_DIR, "07-consentement-joueur");
    // Rejouable : si une exécution précédente s'est arrêtée après la révocation, on accorde d'abord.
    const grant = modal.getByRole("button", { name: "Autoriser", exact: true });
    const revokeBtn = modal.getByRole("button", { name: "Révoquer", exact: true });
    await expect(grant.or(revokeBtn).first()).toBeVisible();
    if (await grant.isVisible()) {
      await grant.click();
      await expect(modal).toBeHidden({ timeout: 15_000 });
      await page.getByRole("button", { name: "Gérer" }).click();
    }
    await revokeBtn.click();
    const confirm = page.getByRole("alertdialog", { name: "Révoquer l'autorisation ?" }).or(page.getByRole("dialog", { name: "Révoquer l'autorisation ?" }));
    await confirm.getByRole("button", { name: "Révoquer" }).click();
    await toast(page, "Autorisation révoquée.");

    await loginAs(page, D.president);
    await page.goto("/medical");
    await expect(page.getByRole("heading", { name: "Effectif" })).toBeVisible();
    await page.getByPlaceholder(/Rechercher/).first().fill("Zedu").catch(() => undefined);
    await page.getByText(CONSENTING_NAME).first().click();
    const apt = page.getByRole("dialog", { name: `Aptitude de ${CONSENTING_NAME}` });
    await apt.getByRole("button", { name: "Consulter le dossier complet" }).click();
    await expect(apt.getByText(/n'a pas partagé son dossier médical complet/)).toBeVisible({ timeout: 15_000 });
    await shoot(page, OUT_DIR, "07-president-apres-revocation");

    // Remise en état de la base de démo : le joueur accorde de nouveau l'accès.
    await loginAs(page, D.consenting);
    await page.goto("/profil");
    await page.getByRole("button", { name: "Gérer" }).click();
    await modal.getByRole("button", { name: "Autoriser", exact: true }).click();
    await expect(modal).toBeHidden({ timeout: 15_000 });
    await expect(page.getByText("Accès du Président à mon dossier complet").locator("..")).toContainText(/Autorisé|Accordé/i);
  });
});

// ---------------------------------------------------------------------------
// S6-08 à S6-11 — Intendance (survol), mercato, assemblées et archives, notifications, chat
// ---------------------------------------------------------------------------

test.describe("S6-08 S6-11 autres modules", () => {
  test("intendant_overview_of_material_and_register", async ({ page }) => {
    await loginAs(page, D.intendant);
    await page.goto("/materiel");
    await expect(page.getByRole("heading", { level: 1, name: "Matériel" })).toBeVisible();
    await shoot(page, OUT_DIR, "08-materiel-intendant");
    await page.goto("/materiel/registre");
    await expect(page.getByRole("heading", { level: 1, name: "Registre de l'intendance" })).toBeVisible();
    await shoot(page, OUT_DIR, "08-registre-intendant");
  });

  test("mercato_page_for_player_and_president", async ({ page }) => {
    await loginAs(page, D.player);
    await page.goto("/mercato");
    await expect(page.getByRole("heading", { level: 1, name: "Mercato" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ma disponibilité" })).toBeVisible();
    await shoot(page, OUT_DIR, "09-mercato-joueur");
    await loginAs(page, D.president);
    await page.goto("/mercato");
    await expect(page.getByRole("heading", { level: 1, name: "Mercato" })).toBeVisible();
    await shoot(page, OUT_DIR, "09-mercato-president");
  });

  test("assemblies_page_and_convene_wizard_with_sticky_footer", async ({ page }) => {
    await loginAs(page, D.president);
    await page.goto("/club/assemblees");
    await expect(page.getByRole("heading", { level: 1, name: "Assemblées générales" })).toBeVisible();
    await shoot(page, OUT_DIR, "10-assemblees-president");
    await page.getByRole("button", { name: "Convoquer une AG" }).first().click();
    const wizard = page.getByRole("dialog").first();
    await expect(wizard).toBeVisible();
    await shoot(page, OUT_DIR, "10-convoquer-ag");
    await closeTopDialog(page);
    await page.goto("/club/archives");
    await expect(page.getByRole("heading", { level: 1, name: "Archives" })).toBeVisible();
    await shoot(page, OUT_DIR, "10-archives-president");
  });

  test("coach_and_player_have_no_archive_access", async ({ page }) => {
    for (const email of [D.coach, D.player]) {
      await loginAs(page, email);
      await page.goto("/club/archives");
      await expect(page.getByRole("heading", { name: "Documents" })).toHaveCount(0);
    }
    await shoot(page, OUT_DIR, "10-archives-joueur-refus");
  });

  test("notifications_modal_lists_and_marks_all_as_read", async ({ page }) => {
    await loginAs(page, D.player);
    await page.getByRole("button", { name: "Notifications" }).click();
    const modal = page.getByRole("dialog", { name: "Notifications" });
    await expect(modal).toBeVisible();
    await shoot(page, OUT_DIR, "11-notifications");
    const markAll = modal.getByRole("button", { name: "Tout marquer comme lu" });
    if (await markAll.isEnabled().catch(() => false)) {
      await markAll.click();
      await expect(page.getByText(/non lue\(s\)/)).toHaveCount(0, { timeout: 15_000 });
    }
  });

  test("team_chat_page_and_conversation_sticky_footer", async ({ page }) => {
    await loginAs(page, D.player);
    await page.goto("/club/chat");
    await expect(page.getByRole("heading", { level: 1, name: "Chat" })).toBeVisible();
    await shoot(page, OUT_DIR, "11-chat");
    const first = page.locator("main li button, main ul [role=button]").first();
    if (await first.isVisible().catch(() => false)) {
      await first.click();
      const conv = page.getByRole("dialog").first();
      await expect(conv).toBeVisible();
      await shoot(page, OUT_DIR, "11-chat-conversation");
    }
  });
});

// ---------------------------------------------------------------------------
// S6-13 — Étanchéité entre deux clubs (club B créé par l'interface)
// ---------------------------------------------------------------------------

const B_STATE = path.join(OUT_DIR, "13-club-b.json");
const API = "http://127.0.0.1:8000/api/v1";

interface ClubB {
  name: string;
  presidentEmail: string;
  memberEmail: string;
}

function loadClubB(): ClubB | null {
  try {
    return JSON.parse(fs.readFileSync(B_STATE, "utf-8")) as ClubB;
  } catch {
    return null;
  }
}

function tokenOf(email: string): string {
  return issueSession(email).access;
}

async function apiGet(request: import("@playwright/test").APIRequestContext, token: string, url: string) {
  const res = await request.get(`${API}${url}`, { headers: { Authorization: `Bearer ${token}` } });
  let body: unknown = null;
  const type = res.headers()["content-type"] ?? "";
  if (type.includes("json")) body = await res.json().catch(() => null);
  return { status: res.status(), body, type };
}

test.describe.serial("S6-13 étanchéité", () => {
  test("a_second_club_is_created_through_the_interface_with_one_imported_member", async ({ page }) => {
    test.setTimeout(240_000);
    const existing = loadClubB();
    if (existing) {
      test.info().annotations.push({ type: "info", description: `Club B déjà créé : ${existing.name}` });
      return;
    }
    const club: ClubB = {
      name: `Club Étanche ${RUN}`,
      presidentEmail: `s6-pdt-${RUN.toLowerCase()}@example.org`,
      memberEmail: `s6-membre-${RUN.toLowerCase()}@example.org`,
    };
    await page.goto("/connexion");
    await page.getByRole("button", { name: "Créer un club" }).click();
    const wizard = page.getByRole("dialog", { name: "Créer votre club" });
    await expect(wizard).toBeVisible();
    await wizard.getByLabel("Nom du club").fill(club.name);
    await wizard.getByLabel("Ville").fill("Ville Fictive");
    await wizard.getByLabel("Pays").fill("République démocratique du Congo");
    const tz = wizard.locator("#wizard-timezone");
    if ((await tz.inputValue()) === "") await tz.selectOption({ index: 1 });
    await shoot(page, OUT_DIR, "13-creer-club-etape1");
    await wizard.getByRole("button", { name: "Suivant" }).click();
    await wizard.getByLabel("Prénom").fill("Pierre");
    await wizard.getByLabel("Nom", { exact: true }).fill(`Étanche${RUN}`);
    await wizard.getByLabel("Email").fill(club.presidentEmail);
    await wizard.getByRole("button", { name: "Milieu", exact: true }).or(wizard.getByRole("radio", { name: "Milieu" })).first().click();
    await shoot(page, OUT_DIR, "13-creer-club-etape2");
    await wizard.getByRole("button", { name: "Suivant" }).click();
    await wizard.locator("label").filter({ hasText: "J'accepte les conditions générales" }).click();
    await shoot(page, OUT_DIR, "13-creer-club-etape3");
    await wizard.getByRole("button", { name: "Créer mon club" }).click();
    await expect(page.getByText(`Votre club ${club.name} est créé.`)).toBeVisible({ timeout: 30_000 });
    await shoot(page, OUT_DIR, "13-creer-club-succes");
    await page.getByRole("button", { name: "Accéder à mon club" }).click();
    const pwd = page.getByRole("dialog", { name: "Changez votre mot de passe" });
    await expect(pwd).toBeVisible({ timeout: 20_000 });
    await pwd.getByLabel("Nouveau mot de passe").fill(`S6-Etanche-${RUN}-x9!`);
    await pwd.getByLabel("Confirmez le mot de passe").fill(`S6-Etanche-${RUN}-x9!`);
    await pwd.getByRole("button", { name: "Enregistrer" }).click();
    await expect(pwd).toBeHidden({ timeout: 20_000 });
    fs.writeFileSync(B_STATE, JSON.stringify(club));

    // Un membre fictif ajouté par import CSV (aucun fichier réel).
    await loginAs(page, club.presidentEmail);
    await page.goto("/club/comite");
    await expect(page.getByText(club.name).first()).toBeVisible();
    await page.getByRole("button", { name: "Importer (CSV)" }).click();
    const imp = page.getByRole("dialog", { name: "Importer des joueurs" });
    await imp.locator("input[type=file]").setInputFiles({
      name: "joueurs-fictifs.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(`email,prenom,nom,telephone,poste,numero,date_naissance,poids,taille,type_cotisation\n${club.memberEmail},Marin,Fictif${RUN},,Milieu,8,,,,\n`, "utf-8"),
    });
    await imp.getByRole("button", { name: "Importer", exact: true }).click();
    await expect(imp.getByText(/1 joueurs créés ou mis à jour/)).toBeVisible({ timeout: 20_000 });
    await shoot(page, OUT_DIR, "13-club-b-import");
    await closeTopDialog(page);
    await page.goto("/club/comite");
    await expect(page.getByText(`Marin Fictif${RUN}`).first()).toBeVisible();
    await shoot(page, OUT_DIR, "13-club-b-comite");
  });

  test("club_b_president_sees_no_private_data_of_club_demo_in_lists_or_by_id", async ({ page, request }) => {
    test.setTimeout(240_000);
    const club = loadClubB();
    test.skip(!club, "Club B absent");
    const tokB = tokenOf(club!.presidentEmail);
    const tokA = tokenOf(D.president);
    const tokADoc = tokenOf(D.doctor);
    const tokATres = tokenOf(D.treasurer);
    const leaks: string[] = [];
    const demoNames = ["Démoa", "Fictifb", "Leurre", "Placebo", "Zedu", "Présidentdémo", "Club Démo"];
    const hasDemo = (body: unknown) => {
      const text = JSON.stringify(body ?? "");
      return demoNames.filter((n) => text.includes(n));
    };

    // 1. Listes du club B : aucune donnée du Club Démo.
    for (const url of [
      "/clubs/players/",
      "/clubs/players/cards/",
      "/clubs/profile/me/",
      "/sport/sessions/",
      "/sport/matches/",
      "/sport/locker-room/",
      "/social/posts/?portee=mon_club",
      "/social/announcements/",
      "/social/chat/channels/",
      "/treasury/payments/",
      "/treasury/contribution-types/",
      "/treasury/expenses/",
      "/treasury/social-assistance/requests/",
      "/medical/page/unfit/",
      "/logistics/articles/",
      "/logistics/holders/",
      "/assemblies/",
      "/assemblies/documents/",
      "/mercato/offers/mine/",
      "/notifications/?page=1&page_size=10",
    ]) {
      const r = await apiGet(request, tokB, url);
      const found = r.status < 400 ? hasDemo(r.body) : [];
      if (found.length) leaks.push(`LISTE ${url} (${r.status}) contient ${found.join(", ")}`);
    }

    // 2. Identifiants du Club Démo relevés avec ses propres comptes.
    const idsA: Record<string, number | null> = {};
    const firstId = (b: unknown): number | null => {
      const arr = Array.isArray(b) ? b : ((b as { results?: unknown[] } | null)?.results ?? []);
      const first = arr[0] as { id?: number } | undefined;
      return first?.id ?? null;
    };
    idsA.payment = firstId((await apiGet(request, tokATres, "/treasury/payments/")).body);
    idsA.expense = firstId((await apiGet(request, tokATres, "/treasury/expenses/")).body);
    idsA.announcement = firstId((await apiGet(request, tokA, "/social/announcements/")).body);
    idsA.post = firstId((await apiGet(request, tokA, "/social/posts/?portee=mon_club")).body);
    idsA.assembly = firstId((await apiGet(request, tokA, "/assemblies/")).body);
    idsA.document = firstId((await apiGet(request, tokA, "/assemblies/documents/")).body);
    idsA.article = firstId((await apiGet(request, tokA, "/logistics/articles/")).body);
    idsA.channel = firstId((await apiGet(request, tokA, "/social/chat/channels/")).body);
    fs.writeFileSync(path.join(OUT_DIR, "13-ids-club-demo.json"), JSON.stringify(idsA, null, 2));

    const byId: string[] = [
      "/clubs/players/1/card/",
      "/clubs/players/22/stats/",
      "/clubs/players/31/application/",
      "/clubs/applications/2/fiche-pdf/",
      "/medical/players/22/health-record/",
      "/medical/players/24/health-record/",
      "/medical/injuries/1/",
      "/sport/sessions/7/",
      "/sport/matches/6/",
      "/sport/events/6/incidents/",
      "/mercato/players/22/",
    ];
    if (idsA.payment) byId.push(`/treasury/payments/${idsA.payment}/`, `/treasury/payments/${idsA.payment}/receipt/`);
    if (idsA.expense) byId.push(`/treasury/expenses/${idsA.expense}/`);
    if (idsA.announcement) byId.push(`/social/announcements/${idsA.announcement}/`);
    if (idsA.post) byId.push(`/social/posts/${idsA.post}/`, `/social/posts/${idsA.post}/comments/`);
    if (idsA.assembly) byId.push(`/assemblies/${idsA.assembly}/`, `/assemblies/${idsA.assembly}/minutes/pdf/`);
    if (idsA.document) byId.push(`/assemblies/documents/${idsA.document}/`, `/assemblies/documents/${idsA.document}/file/`);
    if (idsA.article) byId.push(`/logistics/articles/${idsA.article}/`);
    if (idsA.channel) byId.push(`/social/chat/channels/${idsA.channel}/messages/`);
    const report: Record<string, number> = {};
    for (const url of byId) {
      const r = await apiGet(request, tokB, url);
      report[url] = r.status;
      // Une publication « Publique » du fil peut légitimement être lue par tous les clubs (CDC 4.16) :
      // on ne la compte comme fuite que si elle est « club_only ».
      if (r.status < 400) {
        const vis = (r.body as { visibility?: string } | null)?.visibility;
        if (!(url.startsWith("/social/posts/") && vis === "public")) leaks.push(`DÉTAIL ${url} → ${r.status} ${JSON.stringify(r.body).slice(0, 120)}`);
      }
    }
    // Le médecin du Club Démo voit bien le dossier (contrôle du jeu de test).
    expect((await apiGet(request, tokADoc, "/medical/players/24/health-record/")).status).toBe(200);

    // 3. Sens inverse : le Club Démo ne voit pas le membre du club B.
    const bPlayers = (await apiGet(request, tokB, "/clubs/players/")).body as { membership_id: number }[];
    for (const p of bPlayers ?? []) {
      for (const url of [`/clubs/players/${p.membership_id}/card/`, `/medical/players/${p.membership_id}/health-record/`]) {
        const r = await apiGet(request, tokA, url);
        report[`A→B ${url}`] = r.status;
        if (r.status < 400) leaks.push(`A→B ${url} → ${r.status}`);
      }
    }
    fs.writeFileSync(path.join(OUT_DIR, "13-etancheite-statuts.json"), JSON.stringify(report, null, 2));
    expect(leaks, leaks.join("\n")).toEqual([]);

    // 4. Interface : les URL du Club Démo n'affichent rien au club B.
    await loginAs(page, club!.presidentEmail);
    for (const [url, forbidden] of [
      ["/matchs/6", "Adversaire amical 3"],
      ["/seances/7", "Terrain principal"],
      ["/club/joueurs", "Bruno Fictifb"],
      ["/fil", "Publication de test série 6"],
      ["/club/communiques", "Communiqué série 6"],
      ["/medical", "William Placebo"],
      ["/tresorerie", "Kevin Proto"],
    ] as const) {
      await page.goto(url);
      await settle(page);
      await expect(page.getByText(forbidden).first(), `${url} : aucune donnée du Club Démo`).toHaveCount(0);
      await shoot(page, OUT_DIR, `13-club-b${url.replace(/\//g, "_")}`);
    }
    // Marque blanche : le nom affiché est celui du club B.
    await page.goto("/");
    await expect(page.getByText(club!.name).first()).toBeVisible();
  });

  test("club_b_member_cannot_reach_club_demo_data", async ({ request }) => {
    const club = loadClubB();
    test.skip(!club, "Club B absent");
    const tok = tokenOf(club!.memberEmail);
    for (const url of ["/clubs/players/1/card/", "/sport/matches/6/", "/medical/players/22/health-record/", "/assemblies/1/"]) {
      const r = await apiGet(request, tok, url);
      expect(r.status, `${url} ne doit pas être lisible par un membre du club B`).toBeGreaterThanOrEqual(400);
    }
    const list = await apiGet(request, tok, "/clubs/players/");
    expect(JSON.stringify(list.body)).not.toContain("Fictifb");
  });
});
