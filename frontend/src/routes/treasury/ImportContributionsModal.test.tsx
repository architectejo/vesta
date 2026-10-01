import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ContributionImportReport, GridTypesResponse } from "../../api/treasury";
import { ToastProvider } from "../../design-system";
import { ImportContributionsModal } from "./ImportContributionsModal";

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getGridContributionTypes: vi.fn(),
    previewContributionImport: vi.fn(),
    createContributionImport: vi.fn(),
    downloadContributionImportReport: vi.fn(),
  };
});

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return { ...actual, triggerBlobDownload: vi.fn() };
});

import { triggerBlobDownload } from "../../api/client";
import {
  createContributionImport,
  downloadContributionImportReport,
  getGridContributionTypes,
  previewContributionImport,
} from "../../api/treasury";

const MONTHLY_TYPE = {
  id: 1,
  name: "Mensuelle",
  nature: "mandatory" as const,
  nature_label: "Obligatoire",
  periodicity: "monthly" as const,
  periodicity_label: "Mensuelle",
  amount: "20.00",
  scope: "all" as const,
  status: "active" as const,
  is_free: false,
};

const TYPES_RESPONSE: GridTypesResponse = {
  currency: "USD",
  default_type_id: 1,
  active: [MONTHLY_TYPE],
  archived: [],
};

const MONTH_LABELS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

function buildReport(overrides: Partial<ContributionImportReport> = {}): ContributionImportReport {
  return {
    is_preview: true,
    import_batch_id: null,
    contribution_type: MONTHLY_TYPE,
    year: 2026,
    currency: "USD",
    months: MONTH_LABELS.map((label, index) => ({
      period: `2026-${String(index + 1).padStart(2, "0")}-01`,
      month: index + 1,
      label,
    })),
    summary: {
      rows_total: 2,
      rows_succeeded: 1,
      rows_failed: 1,
      payments_count: 1,
      payments_total: "20.00",
      dues_count: 0,
      already_imported_count: 0,
    },
    ignored_columns: [],
    ignored_lines: [],
    rows: [
      {
        line_number: 2,
        identity: "jean@example.com",
        status: "ok",
        player: {
          membership_id: 11,
          first_name: "Jean",
          last_name: "Kabila",
          name: "Jean Kabila",
          jersey_number: 7,
          photo: null,
          membership_status: "active",
          membership_status_label: "Inscrit",
        },
        errors: [],
        warnings: [],
        payments: [
          { period: "2026-01-01", paid_on: "2026-01-01", amount: "20.00", origin: "amount", reference: "Import historique 01/2026" },
        ],
        already_imported: [],
        dues: [],
        cells: [],
        total: null,
        balance_before: "-20.00",
        balance_after: "0.00",
        player_status_after: { balance: "0.00", amount_due: "0.00", is_in_good_standing: true, reason: "", currency: "USD" },
      },
      {
        line_number: 3,
        identity: "Paul Foo",
        status: "failed",
        player: null,
        errors: ["Aucun joueur ne correspond à ce nom."],
        warnings: [],
        payments: [],
        already_imported: [],
        dues: [],
        cells: [],
        total: null,
        balance_before: null,
        balance_after: null,
        player_status_after: null,
      },
    ],
    ...overrides,
  };
}

function renderModal(props: Partial<Parameters<typeof ImportContributionsModal>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  const onImported = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ImportContributionsModal
          open
          currency="USD"
          initialTypeId={null}
          initialYear={2026}
          onClose={onClose}
          onImported={onImported}
          {...props}
        />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onClose, onImported };
}

async function fillStep1(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByLabelText("Type de cotisation");
  await user.selectOptions(screen.getByLabelText("Type de cotisation"), "1");
  const file = new File(["email;janv.\njean@example.com;20\n"], "suivi.csv", { type: "text/csv" });
  await user.upload(screen.getByLabelText("Choisir un fichier CSV"), file);
  await user.click(screen.getByRole("button", { name: "Voir l'aperçu" }));
}

describe("ImportContributionsModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("ferme sans confirmation tant qu'aucun fichier n'a été choisi", async () => {
    vi.mocked(getGridContributionTypes).mockResolvedValue(TYPES_RESPONSE);
    const user = userEvent.setup();
    const { onClose } = renderModal();

    await screen.findByText("Importer les cotisations");
    await user.click(screen.getByRole("button", { name: "Annuler" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("affiche l'aperçu avec les lignes prêtes et en échec", async () => {
    vi.mocked(getGridContributionTypes).mockResolvedValue(TYPES_RESPONSE);
    vi.mocked(previewContributionImport).mockResolvedValue(buildReport());
    const user = userEvent.setup();
    renderModal();

    await fillStep1(user);

    await waitFor(() => expect(previewContributionImport).toHaveBeenCalled());
    expect(await screen.findByText("Étape 2 sur 3 · Aperçu")).toBeInTheDocument();
    expect(screen.getByText("Mensuelle · 2026 · suivi.csv")).toBeInTheDocument();
    expect(screen.getByText("En échec (1)")).toBeInTheDocument();
    expect(screen.getByText("Prêtes (1)")).toBeInTheDocument();
    // Onglet par défaut : « En échec » puisqu'il y en a (§6 de la fiche).
    expect(screen.getByText("Ligne 3 · Paul Foo")).toBeInTheDocument();
    expect(screen.getByText("Aucun joueur ne correspond à ce nom.")).toBeInTheDocument();

    await user.click(screen.getByText("Prêtes (1)"));
    expect(await screen.findByText("Jean Kabila")).toBeInTheDocument();
  });

  it("demande le code PIN avant d'importer, puis affiche le résultat", async () => {
    vi.mocked(getGridContributionTypes).mockResolvedValue(TYPES_RESPONSE);
    vi.mocked(previewContributionImport).mockResolvedValue(buildReport());
    vi.mocked(createContributionImport).mockResolvedValue(
      buildReport({
        is_preview: false,
        import_batch_id: 42,
        summary: {
          rows_total: 2,
          rows_succeeded: 1,
          rows_failed: 0,
          payments_count: 1,
          payments_total: "20.00",
          dues_count: 0,
          already_imported_count: 0,
        },
      }),
    );
    const user = userEvent.setup();
    renderModal();

    await fillStep1(user);
    await screen.findByText("Étape 2 sur 3 · Aperçu");

    await user.click(screen.getByRole("button", { name: "Importer 1 ligne(s)" }));
    const pinInput = await screen.findByLabelText("Votre code PIN");
    expect(createContributionImport).not.toHaveBeenCalled();

    await user.type(pinInput, "1234");
    await user.click(screen.getByRole("button", { name: "Importer" }));

    await waitFor(() =>
      expect(createContributionImport).toHaveBeenCalledWith(
        expect.objectContaining({ contribution_type_id: 1, year: 2026, pin: "1234" }),
      ),
    );
    expect(await screen.findByText("Import terminé.")).toBeInTheDocument();
  });

  it("propose le téléchargement du rapport après un import réussi", async () => {
    vi.mocked(getGridContributionTypes).mockResolvedValue(TYPES_RESPONSE);
    vi.mocked(previewContributionImport).mockResolvedValue(buildReport());
    vi.mocked(createContributionImport).mockResolvedValue(
      buildReport({
        is_preview: false,
        import_batch_id: 42,
        summary: {
          rows_total: 2,
          rows_succeeded: 1,
          rows_failed: 0,
          payments_count: 1,
          payments_total: "20.00",
          dues_count: 0,
          already_imported_count: 0,
        },
      }),
    );
    vi.mocked(downloadContributionImportReport).mockResolvedValue({
      blob: new Blob(["ligne,statut"]),
      filename: "rapport-import-cotisations-2026.csv",
    });
    const user = userEvent.setup();
    renderModal();

    await fillStep1(user);
    await user.click(screen.getByRole("button", { name: "Importer 1 ligne(s)" }));
    await user.type(await screen.findByLabelText("Votre code PIN"), "1234");
    await user.click(screen.getByRole("button", { name: "Importer" }));

    const downloadButton = await screen.findByRole("button", { name: "Télécharger le rapport (CSV)" });
    await user.click(downloadButton);

    await waitFor(() => expect(downloadContributionImportReport).toHaveBeenCalledWith(42, 2026));
    expect(triggerBlobDownload).toHaveBeenCalledWith(expect.any(Blob), "rapport-import-cotisations-2026.csv");
  });

  it("affiche le nombre d'essais restants sur un code PIN incorrect", async () => {
    vi.mocked(getGridContributionTypes).mockResolvedValue(TYPES_RESPONSE);
    vi.mocked(previewContributionImport).mockResolvedValue(buildReport());
    const { ApiError } = await import("../../api/client");
    vi.mocked(createContributionImport).mockRejectedValue(
      new ApiError(400, { detail: "Code PIN incorrect.", attempts_remaining: 2 }),
    );
    const user = userEvent.setup();
    renderModal();

    await fillStep1(user);
    await user.click(screen.getByRole("button", { name: "Importer 1 ligne(s)" }));
    await user.type(await screen.findByLabelText("Votre code PIN"), "0000");
    await user.click(screen.getByRole("button", { name: "Importer" }));

    expect(await screen.findByText("Code PIN incorrect. Il vous reste 2 essais.")).toBeInTheDocument();
  });
});
