import { useMemo, useState, type ReactNode } from "react";
import {
  Avatar,
  Button,
  ClubBrandingProvider,
  DataTable,
  EmptyState,
  Footer,
  IconButton,
  Loader,
  Modal,
  PlayerMultiSearch,
  PlayerSearch,
  Sidebar,
  StatusBadge,
  ThemeProvider,
  THEME_LABELS,
  useTheme,
  type ClubBranding,
  type DataTableColumn,
  type PlayerSearchResult,
  type SidebarNavGroup,
  type StatusKey,
} from "../../design-system";

/**
 * Page de démonstration interne du design system (Lot 1, tâche 1.0).
 *
 * Route non protégée, non reliée à la navigation publique : `frontend-dev`
 * doit la retirer ou la protéger avant la mise en production (voir compte
 * rendu de la tâche).
 *
 * Toutes les données ci-dessous sont FICTIVES : aucun nom de club réel,
 * aucune couleur de club réelle, aucune donnée personnelle (CLAUDE.md §2.18).
 */

// ---------------------------------------------------------------------------
// Données fictives de démonstration
// ---------------------------------------------------------------------------

const FICTITIOUS_CLUB_BRANDING: ClubBranding = {
  name: "Club fictif de démonstration",
  logoUrl: null,
  primaryColor: "#0F766E",
  secondaryColor: "#F97316",
};

interface DemoPlayer {
  id: number;
  firstName: string;
  lastName: string;
  number: number;
  position: string;
  statusKey: StatusKey;
  eligible: boolean;
  ineligibleReason?: string;
}

const DEMO_PLAYERS: DemoPlayer[] = [
  { id: 1, firstName: "Joueur", lastName: "Un", number: 1, position: "Gardien", statusKey: "in_good_standing", eligible: true },
  { id: 2, firstName: "Joueur", lastName: "Deux", number: 4, position: "Défenseur", statusKey: "in_debt", eligible: false, ineligibleReason: "En dette : 20 $" },
  { id: 3, firstName: "Joueur", lastName: "Trois", number: 7, position: "Milieu", statusKey: "suspended", eligible: false, ineligibleReason: "Suspendu : encore 1 match" },
  { id: 4, firstName: "Joueur", lastName: "Quatre", number: 9, position: "Attaquant", statusKey: "unfit", eligible: false, ineligibleReason: "Inapte (avis médical)" },
  { id: 5, firstName: "Joueur", lastName: "Cinq", number: 10, position: "Attaquant", statusKey: "in_good_standing", eligible: true },
  { id: 6, firstName: "Joueur", lastName: "Six", number: 11, position: "Milieu", statusKey: "pending", eligible: true },
  { id: 7, firstName: "Joueur", lastName: "Sept", number: 3, position: "Défenseur", statusKey: "in_good_standing", eligible: true },
];

const MANY_DEMO_ROWS: DemoPlayer[] = Array.from({ length: 34 }, (_, i) => ({
  id: 100 + i,
  firstName: "Joueur",
  lastName: `Numéro ${i + 1}`,
  number: i + 1,
  position: ["Gardien", "Défenseur", "Milieu", "Attaquant"][i % 4] ?? "Milieu",
  statusKey: (["in_good_standing", "in_debt", "pending", "suspended"] as StatusKey[])[i % 4] ?? "in_good_standing",
  eligible: i % 4 !== 1,
  ineligibleReason: i % 4 === 1 ? "En dette : 15 $" : undefined,
}));

function toPlayerSearchResult(player: DemoPlayer): PlayerSearchResult {
  return {
    id: player.id,
    firstName: player.firstName,
    lastName: player.lastName,
    number: player.number,
    position: player.position,
    status: { key: player.statusKey },
    eligible: player.eligible,
    ineligibleReason: player.ineligibleReason,
  };
}

async function mockSearchPlayers(query: string): Promise<PlayerSearchResult[]> {
  await new Promise((resolve) => setTimeout(resolve, 150));
  const needle = query.trim().toLowerCase();
  return DEMO_PLAYERS.filter(
    (p) =>
      `${p.firstName} ${p.lastName}`.toLowerCase().includes(needle) ||
      String(p.number) === needle,
  ).map(toPlayerSearchResult);
}

const SIDEBAR_GROUPS: SidebarNavGroup[] = [
  {
    items: [
      { key: "home", label: "Accueil", href: "/dev/design-system#accueil" },
      { key: "locker", label: "Vestiaire du jour", href: "/dev/design-system#vestiaire" },
      { key: "profile", label: "Mon profil", href: "/dev/design-system#profil" },
    ],
  },
  {
    title: "Trésorerie",
    items: [
      { key: "dashboard", label: "Tableau de bord", href: "/dev/design-system#dashboard" },
      { key: "grid", label: "Grille des cotisations", href: "/dev/design-system#grille" },
    ],
  },
];

const ALL_STATUS_KEYS: StatusKey[] = [
  "in_good_standing",
  "in_debt",
  "pending",
  "to_justify",
  "suspended",
  "left",
  "archived",
  "registered",
  "present",
  "absent",
  "late",
  "excused",
  "unfit",
  "injured",
  "fit",
  "fit_restricted",
  "to_validate",
  "validated",
  "refused",
  "cancelled",
  "queued",
  "expense_pending",
  "expense_released",
  "expense_justified",
  "expense_unjustified",
  "expense_refused",
  "session_open",
  "session_locked",
  "lineup_draft",
  "lineup_published",
  "challenge_pending",
  "challenge_accepted",
  "challenge_refused",
  "transfer_pending",
  "transfer_accepted",
  "transfer_refused",
  "transfer_blocked",
  "transfer_done",
  "ag_convened",
  "ag_pv_to_sign",
  "ag_closed",
  "licence_trial",
  "licence_active",
  "licence_expired_grace",
  "licence_suspended",
  "licence_terminated",
  "mercato_open",
  "mercato_closed",
  "vacant",
];

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="mb-3 text-base font-semibold text-text">{title}</h2>
      <div className="space-y-3 rounded-md border border-border bg-surface p-3">{children}</div>
    </section>
  );
}

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="flex flex-wrap gap-2">
      {(Object.keys(THEME_LABELS) as Array<keyof typeof THEME_LABELS>).map((name) => (
        <Button
          key={name}
          size="sm"
          variant={theme === name ? "primary" : "secondary"}
          onClick={() => setTheme(name)}
        >
          {THEME_LABELS[name]}
        </Button>
      ))}
    </div>
  );
}

function ButtonsSection() {
  const [loading, setLoading] = useState(false);
  return (
    <Section title="Button / IconButton">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary">Primaire</Button>
        <Button variant="secondary">Secondaire</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="danger">Détruire</Button>
        <Button size="sm" variant="secondary">
          Petit (36 px)
        </Button>
        <Button
          variant="primary"
          loading={loading}
          loadingLabel="Enregistrement…"
          onClick={() => {
            setLoading(true);
            setTimeout(() => setLoading(false), 1500);
          }}
        >
          Enregistrer
        </Button>
        <IconButton
          aria-label="Notifications"
          icon={
            <svg aria-hidden viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M6 8a6 6 0 1112 0c0 5 2 6 2 6H4s2-1 2-6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M10 20a2 2 0 004 0" strokeLinecap="round" />
            </svg>
          }
        />
      </div>
    </Section>
  );
}

function AvatarSection() {
  return (
    <Section title="Avatar">
      <div className="flex flex-wrap items-center gap-3">
        <Avatar name="Joueur Un" size={24} />
        <Avatar name="Joueur Deux" size={32} />
        <Avatar name="Joueur Trois" size={40} />
        <Avatar name="Joueur Quatre" size={72} />
      </div>
    </Section>
  );
}

function LoaderSection() {
  const [loading, setLoading] = useState(true);
  return (
    <Section title="Loader">
      <Button size="sm" variant="secondary" onClick={() => setLoading((v) => !v)}>
        {loading ? "Arrêter le chargement" : "Relancer le chargement"}
      </Button>
      <p className="text-xs text-text-muted">Variante liste :</p>
      <Loader loading={loading} variant="list" count={3} />
      <p className="text-xs text-text-muted">Variante pleine page :</p>
      <Loader loading={loading} variant="page" />
    </Section>
  );
}

function EmptyStateSection() {
  return (
    <Section title="EmptyState">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded-md border border-border">
          <EmptyState message="Aucun paiement pour l'instant." />
        </div>
        <div className="rounded-md border border-border">
          <EmptyState
            variant="error"
            onAction={() => window.alert("Nouvelle tentative (démonstration).")}
            actionLabel="Réessayer"
          />
        </div>
        <div className="rounded-md border border-border">
          <EmptyState
            variant="no-results"
            message="Aucun résultat pour « xyz »."
            actionLabel="Effacer les filtres"
            onAction={() => window.alert("Filtres effacés (démonstration).")}
          />
        </div>
      </div>
    </Section>
  );
}

function StatusBadgeSection() {
  return (
    <Section title="StatusBadge (correspondance complète §2.5)">
      <div className="flex flex-wrap gap-2">
        {ALL_STATUS_KEYS.map((key) => (
          <StatusBadge key={key} status={key} />
        ))}
      </div>
      <p className="text-xs text-text-muted">
        Superposition (financier + discipline/santé) :
      </p>
      <div className="flex flex-wrap gap-2">
        <StatusBadge status="in_debt" detail="20 $" />
        <StatusBadge status="suspended" detail="1 match" />
      </div>
    </Section>
  );
}

function ModalSection() {
  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(true);
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  return (
    <Section title="Modal">
      <div className="flex flex-wrap gap-2">
        <Button
          variant="primary"
          onClick={() => {
            setName("");
            setFormOpen(true);
          }}
        >
          Ouvrir un formulaire (md)
        </Button>
        <Button
          variant="secondary"
          onClick={() => {
            setDetailLoading(true);
            setDetailOpen(true);
            setTimeout(() => setDetailLoading(false), 1200);
          }}
        >
          Ouvrir un détail (lg, avec chargement)
        </Button>
      </div>

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title="Ajouter un joueur (démonstration)"
        size="md"
        isDirty={name.trim() !== ""}
        isSubmitting={submitting}
        onConfirm={() => {
          setSubmitting(true);
          setTimeout(() => {
            setSubmitting(false);
            setFormOpen(false);
          }, 1000);
        }}
        confirmLabel="Enregistrer"
      >
        <label className="mb-1 block text-sm font-medium text-text" htmlFor="demo-name">
          Nom complet
        </label>
        <input
          id="demo-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Ex. Joueur Un (donnée fictive)"
          className="h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text"
        />
        <p className="mt-1 text-xs text-text-muted">
          Modifiez ce champ puis tentez de fermer : la confirmation d'abandon
          s'affiche (3.2).
        </p>
      </Modal>

      <Modal
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title="Détail du joueur (démonstration)"
        size="lg"
        loading={detailLoading}
        cancelLabel="Fermer"
      >
        <p className="text-sm text-text">Contenu chargé après un court délai.</p>
      </Modal>
    </Section>
  );
}

function DataTableSection() {
  const columns: Array<DataTableColumn<DemoPlayer>> = useMemo(
    () => [
      {
        key: "name",
        header: "Joueur",
        widthPx: 180,
        render: (p) => (
          <span className="flex items-center gap-2">
            <Avatar name={`${p.firstName} ${p.lastName}`} size={24} />
            {p.firstName} {p.lastName}
          </span>
        ),
        sortAccessor: (p) => `${p.firstName} ${p.lastName}`,
      },
      { key: "number", header: "N°", align: "right", render: (p) => p.number, sortAccessor: (p) => p.number },
      { key: "position", header: "Poste", render: (p) => p.position },
      { key: "status", header: "Statut", render: (p) => <StatusBadge status={p.statusKey} /> },
    ],
    [],
  );

  return (
    <Section title="DataTable">
      <DataTable
        columns={columns}
        rows={MANY_DEMO_ROWS}
        getRowId={(p) => p.id}
        getSearchableText={(p) => `${p.firstName} ${p.lastName} ${p.number}`}
        searchPlaceholder="Rechercher un joueur"
        resultLabel="joueurs"
        stickyFirstColumn
        onRowClick={(p) => window.alert(`Détail de ${p.firstName} ${p.lastName} (démonstration).`)}
        onExport={() => window.alert("Export CSV (démonstration).")}
      />
    </Section>
  );
}

function PlayerSearchSection() {
  const [single, setSingle] = useState<PlayerSearchResult | null>(null);
  const [multi, setMulti] = useState<PlayerSearchResult[]>([]);

  return (
    <Section title="PlayerSearch (jamais de <select> de joueurs)">
      <div>
        <p className="mb-1 text-sm font-medium text-text">Sélection simple</p>
        <PlayerSearch value={single} onChange={setSingle} searchPlayers={mockSearchPlayers} />
      </div>
      <div>
        <p className="mb-1 text-sm font-medium text-text">Sélection multiple</p>
        <PlayerMultiSearch values={multi} onChange={setMulti} searchPlayers={mockSearchPlayers} />
      </div>
    </Section>
  );
}

function SidebarSection() {
  const [path, setPath] = useState("/dev/design-system#accueil");
  return (
    <Section title="Sidebar / Footer">
      <p className="text-xs text-text-muted">
        En dessous de 1024 px : barre supérieure + tiroir (redimensionnez la
        fenêtre à 360 px pour vérifier). À partir de 1024 px : barre latérale
        fixe à gauche — elle chevauche alors cette page de démonstration, qui
        ne simule pas une mise en page d'application réelle.
      </p>
      <div className="relative min-h-[420px] overflow-hidden rounded-md border border-border">
        <Sidebar
          groups={SIDEBAR_GROUPS}
          currentPath={path}
          onNavigate={setPath}
          user={{ name: "Joueur Un (fictif)", roleLabel: "Trésorier" }}
          profileHref="/dev/design-system#profil"
          onLogout={() => window.alert("Déconnexion (démonstration).")}
        />
      </div>
      <div>
        <Footer />
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function DesignSystemDemoPage() {
  return (
    <ClubBrandingProvider branding={FICTITIOUS_CLUB_BRANDING}>
      <ThemeProvider initialTheme="classic">
        <div className="mx-auto max-w-3xl p-3 sm:p-6">
          <h1 className="text-xl font-semibold text-text sm:text-2xl">
            Design system Vesta — démonstration interne
          </h1>
          <p className="mb-4 text-sm text-text-muted">
            Route de développement (§ tâche 1.0, Lot 1). Données et couleurs de
            club entièrement fictives. À vérifier à 360 px de large.
          </p>

          <Section title="Thème">
            <ThemeSwitcher />
          </Section>

          <ButtonsSection />
          <AvatarSection />
          <LoaderSection />
          <EmptyStateSection />
          <StatusBadgeSection />
          <ModalSection />
          <DataTableSection />
          <PlayerSearchSection />
          <SidebarSection />
        </div>
      </ThemeProvider>
    </ClubBrandingProvider>
  );
}
