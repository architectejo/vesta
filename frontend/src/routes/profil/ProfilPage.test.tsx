import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";

vi.mock("../../auth/AuthContext", () => ({ useAuth: () => ({ logout: vi.fn() }) }));
vi.mock("../../api/auth", () => ({ downloadPersonalData: vi.fn(), logoutAllDevices: vi.fn() }));
vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return { ...actual, triggerBlobDownload: vi.fn() };
});
vi.mock("../../api/clubs", () => ({ getMyProfile: vi.fn() }));
vi.mock("../../api/medical", () => ({ getMyPresidentAccess: vi.fn() }));
vi.mock("../../api/notifications", () => ({
  getNotificationPreference: vi.fn(),
  setNotificationPreference: vi.fn(),
}));
vi.mock("./FinancialSituationCard", () => ({ FinancialSituationCard: () => null }));
vi.mock("./AssistanceCard", () => ({ AssistanceCard: () => null }));
vi.mock("../club/PlayerCardModal", () => ({ PlayerCardModal: () => null }));
vi.mock("../medical/MedicalConsentModal", () => ({ MedicalConsentModal: () => null }));
vi.mock("../medical/MyHealthRecordModal", () => ({ MyHealthRecordModal: () => null }));
vi.mock("./EditProfileModal", () => ({ EditProfileModal: () => null }));

import { downloadPersonalData } from "../../api/auth";
import { triggerBlobDownload } from "../../api/client";
import { getMyProfile } from "../../api/clubs";
import { getMyPresidentAccess } from "../../api/medical";
import { getNotificationPreference } from "../../api/notifications";
import { ProfilPage } from "./ProfilPage";

function renderPage() {
  vi.mocked(getMyProfile).mockResolvedValue({
    membership_id: 1,
    club: { id: 1, slug: "c", name: "Club Test", logo: null, primary_color: "", secondary_color: "" },
    identity: {
      first_name: "Jean",
      last_name: "Dupont",
      photo: null,
      email: "j@example.com",
      phone: "",
      birth_date: null,
      weight_kg: null,
      height_cm: null,
    },
    position: "",
    position_label: "",
    position_detail: "",
    jersey_number: null,
    membership_status: "active",
    membership_status_label: "Inscrit",
    roles: [],
    email_notifications_enabled: false,
  });
  vi.mocked(getMyPresidentAccess).mockResolvedValue({ granted: false } as never);
  vi.mocked(getNotificationPreference).mockResolvedValue({ email_enabled: false, updated_at: "" });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>
          <ProfilPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ProfilPage — export des données", () => {
  it("télécharge les données personnelles via le client authentifié", async () => {
    const blob = new Blob(["{}"], { type: "application/json" });
    vi.mocked(downloadPersonalData).mockResolvedValue({ blob, filename: "mes-donnees-vesta.json" });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Ouvrir le menu" }));
    await user.click(screen.getByRole("button", { name: "Télécharger mes données" }));
    await waitFor(() => expect(triggerBlobDownload).toHaveBeenCalledWith(blob, "mes-donnees-vesta.json"));
  });

  it("affiche un message d'erreur en français si l'export échoue", async () => {
    vi.mocked(downloadPersonalData).mockRejectedValue(new Error("réseau"));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Ouvrir le menu" }));
    await user.click(screen.getByRole("button", { name: "Télécharger mes données" }));
    expect(await screen.findByText(/Impossible de télécharger vos données/)).toBeInTheDocument();
    expect(triggerBlobDownload).not.toHaveBeenCalled();
  });

  it("laisse « Demander la suppression » désactivée", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Ouvrir le menu" }));
    expect(screen.getByRole("button", { name: /Demander la suppression/ })).toBeDisabled();
  });
});
