import { useEffect, useMemo, useState } from "react";
import type { PerformanceTest, PlayerBrief } from "../../../api/performance";
import { Avatar, Banner, Button, TextField } from "../../../design-system";
import type { ManualEntries } from "./chronoDraft";
import type { DraftItem } from "./measureTypes";
import { describeFields } from "./performanceFormat";
import { StepFooter } from "./StepFooter";
import { emptyDraft, readDraft, ValueInput, type ValueDraft } from "./ValueInput";

export interface ManualStepProps {
  test: PerformanceTest;
  players: PlayerBrief[];
  /** Message d'introduction (ex. « Temps écoulé. Saisissez la distance de chaque joueur. »). */
  intro?: string;
  onDirtyChange: (dirty: boolean) => void;
  onReview: (items: DraftItem[]) => void;
  /** Saisie restaurée d'une sauvegarde locale du chrono. */
  initial?: ManualEntries;
  /** Reçoit la saisie à chaque changement, pour la sauvegarde locale. */
  onSnapshot?: (entries: ManualEntries) => void;
}

/** Saisie manuelle de secours (C6.3) : une ligne par joueur, ligne vide = non mesuré. */
export function ManualStep({ test, players, intro, onDirtyChange, onReview, initial, onSnapshot }: ManualStepProps) {
  const [drafts, setDrafts] = useState<Record<number, ValueDraft>>(() => initial?.drafts ?? {});
  const [lapLength, setLapLength] = useState(() => initial?.lapLength ?? "");

  useEffect(() => {
    onSnapshot?.({ drafts, lapLength });
  }, [drafts, lapLength, onSnapshot]);

  const rows = useMemo(
    () =>
      players.map((player) => {
        const draft = drafts[player.membership_id] ?? emptyDraft();
        return { player, draft, read: readDraft(test, draft, lapLength) };
      }),
    [players, drafts, test, lapLength],
  );
  const filled = rows.filter((row) => row.read.state === "ok");
  const hasError = rows.some((row) => row.read.state === "error");
  const dirty = rows.some((row) => row.draft.text !== "" || row.draft.laps !== "" || row.draft.dnf);
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  function review() {
    const items: DraftItem[] = [];
    for (const row of rows) {
      if (row.read.state !== "ok") continue;
      items.push({
        membershipId: row.player.membership_id,
        name: row.player.name,
        attemptNo: 1,
        fields: row.read.fields,
        label: describeFields(test, row.read.fields),
      });
    }
    onReview(items);
  }

  return (
    <div className="space-y-3">
      {intro ? <Banner variant="info">{intro}</Banner> : null}
      {test.kind === "distance_in_time" ? (
        <TextField
          label="Longueur du tour (m)"
          value={lapLength}
          onChange={setLapLength}
          inputMode="decimal"
          optional
          help="Saisie une fois pour tous : tours × longueur du tour + mètres en plus."
        />
      ) : null}
      <p className="sticky top-0 z-10 -mx-4 bg-surface px-4 py-1 text-sm text-text-muted">
        {filled.length} résultat{filled.length > 1 ? "s" : ""} saisi{filled.length > 1 ? "s" : ""} sur {players.length}{" "}
        joueur{players.length > 1 ? "s" : ""}
      </p>
      <ul className="divide-y divide-border">
        {rows.map(({ player, draft, read }) => (
          <li key={player.membership_id} className="space-y-1 py-3">
            <div className="flex items-center gap-2">
              <Avatar name={player.name} photoUrl={player.photo} size={32} />
              <span className="min-w-0 break-words text-sm font-medium text-text">{player.name}</span>
            </div>
            <ValueInput
              test={test}
              name={player.name}
              draft={draft}
              lapLength={lapLength}
              error={read.state === "error" ? read.message : undefined}
              onChange={(next) => setDrafts({ ...drafts, [player.membership_id]: next })}
            />
          </li>
        ))}
      </ul>
      <StepFooter>
        <Button variant="primary" className="w-full" disabled={filled.length === 0 || hasError} onClick={review}>
          Envoyer les mesures ({filled.length})
        </Button>
      </StepFooter>
    </div>
  );
}
