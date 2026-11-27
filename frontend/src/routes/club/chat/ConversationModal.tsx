import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../../api/client";
import {
  downloadChatMessageImage,
  listChatMessages,
  markChannelRead,
  sendChatMessage,
  type ChatChannel,
  type ChatMessage,
} from "../../../api/social";
import { useAuth } from "../../../auth/AuthContext";
import {
  AuthenticatedImage,
  Banner,
  Button,
  Checkbox,
  ConfirmDialog,
  EmptyState,
  IconLock,
  Modal,
  Skeleton,
} from "../../../design-system";
import { ImagePickerField } from "../../fil/ImagePickerField";
import { ImageViewerModal } from "../../fil/ImageViewerModal";
import { useOnlineStatus } from "../../logistics/useOnlineStatus";
import { FINANCIAL_SITUATION_ROUTE } from "../../profil/profileLinks";

const PAGE_SIZE = 30;
const MAX_BODY = 2000;
/** Marge (px) sous laquelle le lecteur est considéré « en bas » de la conversation. */
const BOTTOM_THRESHOLD = 48;

const CHANNEL_META: Record<ChatChannel["channel_type"], string> = { general: "Général", board: "Bureau" };

/** Textes exacts de la fiche fil-public-communication.md C7.8. */
const RESERVED_LABEL = "Réservé aux membres en ordre";
const RESERVED_HELP = "Seuls les joueurs en ordre de cotisation et le bureau le verront.";
const RESERVED_PLACEHOLDER = "Message réservé aux membres en ordre…";
const RESERVED_BADGE = "Membres en ordre";
const HIDDEN_RESERVED_NOTICE = "Certains messages sont réservés aux membres en ordre de cotisation.";
const RESERVED_REVOKED_ERROR = "Vous ne pouvez plus réserver un message aux membres en ordre.";
const DEFAULT_PLACEHOLDER = "Écrire un message…";

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

/**
 * Badge « Membres en ordre » d'un message réservé (C7.3, P4) : gris neutre,
 * il qualifie le message et non un joueur (jamais le vert du statut financier).
 */
function ReservedBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-status-neutral-bg px-2 py-0.5 text-[13px] font-medium text-status-neutral-fg">
      <IconLock aria-hidden="true" className="h-3 w-3" strokeWidth={1.75} />
      {RESERVED_BADGE}
    </span>
  );
}

/** Modale « Conversation » (fil-public-communication.md C4 et C7). */
export function ConversationModal({ channel, onClose }: { channel: ChatChannel; onClose: () => void }) {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const online = useOnlineStatus();
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [body, setBody] = useState("");
  const [image, setImage] = useState<File[]>([]);
  // C7.2 : décochée à l'ouverture et après chaque envoi réussi.
  const [membersInOrderOnly, setMembersInOrderOnly] = useState(false);
  // C7.6 : droit retiré entre-temps (refus de l'API) -> la case disparaît.
  const [restrictRevoked, setRestrictRevoked] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [viewerMessageId, setViewerMessageId] = useState<number | null>(null);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const atBottomRef = useRef(true);
  const markedIdRef = useRef<number | null>(null);
  const fingerprintRef = useRef<string | null>(null);
  const hiddenFlagRef = useRef(channel.has_hidden_reserved_messages);

  // Le droit de réserver est porté par le canal (API) : jamais déduit des rôles.
  const canRestrict = channel.can_restrict_to_members_in_order && !restrictRevoked;
  const reserved = canRestrict && membersInOrderOnly;
  const isDirty = body.trim() !== "" || image.length > 0;

  const messagesQuery = useQuery({
    queryKey: ["social", "chat", "messages", channel.id, limit],
    // Fenêtre complète à chaque interrogation (`limit`, pas `after=`) : les
    // messages réservés rendus visibles ou masqués par un changement de
    // situation du joueur apparaissent ou disparaissent à leur place (C7.4).
    queryFn: () => listChatMessages(channel.id, { limit }),
    refetchInterval: () => (document.visibilityState === "hidden" ? false : 10_000),
  });

  const messages = messagesQuery.data?.results ?? [];
  const fingerprint = messages.map((m) => m.id).join(",");

  // C7.4 : la situation du joueur a changé (indicateur du canal) -> rechargement
  // complet de la fenêtre affichée, sans attendre l'interrogation suivante.
  useEffect(() => {
    if (hiddenFlagRef.current === channel.has_hidden_reserved_messages) return;
    hiddenFlagRef.current = channel.has_hidden_reserved_messages;
    void queryClient.invalidateQueries({ queryKey: ["social", "chat", "messages", channel.id] });
  }, [channel.has_hidden_reserved_messages, channel.id, queryClient]);

  // Inversement : la fenêtre a changé (messages apparus ou disparus) -> la
  // liste des canaux est relue (bandeau, aperçu, compteur).
  useEffect(() => {
    if (!messagesQuery.isSuccess) return;
    if (fingerprintRef.current !== null && fingerprintRef.current !== fingerprint) {
      void queryClient.invalidateQueries({ queryKey: ["social", "chat", "channels"] });
    }
    fingerprintRef.current = fingerprint;
  }, [fingerprint, messagesQuery.isSuccess, queryClient]);

  useEffect(() => {
    // Défilement automatique seulement si le lecteur est en bas (C4 ; C7.4 :
    // pas de saut si le joueur lit plus haut). `scrollIntoView` n'existe pas
    // dans jsdom (tests) : jamais supposé présent.
    if (!atBottomRef.current) return;
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

  function handleScroll(): void {
    const el = scrollRef.current;
    if (!el) return;
    atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < BOTTOM_THRESHOLD;
  }

  async function handleSend(): Promise<void> {
    if (!body.trim() && image.length === 0) return;
    setSending(true);
    setSendError(null);
    try {
      await sendChatMessage(channel.id, {
        body: body.trim(),
        image: image[0] ?? null,
        membersInOrderOnly: reserved,
      });
      setBody("");
      setImage([]);
      setMembersInOrderOnly(false);
      atBottomRef.current = true;
      await queryClient.invalidateQueries({ queryKey: ["social", "chat", "messages", channel.id] });
      await queryClient.invalidateQueries({ queryKey: ["social", "chat", "channels"] });
    } catch (error) {
      if (reserved && error instanceof ApiError && error.status === 403) {
        // Droit retiré entre-temps : brouillon conservé, aucun renvoi
        // automatique « visible par tous » (C7.6).
        setRestrictRevoked(true);
        setMembersInOrderOnly(false);
        setSendError(RESERVED_REVOKED_ERROR);
      } else if (error instanceof ApiError && error.status === 400) {
        setSendError(error.detail);
      } else {
        setSendError("Non envoyé");
      }
    } finally {
      setSending(false);
    }
  }

  function goToBalance(): void {
    navigate(FINANCIAL_SITUATION_ROUTE);
    onClose();
  }

  const grouped: Array<{ day: string; items: ChatMessage[] }> = [];
  for (const message of messages) {
    const label = dayLabel(message.sent_at);
    const lastGroup = grouped[grouped.length - 1];
    if (lastGroup && lastGroup.day === label) lastGroup.items.push(message);
    else grouped.push({ day: label, items: [message] });
  }

  const viewerImage = messages.find((m) => m.id === viewerMessageId);
  // C7.4 / C7.6 : bandeau seulement si l'API l'indique, jamais pendant le
  // chargement ni en cas d'erreur de la liste.
  const showHiddenNotice = channel.has_hidden_reserved_messages && messagesQuery.isSuccess;

  return (
    <Modal open onClose={onClose} title={CHANNEL_META[channel.channel_type]} size="lg" hideFooter isDirty={isDirty}>
      <div className="flex h-[70vh] flex-col">
        {showHiddenNotice ? (
          // Lien en ligne après la phrase : 2 lignes au plus à 360 px ; la zone
          // tactile de 44 px est portée par un pseudo-élément (comme `Checkbox`).
          <Banner variant="info" role="note" className="mb-2 shrink-0">
            <span className="text-[13px]">
              {HIDDEN_RESERVED_NOTICE}{" "}
              <button
                type="button"
                onClick={() => (isDirty ? setConfirmLeave(true) : goToBalance())}
                className="relative inline font-medium text-primary-text underline before:absolute before:-inset-x-1 before:-inset-y-3 before:content-['']"
              >
                Voir mon solde
              </button>
            </span>
          </Banner>
        ) : null}

        <div ref={scrollRef} onScroll={handleScroll} className="flex-1 space-y-3 overflow-y-auto pr-1">
          {messagesQuery.isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} variant="row" />
              ))}
            </div>
          ) : messagesQuery.isError ? (
            <EmptyState variant="error" message="Impossible de charger les messages." actionLabel="Réessayer" onAction={() => void messagesQuery.refetch()} />
          ) : messages.length === 0 ? (
            <EmptyState
              message={
                channel.has_hidden_reserved_messages
                  ? "Aucun message à afficher pour l'instant."
                  : "Aucun message pour l'instant. Lancez la conversation."
              }
            />
          ) : (
            <>
              {messagesQuery.data && messagesQuery.data.next_offset !== null ? (
                <button
                  type="button"
                  className="mx-auto flex min-h-control-sm w-fit items-center text-xs font-medium text-primary-text hover:underline"
                  onClick={() => {
                    atBottomRef.current = false;
                    setLimit((n) => n + PAGE_SIZE);
                  }}
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
                        <div
                          key={message.id}
                          data-testid={`chat-message-${message.id}`}
                          className={["flex flex-col", isMine ? "items-end" : "items-start"].join(" ")}
                        >
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
                            {message.members_in_order_only ? (
                              <div className={["mb-1 flex", isMine ? "justify-end" : "justify-start"].join(" ")}>
                                <ReservedBadge />
                              </div>
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
          {canRestrict ? (
            <Checkbox
              checked={membersInOrderOnly}
              onChange={setMembersInOrderOnly}
              disabled={!online}
              label={
                <span className="inline-flex items-center gap-1 font-medium">
                  {membersInOrderOnly ? <IconLock aria-hidden="true" className="h-4 w-4" strokeWidth={1.75} /> : null}
                  {RESERVED_LABEL}
                </span>
              }
              description={RESERVED_HELP}
            />
          ) : null}
          <div className="flex items-end gap-2">
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value.slice(0, MAX_BODY))}
              rows={1}
              placeholder={reserved ? RESERVED_PLACEHOLDER : DEFAULT_PLACEHOLDER}
              aria-label={DEFAULT_PLACEHOLDER}
              maxLength={MAX_BODY}
              className="h-control-md flex-1 resize-none rounded-sm border border-border-strong bg-surface px-3 py-2 text-base text-text placeholder:text-text-muted"
            />
            <Button
              variant="primary"
              size="md"
              disabled={!online || (!body.trim() && image.length === 0)}
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

      <ConfirmDialog
        open={confirmLeave}
        title="Abandonner les modifications ?"
        description="Les informations saisies seront perdues."
        confirmLabel="Abandonner"
        cancelLabel="Continuer la saisie"
        onConfirm={() => {
          setConfirmLeave(false);
          goToBalance();
        }}
        onCancel={() => setConfirmLeave(false)}
      />
    </Modal>
  );
}
