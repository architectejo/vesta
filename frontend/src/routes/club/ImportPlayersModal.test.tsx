import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ImportBatch } from "../../api/clubs";
import { ImportPlayersModal } from "./ImportPlayersModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return {
    ...actual,
    importPlayers: vi.fn(),
  };
});

import { importPlayers } from "../../api/clubs";

const CSV_FILE = new File(["email,prenom,nom\njean@example.com,Jean,Mbala"], "joueurs.csv", {
  type: "text/csv",
});

function renderModal(onImported = vi.fn()) {
  const onClose = vi.fn();
  render(<ImportPlayersModal onClose={onClose} onImported={onImported} />);
  return { onClose, onImported };
}

// Modal.tsx rend son contenu dans un portail vers document.body : le
// container renvoyé par render() ne le contient pas, il faut chercher
// l'input directement dans le document.
function getFileInput(): HTMLInputElement {
  const input = document.body.querySelector('input[type="file"]');
  if (!input) throw new Error("Aucun <input type=file> trouvé dans la modale.");
  return input as HTMLInputElement;
}

describe("ImportPlayersModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche le compteur et chaque message d'échec tel quel, une seule fois, sans préfixe ajouté", async () => {
    const batch: ImportBatch = {
      id: 1,
      import_type: "players",
      imported_by_id: 7,
      imported_at: "2026-09-27T12:00:00Z",
      row_count_success: 2,
      row_count_failed: 2,
      report_file: null,
      failed_rows: [
        { line_number: 3, message: "Ligne 3 : email invalide." },
        { line_number: 5, message: "Ligne 5 : numéro de maillot déjà utilisé." },
      ],
    };
    vi.mocked(importPlayers).mockResolvedValue(batch);
    const user = userEvent.setup();
    const { onImported } = renderModal();

    await user.upload(getFileInput(), CSV_FILE);
    await user.click(screen.getByRole("button", { name: "Importer" }));

    await waitFor(() => {
      expect(onImported).toHaveBeenCalled();
    });

    expect(screen.getByText("2 joueurs créés ou mis à jour · 2 lignes en échec")).toBeInTheDocument();

    // Le message mocké contient déjà son propre préfixe « Ligne N : » ; le
    // composant ne doit pas en ajouter un second (pas de doublon dans le DOM).
    expect(screen.getAllByText("Ligne 3 : email invalide.")).toHaveLength(1);
    expect(screen.getAllByText("Ligne 5 : numéro de maillot déjà utilisé.")).toHaveLength(1);
    expect(screen.queryByText(/Ligne 3 : Ligne 3/)).not.toBeInTheDocument();
  });

  it("affiche le compteur sans liste d'échecs quand toutes les lignes réussissent", async () => {
    const batch: ImportBatch = {
      id: 2,
      import_type: "players",
      imported_by_id: 7,
      imported_at: "2026-09-27T12:00:00Z",
      row_count_success: 4,
      row_count_failed: 0,
      report_file: null,
      failed_rows: [],
    };
    vi.mocked(importPlayers).mockResolvedValue(batch);
    const user = userEvent.setup();
    renderModal();

    await user.upload(getFileInput(), CSV_FILE);
    await user.click(screen.getByRole("button", { name: "Importer" }));

    expect(
      await screen.findByText("4 joueurs créés ou mis à jour · 0 lignes en échec"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("appelle importPlayers avec le fichier choisi", async () => {
    vi.mocked(importPlayers).mockResolvedValue({
      id: 3,
      import_type: "players",
      imported_by_id: 7,
      imported_at: "2026-09-27T12:00:00Z",
      row_count_success: 1,
      row_count_failed: 0,
      report_file: null,
      failed_rows: [],
    });
    const user = userEvent.setup();
    renderModal();

    await user.upload(getFileInput(), CSV_FILE);
    await user.click(screen.getByRole("button", { name: "Importer" }));

    await waitFor(() => {
      expect(importPlayers).toHaveBeenCalledWith(CSV_FILE);
    });
  });

  it("le bouton Importer reste désactivé sans fichier choisi", () => {
    renderModal();
    expect(screen.getByRole("button", { name: "Importer" })).toBeDisabled();
    expect(importPlayers).not.toHaveBeenCalled();
  });
});
