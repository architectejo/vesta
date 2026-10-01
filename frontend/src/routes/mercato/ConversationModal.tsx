import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listThreadMessages, sendThreadMessage, type MercatoMessage, type MercatoThread } from "../../api/mercato";
import { Avatar, Button, Modal } from "../../design-system";

export interface ConversationModalProps {
  thread: MercatoThread | null;
  viewerClubId: number | undefined;
  onClose: () => void;
  onOpenOffer?: (offerId: number) => void;
}

interface PendingMessage {
  tempId: string;
  body: string;
  status: "sending" | "failed";
}

/** « Conversation » (fiche `mercato.md` §4.6). Interrogation toutes les 30 s
 * tant que la modale est ouverte, suspendue hors focus (React Query ne
 * relance pas `refetchInterval` quand l'onglet n'est pas visible, 6.5). */
export function ConversationModal({ thread, viewerClubId, onClose, onOpenOffer }: ConversationModalProps) {
  const open = thread !== null;
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<PendingMessage[]>([]);

  const messagesQuery = useQuery({
    queryKey: ["mercato", "thread-messages", thread?.id],
    queryFn: () => listThreadMessages(thread!.id),
    enabled: open,
    refetchInterval: open ? 30_000 : false,
  });

  useEffect(() => {
    if (!open) {
      setDraft("");
      setPending([]);
    }
  }, [open]);

  async function handleSend(): Promise<void> {
    if (!thread || !draft.trim()) return;
    const body = draft.trim();
    const tempId = crypto.randomUUID();
    setDraft("");
    setPending((current) => [...current, { tempId, body, status: "sending" }]);
    try {
      await sendThreadMessage(thread.id, body);
      setPending((current) => current.filter((m) => m.tempId !== tempId));
      void queryClient.invalidateQueries({ queryKey: ["mercato", "thread-messages", thread.id] });
      void queryClient.invalidateQueries({ queryKey: ["mercato", "threads"] });
    } catch {
      setPending((current) => current.map((m) => (m.tempId === tempId ? { ...m, status: "failed" } : m)));
    }
  }

  async function handleRetry(message: PendingMessage): Promise<void> {
    if (!thread) return;
    setPending((current) => current.map((m) => (m.tempId === message.tempId ? { ...m, status: "sending" } : m)));
    try {
      await sendThreadMessage(thread.id, message.body);
      setPending((current) => current.filter((m) => m.tempId !== message.tempId));
      void queryClient.invalidateQueries({ queryKey: ["mercato", "thread-messages", thread.id] });
    } catch {
      setPending((current) => current.map((m) => (m.tempId === message.tempId ? { ...m, status: "failed" } : m)));
    }
  }

  if (!thread) return null;

  const messages = messagesQuery.data?.results ?? [];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={thread.other_club.name}
      subtitle={thread.subject || "Échange entre dirigeants"}
      size="md"
      isDirty={draft.trim() !== ""}
      hideFooter
    >
      <div className="flex h-full flex-col">
        {thread.transfer_offer_id && onOpenOffer ? (
          <button
            type="button"
            onClick={() => onOpenOffer(thread.transfer_offer_id as number)}
            className="mb-3 inline-flex w-fit rounded-full bg-surface-muted px-2 py-1 text-xs text-text-muted hover:underline"
          >
            Offre · voir le détail
          </button>
        ) : null}

        {messagesQuery.isLoading ? (
          <p className="text-sm text-text-muted">Chargement…</p>
        ) : messagesQuery.isError ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            Impossible de charger la conversation. Réessayez.
          </p>
        ) : messages.length === 0 && pending.length === 0 ? (
          <p className="text-sm text-text-muted">Aucun message pour l'instant.</p>
        ) : (
          <div className="flex-1 space-y-3 overflow-y-auto">
            {messages.map((message: MercatoMessage) => {
              const own = message.club_id === viewerClubId;
              return (
                <div key={message.id} className={`flex gap-2 ${own ? "flex-row-reverse" : ""}`}>
                  <Avatar name={message.sender.name} size={32} />
                  <div className={`max-w-[75%] rounded-md px-3 py-2 text-sm ${own ? "bg-surface-muted" : "bg-surface"}`}>
                    <p className="text-xs text-text-muted">
                      {message.sender.name} · {new Date(message.sent_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                    </p>
                    <p className="text-text">{message.body}</p>
                  </div>
                </div>
              );
            })}
            {pending.map((message) => (
              <div key={message.tempId} className="flex flex-row-reverse gap-2">
                <div className="max-w-[75%] rounded-md bg-surface-muted px-3 py-2 text-sm">
                  <p className="text-text">{message.body}</p>
                  {message.status === "sending" ? (
                    <p className="text-xs text-text-muted">Envoi…</p>
                  ) : (
                    <p className="text-xs text-status-danger-fg">
                      Non envoyé.{" "}
                      <button type="button" className="underline" onClick={() => void handleRetry(message)}>
                        Réessayer
                      </button>
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-3 flex items-end gap-2 border-t border-border pt-3">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            placeholder="Votre message"
            aria-label="Votre message"
            className="h-16 max-h-32 flex-1 rounded-sm border border-border-strong bg-surface px-3 py-2 text-base text-text placeholder:text-text-muted"
          />
          <Button variant="primary" size="md" onClick={() => void handleSend()} disabled={!draft.trim()}>
            Envoyer
          </Button>
        </div>
      </div>
    </Modal>
  );
}
