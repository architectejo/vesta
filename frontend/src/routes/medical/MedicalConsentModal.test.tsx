import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import { MedicalConsentModal } from "./MedicalConsentModal";

vi.mock("../../api/medical", async () => {
  const actual = await vi.importActual<typeof import("../../api/medical")>("../../api/medical");
  return {
    ...actual,
    getMyPresidentAccess: vi.fn(),
    grantMyPresidentAccess: vi.fn(),
    revokeMyPresidentAccess: vi.fn(),
  };
});

import {
  getMyPresidentAccess,
  grantMyPresidentAccess,
  revokeMyPresidentAccess,
} from "../../api/medical";

function renderModal() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MedicalConsentModal open onClose={onClose} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onClose };
}

describe("MedicalConsentModal (medical.md §4.11)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("propose « Autoriser » quand l'accès n'est pas accordé", async () => {
    vi.mocked(getMyPresidentAccess).mockResolvedValue({ granted: false, granted_at: null });
    renderModal();

    expect(await screen.findByText("Autorisation non accordée.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Autoriser" })).toBeInTheDocument();
  });

  it("accorde l'accès et affiche un toast de succès", async () => {
    vi.mocked(getMyPresidentAccess).mockResolvedValue({ granted: false, granted_at: null });
    vi.mocked(grantMyPresidentAccess).mockResolvedValue({
      granted: true,
      granted_at: "2026-10-01T00:00:00Z",
    });
    const user = userEvent.setup();
    renderModal();

    await screen.findByRole("button", { name: "Autoriser" });
    await user.click(screen.getByRole("button", { name: "Autoriser" }));

    await waitFor(() => expect(grantMyPresidentAccess).toHaveBeenCalled());
    expect(await screen.findByText("Autorisation accordée au Président.")).toBeInTheDocument();
  });

  it("propose « Révoquer » avec confirmation quand l'accès est accordé", async () => {
    vi.mocked(getMyPresidentAccess).mockResolvedValue({
      granted: true,
      granted_at: "2026-09-01T00:00:00Z",
    });
    vi.mocked(revokeMyPresidentAccess).mockResolvedValue({ granted: false, granted_at: null });
    const user = userEvent.setup();
    renderModal();

    await screen.findByText(/Autorisation accordée depuis le/);
    await user.click(screen.getByRole("button", { name: "Révoquer" }));

    const confirmDialog = await screen.findByRole("dialog", { name: "Révoquer l'autorisation ?" });
    await user.click(within(confirmDialog).getByRole("button", { name: "Révoquer" }));

    await waitFor(() => expect(revokeMyPresidentAccess).toHaveBeenCalled());
    expect(await screen.findByText("Autorisation révoquée.")).toBeInTheDocument();
  });
});
