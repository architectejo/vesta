import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  downloadChatMessageImage,
  listChatMessages,
  markChannelRead,
  sendChatMessage,
  type ChatChannel,
  type ChatMessage,
} from "../../../api/social";
import { useAuth } from "../../../auth/AuthContext";
import { AuthenticatedImage, Button, EmptyState, Modal, Skeleton } from "../../../design-system";
import { ImagePickerField } from "../../fil/ImagePickerField";
import { ImageViewerModal } from "../../fil/ImageViewerModal";

const PAGE_SIZE = 30;
const MAX_BODY = 2000;

const CHANNEL_META: Record<ChatChannel["channel_type"], string> = { general: "Général", board: "Bureau" };

function dayLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return "Aujourd'hui";
  if (date.toDateString() === yesterday.toDateString()) return "Hier";
  return new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" }).format(date);
}

function formatTime(iso: string): string {
  return new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

function MessageImage({ message, onOpen }: { message: ChatMessage; onOpen: () => void }) {
  if (!message.image_url) return null;
  return (
    <AuthenticatedImage
      cacheKey={message.id}
      download={() => downloadChatMessageImage(message.id)}
      alt={`Image envoyée par ${message.sender.first_name} ${message.sender.last_name}`}
      onClick={onOpen}
      className="mt-1 max-w-[240px] cursor-pointer rounded-md object-cover"
    />
  );
}

/** Modale « Conversation » (fil-public-communication.md C4). */
export function ConversationModal({ channel, onClose }: { channel: ChatChannel; onClose: () => void }) {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [body, setBody] = useState("");
  const [image, setImage] = useState<File[]>([]);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [viewerMessageId, setViewerMessageId] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const markedIdRef = useRef<number | null>(null);

  const messagesQuery = useQuery({
    queryKey: ["social", "chat", "messages", channel.id, limit],
    queryFn: () => listChatMessages(channel.id, { limit }),
    refetchInterval: () => (document.visibilityState === "hidden" ? false : 10_000),
  });

  const messages = messagesQuery.data?.results ?? [];

  useEffect(() => {
    // `scrollIntoView` n'existe pas dans jsdom (tests) : jamais supposé
    // présent, comme les autres accès DOM optionnels du projet.
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ block: "end" });
    }
  }, [messages.length]);

  useEffect(() => {
    const last = messages[messages.length - 1];
    if (!last || markedIdRef.current === last.id) return;
    markedIdRef.current = last.id;
    void markChannelRead(channel.id, last.id).then(() => {
      void queryClient.invalidateQueries({ queryKey: ["social", "chat", "channels"] });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length]);

  async function handleSend(): Promise<void> {
    if (!body.trim() && image.length === 0) return;
    setSending(true);
    setSendError(null);
    try {
      await sendChatMessage(channel.id, { body: body.trim(), image: image[0] ?? null });
      setBody("");
      setImage([]);
      await queryClient.invalidateQueries({ queryKey: ["social", "chat", "messages", channel.id] });
      await queryClient.invalidateQueries({ queryKey: ["social", "chat", "channels"] });
    } catch {
      setSendError("Non envoyé");
    } finally {
      setSending(false);
    }
  }

  const grouped: Array<{ day: string; items: ChatMessage[] }> = [];
  for (const message of messages) {
    const label = dayLabel(message.sent_at);
    const lastGroup = grouped[grouped.length - 1];
    if (lastGroup && lastGroup.day === label) lastGroup.items.push(message);
    else grouped.push({ day: label, items: [message] });
  }

  const viewerImage = messages.find((m) => m.id === viewerMessageId);

  return (
    <Modal open onClose={onClose} title={CHANNEL_META[channel.channel_type]} size="lg" hideFooter>
      <div className="flex h-[70vh] flex-col">
        <div className="flex-1 space-y-3 overflow-y-auto pr-1">
          {messagesQuery.isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} variant="row" />
              ))}
            </div>
          ) : messagesQuery.isError ? (
            <EmptyState variant="error" message="Impossible de charger les messages." actionLabel="Réessayer" onAction={() => void messagesQuery.refetch()} />
          ) : messages.length === 0 ? (
            <EmptyState message="Aucun message pour l'instant. Lancez la conversation." />
          ) : (
            <>
              {messagesQuery.data && messagesQuery.data.next_offset !== null ? (
                <button
                  type="button"
                  className="mx-auto flex min-h-control-sm w-fit items-center text-xs font-medium text-primary-text hover:underline"
                  onClick={() => setLimit((n) => n + PAGE_SIZE)}
                >
                  Messages précédents
                </button>
              ) : null}
              {grouped.map((group) => (
                <div key={group.day}>
                  <p className="my-2 text-center text-[13px] text-text-muted">{group.day}</p>
                  <div className="space-y-2">
                    {group.items.map((message) => {
                      const isMine = auth.user?.id === message.sender.id;
                      return (
                        <div key={message.id} className={["flex flex-col", isMine ? "items-end" : "items-start"].join(" ")}>
                          <div
                            className={[
                              "max-w-[80%] rounded-md px-3 py-2",
                              isMine ? "bg-primary/10 text-text" : "bg-surface-muted text-text",
                            ].join(" ")}
                          >
                            {!isMine ? (
                              <p className="text-[13px] font-semibold text-text">
                                {message.sender.first_name} {message.sender.last_name}
                              </p>
                            ) : null}
                            {message.body ? <p className="text-sm" style={{ overflowWrap: "anywhere" }}>{message.body}</p> : null}
                            <MessageImage message={message} onOpen={() => setViewerMessageId(message.id)} />
                          </div>
                          <p className="mt-0.5 text-[13px] text-text-muted">{formatTime(message.sent_at)}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="sticky -bottom-4 z-20 -mx-4 -mb-4 mt-2 space-y-2 border-t border-border bg-surface px-4 py-3">
          {sendError ? <p className="text-xs text-status-danger-fg">{sendError}</p> : null}
          <ImagePickerField images={image} onChange={setImage} max={1} maxLabel="1 image au maximum." addLabel="Ajouter une image" />
          <div className="flex items-end gap-2">
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value.slice(0, MAX_BODY))}
              rows={1}
              placeholder="Écrire un message…"
              aria-label="Écrire un message…"
              maxLength={MAX_BODY}
              className="h-control-md flex-1 resize-none rounded-sm border border-border-strong bg-surface px-3 py-2 text-base text-text placeholder:text-text-muted"
            />
            <Button
              variant="primary"
              size="md"
              disabled={!body.trim() && image.length === 0}
              loading={sending}
              onClick={() => void handleSend()}
            >
              Envoyer
            </Button>
          </div>
        </div>
      </div>

      {viewerImage?.image_url ? (
        <ImageViewerModal
          images={[
            {
              id: viewerImage.id,
              url: null,
              download: () => downloadChatMessageImage(viewerImage.id),
              alt: `Image envoyée par ${viewerImage.sender.first_name} ${viewerImage.sender.last_name}`,
            },
          ]}
          startIndex={0}
          onClose={() => setViewerMessageId(null)}
        />
      ) : null}
    </Modal>
  );
}
