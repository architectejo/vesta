import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";

/**
 * Ouvre une session réelle (CDC 9.3, tâche 5.2) pour un compte du jeu de
 * simulation `fc-malaika` (tâche 5.1, `seed_simulation`), SANS connaître
 * son mot de passe réel : le backend (`python manage.py issue_e2e_session`,
 * réservé à DEBUG=True, voir sa docstring) émet un vrai jeton SimpleJWT
 * (`RefreshToken.for_user`) et l'identité exactement comme
 * `apps.accounts.views.LoginView` — le test ne saute que la saisie du mot
 * de passe, tout le reste (résolution du club actif par adhésion réelle,
 * CLAUDE.md règle n9 ; permissions par rôle) reste le comportement réel du
 * serveur.
 */

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BACKEND_DIR = path.resolve(__dirname, "../../../backend");
const PYTHON_BIN = path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe");

interface SessionPayload {
  access: string;
  refresh: string;
  user: {
    id: number;
    email: string;
    first_name: string;
    last_name: string;
    is_superuser: boolean;
    must_change_password: boolean;
    preferred_theme: string;
  };
  club: {
    id: number;
    slug: string;
    name: string;
    logo: string | null;
    primary_color: string;
    secondary_color: string;
  } | null;
}

export function issueSession(email: string): SessionPayload {
  const result = spawnSync(
    PYTHON_BIN,
    ["manage.py", "issue_e2e_session", "--email", email],
    { cwd: BACKEND_DIR, encoding: "utf-8" },
  );
  if (result.status !== 0) {
    throw new Error(
      `issue_e2e_session a échoué pour ${email} (code ${result.status}) :\n` +
        `stdout: ${result.stdout}\nstderr: ${result.stderr}`,
    );
  }
  const lastLine = result.stdout
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .pop();
  if (!lastLine) {
    throw new Error(`issue_e2e_session n'a produit aucune sortie pour ${email}.`);
  }
  return JSON.parse(lastLine) as SessionPayload;
}

/**
 * Ouvre la session dans CET onglet Playwright : injecte les jetons et
 * l'identité en `sessionStorage` (format exact de `frontend/src/auth/session.ts`,
 * clés `vesta:access`/`vesta:refresh`/`vesta:identity`) AVANT de naviguer,
 * puis charge la page d'accueil du club.
 */
export async function loginAs(page: Page, email: string): Promise<SessionPayload> {
  const session = issueSession(email);
  // sessionStorage n'existe qu'après une première navigation vers l'origine.
  await page.goto("/connexion");
  await page.evaluate(
    ([access, refresh, identity]) => {
      window.sessionStorage.setItem("vesta:access", access as string);
      window.sessionStorage.setItem("vesta:refresh", refresh as string);
      window.sessionStorage.setItem("vesta:identity", identity as string);
      // Supprime l'invite non bloquante « Ajoutez votre photo » (OnboardingGate
      // / PhotoPromptModal) : hors sujet pour ce parcours de recette, mais son
      // fond opaque intercepte quand même les clics tant qu'elle n'est pas
      // écartée une première fois (comportement normal pour un vrai nouvel
      // utilisateur, gênant seulement parce que chaque connexion de test est
      // la "première" sur une page fraîche).
      window.sessionStorage.setItem("vesta:photo-prompt-seen", "1");
    },
    [
      session.access,
      session.refresh,
      JSON.stringify({ user: session.user, club: session.club }),
    ],
  );
  await page.goto("/");
  return session;
}
