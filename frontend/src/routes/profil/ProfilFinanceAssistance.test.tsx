import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { ToastProvider } from "../../design-system";

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return { ...actual, triggerBlobDownload: vi.fn() };
});

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getMyBalance: vi.fn(),
    getContributeInfo: vi.fn(),
    getPaymentDeclarations: vi.fn(),
    getMyPayments: vi.fn(),
    getMyPayment: vi.fn(),
    getMyGrid: vi.fn(),
    getMyGridMonthDetail: vi.fn(),
    getPaymentDeclaration: vi.fn(),
    downloadPaymentReceipt: vi.fn(),
    getSocialAssistanceRequests: vi.fn(),
    getSocialAssistanceScales: vi.fn(),
    getSocialAssistancePreview: vi.fn(),
    createSocialAssistanceRequest: vi.fn(),
  };
});

import { triggerBlobDownload } from "../../api/client";
import * as treasury from "../../api/treasury";
import { AssistanceCard } from "./AssistanceCard";
import { FinancialSituationCard } from "./FinancialSituationCard";

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
    <QueryClientProvider client={client}>
      <ToastProvider>{node}</ToastProvider>
    </QueryClientProvider>
    </MemoryRouter>,
  );
}

const balance = {
  membership_id: 1,
  club_id: 1,
  balance: "-20.00",
  amount_due: "20.00",
  is_in_good_standing: false,
  reason: "Le joueur est en dette : 20.00 USD à régulariser.",
  currency: "USD",
};

function contribute(link: string | null) {
  return {
    payment_link_configured: link !== null,
    payment_link_url: link,
    currency: "USD",
    contribution_types: [],
    default_contribution_type_id: null,
  };
}

function myPayment(id: number, receipt: boolean) {
  return {
    id,
    contribution_type: { id: 1, name: "Cotisation mensuelle" },
    amount: "10.00",
    currency: "USD",
    paid_on: "2026-03-12",
    method_label: "Espèces",
    reference: "",
    status: "validated",
    receipt_available: receipt,
    receipt_number: receipt ? id : null,
  } as unknown as treasury.MyPaymentItem;
}

function declaration(id: number, receipt: boolean) {
  return {
    id,
    contribution_type: { id: 1, name: "Cotisation mensuelle" },
    amount: "10.00",
    currency: "USD",
    paid_on: "2026-03-12",
    status: receipt ? "validated" : "to_validate",
    receipt_available: receipt,
  } as unknown as treasury.PaymentDeclaration;
}

const emptyPage = { count: 0, next_offset: null, results: [] };

function mockNoPayments() {
  vi.mocked(treasury.getMyPayments).mockResolvedValue(emptyPage);
  vi.mocked(treasury.getPaymentDeclarations).mockResolvedValue(emptyPage);
  vi.mocked(treasury.getMyGrid).mockResolvedValue({
    year: 2026,
    currency: "USD",
    today: "2026-10-07",
    months: [],
    states: {} as treasury.MyGridResponse["states"],
    player_status: { balance: "0", amount_due: "0", is_in_good_standing: true, reason: "", currency: "USD" },
    lines: [],
  });
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("FinancialSituationCard", () => {
  it("affiche le solde, la raison de l'API et masque « Contribuer » sans lien de paiement", async () => {
    vi.mocked(treasury.getMyBalance).mockResolvedValue(balance);
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute(null));
    mockNoPayments();
    wrap(<FinancialSituationCard />);

    expect(await screen.findByText(/Le joueur est en dette : 20.00 USD/)).toBeInTheDocument();
    expect(await screen.findByText("Aucun paiement enregistré pour l'instant.")).toBeInTheDocument();
    expect(await screen.findByText(/pas encore configuré de lien de paiement/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Contribuer" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "J'ai payé" })).toBeInTheDocument();
  });

  it("ouvre la modale « J'ai payé » depuis la carte", async () => {
    vi.mocked(treasury.getMyBalance).mockResolvedValue(balance);
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute("https://pay.example/club"));
    mockNoPayments();
    wrap(<FinancialSituationCard />);

    await userEvent.click(await screen.findByRole("button", { name: "J'ai payé" }));
    expect(await screen.findByText("Envoyer la déclaration")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Contribuer" })).toBeInTheDocument();
  });

  it("fusionne paiements validés et déclarations, reçu seulement si disponible", async () => {
    mockNoPayments();
    vi.mocked(treasury.getMyBalance).mockResolvedValue(balance);
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute(null));
    vi.mocked(treasury.getMyPayments).mockResolvedValue({
      count: 2,
      next_offset: null,
      results: [myPayment(7, true), myPayment(9, false)],
    });
    vi.mocked(treasury.getPaymentDeclarations).mockResolvedValue({
      count: 1,
      next_offset: null,
      results: [declaration(8, false)],
    });
    vi.mocked(treasury.downloadPaymentReceipt).mockResolvedValue({ blob: new Blob(["pdf"]), filename: "recu.pdf" });
    wrap(<FinancialSituationCard />);

    expect(await screen.findAllByRole("button", { name: /^Paiement du/ })).toHaveLength(3);
    expect(treasury.getMyPayments).toHaveBeenCalledWith(expect.objectContaining({ status: ["validated", "cancelled"] }));
    const buttons = await screen.findAllByRole("button", { name: "Télécharger le reçu" });
    expect(buttons).toHaveLength(1);
    await userEvent.click(buttons[0] as HTMLElement);
    await waitFor(() => expect(treasury.downloadPaymentReceipt).toHaveBeenCalledWith(7));
    await waitFor(() => expect(triggerBlobDownload).toHaveBeenCalled());
  });

  it("ouvre le détail d'un paiement validé avec sa répartition par mois", async () => {
    mockNoPayments();
    vi.mocked(treasury.getMyBalance).mockResolvedValue(balance);
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute(null));
    vi.mocked(treasury.getMyPayments).mockResolvedValue({ count: 1, next_offset: null, results: [myPayment(7, false)] });
    vi.mocked(treasury.getMyPayment).mockResolvedValue({
      ...myPayment(7, false),
      allocations: [{ period: "2026-03-01", period_label: "mars 2026", amount: "10.00" }],
    });
    wrap(<FinancialSituationCard />);

    await userEvent.click(await screen.findByRole("button", { name: /^Paiement du/ }));
    expect(await screen.findByText("Détail du paiement")).toBeInTheDocument();
    expect(treasury.getMyPayment).toHaveBeenCalledWith(7);
    expect(await screen.findByText("Mois")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Télécharger le reçu" })).not.toBeInTheDocument();
  });

  it("propose « Voir plus » quand l'API indique une page suivante", async () => {
    mockNoPayments();
    vi.mocked(treasury.getMyBalance).mockResolvedValue(balance);
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute(null));
    vi.mocked(treasury.getMyPayments)
      .mockResolvedValueOnce({ count: 2, next_offset: 1, results: [myPayment(7, false)] })
      .mockResolvedValueOnce({ count: 2, next_offset: null, results: [myPayment(6, false)] });
    wrap(<FinancialSituationCard />);

    await userEvent.click(await screen.findByRole("button", { name: "Voir plus" }));
    await waitFor(() => expect(screen.getAllByRole("button", { name: /^Paiement du/ })).toHaveLength(2));
  });

  it("affiche l'état vide des cotisations quand lines est vide", async () => {
    mockNoPayments();
    vi.mocked(treasury.getMyBalance).mockResolvedValue(balance);
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute(null));
    wrap(<FinancialSituationCard />);
    expect(await screen.findByText("Vous n'êtes rattaché à aucun type de cotisation.")).toBeInTheDocument();
  });

  it("affiche la mini-grille, change d'année et ouvre le détail du mois", async () => {
    mockNoPayments();
    vi.mocked(treasury.getMyBalance).mockResolvedValue(balance);
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute(null));
    const cell = {
      period: "2026-01-01",
      month: 1,
      amount_due: "10.00",
      allocated: "10.00",
      state: "paid" as const,
      state_label: "Payé",
      overdue_amount: "0.00",
    };
    vi.mocked(treasury.getMyGrid).mockResolvedValue({
      year: 2026,
      currency: "USD",
      today: "2026-10-07",
      months: [{ period: "2026-01-01", month: 1, label: "janv.", long_label: "janvier 2026" }],
      states: {} as treasury.MyGridResponse["states"],
      player_status: { balance: "0", amount_due: "0", is_in_good_standing: true, reason: "", currency: "USD" },
      lines: [
        {
          contribution_type: { id: 3, name: "Cotisation mensuelle" } as treasury.GridContributionType,
          cells: [cell],
          total: "10.00",
          overdue_amount: "0.00",
          has_unpaid: false,
        },
      ],
    });
    vi.mocked(treasury.getMyGridMonthDetail).mockResolvedValue({
      contribution_type: { id: 3, name: "Cotisation mensuelle" } as treasury.GridContributionType,
      player: {} as treasury.GridMonthDetail["player"],
      currency: "USD",
      period: "2026-01-01",
      period_label: "janvier 2026",
      cell,
      payments: [],
      can_record_payment: false,
    });
    wrap(<FinancialSituationCard />);

    await userEvent.click(await screen.findByRole("button", { name: /janvier 2026 : Payé/ }));
    expect(await screen.findByText("Aucun paiement n'a alimenté ce mois.")).toBeInTheDocument();
    expect(treasury.getMyGridMonthDetail).toHaveBeenCalledWith(3, new Date().getFullYear(), 1);

    await userEvent.click(screen.getAllByRole("button", { name: "Fermer" }).at(-1) as HTMLElement);
    await userEvent.click(screen.getByRole("button", { name: "Année précédente" }));
    await waitFor(() => expect(treasury.getMyGrid).toHaveBeenCalledWith(new Date().getFullYear() - 1));
  });

  it("charge 20 paiements par page", async () => {
    mockNoPayments();
    vi.mocked(treasury.getMyBalance).mockResolvedValue(balance);
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute(null));
    wrap(<FinancialSituationCard />);
    await waitFor(() =>
      expect(treasury.getMyPayments).toHaveBeenCalledWith(expect.objectContaining({ limit: 20, offset: 0 })),
    );
  });

  it("ne permet pas de consulter une année postérieure à l'année en cours", async () => {
    mockNoPayments();
    vi.mocked(treasury.getMyBalance).mockResolvedValue(balance);
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute(null));
    wrap(<FinancialSituationCard />);
    expect(await screen.findByRole("button", { name: "Année suivante" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Année précédente" }));
    expect(await screen.findByRole("button", { name: "Année suivante" })).toBeEnabled();
  });

  it("affiche une erreur avec « Réessayer » si le solde ne charge pas", async () => {
    vi.mocked(treasury.getMyBalance).mockRejectedValue(new Error("boom"));
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute(null));
    mockNoPayments();
    wrap(<FinancialSituationCard />);
    expect(await screen.findByText("Impossible de charger votre situation financière.")).toBeInTheDocument();
  });
});

describe("AssistanceCard", () => {
  it("affiche l'état vide et les barèmes lus depuis l'API", async () => {
    vi.mocked(treasury.getSocialAssistanceRequests).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute(null));
    vi.mocked(treasury.getSocialAssistanceScales).mockResolvedValue([
      {
        id: 1,
        event_type: "birth",
        event_type_label: "Naissance",
        amount: "50.00",
        processing_days: 7,
        expense_category: { id: 1, name: "Social" },
        status: "active",
        archived_at: null,
      },
    ]);
    wrap(<AssistanceCard />);

    expect(await screen.findByText("Aucune demande d'assistance.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Voir les barèmes" }));
    expect(await screen.findByText("50 USD")).toBeInTheDocument();
    expect(screen.getByText("Délai : 7 jours")).toBeInTheDocument();
  });

  it("affiche « En attente » pour une demande non encore traitée", async () => {
    vi.mocked(treasury.getSocialAssistanceRequests).mockResolvedValue({
      count: 1,
      next_offset: null,
      results: [
        {
          id: 4,
          event_type: "birth",
          event_type_label: "Naissance",
          event_date: "2026-09-01",
          planned_amount: "50.00",
          currency: "USD",
          status: "submitted",
          eligible_at_submission: false,
        } as unknown as treasury.SocialAssistanceRequest,
      ],
    });
    wrap(<AssistanceCard />);
    expect(await screen.findByText("En attente")).toBeInTheDocument();
  });

  it("garde « Envoyer la demande » actif et montre le montant à régulariser fourni par l'API", async () => {
    vi.mocked(treasury.getSocialAssistanceRequests).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute("https://pay.example/club"));
    vi.mocked(treasury.getSocialAssistancePreview).mockResolvedValue({
      scale_configured: true,
      planned_amount: "50.00",
      processing_days: 7,
      eligibility: {
        eligible: false,
        was_in_good_standing_at_event: false,
        amount_due_at_event: "20.00",
        amount_to_regularize: "20.00",
        can_be_approved: false,
        currency: "USD",
        reason: "En dette",
      },
    });
    wrap(<AssistanceCard />);

    await userEvent.click(await screen.findByRole("button", { name: "Demander une assistance" }));
    await userEvent.click(await screen.findByRole("button", { name: "Naissance" }));
    await userEvent.type(screen.getByLabelText("Date de l'événement"), "2026-01-10");

    expect(await screen.findByText(/Régularisez 20 USD pour devenir éligible/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Envoyer la demande" })).toBeEnabled();
  });

  it("refuse l'envoi sans description ni pièce et indique les erreurs en français", async () => {
    vi.mocked(treasury.getSocialAssistanceRequests).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(treasury.getContributeInfo).mockResolvedValue(contribute(null));
    wrap(<AssistanceCard />);

    await userEvent.click(await screen.findByRole("button", { name: "Demander une assistance" }));
    await userEvent.click(await screen.findByRole("button", { name: "Envoyer la demande" }));
    expect(await screen.findByText("Choisissez un événement.")).toBeInTheDocument();
    expect(screen.getByText("Joignez une pièce justificative.")).toBeInTheDocument();
    expect(treasury.createSocialAssistanceRequest).not.toHaveBeenCalled();
  });
});
