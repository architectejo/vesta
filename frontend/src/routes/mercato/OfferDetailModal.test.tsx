import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TransferOffer } from "../../api/mercato";
import { ToastProvider } from "../../design-system";
import { OfferDetailModal } from "./OfferDetailModal";

vi.mock("../../api/mercato", async () => {
  const actual = await vi.importActual<typeof import("../../api/mercato")>("../../api/mercato");
  return { ...actual, getOffer: vi.fn() };
});
vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getClubIdentity: vi.fn() };
});

import { getOffer } from "../../api/mercato";

const ORIGIN = { id: 1, name: "Club A", logo: null };
const TARGET = { id: 2, name: "Club B", logo: null };

function offer(overrides: Partial<TransferOffer> = {}): TransferOffer {
  return {
    id: 9,
    status: "awaiting_quitus",
    origin_club: ORIGIN,
    target_club: TARGET,
    player: {
      membership_id: 10,
      first_name: "Jean",
      last_name: "Kabila",
      photo: null,
      position: "midfielder",
      position_label: "Milieu",
      jersey_number: 8,
      age: 24,
      club: ORIGIN,
      average_rating: "7.5",
      is_on_transfer_market: true,
    },
    message: "Venez nous rejoindre.",
    conditions: "",
    membership_fee_due_at_target: true,
    // Contrat de l'API pour le DS, le Coach et l'Assistant du Coach du club A.
    debt_amount: null,
    debt_checked_at: null,
    player_decision_at: "2026-03-13T10:00:00Z",
    quitus_available: false,
    completed_at: null,
    created_at: "2026-03-12T10:00:00Z",
    ...overrides,
  };
}

function renderModal(viewerClubId: number) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <OfferDetailModal offerId={9} viewerIsTargetPlayer={false} viewerClubId={viewerClubId} onClose={vi.fn()} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("OfferDetailModal — offre bloquée vue par le Coach ou le DS du club d'origine (CDC 10.3 n° 188 et 192)", () => {
  it("ni « dette », ni « régulariser », ni « solde », ni montant : texte neutre du club A", async () => {
    vi.mocked(getOffer).mockResolvedValue(offer());
    renderModal(ORIGIN.id);

    const dialog = await screen.findByRole("dialog", { name: "Offre pour Jean Kabila" });
    expect(
      await screen.findByText(
        "Quitus en attente. Le transfert se fera automatiquement dès que le quitus pourra être établi.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Quitus en attente")).toBeInTheDocument();
    expect(screen.getByText("Vérification auprès de Club A")).toBeInTheDocument();
    const text = dialog.textContent ?? "";
    expect(text).not.toMatch(/dette|régularis|solde|\d+[.,]\d{2}/i);
    expect(text).not.toContain("Bloquée");
  });

  it("club B : texte propre au club offrant, toujours sans montant ni dette", async () => {
    vi.mocked(getOffer).mockResolvedValue(offer());
    renderModal(TARGET.id);

    expect(await screen.findByText("En attente du quitus de son club actuel")).toBeInTheDocument();
    const text = screen.getByRole("dialog", { name: "Offre pour Jean Kabila" }).textContent ?? "";
    expect(text).not.toMatch(/dette|régularis|\d+[.,]\d{2}/i);
  });
});
