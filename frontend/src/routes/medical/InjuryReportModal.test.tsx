import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../design-system";
import { InjuryReportModal } from "./InjuryReportModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, searchActiveClubPlayers: vi.fn() };
});

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, listSessions: vi.fn(), listMatches: vi.fn() };
});

vi.mock("../../api/medical", async () => {
  const actual = await vi.importActual<typeof import("../../api/medical")>("../../api/medical");
  return { ...actual, reportInjury: vi.fn() };
});

import { searchActiveClubPlayers } from "../../api/clubs";
import { reportInjury } from "../../api/medical";
import { listMatches, listSessions } from "../../api/sport";

function renderModal(props: Partial<Parameters<typeof InjuryReportModal>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  const onReported = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <InjuryReportModal open onClose={onClose} onReported={onReported} {...props} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onClose, onReported };
}

async function choosePlayer(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole("combobox", { name: "Nom ou numéro du joueur" }), "Jean");
  const option = await screen.findByRole("option", { name: /Jean Kabila/ });
  await user.click(option);
}

describe("InjuryReportModal (medical.md §4.1)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("exige un joueur, un évènement et des circonstances avant l'envoi (mode page)", async () => {
    vi.mocked(listSessions).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(listMatches).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    const user = userEvent.setup();
    renderModal();

    await user.click(screen.getByRole("button", { name: "Déclarer" }));

    expect(await screen.findByText("Choisissez un joueur.")).toBeInTheDocument();
    expect(screen.getByText("Indiquez quand la blessure est survenue.")).toBeInTheDocument();
    expect(screen.getByText("Décrivez brièvement les circonstances.")).toBeInTheDocument();
    expect(reportInjury).not.toHaveBeenCalled();
  });

  it("déclare une blessure « Hors séance ou match » depuis la page Médical", async () => {
    vi.mocked(listSessions).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(listMatches).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 7, firstName: "Jean", lastName: "Kabila", number: 10, position: "Milieu" },
    ]);
    vi.mocked(reportInjury).mockResolvedValue({
      id: 1,
      membership_id: 7,
      status: "open",
      reported_by: "Coach Test",
      reported_at: "2026-10-01T10:00:00Z",
      event_id: null,
      occurred_time: "10:00:00",
      occurred_minute: null,
      circumstances: "Entorse à la cheville",
      location_on_body: "",
      severity: "",
      on_site_care: "",
      referral: "",
      estimated_days_out: null,
      doctor_completed_by: null,
      doctor_completed_at: null,
      resolved_by: null,
      resolved_at: null,
      followups: [],
    });

    const user = userEvent.setup();
    const { onReported, onClose } = renderModal();

    await choosePlayer(user);
    await user.selectOptions(screen.getByLabelText("Séance ou match"), "Hors séance ou match");
    await user.type(screen.getByLabelText("Circonstances"), "Entorse à la cheville");
    await user.click(screen.getByRole("button", { name: "Déclarer" }));

    await waitFor(() => expect(reportInjury).toHaveBeenCalledWith(
      expect.objectContaining({ membership_id: 7, event_id: null, circumstances: "Entorse à la cheville" }),
    ));
    await waitFor(() => expect(onReported).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
  });

  it("enfile la déclaration hors connexion depuis une séance (contexte fixe)", async () => {
    vi.mocked(searchActiveClubPlayers).mockResolvedValue([
      { id: 7, firstName: "Jean", lastName: "Kabila", number: 10, position: "Milieu" },
    ]);
    const enqueue = vi.fn();
    const user = userEvent.setup();
    const { onReported } = renderModal({
      context: { eventId: 5, eventKind: "session", eventLabel: "Séance du 1 oct. 2026" },
      offline: { isOnline: false, enqueue },
    });

    await choosePlayer(user);
    await user.type(screen.getByLabelText("Circonstances"), "Choc au genou");
    await user.click(screen.getByRole("button", { name: "Déclarer" }));

    await waitFor(() =>
      expect(enqueue).toHaveBeenCalledWith(
        expect.objectContaining({ membership_id: 7, event_id: 5, circumstances: "Choc au genou" }),
      ),
    );
    expect(reportInjury).not.toHaveBeenCalled();
    await waitFor(() => expect(onReported).toHaveBeenCalled());
  });
});
