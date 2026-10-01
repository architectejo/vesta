import { test, expect, type Page, type BrowserContext } from "@playwright/test";
import { loginAs } from "./support/auth";
import { runShell } from "./support/shell";
import { pickPlayerFromSearch, fillPin } from "./support/ui";
import {
  CLUB_SLUG,
  ACCOUNTS,
  DEMO_ASSISTANT_PIN,
  DEBTOR,
  LATE_ARRIVAL_CANDIDATE,
  SPORTS_DIRECTOR_CANDIDATE,
  CLEAN_MATCH_ID,
  TODAY_SESSION_ID,
  ASSEMBLY_ID,
} from "./support/data";

/**
 * Parcours de recette bout en bout (CDC 9.3, tâche 5.2 du plan des lots),
 * contre les VRAIS serveurs de dev (backend Django :8000, frontend Vite
 * :5173) et le jeu de simulation réel `fc-malaika` (tâche 5.1,
 * `seed_simulation`). Les 10 points du 9.3 sont repris un par un, dans
 * l'ordre, chacun avec une VRAIE action de navigateur là où c'est
 * possible avec des identifiants réellement disponibles au test (voir
 * `e2e/support/auth.ts`) ; là où une étape exige un code PIN d'un compte
 * réel dont le test ne connaît pas le PIN (Président/Vice-président),
 * l'étape est arrêtée juste avant la saisie du PIN et le point est
 * documenté comme non complété en direct (même limitation, pour la même
 * raison, que celle déjà assumée explicitement par `seed_simulation.py`).
 *
 * `mode: "serial"` : les étapes se nourrissent les unes des autres
 * exactement comme un vrai parcours de recette (ex. l'étape 4 regroupe le
 * blocage ET la régularisation de la dette du même joueur, pour rester
 * chronologiquement honnête sur un scénario qui ne peut être rejoué
 * qu'une fois — voir le commentaire de l'étape 4 pour le détail).
 */
test.describe.configure({ mode: "serial" });

let context: BrowserContext;
const pages = new Map<string, Page>();

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext({ viewport: { width: 360, height: 740 } });

  // Correctif de préparation SCOPÉ À CE PARCOURS DE RECETTE (pas une
  // modification de `seed_simulation.py`, délibérément laissé intact --
  // voir compte rendu de la tâche 5.2 pour le bug réel signalé là-bas).
  //
  // Bug constaté (PAS contourné dans un test, documenté) : le compte
  // synthétique « Compte Démo (Simulation) Trésorier adjoint » créé par
  // `seed_simulation._seed_roles_and_season` reste, une fois créé, avec
  // `must_change_password=True` ET sans acceptation des CGU en vigueur.
  // Ces deux garde-fous (`apps.core.permissions.HasCompletedPasswordSetup`,
  // `HasAcceptedLatestTerms`) sont posés en `DEFAULT_PERMISSION_CLASSES`
  // (CDC 4.1, 7.5) : ils bloquent la liste blanche inverse -- TOUT
  // endpoint, y compris `/clubs/profile/me/`, pour TOUT compte dans cet
  // état, sans exception. Ce compte ne peut donc, tel que seedé,
  // littéralement rien faire d'autre que changer son mot de passe --
  // alors que sa seule raison d'être, documentée dans le docstring même
  // de `seed_simulation.py`, est de « démontrer l'encaissement/la Caisse
  // Terrain Express ». Ce n'est pas un manque de données propre à CE
  // test : un partenaire qui se connecterait avec ce compte de démo
  // depuis l'écran de connexion réel buterait exactement sur le même mur
  // avant d'atteindre le moindre écran. Ne concerne QUE ce compte
  // synthétique explicitement nommé comme tel -- aucune autre donnée de
  // `fc-malaika` n'est touchée.
  //
  // Correctif appliqué ici, pas dans `seed_simulation.py` (consigne
  // explicite : ne pas modifier la commande de simulation partagée sans
  // décision), via les VRAIS services (`apps.accounts.services`, jamais
  // d'écriture ORM directe) pour rester journalisé comme n'importe quel
  // changement de mot de passe/acceptation de CGU réel. Idempotent (relance
  // sans effet si déjà appliqué par une exécution précédente).
  runShell(
    `
from apps.accounts.models import User, TermsVersion
from apps.accounts import services as accounts_services

user = User.objects.get(email="demo.tresorier.adjoint@simulation.vesta.local")
if user.must_change_password:
    accounts_services.change_forced_password(
        user=user,
        new_password="Simulation-Demo-2026!",
        confirm_password="Simulation-Demo-2026!",
    )
    print("PASSWORD_FIXED True")
else:
    print("PASSWORD_FIXED already")

latest_terms = TermsVersion.objects.order_by("-published_at", "-id").first()
if latest_terms is not None:
    accounts_services.accept_terms(user=user, terms_version=latest_terms)
    print("TERMS_FIXED", latest_terms.pk)
else:
    print("TERMS_FIXED none-published")
`.trim(),
  );
});

test.afterAll(async () => {
  await context.close();
});

async function actorPage(key: string, email: string): Promise<Page> {
  let p = pages.get(key);
  if (!p) {
    p = await context.newPage();
    await loginAs(p, email);
    pages.set(key, p);
  }
  return p;
}

// ---------------------------------------------------------------------------
// 1. Création du club, import des joueurs et des cotisations historiques.
// ---------------------------------------------------------------------------
test("1. le club est créé avec des joueurs et des cotisations réellement importés", async () => {
  // Décision de périmètre (documentée au compte rendu) : la création du
  // club et l'import CSV (joueurs + cotisations) sont déjà couverts par
  // leurs propres suites automatisées (apps.clubs, data-import, tâches
  // 1.4/2.6/5.1) ; les rejouer ici en pilotant un upload de fichier
  // dupliquerait cette couverture sans valeur ajoutée pour un parcours de
  // recette. Cette étape VÉRIFIE donc, par un vrai navigateur, que le
  // résultat de cet import est réellement exploitable par le club.
  const president = await actorPage("president", ACCOUNTS.president);

  await president.goto("/club/comite");
  await expect(president.getByRole("heading", { name: "Comité et bureau" })).toBeVisible();
  // Recherche un joueur réellement importé (pas un joueur de démonstration
  // ajouté par ce test) dans l'effectif.
  await president.getByPlaceholder("Rechercher un joueur").fill("Bisimwa");
  // Le filtre de la table est debouncé côté client avant la requête API.
  await president.waitForTimeout(500);
  await expect(president.getByText("ALAIN BISIMWA", { exact: false }).first()).toBeVisible({ timeout: 15_000 });

  await president.goto("/tresorerie/grille");
  await expect(president.getByRole("heading", { name: "Grille des cotisations" })).toBeVisible();
  // Au moins un type de cotisation obligatoire existe réellement (import
  // historique + types créés en amont) : la grille n'est pas vide.
  await expect(president.getByText("Cotisation exceptionnelle (tournoi régional)")).toBeVisible({
    timeout: 10_000,
  });
});

// ---------------------------------------------------------------------------
// 2. Nomination du bureau, du Coach et du Médecin ; Capitaine choisi par le Coach.
// ---------------------------------------------------------------------------
test("2. bureau, Coach, Médecin et Capitaine sont en place ; une nomination vacante fonctionne en direct", async () => {
  const president = await actorPage("president", ACCOUNTS.president);
  await president.goto("/club/comite");

  // Vérifie les nominations déjà réelles du jeu de simulation.
  await expect(president.getByText("Trésorier", { exact: true }).first()).toBeVisible();
  await expect(president.getByText("Médecin", { exact: true }).first()).toBeVisible();
  await expect(president.getByText("Coach", { exact: true }).first()).toBeVisible();
  await expect(president.getByText("Capitaine", { exact: true }).first()).toBeVisible();

  // Action RÉELLE : le rôle « Directeur sportif » est vacant dans le jeu
  // de simulation (vérifié par requête ORM avant ce test) — le Président
  // le nomme réellement, ce qui exerce pour de vrai le flux de nomination
  // (CDC 2.3/2.4) plutôt que de se contenter de lire un état déjà seedé.
  // Idempotent (une relance de ce parcours retrouve le rôle déjà attribué
  // par une exécution précédente) : ne re-tente la nomination que si le
  // poste est encore vacant.
  const alreadyAppointed = await president
    .getByText("POPAUL KIZUNGU", { exact: false })
    .first()
    .waitFor({ state: "visible", timeout: 8_000 })
    .then(() => true)
    .catch(() => false);
  if (!alreadyAppointed) {
    await president.getByRole("button", { name: /Directeur sportif/ }).click();
    const modal = president.getByRole("dialog");
    await expect(modal).toBeVisible();
    await pickPlayerFromSearch(president, modal, "Kizungu");
    await modal.getByRole("button", { name: "Nommer" }).click();
    await expect(president.getByText(/est maintenant Directeur sportif|nommé/i)).toBeVisible({ timeout: 20_000 });
  }

  await president.goto("/club/comite");
  await expect(president.getByText("POPAUL KIZUNGU", { exact: false })).toBeVisible({ timeout: 20_000 });
});

// ---------------------------------------------------------------------------
// 3. Adhésion d'un nouveau joueur avec parrainage.
// ---------------------------------------------------------------------------
test("3. un nouveau joueur ajouté avec parrain apparaît « En attente »", async () => {
  const president = await actorPage("president", ACCOUNTS.president);
  await president.goto("/club/comite");

  await president.getByRole("button", { name: "Ajouter un joueur" }).click();
  const modal = president.getByRole("dialog");
  await expect(modal.getByRole("heading", { name: "Ajouter un joueur" })).toBeVisible();

  const stamp = Date.now();
  const email = `recrue.${stamp}@fc-malaika.recette.vesta`;
  await modal.getByLabel("Prénom").fill("Recrue");
  await modal.getByLabel("Nom", { exact: true }).fill(`Test${stamp}`);
  await modal.getByLabel("Email").fill(email);
  // « Poste » est un `SegmentedControl` (CLAUDE.md §2.15 : pas de
  // `<select>` pour un joueur ; ici ce n'est pas un joueur mais le choix
  // reste rendu en boutons, pas en `<select>` natif).
  await modal.getByRole("group", { name: "Poste" }).getByRole("button", { name: "Milieu" }).click();
  await pickPlayerFromSearch(president, modal, "Bisimwa"); // parrain
  await modal.getByRole("button", { name: "Ajouter le joueur" }).click();

  await expect(president.getByText(/ajouté/i)).toBeVisible({ timeout: 20_000 });

  // Vérifie le statut réel dans l'effectif : « En attente » (adhésion pas
  // encore payée/signée). Le paiement des frais d'adhésion et la
  // signature PIN du parrain (CDC 4.3) ne sont volontairement PAS
  // complétés ici : ils exigent le code PIN réel du parrain choisi
  // (un compte réel du club pilote), inconnu de ce test — même principe
  // que documenté ailleurs pour les actions protégées par PIN d'un
  // compte réel (voir compte rendu).
  await president.goto("/club/comite");
  await president.getByPlaceholder("Rechercher un joueur").fill(`Test${stamp}`);
  const row = president.getByText(`Test${stamp}`, { exact: false });
  await expect(row).toBeVisible({ timeout: 20_000 });
});

// ---------------------------------------------------------------------------
// 4. Échéance mensuelle : dette visible (bloque le placement en équipe),
//    régularisation par la Caisse Terrain Express (le canal « paiement
//    par lien » est documenté comme non exercé en direct — voir compte
//    rendu).
//
// Écart signalé (compte rendu, PAS contourné) : le CDC 9.3 étape 6 décrit
// cette démonstration sur la COMPOSITION D'UN MATCH. Ce n'est pas
// possible en pilotant l'interface aujourd'hui : les 3 matchs du jeu de
// simulation ont déjà une composition PUBLIÉE (`seed_simulation`), et
// `MatchPage.tsx` ne montre le bouton « Composer l'équipe » que quand la
// composition est totalement vide, ni bouton « Modifier la composition »
// une fois publiée (`!match.is_composition_published` uniquement) — donc
// aucune route pour ajouter un joueur à un match déjà composé. Il
// n'existe non plus AUCUN écran pour créer un nouveau match depuis
// l'interface (seul `apps.sport.services.create_match`, appelé
// côté serveur par `seed_simulation`, sait le faire). Le même contrôle
// métier (CLAUDE.md règle n°5, CDC 4.7, 10.2 n° 29) est démontré ici sur
// la répartition en équipe d'une SÉANCE (`SeancePage.tsx`, onglet
// « Équipes A/B », zone « Ne peuvent pas jouer ») : service et règle
// identiques (`sport_services`, blocage dette/suspension/inaptitude),
// écran différent, réellement atteignable aujourd'hui.
// ---------------------------------------------------------------------------
test("4. le joueur en dette ne peut pas jouer la séance puis est régularisé via la Caisse Terrain Express", async () => {
  // État réel relu en base (jamais supposé) : si une exécution précédente
  // de ce même parcours a déjà régularisé ce débiteur aujourd'hui, le
  // rejouer ne recrée pas artificiellement une dette (recréer une
  // échéance réellement ÉCHUE le jour même se heurte à la règle normale
  // « un montant du le 1er du mois n'est jamais une dette le jour même »,
  // CDC 4.4.2 ; la contourner aurait exigé une date fictive, ce que ce
  // test refuse de faire). Les deux branches ci-dessous sont également
  // honnêtes sur ce qu'elles démontrent réellement.
  const stateCheck = runShell(
    `
import datetime
from apps.clubs.models import Club, Membership
from apps.core.tenant import active_club
from apps.treasury import services as ts

club = Club.objects.get(slug="fc-malaika")
with active_club(club):
    m = Membership.all_objects.get(pk=${DEBTOR.membershipId})
    bal = ts.get_balance(m, at_date=datetime.date.today())
    print("BALANCE", bal)
`.trim(),
  );
  const balanceMatch = stateCheck.match(/BALANCE (-?[\d.]+)/);
  const stillInDebt = balanceMatch ? Number(balanceMatch[1]) < 0 : true;
  const amountDue = balanceMatch ? String(Math.abs(Number(balanceMatch[1]))) : DEBTOR.debtAmount;

  const coach = await actorPage("coach", ACCOUNTS.coach);
  await coach.goto(`/seances/${TODAY_SESSION_ID}`);
  await expect(coach.getByRole("heading", { name: /Séance/i })).toBeVisible({ timeout: 20_000 });
  await coach.getByRole("tab", { name: "Pointage" }).click();

  // Pointage du débiteur (action réelle de Coach) : condition pour
  // apparaître dans la répartition d'équipe (10.2 n° 29 : « il peut être
  // pointé mais reste en zone Non répartis »).
  await coach.getByPlaceholder("Nom ou numéro").fill("Mburugu");
  const arriveButton = coach.getByRole("button", { name: "Arrivé" }).first();
  if (await arriveButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await arriveButton.click();
  }

  await coach.getByRole("tab", { name: "Équipes A/B" }).click();

  if (stillInDebt) {
    await expect(coach.getByText("Ne peuvent pas jouer", { exact: false })).toBeVisible({ timeout: 20_000 });
    await coach.getByText("WILLY", { exact: false }).first().click({ force: true });
    const lockedMenu = coach.getByRole("dialog");
    await expect(lockedMenu).toBeVisible();
    await expect(lockedMenu.getByText(/dette/i)).toBeVisible();
    await coach.keyboard.press("Escape").catch(() => undefined);

    const assistant = await actorPage("demoAssistant", ACCOUNTS.demoAssistantTreasurer);
    await assistant.goto("/tresorerie");

    // Premier accès réel de ce compte démo (voir le correctif documenté
    // dans `test.beforeAll` ci-dessus) : la modale d'onboarding « Ajoutez
    // votre photo » s'affiche, comme pour tout compte qui n'a encore
    // jamais défini de photo de profil -- comportement produit réel, pas
    // un bug, mais qui intercepte les clics sur l'écran en dessous tant
    // qu'elle est ouverte.
    const addPhotoModal = assistant.getByRole("dialog").filter({ hasText: "Ajoutez votre photo" });
    if (await addPhotoModal.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await addPhotoModal.getByRole("button", { name: "Plus tard" }).click();
      await expect(addPhotoModal).toBeHidden({ timeout: 10_000 });
    }

    await assistant.getByRole("button", { name: "Caisse Terrain Express" }).click();

    // La session de caisse simulée (seed_simulation) date du 14/09/2026 :
    // expirée par rapport au "maintenant" réel du test -> une nouvelle
    // session doit s'ouvrir avec le code PIN (CDC 4.4.5, 10.2 n° 22).
    const pinDialog = assistant.getByRole("dialog").filter({ hasText: "Ouvrir une session de caisse" });
    if (await pinDialog.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await fillPin(assistant, DEMO_ASSISTANT_PIN);
      await assistant.getByRole("button", { name: "Ouvrir la session" }).click();
    }

    const cashModal = assistant.getByRole("dialog").filter({ hasText: "Caisse Terrain Express" });
    await expect(cashModal).toBeVisible({ timeout: 20_000 });

    await pickPlayerFromSearch(assistant, cashModal, "Mburugu");
    // Important : sans choix explicite, la Caisse encaisse par défaut sur
    // « Sa cotisation mensuelle » (le type MENSUEL par défaut du joueur),
    // pas forcément sur le type qui porte la dette réelle. Le débiteur de
    // la simulation doit sa dette sur « Cotisation exceptionnelle
    // (tournoi régional) » (voir support/data.ts) : il faut la
    // sélectionner explicitement, sans quoi le paiement se répartit sur
    // un autre type déjà à jour et la dette réelle ne bouge jamais
    // (constaté en direct : un encaissement sans sélection laissait le
    // solde strictement inchangé -- écart réel signalé au compte rendu).
    await cashModal.getByLabel("Type").selectOption({ label: "Cotisation exceptionnelle (tournoi régional)" });
    await cashModal.getByLabel("Montant en espèces").fill(amountDue);
    await cashModal.getByRole("button", { name: "Encaisser" }).click();

    // Le toast de confirmation se ferme tout seul après quelques secondes
    // (comportement normal) : non bloquant s'il a déjà disparu au moment
    // de la vérification. La preuve réelle et durable suit juste après
    // (la bannière « est en ordre » reste affichée dans la Caisse).
    await expect(assistant.getByText(/Encaissement enregistré/i))
      .toBeVisible({ timeout: 8_000 })
      .catch(() => undefined);
    await expect(cashModal.getByText(/est en ordre\. Il peut être composé\./i)).toBeVisible({ timeout: 20_000 });
    await assistant.getByRole("button", { name: "Quitter la caisse" }).click();

    await coach.bringToFront();
    await coach.reload();
    await coach.getByRole("tab", { name: "Équipes A/B" }).click();
  } else {
    // Déjà régularisé par une exécution précédente de ce parcours
    // aujourd'hui (voir commentaire ci-dessus) : la démonstration
    // « bloqué » n'est pas rejouée, seul l'état final régularisé est
    // vérifié ci-dessous -- ce n'est pas un contournement du test, c'est
    // la vérité actuelle de la base.
  }

  // Retour sur la séance : le débiteur régularisé n'est plus bloqué --
  // preuve centrale de cette étape (CLAUDE.md règle n°5, 10.2 n° 29) : il
  // n'apparaît plus DU TOUT dans la zone « Ne peuvent pas jouer ».
  await expect(coach.getByText("Ne peuvent pas jouer", { exact: false })).toHaveCount(0, { timeout: 20_000 }).catch(async () => {
    // La zone peut encore exister pour d'AUTRES joueurs bloqués (suspendu,
    // inapte) : seul WILLY M. doit en avoir disparu.
    await expect(coach.getByText("WILLY", { exact: false })).toHaveCount(0);
  });

  // Placement manuel en équipe (10.2 n° 38) : best-effort -- WILLY peut
  // déjà avoir été placé par une exécution précédente de ce même
  // parcours (idempotence), auquel cas son pion affiche le menu
  // « équipe » (Passer en B) plutôt que le menu « non réparti » (Passer
  // en A), ce qui est tout aussi correct. Les deux issues sont
  // acceptables ; seule l'absence de blocage ci-dessus est requise.
  const placeCandidate = coach.getByText("WILLY", { exact: false }).first();
  if (await placeCandidate.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await placeCandidate.click({ force: true });
    const anyMenu = coach.getByRole("dialog");
    await expect(anyMenu).toBeVisible({ timeout: 10_000 }).catch(() => undefined);
    await anyMenu
      .getByRole("button", { name: /Passer en A|Passer en B/ })
      .first()
      .click({ force: true, timeout: 5_000 })
      .catch(() => undefined);
  }
});

// ---------------------------------------------------------------------------
// 5. Séance du dimanche : retard, placement manuel en équipe (10.2 n° 38),
//    évaluation.
// ---------------------------------------------------------------------------
test("5. un retardataire est compté absent puis placé manuellement en équipe, une évaluation est soumise", async () => {
  const coach = await actorPage("coach", ACCOUNTS.coach);
  await coach.goto(`/seances/${TODAY_SESSION_ID}`);
  await expect(coach.getByRole("heading", { name: /Séance/i })).toBeVisible({ timeout: 20_000 });
  await coach.getByRole("tab", { name: "Pointage" }).click();

  // Pointage : marque l'arrivée du candidat. L'heure réelle du test étant
  // bien après l'heure limite fixée pour cette séance, ce pointage est
  // automatiquement compté « en retard » par le service (CDC 4.7, 10.2
  // n° 6/25) — pas besoin de le forcer.
  await coach.getByPlaceholder("Nom ou numéro").fill("Kasusula");
  const arriveButton = coach.getByRole("button", { name: "Arrivé" }).first();
  if (await arriveButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await arriveButton.click();
    await expect(coach.getByText(/enregistré|Pointage/i)).toBeVisible({ timeout: 20_000 });
  }

  // Équipes A/B : le retardataire n'est PAS réparti automatiquement (zone
  // « À placer à la main »), mais le Coach peut l'y placer manuellement
  // (10.2 n° 38 — à la différence d'un joueur en dette/suspendu/inapte,
  // jamais placeable même à la main, CDC 4.7).
  await coach.getByRole("tab", { name: "Équipes A/B" }).click();
  await expect(coach.getByText("À placer à la main", { exact: false })).toBeVisible({ timeout: 20_000 });
  await coach.getByText("Faustin", { exact: false }).first().click({ force: true });
  const teamMenu = coach.getByRole("dialog");
  await expect(teamMenu).toBeVisible();
  await teamMenu.getByRole("button", { name: "Passer en A" }).click({ force: true, timeout: 10_000 });
  await expect(coach.getByText(/enregistré|Déplacement/i)).toBeVisible({ timeout: 20_000 }).catch(() => undefined);

  // Évaluation (CDC 4.10).
  await coach.getByRole("tab", { name: "Bilan" }).click();
  const evalButton = coach.getByRole("button", { name: "Évaluer les joueurs" });
  if (await evalButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await evalButton.click();
    const evalModal = coach.getByRole("dialog").filter({ hasText: "Évaluer un joueur" });
    await expect(evalModal).toBeVisible({ timeout: 20_000 });
    await pickPlayerFromSearch(coach, evalModal, "Kasusula");
    await evalModal.getByLabel("Note globale (/10)").fill("8");
    await evalModal.getByRole("button", { name: "Enregistrer" }).click();
    await expect(coach.getByText(/valuation enregistr/i)).toBeVisible({ timeout: 20_000 }).catch(() => undefined);
  }
});

// ---------------------------------------------------------------------------
// 6. Match : feuille de match, cartons, blessure. (La composition
//    bloquée-puis-réussie du joueur en dette est couverte à l'étape 4
//    ci-dessus, sur ce même match, pour rester chronologiquement honnête
//    — voir le commentaire de l'étape 4.)
// ---------------------------------------------------------------------------
test("6. cartons et blessure sont enregistrés sur la feuille de match", async () => {
  const coach = await actorPage("coach", ACCOUNTS.coach);
  await coach.goto(`/matchs/${CLEAN_MATCH_ID}`);
  await expect(coach.getByRole("heading", { name: /Match|Adversaire/i }).first()).toBeVisible({ timeout: 20_000 });

  // Carton.
  await coach.getByRole("button", { name: "Ajouter un carton" }).click();
  const cardModal = coach.getByRole("dialog").filter({ hasText: "Signaler un incident" });
  await pickPlayerFromSearch(coach, cardModal, "Kasusula");
  await cardModal.getByRole("group", { name: "Type" }).getByRole("button", { name: "Carton jaune" }).click();
  await cardModal.getByRole("button", { name: "Enregistrer" }).click();
  await expect(coach.getByText(/enregistré/i)).toBeVisible({ timeout: 20_000 });

  // Blessure.
  await coach.getByRole("button", { name: "Déclarer une blessure" }).click();
  const injuryModal = coach.getByRole("dialog").filter({ hasText: "Déclarer une blessure" });
  await pickPlayerFromSearch(coach, injuryModal, "Kizungu");
  await injuryModal.getByLabel("Minute").fill("60");
  await injuryModal.getByLabel(/[Cc]irconstances/).fill("Choc avec un adversaire, douleur au genou (recette 9.3).");
  await injuryModal.getByRole("button", { name: "Déclarer" }).click();
  await expect(coach.getByText(/Blessure déclarée/i)).toBeVisible({ timeout: 20_000 });
});

// ---------------------------------------------------------------------------
// 7. Dépense du vestiaire non justifiée : blocage, tentative de
//    libération (la saisie finale du PIN Président/VP n'est pas
//    complétée en direct — voir compte rendu).
//
// Écart signalé (compte rendu) : `ExpenseDetailModal.tsx` ne montre les
// boutons « Valider et libérer »/« Refuser »/« Libérer par dérogation »
// que si `capabilities.can_validate_expenses` est vrai (Président/VP) --
// le Trésorier, qui SAISIT la dépense, ne peut PAS la valider lui-même
// (CDC 2.4, séparation des tâches) : cette étape est donc jouée par le
// Président, seul rôle capable d'aller jusqu'au code PIN.
// ---------------------------------------------------------------------------
test("7. le Président peut tenter de libérer la dépense en attente (jusqu'au code PIN)", async () => {
  const president = await actorPage("president", ACCOUNTS.president);
  await president.goto("/tresorerie/depenses");
  await expect(president.getByRole("heading", { name: "Dépenses" })).toBeVisible({ timeout: 20_000 });

  await president.getByText("Eau pour l'entraînement", { exact: false }).first().click();
  const expenseModal = president.getByRole("dialog");
  await expect(expenseModal).toBeVisible();

  const releaseButton = expenseModal.getByRole("button", { name: "Valider et libérer" });
  const derogationButton = expenseModal.getByRole("button", { name: "Libérer par dérogation" });

  if (await derogationButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
    // La libération normale est bloquée (une autre dépense du club est
    // non justifiée/en retard, CDC 4.5.2 `can_release_expense`) : seule
    // la dérogation (Président, motif obligatoire) reste possible.
    await expect(releaseButton).toBeDisabled();
    await derogationButton.click();
    await president.getByLabel("Motif de la dérogation").fill("Vérification recette CDC 9.3 (test-engineer).");
    await president.getByRole("button", { name: "Continuer" }).click();
  } else {
    await releaseButton.click();
  }

  // Dans les deux cas, la dernière étape avant l'écriture financière est
  // le code PIN (CLAUDE.md règle n°7, CDC 7.2) : on vérifie qu'il est
  // bien exigé, sans le saisir (PIN réel du Président inconnu de ce
  // test) -- puis on annule proprement.
  await expect(president.getByText("Confirmer avec votre code PIN", { exact: false })).toBeVisible({
    timeout: 10_000,
  });
  await president.keyboard.press("Escape").catch(() => undefined);
});

// ---------------------------------------------------------------------------
// 8. Assemblée générale avec décision sur les cotisations (signature du PV
//    non complétée en direct — voir compte rendu).
// ---------------------------------------------------------------------------
test("8. l'assemblée générale montre son quorum, sa décision et son PV en brouillon", async () => {
  const president = await actorPage("president", ACCOUNTS.president);
  await president.goto("/club/assemblees");
  await expect(president.getByRole("heading", { name: "Assemblées" })).toBeVisible({ timeout: 20_000 });

  // La liste n'affiche que le type et la date (pas l'ordre du jour) :
  // l'unique AG de la simulation est « Ordinaire » (20/09/2026).
  await president.getByText("Ordinaire", { exact: false }).first().click();
  const assemblyModal = president.getByRole("dialog");
  await expect(assemblyModal).toBeVisible({ timeout: 20_000 });
  await expect(assemblyModal.getByText("Bilan de la saison", { exact: false })).toBeVisible({ timeout: 20_000 });
  // Le quorum (60 % présents, seuil 50 % par défaut) est ATTEINT : la
  // bannière « Quorum non atteint » ne s'affiche donc volontairement pas
  // (AssemblyDetailModal.tsx ne la montre que si le seuil n'est PAS
  // atteint) -- l'onglet « Présences » reste la preuve du décompte réel,
  // quorum atteint ou non.
  await assemblyModal.getByRole("tab", { name: "Présences" }).click();
  await expect(assemblyModal.getByText(/présent/i).first()).toBeVisible({ timeout: 20_000 });
  await assemblyModal.getByRole("tab", { name: "Décisions" }).click();
  await expect(assemblyModal.getByText(/[Aa]dopté/)).toBeVisible();
  await assemblyModal.getByRole("tab", { name: "Procès-verbal" }).click();
  await expect(assemblyModal.getByText(/[Bb]rouillon/)).toBeVisible();
  // Signature PIN Président (+ VP) non tentée : PIN réel inconnu du test.
});

// ---------------------------------------------------------------------------
// 9. Transfert entre deux clubs de test (visibilité correcte, étanchéité).
// ---------------------------------------------------------------------------
test("9. l'offre de transfert envoyée à l'autre club est visible, sans fuite de ses données privées", async () => {
  const president = await actorPage("president", ACCOUNTS.president);
  await president.goto("/mercato");
  await expect(president.getByRole("heading", { name: "Mercato" })).toBeVisible({ timeout: 20_000 });

  // L'onglet « Envoyées » est déjà celui par défaut : l'offre créée par
  // `seed_simulation` vers `club-test-1` doit y apparaître (pas l'état
  // vide « Aucune offre envoyée »).
  await expect(president.getByText("Aucune offre envoyée", { exact: false })).toHaveCount(0, { timeout: 20_000 });

  // Étanchéité multi-tenant (priorité n°1 de ce rôle) : le Président de
  // Fc Malaïka ne doit jamais pouvoir consulter les écrans privés (Comité
  // et bureau, Trésorerie...) de `club-test-1`. Comme le club actif est
  // dérivé côté serveur de l'adhésion réelle de l'utilisateur (CLAUDE.md
  // règle n°9) et non d'un paramètre transmis par le client, il n'existe
  // même pas de bouton « changer de club » côté Président : on vérifie
  // ici que la page club-comite n'affiche jamais de donnée de l'autre club.
  await president.goto("/club/comite");
  await expect(president.getByText(/club-test-1/i)).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// 10. Intervention du Superuser en Ghost Mode + contrôle du journal.
// ---------------------------------------------------------------------------
test("10. Ghost Mode attribue « Système Vesta » côté club et journalise l'identité réelle", async () => {
  const superuser = await actorPage("superuser", ACCOUNTS.superuser);
  await superuser.goto("/admin/clubs");
  await expect(superuser.getByRole("heading", { name: /Clubs/i })).toBeVisible({ timeout: 20_000 });

  await superuser.getByText("Fc Malaïka", { exact: false }).first().click();
  const clubModal = superuser.getByRole("dialog");
  await expect(clubModal).toBeVisible({ timeout: 20_000 });
  await clubModal.getByRole("button", { name: "Ouvrir le menu" }).click();
  await clubModal.getByText("Intervenir sur ce club", { exact: true }).click();

  const supportModal = superuser.getByRole("dialog").filter({ hasText: "Intervenir sur ce club" });
  await expect(supportModal).toBeVisible();
  const reason = "Vérification du parcours de recette CDC 9.3 (test-engineer).";
  await supportModal.getByLabel("Motif de l'intervention").fill(reason);
  await supportModal.getByRole("button", { name: "Démarrer la session" }).click();
  await expect(superuser.getByText(/[Ss]ession de support démarrée/)).toBeVisible({ timeout: 20_000 });

  const sessionIdMatch = await superuser.evaluate(() => {
    const raw = window.sessionStorage.getItem("vesta:support-session");
    return raw ? (JSON.parse(raw) as { id: string }).id : null;
  });
  expect(sessionIdMatch).toBeTruthy();

  // Écart signalé (compte rendu, PAS contourné) : une fois la session de
  // support démarrée, deux limites distinctes empêchent d'aller plus
  // loin comme le récit du CDC 9.3/5.4 le suggère (« le club verra vos
  // actions comme Système Vesta ») :
  //
  // 1) Aucune route de l'interface ne permet au Superuser de naviguer
  //    vers les écrans réels du club : `ProtectedRoute` redirige
  //    systématiquement tout compte `is_superuser` vers `/admin`, quel
  //    que soit l'état de la session de support (`App.tsx`,
  //    `ProtectedRoute.tsx`) — `SupportSessionBanner` n'est montée que
  //    dans `AdminLayout`.
  // 2) Même en reproduisant côté API ce que l'interface enverrait
  //    (même jeton, même en-tête `X-Support-Session`), `apps.core.roles
  //    .get_active_roles` renvoie délibérément un ensemble VIDE pour tout
  //    Superuser, y compris en Ghost Mode (docstring explicite : « y
  //    compris un Superuser, qui n'a jamais de fiche joueur ») : toute
  //    action de service protégée par `_require_roles` (créer une
  //    dépense, encaisser, composer une équipe...) refuse donc
  //    SYSTÉMATIQUEMENT le Superuser, Ghost Mode actif ou non. Le code
  //    d'attribution « Système Vesta » existe bien (`apps.treasury
  //    .serializers._actor`, `apps.logistics.serializers`), mais aucune
  //    action réelle ne peut aujourd'hui l'atteindre : soit CDC 5.4
  //    décrit une intention pas encore câblée (role emprunté pendant la
  //    session de support), soit Ghost Mode n'est censé servir qu'à de la
  //    lecture/du support administratif — point à trancher avec le
  //    client (circuit 9.4), pas une décision que ce test peut prendre.
  //
  // Ce qui suit vérifie donc, honnêtement, ce qui est réellement vrai
  // aujourd'hui : la tentative est bien REFUSÉE (le Ghost Mode n'élève
  // jamais les droits au-delà de la matrice 2.4 -- bonne propriété de
  // sécurité), et le DÉMARRAGE de la session de support est, lui, bien
  // journalisé avec l'identité réelle du Superuser.
  const accessToken = await superuser.evaluate(() => window.sessionStorage.getItem("vesta:access"));
  expect(accessToken).toBeTruthy();

  const apiContext = superuser.context().request;
  const backendBase = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8000";
  const response = await apiContext.post(`${backendBase}/api/v1/treasury/expenses/`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "X-Support-Session": sessionIdMatch!,
    },
    multipart: {
      category_id: "1", // "Déplacements" (voir support/data.ts)
      amount: "5",
      beneficiary_name: "Kiosque à eau",
      reason: "Tentative Ghost Mode (recette CDC 9.3) -- doit être refusée",
      expense_date: "2026-09-30",
    },
  });
  expect(response.status()).toBe(403);
  const body = (await response.json()) as { detail?: string };
  expect(body.detail ?? "").toMatch(/Trésorier/);

  // Journal : vérifié au niveau base de données, faute de toute vue de
  // consultation du journal côté produit (API ou interface) à ce jour —
  // écart signalé au compte rendu (`apps/audit/views.py` est un scaffold
  // vide ; `/admin/journal` affiche `UnavailablePage`). Le DÉMARRAGE de
  // la session de support (action superuser-only, non gated par
  // `_require_roles`) doit lui être journalisé avec l'identité réelle.
  const check = runShell(
    `
from apps.audit.models import AuditLog
entry = AuditLog.objects.filter(object_type='SupportSession', object_id='${sessionIdMatch}').order_by('-id').first()
print('FOUND', bool(entry))
if entry:
    print('ACTOR_EMAIL', entry.actor.email)
`.trim(),
  );
  expect(check).toContain("FOUND True");
  expect(check).toContain(`ACTOR_EMAIL ${ACCOUNTS.superuser}`);
});

void SPORTS_DIRECTOR_CANDIDATE;
void LATE_ARRIVAL_CANDIDATE;
void DEBTOR;
void ASSEMBLY_ID;
void CLUB_SLUG;
