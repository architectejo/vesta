import { useMemo, useState, type ReactNode } from "react";
import {
  Avatar,
  BarChart,
  Button,
  ChartCard,
  ClubBrandingProvider,
  DataTable,
  EmptyState,
  Footer,
  FormStrip,
  IconButton,
  IconNotifications,
  KpiTile,
  LineChart,
  Loader,
  Modal,
  PeriodPicker,
  PlayerMultiSearch,
  PlayerSearch,
  RadarChart,
  Sidebar,
  StackedBar,
  StatusBadge,
  ThemeProvider,
  THEME_LABELS,
  useTheme,
  type ChartCardState,
  type ClubBranding,
  type DataTableColumn,
  type PeriodValue,
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
          icon={<IconNotifications aria-hidden="true" className="h-5 w-5" />}
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
// Graphiques (données fictives : aucun nom de club réel)
// ---------------------------------------------------------------------------

const DEMO_PERIOD_SEASONS = [
  { id: "demo-2", label: "2026-2027" },
  { id: "demo-1", label: "2025-2026" },
];
const DEMO_SESSIONS = ["3 nov.", "10 nov.", "17 nov.", "24 nov."];
const DEMO_MONTHS = ["juin", "juil.", "août", "sept.", "oct.", "nov."];
const DEMO_RADAR_AXES = [
  { label: "Vitesse" },
  { label: "Endurance physique" },
  { label: "Technique" },
  { label: "Frappe" },
  { label: "Défense" },
  { label: "Passes" },
];
const CARD_STATE_LABELS: Record<ChartCardState, string> = {
  ready: "Normal",
  loading: "Chargement",
  error: "Erreur",
  empty: "Vide",
};

function ChartsSection() {
  const [period, setPeriod] = useState<PeriodValue>({ mode: "month", month: "2026-11" });
  const [cardState, setCardState] = useState<ChartCardState>("ready");
  const [selected, setSelected] = useState("Aucune sélection");

  return (
    <Section title="Graphiques (SVG maison, données fictives)">
      <PeriodPicker value={period} onChange={setPeriod} seasons={DEMO_PERIOD_SEASONS} />
      <div className="flex flex-wrap gap-2">
        {(Object.keys(CARD_STATE_LABELS) as ChartCardState[]).map((state) => (
          <Button
            key={state}
            size="sm"
            variant={cardState === state ? "primary" : "secondary"}
            onClick={() => setCardState(state)}
          >
            {CARD_STATE_LABELS[state]}
          </Button>
        ))}
      </div>
      <p className="text-xs text-text-muted" aria-live="polite">
        Dernière interaction : {selected}
      </p>

      <div className="grid grid-cols-2 gap-3">
        <KpiTile label="Taux de recouvrement" value="82 %" hint="Types obligatoires" />
        <KpiTile
          label="Joueurs suspendus"
          value={2}
          family="suspended"
          statusLabel="À surveiller"
          onClick={() => setSelected("Tuile : suspendus")}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <ChartCard
          title="Présences"
          periodLabel="novembre 2026"
          value="74 % de présence moyenne"
          caption="Dernière séance 72 % · 4 séances"
          state={cardState}
          emptyMessage="Aucune séance sur la période."
          onRetry={() => setCardState("ready")}
          onOpen={() => setSelected("Carte : présences")}
        >
          <LineChart
            title="Taux de présence par séance"
            labels={DEMO_SESSIONS}
            series={[{ name: "Présence", values: [60, 80, 70, 72] }]}
            yMin={0}
            yMax={100}
            unit="%"
            reference={{ value: 74, label: "Moyenne" }}
          />
        </ChartCard>

        <ChartCard
          title="Cotisations"
          periodLabel="6 derniers mois"
          value="82 % recouvré"
          caption="1 240 $ encaissés"
          state={cardState}
          emptyMessage="Aucune cotisation due sur la période."
          onRetry={() => setCardState("ready")}
          onOpen={() => setSelected("Carte : cotisations")}
        >
          <BarChart
            title="Encaissé par mois"
            categories={DEMO_MONTHS}
            series={[{ name: "Encaissé", values: [180, 220, 150, 0, 300, 390] }]}
            unit="$"
            reference={{ value: 250, label: "Dû" }}
          />
        </ChartCard>

        <ChartCard
          title="Situation de l'effectif"
          periodLabel="Aujourd'hui"
          state={cardState}
          onRetry={() => setCardState("ready")}
          onOpen={() => setSelected("Carte : effectif")}
        >
          <StackedBar
            title="Répartition de l'effectif"
            segments={[
              { label: "En ordre", value: 24, family: "success" },
              { label: "En dette", value: 6, family: "danger" },
              { label: "En attente", value: 2, family: "warning" },
              { label: "Suspendus", value: 1, family: "suspended" },
            ]}
          />
        </ChartCard>

        <ChartCard
          title="Résultats"
          periodLabel="novembre 2026"
          caption="7 V · 2 N · 3 D · 24 buts marqués, 15 encaissés"
          state={cardState}
          onRetry={() => setCardState("ready")}
          onOpen={() => setSelected("Carte : résultats")}
        >
          <FormStrip
            results={[
              { outcome: "win", opponent: "Équipe fictive A", score: "3-1" },
              { outcome: "draw", opponent: "Équipe fictive B", score: "1-1" },
              { outcome: "loss", opponent: "Équipe fictive C", score: "0-2" },
              { outcome: "win", opponent: "Équipe fictive D", score: "2-0" },
              { outcome: "win", opponent: "Équipe fictive E", score: "4-2" },
            ]}
          />
        </ChartCard>
      </div>

      <p className="text-sm font-medium text-text">
        Graphiques interactifs (clic, Entrée, Espace ; deux séries ; empilé ; horizontal ; radar)
      </p>
      <div className="space-y-4">
        <LineChart
          title="Encaissé et dû par séance"
          labels={DEMO_SESSIONS}
          series={[
            { name: "Encaissé", values: [100, 140, null, 180] },
            { name: "Dû", values: [120, 120, 150, 150] },
          ]}
          unit="$"
          height={220}
          onSelect={(i) => setSelected(`Courbe : ${DEMO_SESSIONS[i] ?? ""}`)}
        />
        <BarChart
          title="Caisse : encaissé et dépensé"
          categories={DEMO_MONTHS}
          series={[
            { name: "Encaissé", values: [180, 220, 150, 40, 300, 390] },
            { name: "Dépensé", values: [90, 60, 150, 20, 110, 80] },
          ]}
          unit="$"
          height={220}
          onSelect={(i) => setSelected(`Barres : ${DEMO_MONTHS[i] ?? ""}`)}
        />
        <BarChart
          title="Cartons par mois"
          stacked
          categories={DEMO_MONTHS}
          series={[
            { name: "Jaunes", values: [4, 2, 0, 3, 5, 2] },
            { name: "Rouges", values: [0, 1, 0, 0, 1, 0] },
          ]}
          height={220}
        />
        <BarChart
          title="Dépenses par catégorie"
          orientation="horizontal"
          categories={["Équipement sportif et entretien du terrain", "Transport", "Arbitrage", "Autres"]}
          series={[{ name: "Montant", values: [900, 420, 180, 60] }]}
          unit="$"
          onSelect={(i) => setSelected(`Catégorie ${i + 1}`)}
        />
        <RadarChart
          title="Comparaison de deux joueurs fictifs"
          axes={DEMO_RADAR_AXES}
          maxValue={10}
          series={[
            { name: "Joueur Un", values: [8, 6, 7, 5, 4, 7] },
            { name: "Joueur Deux", values: [5, 7, 6, 8, 9, 5] },
          ]}
          onSelect={(i) => setSelected(`Axe : ${DEMO_RADAR_AXES[i]?.label ?? ""}`)}
        />
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
          <ChartsSection />
          <SidebarSection />
        </div>
      </ThemeProvider>
    </ClubBrandingProvider>
  );
}
