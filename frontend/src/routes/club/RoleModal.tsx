import { useState } from "react";
import {
  appointCaptain,
  appointRole,
  revokeCaptain,
  revokeRole,
  searchActiveClubPlayers,
} from "../../api/clubs";
import type { MembershipRole } from "../../api/clubs";
import { ApiError } from "../../api/client";
import { Banner, Button, ConfirmDialog, Modal, PlayerSearch, useToast } from "../../design-system";
import type { PlayerSearchResult } from "../../design-system";

/**
 * Modale « Rôle : {rôle} » (club-comite-bureau.md §4.2). Nomination sur poste
 * vacant, remplacement d'un titulaire et révocation, toutes bornées aux
 * joueurs inscrits du club (`GET /clubs/players/?status=active`).
 */
export function RoleModal({
  roleKey,
  roleLabel,
  role,
  holderName,
  canManage,
  onClose,
  onChanged,
}: {
  /** Clé brute du rôle (`MembershipRole.Role`) : détermine l'endpoint appelé. */
  roleKey: string;
  roleLabel: string;
  role: MembershipRole | null;
  holderName: string | null;
  canManage: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { showToast } = useToast();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [selectedPlayer, setSelectedPlayer] = useState<PlayerSearchResult | null>(null);
  const [isQualifiedProfessional, setIsQualifiedProfessional] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const showSearch = canManage && (!role || replacing);
  // Le role Medecin exige un choix explicite qualifie/non-qualifie a la
  // nomination : jamais devine (backend `MembershipRole.clean()`, CDC 10.2 n17).
  const isDoctorRole = roleKey === "doctor";

  async function handleRevoke(): Promise<void> {
    if (!role) return;
    setSubmitting(true);
    setError(null);
    try {
      if (roleKey === "captain") {
        await revokeCaptain({ role_id: role.id });
      } else {
        await revokeRole({ role_id: role.id });
      }
      showToast(`${holderName ?? "Le titulaire"} n'est plus ${roleLabel.toLowerCase()}.`);
      setConfirmOpen(false);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAppoint(): Promise<void> {
    if (!selectedPlayer) return;
    if (isDoctorRole && isQualifiedProfessional === null) return;
    setSubmitting(true);
    setError(null);
    try {
      if (replacing && role) {
        // Le poste n'accueille par defaut qu'un seul titulaire actif a la
        // fois (`ClubSettings.board_seats_per_role`, CDC 10.2 n24) : il faut
        // revoquer l'ancien avant de nommer le nouveau, sinon le backend
        // refuse la nomination pour poste deja occupe.
        if (roleKey === "captain") {
          await revokeCaptain({ role_id: role.id });
        } else {
          await revokeRole({ role_id: role.id });
        }
      }
      if (roleKey === "captain") {
        await appointCaptain({ membership_id: Number(selectedPlayer.id) });
      } else {
        await appointRole({
          membership_id: Number(selectedPlayer.id),
          role: roleKey,
          ...(isDoctorRole ? { is_qualified_professional: isQualifiedProfessional } : {}),
        });
      }
      showToast(
        `${selectedPlayer.firstName} ${selectedPlayer.lastName} est nommé ${roleLabel.toLowerCase()}. Il a été prévenu.`,
      );
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title={`Rôle : ${roleLabel}`}
        size="md"
        isSubmitting={submitting}
        hideFooter={!showSearch && !(canManage && role)}
        confirmLabel="Nommer"
        confirmLoadingLabel="Nomination…"
        confirmDisabled={!selectedPlayer || (isDoctorRole && isQualifiedProfessional === null)}
        onConfirm={showSearch ? () => void handleAppoint() : undefined}
        footer={
          canManage && role && !replacing ? (
            <>
              <Button variant="secondary" size="md" className="flex-1 sm:flex-none" onClick={onClose}>
                Fermer
              </Button>
              <Button
                variant="primary"
                size="md"
                className="flex-1 sm:flex-none"
                onClick={() => setReplacing(true)}
              >
                Remplacer
              </Button>
            </>
          ) : undefined
        }
      >
        <div className="space-y-4">
          {error ? <Banner variant="danger">{error}</Banner> : null}
          {role && holderName ? (
            <p className="text-sm text-text">
              Titulaire actuel : <span className="font-medium">{holderName}</span>
              {role.appointed_at ? (
                <span className="text-text-muted">
                  {" "}
                  · depuis le {new Date(role.appointed_at).toLocaleDateString("fr-FR")}
                </span>
              ) : null}
            </p>
          ) : (
            <p className="text-sm text-text-muted">Poste vacant.</p>
          )}

          {roleKey === "secretary" ? (
            <p className="text-[13px] text-text-muted">
              Le Secrétaire publie les communiqués, prépare les assemblées générales et dépose les documents dans les
              archives du club. Le nombre de titulaires dépend du réglage du club.
            </p>
          ) : null}

          {showSearch ? (
            <div>
              {replacing && holderName ? (
                <p className="mb-2 text-xs text-text-muted">{holderName} sera révoqué de ce rôle.</p>
              ) : null}
              <PlayerSearch
                value={selectedPlayer}
                onChange={setSelectedPlayer}
                searchPlayers={searchActiveClubPlayers}
                ariaLabel="Choisir un joueur"
                placeholder="Nom ou numéro du joueur"
              />
              {isDoctorRole ? (
                <fieldset className="mt-3 space-y-2">
                  <legend className="text-sm font-medium text-text">Statut du médecin</legend>
                  <label className="flex items-start gap-2 text-sm text-text">
                    <input
                      type="radio"
                      name="doctor-qualification"
                      checked={isQualifiedProfessional === true}
                      onChange={() => setIsQualifiedProfessional(true)}
                      className="mt-0.5 h-4 w-4 shrink-0 border-border-strong text-primary"
                    />
                    <span>Professionnel de santé qualifié</span>
                  </label>
                  <label className="flex items-start gap-2 text-sm text-text">
                    <input
                      type="radio"
                      name="doctor-qualification"
                      checked={isQualifiedProfessional === false}
                      onChange={() => setIsQualifiedProfessional(false)}
                      className="mt-0.5 h-4 w-4 shrink-0 border-border-strong text-primary"
                    />
                    <span>Non qualifié (affiché comme « Médecin / référent santé »)</span>
                  </label>
                </fieldset>
              ) : null}
              {!replacing ? (
                <p className="mt-2 text-xs text-text-muted">Un joueur peut cumuler plusieurs rôles.</p>
              ) : null}
            </div>
          ) : null}

          {canManage && role && !replacing ? (
            <button
              type="button"
              onClick={() => setConfirmOpen(true)}
              className="text-sm font-medium text-status-danger-fg hover:underline"
            >
              Révoquer {holderName}
            </button>
          ) : null}
        </div>
      </Modal>
      <ConfirmDialog
        open={confirmOpen}
        title={`Révoquer ${holderName ?? "ce titulaire"} du rôle de ${roleLabel} ?`}
        description="Il sera prévenu."
        confirmLabel="Révoquer"
        loading={submitting}
        onConfirm={() => void handleRevoke()}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
