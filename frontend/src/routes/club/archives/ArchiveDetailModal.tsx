import { toViewableBlob, UNOPENABLE_FILE_MESSAGE } from "../../../api/safeBlob";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  downloadArchivedDocument,
  getArchivedDocument,
  type ArchivedDocument,
} from "../../../api/assemblies";
import { ApiError, triggerBlobDownload } from "../../../api/client";
import {
  Avatar,
  AuthenticatedImage,
  Banner,
  Button,
  EmptyState,
  IconDocumentPdf,
  IconDownload,
  IconOpenExternal,
  IconWithdraw,
  Modal,
  StatusBadge,
  useToast,
} from "../../../design-system";
import { ArchiveWithdrawModal } from "./ArchiveWithdrawModal";
import {
  CATEGORY_LABELS,
  fileFormatLabel,
  formatDateTime,
  formatDocumentDate,
  isImageFileName,
} from "./archivesFormat";

function Definition({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
      <dt className="shrink-0 text-[13px] text-text-muted sm:w-40">{term}</dt>
      <dd className="min-w-0 break-words text-sm text-text">{children}</dd>
    </div>
  );
}

/**
 * Modale « Document » (club-archives.md §4.2). Aperçu par vue authentifiée,
 * jamais d'adresse publique (CDC 6.7). Les actions « Remplacer » et « Retirer »
 * ne sont proposées que si `canWrite` ; l'API refuse de toute façon.
 */
export function ArchiveDetailModal({
  summary,
  canWrite,
  readOnlyLicence = false,
  onClose,
  onReplace,
  onChanged,
}: {
  /** Ligne de liste déjà connue : affichée dès l'ouverture (titre immédiat). */
  summary: ArchivedDocument;
  canWrite: boolean;
  readOnlyLicence?: boolean;
  onClose: () => void;
  onReplace: (document: ArchivedDocument) => void;
  onChanged: () => void;
}) {
  const { showToast } = useToast();
  const [downloading, setDownloading] = useState(false);
  const [opening, setOpening] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  const [withdrawOpen, setWithdrawOpen] = useState(false);

  const query = useQuery({
    queryKey: ["assemblies", "archive", summary.id],
    queryFn: () => getArchivedDocument(summary.id),
    placeholderData: summary,
    retry: false,
  });
  const document_ = query.data ?? summary;
  const online = typeof navigator === "undefined" ? true : navigator.onLine;
  const notFound = query.error instanceof ApiError && query.error.status === 404;
  const isImage = isImageFileName(document_.file_name);
  const withdrawn = document_.status === "withdrawn";
  const canAct = canWrite && !readOnlyLicence && !withdrawn;

  async function handleDownload(): Promise<void> {
    setDownloading(true);
    try {
      const { blob, filename } = await downloadArchivedDocument(summary.id);
      triggerBlobDownload(blob, filename);
    } catch {
      showToast("Le téléchargement a échoué. Vérifiez votre réseau et réessayez.");
    } finally {
      setDownloading(false);
    }
  }

  async function handleOpen(): Promise<void> {
    setOpening(true);
    try {
      const { blob } = await downloadArchivedDocument(summary.id);
      const safe = toViewableBlob(blob);
      if (!safe) {
        showToast(UNOPENABLE_FILE_MESSAGE);
        return;
      }
      const url = URL.createObjectURL(safe);
      window.open(url, "_blank", "noopener,noreferrer");
      // L'URL d'objet est révoquée après un délai : la visionneuse l'a déjà lue.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      showToast("Le fichier n'a pas pu être chargé.");
    } finally {
      setOpening(false);
    }
  }

  const footer = (
    <>
      <Button variant="secondary" size="md" className="flex-1 sm:flex-none" onClick={onClose}>
        Fermer
      </Button>
      {!notFound ? (
        <Button
          variant="primary"
          size="md"
          className="flex-1 sm:flex-none"
          loading={downloading}
          loadingLabel="Téléchargement…"
          disabled={!online}
          icon={<IconDownload aria-hidden="true" className="h-4 w-4" />}
          onClick={() => void handleDownload()}
        >
          Télécharger
        </Button>
      ) : null}
    </>
  );

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title={document_.title}
        subtitle={`${CATEGORY_LABELS[document_.category]} · ${formatDocumentDate(document_.document_date, "long")}`}
        size="lg"
        footer={footer}
      >
        {notFound ? (
          <EmptyState variant="error" message="Cet élément n'existe plus." />
        ) : (
          <div className="space-y-4">
            {query.isError ? (
              <Banner
                variant="danger"
                action={
                  <Button variant="secondary" size="sm" onClick={() => void query.refetch()}>
                    Réessayer
                  </Button>
                }
              >
                Impossible de charger les détails du document.
              </Banner>
            ) : null}
            {!online ? <Banner variant="info">Vous êtes hors connexion : le téléchargement est indisponible.</Banner> : null}
            {withdrawn ? (
              <div className="flex items-center gap-2">
                <StatusBadge status="withdrawn" />
              </div>
            ) : null}

            {isImage ? (
              <AuthenticatedImage
                key={previewKey}
                cacheKey={`${summary.id}-${previewKey}`}
                download={() => downloadArchivedDocument(summary.id)}
                alt={document_.title}
                className="mx-auto max-h-[60vh] w-full rounded-md object-contain"
              />
            ) : (
              <div className="flex min-h-[72px] items-center gap-3 rounded-md bg-surface-muted p-3">
                <IconDocumentPdf aria-hidden="true" className="h-6 w-6 shrink-0 text-text-muted" />
                <div className="min-w-0 flex-1">
                  <p className="break-words text-sm text-text">{document_.file_name || "Document PDF"}</p>
                  <p className="text-[13px] text-text-muted">{fileFormatLabel(document_)}</p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  loading={opening}
                  loadingLabel="Ouverture…"
                  disabled={!online}
                  icon={<IconOpenExternal aria-hidden="true" className="h-4 w-4" />}
                  onClick={() => void handleOpen()}
                >
                  Ouvrir
                </Button>
              </div>
            )}
            {isImage ? (
              <button
                type="button"
                className="inline-flex min-h-control-sm items-center text-[13px] text-primary-text hover:underline"
                onClick={() => setPreviewKey((k) => k + 1)}
              >
                Recharger l'aperçu
              </button>
            ) : null}

            <dl className="space-y-2">
              <Definition term="Catégorie">{CATEGORY_LABELS[document_.category]}</Definition>
              <Definition term="Date du document">{formatDocumentDate(document_.document_date, "long")}</Definition>
              <Definition term="Déposé par">
                <span className="inline-flex items-center gap-2">
                  <Avatar name={document_.uploaded_by_name} size={24} />
                  {document_.uploaded_by_name}
                </span>
              </Definition>
              <Definition term="Déposé le">{formatDateTime(document_.uploaded_at)}</Definition>
              <Definition term="Fichier">{fileFormatLabel(document_)}</Definition>
            </dl>

            {withdrawn ? (
              <Banner variant="info">
                Retiré le {document_.withdrawn_at ? formatDateTime(document_.withdrawn_at) : "—"} par{" "}
                {document_.withdrawn_by_name || "—"} — Motif : {document_.withdrawn_reason}
              </Banner>
            ) : null}

            {canAct ? (
              <div className="flex flex-wrap gap-2 border-t border-border pt-3">
                <Button variant="secondary" size="sm" disabled={!online} onClick={() => onReplace(document_)}>
                  Remplacer le fichier
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!online}
                  icon={<IconWithdraw aria-hidden="true" className="h-4 w-4" />}
                  onClick={() => setWithdrawOpen(true)}
                >
                  Retirer le document
                </Button>
                {!online ? <p className="w-full text-xs text-text-muted">Cette action nécessite une connexion.</p> : null}
              </div>
            ) : null}
          </div>
        )}
      </Modal>
      {withdrawOpen ? (
        <ArchiveWithdrawModal
          document={document_}
          onClose={() => setWithdrawOpen(false)}
          onWithdrawn={() => {
            setWithdrawOpen(false);
            onChanged();
            onClose();
          }}
        />
      ) : null}
    </>
  );
}
