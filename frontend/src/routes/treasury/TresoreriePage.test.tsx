import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import { ApiError } from "../../api/client";
import type { ContributionType } from "../../api/treasury";
import { AuthProvider } from "../../auth/AuthContext";
import { ToastProvider } from "../../design-system";
import { TresoreriePage } from "./TresoreriePage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getContributionTypes: vi.fn(),
    createContributionType: vi.fn(),
    updateContributionType: vi.fn(),
    archiveContributionType: vi.fn(),
    getTreasuryCapabilities: vi.fn(),
  };
});

import { getMyProfile } from "../../api/clubs";
import {
  archiveContributionType,
  createContributionType,
  getContributionTypes,
  getTreasuryCapabilities,
  type TreasuryCapabilities,
} from "../../api/treasury";

const ACCESS_DENIED = "Vous n'avez pas accès à la trésorerie.";

function makeProfile(...roles: string[]): MyProfile {
  return {
    membership_id: 1,
    club: { id: 1, slug: "test", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    identity: {
      first_name: "Jean",
      last_name: "Mukendi",
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

function makeType(overrides: Partial<ContributionType> = {}): ContributionType {
  return {
    id: 1,
    name: "Mensuelle catégorie A",
    nature: "mandatory",
    amount: "20.00",
    periodicity: "monthly",
    due_day: 10,
    due_month: null,
    deadline: null,
    is_membership_fee: false,
    scope: "all",
    status: "active",
    archived_at: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

function makeCapabilities(overrides: Partial<TreasuryCapabilities> = {}): {
  currency: string;
  capabilities: TreasuryCapabilities;
} {
  return {
    currency: "USD",
    capabilities: {
      can_read: true,
      can_write: false,
      can_record_payments: false,
      can_read_expenses: false,
      can_manage_expense_categories: false,
      can_submit_expenses: false,
      can_validate_expenses: false,
      can_derogate: false,
      can_decide_payment_reversal: false,
      can_upload_expense_receipts: false,
      can_manage_assistance_scales: false,
      can_process_assistance_requests: false,
      can_request_assistance: true,
      ...overrides,
    },
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ToastProvider>
          <TresoreriePage />
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TresoreriePage", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.mocked(getContributionTypes).mockResolvedValue([]);
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe("chargement et accès", () => {
    it("affiche le loader pendant le chargement du profil, sans jamais afficher « accès refusé »", async () => {
      vi.mocked(getMyProfile).mockReturnValue(new Promise(() => undefined));
      renderPage();

      expect(screen.queryByText(ACCESS_DENIED)).not.toBeInTheDocument();
      await screen.findByText("Chargement…");
      expect(screen.queryByText(ACCESS_DENIED)).not.toBeInTheDocument();
      expect(getContributionTypes).not.toHaveBeenCalled();
    });

    it("refuse l'accès à un rôle non autorisé, seulement après le chargement du profil", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
      renderPage();

      expect(screen.queryByText(ACCESS_DENIED)).not.toBeInTheDocument();
      expect(await screen.findByText(ACCESS_DENIED)).toBeInTheDocument();
      expect(getContributionTypes).not.toHaveBeenCalled();
    });

    it("n'affiche pas « accès refusé » à un Trésorier légitime", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      renderPage();

      expect(await screen.findByRole("heading", { name: "Trésorerie" })).toBeInTheDocument();
      expect(screen.queryByText(ACCESS_DENIED)).not.toBeInTheDocument();
    });

    it("affiche l'état d'erreur avec « Réessayer » quand le profil ne charge pas", async () => {
      vi.mocked(getMyProfile).mockRejectedValueOnce(new ApiError(500, null));
      renderPage();

      expect(await screen.findByText("Impossible de charger cette section.")).toBeInTheDocument();
      expect(screen.queryByText(ACCESS_DENIED)).not.toBeInTheDocument();

      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      await userEvent.setup().click(screen.getByRole("button", { name: "Réessayer" }));
      expect(await screen.findByRole("heading", { name: "Trésorerie" })).toBeInTheDocument();
    });

    it("affiche le loader pendant le chargement des types", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(getContributionTypes).mockReturnValue(new Promise(() => undefined));
      renderPage();

      await screen.findByText("Chargement…");
      expect(screen.queryByText(ACCESS_DENIED)).not.toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "Trésorerie" })).not.toBeInTheDocument();
    });

    it("affiche un message d'erreur en français quand le chargement des types échoue", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(getContributionTypes).mockRejectedValueOnce(new ApiError(500, null));
      renderPage();

      expect(await screen.findByText("Impossible de charger cette section.")).toBeInTheDocument();

      vi.mocked(getContributionTypes).mockResolvedValue([makeType()]);
      await userEvent.setup().click(screen.getByRole("button", { name: "Réessayer" }));
      expect(await screen.findByText("Mensuelle catégorie A", { selector: "p" })).toBeInTheDocument();
    });
  });

  describe("liste", () => {
    it("affiche l'état vide quand aucun type n'existe", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("vice_president"));
      renderPage();

      expect(await screen.findByText("Aucun type de cotisation.")).toBeInTheDocument();
      expect(screen.getByText("0 actif")).toBeInTheDocument();
    });

    it("affiche les types avec leur nature, périodicité et montant", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(getContributionTypes).mockResolvedValue([
        makeType(),
        makeType({
          id: 2,
          name: "Cotisation vestiaire",
          nature: "free",
          amount: null,
          periodicity: "one_off",
          due_day: null,
        }),
        makeType({ id: 3, name: "Adhésion", periodicity: "annual", amount: "5.00" }),
      ]);
      renderPage();

      expect(await screen.findByText("Mensuelle catégorie A", { selector: "p" })).toBeInTheDocument();
      expect(screen.getByText("Obligatoire · Mensuelle · 20.00")).toBeInTheDocument();
      expect(screen.getByText("Libre · Ponctuelle")).toBeInTheDocument();
      expect(screen.getByText("Obligatoire · Annuelle · 5.00")).toBeInTheDocument();
      expect(screen.getByText("3 actifs")).toBeInTheDocument();
    });
  });

  describe("droits d'écriture", () => {
    it.each(["president", "treasurer"])("montre « Nouveau type » et « Archiver » au rôle %s", async (role) => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile(role));
      vi.mocked(getContributionTypes).mockResolvedValue([makeType()]);
      renderPage();

      expect(await screen.findByRole("button", { name: "Nouveau type" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Archiver" })).toBeInTheDocument();
    });

    it.each(["vice_president", "assistant_treasurer"])(
      "masque « Nouveau type » et « Archiver » au rôle %s (lecture seule)",
      async (role) => {
        vi.mocked(getMyProfile).mockResolvedValue(makeProfile(role));
        vi.mocked(getContributionTypes).mockResolvedValue([makeType()]);
        renderPage();

        expect(await screen.findByText("Mensuelle catégorie A", { selector: "p" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Nouveau type" })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Archiver" })).not.toBeInTheDocument();
      },
    );

    it("n'offre pas la création dans l'état vide à un rôle en lecture seule", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("assistant_treasurer"));
      renderPage();

      expect(await screen.findByText("Aucun type de cotisation.")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Nouveau type" })).not.toBeInTheDocument();
    });
  });

  describe("modale de détail et de formulaire", () => {
    it("ouvre la modale de détail avec les valeurs du type cliqué", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(getContributionTypes).mockResolvedValue([
        makeType(),
        makeType({ id: 2, name: "Adhésion", amount: "5.00", periodicity: "annual", due_day: 15 }),
      ]);
      const user = userEvent.setup();
      renderPage();

      await user.click(await screen.findByRole("button", { name: /Adhésion/ }));

      const dialog = await screen.findByRole("dialog", { name: "Modifier le type de cotisation" });
      expect(within(dialog).getByLabelText("Nom")).toHaveValue("Adhésion");
      expect(within(dialog).getByLabelText("Montant")).toHaveValue("5.00");
      expect(within(dialog).getByLabelText("Périodicité")).toHaveValue("annual");
      expect(within(dialog).getByLabelText("Jour d'échéance")).toHaveValue(15);
    });

    it("ouvre le détail en lecture seule pour un rôle sans droit d'écriture", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("vice_president"));
      vi.mocked(getContributionTypes).mockResolvedValue([makeType()]);
      const user = userEvent.setup();
      renderPage();

      await user.click(await screen.findByRole("button", { name: /Mensuelle catégorie A/ }));

      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).getByText("Ce type est consultable en lecture seule.")).toBeInTheDocument();
      expect(within(dialog).getByLabelText("Nom")).toBeDisabled();
      expect(within(dialog).queryByRole("button", { name: "Enregistrer" })).not.toBeInTheDocument();
    });

    it("ouvre un formulaire vide de création avec « Nouveau type »", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("president"));
      vi.mocked(getContributionTypes).mockResolvedValue([makeType()]);
      const user = userEvent.setup();
      renderPage();

      await user.click(await screen.findByRole("button", { name: "Nouveau type" }));

      const dialog = await screen.findByRole("dialog", { name: "Nouveau type de cotisation" });
      expect(within(dialog).getByLabelText("Nom")).toHaveValue("");
    });

    it("crée un type puis ferme la modale et confirme par un message", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(createContributionType).mockResolvedValue(makeType({ id: 9 }));
      const user = userEvent.setup();
      renderPage();

      await user.click((await screen.findAllByRole("button", { name: "Nouveau type" }))[0]!);
      const dialog = await screen.findByRole("dialog");
      await user.type(within(dialog).getByLabelText("Nom"), "Mensuelle B");
      await user.type(within(dialog).getByLabelText("Montant"), "10");
      await user.click(within(dialog).getByRole("button", { name: "Enregistrer" }));

      await waitFor(() =>
        expect(createContributionType).toHaveBeenCalledWith({
          name: "Mensuelle B",
          nature: "mandatory",
          amount: "10",
          periodicity: "monthly",
          due_day: 10,
          scope: "all",
        }),
      );
      expect(await screen.findByText("Type de cotisation enregistré.")).toBeInTheDocument();
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    });

    it("affiche dans la modale le message en français renvoyé par l'API quand l'enregistrement échoue", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(createContributionType).mockRejectedValue(
        new ApiError(400, { detail: "Un type portant ce nom existe déjà." }),
      );
      const user = userEvent.setup();
      renderPage();

      await user.click((await screen.findAllByRole("button", { name: "Nouveau type" }))[0]!);
      const dialog = await screen.findByRole("dialog");
      await user.type(within(dialog).getByLabelText("Nom"), "Doublon");
      await user.type(within(dialog).getByLabelText("Montant"), "10");
      await user.click(within(dialog).getByRole("button", { name: "Enregistrer" }));

      expect(await within(dialog).findByRole("alert")).toHaveTextContent("Un type portant ce nom existe déjà.");
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    it("affiche un message générique en français pour une erreur inattendue", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(createContributionType).mockRejectedValue(new Error("boom"));
      const user = userEvent.setup();
      renderPage();

      await user.click((await screen.findAllByRole("button", { name: "Nouveau type" }))[0]!);
      const dialog = await screen.findByRole("dialog");
      await user.type(within(dialog).getByLabelText("Nom"), "X");
      await user.type(within(dialog).getByLabelText("Montant"), "10");
      await user.click(within(dialog).getByRole("button", { name: "Enregistrer" }));

      expect(await within(dialog).findByRole("alert")).toHaveTextContent(
        "Une erreur est survenue de notre côté. Réessayez dans un instant.",
      );
    });
  });

  describe("archivage", () => {
    it("demande confirmation avant d'archiver, puis archive le type", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(getContributionTypes).mockResolvedValue([makeType({ id: 42 })]);
      vi.mocked(archiveContributionType).mockResolvedValue(makeType({ id: 42, status: "archived" }));
      const user = userEvent.setup();
      renderPage();

      await user.click(await screen.findByRole("button", { name: "Archiver" }));

      const dialog = await screen.findByRole("dialog", { name: "Archiver ce type ?" });
      expect(within(dialog).getByText("Il ne sera plus proposé pour de nouveaux paiements.")).toBeInTheDocument();
      expect(archiveContributionType).not.toHaveBeenCalled();

      await user.click(within(dialog).getByRole("button", { name: "Archiver" }));

      await waitFor(() => expect(archiveContributionType).toHaveBeenCalledWith(42));
      expect(await screen.findByText("Type de cotisation archivé.")).toBeInTheDocument();
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    });

    it("n'archive rien quand on annule la confirmation", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(getContributionTypes).mockResolvedValue([makeType()]);
      const user = userEvent.setup();
      renderPage();

      await user.click(await screen.findByRole("button", { name: "Archiver" }));
      const dialog = await screen.findByRole("dialog", { name: "Archiver ce type ?" });
      await user.click(within(dialog).getByRole("button", { name: "Annuler" }));

      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(archiveContributionType).not.toHaveBeenCalled();
    });

    it("affiche dans la confirmation le message en français quand l'archivage échoue", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(getContributionTypes).mockResolvedValue([makeType()]);
      vi.mocked(archiveContributionType).mockRejectedValue(
        new ApiError(409, { detail: "Ce type est déjà archivé." }),
      );
      const user = userEvent.setup();
      renderPage();

      await user.click(await screen.findByRole("button", { name: "Archiver" }));
      const dialog = await screen.findByRole("dialog", { name: "Archiver ce type ?" });
      await user.click(within(dialog).getByRole("button", { name: "Archiver" }));

      expect(await within(dialog).findByRole("alert")).toHaveTextContent("Ce type est déjà archivé.");
    });
  });

  describe("Enregistrer un paiement et Caisse Terrain Express", () => {
    it("masque les deux actions quand l'utilisateur ne peut pas enregistrer de paiement", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("vice_president"));
      renderPage();

      expect(await screen.findByRole("heading", { name: "Trésorerie" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Enregistrer un paiement" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Caisse Terrain Express" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Importer des cotisations" })).not.toBeInTheDocument();
    });

    it("affiche les deux actions et ouvre « Enregistrer un paiement » pour un Trésorier", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(getTreasuryCapabilities).mockResolvedValue(
        makeCapabilities({ can_write: true, can_record_payments: true }),
      );
      const user = userEvent.setup();
      renderPage();

      const recordButton = await screen.findByRole("button", { name: "Enregistrer un paiement" });
      expect(screen.getByRole("button", { name: "Caisse Terrain Express" })).toBeInTheDocument();

      await user.click(recordButton);
      expect(await screen.findByRole("dialog", { name: "Enregistrer un paiement" })).toBeInTheDocument();
    });

    it("affiche « Importer des cotisations » selon la capacité et l'ouvre", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("treasurer"));
      vi.mocked(getTreasuryCapabilities).mockResolvedValue(
        makeCapabilities({ can_write: true, can_record_payments: true }),
      );
      const user = userEvent.setup();
      renderPage();

      await user.click(await screen.findByRole("button", { name: "Importer des cotisations" }));
      expect(await screen.findByRole("dialog", { name: /Importer/ })).toBeInTheDocument();
    });

    it("affiche la section « Membres du club »", async () => {
      vi.mocked(getMyProfile).mockResolvedValue(makeProfile("vice_president"));
      renderPage();
      expect(await screen.findByRole("region", { name: "Membres du club" })).toBeInTheDocument();
    });
  });
});
