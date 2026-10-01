import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SocialAssistanceRequest, TreasuryCapabilities } from "../../api/treasury";
import { ToastProvider } from "../../design-system";
import { AssistanceRequestDetailModal } from "./AssistanceRequestDetailModal";

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getSocialAssistanceRequest: vi.fn(),
    approveSocialAssistanceRequest: vi.fn(),
    rejectSocialAssistanceRequest: vi.fn(),
    downloadSocialAssistanceAttachment: vi.fn(),
  };
});

import {
  approveSocialAssistanceRequest,
  getSocialAssistanceRequest,
  rejectSocialAssistanceRequest,
} from "../../api/treasury";

function makeCapabilities(overrides: Partial<TreasuryCapabilities> = {}): TreasuryCapabilities {
  return {
    can_read: true,
    can_write: false,
    can_record_payments: false,
    can_read_expenses: true,
    can_manage_expense_categories: false,
    can_submit_expenses: false,
    can_validate_expenses: true,
    can_derogate: true,
    can_upload_expense_receipts: false,
    can_manage_assistance_scales: false,
    can_process_assistance_requests: true,
    can_request_assistance: true,
    ...overrides,
  };
}

function makeRequest(overrides: Partial<SocialAssistanceRequest> = {}): SocialAssistanceRequest {
  return {
    id: 1,
    membership_id: 5,
    player_name: "Paul Kabeya",
    event_type: "birth",
    event_type_label: "Naissance",
    event_date: "2026-08-01",
    description: "Naissance de mon fils",
    planned_amount: "40.00",
    currency: "USD",
    processing_days: 7,
    eligible_at_submission: true,
    amount_to_regularize_at_submission: "0.00",
    status: "submitted",
    status_label: "Envoyée",
    submitted_at: "2026-08-02T10:00:00Z",
    decided_at: null,
    rejection_reason: "",
    expense: null,
    attachment_url: "/api/v1/treasury/social-assistance/requests/1/attachment/",
    current_eligibility: {
      eligible: true,
      was_in_good_standing_at_event: true,
      amount_due_at_event: "0.00",
      amount_to_regularize: "0.00",
      can_be_approved: true,
      currency: "USD",
      reason: "",
    },
    ...overrides,
  };
}

function renderModal(request: SocialAssistanceRequest, capabilities: TreasuryCapabilities) {
  vi.mocked(getSocialAssistanceRequest).mockResolvedValue(request);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  const onChanged = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AssistanceRequestDetailModal
          requestId={request.id}
          capabilities={capabilities}
          onClose={onClose}
          onChanged={onChanged}
        />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onClose, onChanged };
}

describe("AssistanceRequestDetailModal", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it("accepte la demande sans code PIN (résolution du §9.1)", async () => {
    vi.mocked(approveSocialAssistanceRequest).mockResolvedValue(makeRequest({ status: "approved" }));
    const user = userEvent.setup();
    renderModal(makeRequest(), makeCapabilities());

    const acceptButton = await screen.findByRole("button", { name: "Accepter la demande" });
    expect(screen.queryByLabelText("Votre code PIN")).not.toBeInTheDocument();
    await user.click(acceptButton);

    await waitFor(() => expect(approveSocialAssistanceRequest).toHaveBeenCalledWith(1));
    expect(await screen.findByText("Demande acceptée. Une dépense en attente a été créée.")).toBeInTheDocument();
  });

  it("désactive « Accepter la demande » si le joueur est encore en dette (10.2 n° 37)", async () => {
    renderModal(
      makeRequest({
        current_eligibility: {
          eligible: false,
          was_in_good_standing_at_event: false,
          amount_due_at_event: "20.00",
          amount_to_regularize: "20.00",
          can_be_approved: false,
          currency: "USD",
          reason: "Demande non approuvable : le joueur est en dette (20.00 USD à régulariser).",
        },
      }),
      makeCapabilities(),
    );

    expect(
      await screen.findByText("Demande non approuvable : le joueur est en dette (20.00 USD à régulariser)."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accepter la demande" })).toBeDisabled();
  });

  it("affiche le bandeau orange et le badge « Non éligible » pour une demande non éligible à l'envoi", async () => {
    renderModal(
      makeRequest({ eligible_at_submission: false, amount_to_regularize_at_submission: "15.00" }),
      makeCapabilities(),
    );

    expect(await screen.findByText("Non éligible · 15 USD")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Paul n'était pas en ordre à la date de l'événement (15 USD à régulariser). Vous décidez au cas par cas.",
      ),
    ).toBeInTheDocument();
  });

  it("refuse la demande avec un motif obligatoire", async () => {
    vi.mocked(rejectSocialAssistanceRequest).mockResolvedValue(makeRequest({ status: "rejected" }));
    const user = userEvent.setup();
    renderModal(makeRequest(), makeCapabilities());

    await user.click(await screen.findByRole("button", { name: "Refuser" }));
    const dialog = await screen.findByRole("dialog", { name: "Refuser la demande" });
    await user.click(within(dialog).getByRole("button", { name: "Refuser la demande" }));
    expect(await within(dialog).findByText("Indiquez le motif du refus.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Motif du refus"), "Pièce justificative illisible");
    await user.click(within(dialog).getByRole("button", { name: "Refuser la demande" }));

    await waitFor(() =>
      expect(rejectSocialAssistanceRequest).toHaveBeenCalledWith(1, "Pièce justificative illisible"),
    );
    expect(await screen.findByText("Demande refusée. Paul a été prévenu.")).toBeInTheDocument();
  });

  it("affiche une demande traitée en lecture seule", async () => {
    renderModal(
      makeRequest({ status: "approved", decided_at: "2026-08-05T00:00:00Z", expense: { id: 3, status: "pending", status_label: "En attente" } }),
      makeCapabilities(),
    );

    await screen.findByText("Approuvée");
    expect(screen.queryByRole("button", { name: "Accepter la demande" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Refuser" })).not.toBeInTheDocument();
    // Deux boutons « Fermer » : la croix d'en-tête et le pied de la modale.
    expect(screen.getAllByRole("button", { name: "Fermer" })).toHaveLength(2);
  });
});
