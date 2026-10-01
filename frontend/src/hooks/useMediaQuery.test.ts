import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useMediaQuery } from "./useMediaQuery";

interface MockMediaQueryList {
  matches: boolean;
  addEventListener: (type: string, listener: (event: MediaQueryListEvent) => void) => void;
  removeEventListener: (type: string, listener: (event: MediaQueryListEvent) => void) => void;
  listeners: Array<(event: MediaQueryListEvent) => void>;
}

function mockMatchMedia(initialMatches: boolean): MockMediaQueryList {
  const mql: MockMediaQueryList = {
    matches: initialMatches,
    listeners: [],
    addEventListener(_type, listener) {
      mql.listeners.push(listener);
    },
    removeEventListener(_type, listener) {
      mql.listeners = mql.listeners.filter((l) => l !== listener);
    },
  };
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation(() => mql),
  );
  return mql;
}

describe("useMediaQuery", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renvoie l'état initial de la media query", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useMediaQuery("(min-width: 1024px)"));
    expect(result.current).toBe(true);
  });

  it("met à jour la valeur quand la media query change", () => {
    const mql = mockMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery("(min-width: 1024px)"));
    expect(result.current).toBe(false);

    act(() => {
      mql.listeners.forEach((listener) => listener({ matches: true } as MediaQueryListEvent));
    });
    expect(result.current).toBe(true);
  });
});
