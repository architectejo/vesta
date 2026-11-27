/**
 * Destination d'un clic sur une notification (CDC 4.17 : « mène à l'élément
 * concerné »). `link_object_type` est le nom de la classe du modèle cible
 * côté API. Les écrans de destination ouvrent la modale de détail grâce à un
 * paramètre d'URL (voir `hooks/useDeepLink.ts`).
 *
 * Types émis par l'API SANS écran atteignable (le clic marque seulement la
 * notification comme lue) :
 * - `Licence` (rappel d'expiration envoyé au Président du club) : aucun écran
 *   de licence n'existe dans l'espace club ;
 * - `LedgerChainState` (alerte Superuser) ;
 * - `Incident` (carton, suspension) : l'incident est rattaché à un match ou une
 *   séance, mais la notification ne porte que l'identifiant de l'incident et
 *   l'API n'expose aucun moyen de retrouver l'événement depuis cet
 *   identifiant. Correction backend nécessaire : exposer l'événement (ou le
 *   match) dans la notification ;
 * - `Post` signalé (`post_reported`, destiné aux Superusers) : /fil est un écran
 *   de l'espace club, hors de portée d'un Superuser ;
 * - tout type inconnu ou vide.
 */

import { FINANCIAL_SITUATION_ROUTE } from "../routes/profil/profileLinks";

export interface NotificationLinkInput {
  eventType: string;
  linkObjectType: string;
  linkObjectId: number | null;
}

export interface NotificationLinkContext {
  /** Vrai pour le Trésorier et l'adjoint : destinataires des déclarations « J'ai payé ». */
  isPaymentRecorder: boolean;
  /**
   * Vrai pour le Coach, seul à pouvoir ouvrir le tableau noir (édition). Les
   * autres rôles consultent le plan en lecture seule, dans la modale de la
   * liste des plans (CDC 4.11 « Partage »).
   */
  isCoach?: boolean;
  /** Vrai pour le Trésorier, l'adjoint et le Président (vue d'ensemble de la trésorerie). */
  isTreasuryViewer?: boolean;
  /** Vrai pour un Superuser (aucun écran de l'espace club ne le concerne). */
  isSuperuser?: boolean;
}

export function resolveNotificationRoute(
  { eventType, linkObjectType, linkObjectId }: NotificationLinkInput,
  { isPaymentRecorder, isCoach = false, isTreasuryViewer = false, isSuperuser = false }: NotificationLinkContext,
): string | null {
  const id = linkObjectId;
  // Incitation du chat (CDC 10.3 n° 182, fil-public-communication.md C7.5) :
  // sans objet lié ; « mène à leur solde », jamais au chat.
  if (eventType === "chat_members_in_order_incentive") return FINANCIAL_SITUATION_ROUTE;
  switch (linkObjectType) {
    case "Match":
      return id === null ? null : `/matchs/${id}`;
    case "TacticalPlan":
      if (id === null) return null;
      return isCoach ? `/plans/${id}/tableau` : `/vestiaire?onglet=plans&plan=${id}`;
    case "MembershipApplication":
      return id === null ? "/club/comite" : `/club/comite?adhesion=${id}`;
    case "Membership":
      return "/club/comite";
    case "Payment":
      if (id === null) return isPaymentRecorder ? "/tresorerie" : "/profil";
      if (isPaymentRecorder && eventType === "i_paid_declared") return `/tresorerie?paiement=${id}`;
      // Paiement validé ou déclaration refusée (`i_paid_rejected`) : le joueur concerné
      // les retrouve sur son profil (la déclaration refusée y est rouverte).
      if (eventType === "i_paid_rejected") return `/profil?declaration=${id}`;
      return eventType === "i_paid_declared" ? `/profil?declaration=${id}` : `/profil?paiement=${id}`;
    case "Due":
      // « Dette constatée » : le joueur concerné n'est pas identifiable par le seul type ;
      // le rôle du profil en cache décide (joueur -> son profil, bureau financier -> trésorerie).
      return isTreasuryViewer ? "/tresorerie" : "/profil";
    case "Session":
      return id === null ? null : `/seances/${id}`;
    case "Expense":
      return id === null ? "/tresorerie/depenses" : `/tresorerie/depenses?depense=${id}`;
    case "SocialAssistanceRequest":
      return id === null ? "/tresorerie/assistance" : `/tresorerie/assistance?demande=${id}`;
    case "Assembly":
      return id === null ? "/club/assemblees" : `/club/assemblees?assemblee=${id}`;
    case "Post":
      // Signalement : notification réservée aux Superusers, sans écran de modération.
      if (isSuperuser || eventType === "post_reported") return null;
      return id === null ? "/fil" : `/fil?publication=${id}`;
    case "Announcement":
      return id === null ? "/club/communiques" : `/club/communiques?communique=${id}`;
    case "Injury":
      return "/medical";
    case "TransferOffer":
    case "MercatoThread":
      return "/mercato";
    case "Inventory":
      return id === null ? "/materiel" : `/materiel?inventaire=${id}`;
    default:
      return null;
  }
}
