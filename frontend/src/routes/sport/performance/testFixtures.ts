import type { MyProfile } from "../../../api/clubs";
import type {
  BulkPerformanceResponse,
  EventPerformanceResults,
  PerformanceResultDetail,
  PerformanceResultRow,
  PerformanceTest,
  PerformanceValue,
  PlayerBrief,
} from "../../../api/performance";

export function brief(id: number, name: string, jersey: number | null = id): PlayerBrief {
  return { membership_id: id, name, jersey_number: jersey, position: "midfielder", position_label: "Milieu", photo: null };
}

export function makeTest(overrides: Partial<PerformanceTest> = {}): PerformanceTest {
  return {
    id: 1,
    name: "Sprint 30 m",
    kind: "timed_distance",
    kind_label: "Chrono sur distance",
    kind_text: "Chrono sur 30 m",
    distance_m: "30.00",
    duration_s: null,
    attempts: null,
    time_limit_s: null,
    unit: "seconds",
    unit_label: "secondes",
    decimals: 2,
    higher_is_better: false,
    description: "",
    archived: false,
    stopwatch_available: true,
    has_results: false,
    ...overrides,
  };
}

export function makeValue(overrides: Partial<PerformanceValue> = {}): PerformanceValue {
  return {
    outcome: "done",
    time_ms: 4520,
    distance_m: null,
    count: null,
    value: null,
    display: "4,52 s",
    derived: { speed_ms: "6.64", speed_kmh: "23.9", speed_display: "23,9 km/h", speed_ms_display: "6,64 m/s" },
    ...overrides,
  };
}

export function bulkResponse(results: BulkPerformanceResponse["results"]): BulkPerformanceResponse {
  const counts = { created: 0, skipped: 0, refused: 0 };
  for (const r of results) counts[r.outcome] += 1;
  return { run_id: 1, counts, results };
}

export function profileWith(...roles: string[]): MyProfile {
  // Seuls les rôles sont lus pour décider de l'affichage.
  return {
    membership_id: 1,
    club: { id: 1, slug: "demo", name: "Club Test", logo: null, primary_color: "", secondary_color: "" },
    roles: roles.map((role) => ({ role, label: role })),
  } as unknown as MyProfile;
}

export function makeRow(overrides: Partial<PerformanceResultRow> = {}): PerformanceResultRow {
  return {
    id: 11,
    rank: 1,
    player: brief(1, "Alice Durand"),
    attempt_no: 1,
    attempts_count: 1,
    attempts: [],
    method: "stopwatch",
    method_label: "Chrono",
    personal_record: false,
    recorded_by: { id: 9, name: "Coach Dupont" },
    recorded_at: "2026-11-10T10:00:00Z",
    ...makeValue(),
    ...overrides,
  };
}

export function makeResults(overrides: Partial<EventPerformanceResults> = {}): EventPerformanceResults {
  return {
    event_id: 7,
    date: "2026-11-10",
    test: makeTest(),
    scope: "all",
    summary: { measured_count: 2, best: "4,21 s", average: "4,63 s" },
    results: [
      makeRow({ id: 11, rank: 1, player: brief(1, "Alice Durand"), time_ms: 4210, display: "4,21 s", personal_record: true }),
      makeRow({ id: 12, rank: 2, player: brief(2, "Bob Martin"), time_ms: 5050, display: "5,05 s", attempt_no: 2, attempts_count: 2 }),
    ],
    dnf: [],
    window_open: true,
    ...overrides,
  };
}

export function makeDetail(overrides: Partial<PerformanceResultDetail> = {}): PerformanceResultDetail {
  return {
    id: 11,
    event_id: 7,
    date: "2026-11-10",
    test: makeTest(),
    player: brief(1, "Alice Durand"),
    attempt_no: 1,
    method: "stopwatch",
    method_label: "Chrono",
    status: "active",
    recorded_by: { id: 9, name: "Coach Dupont" },
    recorded_at: "2026-11-10T10:00:00Z",
    locked: false,
    corrections: [],
    ...makeValue({ time_ms: 4210, display: "4,21 s" }),
    ...overrides,
  };
}
