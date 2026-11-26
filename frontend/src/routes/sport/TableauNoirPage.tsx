import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { getMyProfile, listClubPlayers, type ClubPlayerListItem } from "../../api/clubs";
import {
  addAnnotation,
  deleteTacticalPlan,
  getMatch,
  getTacticalPlan,
  placeOnPlan,
  publishTacticalPlan,
  removeAnnotation,
  removePlacement,
  updateTacticalPlanSettings,
  type Annotation,
  type AnnotationInput,
  type Placement,
} from "../../api/sport";
import {
  Banner,
  Button,
  ConfirmDialog,
  EmptyState,
  FORMATION_LABELS,
  IconBack,
  IconButton,
  IconMore,
  IconRedo,
  IconUndo,
  Loader,
  Modal,
  PitchBoard,
  PitchDragGhost,
  PitchPin,
  slotsForFormation,
  StatusBadge,
  Tabs,
  type FormationSlot,
  type PitchAnnotationData,
  type PitchPinData,
  useToast,
} from "../../design-system";
import { useClosingState } from "../../hooks/useClosingState";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { ChoosePlayerModal } from "./ChoosePlayerModal";
import { ConsigneModal } from "./ConsigneModal";
import { DuplicatePlanModal } from "./DuplicatePlanModal";
import { NumberPositionModal } from "./NumberPositionModal";
import { PlanFormModal } from "./PlanFormModal";
import { PlayerCardModal } from "./PlayerCardModal";
import { shortLabel } from "./pinLayout";
import { getSportAccess } from "./sportAccess";

type Tool = "select" | "arrow" | "zone" | "text" | "eraser";

interface HistoryEntry {
  id: string;
  kind: "create" | "delete";
  data: AnnotationInput;
  annotationId: number;
}

function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

function annotationToInput(a: Annotation): AnnotationInput {
  return {
    annotation_type: a.annotation_type,
    path_data: a.path_data,
    text: a.text,
    target_membership_id: a.target_membership_id,
    target_line: a.target_line || "",
  };
}

/**
 * Tableau noir (docs/ecrans/sport-plan-tactique.md §5) : page d'édition,
 * exception documentée à la règle des modales (10.2 n° 32). Réservée au
 * Coach.
 *
 * **Écarts signalés au compte rendu** (voir aussi `MatchComposeModal.tsx`) :
 * - le banc affiche tout l'effectif actif sans pré-grisage des joueurs
 *   non éligibles (aucun endpoint d'éligibilité groupée) ; le refus reste
 *   entièrement fait par le service au moment du placement, avec le
 *   message renvoyé affiché tel quel ;
 * - « Modifier le numéro et le poste » depuis le banc (§5.2) n'est pas
 *   proposé : ce formulaire modifie un `TacticalPlanPlacement`, qui
 *   n'existe pas pour un joueur non encore placé — action disponible
 *   uniquement depuis un pion déjà sur le terrain, cohérent avec le
 *   contrat d'API vérifié ;
 * - le passage automatique de la formation en « Personnalisée » lors d'un
 *   déplacement libre (hors emplacement) n'écrit aucune métadonnée : la
 *   formation ne change que depuis « Paramètres du plan », pour ne
 *   jamais modifier silencieusement une donnée non demandée explicitement.
 *
 * **Disposition (retour direct, remarques.md, Lot 3)** : à partir de
 * 768 px, deux colonnes — le terrain et la barre d'outils à gauche, le
 * banc et les consignes (onglets) à droite, plus un résumé de la
 * composition du match rattaché (lecture seule, lien vers `MatchPage`).
 * En dessous de 768 px, une seule colonne, dans l'ordre du §7.1 (terrain,
 * banc, barre d'outils). Le terrain reste en mode portrait à tous les
 * gabarits dans cette page (le §7.4 demande un terrain paysage à partir
 * de 768 px ; non fait ici pour ne pas toucher aux calculs de
 * coordonnées du dessin, voir le compte rendu).
 */
export function TableauNoirPage() {
  const { id } = useParams();
  const planId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const online = useOnlineStatus();

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const access = getSportAccess(profileQuery.data?.roles);

  const planQuery = useQuery({
    queryKey: ["sport", "tactical-plan", planId],
    queryFn: () => getTacticalPlan(planId),
    enabled: Number.isFinite(planId),
    refetchInterval: 15_000,
  });

  const rosterQuery = useQuery({
    queryKey: ["clubs", "players", "active"],
    queryFn: () => listClubPlayers({ status: "active" }),
  });

  // Composition du match rattaché (§7.4 : « les autres détails » de la
  // colonne de droite). Lecture seule ici, avec un lien vers `MatchPage`,
  // qui reste seul propriétaire de la gestion de la composition (4.8) —
  // on ne duplique pas cette logique.
  const matchId = planQuery.data?.match_id ?? null;
  const matchQuery = useQuery({
    queryKey: ["sport", "match", matchId],
    queryFn: () => getMatch(matchId as number),
    enabled: matchId != null,
  });

  // Disposition en deux colonnes à partir de 768 px (remarques.md, Lot 3 :
  // « à gauche le plan tactique, à droite la liste des joueurs et les
  // autres détails »). En dessous, l'ordre reste celui du §7.1 (terrain,
  // banc, barre d'outils).
  const isDesktop = useMediaQuery("(min-width: 768px)");
  const [rightTab, setRightTab] = useState<"bench" | "consignes">("bench");

  const [tool, setTool] = useState<Tool>("select");
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const [benchSearch, setBenchSearch] = useState("");
  const [benchPositionFilter, setBenchPositionFilter] = useState<"all" | "goalkeeper" | "defender" | "midfielder" | "forward">("all");
  const [armedBenchId, setArmedBenchId] = useState<number | null>(null);
  const [choosePlayerSlot, setChoosePlayerSlot] = useState<FormationSlot | null>(null);
  const [numberPositionTarget, setNumberPositionTarget] = useState<Placement | null>(null);
  const [consigneModal, setConsigneModal] = useState<{ open: boolean; existing?: Annotation | null; point?: { x: number; y: number } | null }>({
    open: false,
  });
  const [pinMenuTarget, setPinMenuTarget] = useState<Placement | null>(null);
  const [benchMenuTarget, setBenchMenuTarget] = useState<ClubPlayerListItem | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [duplicateOpen, setDuplicateOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [publishConfirm, setPublishConfirm] = useState(false);
  const [consignesPanelOpen, setConsignesPanelOpen] = useState(false);
  const [cardMembershipId, setCardMembershipId] = useState<number | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const { mounted: menuMounted, dataState: menuDataState, onAnimationEnd: onMenuAnimationEnd } =
    useClosingState(menuOpen, 200);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const pitchWrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!profileQuery.isLoading && !access.isCoach) {
      navigate("/vestiaire?onglet=plans", { replace: true });
    }
  }, [profileQuery.isLoading, access.isCoach, navigate]);

  const [undoStack, setUndoStack] = useState<HistoryEntry[]>([]);
  const [redoStack, setRedoStack] = useState<HistoryEntry[]>([]);

  const plan = planQuery.data;
  const slots = plan ? slotsForFormation(plan.formation, plan.squad_size) : [];

  const placedIds = useMemo(() => new Set((plan?.placements ?? []).map((p) => p.membership_id).filter((v): v is number => v != null)), [plan]);

  const bench = (rosterQuery.data ?? []).filter((p) => !placedIds.has(p.membership_id));
  const filteredBench = bench.filter((p) => {
    if (benchPositionFilter !== "all" && p.position !== benchPositionFilter) return false;
    if (!benchSearch.trim()) return true;
    const q = benchSearch.trim().toLowerCase();
    return `${p.first_name} ${p.last_name}`.toLowerCase().includes(q) || String(p.jersey_number ?? "").includes(q);
  });

  const ineligiblePlaced = (plan?.placements ?? []).filter((p) => p.no_longer_eligible);

  function occupiedSlotFor(placement: Placement): FormationSlot | undefined {
    return slots.find((s) => Math.abs(s.x - Number(placement.x_coord)) < 3 && Math.abs(s.y - Number(placement.y_coord)) < 3);
  }

  const occupiedSlotIds = new Set((plan?.placements ?? []).map((p) => occupiedSlotFor(p)?.id).filter(Boolean));

  async function invalidate(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["sport", "tactical-plan", planId] });
  }

  function nearestFreeSlot(x: number, y: number): FormationSlot | null {
    let best: FormationSlot | null = null;
    let bestDist = Infinity;
    for (const slot of slots) {
      if (occupiedSlotIds.has(slot.id)) continue;
      const dist = Math.hypot(slot.x - x, slot.y - y);
      if (dist < 8 && dist < bestDist) {
        best = slot;
        bestDist = dist;
      }
    }
    return best;
  }

  function occupantAt(x: number, y: number): Placement | null {
    return (plan?.placements ?? []).find((p) => Math.abs(Number(p.x_coord) - x) < 4 && Math.abs(Number(p.y_coord) - y) < 4) ?? null;
  }

  async function place(membershipId: number, x: number, y: number, occupant?: Placement | null): Promise<void> {
    setSaveState("saving");
    try {
      if (occupant && occupant.membership_id !== membershipId) {
        await removePlacement(occupant.id);
      }
      await placeOnPlan(planId, { membership_id: membershipId, x_coord: x, y_coord: y });
      await invalidate();
      setSaveState("saved");
    } catch (error) {
      setSaveState("error");
      showToast(error instanceof ApiError ? `${error.detail}` : "Modification non enregistrée. Réessayez.");
    }
  }

  async function handleDropOnPitch(membershipId: number, x: number, y: number): Promise<void> {
    const slot = nearestFreeSlot(x, y);
    const target = slot ?? { x, y };
    const occupant = occupantAt(target.x, target.y);
    await place(membershipId, target.x, target.y, occupant);
  }

  async function handleRemoveFromPlan(placement: Placement): Promise<void> {
    setSaveState("saving");
    try {
      await removePlacement(placement.id);
      await invalidate();
      setSaveState("saved");
      showToast(`${placement.player?.name ?? "Joueur"} retiré du terrain.`);
    } catch (error) {
      setSaveState("error");
      showToast(error instanceof ApiError ? error.detail : "Retrait impossible.");
    }
  }

  async function pushAnnotation(input: AnnotationInput): Promise<void> {
    setSaveState("saving");
    try {
      const created = await addAnnotation(planId, input);
      await invalidate();
      setSaveState("saved");
      setUndoStack((s) => [...s.slice(-19), { id: crypto.randomUUID(), kind: "create", data: input, annotationId: created.id }]);
      setRedoStack([]);
    } catch (error) {
      setSaveState("error");
      showToast(error instanceof ApiError ? error.detail : "Modification non enregistrée. Réessayez.");
    }
  }

  async function eraseAnnotation(annotation: Annotation): Promise<void> {
    setSaveState("saving");
    try {
      await removeAnnotation(annotation.id);
      await invalidate();
      setSaveState("saved");
      setUndoStack((s) => [...s.slice(-19), { id: crypto.randomUUID(), kind: "delete", data: annotationToInput(annotation), annotationId: annotation.id }]);
      setRedoStack([]);
      showToast("Élément effacé.");
    } catch (error) {
      setSaveState("error");
      showToast(error instanceof ApiError ? error.detail : "Suppression impossible.");
    }
  }

  async function handleUndo(): Promise<void> {
    const last = undoStack[undoStack.length - 1];
    if (!last) return;
    setUndoStack((s) => s.slice(0, -1));
    if (last.kind === "create") {
      await removeAnnotation(last.annotationId);
      setRedoStack((s) => [...s, last]);
    } else {
      const created = await addAnnotation(planId, last.data);
      setRedoStack((s) => [...s, { ...last, annotationId: created.id }]);
    }
    await invalidate();
  }

  async function handleRedo(): Promise<void> {
    const last = redoStack[redoStack.length - 1];
    if (!last) return;
    setRedoStack((s) => s.slice(0, -1));
    if (last.kind === "create") {
      const created = await addAnnotation(planId, last.data);
      setUndoStack((s) => [...s, { ...last, annotationId: created.id }]);
    } else {
      await removeAnnotation(last.annotationId);
      setUndoStack((s) => [...s, last]);
    }
    await invalidate();
  }

  function handleSurfacePointerDown(event: ReactPointerEvent<HTMLDivElement>): void {
    if (tool !== "arrow" && tool !== "zone") return;
    const rect = pitchWrapRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    const y = 100 - ((event.clientY - rect.top) / rect.height) * 100;
    setDrawStart({ x, y });
  }

  function handleSurfacePointerUp(event: ReactPointerEvent<HTMLDivElement>): void {
    if (!drawStart || (tool !== "arrow" && tool !== "zone")) return;
    const rect = pitchWrapRef.current?.getBoundingClientRect();
    if (!rect) {
      setDrawStart(null);
      return;
    }
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    const y = 100 - ((event.clientY - rect.top) / rect.height) * 100;
    const dist = Math.hypot(x - drawStart.x, y - drawStart.y);
    setDrawStart(null);
    if (dist < 2) return; // tracé involontaire (< 12 px environ, §5.4)
    void pushAnnotation({
      annotation_type: tool,
      path_data: JSON.stringify([drawStart, { x, y }]),
      text: "",
    });
  }

  function handleSurfaceClick(event: ReactMouseEvent<HTMLDivElement>): void {
    if (tool !== "text") return;
    const rect = pitchWrapRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    const y = 100 - ((event.clientY - rect.top) / rect.height) * 100;
    setConsigneModal({ open: true, existing: null, point: { x, y } });
  }

  if (profileQuery.isLoading || planQuery.isLoading || rosterQuery.isLoading) {
    return <Loader loading variant="page" />;
  }
  if (!access.isCoach) {
    return null;
  }
  if (planQuery.isError || !plan) {
    return <EmptyState variant="error" message="Impossible de charger le plan." actionLabel="Réessayer" onAction={() => void planQuery.refetch()} />;
  }

  const pins: PitchPinData[] = plan.placements
    .filter((p) => p.membership_id != null)
    .map((p) => ({
      id: String(p.id),
      membershipId: p.membership_id as number,
      label: shortLabel(p.player?.name ?? ""),
      number: p.jersey_number_override ?? p.player?.jersey_number ?? null,
      photoUrl: p.player?.photo ?? null,
      fullName: p.player?.name,
      x: Number(p.x_coord),
      y: Number(p.y_coord),
      locked: Boolean(p.no_longer_eligible),
    }));

  const boardSlots = slots.map((s) => ({ id: s.id, x: s.x, y: s.y, abbrev: s.abbrev, occupied: occupiedSlotIds.has(s.id) }));

  const annotationsForBoard: PitchAnnotationData[] = plan.annotations
    .filter((a) => a.annotation_type !== "note")
    .map((a) => {
      let points: Array<{ x: number; y: number }> = [];
      try {
        const parsed = JSON.parse(a.path_data || "[]");
        if (Array.isArray(parsed)) points = parsed;
      } catch {
        points = [];
      }
      return { id: String(a.id), type: a.annotation_type, points, text: a.text };
    });

  const noteAnnotations = plan.annotations.filter((a) => a.annotation_type === "note");
  const lineNotes = noteAnnotations.filter((a) => a.target_line);
  const playerNotes = noteAnnotations.filter((a) => a.target_membership_id);
  const freeNotes = noteAnnotations.filter((a) => !a.target_line && !a.target_membership_id);

  function handleTapSlot(boardSlot: { id: string; x: number; y: number; abbrev: string; occupied?: boolean }): void {
    if (boardSlot.occupied) return;
    const fullSlot = slots.find((s) => s.id === boardSlot.id) ?? null;
    if (!fullSlot) return;
    if (armedBenchId != null) {
      void place(armedBenchId, fullSlot.x, fullSlot.y);
      setArmedBenchId(null);
      return;
    }
    setChoosePlayerSlot(fullSlot);
  }

  function handleTapPin(pin: PitchPinData): void {
    if (!plan) return;
    const placement = plan.placements.find((p) => String(p.id) === pin.id) ?? null;
    if (!placement) return;
    if (tool === "eraser") return;
    setPinMenuTarget(placement);
  }

  // Terrain (colonne de gauche, §5.1 point 3). Contraint en largeur à
  // partir de 768 px pour ne jamais déborder du cadre de la page une fois
  // la colonne de droite ajoutée (remarques.md, Lot 3).
  const pitchBlock = (
    <div
      ref={pitchWrapRef}
      onPointerDown={handleSurfacePointerDown}
      onPointerUp={handleSurfacePointerUp}
      onClick={handleSurfaceClick}
      className={[
        "mx-auto w-full",
        isDesktop ? "max-w-[440px] lg:max-w-[500px]" : "",
        tool === "arrow" || tool === "zone" ? "touch-none" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <PitchBoard
        mode="tactic"
        ariaLabel={plan.name}
        pins={pins}
        slots={boardSlots}
        annotations={annotationsForBoard}
        dropZoneKey={online && tool === "select" ? "tactic-pitch" : undefined}
        onDropPlayer={(item, x, y) => void handleDropOnPitch(item.data.membershipId, x, y)}
        onTapSlot={handleTapSlot}
        onTapPin={handleTapPin}
        pinsDraggable={online && tool === "select"}
        pinsInteractive={online && tool === "select"}
      />
    </div>
  );

  // Repères visuels au-dessus du terrain (constat du client, référence
  // externe : l'état se lit d'un coup d'œil) — même badge que les terrains
  // de Séance/Vestiaire (`TeamFieldPanel.tsx`), pour rester cohérent.
  const pitchBadgesBlock = (
    <div className="mx-auto flex w-full flex-wrap items-center justify-center gap-1.5 text-xs font-medium text-text sm:max-w-[440px] lg:max-w-[500px]">
      <span className="inline-flex h-6 items-center rounded-full bg-surface-muted px-2">
        Système : {FORMATION_LABELS[plan.formation]}
      </span>
      <span className="inline-flex h-6 items-center rounded-full bg-surface-muted px-2">
        {pins.length}/{slots.length} postes pourvus
      </span>
    </div>
  );

  // Banc (§5.1 point 4) : liste des joueurs, avec recherche et puces de
  // poste. Colonne de droite à partir de 768 px, sous le terrain en
  // dessous de 768 px.
  const benchBlock = (
    <div className="rounded-md border border-border p-2">
      <div className="mb-2 flex items-center gap-2">
        <input
          type="text"
          placeholder="Nom ou numéro"
          value={benchSearch}
          onChange={(e) => setBenchSearch(e.target.value)}
          className="h-9 flex-1 rounded-sm border border-border-strong bg-surface px-3 text-sm"
        />
      </div>
      <div className="mb-2 flex flex-wrap gap-1">
        {(["all", "goalkeeper", "defender", "midfielder", "forward"] as const).map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={benchPositionFilter === value}
            onClick={() => setBenchPositionFilter(value)}
            className={[
              "h-control-sm rounded-full border px-3 text-xs font-medium",
              benchPositionFilter === value ? "border-primary bg-primary text-on-primary" : "border-border-strong bg-surface text-text",
            ].join(" ")}
          >
            {value === "all" ? "Tous" : value === "goalkeeper" ? "GB" : value === "defender" ? "DEF" : value === "midfielder" ? "MIL" : "ATT"}
          </button>
        ))}
      </div>
      {filteredBench.length === 0 ? (
        <EmptyState message={bench.length === 0 ? "Tous les joueurs disponibles sont sur le terrain." : "Aucun joueur dans ce filtre."} />
      ) : (
        <div className={isDesktop ? "flex flex-col gap-2" : "flex gap-3 overflow-x-auto pb-1"}>
          {filteredBench.map((player) => (
            <PitchPin
              key={player.membership_id}
              vertical
              standalone
              draggable={online && tool === "select"}
              dragKind="bench-player"
              pin={{
                id: String(player.membership_id),
                membershipId: player.membership_id,
                label: shortLabel(`${player.first_name} ${player.last_name}`),
                number: player.jersey_number,
                photoUrl: player.photo,
                fullName: `${player.first_name} ${player.last_name}`,
                x: 50,
                y: 50,
              }}
              onTap={() => setBenchMenuTarget(player)}
            />
          ))}
        </div>
      )}
    </div>
  );

  // Barre d'outils (§5.1 point 5). Reste attenante au terrain dans la
  // colonne de gauche à tous les gabarits.
  const toolbarBlock = (
    <div className="sticky bottom-0 flex flex-wrap items-center gap-1 border-t border-border bg-surface py-2">
      {(
        [
          { value: "select", label: "Placer" },
          { value: "arrow", label: "Flèche" },
          { value: "zone", label: "Zone" },
          { value: "text", label: "Texte" },
          { value: "eraser", label: "Gomme" },
        ] as Array<{ value: Tool; label: string }>
      ).map((item) => (
        <button
          key={item.value}
          type="button"
          aria-label={item.label}
          aria-pressed={tool === item.value}
          onClick={() => setTool(item.value)}
          className={[
            "h-10 rounded-sm border px-3 text-sm font-medium",
            tool === item.value ? "border-primary bg-primary text-on-primary" : "border-border-strong bg-surface text-text",
          ].join(" ")}
        >
          {item.label}
        </button>
      ))}
      <IconButton aria-label="Annuler" disabled={undoStack.length === 0} onClick={() => void handleUndo()} icon={<IconUndo aria-hidden="true" className="h-5 w-5" />} />
      <IconButton aria-label="Rétablir" disabled={redoStack.length === 0} onClick={() => void handleRedo()} icon={<IconRedo aria-hidden="true" className="h-5 w-5" />} />
      <Button
        size="sm"
        variant="ghost"
        onClick={() => (isDesktop ? setRightTab("consignes") : setConsignesPanelOpen((v) => !v))}
      >
        Consignes ({noteAnnotations.length})
      </Button>
    </div>
  );

  const eraserListBlock =
    tool === "eraser" && annotationsForBoard.length > 0 ? (
      <ul className="space-y-1">
        {plan.annotations
          .filter((a) => a.annotation_type !== "note")
          .map((a) => (
            <li key={a.id}>
              <button type="button" className="inline-flex min-h-control-sm items-center text-sm text-status-danger-fg hover:underline" onClick={() => void eraseAnnotation(a)}>
                Effacer {a.annotation_type === "arrow" ? "la flèche" : "la zone"} n° {a.id}
              </button>
            </li>
          ))}
      </ul>
    ) : null;

  // Consignes (§4.6) : « les autres détails » de la colonne de droite.
  const consignesBlock = (
    <div className="rounded-md border border-border p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text">Consignes</h2>
        <Button size="sm" variant="secondary" onClick={() => setConsigneModal({ open: true, existing: null })}>
          Ajouter une consigne
        </Button>
      </div>
      {noteAnnotations.length === 0 ? (
        <EmptyState message="Aucune consigne." />
      ) : (
        <ul className="space-y-2">
          {[...lineNotes, ...playerNotes, ...freeNotes].map((note) => (
            <li key={note.id}>
              <button
                type="button"
                className="inline-flex min-h-control-sm items-center text-left text-sm text-text hover:underline"
                onClick={() => setConsigneModal({ open: true, existing: note })}
              >
                {note.target_line ? `${note.target_line} : ` : note.target_membership_id ? "Joueur : " : ""}
                {note.text}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  const showBench = !isDesktop || rightTab === "bench";
  const showConsignes = isDesktop ? rightTab === "consignes" : consignesPanelOpen;

  // Composition du match rattaché (§7.4, remarques.md : « la composition »).
  // Lecture seule ici ; la gestion (composer, retirer, publier) reste dans
  // `MatchPage`, dont on réutilise l'API (`getMatch`) sans dupliquer la
  // logique d'affichage détaillée de `CompositionCard`.
  const compositionSummary = plan.match_id ? (
    <section className="rounded-md border border-border p-3">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-text">Composition du match</h2>
        {matchQuery.data ? (
          <StatusBadge status={matchQuery.data.is_composition_published ? "lineup_published" : "lineup_draft"} />
        ) : null}
      </div>
      {matchQuery.isLoading ? (
        <Loader loading variant="list" count={2} />
      ) : matchQuery.isError || !matchQuery.data ? (
        <EmptyState variant="error" message="Composition du match non disponible." />
      ) : matchQuery.data.starters.length + matchQuery.data.substitutes.length === 0 ? (
        <EmptyState
          message="Aucune composition pour l'instant."
          actionLabel="Voir le match"
          onAction={() => navigate(`/matchs/${plan.match_id}`)}
        />
      ) : (
        <>
          <p className="mb-2 text-sm text-text-muted">
            {matchQuery.data.starters.length} titulaire(s) · {matchQuery.data.substitutes.length} remplaçant(s)
          </p>
          <Button size="sm" variant="ghost" onClick={() => navigate(`/matchs/${plan.match_id}`)}>
            Voir la composition du match
          </Button>
        </>
      )}
    </section>
  ) : null;

  return (
    <div className="space-y-3">
      <p className="hidden text-xs text-text-muted sm:block">
        {profileQuery.data?.club.name} · {FORMATION_LABELS[plan.formation]}
        {plan.match_id ? ` · Match n° ${plan.match_id}` : ""}
      </p>
      <div className="flex h-12 items-center gap-2">
        <IconButton aria-label="Retour aux plans" onClick={() => navigate("/vestiaire?onglet=plans")} icon={<IconBack aria-hidden="true" className="h-5 w-5" />} />
        <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-text">{plan.name}</h1>
        <span className="shrink-0 text-xs text-text-muted">
          {saveState === "saved" ? "Enregistré" : saveState === "saving" ? "Enregistrement…" : "Non enregistré"}
        </span>
        {!plan.is_published ? (
          <Button size="sm" variant="primary" disabled={ineligiblePlaced.length > 0} onClick={() => setPublishConfirm(true)}>
            Publier
          </Button>
        ) : (
          <span className="shrink-0 rounded-full bg-status-success-bg px-2 py-0.5 text-xs text-status-success-fg">Publié</span>
        )}
        <div className="relative">
          <IconButton aria-label="Plus d'actions" onClick={() => setMenuOpen((v) => !v)} icon={<IconMore aria-hidden="true" className="h-5 w-5" />} />
          {menuMounted ? (
            <div
              data-state={menuDataState}
              onAnimationEnd={onMenuAnimationEnd}
              className="vesta-anim-menu absolute right-0 z-20 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated"
            >
              <button className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-muted" onClick={() => { setMenuOpen(false); setSettingsOpen(true); }}>
                Paramètres du plan
              </button>
              <button className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-muted" onClick={() => { setMenuOpen(false); setDuplicateOpen(true); }}>
                Dupliquer
              </button>
              <button className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-muted" onClick={() => { setMenuOpen(false); setDeleteConfirm(true); }}>
                Supprimer le plan
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {ineligiblePlaced.length > 0 ? (
        <Banner variant="danger">
          {ineligiblePlaced.length} joueur(s) placé(s) ne peuvent plus jouer. Remplacez-les avant de publier.
        </Banner>
      ) : null}
      {!online ? <Banner variant="info">Vous êtes hors connexion. Le tableau noir est en lecture seule jusqu'au retour du réseau.</Banner> : null}

      {armedBenchId != null ? (
        <Banner variant="info" action={<Button size="sm" variant="ghost" onClick={() => setArmedBenchId(null)}>Annuler</Button>}>
          Touchez un emplacement libre pour placer ce joueur.
        </Banner>
      ) : null}

      {compositionSummary}

      {isDesktop ? (
        <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(0,1fr)_280px] lg:grid-cols-[minmax(0,1fr)_300px]">
          {/* Colonne de gauche : le plan tactique */}
          <div className="min-w-0 space-y-2">
            {pitchBadgesBlock}
            {pitchBlock}
            <PitchDragGhost />
            {toolbarBlock}
            {eraserListBlock}
          </div>

          {/* Colonne de droite : la liste des joueurs et les autres détails */}
          <div className="min-w-0 space-y-3">
            <Tabs
              items={[
                { value: "bench", label: "Banc" },
                { value: "consignes", label: `Consignes (${noteAnnotations.length})` },
              ]}
              value={rightTab}
              onChange={setRightTab}
              label="Panneau du tableau noir"
            />
            {showBench ? benchBlock : null}
            {showConsignes ? consignesBlock : null}
          </div>
        </div>
      ) : (
        // Moins de 768 px : une seule colonne, dans l'ordre du §7.1
        // (terrain, banc, barre d'outils).
        <div className="space-y-3">
          {pitchBadgesBlock}
          {pitchBlock}
          <PitchDragGhost />
          {benchBlock}
          {toolbarBlock}
          {eraserListBlock}
          {showConsignes ? consignesBlock : null}
        </div>
      )}

      {/* Modales */}

      <ChoosePlayerModal
        open={choosePlayerSlot !== null}
        slot={choosePlayerSlot}
        placements={plan.placements}
        onClose={() => setChoosePlayerSlot(null)}
        onChoose={(membershipId) => {
          if (choosePlayerSlot) {
            const occupant = occupantAt(choosePlayerSlot.x, choosePlayerSlot.y);
            void place(membershipId, choosePlayerSlot.x, choosePlayerSlot.y, occupant);
          }
          setChoosePlayerSlot(null);
        }}
      />

      <NumberPositionModal
        open={numberPositionTarget !== null}
        placement={numberPositionTarget}
        onClose={() => setNumberPositionTarget(null)}
        onUpdated={(warning) => {
          setNumberPositionTarget(null);
          void invalidate();
          showToast(warning ? `Numéro et poste mis à jour. ${warning}` : "Numéro et poste mis à jour.");
        }}
      />

      <ConsigneModal
        key={consigneModal.existing?.id ?? "new"}
        open={consigneModal.open}
        planId={planId}
        placements={plan.placements}
        existing={consigneModal.existing}
        initialPoint={consigneModal.point}
        onClose={() => setConsigneModal({ open: false })}
        onSaved={() => {
          setConsigneModal({ open: false });
          void invalidate();
          showToast("Consigne ajoutée.");
        }}
        onDeleted={() => {
          setConsigneModal({ open: false });
          void invalidate();
        }}
      />

      <Modal open={pinMenuTarget !== null} onClose={() => setPinMenuTarget(null)} title={pinMenuTarget?.player?.name ?? ""} size="sm" hideFooter>
        {pinMenuTarget ? (
          pinMenuTarget.no_longer_eligible ? (
            <div className="space-y-2">
              <p className="text-sm text-text">Ne peut plus jouer : {pinMenuTarget.no_longer_eligible.reason}</p>
              <Button variant="secondary" className="w-full" onClick={() => { setChoosePlayerSlot(occupiedSlotFor(pinMenuTarget) ?? { id: "free", x: Number(pinMenuTarget.x_coord), y: Number(pinMenuTarget.y_coord), abbrev: "", positionKind: "goalkeeper" }); setPinMenuTarget(null); }}>
                Changer de joueur
              </Button>
              <Button variant="ghost" className="w-full" onClick={() => { void handleRemoveFromPlan(pinMenuTarget); setPinMenuTarget(null); }}>
                Retirer du terrain
              </Button>
              <Button variant="ghost" className="w-full" onClick={() => { setCardMembershipId(pinMenuTarget.membership_id); setPinMenuTarget(null); }}>
                Voir la fiche du joueur
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              <Button variant="secondary" className="w-full" onClick={() => { setChoosePlayerSlot(occupiedSlotFor(pinMenuTarget) ?? { id: "free", x: Number(pinMenuTarget.x_coord), y: Number(pinMenuTarget.y_coord), abbrev: "", positionKind: "goalkeeper" }); setPinMenuTarget(null); }}>
                Changer de joueur
              </Button>
              <Button variant="ghost" className="w-full" onClick={() => { void handleRemoveFromPlan(pinMenuTarget); setPinMenuTarget(null); }}>
                Retirer du terrain
              </Button>
              <Button variant="ghost" className="w-full" onClick={() => { setNumberPositionTarget(pinMenuTarget); setPinMenuTarget(null); }}>
                Modifier le numéro et le poste
              </Button>
              <Button variant="ghost" className="w-full" onClick={() => { setConsigneModal({ open: true, existing: playerNotes.find((n) => n.target_membership_id === pinMenuTarget.membership_id) ?? null }); setPinMenuTarget(null); }}>
                Consigne pour ce joueur
              </Button>
              <Button variant="ghost" className="w-full" onClick={() => { setCardMembershipId(pinMenuTarget.membership_id); setPinMenuTarget(null); }}>
                Voir la fiche du joueur
              </Button>
            </div>
          )
        ) : null}
      </Modal>

      <Modal
        open={benchMenuTarget !== null}
        onClose={() => setBenchMenuTarget(null)}
        title={benchMenuTarget ? `${benchMenuTarget.first_name} ${benchMenuTarget.last_name}` : ""}
        size="sm"
        hideFooter
      >
        {benchMenuTarget ? (
          <div className="space-y-2">
            <Button
              variant="secondary"
              className="w-full"
              onClick={() => {
                setArmedBenchId(benchMenuTarget.membership_id);
                setBenchMenuTarget(null);
              }}
            >
              Placer sur le terrain
            </Button>
            <Button variant="ghost" className="w-full" onClick={() => { setCardMembershipId(benchMenuTarget.membership_id); setBenchMenuTarget(null); }}>
              Voir la fiche du joueur
            </Button>
          </div>
        ) : null}
      </Modal>

      <PlanFormModal
        open={settingsOpen}
        mode="settings"
        initial={{ name: plan.name, formation: plan.formation, squadSize: plan.squad_size, matchId: plan.match_id }}
        onClose={() => setSettingsOpen(false)}
        onSubmit={async (input) => {
          const formationChanged = input.formation !== plan.formation || input.squad_size !== plan.squad_size;
          await updateTacticalPlanSettings(planId, input);
          if (formationChanged) {
            const newSlots = slotsForFormation(input.formation, input.squad_size);
            const used = new Set<string>();
            for (const placement of plan.placements) {
              if (!placement.membership_id) continue;
              if (placement.no_longer_eligible) {
                await removePlacement(placement.id);
                continue;
              }
              const kind = placement.position_override || placement.player?.position;
              const match = newSlots.find((s) => !used.has(s.id) && s.positionKind === kind);
              if (match) {
                used.add(match.id);
                await placeOnPlan(planId, { membership_id: placement.membership_id, x_coord: match.x, y_coord: match.y });
              } else {
                await removePlacement(placement.id);
              }
            }
          }
          setSettingsOpen(false);
          await invalidate();
          showToast("Plan mis à jour.");
        }}
      />

      <DuplicatePlanModal
        open={duplicateOpen}
        planId={planId}
        planName={plan.name}
        onClose={() => setDuplicateOpen(false)}
        onDuplicated={(newPlanId, skippedCount) => {
          setDuplicateOpen(false);
          showToast(skippedCount > 0 ? `Plan dupliqué. ${skippedCount} joueur(s) indisponible(s) n'ont pas été recopiés.` : "Plan dupliqué.");
          navigate(`/plans/${newPlanId}/tableau`);
        }}
      />

      <ConfirmDialog
        open={deleteConfirm}
        title={`Supprimer le plan « ${plan.name} » ?`}
        description="Il ne sera plus visible par les joueurs et ne pourra pas être récupéré."
        confirmLabel="Supprimer"
        onConfirm={async () => {
          await deleteTacticalPlan(planId);
          setDeleteConfirm(false);
          showToast("Plan supprimé.");
          navigate("/vestiaire?onglet=plans");
        }}
        onCancel={() => setDeleteConfirm(false)}
      />

      <ConfirmDialog
        open={publishConfirm}
        title={`Publier le plan « ${plan.name} » ?`}
        description="Tous les joueurs du club pourront le consulter en lecture seule, après connexion."
        confirmLabel="Publier"
        danger={false}
        onConfirm={async () => {
          await publishTacticalPlan(planId);
          setPublishConfirm(false);
          await invalidate();
          showToast("Plan publié.");
        }}
        onCancel={() => setPublishConfirm(false)}
      />

      <PlayerCardModal open={cardMembershipId !== null} membershipId={cardMembershipId} onClose={() => setCardMembershipId(null)} />
    </div>
  );
}
