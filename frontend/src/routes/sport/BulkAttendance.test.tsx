import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BulkConfirmModal } from "./BulkAttendance";

function renderModal(props: Partial<Parameters<typeof BulkConfirmModal>[0]> = {}) {
  return render(
    <BulkConfirmModal
      open
      players={[{ id: 1, name: "Paul Ilunga" }, { id: 2, name: "Anne Kasa" }]}
      canSetTime={false}
      eventDate="2026-09-27"
      submitting={false}
      onCancel={vi.fn()}
      onConfirm={vi.fn()}
      {...props}
    />,
  );
}

describe("BulkConfirmModal", () => {
  it("prévient quand des joueurs cochés ne pourront pas être placés", () => {
    renderModal({ blockedCount: 1 });
    expect(screen.getByText("1 de ces joueurs ne pourront pas être placés dans une équipe.")).toBeInTheDocument();
  });

  it("n'affiche rien quand l'information est absente ou nulle", () => {
    renderModal();
    expect(screen.queryByText(/ne pourront pas être placés/)).not.toBeInTheDocument();
  });

  it("affiche le bandeau de retard avec l'heure limite (coup d'envoi d'un match)", () => {
    renderModal({ lateCutoff: "00:00:00" });
    expect(screen.getByText(/Il est plus de 00:00 : ces joueurs seront enregistrés en retard/)).toBeInTheDocument();
  });
});
