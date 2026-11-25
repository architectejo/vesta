import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AppNotification } from "../api/notifications";
import { NotificationBellWidget } from "./NotificationBellWidget";

vi.mock("../api/notifications", () => ({
  getUnreadCount: vi.fn(),
  getNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));

import {
  getNotifications,
  getUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
} from "../api/notifications";

function makeNotification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: 1,
    event_type: "role_appointed_or_revoked",
    title: "Nouveau rôle",
    body: "Vous avez désormais le rôle « Trésorier » au sein de votre club.",
    link_object_type: "",
    link_object_id: null,
    is_read: false,
    read_at: null,
    created_at: "2026-10-01T10:00:00Z",
    ...overrides,
  };
}

function list(results: AppNotification[], next: string | null = null) {
  return { count: results.length, next, previous: null, results };
}

function renderWidget() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<NotificationBellWidget />} />
          <Route path="/matchs/:id" element={<p>Page du match</p>} />
          <Route path="/club/comite" element={<p>Page du comité</p>} />
          <Route path="/profil" element={<p>Page du profil</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NotificationBellWidget", () => {
  beforeEach(() => {
    vi.mocked(getUnreadCount).mockResolvedValue({ unread_count: 0 });
    vi.mocked(getNotifications).mockResolvedValue(list([]));
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche le compteur de non-lues", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ unread_count: 3 });
    renderWidget();
    expect(await screen.findByTestId("notification-badge")).toHaveTextContent("3");
  });

  it("affiche « 9+ » au-delà de 9", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ unread_count: 14 });
    renderWidget();
    expect(await screen.findByTestId("notification-badge")).toHaveTextContent("9+");
  });

  it("masque le compteur quand tout est lu", async () => {
    renderWidget();
    await waitFor(() => expect(getUnreadCount).toHaveBeenCalled());
    expect(screen.queryByTestId("notification-badge")).not.toBeInTheDocument();
  });

  it("ouvre la modale et liste les notifications, non lues distinguées", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ unread_count: 1 });
    vi.mocked(getNotifications).mockResolvedValue(
      list([makeNotification(), makeNotification({ id: 2, title: "Fin de rôle", is_read: true })]),
    );
    const user = userEvent.setup();
    renderWidget();

    await user.click(screen.getByRole("button", { name: /^Notifications/ }));
    expect(await screen.findByRole("heading", { name: "Notifications" })).toBeInTheDocument();
    expect(await screen.findByText("Nouveau rôle")).toBeInTheDocument();
    expect(screen.getByText("Fin de rôle")).toBeInTheDocument();
    expect(screen.getAllByText("Non lu")).toHaveLength(1);
  });

  it("affiche l'état vide « Aucune notification. »", async () => {
    const user = userEvent.setup();
    renderWidget();
    await user.click(screen.getByRole("button", { name: /^Notifications/ }));
    expect(await screen.findByText("Aucune notification.")).toBeInTheDocument();
  });

  it("propose « Voir plus » quand l'API indique une suite", async () => {
    vi.mocked(getNotifications).mockImplementation(async (page: number) =>
      page === 1
        ? list([makeNotification()], "http://x/?page=2")
        : list([makeNotification({ id: 2, title: "Page deux" })]),
    );
    const user = userEvent.setup();
    renderWidget();
    await user.click(screen.getByRole("button", { name: /^Notifications/ }));
    await user.click(await screen.findByRole("button", { name: "Voir plus" }));
    await waitFor(() => expect(getNotifications).toHaveBeenCalledWith(2));
    expect(await screen.findByText("Page deux")).toBeInTheDocument();
    // Dernière page atteinte : plus de « Voir plus », sans plafond de 50.
    expect(screen.queryByRole("button", { name: "Voir plus" })).not.toBeInTheDocument();
  });

  it("un clic marque la notification comme lue et ferme la modale", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ unread_count: 1 });
    vi.mocked(getNotifications).mockResolvedValue(list([makeNotification()]));
    vi.mocked(markNotificationRead).mockResolvedValue(makeNotification({ is_read: true }));
    const user = userEvent.setup();
    renderWidget();

    await user.click(screen.getByRole("button", { name: /^Notifications/ }));
    await user.click(await screen.findByText("Nouveau rôle"));

    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledWith(1));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Notifications" })).not.toBeInTheDocument());
  });

  it("un clic sur une notification liée à un match mène à la page du match", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ unread_count: 1 });
    vi.mocked(getNotifications).mockResolvedValue(
      list([makeNotification({ title: "Composition publiée", link_object_type: "Match", link_object_id: 7 })]),
    );
    vi.mocked(markNotificationRead).mockResolvedValue(makeNotification({ is_read: true }));
    const user = userEvent.setup();
    renderWidget();

    await user.click(screen.getByRole("button", { name: /^Notifications/ }));
    await user.click(await screen.findByText("Composition publiée"));
    expect(await screen.findByText("Page du match")).toBeInTheDocument();
  });

  it("un clic sur une adhésion à signer mène au comité", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ unread_count: 1 });
    vi.mocked(getNotifications).mockResolvedValue(
      list([
        makeNotification({
          event_type: "membership_signature_pending",
          title: "Fiche d'adhésion à signer",
          link_object_type: "MembershipApplication",
          link_object_id: 12,
        }),
      ]),
    );
    vi.mocked(markNotificationRead).mockResolvedValue(makeNotification({ is_read: true }));
    const user = userEvent.setup();
    renderWidget();

    await user.click(screen.getByRole("button", { name: /^Notifications/ }));
    await user.click(await screen.findByText("Fiche d'adhésion à signer"));
    expect(await screen.findByText("Page du comité")).toBeInTheDocument();
  });

  it("un paiement validé mène au profil du joueur", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ unread_count: 1 });
    vi.mocked(getNotifications).mockResolvedValue(
      list([
        makeNotification({
          event_type: "payment_validated",
          title: "Paiement validé",
          link_object_type: "Payment",
          link_object_id: 4,
        }),
      ]),
    );
    vi.mocked(markNotificationRead).mockResolvedValue(makeNotification({ is_read: true }));
    const user = userEvent.setup();
    renderWidget();

    await user.click(screen.getByRole("button", { name: /^Notifications/ }));
    await user.click(await screen.findByText("Paiement validé"));
    expect(await screen.findByText("Page du profil")).toBeInTheDocument();
  });

  it("un type sans écran reste sur place et marque la notification comme lue", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ unread_count: 1 });
    vi.mocked(getNotifications).mockResolvedValue(
      list([makeNotification({ title: "Licence", link_object_type: "Licence", link_object_id: 1 })]),
    );
    vi.mocked(markNotificationRead).mockResolvedValue(makeNotification({ is_read: true }));
    const user = userEvent.setup();
    renderWidget();

    await user.click(screen.getByRole("button", { name: /^Notifications/ }));
    await user.click(await screen.findByText("Licence"));
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledWith(1));
    expect(screen.queryByText("Page du comité")).not.toBeInTheDocument();
  });

  it("« Tout marquer comme lu » appelle l'API", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ unread_count: 2 });
    vi.mocked(getNotifications).mockResolvedValue(list([makeNotification(), makeNotification({ id: 2 })]));
    vi.mocked(markAllNotificationsRead).mockResolvedValue({ updated: 2 });
    const user = userEvent.setup();
    renderWidget();

    await user.click(screen.getByRole("button", { name: /^Notifications/ }));
    await user.click(await screen.findByRole("button", { name: "Tout marquer comme lu" }));
    await waitFor(() => expect(markAllNotificationsRead).toHaveBeenCalledTimes(1));
  });
});
