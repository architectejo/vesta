import { useState, type ReactNode } from "react";
import {
  getBoardSection,
  type BoardPeriodQuery,
  type BoardSectionKey,
  type PagedList,
} from "../../../api/clubBoardDashboard";
import { ApiError } from "../../../api/client";
import { Avatar, Button, EmptyState } from "../../../design-system";

/** Ligne de liste : texte à gauche, valeur facultative à droite (360 px : retour à la ligne, pas de défilement). */
export function Row({
  title,
  sub,
  right,
  avatar,
}: {
  title: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
  avatar?: ReactNode;
}) {
  return (
    <li className="flex items-center gap-3 py-2">
      {avatar}
      <div className="min-w-0 flex-1">
        <p className="break-words text-sm font-medium text-text">{title}</p>
        {sub ? <p className="break-words text-xs text-text-muted">{sub}</p> : null}
      </div>
      {right ? <div className="max-w-[50%] shrink-0 break-words text-right text-sm tabular-nums text-text">{right}</div> : null}
    </li>
  );
}

/** Ligne de joueur : photo avec repli sur les initiales. */
export function PlayerRow({
  name,
  photo,
  sub,
  right,
}: {
  name: string | null;
  photo: string | null | undefined;
  sub?: ReactNode;
  right?: ReactNode;
}) {
  const label = name ?? "Joueur";
  return <Row avatar={<Avatar name={label} photoUrl={photo ?? null} size={32} />} title={label} sub={sub} right={right} />;
}

export function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-1">
      <h3 className="text-base font-semibold text-text">{title}</h3>
      {children}
    </section>
  );
}

export function List({ children }: { children: ReactNode }) {
  return <ul className="divide-y divide-border">{children}</ul>;
}

interface PagedSectionProps<T> {
  title?: string;
  section: BoardSectionKey;
  period: BoardPeriodQuery | null;
  /** Nom de la liste dans la réponse (paramètre `only`). */
  name: string;
  list: PagedList<T>;
  limit: number;
  emptyMessage: string;
  renderItem: (item: T, index: number) => ReactNode;
}

/**
 * Liste paginée « Voir plus » : chaque clic envoie une nouvelle requête avec
 * `offset=next_offset` et `only=<nom de la liste>` (contrat de l'API). À
 * remonter avec une `key` quand la période change.
 */
export function PagedSection<T>({
  title,
  section,
  period,
  name,
  list,
  limit,
  emptyMessage,
  renderItem,
}: PagedSectionProps<T>) {
  const [items, setItems] = useState<T[]>(list.items);
  const [nextOffset, setNextOffset] = useState<number | null>(list.next_offset);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadMore() {
    if (nextOffset === null) return;
    setLoading(true);
    setError(null);
    try {
      const response = await getBoardSection(section, period, { limit, offset: nextOffset, only: name });
      const page = (response as unknown as Record<string, PagedList<T> | undefined>)[name];
      if (!page) throw new Error("Réponse inattendue.");
      setItems((current) => [...current, ...page.items]);
      setNextOffset(page.next_offset);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Impossible de charger la suite. Réessayez.");
    } finally {
      setLoading(false);
    }
  }

  const body =
    items.length === 0 ? (
      <EmptyState message={emptyMessage} />
    ) : (
      <>
        <List>{items.map((item, index) => renderItem(item, index))}</List>
        {error ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            {error}
          </p>
        ) : null}
        {nextOffset !== null ? (
          <div className="pt-2">
            <Button
              variant="secondary"
              size="sm"
              loading={loading}
              loadingLabel="Chargement…"
              onClick={() => void loadMore()}
            >
              {error ? "Réessayer" : "Voir plus"}
            </Button>
          </div>
        ) : null}
      </>
    );

  return title ? (
    <Block title={`${title} (${list.count})`}>{body}</Block>
  ) : (
    <div>{body}</div>
  );
}
