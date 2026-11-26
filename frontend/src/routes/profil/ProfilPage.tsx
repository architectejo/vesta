import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { downloadPersonalData, logoutAllDevices } from "../../api/auth";
import { ApiError, triggerBlobDownload } from "../../api/client";
import { getMyProfile } from "../../api/clubs";
import { getMyPresidentAccess } from "../../api/medical";
import {
  getNotificationPreference,
  setNotificationPreference,
} from "../../api/notifications";
import { useAuth } from "../../auth/AuthContext";
import { useClosingState } from "../../hooks/useClosingState";
import {
  Avatar,
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  IconMore,
  Loader,
  StatusBadge,
  useToast,
} from "../../design-system";
import { PlayerCardModal } from "../club/PlayerCardModal";
import { MedicalConsentModal } from "../medical/MedicalConsentModal";
import { MyHealthRecordModal } from "../medical/MyHealthRecordModal";
import { AssistanceCard } from "./AssistanceCard";
import { EditProfileModal } from "./EditProfileModal";
import { FinancialSituationCard } from "./FinancialSituationCard";

function formatDate(value: string | null): string {
  if (!value) return "Non renseigné";
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", year: "numeric" }).format(
    new Date(value),
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1 text-sm">
      <span className="text-text-muted">{label}</span>
      <span className="text-text">{value}</span>
    </div>
  );
}

/**
 * Écran « Mon profil » (docs/ecrans/comptes-mon-profil.md). Périmètre du
 * Lot 1 (voir profile_services.get_my_profile) : Identité (sans le
 * `StatusBadge` financier ni le badge Suspendu — trésorerie et discipline
 * ne sont pas construites), Informations personnelles, Préférences. Santé
 * (Lot 4, medical.md §4.10, §4.11) : carte « Santé » avec « Ma fiche de
 * santé » et l'état du consentement d'accès du Président — voir
 * `routes/medical/MyHealthRecordModal.tsx` et
 * `routes/medical/MedicalConsentModal.tsx`. Pas de badge d'aptitude/« Blessé »
 * sur la carte d'identité (voir compte rendu : aucun point d'accès léger
 * N1 sur soi-même n'existe encore côté API sans journaliser une
 * consultation du dossier complet). Situation financière (« J'ai payé »,
 * reçus) et Assistance sociale (demande, barèmes) : voir
 * `FinancialSituationCard` et `AssistanceCard`. Statistiques et Mercato
 * restent hors périmètre. « Télécharger mes données » appelle l'export RGPD
 * authentifié (GET /auth/profile/export/, CDC 7.5) ; « Demander la
 * suppression » reste désactivée : aucun circuit de suppression n'est tranché.
 */
export function ProfilPage() {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const { mounted: menuMounted, dataState: menuDataState, onAnimationEnd: onMenuAnimationEnd } =
    useClosingState(menuOpen, 200);
  const [cardOpen, setCardOpen] = useState(false);
  const [logoutAllOpen, setLogoutAllOpen] = useState(false);
  const [loggingOutAll, setLoggingOutAll] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [healthRecordOpen, setHealthRecordOpen] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);
  const auth = useAuth();

  const profileQuery = useQuery({
    queryKey: ["profile", "me"],
    queryFn: getMyProfile,
    staleTime: 60_000,
  });

  const preferenceQuery = useQuery({
    queryKey: ["notification-preference"],
    queryFn: getNotificationPreference,
  });

  // État EFFECTIF du consentement d'accès du Président (medical.md §4.11) :
  // lecture seule, sans journalisation (contrairement à l'ouverture de
  // « Ma fiche de santé », qui journalise côté API à chaque ouverture —
  // volontairement pas préchargée ici).
  const consentQuery = useQuery({
    queryKey: ["medical", "me", "president-access"],
    queryFn: getMyPresidentAccess,
  });

  async function togglePreference(next: boolean): Promise<void> {
    try {
      await setNotificationPreference(next);
      showToast("Préférence enregistrée.");
      void queryClient.invalidateQueries({ queryKey: ["notification-preference"] });
    } catch {
      showToast("Une erreur est survenue de notre côté. Réessayez dans un instant.");
    }
  }

  async function handleExportData(): Promise<void> {
    setExporting(true);
    try {
      const { blob, filename } = await downloadPersonalData();
      triggerBlobDownload(blob, filename);
    } catch (error) {
      showToast(
        error instanceof ApiError
          ? error.detail
          : "Impossible de télécharger vos données. Réessayez dans un instant.",
      );
    } finally {
      setExporting(false);
      setMenuOpen(false);
    }
  }

  async function handleLogoutAllDevices(): Promise<void> {
    setLoggingOutAll(true);
    try {
      await logoutAllDevices();
      showToast("Déconnecté de tous les appareils.");
      setLogoutAllOpen(false);
      await auth.logout();
    } finally {
      setLoggingOutAll(false);
    }
  }

  if (profileQuery.isLoading) {
    return <Loader loading variant="page" />;
  }

  if (profileQuery.isError || !profileQuery.data) {
    return (
      <EmptyState
        variant="error"
        message="Impossible de charger votre profil."
        actionLabel="Réessayer"
        onAction={() => void profileQuery.refetch()}
      />
    );
  }

  const profile = profileQuery.data;
  const fullName = `${profile.identity.first_name} ${profile.identity.last_name}`;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-text">Mon profil</h1>
          <p className="text-sm text-text-muted">{profile.club.name}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="primary" size="sm" onClick={() => setEditOpen(true)}>
            Modifier mon profil
          </Button>
          <div className="relative">
            <IconButton
              aria-label="Ouvrir le menu"
              onClick={() => setMenuOpen((v) => !v)}
              icon={<IconMore aria-hidden="true" className="h-5 w-5" />}
            />
            {menuMounted ? (
              <div
                data-state={menuDataState}
                onAnimationEnd={onMenuAnimationEnd}
                className="vesta-anim-menu absolute right-0 z-10 mt-1 w-64 rounded-md border border-border bg-surface py-1 shadow-elevated"
              >
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    setCardOpen(true);
                  }}
                  className="flex w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                >
                  Voir ma carte de joueur
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    setLogoutAllOpen(true);
                  }}
                  className="flex w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                >
                  Déconnecter tous mes appareils
                </button>
                <button
                  type="button"
                  disabled={exporting}
                  onClick={() => void handleExportData()}
                  className="flex w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted disabled:cursor-not-allowed disabled:text-text-muted"
                >
                  {exporting ? "Téléchargement…" : "Télécharger mes données"}
                </button>
                {/* Aucun circuit de suppression tranché (CDC 7.5) : entrée désactivée. */}
                <button
                  type="button"
                  disabled
                  title="Bientôt disponible"
                  className="flex w-full cursor-not-allowed px-3 py-2 text-left text-sm text-text-muted"
                >
                  Demander la suppression de mon compte (bientôt disponible)
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <div className="flex items-center gap-3">
          <Avatar name={fullName} photoUrl={profile.identity.photo} size={72} />
          <div>
            <p className="text-xl font-semibold text-text">{fullName}</p>
            <p className="text-sm text-text-muted">
              {profile.position_label || "Poste non renseigné"} · n°{" "}
              {profile.jersey_number ?? "Sans numéro"}
            </p>
            {profile.roles.length > 0 ? (
              <ul className="mt-1 flex flex-wrap gap-1">
                {profile.roles.map((role) => (
                  <li
                    key={role.role}
                    className="rounded-full bg-surface-muted px-2 py-0.5 text-xs text-text"
                  >
                    {role.label}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>
        <p className="mt-2 text-xs text-text-muted">
          Poste et numéro sont attribués par le Coach.
        </p>
      </section>

      <FinancialSituationCard />

      <AssistanceCard />

      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <h2 className="text-base font-semibold text-text">Informations personnelles</h2>
        <div className="mt-2 divide-y divide-border">
          <InfoRow label="Date de naissance" value={formatDate(profile.identity.birth_date)} />
          <InfoRow label="Poids" value={profile.identity.weight_kg ? `${profile.identity.weight_kg} kg` : "Non renseigné"} />
          <InfoRow label="Taille" value={profile.identity.height_cm ? `${profile.identity.height_cm} cm` : "Non renseigné"} />
          <InfoRow label="Téléphone" value={profile.identity.phone || "Non renseigné"} />
          <InfoRow label="Email" value={profile.identity.email} />
        </div>
        <p className="mt-2 text-xs text-text-muted">Ces informations ne sont jamais publiques.</p>
      </section>

      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <h2 className="text-base font-semibold text-text">Santé</h2>
        <div className="mt-2 divide-y divide-border">
          <div className="flex items-center justify-between gap-2 py-2">
            <span className="text-sm text-text">Ma fiche de santé, mes blessures et mon aptitude</span>
            <Button size="sm" variant="secondary" onClick={() => setHealthRecordOpen(true)}>
              Ouvrir
            </Button>
          </div>
          <div className="flex items-center justify-between gap-2 py-2">
            <span className="flex items-center gap-2 text-sm text-text">
              Accès du Président à mon dossier complet
              {!consentQuery.isLoading ? (
                <StatusBadge
                  status={consentQuery.data?.granted ? "medical_consent_granted" : "medical_consent_not_granted"}
                />
              ) : null}
            </span>
            <Button size="sm" variant="secondary" onClick={() => setConsentOpen(true)}>
              Gérer
            </Button>
          </div>
        </div>
      </section>

      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <h2 className="text-base font-semibold text-text">Préférences</h2>
        <label className="mt-2 flex min-h-control-sm cursor-pointer items-center justify-between gap-2 py-2 text-sm text-text">
          <span>Recevoir aussi mes notifications par email</span>
          <input
            type="checkbox"
            role="switch"
            checked={preferenceQuery.data?.email_enabled ?? false}
            disabled={preferenceQuery.isLoading}
            onChange={(e) => void togglePreference(e.target.checked)}
            className="h-5 w-9 shrink-0 rounded-full"
          />
        </label>
      </section>

      {editOpen ? (
        <EditProfileModal
          profile={profile}
          onClose={() => setEditOpen(false)}
          onUpdated={() => void queryClient.invalidateQueries({ queryKey: ["profile", "me"] })}
        />
      ) : null}
      {cardOpen ? (
        <PlayerCardModal
          membershipId={profile.membership_id}
          onClose={() => setCardOpen(false)}
          isOwnCard
        />
      ) : null}
      {healthRecordOpen ? (
        <MyHealthRecordModal
          open
          membershipId={profile.membership_id}
          playerName={fullName}
          onClose={() => setHealthRecordOpen(false)}
        />
      ) : null}
      {consentOpen ? (
        <MedicalConsentModal
          open
          onClose={() => {
            setConsentOpen(false);
            void queryClient.invalidateQueries({ queryKey: ["medical", "me", "president-access"] });
          }}
        />
      ) : null}
      <ConfirmDialog
        open={logoutAllOpen}
        title="Déconnecter tous vos appareils ?"
        description="Vous devrez vous reconnecter partout, y compris ici."
        confirmLabel="Déconnecter"
        loading={loggingOutAll}
        onConfirm={() => void handleLogoutAllDevices()}
        onCancel={() => setLogoutAllOpen(false)}
      />
    </div>
  );
}
