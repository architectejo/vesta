import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../../design-system";
import type { MembershipApplication } from "../../../api/clubs";

vi.mock("../../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../../api/clubs")>("../../../api/clubs");
  return {
    ...actual,
    getClubIdentity: vi.fn(),
    getMyProfile: vi.fn(),
    getMembershipApplication: vi.fn(),
    listPendingSponsorSignatures: vi.fn(),
    listPendingPresidentDecisions: vi.fn(),
    signSponsorApplication: vi.fn(),
    refuseSponsorApplication: vi.fn(),
    reassignSponsor: vi.fn(),
    cancelMembershipApplication: vi.fn(),
    recordMembershipFeePayment: vi.fn(),
    searchActiveClubPlayers: vi.fn(),
  };
});

import * as clubsApi from "../../../api/clubs";
import { ApiError } from "../../../api/client";
import { MembershipActions } from "./MembershipActions";
import { MembershipDecisionModal } from "./MembershipDecisionModal";
import { MembershipFeePaymentModal } from "./MembershipFeePaymentModal";
import { MembershipFollowUpCard } from "./MembershipFollowUpCard";
import { SponsorSignatureModal } from "./SponsorSignatureModal";

const PERSON = {
  membership_id: 50,
  first_name: "Paul",
  last_name: "Tshimanga",
  photo: null,
  position_label: "Milieu",
  jersey_number: null,
};

function makeApplication(overrides: Partial<MembershipApplication> = {}): MembershipApplication {
  return {
    id: 7,
    membership_id: 50,
    player: PERSON,
    sponsor: { ...PERSON, membership_id: 11, first_name: "Amos", last_name: "Kanku" },
    membership_status: "pending",
    membership_fee_paid: true,
    membership_fee_amount: "5.00",
    membership_fee_paid_on: "2026-10-01",
    application_pdf_url: "/api/clubs/applications/7/fiche-pdf/",
    generated_at: "2026-10-01T10:00:00Z",
    sponsor_notified_at: "2026-10-01T10:00:00Z",
    sponsor_decision: "pending",
    sponsor_signed_by_id: null,
    sponsor_signed_at: null,
    sponsor_refused_reason: "",
    sponsor_reminder_sent_at: null,
    president_alerted_at: null,
    resolved_at: null,
    cancelled_by_id: null,
    cancelled_reason: "",
    membership_fee_payment_id: 3,
    membership_fee_disposition: "",
    ...overrides,
  };
}

function renderWithProviders(ui: React.ReactElement, route = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[route]}>
    <QueryClientProvider client={client}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(clubsApi.getClubIdentity).mockResolvedValue({ currency: "USD" } as never);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("SponsorSignatureModal", () => {
  it("signe la fiche seulement après confirmation, sans champ PIN", async () => {
    vi.mocked(clubsApi.signSponsorApplication).mockResolvedValue(makeApplication({ sponsor_decision: "signed" }));
    const onDone = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<SponsorSignatureModal application={makeApplication()} onClose={vi.fn()} onDone={onDone} />);

    await user.click(screen.getByRole("button", { name: "Signer la fiche" }));
    await screen.findByRole("dialog", { name: /Signer la fiche d'adhésion de/ });
    expect(screen.queryByLabelText(/PIN/i)).not.toBeInTheDocument();
    expect(clubsApi.signSponsorApplication).not.toHaveBeenCalled();
    const confirm = screen.getByRole("dialog", { name: /Signer la fiche d'adhésion de/ });
    await user.click(within(confirm).getByRole("button", { name: "Signer la fiche" }));

    await waitFor(() => expect(clubsApi.signSponsorApplication).toHaveBeenCalledWith({ application_id: 7 }));
    expect(onDone).toHaveBeenCalled();
  });

  it("affiche le message de l'API si la signature échoue", async () => {
    vi.mocked(clubsApi.signSponsorApplication).mockRejectedValue(
      new ApiError(400, { detail: "Cette fiche a déjà été signée." }),
    );
    const user = userEvent.setup();
    renderWithProviders(<SponsorSignatureModal application={makeApplication()} onClose={vi.fn()} onDone={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Signer la fiche" }));
    const confirm = await screen.findByRole("dialog", { name: /Signer la fiche d'adhésion de/ });
    await user.click(within(confirm).getByRole("button", { name: "Signer la fiche" }));

    expect(await screen.findByText("Cette fiche a déjà été signée.")).toBeInTheDocument();
  });

  it("exige un motif pour refuser puis envoie le refus", async () => {
    vi.mocked(clubsApi.refuseSponsorApplication).mockResolvedValue(makeApplication({ sponsor_decision: "refused" }));
    const onDone = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<SponsorSignatureModal application={makeApplication()} onClose={vi.fn()} onDone={onDone} />);

    await user.click(screen.getByRole("button", { name: "Refuser" }));
    await user.click(await screen.findByRole("button", { name: "Refuser le parrainage" }));
    expect(await screen.findByText("Indiquez le motif.")).toBeInTheDocument();
    expect(clubsApi.refuseSponsorApplication).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Motif du refus"), "Je ne le connais pas");
    await user.click(screen.getByRole("button", { name: "Refuser le parrainage" }));

    await waitFor(() =>
      expect(clubsApi.refuseSponsorApplication).toHaveBeenCalledWith({
        application_id: 7,
        reason: "Je ne le connais pas",
      }),
    );
    expect(onDone).toHaveBeenCalled();
  });

  it("s'ouvre en lecture seule si la fiche n'est plus en attente", () => {
    renderWithProviders(
      <SponsorSignatureModal
        application={makeApplication({ sponsor_decision: "signed", resolved_at: "2026-10-02T00:00:00Z" })}
        onClose={vi.fn()}
        onDone={vi.fn()}
      />,
    );
    expect(screen.getByText("Cette fiche a déjà été signée ou n'est plus en attente.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Signer la fiche" })).not.toBeInTheDocument();
  });
});

describe("MembershipDecisionModal", () => {
  const refused = () => makeApplication({ sponsor_decision: "refused", sponsor_refused_reason: "Inconnu" });

  it("réassigne un autre parrain choisi par recherche", async () => {
    vi.mocked(clubsApi.searchActiveClubPlayers).mockResolvedValue([
      { id: 22, firstName: "Jean", lastName: "Mbuyi" },
    ]);
    vi.mocked(clubsApi.reassignSponsor).mockResolvedValue(makeApplication());
    const onDone = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<MembershipDecisionModal application={refused()} onClose={vi.fn()} onDone={onDone} />);

    expect(screen.getByText(/Inconnu/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Désigner un autre parrain" }));
    await user.type(screen.getByRole("combobox"), "Jean");
    await user.click(await screen.findByRole("option", { name: /Jean Mbuyi/ }));
    await user.click(screen.getByRole("button", { name: "Désigner" }));

    await waitFor(() =>
      expect(clubsApi.reassignSponsor).toHaveBeenCalledWith({ application_id: 7, new_sponsor_membership_id: 22 }),
    );
    expect(onDone).toHaveBeenCalled();
  });

  it("annule avec remboursement après confirmation, sans champ PIN", async () => {
    vi.mocked(clubsApi.cancelMembershipApplication).mockResolvedValue(makeApplication());
    const onDone = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<MembershipDecisionModal application={refused()} onClose={vi.fn()} onDone={onDone} />);

    await user.click(screen.getByRole("button", { name: "Annuler l'adhésion" }));
    await user.click(screen.getByRole("button", { name: "Rembourser" }));
    await user.type(screen.getByLabelText("Motif"), "Doublon");
    await user.click(screen.getAllByRole("button", { name: "Annuler l'adhésion" }).at(-1)!);
    await screen.findByRole("dialog", { name: /Annuler l'adhésion de/ });
    expect(screen.queryByLabelText(/PIN/i)).not.toBeInTheDocument();
    expect(screen.getByText(/paiement d'adhésion de 5 USD remboursé/)).toBeInTheDocument();
    expect(clubsApi.cancelMembershipApplication).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirmer l'annulation" }));

    await waitFor(() =>
      expect(clubsApi.cancelMembershipApplication).toHaveBeenCalledWith({
        application_id: 7,
        reason: "Doublon",
        disposition: "refunded",
      }),
    );
    expect(onDone).toHaveBeenCalled();
  });

  it("annule en conservant le paiement", async () => {
    vi.mocked(clubsApi.cancelMembershipApplication).mockResolvedValue(makeApplication());
    const user = userEvent.setup();
    renderWithProviders(<MembershipDecisionModal application={refused()} onClose={vi.fn()} onDone={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Annuler l'adhésion" }));
    await user.click(screen.getByRole("button", { name: "Conserver" }));
    await user.type(screen.getByLabelText("Motif"), "Refus du club");
    await user.click(screen.getAllByRole("button", { name: "Annuler l'adhésion" }).at(-1)!);
    await user.click(await screen.findByRole("button", { name: "Confirmer l'annulation" }));

    await waitFor(() =>
      expect(clubsApi.cancelMembershipApplication).toHaveBeenCalledWith(
        expect.objectContaining({ disposition: "kept" }),
      ),
    );
  });

  it("n'offre aucune action quand le parrain est seulement sans réponse", () => {
    renderWithProviders(
      <MembershipDecisionModal
        application={makeApplication({ president_alerted_at: new Date().toISOString() })}
        onClose={vi.fn()}
        onDone={vi.fn()}
      />,
    );
    expect(screen.getByText(/Aucune action n'est possible/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Désigner un autre parrain" })).not.toBeInTheDocument();
  });
});

describe("MembershipFeePaymentModal", () => {
  it("enregistre les frais d'adhésion après confirmation, sans champ PIN", async () => {
    vi.mocked(clubsApi.recordMembershipFeePayment).mockResolvedValue(makeApplication());
    const onDone = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <MembershipFeePaymentModal
        application={makeApplication({ membership_fee_paid: false })}
        onClose={vi.fn()}
        onDone={onDone}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(await screen.findByText("Saisissez un montant supérieur à 0.")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Montant/), "5");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await screen.findByRole("dialog", { name: /Valider ce paiement de/ });
    expect(screen.queryByLabelText(/PIN/i)).not.toBeInTheDocument();
    expect(clubsApi.recordMembershipFeePayment).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Valider" }));

    await waitFor(() =>
      expect(clubsApi.recordMembershipFeePayment).toHaveBeenCalledWith(
        expect.objectContaining({ application_id: 7, amount: "5", method: "cash" }),
      ),
    );
    expect(onDone).toHaveBeenCalled();
    expect(vi.mocked(clubsApi.recordMembershipFeePayment).mock.calls[0]?.[0].client_uuid).toBeTruthy();
  });

  it("conserve le client_uuid après erreur réseau puis affiche le conflit 409", async () => {
    vi.mocked(clubsApi.recordMembershipFeePayment)
      .mockRejectedValueOnce(new ApiError(0, null))
      .mockRejectedValueOnce(new ApiError(409, { detail: "x", code: "client_uuid_conflict" }));
    const user = userEvent.setup();
    renderWithProviders(
      <MembershipFeePaymentModal
        application={makeApplication({ membership_fee_paid: false })}
        onClose={vi.fn()}
        onDone={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText(/Montant/), "5");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await user.click(await screen.findByRole("button", { name: "Valider" }));
    await waitFor(() => expect(clubsApi.recordMembershipFeePayment).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /Valider ce paiement/ })).not.toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await user.click(await screen.findByRole("button", { name: "Valider" }));
    await waitFor(() => expect(clubsApi.recordMembershipFeePayment).toHaveBeenCalledTimes(2));

    const calls = vi.mocked(clubsApi.recordMembershipFeePayment).mock.calls;
    expect(calls[0]?.[0].client_uuid).toBeTruthy();
    expect(calls[1]?.[0].client_uuid).toBe(calls[0]?.[0].client_uuid);
    expect(
      await screen.findByText(
        "Cette saisie a déjà été enregistrée avec des informations différentes. Rechargez la page.",
      ),
    ).toBeInTheDocument();
  });
});

describe("MembershipFollowUpCard", () => {
  it("affiche un état vide explicite", async () => {
    vi.mocked(clubsApi.listPendingSponsorSignatures).mockResolvedValue([]);
    renderWithProviders(<MembershipFollowUpCard isPresident={false} />);
    expect(await screen.findByText("Aucune adhésion à traiter pour l'instant.")).toBeInTheDocument();
  });

  it("liste les fiches à signer et ouvre la modale de signature", async () => {
    vi.mocked(clubsApi.listPendingSponsorSignatures).mockResolvedValue([makeApplication()]);
    const user = userEvent.setup();
    renderWithProviders(<MembershipFollowUpCard isPresident={false} />);

    await user.click(await screen.findByRole("button", { name: /Paul Tshimanga/ }));
    expect(await screen.findByText("Fiche d'adhésion de Paul Tshimanga")).toBeInTheDocument();
  });

  it("ouvre la modale de signature du parrain depuis une notification (?adhesion=)", async () => {
    vi.mocked(clubsApi.listPendingSponsorSignatures).mockResolvedValue([makeApplication()]);
    renderWithProviders(<MembershipFollowUpCard isPresident={false} />, "/?adhesion=7");
    expect(await screen.findByText("Fiche d'adhésion de Paul Tshimanga")).toBeInTheDocument();
  });

  it("ouvre la décision du Président depuis une notification (?adhesion=)", async () => {
    vi.mocked(clubsApi.listPendingSponsorSignatures).mockResolvedValue([]);
    vi.mocked(clubsApi.listPendingPresidentDecisions).mockResolvedValue({
      refused: [makeApplication({ id: 8, sponsor_decision: "refused", sponsor_refused_reason: "Inconnu du club" })],
      awaiting_sponsor: [],
    });
    renderWithProviders(<MembershipFollowUpCard isPresident />, "/?adhesion=8");
    expect(await screen.findByRole("heading", { name: "Adhésion de Paul Tshimanga" })).toBeInTheDocument();
  });

  it("prévient quand l'adhésion ciblée ne demande plus d'action", async () => {
    vi.mocked(clubsApi.listPendingSponsorSignatures).mockResolvedValue([]);
    renderWithProviders(<MembershipFollowUpCard isPresident={false} />, "/?adhesion=99");
    expect(await screen.findByText("Cette adhésion ne demande plus d'action de votre part.")).toBeInTheDocument();
  });

  it("montre au Président les refus et les silences", async () => {
    vi.mocked(clubsApi.listPendingSponsorSignatures).mockResolvedValue([]);
    vi.mocked(clubsApi.listPendingPresidentDecisions).mockResolvedValue({
      refused: [makeApplication({ id: 8, sponsor_decision: "refused" })],
      awaiting_sponsor: [makeApplication({ id: 9, president_alerted_at: new Date().toISOString() })],
    });
    renderWithProviders(<MembershipFollowUpCard isPresident />);
    expect(await screen.findByText("Parrainages refusés")).toBeInTheDocument();
    expect(screen.getByText("Parrains sans réponse")).toBeInTheDocument();
  });
});

describe("MembershipActions", () => {
  it("propose la signature au parrain désigné seulement", async () => {
    vi.mocked(clubsApi.getMyProfile).mockResolvedValue({ membership_id: 11, roles: [] } as never);
    vi.mocked(clubsApi.getMembershipApplication).mockResolvedValue(makeApplication());
    renderWithProviders(<MembershipActions membershipId={50} />);
    expect(await screen.findByRole("button", { name: "Signer la fiche d'adhésion" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Décider de l'adhésion" })).not.toBeInTheDocument();
  });

  it("propose la décision au Président après un refus", async () => {
    vi.mocked(clubsApi.getMyProfile).mockResolvedValue({
      membership_id: 1,
      roles: [{ role: "president", label: "Président" }],
    } as never);
    vi.mocked(clubsApi.getMembershipApplication).mockResolvedValue(makeApplication({ sponsor_decision: "refused" }));
    renderWithProviders(<MembershipActions membershipId={50} />);
    expect(await screen.findByRole("button", { name: "Décider de l'adhésion" })).toBeInTheDocument();
  });

  it("propose les frais d'adhésion au Trésorier tant qu'ils ne sont pas payés", async () => {
    vi.mocked(clubsApi.getMyProfile).mockResolvedValue({
      membership_id: 2,
      roles: [{ role: "treasurer", label: "Trésorier" }],
    } as never);
    vi.mocked(clubsApi.getMembershipApplication).mockResolvedValue(
      makeApplication({ membership_fee_paid: false, generated_at: null }),
    );
    renderWithProviders(<MembershipActions membershipId={50} />);
    expect(await screen.findByRole("button", { name: "Enregistrer les frais d'adhésion" })).toBeInTheDocument();
  });

  it("n'affiche rien si l'API refuse de servir le dossier", async () => {
    vi.mocked(clubsApi.getMyProfile).mockResolvedValue({ membership_id: 3, roles: [] } as never);
    vi.mocked(clubsApi.getMembershipApplication).mockRejectedValue(new ApiError(403, { detail: "Non autorisé." }));
    const { container } = renderWithProviders(<MembershipActions membershipId={50} />);
    await waitFor(() => expect(clubsApi.getMembershipApplication).toHaveBeenCalled());
    expect(container.querySelector("button")).toBeNull();
  });
});
