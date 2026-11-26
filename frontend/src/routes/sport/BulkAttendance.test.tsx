import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BulkActionBar, BulkConfirmModal, BulkHeaderBar } from "./BulkAttendance";

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

describe("BulkActionBar", () => {
  it("compense exactement la marge de la page (12 px sous 640 px) : aucun défilement horizontal à 360 px", () => {
    // Vérification visuelle B3 : avec `-mx-4` (16 px) dans un `main` en `px-3`
    // (12 px), la barre dépassait de 4 px et la page défilait horizontalement
    // (364 px pour 360). jsdom ne calcule pas la mise en page : on fige les
    // marges alignées sur celles de `AppLayout` (`px-3 sm:px-4`).
    render(<BulkActionBar count={2} canExcuse submitting={false} onArrive={vi.fn()} onExcuse={vi.fn()} />);
    const classes = screen.getByRole("region", { name: "Actions sur la sélection" }).className.split(" ");
    expect(classes).toEqual(expect.arrayContaining(["-mx-3", "px-3", "sm:-mx-4", "sm:px-4"]));
    expect(classes).not.toContain("-mx-4");
  });
});

describe("BulkHeaderBar", () => {
  it("à 360 px, un seul bouton « Tout cocher » ; libellés jamais coupés sur plusieurs lignes (spec §3.2 point 1)", () => {
    // Vérification visuelle B3 : en sélection partielle, trois boutons texte
    // (« Tout cocher (15) », « Tout décocher », « Terminer ») passaient sur 2
    // à 3 lignes et sortaient de la barre de 44 px. Le second « Tout décocher »
    // est réservé aux écrans de 640 px et plus ; jsdom n'applique pas le CSS,
    // on fige donc les classes.
    render(
      <BulkHeaderBar checkableIds={[1, 2, 3]} selected={[1]} onCheckAll={vi.fn()} onUncheckAll={vi.fn()} onStop={vi.fn()} />,
    );
    const checkAll = screen.getByRole("button", { name: "Tout cocher (3)" });
    const extraUncheck = screen.getByRole("button", { name: "Tout décocher" });
    const stop = screen.getByRole("button", { name: "Terminer" });
    expect(extraUncheck.className.split(" ")).toContain("max-sm:hidden");
    for (const button of [checkAll, extraUncheck, stop]) {
      expect(button.className.split(" ")).toContain("whitespace-nowrap");
    }
    expect(checkAll.className.split(" ")).not.toContain("max-sm:hidden");
  });
});
