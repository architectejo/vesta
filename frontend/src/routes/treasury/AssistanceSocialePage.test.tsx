import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import { ApiError } from "../../api/client";
import type {
  SocialAssistanceRequest,
  SocialAssistanceRequestListResponse,
  TreasuryCapabilities,
} from "../../api/treasury";
import { ToastProvider } from "../../design-system";
import { AssistanceSocialePage } from "./AssistanceSocialePage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return {
    ...actual,
    getTreasuryCapabilities: vi.fn(),
    getSocialAssistanceRequests: vi.fn(),
    getSocialAssistanceRequest: vi.fn(),
  };
});

import { getMyProfile } from "../../api/clubs";
import { getSocialAssistanceRequest, getSocialAssistanceRequests, getTreasuryCapabilities } from "../../api/treasury";

function makeProfile(): MyProfile {
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
    roles: [{ role: "president", label: "Président" }],
    email_notifications_enabled: true,
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
    },
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
    current_eligibility: null,
    ...overrides,
  };
}

function listResponse(results: SocialAssistanceRequest[]): SocialAssistanceRequestListResponse {
  return { count: results.length, next_offset: null, results };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AssistanceSocialePage />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("AssistanceSocialePage", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it("refuse l'accès à un rôle qui ne traite pas les demandes", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(
      makeCapabilities({ can_process_assistance_requests: false }),
    );
    renderPage();

    expect(await screen.findByText("Vous n'avez pas accès à cette page.")).toBeInTheDocument();
    expect(screen.getByText("Suivez vos propres demandes depuis « Mon profil ».")).toBeInTheDocument();
  });

  it("affiche un message d'erreur en français quand les capacités ne chargent pas", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockRejectedValueOnce(new ApiError(500, null));
    renderPage();

    expect(await screen.findByText("Impossible de charger cette section.")).toBeInTheDocument();
  });

  it("affiche les états vides de « À traiter » et « Demandes traitées »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());
    vi.mocked(getSocialAssistanceRequests).mockResolvedValue(listResponse([]));
    renderPage();

    expect(await screen.findByText("Aucune demande d'assistance à traiter.")).toBeInTheDocument();
    expect(await screen.findByText("Aucune demande traitée pour l'instant.")).toBeInTheDocument();
  });

  it("liste les demandes à traiter avec l'éligibilité et ouvre le détail", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());
    vi.mocked(getSocialAssistanceRequests).mockImplementation(({ status } = {}) =>
      Promise.resolve(listResponse(status?.includes("submitted") ? [makeRequest()] : [])),
    );
    vi.mocked(getSocialAssistanceRequest).mockResolvedValue(makeRequest());
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("Paul Kabeya")).toBeInTheDocument();
    expect(screen.getByText("Éligible")).toBeInTheDocument();

    await user.click(screen.getByText("Paul Kabeya"));
    expect(await screen.findByRole("dialog", { name: "Demande d'assistance de Paul Kabeya" })).toBeInTheDocument();
  });

  it("affiche « Non éligible » avec le montant à régulariser pour une demande non éligible", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTreasuryCapabilities).mockResolvedValue(makeCapabilities());
    vi.mocked(getSocialAssistanceRequests).mockImplementation(({ status } = {}) =>
      Promise.resolve(
        listResponse(
          status?.includes("submitted")
            ? [makeRequest({ eligible_at_submission: false, amount_to_regularize_at_submission: "20.00" })]
            : [],
        ),
      ),
    );
    renderPage();

    expect(await screen.findByText("Non éligible · 20 USD")).toBeInTheDocument();
  });
});
