import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  downloadApplicationPdf,
  getClubIdentity,
  refuseSponsorApplication,
  signSponsorApplication,
  type MembershipApplication,
} from "../../../api/clubs";
import { triggerBlobDownload } from "../../../api/client";
import { Avatar, Banner, Button, ConfirmDialog, Modal, TextArea, useToast } from "../../../design-system";
import { apiMessage, feeSummary, personName } from "./applicationText";

/**
 * Modale « Fiche d'adhésion de {nom} » : signature (après confirmation explicite) ou refus motivé
 * du parrain désigné (club-accueil.md §5.4 ; CDC 4.3 étape 4). Qui peut
 * signer est décidé par l'API : l'interface affiche ses messages.
 */
export function SponsorSignatureModal({
  application,
  level = 1,
  onClose,
  onDone,
}: {
  application: MembershipApplication;
  level?: 1 | 2;
  onClose: () => void;
  onDone: () => void;
}) {
  const { showToast } = useToast();
  const identityQuery = useQuery({ queryKey: ["club-identity"], queryFn: getClubIdentity });
  const currency = identityQuery.data?.currency ?? "";
  const firstName = application.player?.first_name ?? "le joueur";

  const [signOpen, setSignOpen] = useState(false);
  const [signing, setSigning] = useState(false);
  const [refuseOpen, setRefuseOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | undefined>();
  const [refusing, setRefusing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stillPending = application.sponsor_decision === "pending" && application.resolved_at === null;

  async function handleSign(): Promise<void> {
    if (signing) return;
    setSigning(true);
    try {
      await signSponsorApplication({ application_id: application.id });
      setSignOpen(false);
      showToast(`Fiche signée. ${firstName} est maintenant inscrit.`);
      onDone();
    } catch (err) {
      setSignOpen(false);
      setError(apiMessage(err));
    } finally {
      setSigning(false);
    }
  }

  async function handleRefuse(): Promise<void> {
    if (!reason.trim()) {
      setReasonError("Indiquez le motif.");
      return;
    }
    setReasonError(undefined);
    setRefusing(true);
    try {
      await refuseSponsorApplication({ application_id: application.id, reason: reason.trim() });
      setRefuseOpen(false);
      showToast("Refus enregistré. Le Président a été prévenu.");
      onDone();
    } catch (err) {
      setRefuseOpen(false);
      setError(apiMessage(err));
    } finally {
      setRefusing(false);
    }
  }

  async function handleDownload(): Promise<void> {
    setDownloading(true);
    try {
      const { blob, filename } = await downloadApplicationPdf(application.id);
      triggerBlobDownload(blob, filename);
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setDownloading(false);
    }
  }

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title={`Fiche d'adhésion de ${personName(application.player)}`}
        size="lg"
        level={level}
        footer={
          stillPending ? (
            <div className="flex w-full items-center justify-between gap-2">
              <Button variant="secondary" size="md" onClick={() => setRefuseOpen(true)}>
                Refuser
              </Button>
              <Button
                variant="primary"
                size="md"
                disabled={application.generated_at === null}
                onClick={() => setSignOpen(true)}
              >
                Signer la fiche
              </Button>
            </div>
          ) : (
            <Button variant="secondary" size="md" onClick={onClose}>
              Fermer
            </Button>
          )
        }
      >
        <div className="space-y-4">
          {error ? <Banner variant="danger">{error}</Banner> : null}
          {!stillPending ? (
            <Banner variant="info">Cette fiche a déjà été signée ou n'est plus en attente.</Banner>
          ) : null}
          <div className="flex items-center gap-3">
            <Avatar name={personName(application.player)} photoUrl={application.player?.photo} size={40} />
            <div>
              <p className="text-sm font-medium text-text">{personName(application.player)}</p>
              <p className="text-xs text-text-muted">
                {application.player?.position_label || "Poste non précisé"}
              </p>
            </div>
          </div>
          <p className="text-sm text-text">Frais d'adhésion : {feeSummary(application, currency)}</p>
          {application.application_pdf_url ? (
            <Button variant="secondary" size="md" loading={downloading} onClick={() => void handleDownload()}>
              Voir la fiche d'adhésion (PDF)
            </Button>
          ) : (
            <p className="text-sm text-text-muted">
              La fiche sera disponible une fois les frais d'adhésion payés.
            </p>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={signOpen}
        danger={false}
        title={`Signer la fiche d'adhésion de ${personName(application.player)} ?`}
        description={`Vous vous portez garant de ${firstName}. Une fois la fiche signée, il sera inscrit au club.`}
        confirmLabel="Signer la fiche"
        loadingLabel="Signature…"
        loading={signing}
        onConfirm={() => void handleSign()}
        onCancel={() => setSignOpen(false)}
      />

      <Modal
        open={refuseOpen}
        onClose={() => setRefuseOpen(false)}
        title="Refuser le parrainage"
        size="md"
        level={2}
        isDirty={reason !== ""}
        isSubmitting={refusing}
        confirmLabel="Refuser le parrainage"
        confirmLoadingLabel="Envoi…"
        onConfirm={() => void handleRefuse()}
      >
        <TextArea label="Motif du refus" value={reason} onChange={setReason} error={reasonError} />
      </Modal>
    </>
  );
}
