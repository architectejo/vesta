import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { listChatChannels, type ChatChannel } from "../../../api/social";
import { EmptyState, Skeleton, useClubBranding } from "../../../design-system";
import { ConversationModal } from "./ConversationModal";

const CHANNEL_LABEL: Record<ChatChannel["channel_type"], { name: string; description: string }> = {
  general: { name: "Général", description: "Tous les joueurs du club" },
  board: { name: "Bureau", description: "Membres du bureau" },
};

function ChannelIcon({ type }: { type: ChatChannel["channel_type"] }) {
  if (type === "board") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.5}>
        <rect x="5" y="11" width="14" height="9" rx="1.5" />
        <path d="M8 11V8a4 4 0 018 0v3" />
      </svg>
    );
  }
  return (
    <span aria-hidden="true" className="text-lg font-semibold">
      #
    </span>
  );
}

function lastMessagePreview(channel: ChatChannel): string {
  const message = channel.last_message;
  if (!message) return "";
  const first = message.sender.first_name;
  return message.image_url && !message.body ? `${first} a envoyé une image` : `${first} : ${message.body}`;
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const today = new Date();
  const isToday = date.toDateString() === today.toDateString();
  return isToday
    ? new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(date)
    : new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit" }).format(date);
}

/** Page « Chat » (fil-public-communication.md, PARTIE C). */
export function ChatPage() {
  const branding = useClubBranding();
  const [openChannel, setOpenChannel] = useState<ChatChannel | null>(null);

  const query = useQuery({
    queryKey: ["social", "chat", "channels"],
    queryFn: listChatChannels,
    refetchInterval: () => (document.visibilityState === "hidden" ? false : 30_000),
  });

  return (
    <div className="mx-auto max-w-[640px] space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-text">Chat</h1>
        <p className="text-sm text-text-muted">
          {branding?.name ?? ""} · {query.data?.results.length ?? 0} canal{(query.data?.results.length ?? 0) > 1 ? "aux" : ""}
        </p>
      </header>

      <section className="rounded-lg bg-surface p-2 shadow-card">
        {query.isLoading ? (
          <div className="space-y-2 p-2">
            <Skeleton variant="row" />
            <Skeleton variant="row" />
          </div>
        ) : query.isError ? (
          <EmptyState variant="error" message="Impossible de charger les canaux." actionLabel="Réessayer" onAction={() => void query.refetch()} />
        ) : (
          <ul className="divide-y divide-border">
            {(query.data?.results ?? []).map((channel) => {
              const meta = CHANNEL_LABEL[channel.channel_type];
              return (
                <li key={channel.id}>
                  <button
                    type="button"
                    onClick={() => setOpenChannel(channel)}
                    className="flex min-h-16 w-full items-center gap-3 px-2 py-2 text-left hover:bg-surface-muted"
                  >
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-muted text-text-muted">
                      <ChannelIcon type={channel.channel_type} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-text">{meta.name}</p>
                      <p className="text-[13px] text-text-muted">{meta.description}</p>
                      {channel.last_message ? (
                        <p className="truncate text-[13px] text-text-muted">{lastMessagePreview(channel)}</p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      {channel.last_message ? (
                        <span className="text-[13px] text-text-muted">{formatWhen(channel.last_message.sent_at)}</span>
                      ) : null}
                      {channel.unread_count > 0 ? (
                        <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-[11px] font-medium text-on-primary">
                          {channel.unread_count > 99 ? "99+" : channel.unread_count}
                        </span>
                      ) : null}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {openChannel !== null ? <ConversationModal channel={openChannel} onClose={() => setOpenChannel(null)} /> : null}
    </div>
  );
}
