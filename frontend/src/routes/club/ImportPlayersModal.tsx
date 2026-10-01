import { useState } from "react";
import { importPlayers } from "../../api/clubs";
import type { ImportBatch } from "../../api/clubs";
import { ApiError } from "../../api/client";
import { Banner, Button, Modal } from "../../design-system";

// Mêmes exemples que docs/annexes/formats-csv.md et
// docs/annexes/modele-import-joueurs.csv (CDC 10.1, Annexe C) : une seule
// source de vérité pour ce modèle, ne pas faire diverger l'un sans l'autre.
const CSV_TEMPLATE =
  "email,prenom,nom,telephone,poste,numero,date_naissance,poids,taille,type_cotisation\n" +
  "jean.mbala@example.com,Jean,Mbala,+243811111111,Gardien,1,14/03/1990,78.5,182,Mensuelle 20$\n" +
  "alice.tshimanga@example.com,Alice,Tshimanga,,,,,,,\n" +
  "patrick.kalala@example.com,Patrick,Kalala,,midfielder,8,1988-07-22,74,178,Mensuelle 10$\n" +
  'sarah.ilunga@example.com,Sarah,Ilunga,0899999999,Attaquant,9,05/11/1995,"62,3",167,Mensuelle 5$\n';

function downloadCsvTemplate(): void {
  const blob = new Blob([CSV_TEMPLATE], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "modele-import-joueurs.csv";
  link.click();
  URL.revokeObjectURL(url);
}

/** Assistant « Importer des joueurs » (club-comite-bureau.md §4.6), 2 étapes. */
export function ImportPlayersModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ImportBatch | null>(null);

  async function handleImport(): Promise<void> {
    if (!file) {
      setError("Choisissez un fichier CSV.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const batch = await importPlayers(file);
      setResult(batch);
      onImported();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    return (
      <Modal open onClose={onClose} title="Importer des joueurs" size="xl" footer={<Button onClick={onClose}>Fermer</Button>}>
        <div className="space-y-3">
          <p className="text-sm text-text">
            {result.row_count_success} joueurs créés ou mis à jour · {result.row_count_failed} lignes en
            échec
          </p>
          {result.failed_rows.length > 0 ? (
            <ul className="space-y-1 text-sm text-status-danger-fg">
              {result.failed_rows.map((row) => (
                <li key={row.line_number}>{row.message}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Importer des joueurs"
      size="xl"
      isSubmitting={submitting}
      confirmLabel="Importer"
      confirmLoadingLabel="Import…"
      confirmDisabled={!file}
      onConfirm={() => void handleImport()}
    >
      <div className="space-y-4">
        {error ? <Banner variant="danger">{error}</Banner> : null}
        <button
          type="button"
          onClick={downloadCsvTemplate}
          className="text-sm font-medium text-primary-text hover:underline"
        >
          Télécharger le modèle CSV
        </button>
        <p className="text-xs text-text-muted">
          Colonnes : email, prenom, nom, telephone, poste, numero, date_naissance, poids, taille,
          type_cotisation. Seuls email, prénom et nom sont obligatoires. Dates au format
          JJ/MM/AAAA ou AAAA-MM-JJ. Un email déjà présent met la fiche à jour. Les joueurs importés
          sont inscrits directement, sans parrainage.
        </p>
        <input
          type="file"
          accept=".csv"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-sm"
        />
      </div>
    </Modal>
  );
}
