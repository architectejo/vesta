import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AttendanceDetail as AttendanceDetailData } from "../../../api/clubBoardDashboard";
import { AttendanceDetail } from "./BoardDetails";

vi.mock("../../../api/clubBoardDashboard", async () => {
  const actual = await vi.importActual<typeof import("../../../api/clubBoardDashboard")>(
    "../../../api/clubBoardDashboard",
  );
  return { ...actual, getBoardSection: vi.fn() };
});

import { getBoardSection } from "../../../api/clubBoardDashboard";

const PERIOD = {
  mode: "month" as const,
  month: "2026-11",
  season_id: null,
  label: "novembre 2026",
  start: "2026-11-01",
  end: "2026-11-30",
  months: ["2026-11"],
};

function detail(): AttendanceDetailData {
  return {
    section: "attendance",
    period: PERIOD,
    summary: {
      events_count: 1,
      unmarked_count: 1,
      average_rate: "80",
      last_rate: "80",
      late_counts_absent: false,
      totals: { expected: 10, present: 8, late: 0, excused: 1, absent: 1 },
      by_kind: {},
      points: [
        { event_id: 1, kind: "session", kind_label: "Séance", date: "2026-11-03", expected: 10, present: 8, late: 0, excused: 1, absent: 1, marked: true, rate: "80" },
      ],
      series: [],
    },
    sessions: {
      count: 2,
      next_offset: null,
      items: [
        { event_id: 1, kind: "session", kind_label: "Séance", date: "2026-11-03", expected: 10, present: 8, late: 0, excused: 1, absent: 1, marked: true, rate: "80" },
        { event_id: 2, kind: "session", kind_label: "Séance", date: "2026-11-10", expected: 10, present: 0, late: 0, excused: 0, absent: 10, marked: false, rate: null },
      ],
    },
  };
}

describe("AttendanceDetail — séance non pointée (club-tableau-de-bord-bureau.md)", () => {
  it("affiche « Non pointée » sans compteur d'absents ni taux, et la séance pointée avec ses compteurs", async () => {
    vi.mocked(getBoardSection).mockResolvedValue(detail() as never);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <AttendanceDetail period={null} currency="USD" />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Non pointée")).toBeInTheDocument();
    expect(screen.queryByText(/absents 10/)).not.toBeInTheDocument();
    expect(screen.getByText(/Présents 8\/10 · retards 0 · excusés 1 · absents 1/)).toBeInTheDocument();
    expect(screen.getByText(/1 séance non pointée, hors moyenne\./)).toBeInTheDocument();
  });
});
