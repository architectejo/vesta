/**
 * Correspondance statut -> couleur (docs/lot0/design-system.md §2.5,
 * cahier des charges §3.4). Les clés marquées « (proposition) » ne sont
 * pas imposées par le 3.4 et restent à valider par le client (§6 du
 * document) ; elles sont néanmoins déjà câblées pour que les écrans futurs
 * n'aient jamais à choisir une couleur eux-mêmes.
 */
export type StatusFamily = "success" | "warning" | "danger" | "suspended" | "neutral";

export type StatusKey =
  // Situation financière / adhésion (3.4)
  | "in_good_standing" // En ordre
  | "in_debt" // En dette
  | "pending" // En attente
  | "to_justify" // À justifier
  | "suspended" // Suspendu
  | "left" // Parti
  | "archived" // Archivé
  | "registered" // Inscrit (proposition)
  // Pointage (3.4)
  | "present"
  | "absent"
  | "late" // En retard, compté absent (proposition)
  | "excused" // Absent excusé (proposition)
  // Santé (3.4 ; medical.md §10 point 9 : ajouts « À compléter »/« En cours »/
  // « Retour déclaré »/« Indisponible » pour le module médical, lot 4)
  | "unfit" // Inapte
  | "injured" // Blessé (proposition)
  | "fit" // Apte (proposition)
  | "fit_restricted" // Apte avec restriction (proposition)
  | "medical_unavailable" // Indisponible (N0, medical.md §2.1)
  | "medical_injury_to_complete" // À compléter (blessure non complétée par le Médecin)
  | "medical_injury_open" // En cours (blessure)
  | "medical_injury_resolved" // Retour déclaré
  | "medical_consent_granted" // Accordé (consentement d'accès du Président, medical.md §4.11)
  | "medical_consent_not_granted" // Non accordé
  // Paiements (3.4 / proposition)
  | "to_validate" // À valider
  | "validated"
  | "refused"
  | "cancelled"
  | "queued" // En attente d'envoi (hors connexion)
  // Dépenses (proposition)
  | "expense_pending"
  | "expense_released"
  | "expense_justified"
  | "expense_unjustified"
  | "expense_refused"
  // Assistance sociale (CDC 4.5.3 ; fiche tresorerie-depenses-assistance.md §4.2, §7)
  | "assistance_eligible"
  | "assistance_not_eligible"
  | "assistance_approved"
  | "assistance_rejected"
  // Séance / match (proposition)
  | "session_open"
  | "session_locked"
  // Composition (proposition)
  | "lineup_draft"
  | "lineup_published"
  // Défi entre clubs (proposition)
  | "challenge_pending"
  | "challenge_accepted"
  | "challenge_refused"
  // Offre de transfert (proposition)
  | "transfer_pending"
  | "transfer_accepted"
  | "transfer_refused"
  | "transfer_blocked"
  | "transfer_done"
  // Assemblée générale (proposition)
  | "ag_convened"
  | "ag_pv_to_sign"
  | "ag_closed"
  // Licence (proposition)
  | "licence_trial"
  | "licence_active"
  | "licence_expired_grace"
  | "licence_suspended"
  | "licence_terminated"
  // Mercato (proposition)
  | "mercato_open"
  | "mercato_closed"
  | "vacant"
  // Mercato : offres et transferts (fiche mercato.md §8)
  | "transfer_awaiting_quitus" // Quitus en attente (vue du club offrant)
  | "transfer_cancelled" // Annulée
  | "unread" // Non lu (messagerie)
  // Matériel (fiche logistique.md §9)
  | "equipment_out" // Sorti
  | "equipment_partially_returned" // Rendu partiellement
  | "equipment_returned" // Rendu
  | "inventory_open" // En cours
  | "inventory_overdue" // Non clôturé
  | "inventory_closed" // Clôturé
  | "inventory_line_to_count" // À compter
  | "inventory_line_no_gap" // Sans écart
  | "inventory_line_justified" // Justifié (ligne d'inventaire)
  // Grille des cotisations (2.6, 4.4.7) : état d'une cellule mois × joueur
  | "grid_paid"
  | "grid_partial"
  | "grid_overdue"
  | "grid_upcoming"
  | "grid_free"
  | "grid_not_due"
  // Import des cotisations historiques (CDC 4.4.8 ; fiche tresorerie-import-cotisations.md §6)
  | "import_ready" // Prête
  | "import_failed" // Échec
  | "import_to_check"; // À vérifier (ligne prête avec avertissements)

export const STATUS_MAP: Record<StatusKey, { family: StatusFamily; label: string }> = {
  in_good_standing: { family: "success", label: "En ordre" },
  in_debt: { family: "danger", label: "En dette" },
  pending: { family: "warning", label: "En attente" },
  to_justify: { family: "warning", label: "À justifier" },
  suspended: { family: "suspended", label: "Suspendu" },
  left: { family: "neutral", label: "Parti" },
  archived: { family: "neutral", label: "Archivé" },
  registered: { family: "success", label: "Inscrit" },

  present: { family: "success", label: "Présent" },
  absent: { family: "danger", label: "Absent" },
  late: { family: "danger", label: "En retard" },
  excused: { family: "neutral", label: "Absent excusé" },

  unfit: { family: "danger", label: "Inapte" },
  injured: { family: "danger", label: "Blessé" },
  fit: { family: "success", label: "Apte" },
  fit_restricted: { family: "warning", label: "Apte avec restriction" },
  medical_unavailable: { family: "neutral", label: "Indisponible" },
  medical_injury_to_complete: { family: "warning", label: "À compléter" },
  medical_injury_open: { family: "warning", label: "En cours" },
  medical_injury_resolved: { family: "success", label: "Retour déclaré" },
  medical_consent_granted: { family: "success", label: "Accordé" },
  medical_consent_not_granted: { family: "neutral", label: "Non accordé" },

  to_validate: { family: "warning", label: "À valider" },
  validated: { family: "success", label: "Validé" },
  refused: { family: "danger", label: "Refusé" },
  cancelled: { family: "neutral", label: "Annulé" },
  queued: { family: "warning", label: "En attente d'envoi" },

  expense_pending: { family: "warning", label: "En attente" },
  expense_released: { family: "success", label: "Libérée" },
  expense_justified: { family: "success", label: "Justifiée" },
  expense_unjustified: { family: "danger", label: "Non justifiée" },
  expense_refused: { family: "danger", label: "Refusée" },

  assistance_eligible: { family: "success", label: "Éligible" },
  assistance_not_eligible: { family: "warning", label: "Non éligible" },
  assistance_approved: { family: "success", label: "Approuvée" },
  assistance_rejected: { family: "danger", label: "Refusée" },

  session_open: { family: "success", label: "Ouverte" },
  session_locked: { family: "neutral", label: "Verrouillée" },

  lineup_draft: { family: "warning", label: "Brouillon" },
  lineup_published: { family: "success", label: "Publiée" },

  challenge_pending: { family: "warning", label: "En attente" },
  challenge_accepted: { family: "success", label: "Accepté" },
  challenge_refused: { family: "danger", label: "Refusé" },

  transfer_pending: { family: "warning", label: "En attente" },
  transfer_accepted: { family: "success", label: "Acceptée" },
  transfer_refused: { family: "danger", label: "Refusée" },
  transfer_blocked: { family: "danger", label: "Bloquée (dette)" },
  transfer_done: { family: "success", label: "Transfert effectué" },

  ag_convened: { family: "warning", label: "Convoquée" },
  ag_pv_to_sign: { family: "warning", label: "PV à signer" },
  ag_closed: { family: "success", label: "Clôturée" },

  licence_trial: { family: "success", label: "Essai" },
  licence_active: { family: "success", label: "Active" },
  licence_expired_grace: { family: "warning", label: "Expirée (grâce)" },
  licence_suspended: { family: "suspended", label: "Suspendue" },
  licence_terminated: { family: "neutral", label: "Résiliée" },

  mercato_open: { family: "success", label: "Sur le marché" },
  mercato_closed: { family: "neutral", label: "Fermé aux offres" },
  vacant: { family: "neutral", label: "Poste vacant" },

  transfer_awaiting_quitus: { family: "warning", label: "Quitus en attente" },
  transfer_cancelled: { family: "neutral", label: "Annulée" },
  unread: { family: "warning", label: "Non lu" },

  equipment_out: { family: "warning", label: "Sorti" },
  equipment_partially_returned: { family: "warning", label: "Rendu partiellement" },
  equipment_returned: { family: "success", label: "Rendu" },
  inventory_open: { family: "warning", label: "En cours" },
  inventory_overdue: { family: "danger", label: "Non clôturé" },
  inventory_closed: { family: "success", label: "Clôturé" },
  inventory_line_to_count: { family: "neutral", label: "À compter" },
  inventory_line_no_gap: { family: "success", label: "Sans écart" },
  inventory_line_justified: { family: "success", label: "Justifié" },

  grid_paid: { family: "success", label: "Payé" },
  grid_partial: { family: "warning", label: "Partiel" },
  grid_overdue: { family: "danger", label: "Impayé échu" },
  grid_upcoming: { family: "neutral", label: "À venir" },
  grid_free: { family: "neutral", label: "Libre" },
  grid_not_due: { family: "neutral", label: "Non dû" },

  import_ready: { family: "success", label: "Prête" },
  import_failed: { family: "danger", label: "Échec" },
  import_to_check: { family: "warning", label: "À vérifier" },
};
